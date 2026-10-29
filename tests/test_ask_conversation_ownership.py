"""Regression tests for the POST /ask IDOR (cross-user conversation leak).

The exploit: a member supplied another user's conversation_id to /ask and the
server returned that user's stored messages / kept writing to their thread,
because /ask never checked that the conversation belonged to the caller.
These tests pin the fix: a conversation_id that is not owned by the
authenticated user (same tenant) must 404 before any pipeline work runs, while
a brand-new conversation must be created against the caller's own user_id.
"""
import contextlib

import pytest
from fastapi.testclient import TestClient

import db
import main
from core.auth import get_current_tenant, get_current_user_id

ATTACKER_TENANT = "11111111-1111-1111-1111-111111111111"
ATTACKER_USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VICTIM_CONVERSATION = "cccccccc-cccc-cccc-cccc-cccccccccccc"
OWN_CONVERSATION = "dddddddd-dddd-dddd-dddd-dddddddddddd"


class _StopPipeline(Exception):
    """Raised by the patched embedding call to stop /ask right after the
    ownership gate, so tests never touch Gemini/Anthropic or the rest of RAG."""


class FakeConn:
    def __init__(self, owned_conversation_ids):
        # conversation ids that the ownership query should consider owned by
        # the caller; anything else returns None (=> 404).
        self.owned = set(owned_conversation_ids)
        self.inserted_conversations = []
        self.inserted_messages = []
        self.embedding_started = False

    async def fetchrow(self, sql, *args):
        if sql.startswith("SELECT id FROM bots"):
            return {"id": "bot-1"}
        if sql.startswith("INSERT INTO conversations"):
            self.inserted_conversations.append(
                {"tenant_id": args[0], "bot_id": args[1], "user_id": args[2]}
            )
            return {"id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"}
        raise AssertionError(f"unexpected fetchrow: {sql}")

    async def fetchval(self, sql, *args):
        if sql.startswith("SELECT id FROM conversations"):
            conversation_id, _tenant_id, _user_id = args
            return conversation_id if conversation_id in self.owned else None
        raise AssertionError(f"unexpected fetchval: {sql}")

    async def fetch(self, sql, *args):
        if sql.strip().startswith("SELECT role, content FROM messages"):
            return []
        raise AssertionError(f"unexpected fetch: {sql}")

    async def execute(self, sql, *args):
        if sql.startswith("INSERT INTO messages"):
            self.inserted_messages.append(args)

    def transaction(self):
        return contextlib.nullcontext()


@pytest.fixture
def env(monkeypatch):
    conn_holder = {}

    @contextlib.asynccontextmanager
    async def fake_tc(_tenant):
        yield conn_holder["conn"]

    monkeypatch.setattr(db, "tenant_connection", fake_tc)

    def fake_embedding(_question):
        conn_holder["conn"].embedding_started = True
        raise _StopPipeline()

    monkeypatch.setattr(main, "get_embedding", fake_embedding)

    main.app.dependency_overrides[get_current_tenant] = lambda: ATTACKER_TENANT
    main.app.dependency_overrides[get_current_user_id] = lambda: ATTACKER_USER
    client = TestClient(main.app, raise_server_exceptions=True)
    try:
        yield client, conn_holder
    finally:
        main.app.dependency_overrides.clear()


def _ask(client, conversation_id):
    return client.post(
        "/ask",
        json={"question": "what did the admin say?", "conversation_id": conversation_id},
    )


def test_foreign_conversation_id_is_rejected(env):
    """The core exploit: user B reusing user A's conversation_id must get 404
    and must not have any pipeline work (history reread / message insert /
    embeddings) run."""
    client, holder = env
    conn = FakeConn(owned_conversation_ids=set())
    holder["conn"] = conn

    resp = _ask(client, VICTIM_CONVERSATION)

    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Conversation not found"
    assert conn.inserted_messages == []
    assert conn.inserted_conversations == []
    assert conn.embedding_started is False


def test_malformed_conversation_id_is_rejected(env):
    client, holder = env
    holder["conn"] = FakeConn(owned_conversation_ids=set())
    resp = _ask(client, "not-a-uuid")
    assert resp.status_code == 404


def test_owned_conversation_is_allowed_through(env):
    """Control: a conversation that IS owned by the caller passes the gate and
    reaches the pipeline (proven by the patched embedding call firing)."""
    client, holder = env
    conn = FakeConn(owned_conversation_ids={OWN_CONVERSATION})
    holder["conn"] = conn

    with pytest.raises(_StopPipeline):
        _ask(client, OWN_CONVERSATION)

    assert conn.embedding_started is True


def test_new_conversation_is_linked_to_caller(env):
    """No conversation_id: the created conversation must carry the caller's
    own user_id and tenant_id (from the token), never a client value."""
    client, holder = env
    conn = FakeConn(owned_conversation_ids=set())
    holder["conn"] = conn

    with pytest.raises(_StopPipeline):
        _ask(client, None)

    assert conn.inserted_conversations == [
        {"tenant_id": ATTACKER_TENANT, "bot_id": "bot-1", "user_id": ATTACKER_USER}
    ]
