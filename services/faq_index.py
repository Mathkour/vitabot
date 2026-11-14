"""Makes FAQ items and error solutions answerable in chat.

Both live in their own tables (shown on the FAQ page), which /ask never
searched. Each entry now also gets one chunk in the knowledge base, under a
hidden per-tenant document, with no category so it's found whichever
category the user asks in (same as Unanswered Questions answers). The
entry's chunk_id points at it so edits and deletes keep the two in step.

Indexing never blocks an admin's save: if the embedding call fails, the
entry is left unindexed (chunk_id NULL) and backfill_unindexed(), run on
startup, picks it up.
"""
from __future__ import annotations

from loguru import logger

import db
from services.embeddings import get_embedding

FAQ_INDEX_DOC_FILENAME = "__faq_and_error_solutions__"
FAQ_INDEX_DOC_NAME = "FAQ and error solutions"
FAQ_INDEX_DOC_NAME_AR = "الأسئلة الشائعة وحلول الأخطاء"

# table -> its text columns, aliased to one shape
_SOURCES = {
    "faq_items": "question, answer, question_ar, answer_ar",
    "error_solutions": "error_text AS question, solution_text AS answer, "
                       "error_text_ar AS question_ar, solution_text_ar AS answer_ar",
}
_LABELS = {
    "faq_items": ("Question", "Answer", "السؤال", "الجواب"),
    "error_solutions": ("Error", "Solution", "الخطأ", "الحل"),
}


def entry_content(table: str, question, answer, question_ar=None, answer_ar=None) -> str:
    q, a, q_ar, a_ar = _LABELS[table]
    parts = []
    if question or answer:
        parts.append(f"{q}: {(question or '').strip()} | {a}: {(answer or '').strip()}")
    if question_ar or answer_ar:
        parts.append(f"{q_ar}: {(question_ar or '').strip()} | {a_ar}: {(answer_ar or '').strip()}")
    return " | ".join(parts)


async def _index_document_id(conn, tenant_id: str) -> str:
    # Serialized per tenant so concurrent saves can't create two documents.
    await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"faq_index_doc:{tenant_id}")
    doc_id = await conn.fetchval(
        "SELECT id FROM documents WHERE tenant_id = $1 AND filename = $2", tenant_id, FAQ_INDEX_DOC_FILENAME,
    )
    if doc_id is None:
        doc_id = await conn.fetchval(
            """
            INSERT INTO documents (tenant_id, filename, status, display_name, display_name_ar)
            VALUES ($1, $2, 'ready', $3, $4) RETURNING id
            """,
            tenant_id, FAQ_INDEX_DOC_FILENAME, FAQ_INDEX_DOC_NAME, FAQ_INDEX_DOC_NAME_AR,
        )
    return doc_id


async def index_entry(table: str, tenant_id: str, entry_id) -> bool:
    """(Re)builds the chunk for one entry from its current row. Call after the
    row's own transaction has committed. Returns False (and leaves the entry
    unindexed for the startup backfill) if anything fails."""
    try:
        async with db.tenant_connection(tenant_id) as conn:
            row = await conn.fetchrow(
                f"SELECT {_SOURCES[table]}, chunk_id FROM {table} WHERE id = $1 AND tenant_id = $2",
                entry_id, tenant_id,
            )
        if row is None:
            return False
        content = entry_content(table, row["question"], row["answer"], row["question_ar"], row["answer_ar"])
        embedding = await get_embedding(content)
        embedding_str = "[" + ",".join(f"{x:.10f}" for x in embedding) + "]"

        async with db.tenant_connection(tenant_id) as conn:
            chunk_id = row["chunk_id"]
            updated = None
            if chunk_id is not None:
                updated = await conn.fetchval(
                    "UPDATE chunks SET content = $1, embedding = $2 WHERE id = $3 AND tenant_id = $4 RETURNING id",
                    content, embedding_str, chunk_id, tenant_id,
                )
            if updated is None:
                doc_id = await _index_document_id(conn, tenant_id)
                chunk_id = await conn.fetchval(
                    "INSERT INTO chunks (tenant_id, document_id, content, embedding, category_id) "
                    "VALUES ($1, $2, $3, $4, NULL) RETURNING id",
                    tenant_id, doc_id, content, embedding_str,
                )
            await conn.execute(
                f"UPDATE {table} SET chunk_id = $1 WHERE id = $2 AND tenant_id = $3",
                chunk_id, entry_id, tenant_id,
            )
        return True
    except Exception:
        logger.exception(f"Indexing {table} {entry_id} for chat failed; it will be retried on next startup")
        await unindex_entry(table, tenant_id, entry_id)
        return False


async def unindex_entry(table: str, tenant_id: str, entry_id) -> None:
    """Removes the entry's chunk (so stale text isn't served) and marks it
    unindexed. Never raises."""
    try:
        async with db.tenant_connection(tenant_id) as conn:
            chunk_id = await conn.fetchval(
                f"SELECT chunk_id FROM {table} WHERE id = $1 AND tenant_id = $2", entry_id, tenant_id,
            )
            if chunk_id is not None:
                await conn.execute(f"UPDATE {table} SET chunk_id = NULL WHERE id = $1", entry_id)
                await delete_chunk(conn, tenant_id, chunk_id)
    except Exception:
        logger.exception(f"Removing the chat index for {table} {entry_id} failed")


async def delete_chunk(conn, tenant_id: str, chunk_id) -> None:
    if chunk_id is not None:
        await conn.execute("DELETE FROM chunks WHERE id = $1 AND tenant_id = $2", chunk_id, tenant_id)


async def backfill_unindexed() -> int:
    """Indexes every FAQ item / error solution with no chunk yet (existing
    entries, or ones whose indexing failed). Returns how many were indexed."""
    indexed = 0
    try:
        async with db.pool.acquire() as conn:
            pending = [
                (table, r["tenant_id"], r["id"])
                for table in _SOURCES
                for r in await conn.fetch(f"SELECT tenant_id, id FROM {table} WHERE chunk_id IS NULL")
            ]
    except Exception:
        logger.exception("FAQ chat-index backfill couldn't list entries (migration not applied yet?)")
        return 0
    for table, tenant_id, entry_id in pending:
        if await index_entry(table, str(tenant_id), entry_id):
            indexed += 1
    if pending:
        logger.info(f"FAQ chat-index backfill: indexed {indexed} of {len(pending)} entries")
    return indexed
