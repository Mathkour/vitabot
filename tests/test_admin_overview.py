"""Admin-only access for the new admin pages' endpoints, and the activity
log never breaking the action it records. The full flows are exercised end
to end against a real database separately."""
import asyncio

import asyncpg
import pytest
from fastapi.testclient import TestClient

import main
from core.auth import get_current_role, get_current_tenant, get_current_user_id
from services.activity import log_activity

TENANT = "11111111-1111-1111-1111-111111111111"
USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

ADMIN_ENDPOINTS = [
    ("get", "/dashboard/summary", None),
    ("get", "/activity-log", None),
    ("get", "/conversations/search", None),
    ("get", "/analytics/companies", None),
    ("get", "/answer-feedback", None),
    ("post", "/answer-feedback/x/fix", {"answer": "a"}),
    ("post", "/answer-feedback/x/dismiss", None),
    ("post", "/answer-feedback/x/reopen", None),
    ("post", "/faq", {"question": "q", "answer": "a"}),
    ("delete", "/faq/x", None),
    ("post", "/users/import/confirm", {"mapping": {"email": 0, "username": 1}, "rows": []}),
    ("post", "/media/link", {"url": "u", "description": "d", "category_id": "c"}),
]


@pytest.fixture
def client():
    state = {"role": "member"}
    main.app.dependency_overrides[get_current_tenant] = lambda: TENANT
    main.app.dependency_overrides[get_current_user_id] = lambda: USER
    main.app.dependency_overrides[get_current_role] = lambda: state["role"]
    try:
        yield TestClient(main.app), state
    finally:
        main.app.dependency_overrides.clear()


@pytest.mark.parametrize("role", ["member", "company_admin", "bank"])
@pytest.mark.parametrize("method, path, body", ADMIN_ENDPOINTS)
def test_non_admins_are_refused(client, role, method, path, body):
    c, state = client
    state["role"] = role
    resp = getattr(c, method)(path, **({"json": body} if body else {}))
    assert resp.status_code == 403, (path, resp.status_code, resp.text)


class _Savepoint:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class BrokenConn:
    def __init__(self, exc):
        self.exc = exc

    def transaction(self):
        return _Savepoint()

    async def execute(self, *_a):
        raise self.exc


@pytest.mark.parametrize("exc", [asyncpg.UndefinedTableError("activity_log missing"), RuntimeError("boom")])
def test_activity_log_never_raises(exc):
    asyncio.run(log_activity(BrokenConn(exc), TENANT, USER, "faq.create", "q"))
