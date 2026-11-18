"""Admin overview endpoints: the dashboard summary, the activity log,
conversation search and the per-company analytics breakdown.

All tenant-admin only and scoped to the admin's own tenant. Anything that
reads a table from a not-yet-applied migration degrades to empty/zero
instead of failing the whole page.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

import db
from services.search import like_pattern
from core.auth import require_admin

router = APIRouter(tags=["admin-overview"])


async def _safe_val(conn, sql: str, *args, default=0):
    """fetchval that returns `default` when a migration-created table or
    column doesn't exist yet (savepoint so the outer transaction survives)."""
    try:
        async with conn.transaction():
            return await conn.fetchval(sql, *args)
    except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError):
        return default


async def _safe_rows(conn, sql: str, *args) -> list:
    try:
        async with conn.transaction():
            return await conn.fetch(sql, *args)
    except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError):
        return []


@router.get("/dashboard/summary")
async def dashboard_summary(
    days: int = Query(7, ge=1, le=90),
    tenant_id: str = Depends(require_admin),
):
    """Everything the admin home page shows: this period vs the previous
    one, what needs attention, and the latest items to act on."""
    async with db.tenant_connection(tenant_id) as conn:
        window = "now() - ($2 * interval '1 day')"
        prev_window = "now() - ($2 * 2 * interval '1 day')"
        questions = await conn.fetchval(
            f"SELECT count(*) FROM messages WHERE tenant_id = $1 AND role = 'user' AND created_at >= {window}",
            tenant_id, days,
        )
        questions_prev = await conn.fetchval(
            f"SELECT count(*) FROM messages WHERE tenant_id = $1 AND role = 'user' "
            f"AND created_at >= {prev_window} AND created_at < {window}",
            tenant_id, days,
        )
        active_users = await conn.fetchval(
            f"""SELECT count(DISTINCT cv.user_id) FROM messages m JOIN conversations cv ON cv.id = m.conversation_id
                WHERE m.tenant_id = $1 AND m.role = 'user' AND m.created_at >= {window}""",
            tenant_id, days,
        )
        total_companies = await _safe_val(
            conn, "SELECT count(*) FROM companies WHERE tenant_id = $1", tenant_id,
        )
        total_users = await _safe_val(
            conn, "SELECT count(*) FROM users WHERE tenant_id = $1", tenant_id,
        )
        unanswered_in_period = await _safe_val(
            conn,
            f"SELECT count(*) FROM unanswered_questions WHERE tenant_id = $1 AND created_at >= {window}",
            tenant_id, days,
        )
        rated = await conn.fetchrow(
            f"""SELECT count(*) FILTER (WHERE score = 1) AS up, count(*) FILTER (WHERE score = -1) AS down
                FROM ratings WHERE tenant_id = $1 AND created_at >= {window}""",
            tenant_id, days,
        )
        open_unanswered = await _safe_val(
            conn, "SELECT count(*) FROM unanswered_questions WHERE tenant_id = $1 AND status = 'open'", tenant_id,
        )
        pending_tickets = await conn.fetchval(
            "SELECT count(*) FROM support_tickets WHERE tenant_id = $1 AND status = 'pending'", tenant_id,
        )
        feedback_to_review = await _safe_val(
            conn, "SELECT count(*) FROM ratings WHERE tenant_id = $1 AND score = -1 AND review_status IS NULL",
            tenant_id,
        )
        daily = await conn.fetch(
            f"""SELECT date_trunc('day', created_at) AS day, count(*) AS n FROM messages
                WHERE tenant_id = $1 AND role = 'user' AND created_at >= {window}
                GROUP BY 1 ORDER BY 1""",
            tenant_id, days,
        )
        recent_unanswered = await _safe_rows(
            conn,
            """SELECT q.id, q.question, q.created_at, u.username, u.email, c.name AS company_name
               FROM unanswered_questions q LEFT JOIN users u ON u.id = q.user_id
               LEFT JOIN companies c ON c.id = u.company_id
               WHERE q.tenant_id = $1 AND q.status = 'open' ORDER BY q.created_at DESC LIMIT 5""",
            tenant_id,
        )
        recent_feedback = await _safe_rows(
            conn,
            """SELECT r.id, r.created_at, r.feedback, m.content AS answer,
                      (SELECT um.content FROM messages um WHERE um.tenant_id = m.tenant_id
                         AND um.conversation_id = m.conversation_id AND um.role = 'user'
                         AND um.created_at <= m.created_at ORDER BY um.created_at DESC LIMIT 1) AS question
               FROM ratings r JOIN messages m ON m.id = r.message_id AND m.tenant_id = r.tenant_id
               WHERE r.tenant_id = $1 AND r.score = -1 AND r.review_status IS NULL
               ORDER BY r.created_at DESC LIMIT 5""",
            tenant_id,
        )
        top_companies = await conn.fetch(
            f"""SELECT c.name, count(*) AS questions FROM messages m
                JOIN conversations cv ON cv.id = m.conversation_id
                JOIN users u ON u.id = cv.user_id JOIN companies c ON c.id = u.company_id
                WHERE m.tenant_id = $1 AND m.role = 'user' AND m.created_at >= {window}
                GROUP BY c.name ORDER BY questions DESC LIMIT 5""",
            tenant_id, days,
        )

    # Fill in days with no questions so the chart has every day.
    by_day = {r["day"].date(): r["n"] for r in daily}
    today = datetime.now(timezone.utc).date()
    series = [
        {"day": (today - timedelta(days=i)).isoformat(), "count": by_day.get(today - timedelta(days=i), 0)}
        for i in range(days - 1, -1, -1)
    ]
    total_rated = (rated["up"] or 0) + (rated["down"] or 0)
    return {
        "days": days,
        "questions": questions,
        "questions_prev": questions_prev,
        "active_users": active_users,
        "total_companies": total_companies,
        "total_users": total_users,
        "answered_rate": round(100 * (1 - unanswered_in_period / questions)) if questions else None,
        "unanswered_in_period": unanswered_in_period,
        "satisfaction_rate": round(100 * rated["up"] / total_rated) if total_rated else None,
        "ratings_up": rated["up"],
        "ratings_down": rated["down"],
        "open_unanswered": open_unanswered,
        "pending_tickets": pending_tickets,
        "feedback_to_review": feedback_to_review,
        "daily": series,
        "recent_unanswered": [
            {"id": str(r["id"]), "question": r["question"], "created_at": r["created_at"],
             "user": r["username"] or r["email"], "company_name": r["company_name"]}
            for r in recent_unanswered
        ],
        "recent_feedback": [
            {"id": str(r["id"]), "question": r["question"], "answer": r["answer"],
             "feedback": r["feedback"], "created_at": r["created_at"]}
            for r in recent_feedback
        ],
        "top_companies": [{"name": r["name"], "questions": r["questions"]} for r in top_companies],
    }


@router.get("/activity-log")
async def activity_log(
    search: str | None = Query(None, max_length=200),
    area: str | None = Query(None, max_length=40),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    tenant_id: str = Depends(require_admin),
):
    """Who changed what. `area` filters by the action prefix (e.g. 'faq',
    'document', 'user', 'question')."""
    pattern = like_pattern(search)
    area_prefix = f"{area.strip()}.%" if area and area.strip() else None
    base = """
        FROM activity_log a LEFT JOIN users u ON u.id = a.user_id
        WHERE a.tenant_id = $1
          AND ($2::text IS NULL OR a.summary ILIKE $2 OR u.username ILIKE $2 OR u.email ILIKE $2)
          AND ($3::text IS NULL OR a.action LIKE $3)
    """
    try:
        async with db.tenant_connection(tenant_id) as conn:
            total = await conn.fetchval(f"SELECT count(*) {base}", tenant_id, pattern, area_prefix)
            rows = await conn.fetch(
                f"""SELECT a.id, a.action, a.summary, a.created_at, COALESCE(u.username, u.email) AS user_name
                    {base} ORDER BY a.created_at DESC LIMIT $4 OFFSET $5""",
                tenant_id, pattern, area_prefix, page_size, (page - 1) * page_size,
            )
    except asyncpg.UndefinedTableError as e:
        raise HTTPException(status_code=503, detail="Activity log isn't set up yet: restart the backend so migrations apply") from e
    return {
        "items": [
            {"id": str(r["id"]), "action": r["action"], "summary": r["summary"],
             "created_at": r["created_at"], "user_name": r["user_name"]}
            for r in rows
        ],
        "total": total,
    }


def _day_bound(d: date | None, end: bool) -> datetime | None:
    if d is None:
        return None
    return datetime.combine(d + timedelta(days=1) if end else d, time.min, tzinfo=timezone.utc)


@router.get("/conversations/search")
async def search_conversations(
    q: str | None = Query(None, max_length=200),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    company_id: str | None = Query(None),
    only_disliked: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tenant_id: str = Depends(require_admin),
):
    """Message-level search across every user's conversations. A hit links
    to that user's conversation page. `only_disliked` limits it to bot
    answers rated thumbs-down; `company_id='none'` means users without one."""
    pattern = like_pattern(q)
    no_company = company_id == "none"
    company = None if (no_company or not company_id) else company_id
    base = """
        FROM messages m
        JOIN conversations cv ON cv.id = m.conversation_id
        LEFT JOIN users u ON u.id = cv.user_id
        LEFT JOIN companies c ON c.id = u.company_id
        LEFT JOIN ratings r ON r.message_id = m.id AND r.tenant_id = m.tenant_id
        WHERE m.tenant_id = $1
          AND ($2::text IS NULL OR m.content ILIKE $2)
          AND ($3::timestamptz IS NULL OR m.created_at >= $3)
          AND ($4::timestamptz IS NULL OR m.created_at < $4)
          AND ($5::uuid IS NULL OR u.company_id = $5)
          AND (NOT $6 OR u.company_id IS NULL)
          AND (NOT $7 OR r.score = -1)
    """
    args = [tenant_id, pattern, _day_bound(date_from, False), _day_bound(date_to, True), company, no_company, only_disliked]
    async with db.tenant_connection(tenant_id) as conn:
        try:
            total = await conn.fetchval(f"SELECT count(*) {base}", *args)
        except asyncpg.DataError as e:  # malformed company_id
            raise HTTPException(status_code=400, detail="Invalid company") from e
        rows = await conn.fetch(
            f"""SELECT m.id, m.role, m.content, m.created_at, m.conversation_id, r.score,
                       u.id AS user_id, u.username, u.email, c.name AS company_name
                {base} ORDER BY m.created_at DESC LIMIT $8 OFFSET $9""",
            *args, page_size, (page - 1) * page_size,
        )
    return {
        "items": [
            {"id": str(r["id"]), "role": r["role"], "content": r["content"], "created_at": r["created_at"],
             "conversation_id": str(r["conversation_id"]), "score": r["score"],
             "user_id": str(r["user_id"]) if r["user_id"] else None,
             "username": r["username"], "email": r["email"], "company_name": r["company_name"]}
            for r in rows
        ],
        "total": total,
    }


@router.get("/analytics/companies")
async def analytics_by_company(
    days: int = Query(7, ge=1, le=90),
    tenant_id: str = Depends(require_admin),
):
    """Per-company usage for the period, plus a 'no company' row."""
    async with db.tenant_connection(tenant_id) as conn:
        rows = await conn.fetch(
            """
            WITH asked AS (
                SELECT u.company_id, cv.user_id, m.id
                FROM messages m JOIN conversations cv ON cv.id = m.conversation_id
                LEFT JOIN users u ON u.id = cv.user_id
                WHERE m.tenant_id = $1 AND m.role = 'user' AND m.created_at >= now() - ($2 * interval '1 day')
            ), rated AS (
                SELECT u.company_id, r.score
                FROM ratings r JOIN messages m ON m.id = r.message_id AND m.tenant_id = r.tenant_id
                JOIN conversations cv ON cv.id = m.conversation_id LEFT JOIN users u ON u.id = cv.user_id
                WHERE r.tenant_id = $1 AND r.created_at >= now() - ($2 * interval '1 day')
            ), members AS (
                SELECT company_id, count(*) AS n FROM users WHERE tenant_id = $1 GROUP BY company_id
            )
            SELECT c.id, c.name,
                   COALESCE(mb.n, 0) AS users,
                   (SELECT count(DISTINCT a.user_id) FROM asked a WHERE a.company_id IS NOT DISTINCT FROM c.id) AS active_users,
                   (SELECT count(*) FROM asked a WHERE a.company_id IS NOT DISTINCT FROM c.id) AS questions,
                   (SELECT count(*) FROM rated x WHERE x.company_id IS NOT DISTINCT FROM c.id AND x.score = 1) AS thumbs_up,
                   (SELECT count(*) FROM rated x WHERE x.company_id IS NOT DISTINCT FROM c.id AND x.score = -1) AS thumbs_down
            FROM (SELECT id, name FROM companies WHERE tenant_id = $1
                  UNION ALL SELECT NULL::uuid, NULL::text) c
            LEFT JOIN members mb ON mb.company_id IS NOT DISTINCT FROM c.id
            ORDER BY questions DESC, c.name NULLS LAST
            """,
            tenant_id, days,
        )
        unanswered = {
            r["company_id"]: r["n"]
            for r in await _safe_rows(
                conn,
                """SELECT u.company_id, count(*) AS n FROM unanswered_questions q
                   LEFT JOIN users u ON u.id = q.user_id
                   WHERE q.tenant_id = $1 AND q.created_at >= now() - ($2 * interval '1 day')
                   GROUP BY u.company_id""",
                tenant_id, days,
            )
        }
    return [
        {"company_id": str(r["id"]) if r["id"] else None, "name": r["name"], "users": r["users"],
         "active_users": r["active_users"], "questions": r["questions"],
         "unanswered": unanswered.get(r["id"], 0),
         "thumbs_up": r["thumbs_up"], "thumbs_down": r["thumbs_down"]}
        for r in rows
        if r["id"] is not None or r["users"] or r["questions"]
    ]
