"""
One-off backfill for the OpenAI -> Gemini embeddings migration (step 4 of the
plan; see migrations/004_add_embedding_new_column.sql, run first and
separately). Populates the new `embedding_new` column on `chunks` and
`media` for every existing row, using Gemini's gemini-embedding-001 at
output_dimensionality=1536 — the OLD `embedding` column (OpenAI
text-embedding-3-small) is never read or modified by this script.

Source text per table (must match what main.py actually embeds today, or
Gemini search quality will differ from what the OpenAI-embedding rows had):
  - chunks.content: embedded AS-IS. Confirmed against every get_embedding()
    call site in main.py (document chunks, excel-row chunks) — always the
    literal stored `content` text, no extra wrapping.
  - media: embedded text is translate_text(media.description) — the
    original description concatenated with an auto-detected-direction
    translation (see services/llm.py's translate_text, called at
    main.py's two POST /media/upload and POST /media/link call sites, both
    currently just before their `get_embedding(bilingual_description)`
    call). This is NOT display_name (never embedded) and NOT
    description_ar (a different, EN->AR-only translation used only for the
    display column, produced by a different function). Re-running
    translate_text here will not reproduce the exact original translation
    byte-for-byte (LLM output isn't deterministic), but it reproduces the
    same source-text *logic*, which is the best available given the
    original bilingual text was never stored anywhere.

Gemini's gemini-embedding-001 does not auto-normalize truncated
(non-native-3072) output — verified live: an output_dimensionality=1536
vector this script fetched had L2 norm ~0.69, not 1.0. Each vector is
L2-normalized here before being written, per Google's documented guidance,
even though this codebase's pgvector cosine (`<=>`) searches are already
scale-invariant on their own.

Iterates tenant-by-tenant via db.tenant_connection() (these tables use
FORCE ROW LEVEL SECURITY — same reasoning as scripts/backfill_translations.py).
One row's failure is logged and skipped, never aborts the run.

Usage:
    python scripts/backfill_embeddings.py                # embed + write
    python scripts/backfill_embeddings.py --dry-run       # list what would run, no API calls, no writes
    python scripts/backfill_embeddings.py --delay 2.0     # slower, gentler pacing
"""
import argparse
import asyncio
import math
import os
import sys
import time

# Some existing uploaded content has non-ASCII/mojibake bytes that crash a plain `print()` under Windows'
# default cp1252 console encoding. Only the printed preview is at risk here
# (the actual embedding/DB-write path never encodes to console charset) —
# replacing unprintable characters keeps the run going instead of crashing
# partway through a tenant.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.genai import types
from google.genai.errors import ClientError, ServerError

import db
from core.ai_client import gemini_client, GEMINI_EMBEDDING_MODEL
from services.llm import translate_text

GEMINI_EMBEDDING_DIM = 1536


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    return vec if norm == 0 else [x / norm for x in vec]


def get_gemini_embedding(text: str, max_retries: int = 3) -> list[float]:
    # Standalone here rather than reusing services/embeddings.py's
    # get_embedding(): that function now also targets Gemini (cut over
    # alongside this script), but still writes to the OLD `embedding`
    # column for live traffic until migrations/005_cutover_embedding_dimension.sql
    # renames embedding_new -> embedding — this backfill must keep writing
    # embedding_new specifically, so it can't just call get_embedding().
    # Mirrors that function's retry-with-backoff shape.
    last_error = None
    for attempt in range(max_retries):
        try:
            response = gemini_client.models.embed_content(
                model=GEMINI_EMBEDDING_MODEL,
                contents=text,
                config=types.EmbedContentConfig(
                    output_dimensionality=GEMINI_EMBEDDING_DIM,
                    task_type="RETRIEVAL_DOCUMENT",
                ),
            )
            return _l2_normalize(response.embeddings[0].values)
        except (ClientError, ServerError) as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise last_error


def _to_pgvector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in vec) + "]"


def _preview(text: str, width: int = 60) -> str:
    return text if len(text) <= width else text[: width - 3] + "..."


async def backfill_chunks(conn, tenant_id: str, delay: float, dry_run: bool) -> tuple[int, int, int]:
    # Explicit tenant_id filter on both the SELECT and the UPDATE — this must
    # not depend on the RLS session variable alone. The DB role behind
    # DATABASE_URL turned out to be a member of AWS RDS's pg_read_all_data /
    # pg_write_all_data (via rds_superuser), which silently bypasses RLS for
    # this and every other role in that membership chain — confirmed live:
    # every tenant's tenant_connection() saw all 404 rows from every other
    # tenant too, despite the RLS policy and session variable both being
    # individually correct. Until that's fixed at the database/role level
    # (tracked separately), every query in this script scopes itself.
    rows = await conn.fetch(
        "SELECT id, content FROM chunks WHERE tenant_id = $1 AND embedding_new IS NULL",
        tenant_id,
    )
    # Printed unconditionally, even when 0 — so "0 done because 0 were
    # pending" (fine) can never be mistaken for "0 done despite N pending"
    # (a real problem) the way a bare "-> embedded 0" summary line can be.
    print(f"  chunks: {len(rows)} row(s) pending for this tenant")
    done = skipped = failed = 0
    for row in rows:
        text = (row["content"] or "").strip()
        print(f"  chunks.embedding_new <- chunks.id={row['id']}: {_preview(text)!r}")

        if not text:
            print("    !! empty content, skipping")
            skipped += 1
            continue
        if dry_run:
            done += 1
            continue

        try:
            vector = get_gemini_embedding(text)
        except Exception as e:
            print(f"    !! embedding failed, leaving embedding_new null: {e}")
            failed += 1
            continue

        await conn.execute(
            "UPDATE chunks SET embedding_new = $1 WHERE id = $2 AND tenant_id = $3",
            _to_pgvector_literal(vector), row["id"], tenant_id,
        )
        done += 1
        time.sleep(delay)

    return done, skipped, failed


async def backfill_media(conn, tenant_id: str, delay: float, dry_run: bool) -> tuple[int, int, int]:
    # Same explicit tenant_id guard as backfill_chunks above — see that
    # function's comment for why this can't rely on RLS alone right now.
    rows = await conn.fetch(
        "SELECT id, description FROM media WHERE tenant_id = $1 AND embedding_new IS NULL",
        tenant_id,
    )
    print(f"  media: {len(rows)} row(s) pending for this tenant")
    done = skipped = failed = 0
    for row in rows:
        description = (row["description"] or "").strip()
        print(f"  media.embedding_new <- media.id={row['id']}: {_preview(description)!r}")

        if not description:
            print("    !! empty description, skipping")
            skipped += 1
            continue
        if dry_run:
            done += 1
            continue

        try:
            bilingual_description = translate_text(description, tenant_id=tenant_id)
            vector = get_gemini_embedding(bilingual_description)
        except Exception as e:
            print(f"    !! translation/embedding failed, leaving embedding_new null: {e}")
            failed += 1
            continue

        await conn.execute(
            "UPDATE media SET embedding_new = $1 WHERE id = $2 AND tenant_id = $3",
            _to_pgvector_literal(vector), row["id"], tenant_id,
        )
        done += 1
        time.sleep(delay)

    return done, skipped, failed


async def backfill_tenant(tenant_id: str, tenant_name: str, delay: float, dry_run: bool) -> tuple[int, int, int]:
    print(f"\n=== Tenant: {tenant_name} ({tenant_id}) ===")
    async with db.tenant_connection(tenant_id) as conn:
        c_done, c_skipped, c_failed = await backfill_chunks(conn, tenant_id, delay, dry_run)
        m_done, m_skipped, m_failed = await backfill_media(conn, tenant_id, delay, dry_run)

    done, skipped, failed = c_done + m_done, c_skipped + m_skipped, c_failed + m_failed
    verb = "would embed" if dry_run else "embedded"
    print(f"  -> {verb} {done}, skipped {skipped} (empty text), failed {failed}")
    return done, skipped, failed


async def main_async(delay: float, dry_run: bool) -> None:
    await db.init_pool()
    try:
        async with db.pool.acquire() as conn:
            tenants = await conn.fetch("SELECT id, name FROM tenants ORDER BY created_at")

        totals = [0, 0, 0]  # done, skipped, failed
        for row in tenants:
            result = await backfill_tenant(str(row["id"]), row["name"], delay, dry_run)
            totals = [a + b for a, b in zip(totals, result)]
    finally:
        await db.close_pool()

    done, skipped, failed = totals
    verb = "Would embed" if dry_run else "Embedded"
    print(f"\n=== Totals across all tenants ===")
    print(f"{verb}: {done}   Skipped (empty text): {skipped}   Failed: {failed}")
    if failed and not dry_run:
        print(
            "Some rows failed and were left with embedding_new = NULL — safe to re-run "
            "this script (it only processes rows still missing embedding_new)."
        )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Backfill embedding_new on chunks/media with Gemini gemini-embedding-001 "
            "(1536-dim), for rows that still only have an OpenAI embedding."
        ),
    )
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="Seconds to sleep between embedding calls (default: 1.0) — keeps this from "
             "hammering the API and running up unnecessary cost on a large backlog.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List what would be embedded without calling any API or writing anything.",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args.delay, args.dry_run))


if __name__ == "__main__":
    main()
