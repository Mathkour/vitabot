"""Answer Feedback: answers users rated thumbs-down, with the question that
was asked, who asked it (user, company) and their comment, so an admin can
review each one.

"Fix" teaches the bot the correct answer through the same mechanism as
Unanswered Questions (a knowledge-base chunk; see save_answer), so fixed
answers show up there too and can be edited or removed from either page.
"Dismiss" marks the answer as fine.

The review columns come from migrations/2026-11-10b_admin_feedback_activity.sql,
applied on startup.
"""
from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

import db
from services.search import like_pattern
from core.auth import get_current_user_id, require_admin
from routers.unanswered_questions import save_answer
from services.activity import log_activity

router = APIRouter(prefix="/answer-feedback", tags=["answer-feedback"])

STATUSES = ("open", "fixed", "dismissed")
MIGRATION_MISSING = "Answer Feedback isn't set up yet: restart the backend so migrations apply"

# The question is the user message just before the rated answer in the
# same conversation.
_QUESTION_SQL = """
    (SELECT um.content FROM messages um
     WHERE um.tenant_id = m.tenant_id AND um.conversation_id = m.conversation_id
       AND um.role = 'user' AND um.created_at <= m.created_at
     ORDER BY um.created_at DESC LIMIT 1)
"""


def _status_filter(status: str) -> str:
    return "r.review_status IS NULL" if status == "open" else f"r.review_status = '{status}'"


@router.get("")
async def list_feedback(
    status: str = Query("open"),
    search: str | None = Query(None, max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tenant_id: str = Depends(require_admin),
):
    if status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {', '.join(STATUSES)}")
    pattern = like_pattern(search)
    base = f"""
        FROM ratings r
        JOIN messages m ON m.id = r.message_id AND m.tenant_id = r.tenant_id
        LEFT JOIN conversations cv ON cv.id = m.conversation_id
        LEFT JOIN users u ON u.id = cv.user_id
        LEFT JOIN companies c ON c.id = u.company_id
        WHERE r.tenant_id = $1 AND r.score = -1 AND {_status_filter(status)}
          AND ($2::text IS NULL OR m.content ILIKE $2 OR r.feedback ILIKE $2
               OR u.username ILIKE $2 OR u.email ILIKE $2 OR c.name ILIKE $2
               OR {_QUESTION_SQL} ILIKE $2)
    """
    try:
        async with db.tenant_connection(tenant_id) as conn:
            total = await conn.fetchval(f"SELECT count(*) {base}", tenant_id, pattern)
            rows = await conn.fetch(
                f"""
                SELECT r.id, r.feedback, r.created_at, r.review_status, r.reviewed_at,
                       m.id AS message_id, m.content AS answer, m.conversation_id,
                       {_QUESTION_SQL} AS question,
                       u.id AS user_id, u.username, u.email, c.name AS company_name,
                       (SELECT COALESCE(rv.username, rv.email) FROM users rv WHERE rv.id = r.reviewed_by) AS reviewed_by_name,
                       (SELECT q.answer FROM unanswered_questions q
                        WHERE q.tenant_id = r.tenant_id AND q.message_id = m.id LIMIT 1) AS corrected_answer,
                       (SELECT q.id FROM unanswered_questions q
                        WHERE q.tenant_id = r.tenant_id AND q.message_id = m.id LIMIT 1) AS question_id
                {base}
                ORDER BY r.created_at DESC
                LIMIT $3 OFFSET $4
                """,
                tenant_id, pattern, page_size, (page - 1) * page_size,
            )
            counts = {s: 0 for s in STATUSES}
            for r in await conn.fetch(
                "SELECT COALESCE(review_status, 'open') AS s, count(*) AS n FROM ratings "
                "WHERE tenant_id = $1 AND score = -1 GROUP BY 1",
                tenant_id,
            ):
                counts[r["s"]] = r["n"]
    except (asyncpg.UndefinedColumnError, asyncpg.UndefinedTableError) as e:
        raise HTTPException(status_code=503, detail=MIGRATION_MISSING) from e
    items = [
        {
            "id": str(r["id"]),
            "question": r["question"],
            "answer": r["answer"],
            "feedback": r["feedback"],
            "created_at": r["created_at"],
            "review_status": r["review_status"] or "open",
            "reviewed_at": r["reviewed_at"],
            "reviewed_by_name": r["reviewed_by_name"],
            "corrected_answer": r["corrected_answer"],
            "question_id": str(r["question_id"]) if r["question_id"] else None,
            "user_id": str(r["user_id"]) if r["user_id"] else None,
            "username": r["username"],
            "email": r["email"],
            "company_name": r["company_name"],
        }
        for r in rows
    ]
    return {"items": items, "total": total, "counts": counts}


async def _load_rating(conn, rating_id: str, tenant_id: str):
    row = await conn.fetchrow(
        f"""
        SELECT r.id, r.review_status, m.id AS message_id, m.conversation_id, cv.user_id,
               {_QUESTION_SQL} AS question
        FROM ratings r
        JOIN messages m ON m.id = r.message_id AND m.tenant_id = r.tenant_id
        LEFT JOIN conversations cv ON cv.id = m.conversation_id
        WHERE r.id = $1 AND r.tenant_id = $2 AND r.score = -1
        FOR UPDATE OF r
        """,
        rating_id, tenant_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return row


class FixRequest(BaseModel):
    answer: str
    category_id: str | None = None


@router.post("/{rating_id}/fix")
async def fix_answer(
    rating_id: str,
    body: FixRequest,
    tenant_id: str = Depends(require_admin),
    admin_id: str = Depends(get_current_user_id),
):
    """Teaches the bot the correct answer to the question behind this
    thumbs-down (or edits an earlier correction)."""
    answer = body.answer.strip()
    if not answer:
        raise HTTPException(status_code=400, detail="Answer is required")
    try:
        async with db.tenant_connection(tenant_id) as conn:
            rating = await _load_rating(conn, rating_id, tenant_id)
            if not rating["question"]:
                raise HTTPException(status_code=409, detail="The question for this answer couldn't be found")
            question_id = await conn.fetchval(
                "SELECT id FROM unanswered_questions WHERE tenant_id = $1 AND message_id = $2 LIMIT 1",
                tenant_id, rating["message_id"],
            )
            if question_id is None:
                question_id = await conn.fetchval(
                    """
                    INSERT INTO unanswered_questions (tenant_id, user_id, conversation_id, message_id, question)
                    VALUES ($1, $2, $3, $4, $5) RETURNING id
                    """,
                    tenant_id, rating["user_id"], rating["conversation_id"], rating["message_id"], rating["question"],
                )
            await save_answer(conn, tenant_id, admin_id, str(question_id), answer, body.category_id)
            await conn.execute(
                "UPDATE ratings SET review_status = 'fixed', reviewed_by = $1, reviewed_at = now() "
                "WHERE id = $2 AND tenant_id = $3",
                admin_id, rating_id, tenant_id,
            )
            await log_activity(conn, tenant_id, admin_id, "feedback.fix", rating["question"])
    except (asyncpg.UndefinedColumnError, asyncpg.UndefinedTableError) as e:
        raise HTTPException(status_code=503, detail=MIGRATION_MISSING) from e
    return {"status": "fixed"}


async def _review(rating_id: str, tenant_id: str, admin_id: str, new_status: str | None, allowed: tuple) -> dict:
    try:
        async with db.tenant_connection(tenant_id) as conn:
            rating = await _load_rating(conn, rating_id, tenant_id)
            current = rating["review_status"] or "open"
            if current not in allowed:
                raise HTTPException(status_code=409, detail=f"Can't change feedback that is {current}")
            await conn.execute(
                "UPDATE ratings SET review_status = $1, reviewed_by = $2, reviewed_at = now() "
                "WHERE id = $3 AND tenant_id = $4",
                new_status, admin_id if new_status else None, rating_id, tenant_id,
            )
            await log_activity(
                conn, tenant_id, admin_id,
                "feedback.dismiss" if new_status == "dismissed" else "feedback.reopen", rating["question"] or "",
            )
    except (asyncpg.UndefinedColumnError, asyncpg.UndefinedTableError) as e:
        raise HTTPException(status_code=503, detail=MIGRATION_MISSING) from e
    return {"status": new_status or "open"}


@router.post("/{rating_id}/dismiss")
async def dismiss_feedback(
    rating_id: str, tenant_id: str = Depends(require_admin), admin_id: str = Depends(get_current_user_id),
):
    """The answer was fine (e.g. the user disliked a correct answer)."""
    return await _review(rating_id, tenant_id, admin_id, "dismissed", ("open",))


@router.post("/{rating_id}/reopen")
async def reopen_feedback(
    rating_id: str, tenant_id: str = Depends(require_admin), admin_id: str = Depends(get_current_user_id),
):
    return await _review(rating_id, tenant_id, admin_id, None, ("dismissed",))


@router.delete("/{rating_id}")
async def delete_feedback(
    rating_id: str, tenant_id: str = Depends(require_admin), admin_id: str = Depends(get_current_user_id),
):
    """Removes an unwanted 👎 rating (tests, junk questions) from this page
    and from the satisfaction numbers. The conversation itself, and any
    answer already taught through "Fix", are kept."""
    async with db.tenant_connection(tenant_id) as conn:
        rating = await _load_rating(conn, rating_id, tenant_id)
        await conn.execute("DELETE FROM ratings WHERE id = $1 AND tenant_id = $2", rating_id, tenant_id)
        await log_activity(conn, tenant_id, admin_id, "feedback.delete", rating["question"] or "")
    return {"status": "deleted"}
