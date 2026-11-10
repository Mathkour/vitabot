"""Ask Odoo access: a company user only ever reaches their own company's
Odoo (via their client connection), Vita Care's own staff (no company, no
client key) reach Vita Care's Odoo, and nobody falls back to Vita Care's
Odoo data just because they lack a client connection."""
import contextlib

import pytest
from fastapi.testclient import TestClient

import core.auth
import db
import main
from core.auth import get_current_tenant, get_current_user_id

VITA_CARE = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT = "22222222-2222-2222-2222-222222222222"
USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
COMPANY = "cccccccc-cccc-cccc-cccc-cccccccccccc"
CLIENT_CONN = {"url": "https://acme.example", "db": "acme", "username": "bot", "password": "pw"}


class FakeConn:
    def __init__(self, user):
        self.user = user

    async def fetchrow(self, sql, *args):
        if sql.startswith("SELECT company_id, odoo_client_key FROM users"):
            return self.user
        if sql.startswith("SELECT email, username FROM users"):
            return {"email": "u@x.com", "username": "u"}
        raise AssertionError(f"unexpected fetchrow: {sql}")


@pytest.fixture
def env(monkeypatch):
    state = {"tenant": VITA_CARE, "user": None, "connections": {}, "agent_calls": [], "embedded": False}

    @contextlib.asynccontextmanager
    async def fake_tc(_tenant):
        yield FakeConn(state["user"])

    async def fake_client_conn(client_key):
        return state["connections"].get(client_key)

    async def fake_embedding(_q):
        state["embedded"] = True
        return [0.0]

    async def fake_search_chunk(*_a, **_k):
        return []

    def fake_agent(question, **kwargs):
        state["agent_calls"].append(kwargs["client_connection"])
        return {"answer": "ok", "chart": None}

    monkeypatch.setattr(core.auth, "VITA_CARE_TENANT_ID", VITA_CARE)
    monkeypatch.setattr(db, "tenant_connection", fake_tc)
    monkeypatch.setattr(main.odoo_service, "get_client_odoo_connection", fake_client_conn)
    monkeypatch.setattr(main, "get_embedding", fake_embedding)
    monkeypatch.setattr(main, "search_chunk", fake_search_chunk)
    monkeypatch.setattr(main, "odoo_agent_ask", fake_agent)
    monkeypatch.setattr(main, "get_sales_summary", lambda client=None: {"client": client is not None})
    monkeypatch.setattr(main, "get_top_products", lambda client=None: [])
    monkeypatch.setattr(main, "get_customer_summary", lambda client=None: {})

    main.app.dependency_overrides[get_current_tenant] = lambda: state["tenant"]
    main.app.dependency_overrides[get_current_user_id] = lambda: USER
    try:
        yield TestClient(main.app), state
    finally:
        main.app.dependency_overrides.clear()


def _ask(client):
    return client.post("/odoo/ask", json={"question": "top customers?"})


def test_vita_care_staff_use_vita_care_odoo(env):
    client, state = env
    state["user"] = {"company_id": None, "odoo_client_key": None}

    assert client.get("/odoo/access").json() == {"allowed": True, "source": "vita_care", "reason": None}
    resp = _ask(client)
    assert resp.status_code == 200, resp.text
    assert state["agent_calls"] == [None]  # None = Vita Care's own Odoo


def test_company_user_uses_own_company_odoo(env):
    client, state = env
    state["user"] = {"company_id": COMPANY, "odoo_client_key": "acme"}
    state["connections"] = {"acme": CLIENT_CONN}

    assert client.get("/odoo/access").json()["source"] == "company"
    resp = _ask(client)
    assert resp.status_code == 200, resp.text
    assert state["agent_calls"] == [CLIENT_CONN]


def test_client_key_without_company_still_uses_client_odoo(env):
    """An SSO user whose company slug was lost still belongs to that client's
    Odoo, never Vita Care's."""
    client, state = env
    state["user"] = {"company_id": None, "odoo_client_key": "acme"}
    state["connections"] = {"acme": CLIENT_CONN}

    assert _ask(client).status_code == 200
    assert state["agent_calls"] == [CLIENT_CONN]


@pytest.mark.parametrize("user, connections", [
    ({"company_id": COMPANY, "odoo_client_key": None}, {}),          # company sign-up, no client Odoo
    ({"company_id": COMPANY, "odoo_client_key": "acme"}, {}),        # client key with no connection on file
    ({"company_id": None, "odoo_client_key": "acme"}, {}),           # same, company lost
])
def test_no_fallback_to_vita_care_odoo(env, user, connections):
    client, state = env
    state["user"] = user
    state["connections"] = connections

    access = client.get("/odoo/access").json()
    assert access["allowed"] is False
    assert access["reason"] == main.ODOO_NOT_CONFIGURED_FOR_COMPANY

    resp = _ask(client)
    assert resp.status_code == 403
    assert state["agent_calls"] == []
    assert state["embedded"] is False  # refused before any AI work

    assert client.get("/odoo/dashboard").status_code == 403


def test_dashboard_uses_company_odoo(env):
    client, state = env
    state["user"] = {"company_id": COMPANY, "odoo_client_key": "acme"}
    state["connections"] = {"acme": CLIENT_CONN}
    resp = client.get("/odoo/dashboard")
    assert resp.status_code == 200, resp.text
    assert resp.json()["sales"] == {"client": True}


def test_other_tenant_is_refused(env):
    client, state = env
    state["tenant"] = OTHER_TENANT
    state["user"] = {"company_id": None, "odoo_client_key": None}
    assert client.get("/odoo/access").status_code == 403
    assert _ask(client).status_code == 403
    assert state["agent_calls"] == []
