"""Unanswered Questions: recording must never break /ask, the endpoints are
admin-only, and a missing table (migration not applied yet) is a clear 503
rather than a crash. The full flow is exercised end to end against a real
database separately; these pin the failure modes without one."""
import asyncio
import contextlib

import asyncpg
import pytest
from fastapi.testclient import TestClient

import db
import main
from core.auth import get_current_role, get_current_tenant, get_current_user_id
from routers import unanswered_questions as uq

TENANT = "11111111-1111-1111-1111-111111111111"
USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


class RaisingConn:
    def __init__(self, exc):
        self.exc = exc

    def transaction(self):
        return _AsyncNull()

    async def execute(self, *_a):
        raise self.exc

    async def fetch(self, *_a):
        raise self.exc

    async def fetchval(self, *_a):
        raise self.exc

    async def fetchrow(self, *_a):
        raise self.exc


class _AsyncNull:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.mark.parametrize("exc", [
    asyncpg.UndefinedTableError("relation \"unanswered_questions\" does not exist"),
    RuntimeError("anything else"),
])
def test_recording_never_raises(exc):
    asyncio.run(uq.record_unanswered_question(RaisingConn(exc), TENANT, USER, None, None, "q", None))


@pytest.fixture
def client(monkeypatch):
    state = {"role": "admin", "exc": asyncpg.UndefinedTableError("missing")}

    @contextlib.asynccontextmanager
    async def fake_tc(_tenant):
        yield RaisingConn(state["exc"])

    monkeypatch.setattr(db, "tenant_connection", fake_tc)
    main.app.dependency_overrides[get_current_tenant] = lambda: TENANT
    main.app.dependency_overrides[get_current_user_id] = lambda: USER
    main.app.dependency_overrides[get_current_role] = lambda: state["role"]
    try:
        yield TestClient(main.app), state
    finally:
        main.app.dependency_overrides.clear()


@pytest.mark.parametrize("method, path, body", [
    ("get", "/unanswered-questions", None),
    ("post", "/unanswered-questions/x/answer", {"answer": "a"}),
    ("delete", "/unanswered-questions/x/answer", None),
    ("post", "/unanswered-questions/x/dismiss", None),
    ("post", "/unanswered-questions/x/reopen", None),
])
def test_missing_table_is_a_clear_503(client, method, path, body):
    c, _ = client
    resp = getattr(c, method)(path, **({"json": body} if body else {}))
    assert resp.status_code == 503
    assert "migrations/2026-11-10_unanswered_questions.sql" in resp.json()["detail"]


def test_open_count_is_zero_without_the_table(client):
    c, _ = client
    resp = c.get("/unanswered-questions/open-count")
    assert resp.status_code == 200 and resp.json() == {"count": 0}


@pytest.mark.parametrize("role", ["member", "company_admin", "bank"])
@pytest.mark.parametrize("method, path, body", [
    ("get", "/unanswered-questions", None),
    ("get", "/unanswered-questions/open-count", None),
    ("post", "/unanswered-questions/x/answer", {"answer": "a"}),
    ("delete", "/unanswered-questions/x/answer", None),
    ("post", "/unanswered-questions/x/dismiss", None),
])
def test_non_admins_are_refused(client, role, method, path, body):
    c, state = client
    state["role"] = role
    resp = getattr(c, method)(path, **({"json": body} if body else {}))
    assert resp.status_code == 403
