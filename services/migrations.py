"""Applies migrations/*.sql on startup, each exactly once.

Applied files are recorded in schema_migrations. Files run in filename
order, each in its own transaction, under an advisory lock so two backend
instances starting together can't apply the same file twice.

Never stops the app from starting: a failure is logged (with the file
name) and the remaining files are skipped until the next start, so the
app keeps serving everything that doesn't need the new schema.
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
_LOCK_KEY = 7_316_002_026  # any constant; identifies "vitabot migrations"


async def apply_pending_migrations(pool, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Returns the files applied this run."""
    files = sorted(migrations_dir.glob("*.sql")) if migrations_dir.is_dir() else []
    if not files:
        return []
    applied_now: list[str] = []
    try:
        async with pool.acquire() as conn:
            await conn.execute("SELECT pg_advisory_lock($1)", _LOCK_KEY)
            try:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS public.schema_migrations (
                        filename text PRIMARY KEY,
                        applied_at timestamp with time zone DEFAULT now() NOT NULL
                    )
                    """
                )
                done = {r["filename"] for r in await conn.fetch("SELECT filename FROM public.schema_migrations")}
                for path in files:
                    if path.name in done:
                        continue
                    sql = path.read_text(encoding="utf-8")
                    try:
                        async with conn.transaction():
                            await conn.execute(sql)
                            await conn.execute(
                                "INSERT INTO public.schema_migrations (filename) VALUES ($1)", path.name,
                            )
                    except Exception:
                        logger.exception(
                            f"Migration {path.name} failed and was rolled back; later migrations skipped. "
                            "The app keeps running; fix the cause (e.g. the DB user lacks CREATE rights) and restart."
                        )
                        break
                    applied_now.append(path.name)
                    logger.info(f"Applied migration {path.name}")
            finally:
                await conn.execute("SELECT pg_advisory_unlock($1)", _LOCK_KEY)
    except Exception:
        logger.exception("Could not check for pending migrations; the app keeps running")
    return applied_now
