"""Admin password reset (POST /users/{id}/password): who may reset whom,
validation, and that the user is signed out everywhere."""
import contextlib

import pytest
from fastapi.testclient import TestClient

import db
import main
from core.auth import UserScope, get_current_user_id, require_admin_or_company_admin
from core.security import verify_password

TENANT = "11111111-1111-1111-1111-111111111111"
ADMIN = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TARGET = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
COMPANY = "cccccccc-cccc-cccc-cccc-cccccccccccc"
OTHER_COMPANY = "dddddddd-dddd-dddd-dddd-dddddddddddd"


class FakeConn:
    def __init__(self, target):
        self.target = target
        self.updates = []

    async def fetchrow(self, sql, *args):
        assert sql.startswith("SELECT id, role, company_id")
        return self.target

    async def execute(self, sql, *args):
        assert sql.startswith("UPDATE users SET password_hash")
        assert "token_version = token_version + 1" in sql
        self.updates.append(args)


@pytest.fixture
def env(monkeypatch):
    state = {"conn": None, "scope": UserScope(tenant_id=TENANT, role="admin", company_id=None), "logged": []}

    @contextlib.asynccontextmanager
    async def fake_tc(_tenant):
        yield state["conn"]

    async def fake_log(tenant_id, actor_id, action, label):
        state["logged"].append((action, label))

    monkeypatch.setattr(db, "tenant_connection", fake_tc)
    monkeypatch.setattr(main, "log_detached", fake_log)
    main.limiter.enabled = False
    main.app.dependency_overrides[require_admin_or_company_admin] = lambda: state["scope"]
    main.app.dependency_overrides[get_current_user_id] = lambda: ADMIN
    try:
        yield TestClient(main.app), state
    finally:
        main.app.dependency_overrides.clear()
        main.limiter.enabled = True


def _target(role="member", company_id=COMPANY):
    return {"id": TARGET, "role": role, "company_id": company_id, "label": "ahmed"}


def _reset(client, password="NewPass123"):
    return client.post(f"/users/{TARGET}/password", json={"password": password})


def test_admin_resets_member_password_and_signs_them_out(env):
    client, state = env
    state["conn"] = FakeConn(_target())

    resp = _reset(client)

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "updated", "signed_out": False}
    (hashed, user_id, tenant_id), = state["conn"].updates
    assert verify_password("NewPass123", hashed)
    assert (user_id, tenant_id) == (TARGET, TENANT)
    assert state["logged"] == [("user.password_reset", "ahmed")]


def test_short_password_is_rejected(env):
    client, state = env
    state["conn"] = FakeConn(_target())
    assert _reset(client, "short").status_code == 400
    assert state["conn"].updates == []


def test_superadmin_password_cannot_be_reset_here(env):
    client, state = env
    state["conn"] = FakeConn(_target(role="superadmin", company_id=None))
    assert _reset(client).status_code == 403
    assert state["conn"].updates == []


@pytest.mark.parametrize("target, allowed", [
    (_target("member", COMPANY), True),
    (_target("member", OTHER_COMPANY), False),   # another company's member
    (_target("company_admin", COMPANY), False),  # a peer company admin
    (_target("admin", None), False),              # a tenant admin
])
def test_company_admin_reach(env, target, allowed):
    client, state = env
    state["scope"] = UserScope(tenant_id=TENANT, role="company_admin", company_id=COMPANY)
    state["conn"] = FakeConn(target)

    resp = _reset(client)

    assert resp.status_code == (200 if allowed else 403), resp.text
    assert bool(state["conn"].updates) is allowed


def test_unknown_user_is_404(env):
    client, state = env
    state["conn"] = FakeConn(None)
    assert _reset(client).status_code == 404
