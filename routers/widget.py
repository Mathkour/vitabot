"""Embeddable chat widget backend: SSO verify + per-tenant widget config.

A partner site (e.g. Credit Plus) signs a short-lived HS256 JWT for its
logged-in user with a secret shared with us. The chat iframe posts that JWT
to /widget/sso/verify and gets back a normal cpbot access token.

Per-tenant settings come from env vars (no schema change), keyed by a slug:
    WIDGET_<SLUG>_TENANT_ID   tenants.id this slug maps to
    WIDGET_<SLUG>_JWT_SECRET  shared HS256 secret (>= 32 chars)
e.g. WIDGET_CREDITPLUS_TENANT_ID / WIDGET_CREDITPLUS_JWT_SECRET.
"""
import os
import re
import secrets

import asyncpg
from fastapi import APIRouter, HTTPException, Query, Request, Response
from jose import JWTError, jwt
from pydantic import BaseModel

import db
from core.security import create_access_token, hash_password, ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter(prefix="/widget", tags=["widget"])

WIDGET_JWT_ALGORITHM = "HS256"
WIDGET_JWT_AUDIENCE = "cpbot-widget"
MIN_SECRET_LENGTH = 32
# The partner token only has to survive the trip from their page to our
# verify call, so anything long-lived is a misconfiguration (and a bigger
# replay window if it leaks).
MAX_PARTNER_TOKEN_TTL_SECONDS = 3600

_SLUG_RE = re.compile(r"^[a-z0-9]{1,32}$")


def _tenant_settings(slug: str) -> tuple[str, str]:
    """Returns (tenant_id, jwt_secret) for a widget slug, or raises 404."""
    if not _SLUG_RE.match(slug):
        raise HTTPException(status_code=404, detail="Unknown tenant")
    prefix = f"WIDGET_{slug.upper()}_"
    tenant_id = os.getenv(prefix + "TENANT_ID", "").strip()
    secret = os.getenv(prefix + "JWT_SECRET", "")
    if not tenant_id:
        raise HTTPException(status_code=404, detail="Unknown tenant")
    return tenant_id, secret


@router.get("/config")
async def widget_config(tenant: str = Query(..., min_length=1, max_length=32)):
    """Public, non-sensitive customization used by the widget before login."""
    tenant_id, _ = _tenant_settings(tenant.lower())

    async with db.tenant_connection(tenant_id) as conn:
        row = await conn.fetchrow(
            "SELECT name, primary_color, action_color, logo_path FROM tenants WHERE id = $1",
            tenant_id,
        )
        bot_name = await conn.fetchval(
            "SELECT name FROM bots WHERE tenant_id = $1 ORDER BY created_at LIMIT 1",
            tenant_id,
        )
        questions = await conn.fetch(
            "SELECT question FROM suggested_questions WHERE tenant_id = $1",
            tenant_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown tenant")

    return {
        "tenant": tenant.lower(),
        "bot_name": bot_name or row["name"],
        "tenant_name": row["name"],
        "icon_color": row["action_color"] or "#2563EB",
        "primary_color": row["primary_color"] or "#16244C",
        "logo_path": row["logo_path"],
        "suggested_questions": [r["question"] for r in questions],
    }


class WidgetSSORequest(BaseModel):
    tenant: str
    token: str


def _verify_partner_token(token: str, secret: str) -> dict:
    if len(secret) < MIN_SECRET_LENGTH:
        # Server-side misconfiguration, not the caller's fault.
        raise HTTPException(status_code=503, detail="Widget SSO is not configured for this tenant")
    try:
        # Pin the algorithm: never let the token header choose it (blocks
        # alg=none / algorithm-confusion tricks).
        claims = jwt.decode(
            token,
            secret,
            algorithms=[WIDGET_JWT_ALGORITHM],
            audience=WIDGET_JWT_AUDIENCE,
            options={"require_exp": True, "require_aud": True, "require_sub": True},
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    iat = claims.get("iat")
    if isinstance(iat, (int, float)) and claims["exp"] - iat > MAX_PARTNER_TOKEN_TTL_SECONDS:
        raise HTTPException(status_code=401, detail="Token lifetime too long")
    return claims


async def _find_or_create_user(conn, tenant_id: str, email: str, name: str):
    select_sql = (
        "SELECT id, tenant_id, role, username FROM users "
        "WHERE LOWER(email) = LOWER($1) AND tenant_id = $2"
    )
    user = await conn.fetchrow(select_sql, email, tenant_id)
    if user is not None:
        return user

    hashed = hash_password(secrets.token_urlsafe(32))  # SSO users never log in by password
    insert_sql = (
        "INSERT INTO users (tenant_id, email, password_hash, role, username) "
        "VALUES ($1, $2, $3, 'member', $4) RETURNING id, tenant_id, role, username"
    )
    # Each attempt runs in a savepoint: a unique violation would otherwise
    # abort the whole surrounding tenant_connection transaction.
    for username in (name, f"{name}-{secrets.token_hex(3)}"):
        try:
            async with conn.transaction():
                return await conn.fetchrow(insert_sql, tenant_id, email, hashed, username)
        except asyncpg.UniqueViolationError:
            # Either a concurrent verify for the same email won the race, or
            # the display name collides with another user.
            user = await conn.fetchrow(select_sql, email, tenant_id)
            if user is not None:
                return user
    raise HTTPException(status_code=409, detail="Could not create user")


@router.post("/sso/verify")
async def widget_sso_verify(body: WidgetSSORequest):
    slug = body.tenant.lower()
    tenant_id, secret = _tenant_settings(slug)
    claims = _verify_partner_token(body.token, secret)

    email = str(claims.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=401, detail="Token missing email")
    name = str(claims.get("name") or "").strip() or email.split("@")[0]
    name = name[:100]

    async with db.tenant_connection(tenant_id) as conn:
        user = await _find_or_create_user(conn, tenant_id, email, name)

    # The role is deliberately NOT taken from the partner token, and is
    # capped at "member" even if the matched cpbot account is an admin: the
    # widget is a chat-only surface and must never mint an admin session
    # from a token signed on a third-party site.
    access_token = create_access_token({
        "user_id": str(user["id"]),
        "tenant_id": str(user["tenant_id"]),
        "role": "member",
        "username": user["username"],
        "email": email,
        "widget": True,
    })
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": {"username": user["username"], "email": email},
    }


def _allowed_origins() -> set[str]:
    raw = os.getenv("WIDGET_ALLOWED_ORIGINS", "https://credit-plus.me,https://www.credit-plus.me")
    return {o.strip().rstrip("/") for o in raw.split(",") if o.strip()}


async def widget_cors_middleware(request: Request, call_next):
    """CORS for /widget/* only, driven by WIDGET_ALLOWED_ORIGINS.

    The widget script runs on the partner's page and calls /widget/config
    from there, so that origin must be allowed here without widening the
    app-wide CORS policy. Credentials are never allowed on these responses.
    """
    origin = request.headers.get("origin")
    if not request.url.path.startswith("/widget/") or not origin or origin.rstrip("/") not in _allowed_origins():
        return await call_next(request)

    headers = {"Access-Control-Allow-Origin": origin, "Vary": "Origin"}
    if request.method == "OPTIONS" and "access-control-request-method" in request.headers:
        headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        headers["Access-Control-Allow-Headers"] = request.headers.get("access-control-request-headers", "content-type")
        headers["Access-Control-Max-Age"] = "600"
        return Response(status_code=204, headers=headers)

    response = await call_next(request)
    for key, value in headers.items():
        response.headers[key] = value
    if "access-control-allow-credentials" in response.headers:
        del response.headers["access-control-allow-credentials"]
    return response
