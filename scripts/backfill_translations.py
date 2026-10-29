"""
One-off backfill: fills in the Arabic (_ar) columns added in
migrations/003_add_arabic_translation_columns.sql for rows that already
existed before this feature. New rows already get translated automatically
at write time (see main.py's _translate_ar_safe) — this script only needs to
run once per environment, after the migration, to catch up existing data.

Iterates tenant-by-tenant via db.tenant_connection() (these tables all use
FORCE ROW LEVEL SECURITY, so a plain pool.acquire() without setting
app.current_tenant would just see zero rows — same reasoning as every other
cross-tenant script in this codebase).

Usage:
    python scripts/backfill_translations.py                # translate + write
    python scripts/backfill_translations.py --dry-run       # just list what would run
    python scripts/backfill_translations.py --delay 2.0     # slower, gentler pacing
"""
import argparse
import asyncio
import os
import sys
import time

# Some existing content has non-ASCII/mojibake bytes that crash a plain
# print() under Windows' default cp1252 console encoding — only the printed
# preview is at risk (not the actual translate/DB-write path), so replacing
# unprintable characters keeps the run going instead of crashing partway
# through a tenant.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
from services.llm import translate_verbatim

# (table, id column, English column, Arabic column to fill)
COLUMNS_TO_BACKFILL = [
    ("faq_items", "id", "question", "question_ar"),
    ("faq_items", "id", "answer", "answer_ar"),
    ("error_solutions", "id", "error_text", "error_text_ar"),
    ("error_solutions", "id", "solution_text", "solution_text_ar"),
    ("media", "id", "description", "description_ar"),
    ("media", "id", "display_name", "display_name_ar"),
    ("documents", "id", "display_name", "display_name_ar"),
]


async def _backfill_column(conn, table: str, id_col: str, en_col: str, ar_col: str,
                            tenant_id: str, delay: float, dry_run: bool) -> int:
    # Explicit tenant_id filter on both the SELECT and the UPDATE, not just
    # the RLS session variable set by db.tenant_connection() — the DB role
    # behind DATABASE_URL turned out to be a member of AWS RDS's
    # pg_read_all_data / pg_write_all_data (via rds_superuser), which
    # silently bypasses RLS for this and every other role in that
    # membership chain, confirmed live against this same table set. Until
    # that's fixed at the database/role level (tracked separately), this
    # script scopes itself explicitly rather than trusting RLS alone.
    rows = await conn.fetch(
        f"SELECT {id_col} AS row_id, {en_col} AS text FROM {table} "
        f"WHERE tenant_id = $1 AND {ar_col} IS NULL AND {en_col} IS NOT NULL AND {en_col} <> ''",
        tenant_id,
    )
    done = 0
    for row in rows:
        text = row["text"]
        preview = text if len(text) <= 60 else text[:57] + "..."
        print(f"  {table}.{ar_col} <- {table}.{id_col}={row['row_id']}: {preview!r}")

        if dry_run:
            done += 1
            continue

        try:
            translated = translate_verbatim(text, "Arabic", tenant_id=tenant_id)
        except Exception as e:
            print(f"    !! translation failed, leaving null: {e}")
            continue

        await conn.execute(
            f"UPDATE {table} SET {ar_col} = $1 WHERE {id_col} = $2 AND tenant_id = $3",
            translated, row["row_id"], tenant_id,
        )
        done += 1
        time.sleep(delay)  # basic rate-limiting between LLM calls

    return done


async def backfill_tenant(tenant_id: str, tenant_name: str, delay: float, dry_run: bool) -> None:
    print(f"\n=== Tenant: {tenant_name} ({tenant_id}) ===")
    async with db.tenant_connection(tenant_id) as conn:
        total = 0
        for table, id_col, en_col, ar_col in COLUMNS_TO_BACKFILL:
            total += await _backfill_column(conn, table, id_col, en_col, ar_col, tenant_id, delay, dry_run)
    verb = "would translate" if dry_run else "translated"
    print(f"  -> {verb} {total} value(s) for this tenant")


async def main_async(delay: float, dry_run: bool) -> None:
    await db.init_pool()
    try:
        async with db.pool.acquire() as conn:
            tenants = await conn.fetch("SELECT id, name FROM tenants ORDER BY created_at")
        for row in tenants:
            await backfill_tenant(str(row["id"]), row["name"], delay, dry_run)
    finally:
        await db.close_pool()


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Backfill Arabic (_ar) translations for existing FAQ / Error Solutions / "
            "media / document rows that predate this feature."
        ),
    )
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="Seconds to sleep between LLM calls (default: 1.0) — keeps this from "
             "hammering the API and running up unnecessary cost on a large backlog.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List what would be translated without calling the LLM or writing anything.",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args.delay, args.dry_run))


if __name__ == "__main__":
    main()
