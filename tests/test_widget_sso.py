import contextlib
import time

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt

import db
from core.security import decode_access_token
from routers import widget

SECRET = "x" * 40
TENANT_ID = "819c1132-f67b-42a1-ad46-50e051d398d7"


class FakeConn:
    def __init__(self, users, questions=None):
        self.users = users  # email -> row dict
        self.questions = questions if questions is not None else []  # list of question strings
        self.raise_unique_once = False

    async def fetchrow(self, sql, *args):
        if sql.startswith("SELECT id, tenant_id"):
            return self.users.get(args[0].lower())
        if sql.startswith("INSERT INTO users"):
            if self.raise_unique_once:
                self.raise_unique_once = False
                raise asyncpg.UniqueViolationError("dup")
            row = {"id": "u-new", "tenant_id": args[0], "role": "member", "username": args[3]}
            self.users[args[1]] = row
            return row
        if sql.startswith("SELECT name, primary_color"):
            return {"name": "Credit Plus", "primary_color": "#111111", "action_color": "#222222", "logo_path": None}

    async def fetchval(self, sql, *args):
        return "credit plus Assistant"

    async def fetch(self, sql, *args):
        if sql.startswith("SELECT question FROM suggested_questions"):
            return [{"question": q} for q in self.questions]
        return []

    def transaction(self):
        return contextlib.nullcontext()


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("WIDGET_CREDITPLUS_TENANT_ID", TENANT_ID)
    monkeypatch.setenv("WIDGET_CREDITPLUS_JWT_SECRET", SECRET)
    monkeypatch.setenv("WIDGET_ALLOWED_ORIGINS", "https://credit-plus.me")
    conn = FakeConn({}, questions=["What are your hours?", "How do I reset my password?"])

    @contextlib.asynccontextmanager
    async def fake_tc(_tenant):
        yield conn

    monkeypatch.setattr(db, "tenant_connection", fake_tc)
    app = FastAPI()
    app.middleware("http")(widget.widget_cors_middleware)
    app.include_router(widget.router)
    return TestClient(app), conn


def partner_token(**over):
    now = int(time.time())
    claims = {"sub": "42", "email": "Ali@Example.com", "name": "Ali", "aud": "cpbot-widget",
              "iat": now, "exp": now + 300}
    claims.update(over)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, SECRET, algorithm="HS256")


def verify(client, token, tenant="creditplus"):
    return client.post("/widget/sso/verify", json={"tenant": tenant, "token": token})


def test_happy_path_creates_member_user(env):
    client, conn = env
    r = verify(client, partner_token())
    assert r.status_code == 200, r.text
    payload = decode_access_token(r.json()["access_token"])
    assert payload["role"] == "member" and payload["tenant_id"] == TENANT_ID
    assert payload["email"] == "ali@example.com" and payload["widget"] is True
    assert "ali@example.com" in conn.users


def test_existing_admin_is_capped_to_member(env):
    client, conn = env
    conn.users["ali@example.com"] = {"id": "u1", "tenant_id": TENANT_ID, "role": "admin", "username": "Ali"}
    r = verify(client, partner_token())
    assert decode_access_token(r.json()["access_token"])["role"] == "member"


def test_username_collision_retries(env):
    client, conn = env
    conn.raise_unique_once = True
    assert verify(client, partner_token()).status_code == 200


def test_bad_signature(env):
    client, _ = env
    bad = jwt.encode({"sub": "1", "email": "a@b.c", "aud": "cpbot-widget", "exp": int(time.time()) + 60},
                     "y" * 40, algorithm="HS256")
    assert verify(client, bad).status_code == 401


def test_expired(env):
    client, _ = env
    assert verify(client, partner_token(exp=int(time.time()) - 10)).status_code == 401


def test_missing_exp(env):
    client, _ = env
    assert verify(client, partner_token(exp=None)).status_code == 401


def test_wrong_audience(env):
    client, _ = env
    assert verify(client, partner_token(aud="other")).status_code == 401


def test_long_lived_rejected(env):
    client, _ = env
    now = int(time.time())
    assert verify(client, partner_token(iat=now, exp=now + 86400)).status_code == 401


def test_alg_none_rejected(env):
    client, _ = env
    import base64, json
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    tok = f'{b({"alg": "none", "typ": "JWT"})}.{b({"sub": "1", "email": "a@b.c", "aud": "cpbot-widget", "exp": int(time.time()) + 60})}.'
    assert verify(client, tok).status_code == 401


def test_missing_email(env):
    client, _ = env
    assert verify(client, partner_token(email=None)).status_code == 401


def test_unknown_tenant(env):
    client, _ = env
    assert verify(client, partner_token(), tenant="nope").status_code == 404


def test_short_secret_is_503(env, monkeypatch):
    client, _ = env
    monkeypatch.setenv("WIDGET_CREDITPLUS_JWT_SECRET", "short")
    assert verify(client, partner_token()).status_code == 503


def test_config(env):
    client, _ = env
    r = client.get("/widget/config", params={"tenant": "creditplus"})
    assert r.status_code == 200
    body = r.json()
    assert body["icon_color"] == "#222222" and body["bot_name"] == "credit plus Assistant"
    assert client.get("/widget/config", params={"tenant": "nope"}).status_code == 404


def test_config_suggested_questions(env):
    client, conn = env
    body = client.get("/widget/config", params={"tenant": "creditplus"}).json()
    assert body["suggested_questions"] == ["What are your hours?", "How do I reset my password?"]


def test_config_suggested_questions_empty(env):
    client, conn = env
    conn.questions = []
    body = client.get("/widget/config", params={"tenant": "creditplus"}).json()
    assert body["suggested_questions"] == []


def test_cors(env):
    client, _ = env
    ok = client.get("/widget/config", params={"tenant": "creditplus"}, headers={"Origin": "https://credit-plus.me"})
    assert ok.headers["access-control-allow-origin"] == "https://credit-plus.me"
    assert "access-control-allow-credentials" not in ok.headers
    pre = client.options("/widget/config", headers={"Origin": "https://credit-plus.me",
                                                    "Access-Control-Request-Method": "GET"})
    assert pre.status_code == 204
    evil = client.get("/widget/config", params={"tenant": "creditplus"}, headers={"Origin": "https://evil.com"})
    assert "access-control-allow-origin" not in evil.headers
