import asyncio
import contextlib
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import db
from core.auth import get_current_tenant
from routers import faq_categories

TENANT_A = "819c1132-f67b-42a1-ad46-50e051d398d7"
TENANT_B = "0fdf57fe-d937-4c38-8a67-9836c4aef3a4"


class FakeConn:
    """In-memory faq_categories/faq_items, enough to exercise the router's
    SQL shapes without a real database."""

    def __init__(self):
        self.categories: dict[str, dict] = {}  # id -> row
        self.faqs: dict[str, dict] = {}  # id -> row
        self.error_solutions: dict[str, dict] = {}  # id -> row

    async def fetch(self, sql, *args):
        if sql.startswith("SELECT id, name_ar, name_en, display_order, created_at FROM faq_categories"):
            tenant_id = args[0]
            rows = [c for c in self.categories.values() if c["tenant_id"] == tenant_id]
            rows.sort(key=lambda c: (c["display_order"], c["created_at"]))
            return rows
        if sql.startswith("SELECT id, name_ar, name_en, display_order FROM faq_categories"):
            # Summary-mode category list (no created_at in the SELECT list) —
            # distinct from the admin list query above.
            tenant_id = args[0]
            rows = [c for c in self.categories.values() if c["tenant_id"] == tenant_id]
            rows.sort(key=lambda c: (c["display_order"], c["created_at"]))
            return rows
        if sql.startswith("SELECT id, question, answer, question_ar, answer_ar, category_id FROM faq_items"):
            tenant_id = args[0]
            rows = [f for f in self.faqs.values() if f["tenant_id"] == tenant_id]
            if "category_id IS NULL" in sql:
                rows = [f for f in rows if f["category_id"] is None]
            rows.sort(key=lambda f: f["created_at"])
            return rows
        if sql.startswith("SELECT id, error_text, solution_text, error_text_ar, solution_text_ar, category_id FROM error_solutions"):
            tenant_id = args[0]
            rows = [e for e in self.error_solutions.values() if e["tenant_id"] == tenant_id]
            if "category_id IS NULL" in sql:
                rows = [e for e in rows if e["category_id"] is None]
            rows.sort(key=lambda e: e["created_at"])
            return rows
        if sql.startswith("SELECT id, question, answer, question_ar, answer_ar, created_at, 'faq' AS source FROM faq_items"):
            if "category_id = $1 AND tenant_id = $2" in sql:
                category_id, tenant_id = args
                out = [
                    dict(f, source="faq") for f in self.faqs.values()
                    if f["category_id"] == category_id and f["tenant_id"] == tenant_id
                ]
            else:  # search-corpus: tenant_id = $1 AND category_id IS NOT NULL
                tenant_id = args[0]
                out = [
                    dict(f, source="faq") for f in self.faqs.values()
                    if f["tenant_id"] == tenant_id and f["category_id"] is not None
                ]
            return sorted(out, key=lambda f: f["created_at"])
        if sql.startswith("SELECT id, error_text AS question, solution_text AS answer"):
            if "category_id = $1 AND tenant_id = $2" in sql:
                category_id, tenant_id = args
                matches = [
                    e for e in self.error_solutions.values()
                    if e["category_id"] == category_id and e["tenant_id"] == tenant_id
                ]
            else:  # search-corpus: tenant_id = $1 AND category_id IS NOT NULL
                tenant_id = args[0]
                matches = [
                    e for e in self.error_solutions.values()
                    if e["tenant_id"] == tenant_id and e["category_id"] is not None
                ]
            out = [
                {
                    "id": e["id"], "question": e["error_text"], "answer": e["solution_text"],
                    "question_ar": e["error_text_ar"], "answer_ar": e["solution_text_ar"],
                    "created_at": e["created_at"], "source": "error_solution",
                }
                for e in matches
            ]
            return sorted(out, key=lambda e: e["created_at"])
        raise AssertionError(f"unexpected fetch: {sql}")

    async def fetchrow(self, sql, *args):
        if sql.strip().startswith("INSERT INTO faq_categories"):
            tenant_id, name_ar, name_en, display_order = args
            if display_order is None:
                existing = [c["display_order"] for c in self.categories.values() if c["tenant_id"] == tenant_id]
                display_order = (max(existing) + 1) if existing else 0
            row = {
                "id": str(uuid.uuid4()), "tenant_id": tenant_id, "name_ar": name_ar, "name_en": name_en,
                "display_order": display_order, "created_at": len(self.categories),
            }
            self.categories[row["id"]] = row
            return {k: v for k, v in row.items() if k != "tenant_id"}
        if sql.strip().startswith("UPDATE faq_categories"):
            name_ar, name_en, display_order, category_id, tenant_id = args
            row = self.categories.get(category_id)
            if row is None or row["tenant_id"] != tenant_id:
                return None
            row["name_ar"], row["name_en"] = name_ar, name_en
            if display_order is not None:
                row["display_order"] = display_order
            return {k: v for k, v in row.items() if k != "tenant_id"}
        if sql.startswith("SELECT id, name_ar, name_en, display_order FROM faq_categories WHERE id ="):
            category_id, tenant_id = args
            row = self.categories.get(category_id)
            if row is None or row["tenant_id"] != tenant_id:
                return None
            return {k: v for k, v in row.items() if k != "tenant_id"}
        raise AssertionError(f"unexpected fetchrow: {sql}")

    async def fetchval(self, sql, *args):
        if sql.startswith("SELECT 1 FROM faq_categories WHERE id ="):
            category_id, tenant_id = args
            row = self.categories.get(category_id)
            return 1 if row and row["tenant_id"] == tenant_id else None
        if sql.startswith("SELECT count(*) FROM faq_items WHERE category_id ="):
            category_id, tenant_id = args
            return sum(1 for f in self.faqs.values() if f["category_id"] == category_id and f["tenant_id"] == tenant_id)
        if sql.startswith("SELECT count(*) FROM error_solutions WHERE category_id ="):
            category_id, tenant_id = args
            return sum(
                1 for e in self.error_solutions.values()
                if e["category_id"] == category_id and e["tenant_id"] == tenant_id
            )
        raise AssertionError(f"unexpected fetchval: {sql}")

    async def execute(self, sql, *args):
        if sql.startswith("DELETE FROM faq_categories"):
            category_id, tenant_id = args
            row = self.categories.get(category_id)
            if row is None or row["tenant_id"] != tenant_id:
                return "DELETE 0"
            del self.categories[category_id]
            for f in self.faqs.values():  # mirror ON DELETE SET NULL
                if f["category_id"] == category_id:
                    f["category_id"] = None
            return "DELETE 1"
        raise AssertionError(f"unexpected execute: {sql}")


@pytest.fixture
def env(monkeypatch):
    conn = FakeConn()

    @contextlib.asynccontextmanager
    async def fake_tc(_tenant):
        yield conn

    monkeypatch.setattr(db, "tenant_connection", fake_tc)
    app = FastAPI()
    app.include_router(faq_categories.router)
    app.dependency_overrides[get_current_tenant] = lambda: TENANT_A
    return TestClient(app), conn


@pytest.fixture
def vita_care_env(monkeypatch):
    """Same as `env`, but the overridden tenant *is* Vita Care, so the
    error_solutions merge branch in /faq/grouped and the
    require_vita_care_tenant-gated /admin/error-solutions both activate."""
    import core.auth as core_auth

    conn = FakeConn()

    @contextlib.asynccontextmanager
    async def fake_tc(_tenant):
        yield conn

    monkeypatch.setattr(db, "tenant_connection", fake_tc)
    monkeypatch.setattr(core_auth, "VITA_CARE_TENANT_ID", TENANT_A)
    monkeypatch.setattr(faq_categories, "VITA_CARE_TENANT_ID", TENANT_A)
    app = FastAPI()
    app.include_router(faq_categories.router)
    app.dependency_overrides[get_current_tenant] = lambda: TENANT_A
    return TestClient(app), conn


def test_create_and_list_categories(env):
    client, conn = env
    r = client.post("/admin/faq-categories", json={"name_ar": "عام", "name_en": "General"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["display_order"] == 0 and body["name_en"] == "General"

    r2 = client.post("/admin/faq-categories", json={"name_ar": "دعم", "name_en": "Support"})
    assert r2.json()["display_order"] == 1  # auto-incremented, no explicit value given

    listed = client.get("/admin/faq-categories").json()
    assert [c["name_en"] for c in listed] == ["General", "Support"]


def test_create_category_explicit_display_order(env):
    client, conn = env
    r = client.post("/admin/faq-categories", json={"name_ar": "أ", "name_en": "A", "display_order": 5})
    assert r.json()["display_order"] == 5


def test_update_category(env):
    client, conn = env
    cat = client.post("/admin/faq-categories", json={"name_ar": "عام", "name_en": "General"}).json()
    r = client.put(f"/admin/faq-categories/{cat['id']}", json={"name_ar": "عام2", "name_en": "General2"})
    assert r.status_code == 200
    assert r.json()["name_en"] == "General2"
    assert r.json()["display_order"] == 0  # unchanged, since not passed


def test_update_unknown_category_404(env):
    client, _ = env
    r = client.put(f"/admin/faq-categories/{uuid.uuid4()}", json={"name_ar": "x", "name_en": "x"})
    assert r.status_code == 404


def test_delete_category_sets_null_on_faqs(env):
    client, conn = env
    cat = client.post("/admin/faq-categories", json={"name_ar": "عام", "name_en": "General"}).json()
    conn.faqs["f1"] = {
        "id": "f1", "tenant_id": TENANT_A, "question": "Q1", "answer": "A1",
        "question_ar": None, "answer_ar": None, "category_id": cat["id"], "created_at": 0,
    }

    r = client.delete(f"/admin/faq-categories/{cat['id']}")
    assert r.status_code == 200
    assert conn.faqs["f1"]["category_id"] is None  # mirrors ON DELETE SET NULL


def test_delete_unknown_category_404(env):
    client, _ = env
    assert client.delete(f"/admin/faq-categories/{uuid.uuid4()}").status_code == 404


def test_admin_uncategorized_filter(env):
    client, conn = env
    cat = client.post("/admin/faq-categories", json={"name_ar": "عام", "name_en": "General"}).json()
    conn.faqs["f1"] = {
        "id": "f1", "tenant_id": TENANT_A, "question": "Categorized", "answer": "A",
        "question_ar": None, "answer_ar": None, "category_id": cat["id"], "created_at": 0,
    }
    conn.faqs["f2"] = {
        "id": "f2", "tenant_id": TENANT_A, "question": "Uncategorized", "answer": "A",
        "question_ar": None, "answer_ar": None, "category_id": None, "created_at": 1,
    }

    all_faqs = client.get("/admin/faqs").json()
    assert {f["question"] for f in all_faqs} == {"Categorized", "Uncategorized"}

    uncategorized = client.get("/admin/faqs", params={"uncategorized": "true"}).json()
    assert [f["question"] for f in uncategorized] == ["Uncategorized"]


def _add_faq(conn, faq_id, category_id, question, created_at=0):
    conn.faqs[faq_id] = {
        "id": faq_id, "tenant_id": TENANT_A, "question": question, "answer": "A",
        "question_ar": None, "answer_ar": None, "category_id": category_id, "created_at": created_at,
    }


def _add_error_solution(conn, es_id, category_id, error_text, created_at=0):
    conn.error_solutions[es_id] = {
        "id": es_id, "tenant_id": TENANT_A, "error_text": error_text, "solution_text": "fix",
        "error_text_ar": None, "solution_text_ar": None, "category_id": category_id, "created_at": created_at,
    }


# ──────────── /faq/grouped: summary mode (no category_id) ────────────

def test_grouped_summary_excludes_uncategorized_and_empty_categories(env):
    client, conn = env
    cat_with_faqs = client.post("/admin/faq-categories", json={"name_ar": "عام", "name_en": "General"}).json()
    client.post("/admin/faq-categories", json={"name_ar": "فارغ", "name_en": "Empty"})  # no FAQs linked

    _add_faq(conn, "f1", cat_with_faqs["id"], "Categorized Q")
    _add_faq(conn, "f2", None, "Uncategorized Q")

    summary = client.get("/faq/grouped").json()
    assert len(summary) == 1  # "Empty" category never appears
    assert summary[0]["name_en"] == "General"
    assert summary[0]["total"] == 1
    assert "faqs" not in summary[0]  # summary mode carries no item text, by design


def test_grouped_summary_counts_multiple_faqs(env):
    client, conn = env
    cat = client.post("/admin/faq-categories", json={"name_ar": "عام", "name_en": "General"}).json()
    for i in range(12):
        _add_faq(conn, f"f{i}", cat["id"], f"Q{i}", created_at=i)

    summary = client.get("/faq/grouped").json()
    assert summary[0]["total"] == 12


# ──────────── /faq/grouped?category_id=...: paginated detail mode ────────

def test_grouped_detail_paginates_at_10_per_page(env):
    client, conn = env
    cat = client.post("/admin/faq-categories", json={"name_ar": "عام", "name_en": "General"}).json()
    for i in range(12):
        _add_faq(conn, f"f{i}", cat["id"], f"Q{i}", created_at=i)

    page1 = client.get("/faq/grouped", params={"category_id": cat["id"]}).json()
    assert page1["total"] == 12
    assert page1["total_pages"] == 2
    assert page1["page"] == 1
    assert len(page1["faqs"]) == 10
    assert [f["question"] for f in page1["faqs"]] == [f"Q{i}" for i in range(10)]

    page2 = client.get("/faq/grouped", params={"category_id": cat["id"], "page": 2}).json()
    assert page2["page"] == 2
    assert [f["question"] for f in page2["faqs"]] == ["Q10", "Q11"]


def test_grouped_detail_unknown_category_404(env):
    client, _ = env
    r = client.get("/faq/grouped", params={"category_id": str(uuid.uuid4())})
    assert r.status_code == 404


def test_grouped_detail_cross_tenant_category_404(env):
    client, conn = env
    conn.categories["c1"] = {
        "id": "c1", "tenant_id": TENANT_B, "name_ar": "x", "name_en": "x", "display_order": 0, "created_at": 0,
    }
    r = client.get("/faq/grouped", params={"category_id": "c1"})
    assert r.status_code == 404


def test_categories_are_tenant_scoped(env):
    client, conn = env
    client.post("/admin/faq-categories", json={"name_ar": "عام", "name_en": "General"})

    app_b = FastAPI()
    app_b.include_router(faq_categories.router)
    app_b.dependency_overrides[get_current_tenant] = lambda: TENANT_B

    @contextlib.asynccontextmanager
    async def fake_tc(_tenant):
        yield conn

    import db as _db
    orig = _db.tenant_connection
    _db.tenant_connection = fake_tc
    try:
        client_b = TestClient(app_b)
        assert client_b.get("/admin/faq-categories").json() == []
    finally:
        _db.tenant_connection = orig


class _FakeValidateConn:
    def __init__(self, categories):
        self.categories = categories  # (id, tenant_id) -> True

    async def fetchval(self, sql, *args):
        category_id, tenant_id = args
        return 1 if (category_id, tenant_id) in self.categories else None


def test_validate_category_id_none_is_ok():
    asyncio.run(faq_categories.validate_category_id(_FakeValidateConn({}), TENANT_A, None))


def test_validate_category_id_own_tenant_ok():
    conn = _FakeValidateConn({("cat-1", TENANT_A)})
    asyncio.run(faq_categories.validate_category_id(conn, TENANT_A, "cat-1"))


def test_validate_category_id_cross_tenant_rejected():
    from fastapi import HTTPException

    conn = _FakeValidateConn({("cat-1", TENANT_B)})  # belongs to a different tenant
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(faq_categories.validate_category_id(conn, TENANT_A, "cat-1"))
    assert exc_info.value.status_code == 400


# ──────────── Vita Care: Error Solutions merged into the accordion ────────

def test_grouped_summary_counts_include_error_solutions_for_vita_care(vita_care_env):
    client, conn = vita_care_env
    cat = client.post("/admin/faq-categories", json={"name_ar": "عام", "name_en": "General"}).json()
    _add_faq(conn, "f1", cat["id"], "A real FAQ")
    _add_error_solution(conn, "e1", cat["id"], "Some error")

    summary = client.get("/faq/grouped").json()
    assert summary[0]["total"] == 2  # 1 FAQ + 1 error solution


def test_grouped_detail_merges_error_solutions_for_vita_care(vita_care_env):
    client, conn = vita_care_env
    cat = client.post("/admin/faq-categories", json={"name_ar": "عام", "name_en": "General"}).json()

    _add_faq(conn, "f1", cat["id"], "A real FAQ", created_at=0)
    _add_error_solution(conn, "e1", cat["id"], "Some error", created_at=1)

    detail = client.get("/faq/grouped", params={"category_id": cat["id"]}).json()
    assert detail["total"] == 2
    items = detail["faqs"]
    by_source = {item["source"]: item for item in items}
    assert by_source["faq"]["question"] == "A real FAQ"
    assert by_source["error_solution"]["question"] == "Some error"
    assert by_source["error_solution"]["answer"] == "fix"


def test_grouped_detail_excludes_uncategorized_error_solution_for_vita_care(vita_care_env):
    client, conn = vita_care_env
    cat = client.post("/admin/faq-categories", json={"name_ar": "عام", "name_en": "General"}).json()

    _add_faq(conn, "f1", cat["id"], "Categorized FAQ")
    _add_error_solution(conn, "e1", None, "Uncategorized error")

    detail = client.get("/faq/grouped", params={"category_id": cat["id"]}).json()
    assert [item["question"] for item in detail["faqs"]] == ["Categorized FAQ"]


def test_non_vita_care_tenant_unaffected_by_error_solutions(env):
    """Regression guard: /faq/grouped for a non-Vita-Care tenant must never
    even attempt to query error_solutions (FakeConn would raise
    AssertionError on an unexpected query if it tried)."""
    client, conn = env
    cat = client.post("/admin/faq-categories", json={"name_ar": "عام", "name_en": "General"}).json()
    _add_faq(conn, "f1", cat["id"], "Q")

    summary = client.get("/faq/grouped").json()
    assert summary[0]["total"] == 1

    detail = client.get("/faq/grouped", params={"category_id": cat["id"]}).json()
    assert len(detail["faqs"]) == 1
    assert detail["faqs"][0]["source"] == "faq"


# ──────────── /faq/search-corpus ────────────

def test_search_corpus_is_flat_and_unpaginated(env):
    client, conn = env
    cat = client.post("/admin/faq-categories", json={"name_ar": "عام", "name_en": "General"}).json()
    for i in range(15):
        _add_faq(conn, f"f{i}", cat["id"], f"Q{i}", created_at=i)
    _add_faq(conn, "uncat", None, "Uncategorized, must not appear", created_at=99)

    corpus = client.get("/faq/search-corpus").json()
    assert len(corpus) == 15  # no 10-per-page limit here — this feeds client-side search
    assert "Uncategorized, must not appear" not in [c["question"] for c in corpus]


def test_search_corpus_merges_error_solutions_for_vita_care(vita_care_env):
    client, conn = vita_care_env
    cat = client.post("/admin/faq-categories", json={"name_ar": "عام", "name_en": "General"}).json()
    _add_faq(conn, "f1", cat["id"], "A FAQ")
    _add_error_solution(conn, "e1", cat["id"], "An error")
    _add_error_solution(conn, "e2", None, "Uncategorized error")

    corpus = client.get("/faq/search-corpus").json()
    questions = {c["question"] for c in corpus}
    assert questions == {"A FAQ", "An error"}


def test_admin_error_solutions_uncategorized_filter(vita_care_env):
    client, conn = vita_care_env
    cat = client.post("/admin/faq-categories", json={"name_ar": "عام", "name_en": "General"}).json()
    conn.error_solutions["e1"] = {
        "id": "e1", "tenant_id": TENANT_A, "error_text": "Categorized error", "solution_text": "fix",
        "error_text_ar": None, "solution_text_ar": None, "category_id": cat["id"], "created_at": 0,
    }
    conn.error_solutions["e2"] = {
        "id": "e2", "tenant_id": TENANT_A, "error_text": "Uncategorized error", "solution_text": "fix",
        "error_text_ar": None, "solution_text_ar": None, "category_id": None, "created_at": 1,
    }

    all_es = client.get("/admin/error-solutions").json()
    assert {e["error_text"] for e in all_es} == {"Categorized error", "Uncategorized error"}

    uncategorized = client.get("/admin/error-solutions", params={"uncategorized": "true"}).json()
    assert [e["error_text"] for e in uncategorized] == ["Uncategorized error"]
