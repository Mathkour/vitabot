from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import db
from services.activity import label_for, log_detached
from core.auth import get_current_tenant, get_current_user_id, require_admin_or_company_admin, UserScope

router = APIRouter(prefix="/support-tickets", tags=["support-tickets"])


class CreateTicketRequest(BaseModel):
    question: str
    conversation_id: str | None = None


class SendMessageRequest(BaseModel):
    content: str


async def _company_scoped_ticket_owner(conn, ticket_id: str, tenant_id: str) -> str | None:
    return await conn.fetchval(
        "SELECT u.company_id FROM support_tickets t JOIN users u ON u.id = t.user_id "
        "WHERE t.id = $1 AND t.tenant_id = $2",
        ticket_id, tenant_id,
    )


@router.post("")
async def create_ticket(
    body: CreateTicketRequest,
    tenant_id: str = Depends(get_current_tenant),
    user_id: str = Depends(get_current_user_id),
):
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")
    async with db.tenant_connection(tenant_id) as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO support_tickets (tenant_id, user_id, conversation_id, question)
                VALUES ($1, $2, $3, $4)
                RETURNING id, question, status, created_at
                """,
                tenant_id, user_id, body.conversation_id, question,
            )
            await conn.execute(
                """
                INSERT INTO support_ticket_messages (tenant_id, ticket_id, sender, sender_user_id, content)
                VALUES ($1, $2, 'user', $3, $4)
                """,
                tenant_id, row["id"], user_id, question,
            )
    return dict(row)


@router.get("/me")
async def list_my_tickets(
    tenant_id: str = Depends(get_current_tenant),
    user_id: str = Depends(get_current_user_id),
):
    async with db.tenant_connection(tenant_id) as conn:
        rows = await conn.fetch(
            """
            SELECT id, question, status, created_at, resolved_at, user_last_read_at
            FROM support_tickets
            WHERE tenant_id = $1 AND user_id = $2
            ORDER BY created_at DESC
            """,
            tenant_id, user_id,
        )
    return [dict(r) for r in rows]


@router.get("/me/unseen-count")
async def my_unseen_count(
    tenant_id: str = Depends(get_current_tenant),
    user_id: str = Depends(get_current_user_id),
):
    async with db.tenant_connection(tenant_id) as conn:
        count = await conn.fetchval(
            """
            SELECT count(*) FROM support_tickets t
            WHERE t.tenant_id = $1 AND t.user_id = $2
            AND EXISTS (
                SELECT 1 FROM support_ticket_messages m
                WHERE m.tenant_id = t.tenant_id AND m.ticket_id = t.id AND m.sender = 'admin'
                AND m.created_at > COALESCE(t.user_last_read_at, '-infinity'::timestamptz)
            )
            """,
            tenant_id, user_id,
        )
    return {"count": count}


@router.get("/me/unseen")
async def my_unseen_tickets(
    tenant_id: str = Depends(get_current_tenant),
    user_id: str = Depends(get_current_user_id),
):
    async with db.tenant_connection(tenant_id) as conn:
        rows = await conn.fetch(
            """
            SELECT t.id, t.question, t.status,
                   (
                       SELECT m.content FROM support_ticket_messages m
                       WHERE m.tenant_id = t.tenant_id AND m.ticket_id = t.id AND m.sender = 'admin'
                       ORDER BY m.created_at DESC LIMIT 1
                   ) AS latest_admin_message,
                   (
                       SELECT m.created_at FROM support_ticket_messages m
                       WHERE m.tenant_id = t.tenant_id AND m.ticket_id = t.id AND m.sender = 'admin'
                       ORDER BY m.created_at DESC LIMIT 1
                   ) AS latest_admin_message_at
            FROM support_tickets t
            WHERE t.tenant_id = $1 AND t.user_id = $2
            AND EXISTS (
                SELECT 1 FROM support_ticket_messages m
                WHERE m.tenant_id = t.tenant_id AND m.ticket_id = t.id AND m.sender = 'admin'
                AND m.created_at > COALESCE(t.user_last_read_at, '-infinity'::timestamptz)
            )
            ORDER BY latest_admin_message_at DESC
            """,
            tenant_id, user_id,
        )
    return [dict(r) for r in rows]


@router.post("/{ticket_id}/messages/me")
async def send_user_message(
    ticket_id: str,
    body: SendMessageRequest,
    tenant_id: str = Depends(get_current_tenant),
    user_id: str = Depends(get_current_user_id),
):
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message is required")
    async with db.tenant_connection(tenant_id) as conn:
        ticket = await conn.fetchrow(
            "SELECT user_id, status FROM support_tickets WHERE id = $1 AND tenant_id = $2",
            ticket_id, tenant_id,
        )
        if ticket is None or str(ticket["user_id"]) != str(user_id):
            raise HTTPException(status_code=404, detail="Ticket not found")
        if ticket["status"] != "pending":
            raise HTTPException(status_code=400, detail="Ticket is resolved — open a new ticket to ask more")
        row = await conn.fetchrow(
            """
            INSERT INTO support_ticket_messages (tenant_id, ticket_id, sender, sender_user_id, content)
            VALUES ($1, $2, 'user', $3, $4)
            RETURNING id, sender, content, created_at
            """,
            tenant_id, ticket_id, user_id, content,
        )
    return dict(row)


@router.get("/{ticket_id}/messages")
async def get_ticket_messages(
    ticket_id: str,
    tenant_id: str = Depends(get_current_tenant),
    user_id: str = Depends(get_current_user_id),
):
    async with db.tenant_connection(tenant_id) as conn:
        owner = await conn.fetchval(
            "SELECT user_id FROM support_tickets WHERE id = $1 AND tenant_id = $2",
            ticket_id, tenant_id,
        )
        if owner is None or str(owner) != str(user_id):
            raise HTTPException(status_code=404, detail="Ticket not found")
        rows = await conn.fetch(
            """
            SELECT id, sender, content, created_at FROM support_ticket_messages
            WHERE tenant_id = $1 AND ticket_id = $2
            ORDER BY created_at ASC
            """,
            tenant_id, ticket_id,
        )
        await conn.execute(
            "UPDATE support_tickets SET user_last_read_at = now() WHERE id = $1 AND tenant_id = $2",
            ticket_id, tenant_id,
        )
    return [dict(r) for r in rows]


@router.get("")
async def list_tickets(
    scope: UserScope = Depends(require_admin_or_company_admin),
    status: str | None = None,
):
    async with db.tenant_connection(scope.tenant_id) as conn:
        rows = await conn.fetch(
            """
            SELECT t.id, t.question, t.status, t.created_at, t.resolved_at,
                   u.id AS user_id, u.username, u.email, u.company_id
            FROM support_tickets t
            JOIN users u ON u.id = t.user_id
            WHERE t.tenant_id = $1
            AND ($2::uuid IS NULL OR u.company_id = $2)
            AND ($3::text IS NULL OR t.status = $3)
            ORDER BY t.created_at DESC
            """,
            scope.tenant_id,
            scope.company_id if scope.role == "company_admin" else None,
            status,
        )
    return [dict(r) for r in rows]


@router.get("/pending-count")
async def pending_count(scope: UserScope = Depends(require_admin_or_company_admin)):
    async with db.tenant_connection(scope.tenant_id) as conn:
        count = await conn.fetchval(
            """
            SELECT count(*) FROM support_tickets t
            JOIN users u ON u.id = t.user_id
            WHERE t.tenant_id = $1 AND t.status = 'pending'
            AND ($2::uuid IS NULL OR u.company_id = $2)
            """,
            scope.tenant_id,
            scope.company_id if scope.role == "company_admin" else None,
        )
    return {"count": count}


@router.get("/{ticket_id}/admin-messages")
async def admin_get_ticket_messages(
    ticket_id: str,
    scope: UserScope = Depends(require_admin_or_company_admin),
):
    async with db.tenant_connection(scope.tenant_id) as conn:
        if scope.role == "company_admin":
            owner_company = await _company_scoped_ticket_owner(conn, ticket_id, scope.tenant_id)
            if owner_company is None or str(owner_company) != str(scope.company_id):
                raise HTTPException(status_code=404, detail="Ticket not found")
        rows = await conn.fetch(
            """
            SELECT id, sender, content, created_at FROM support_ticket_messages
            WHERE tenant_id = $1 AND ticket_id = $2
            ORDER BY created_at ASC
            """,
            scope.tenant_id, ticket_id,
        )
    return [dict(r) for r in rows]


@router.post("/{ticket_id}/messages")
async def send_admin_message(
    ticket_id: str,
    body: SendMessageRequest,
    scope: UserScope = Depends(require_admin_or_company_admin),
    admin_user_id: str = Depends(get_current_user_id),
):
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message is required")
    async with db.tenant_connection(scope.tenant_id) as conn:
        if scope.role == "company_admin":
            owner_company = await _company_scoped_ticket_owner(conn, ticket_id, scope.tenant_id)
            if owner_company is None or str(owner_company) != str(scope.company_id):
                raise HTTPException(status_code=404, detail="Ticket not found")
        else:
            exists = await conn.fetchval(
                "SELECT 1 FROM support_tickets WHERE id = $1 AND tenant_id = $2",
                ticket_id, scope.tenant_id,
            )
            if exists is None:
                raise HTTPException(status_code=404, detail="Ticket not found")
        row = await conn.fetchrow(
            """
            INSERT INTO support_ticket_messages (tenant_id, ticket_id, sender, sender_user_id, content)
            VALUES ($1, $2, 'admin', $3, $4)
            RETURNING id, sender, content, created_at
            """,
            scope.tenant_id, ticket_id, admin_user_id, content,
        )
    return dict(row)


@router.post("/{ticket_id}/resolve")
async def resolve_ticket(
    ticket_id: str,
    scope: UserScope = Depends(require_admin_or_company_admin),
    admin_user_id: str = Depends(get_current_user_id),
):
    _label = await label_for(scope.tenant_id, "SELECT question FROM support_tickets WHERE id = $1 AND tenant_id = $2", ticket_id, scope.tenant_id)
    async with db.tenant_connection(scope.tenant_id) as conn:
        if scope.role == "company_admin":
            owner_company = await _company_scoped_ticket_owner(conn, ticket_id, scope.tenant_id)
            if owner_company is None or str(owner_company) != str(scope.company_id):
                raise HTTPException(status_code=404, detail="Ticket not found")
        result = await conn.execute(
            """
            UPDATE support_tickets
            SET status = 'resolved', resolved_at = now(), resolved_by = $1
            WHERE id = $2 AND tenant_id = $3
            """,
            admin_user_id, ticket_id, scope.tenant_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Ticket not found")
    await log_detached(scope.tenant_id, admin_user_id, 'ticket.resolve', _label)
    return {"status": "resolved"}


@router.delete("/{ticket_id}")
async def delete_ticket(
    ticket_id: str,
    scope: UserScope = Depends(require_admin_or_company_admin),
    actor_id: str = Depends(get_current_user_id),
):
    _label = await label_for(scope.tenant_id, "SELECT question FROM support_tickets WHERE id = $1 AND tenant_id = $2", ticket_id, scope.tenant_id)
    async with db.tenant_connection(scope.tenant_id) as conn:
        if scope.role == "company_admin":
            owner_company = await _company_scoped_ticket_owner(conn, ticket_id, scope.tenant_id)
            if owner_company is None or str(owner_company) != str(scope.company_id):
                raise HTTPException(status_code=404, detail="Ticket not found")
        # support_ticket_messages rows cascade-delete via their FK to this ticket.
        result = await conn.execute(
            "DELETE FROM support_tickets WHERE id = $1 AND tenant_id = $2",
            ticket_id, scope.tenant_id,
        )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Ticket not found")
    await log_detached(scope.tenant_id, actor_id, 'ticket.delete', _label)
    return {"status": "deleted"}
