"""Unanswered Questions: every question /ask answered with "I don't know",
with who asked it (user, company), so a tenant admin can answer it.

An admin's answer is saved as a knowledge-base chunk ("Question: ...
Answer: ...", embedded like any other chunk) under one per-tenant
"Answered questions" document, so the very same /ask RAG search finds it
next time. A chunk with no category is searched in every category (see
services/search.py), so an answer without a category applies everywhere.

The table comes from migrations/2026-11-10_unanswered_questions.sql. Until
it's applied, /ask keeps working (record_unanswered_question just logs) and
these endpoints answer 503.
"""
from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel

import db
from core.auth import get_current_user_id, require_admin
from services.activity import log_activity
from services.embeddings import get_embedding

router = APIRouter(prefix="/unanswered-questions", tags=["unanswered-questions"])

STATUSES = ("open", "answered", "dismissed")
# Fixed filename that identifies the per-tenant document holding answer
# chunks; display names are what admins see.
ANSWERS_DOC_FILENAME = "__answered_questions__"
ANSWERS_DOC_NAME = "Answered questions"
ANSWERS_DOC_NAME_AR = "الأسئلة المُجاب عنها"
MIGRATION_MISSING = "Unanswered questions aren't set up yet: run migrations/2026-11-10_unanswered_questions.sql"


async def record_unanswered_question(
    conn, tenant_id: str, user_id: str | None, conversation_id: str | None,
    message_id: str | None, question: str, category_id: str | None,
) -> None:
    """Called by /ask whenever it fell back to "I don't know". Never raises:
    a failure here (including the table not existing yet) must not cost the
    user their chat answer. The savepoint keeps a failed INSERT from
    aborting /ask's own transaction."""
    try:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO unanswered_questions (tenant_id, user_id, conversation_id, message_id, question, category_id)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                tenant_id, user_id, conversation_id, message_id, question, category_id,
            )
    except asyncpg.UndefinedTableError:
        logger.warning("unanswered_questions table missing; run migrations/2026-11-10_unanswered_questions.sql")
    except Exception:
        logger.exception("Could not record unanswered question")


def _migration_guard(e: Exception) -> None:
    if isinstance(e, asyncpg.UndefinedTableError):
        raise HTTPException(status_code=503, detail=MIGRATION_MISSING) from e
    raise e


def _row_to_item(r) -> dict:
    return {
        "id": str(r["id"]),
        "question": r["question"],
        "status": r["status"],
        "created_at": r["created_at"],
        "user_id": str(r["user_id"]) if r["user_id"] else None,
        "username": r["username"],
        "email": r["email"],
        "company_name": r["company_name"],
        "category_id": str(r["category_id"]) if r["category_id"] else None,
        "category_name": r["category_name"],
        "answer": r["answer"],
        "answered_at": r["answered_at"],
        "answered_by_name": r["answered_by_name"],
        "times_asked": r["times_asked"],
    }


@router.get("")
async def list_unanswered_questions(
    status: str = Query("open"),
    search: str | None = Query(None, max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tenant_id: str = Depends(require_admin),
):
    if status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {', '.join(STATUSES)}")
    pattern = f"%{search.strip()}%" if search and search.strip() else None
    try:
        async with db.tenant_connection(tenant_id) as conn:
            base = """
                FROM unanswered_questions q
                LEFT JOIN users u ON u.id = q.user_id
                LEFT JOIN companies c ON c.id = u.company_id
                LEFT JOIN categories cat ON cat.id = q.category_id
                LEFT JOIN users ab ON ab.id = q.answered_by
                WHERE q.tenant_id = $1 AND q.status = $2
                  AND ($3::text IS NULL OR q.question ILIKE $3 OR u.username ILIKE $3
                       OR u.email ILIKE $3 OR c.name ILIKE $3)
            """
            total = await conn.fetchval(f"SELECT count(*) {base}", tenant_id, status, pattern)
            rows = await conn.fetch(
                f"""
                SELECT q.id, q.question, q.status, q.created_at, q.user_id, q.category_id,
                       q.answer, q.answered_at,
                       u.username, u.email, c.name AS company_name, cat.name AS category_name,
                       COALESCE(ab.username, ab.email) AS answered_by_name,
                       (SELECT count(*) FROM unanswered_questions o
                        WHERE o.tenant_id = q.tenant_id
                          AND lower(btrim(o.question)) = lower(btrim(q.question))) AS times_asked
                {base}
                ORDER BY q.created_at DESC
                LIMIT $4 OFFSET $5
                """,
                tenant_id, status, pattern, page_size, (page - 1) * page_size,
            )
            counts = {s: 0 for s in STATUSES}
            for r in await conn.fetch(
                "SELECT status, count(*) AS n FROM unanswered_questions WHERE tenant_id = $1 GROUP BY status",
                tenant_id,
            ):
                counts[r["status"]] = r["n"]
    except asyncpg.UndefinedTableError as e:
        _migration_guard(e)
    return {"items": [_row_to_item(r) for r in rows], "total": total, "counts": counts}


@router.get("/open-count")
async def open_count(tenant_id: str = Depends(require_admin)):
    """For the sidebar badge. 0 (not an error) until the migration is applied."""
    try:
        async with db.tenant_connection(tenant_id) as conn:
            count = await conn.fetchval(
                "SELECT count(*) FROM unanswered_questions WHERE tenant_id = $1 AND status = 'open'", tenant_id,
            )
    except asyncpg.UndefinedTableError:
        count = 0
    return {"count": count}


async def _answers_document_id(conn, tenant_id: str) -> str:
    # Serializes the get-or-create per tenant so two admins answering at
    # once can't create two "Answered questions" documents.
    await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"answered_questions_doc:{tenant_id}")
    doc_id = await conn.fetchval(
        "SELECT id FROM documents WHERE tenant_id = $1 AND filename = $2", tenant_id, ANSWERS_DOC_FILENAME,
    )
    if doc_id is None:
        doc_id = await conn.fetchval(
            """
            INSERT INTO documents (tenant_id, filename, status, display_name, display_name_ar)
            VALUES ($1, $2, 'ready', $3, $4) RETURNING id
            """,
            tenant_id, ANSWERS_DOC_FILENAME, ANSWERS_DOC_NAME, ANSWERS_DOC_NAME_AR,
        )
    return doc_id


class AnswerRequest(BaseModel):
    answer: str
    category_id: str | None = None


async def save_answer(conn, tenant_id: str, admin_id: str, question_id: str, answer: str, category_id: str | None) -> int:
    """Saves (or edits) the answer to one question and teaches it to the bot.
    Every other OPEN occurrence of the same question (case/whitespace
    -insensitive) is answered along with it, sharing one knowledge-base
    chunk. Returns how many questions were answered. Also used by Answer
    Feedback when an admin corrects a thumbs-down answer."""
    target = await conn.fetchrow(
        "SELECT id, question, status, chunk_id FROM unanswered_questions WHERE id = $1 AND tenant_id = $2",
        question_id, tenant_id,
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Question not found")
    if category_id:
        if not await conn.fetchval(
            "SELECT 1 FROM categories WHERE id = $1 AND tenant_id = $2", category_id, tenant_id,
        ):
            raise HTTPException(status_code=400, detail="Unknown category")

    content = f"Question: {target['question'].strip()}\nAnswer: {answer}"
    embedding = await get_embedding(content)
    embedding_str = "[" + ",".join(f"{x:.10f}" for x in embedding) + "]"

    chunk_id = target["chunk_id"]
    updated = None
    if chunk_id is not None:
        updated = await conn.fetchval(
            "UPDATE chunks SET content = $1, embedding = $2, category_id = $3 "
            "WHERE id = $4 AND tenant_id = $5 RETURNING id",
            content, embedding_str, category_id, chunk_id, tenant_id,
        )
    if updated is None:  # first answer, or the old chunk was deleted
        doc_id = await _answers_document_id(conn, tenant_id)
        chunk_id = await conn.fetchval(
            "INSERT INTO chunks (tenant_id, document_id, content, embedding, category_id) "
            "VALUES ($1, $2, $3, $4, $5) RETURNING id",
            tenant_id, doc_id, content, embedding_str, category_id,
        )

    result = await conn.execute(
        """
        UPDATE unanswered_questions
        SET status = 'answered', answer = $1, answered_by = $2, answered_at = now(),
            chunk_id = $3, category_id = $4
        WHERE tenant_id = $5
          AND (id = $6
               OR chunk_id = $3
               OR (status = 'open' AND lower(btrim(question)) = lower(btrim($7))))
        """,
        answer, admin_id, chunk_id, category_id, tenant_id, question_id, target["question"],
    )
    await log_activity(
        conn, tenant_id, admin_id,
        "question.answer" if target["status"] != "answered" else "question.edit_answer",
        target["question"],
    )
    return int(result.split()[-1])


@router.post("/{question_id}/answer")
async def answer_question(
    question_id: str,
    body: AnswerRequest,
    tenant_id: str = Depends(require_admin),
    admin_id: str = Depends(get_current_user_id),
):
    """Answers (or edits the answer to) a question; see save_answer."""
    answer = body.answer.strip()
    if not answer:
        raise HTTPException(status_code=400, detail="Answer is required")
    try:
        async with db.tenant_connection(tenant_id) as conn:
            updated = await save_answer(conn, tenant_id, admin_id, question_id, answer, body.category_id)
    except asyncpg.UndefinedTableError as e:
        _migration_guard(e)
    return {"status": "answered", "updated": updated}


async def _set_status(
    question_id: str, tenant_id: str, admin_id: str, new_status: str, allowed_from: tuple[str, ...],
) -> dict:
    try:
        async with db.tenant_connection(tenant_id) as conn:
            current = await conn.fetchrow(
                "SELECT status, question FROM unanswered_questions WHERE id = $1 AND tenant_id = $2",
                question_id, tenant_id,
            )
            if current is None:
                raise HTTPException(status_code=404, detail="Question not found")
            if current["status"] not in allowed_from:
                raise HTTPException(status_code=409, detail=f"Can't change a question that is {current['status']}")
            await conn.execute(
                "UPDATE unanswered_questions SET status = $1 WHERE id = $2 AND tenant_id = $3",
                new_status, question_id, tenant_id,
            )
            await log_activity(
                conn, tenant_id, admin_id,
                "question.dismiss" if new_status == "dismissed" else "question.reopen", current["question"],
            )
    except asyncpg.UndefinedTableError as e:
        _migration_guard(e)
    return {"status": new_status}


@router.post("/{question_id}/dismiss")
async def dismiss_question(
    question_id: str, tenant_id: str = Depends(require_admin), admin_id: str = Depends(get_current_user_id),
):
    """For questions not worth answering (spam, off-topic, tests)."""
    return await _set_status(question_id, tenant_id, admin_id, "dismissed", ("open",))


@router.post("/{question_id}/reopen")
async def reopen_question(
    question_id: str, tenant_id: str = Depends(require_admin), admin_id: str = Depends(get_current_user_id),
):
    return await _set_status(question_id, tenant_id, admin_id, "open", ("dismissed",))


@router.delete("/{question_id}/answer")
async def remove_answer(
    question_id: str, tenant_id: str = Depends(require_admin), admin_id: str = Depends(get_current_user_id),
):
    """Takes an answer back: deletes its knowledge-base chunk (the bot stops
    using it) and reopens every question that shared it."""
    try:
        async with db.tenant_connection(tenant_id) as conn:
            target = await conn.fetchrow(
                "SELECT status, chunk_id, question FROM unanswered_questions WHERE id = $1 AND tenant_id = $2",
                question_id, tenant_id,
            )
            if target is None:
                raise HTTPException(status_code=404, detail="Question not found")
            if target["status"] != "answered":
                raise HTTPException(status_code=409, detail="This question has no answer")
            reopen_sql = (
                "UPDATE unanswered_questions SET status = 'open', answer = NULL, answered_by = NULL, "
                "answered_at = NULL, chunk_id = NULL WHERE tenant_id = $1 AND "
            )
            if target["chunk_id"] is not None:
                result = await conn.execute(reopen_sql + "chunk_id = $2", tenant_id, target["chunk_id"])
                await conn.execute("DELETE FROM chunks WHERE id = $1 AND tenant_id = $2", target["chunk_id"], tenant_id)
            else:
                result = await conn.execute(reopen_sql + "id = $2", tenant_id, question_id)
            await log_activity(conn, tenant_id, admin_id, "question.remove_answer", target["question"])
    except asyncpg.UndefinedTableError as e:
        _migration_guard(e)
    return {"status": "open", "updated": int(result.split()[-1])}
