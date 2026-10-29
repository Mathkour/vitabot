"""
One-off cleanup script: deletes excel_rows (and their linked chunks) whose
row_data is entirely blank across every stored column.

These come from documents/upload's .xlsx branch having inserted one
excel_rows record per row openpyxl's used-range scan reported, including
rows that were only formatted (borders/column widths) but never actually
contained data. services/import_users.py now filters these out at upload
time, but rows from spreadsheets uploaded before that fix are still sitting
in the database. This script is a one-time cleanup for that existing data,
not a permanent migration — run once and discard.

Usage:
    python cleanup_blank_excel_rows.py            # dry run: report only, no deletes
    python cleanup_blank_excel_rows.py --execute   # actually delete

Runs across every tenant, respecting each tenant's row-level-security
context via db.tenant_connection, the same way the rest of the app does.
"""

import asyncio
import sys
from collections import defaultdict

import db

FIND_BLANK_ROWS_QUERY = """
    SELECT er.id, er.chunk_id, d.filename
    FROM excel_rows er
    JOIN documents d ON d.id = er.document_id AND d.tenant_id = er.tenant_id
    WHERE er.tenant_id = $1
      AND NOT EXISTS (
        SELECT 1 FROM jsonb_each_text(er.row_data) AS kv(key, value)
        WHERE btrim(value) <> ''
      )
"""

DELETE_EXCEL_ROWS_QUERY = """
    DELETE FROM excel_rows
    WHERE tenant_id = $1
      AND id = ANY($2::uuid[])
"""

DELETE_CHUNKS_QUERY = """
    DELETE FROM chunks
    WHERE tenant_id = $1
      AND id = ANY($2::uuid[])
"""


async def main() -> None:
    execute = "--execute" in sys.argv

    await db.init_pool()
    try:
        async with db.pool.acquire() as conn:
            tenants = await conn.fetch("SELECT id, name FROM tenants ORDER BY name")

        total_rows_found = 0
        total_tenants_affected = 0

        for tenant in tenants:
            tenant_id = str(tenant["id"])
            async with db.tenant_connection(tenant_id) as conn:
                blank_rows = await conn.fetch(FIND_BLANK_ROWS_QUERY, tenant_id)

                if not blank_rows:
                    continue

                total_tenants_affected += 1
                total_rows_found += len(blank_rows)

                by_document = defaultdict(int)
                for r in blank_rows:
                    by_document[r["filename"]] += 1

                print(f"{tenant['name']} ({tenant_id}): {len(blank_rows)} blank excel_rows")
                for filename, count in sorted(by_document.items()):
                    print(f"    - {filename}: {count} blank row(s)")

                if execute:
                    row_ids = [r["id"] for r in blank_rows]
                    chunk_ids = [r["chunk_id"] for r in blank_rows if r["chunk_id"] is not None]

                    await conn.execute(DELETE_EXCEL_ROWS_QUERY, tenant_id, row_ids)
                    if chunk_ids:
                        await conn.execute(DELETE_CHUNKS_QUERY, tenant_id, chunk_ids)
                    print(f"    -> deleted {len(row_ids)} excel_rows and {len(chunk_ids)} chunks")

        print()
        if total_rows_found == 0:
            print("No blank excel_rows found. Nothing to do.")
        elif execute:
            print(
                f"Done. Deleted {total_rows_found} blank excel_rows across "
                f"{total_tenants_affected} tenant(s)."
            )
        else:
            print(
                f"DRY RUN — found {total_rows_found} blank excel_rows across "
                f"{total_tenants_affected} tenant(s). Re-run with --execute to delete."
            )
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
