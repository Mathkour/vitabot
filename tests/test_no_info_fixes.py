"""Tests for the fixes ported from CP_BOT (company-domain-module-release):

- 9430620: an answer that declines in the model's own words (no [[NO_INFO]]
  marker) is still treated as "no info" by /ask, and Most Frequent Questions
  excludes questions that ended up as a "don't know".
- ae54845: generate_answer forbids referring to an attachment when none is
  being shown.
"""
import contextlib
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import db
import main
from core.auth import get_current_tenant, get_current_user_id
from routers import tenant_analytics
from services import llm

TENANT = "11111111-1111-1111-1111-111111111111"
USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
FALLBACK = "FALLBACK NO-INFO REPLY"


# --- _looks_like_no_info ----------------------------------------------------

@pytest.mark.parametrize("answer", [
    "I don't have enough information to answer that.",
    "  I'm sorry, but I don't have details on that policy.",
    "Unfortunately, I don't have that in the documents.",
    "لا أملك معلومات كافية حول هذا الموضوع.",
    "للأسف لا أملك إجابة على هذا السؤال.",
    "ليس لدي معلومات عن ذلك.",
])
def test_decline_in_own_words_is_detected(answer):
    assert main._looks_like_no_info(answer)


@pytest.mark.parametrize("answer", [
    "To reset your password, open Settings and choose Security.",
    "يمكنك تجديد الاشتراك من صفحة الحساب.",
    # Uncertainty mentioned only well past the lead must not trigger it.
    "To submit a claim, open the Claims page, fill in the member number, attach the "
    "invoice and the prescription, then press Submit and wait for the confirmation "
    "message. If it fails, note that I don't have enough information about your plan.",
    "",
])
def test_real_answer_is_not_flagged(answer):
    assert not main._looks_like_no_info(answer)


# --- /ask routes own-words declines to the no-info path ----------------------

class FakeConn:
    def __init__(self):
        self.assistant_messages = []
        self.media = []

    async def fetchrow(self, sql, *args):
        if sql.startswith("SELECT id FROM bots"):
            return {"id": "bot-1"}
        if sql.startswith("INSERT INTO conversations"):
            return {"id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"}
        if sql.startswith("INSERT INTO messages") and "'assistant'" in sql:
            self.assistant_messages.append(args[2])
            return {"id": "ffffffff-ffff-ffff-ffff-ffffffffffff"}
        raise AssertionError(f"unexpected fetchrow: {sql}")

    async def fetch(self, sql, *args):
        if "FROM media" in sql:
            return self.media
        if "FROM messages" in sql:
            return []
        raise AssertionError(f"unexpected fetch: {sql}")

    async def execute(self, sql, *args):
        pass


@pytest.fixture
def ask_env(monkeypatch):
    conn = FakeConn()
    calls = {"no_info": 0}

    @contextlib.asynccontextmanager
    async def fake_tc(_tenant):
        yield conn

    async def fake_embedding(_text):
        return [0.0]

    async def fake_search_chunk(*_args, **_kwargs):
        return [{"content": "Claims are submitted from the Claims page.", "distance": 0.1}]

    def fake_no_info(_question, tenant_id=None):
        calls["no_info"] += 1
        return FALLBACK

    monkeypatch.setattr(db, "tenant_connection", fake_tc)
    monkeypatch.setattr(main, "get_embedding", fake_embedding)
    monkeypatch.setattr(main, "translate_to_english", lambda q, tenant_id=None: q)
    monkeypatch.setattr(main, "translate_verbatim", lambda t, _lang, tenant_id=None: t)
    monkeypatch.setattr(main, "search_chunk", fake_search_chunk)
    monkeypatch.setattr(main, "generate_no_info_response", fake_no_info)

    main.app.dependency_overrides[get_current_tenant] = lambda: TENANT
    main.app.dependency_overrides[get_current_user_id] = lambda: USER
    try:
        yield TestClient(main.app), conn, calls, monkeypatch
    finally:
        main.app.dependency_overrides.clear()


@pytest.mark.parametrize("model_answer", [
    "[[NO_INFO]] I could not find that.",
    "I don't have enough information about that procedure.",
    "لا أملك معلومات عن هذا الإجراء.",
])
def test_ask_declines_use_no_info_fallback(ask_env, model_answer):
    client, conn, calls, monkeypatch = ask_env
    monkeypatch.setattr(main, "generate_answer", lambda *a, **k: model_answer)

    resp = client.post("/ask", json={"question": "How do I submit a claim?"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answer"] == FALLBACK
    assert body["offer_support"] is True
    assert calls["no_info"] == 1
    assert conn.assistant_messages == [FALLBACK]


def test_ask_real_answer_is_untouched(ask_env):
    client, conn, calls, monkeypatch = ask_env
    real = "Open the Claims page, attach the invoice and press Submit."
    monkeypatch.setattr(main, "generate_answer", lambda *a, **k: real)

    resp = client.post("/ask", json={"question": "How do I submit a claim?"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answer"] == real
    assert body["offer_support"] is False
    assert calls["no_info"] == 0


VIDEO = {
    "id": "99999999-9999-9999-9999-999999999999", "filename": None, "media_type": "link",
    "display_name": None, "display_name_ar": None, "category_id": None,
    "description": "كيفية تفعيل نقاط الولاء للعملاء", "description_ar": "كيفية تفعيل نقاط الولاء للعملاء",
    "url": "https://www.youtube.com/watch?v=abc",
}


@pytest.mark.parametrize("question,expected_start", [
    ("كيف افعل نقاط الولاء؟", "ما عندي خطوات مكتوبة"),
    ("How do I activate loyalty points?", "I don't have written steps"),
])
def test_ask_video_without_written_steps_points_to_video(ask_env, question, expected_start):
    """A matching video but no written answer: point to the video instead of
    saying "I don't know" right above it, and don't log it as unanswered."""
    client, conn, calls, monkeypatch = ask_env
    conn.media = [VIDEO]
    monkeypatch.setattr(main, "select_matching_video", lambda q, videos, tenant_id=None: videos[0])
    monkeypatch.setattr(main, "generate_answer", lambda *a, **k: "[[NO_INFO]] nothing written")

    body = client.post("/ask", json={"question": question}).json()

    assert body["answer"].startswith(expected_start)
    assert "نقاط الولاء" in body["answer"]
    assert body["media"]["url"] == VIDEO["url"]
    assert body["offer_support"] is False
    assert calls["no_info"] == 0


def test_ask_video_selection_failure_falls_back_to_keywords(ask_env):
    client, conn, calls, monkeypatch = ask_env
    conn.media = [VIDEO]

    def boom(*_a, **_k):
        raise RuntimeError("gemini down")

    monkeypatch.setattr(main, "select_matching_video", boom)
    monkeypatch.setattr(main, "generate_answer", lambda *a, **k: "Open Loyalty and enable it.")

    body = client.post("/ask", json={"question": "تفعيل نقاط الولاء للعملاء"}).json()

    assert body["media"]["url"] == VIDEO["url"]
    assert body["answer"] == "Open Loyalty and enable it."


def test_ask_no_matching_video_attaches_nothing(ask_env):
    client, conn, calls, monkeypatch = ask_env
    conn.media = [VIDEO]
    monkeypatch.setattr(main, "select_matching_video", lambda *a, **k: None)
    monkeypatch.setattr(main, "generate_answer", lambda *a, **k: "Open the Claims page.")

    body = client.post("/ask", json={"question": "How do I submit a claim?"}).json()

    assert body["media"] is None


# --- generate_answer phantom-attachment rule ----------------------------------

def _captured_system_prompt(monkeypatch, media_hint):
    captured = {}

    def generate_content(model, contents, config):
        captured["system"] = config.system_instruction
        return SimpleNamespace(text="ok")

    monkeypatch.setattr(llm, "gemini_client", SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    monkeypatch.setattr(llm, "log_ai_prediction", lambda **_k: None)
    llm.generate_answer("q", ["ctx"], media_hint, [], tenant_id=TENANT)
    return captured["system"]


def test_phantom_attachment_rule_when_nothing_attached(monkeypatch):
    system = _captured_system_prompt(monkeypatch, media_hint=None)
    assert "NO-PHANTOM-ATTACHMENT RULE" in system
    assert "A helpful video titled" not in system


def test_video_note_when_media_attached(monkeypatch):
    system = _captured_system_prompt(monkeypatch, media_hint="Claims walkthrough")
    assert "A helpful video titled 'Claims walkthrough'" in system
    assert "NO-PHANTOM-ATTACHMENT RULE" not in system


# --- analytics: Most Frequent Questions excludes no-info questions -----------

def test_top_questions_and_digest_exclude_no_info(monkeypatch):
    queries = []

    class AnalyticsConn:
        def transaction(self):
            return contextlib.asynccontextmanager(_nothing)()

        async def fetch(self, sql, *args):
            queries.append(sql)
            return []

        async def fetchrow(self, sql, *args):
            queries.append(sql)
            return {"thumbs_up": 0, "thumbs_down": 0}

        async def fetchval(self, sql, *args):
            queries.append(sql)
            return 0

    import asyncio
    asyncio.run(tenant_analytics._build_tenant_digest(AnalyticsConn(), TENANT, 7))

    top = [q for q in queries if "endpoint = 'ask'" in q]
    assert top, "digest should query the 'ask' rows"
    assert all("NOT EXISTS" in q and "'no_info_response'" in q for q in top)


async def _nothing():
    yield
