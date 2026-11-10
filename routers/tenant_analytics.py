"""Per-tenant analytics/insights for tenant admins — distinct from
routers/ai_monitoring.py, which is superadmin-only and aggregates across
every tenant. Everything here is scoped to the calling admin's own tenant
via require_admin (tenant_id comes from the JWT, never a query param), and
reuses ai_predictions_log — already written on every /ask call — instead of
adding new instrumentation:

  - "most frequent questions"  -> endpoint='ask' rows, grouped by the
    logged question text (request_summary).
  - "weak/low-confidence answers" -> endpoint='no_info_response' rows: this
    is already logged exactly when the RAG pipeline found no relevant
    context and fell back to a canned "I don't know" reply (see
    generate_no_info_response in services/llm.py and its call sites in
    main.py's /ask handler) — the simplest available proxy for "the bot
    didn't have a good answer" without building a real confidence model.
    The `confidence_score` column on ai_predictions_log exists but is never
    populated by any current caller, so it isn't usable (yet).
  - satisfaction rate -> the existing ratings table (POST /rate), which is
    already live and tenant-scoped via its own RLS policy.
"""
import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query

import db
from core.auth import require_admin

router = APIRouter(prefix="/analytics", tags=["tenant-analytics"])


@router.get("/top-questions")
async def top_questions(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(20, ge=1, le=100),
    tenant_id: str = Depends(require_admin),
):
    async with db.tenant_connection(tenant_id) as conn:
        rows = await conn.fetch(
            """
            SELECT request_summary AS question, count(*) AS count
            FROM ai_predictions_log a
            WHERE tenant_id = $1
              AND endpoint = 'ask'
              AND request_summary IS NOT NULL
              AND created_at >= now() - ($2 * interval '1 day')
              -- generate_answer() logs an 'ask' row before its caller checks
              -- for the [[NO_INFO]] marker, so a question that ultimately
              -- got the "don't know" fallback is double-logged (one 'ask'
              -- row, one 'no_info_response' row). Exclude those here so a
              -- weak-answer question only ever shows under Weak Answers,
              -- never under Most Frequent Questions.
              AND NOT EXISTS (
                SELECT 1 FROM ai_predictions_log w
                WHERE w.tenant_id = a.tenant_id
                  AND w.endpoint = 'no_info_response'
                  AND w.request_summary = a.request_summary
                  AND w.created_at >= now() - ($2 * interval '1 day')
              )
            GROUP BY request_summary
            ORDER BY count DESC, max(created_at) DESC
            LIMIT $3
            """,
            tenant_id, days, limit,
        )
    return [{"question": r["question"], "count": r["count"]} for r in rows]


@router.get("/weak-answers")
async def weak_answers(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(20, ge=1, le=100),
    tenant_id: str = Depends(require_admin),
):
    async with db.tenant_connection(tenant_id) as conn:
        rows = await conn.fetch(
            """
            SELECT request_summary AS question, count(*) AS count, max(created_at) AS last_seen
            FROM ai_predictions_log
            WHERE tenant_id = $1
              AND endpoint = 'no_info_response'
              AND request_summary IS NOT NULL
              AND created_at >= now() - ($2 * interval '1 day')
            GROUP BY request_summary
            ORDER BY count DESC, last_seen DESC
            LIMIT $3
            """,
            tenant_id, days, limit,
        )
    return [
        {"question": r["question"], "count": r["count"], "last_seen": r["last_seen"]}
        for r in rows
    ]


@router.get("/satisfaction")
async def satisfaction(
    days: int = Query(7, ge=1, le=90),
    tenant_id: str = Depends(require_admin),
):
    async with db.tenant_connection(tenant_id) as conn:
        row = await conn.fetchrow(
            """
            SELECT
                count(*) FILTER (WHERE score = 1) AS thumbs_up,
                count(*) FILTER (WHERE score = -1) AS thumbs_down
            FROM ratings
            WHERE tenant_id = $1
              AND created_at >= now() - ($2 * interval '1 day')
            """,
            tenant_id, days,
        )
    total = row["thumbs_up"] + row["thumbs_down"]
    rate = round(100 * row["thumbs_up"] / total, 1) if total else None
    return {
        "thumbs_up": row["thumbs_up"],
        "thumbs_down": row["thumbs_down"],
        "total_rated": total,
        "satisfaction_rate": rate,
    }


@router.get("/timeseries")
async def timeseries(
    days: int = Query(7, ge=1, le=90),
    interval: str = Query("day", pattern="^(hour|day)$"),
    tenant_id: str = Depends(require_admin),
):
    # `interval` is constrained to "hour"/"day" by the pattern above (FastAPI
    # validates it before this line runs), so it's safe to splice into
    # date_trunc's first argument — same pattern as
    # routers/ai_monitoring.py's get_timeseries.
    async with db.tenant_connection(tenant_id) as conn:
        rows = await conn.fetch(
            f"""
            SELECT date_trunc('{interval}', created_at) AS bucket,
                   count(*) AS call_count,
                   avg(response_time_ms) AS avg_response_time_ms
            FROM ai_predictions_log
            WHERE tenant_id = $1
              AND endpoint = 'ask'
              AND created_at >= now() - ($2 * interval '1 day')
            GROUP BY bucket
            ORDER BY bucket
            """,
            tenant_id, days,
        )
    return [
        {
            "bucket": r["bucket"].isoformat(),
            "call_count": r["call_count"],
            "avg_response_time_ms": round(r["avg_response_time_ms"] or 0),
        }
        for r in rows
    ]


async def _build_tenant_digest(conn, tenant_id: str, days: int) -> dict:
    top = await conn.fetch(
        """
        SELECT request_summary AS question, count(*) AS count
        FROM ai_predictions_log a
        WHERE tenant_id = $1 AND endpoint = 'ask' AND request_summary IS NOT NULL
          AND created_at >= now() - ($2 * interval '1 day')
          AND NOT EXISTS (
            SELECT 1 FROM ai_predictions_log w
            WHERE w.tenant_id = a.tenant_id
              AND w.endpoint = 'no_info_response'
              AND w.request_summary = a.request_summary
              AND w.created_at >= now() - ($2 * interval '1 day')
          )
        GROUP BY request_summary ORDER BY count DESC LIMIT 10
        """,
        tenant_id, days,
    )
    weak = await conn.fetch(
        """
        SELECT request_summary AS question, count(*) AS count
        FROM ai_predictions_log
        WHERE tenant_id = $1 AND endpoint = 'no_info_response' AND request_summary IS NOT NULL
          AND created_at >= now() - ($2 * interval '1 day')
        GROUP BY request_summary ORDER BY count DESC LIMIT 10
        """,
        tenant_id, days,
    )
    rated = await conn.fetchrow(
        """
        SELECT count(*) FILTER (WHERE score = 1) AS thumbs_up,
               count(*) FILTER (WHERE score = -1) AS thumbs_down
        FROM ratings WHERE tenant_id = $1 AND created_at >= now() - ($2 * interval '1 day')
        """,
        tenant_id, days,
    )
    total = rated["thumbs_up"] + rated["thumbs_down"]
    return {
        "tenant_id": tenant_id,
        "days": days,
        "top_questions": [{"question": r["question"], "count": r["count"]} for r in top],
        "weak_answers": [{"question": r["question"], "count": r["count"]} for r in weak],
        "satisfaction_rate": round(100 * rated["thumbs_up"] / total, 1) if total else None,
    }


@router.post("/digest-run")
async def run_digest(
    days: int = Query(7, ge=1, le=90),
    x_analytics_digest_secret: str = Header(...),
):
    """Computes (but does not yet email) each tenant's digest — meant to be
    called by an external scheduler (e.g. a Render Cron Job hitting this
    endpoint weekly with days=7, or monthly with days=30), same
    shared-secret pattern as /auth/odoo-sso. Email delivery is intentionally
    not wired up yet (no email provider/infra exists in this project at
    all — see PRODUCT_AUDIT.md); this endpoint is the plug point for it:
    swap the final `return` for an actual send once a provider is chosen,
    looping over `digests` below.
    """
    if not secrets.compare_digest(x_analytics_digest_secret, os.getenv("ANALYTICS_DIGEST_SECRET", "")):
        raise HTTPException(status_code=403, detail="Invalid digest secret")

    async with db.pool.acquire() as conn:
        tenant_ids = [r["id"] for r in await conn.fetch("SELECT id FROM tenants")]

    digests = []
    for tenant_id in tenant_ids:
        async with db.tenant_connection(str(tenant_id)) as conn:
            digests.append(await _build_tenant_digest(conn, str(tenant_id), days))

    return {"days": days, "tenant_count": len(digests), "digests": digests}
