"""Activity Log: records who changed what in the admin area.

log_activity never raises: a failed log write (or the table not existing
yet) must never undo or fail the admin's actual change. The savepoint keeps
a failed INSERT from aborting the caller's transaction."""
from __future__ import annotations

from loguru import logger

import db

MAX_SUMMARY = 300


async def log_activity(conn, tenant_id: str, user_id: str | None, action: str, summary: str) -> None:
    try:
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO activity_log (tenant_id, user_id, action, summary) VALUES ($1, $2, $3, $4)",
                tenant_id, user_id, action, (summary or "")[:MAX_SUMMARY],
            )
    except Exception:
        logger.warning(f"Could not write activity log entry {action!r}")


async def log_detached(tenant_id: str, user_id: str | None, action: str, summary: str) -> None:
    """log_activity on its own connection, for endpoints that don't hold one
    at the point of logging. Never raises."""
    try:
        async with db.tenant_connection(tenant_id) as conn:
            await log_activity(conn, tenant_id, user_id, action, summary)
    except Exception:
        logger.warning(f"Could not write activity log entry {action!r}")


async def label_for(tenant_id: str, sql: str, *args) -> str:
    """Human-readable name of something about to be deleted (looked up first,
    so the log says what it was). Falls back to its id."""
    try:
        async with db.tenant_connection(tenant_id) as conn:
            value = await conn.fetchval(sql, *args)
        return str(value) if value else str(args[0])
    except Exception:
        return str(args[0])
