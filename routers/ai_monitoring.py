from fastapi import APIRouter, Depends, Query

import db
from core.auth import require_superadmin

router = APIRouter(prefix="/admin/ai-monitoring", tags=["ai-monitoring"])


def _finalize_group(groups: dict) -> list[dict]:
    result = []
    for g in groups.values():
        calls = g["total_calls"]
        weighted_time = g.pop("_weighted_time")
        g["avg_response_time_ms"] = round(weighted_time / calls) if calls else 0
        g["success_rate"] = round(100 * g["success_count"] / calls, 1) if calls else 0.0
        result.append(g)
    return sorted(result, key=lambda x: x["total_calls"], reverse=True)


@router.get("/summary")
async def get_summary(
    days: int = Query(7, ge=1, le=365),
    _: None = Depends(require_superadmin),
):
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT endpoint, model_used,
                   count(*) AS total_calls,
                   count(*) FILTER (WHERE status = 'success') AS success_count,
                   count(*) FILTER (WHERE status = 'error') AS error_count,
                   count(*) FILTER (WHERE status = 'timeout') AS timeout_count,
                   avg(response_time_ms) AS avg_response_time_ms
            FROM ai_predictions_log
            WHERE created_at >= now() - ($1 * interval '1 day')
            GROUP BY endpoint, model_used
            """,
            days,
        )

    by_endpoint: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    total_calls = total_success = total_errors = total_timeouts = 0
    weighted_response_time = 0.0

    for r in rows:
        calls = r["total_calls"]
        avg_time = float(r["avg_response_time_ms"]) if r["avg_response_time_ms"] is not None else 0.0

        total_calls += calls
        total_success += r["success_count"]
        total_errors += r["error_count"]
        total_timeouts += r["timeout_count"]
        weighted_response_time += float(avg_time) * calls

        for key, groups in ((r["endpoint"], by_endpoint), (r["model_used"], by_model)):
            g = groups.setdefault(key, {
                "total_calls": 0, "success_count": 0, "error_count": 0,
                "timeout_count": 0, "_weighted_time": 0.0,
            })
            g["total_calls"] += calls
            g["success_count"] += r["success_count"]
            g["error_count"] += r["error_count"]
            g["timeout_count"] += r["timeout_count"]
            g["_weighted_time"] += avg_time * calls

    for key, g in by_endpoint.items():
        g["endpoint"] = key
    for key, g in by_model.items():
        g["model_used"] = key

    return {
        "days": days,
        "total_calls": total_calls,
        "success_count": total_success,
        "error_count": total_errors,
        "timeout_count": total_timeouts,
        "success_rate": round(100 * total_success / total_calls, 1) if total_calls else 0.0,
        "avg_response_time_ms": round(weighted_response_time / total_calls) if total_calls else 0,
        "by_endpoint": _finalize_group(by_endpoint),
        "by_model": _finalize_group(by_model),
    }


@router.get("/timeseries")
async def get_timeseries(
    days: int = Query(7, ge=1, le=365),
    interval: str = Query("day", pattern="^(hour|day)$"),
    _: None = Depends(require_superadmin),
):
    # `interval` is constrained to the "hour"/"day" literals above (FastAPI
    # validates the pattern before this line runs), so it's safe to splice
    # into date_trunc's first argument — it can never carry user-controlled SQL.
    rows = None
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT date_trunc('{interval}', created_at) AS bucket,
                   count(*) AS call_count,
                   avg(response_time_ms) AS avg_response_time_ms,
                   count(*) FILTER (WHERE status != 'success') AS error_count
            FROM ai_predictions_log
            WHERE created_at >= now() - ($1 * interval '1 day')
            GROUP BY bucket
            ORDER BY bucket
            """,
            days,
        )

    return [
        {
            "bucket": r["bucket"].isoformat(),
            "call_count": r["call_count"],
            "avg_response_time_ms": round(r["avg_response_time_ms"] or 0),
            "error_count": r["error_count"],
        }
        for r in rows
    ]


@router.get("/errors")
async def get_errors(
    limit: int = Query(50, ge=1, le=500),
    _: None = Depends(require_superadmin),
):
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, tenant_id, endpoint, model_used, error_message, created_at
            FROM ai_predictions_log
            WHERE status != 'success'
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )
    return [dict(r) for r in rows]
