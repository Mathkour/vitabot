import asyncio

from loguru import logger

import db

VALID_STATUSES = {"success", "error", "timeout"}
MAX_SUMMARY_LEN = 300


async def _insert_ai_prediction_log(
    tenant_id, endpoint, model_used, request_summary, response_time_ms,
    status, confidence_score, error_message,
):
    try:
        async with db.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ai_predictions_log
                    (tenant_id, endpoint, model_used, request_summary, response_time_ms,
                     status, confidence_score, error_message)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                tenant_id, endpoint, model_used, request_summary, response_time_ms,
                status, confidence_score, error_message,
            )
    except Exception:
        logger.exception(f"ai_predictions_log insert failed for endpoint={endpoint}")


def log_ai_prediction(
    *,
    endpoint: str,
    model_used: str,
    response_time_ms: int,
    status: str,
    tenant_id: str | None = None,
    request_summary: str | None = None,
    confidence_score: float | None = None,
    error_message: str | None = None,
) -> None:
    """Structured, fire-and-forget AI-call log — meant to sit right next to the
    existing Loguru logging around every LLM call, not replace it. Never raises
    and never blocks the caller: the insert runs as a background task on the
    current event loop, and any DB failure is only logged, never propagated.

    Callable from both async endpoint code and the plain sync functions in
    services/llm.py and services/odoo_agent.py, as long as it runs somewhere
    downstream of an async request (there always is a running event loop in
    that case).
    """
    if status not in VALID_STATUSES:
        status = "error"

    summary = (request_summary or "")[:MAX_SUMMARY_LEN] or None

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.debug(f"log_ai_prediction skipped (no running event loop) for endpoint={endpoint}")
        return

    loop.create_task(_insert_ai_prediction_log(
        tenant_id, endpoint, model_used, summary, response_time_ms,
        status, confidence_score, error_message,
    ))
