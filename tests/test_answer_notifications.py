"""The asker's side of Unanswered Questions: "your question was answered"
notifications are scoped to the caller's own questions, and degrade to
empty (not 500) before the migration adds user_seen_at."""
import contextlib

import asyncpg
import pytest
from fastapi.testclient import TestClient

import db
import main
from core.auth import get_current_tenant, get_current_user_id

TENANT = "11111111-1111-1111-1111-111111111111"
USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
QID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class FakeConn:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    async def fetch(self, sql, *args):
        self.calls.append((sql, args))
        if self.fail:
            raise asyncpg.UndefinedColumnError("user_seen_at")
        return [{"id": QID, "question": "q?", "answer": "a.", "answered_at": "2026-11-14T00:00:00Z",
                 "conversation_id": None}]

    async def execute(self, sql, *args):
        self.calls.append((sql, args))
        if self.fail:
            raise asyncpg.UndefinedColumnError("user_seen_at")
        return "UPDATE 1"


@pytest.fixture
def env(monkeypatch):
    state = {"conn": FakeConn()}

    @contextlib.asynccontextmanager
    async def fake_tc(_tenant):
        yield state["conn"]

    monkeypatch.setattr(db, "tenant_connection", fake_tc)
    main.app.dependency_overrides[get_current_tenant] = lambda: TENANT
    main.app.dependency_overrides[get_current_user_id] = lambda: USER
    try:
        yield TestClient(main.app), state
    finally:
        main.app.dependency_overrides.clear()


def test_new_answers_are_only_the_callers(env):
    client, state = env
    resp = client.get("/unanswered-questions/me/answered")
    assert resp.status_code == 200
    assert resp.json()[0]["id"] == QID
    sql, args = state["conn"].calls[0]
    assert "user_id = $2" in sql and "status = 'answered'" in sql
    assert args == (TENANT, USER)


@pytest.mark.parametrize("body, expect_ids", [({}, None), ({"ids": [QID]}, [QID])])
def test_mark_seen_is_scoped_to_caller(env, body, expect_ids):
    client, state = env
    resp = client.post("/unanswered-questions/me/answered/seen", json=body)
    assert resp.json() == {"updated": 1}
    sql, args = state["conn"].calls[0]
    assert "user_id = $2" in sql
    assert args[:2] == (TENANT, USER)
    if expect_ids:
        assert args[2] == expect_ids


def test_before_migration_returns_empty_not_500(env):
    client, state = env
    state["conn"] = FakeConn(fail=True)
    assert client.get("/unanswered-questions/me/answered").json() == []
    assert client.post("/unanswered-questions/me/answered/seen", json={}).json() == {"updated": 0}
