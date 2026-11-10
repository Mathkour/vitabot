from dataclasses import dataclass

from fastapi import Depends , HTTPException , Header , Request
from fastapi.security import HTTPBearer , HTTPAuthorizationCredentials
from core.security import decode_access_token, ACCESS_TOKEN_COOKIE_NAME
import asyncpg
import os

from loguru import logger

import db

# auto_error=False: the cookie is the primary auth source now, so a request
# with no Authorization header must not be rejected before _get_token() gets
# a chance to fall back and check the cookie itself.
bearer_scheme=HTTPBearer(auto_error=False)

def _get_token(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None,
) -> str:
    # An explicit Authorization header wins over the cookie. The web app is
    # cookie-only; a Bearer header is for API clients and tests.
    if credentials:
        return credentials.credentials
    token = request.cookies.get(ACCESS_TOKEN_COOKIE_NAME)
    if token:
        return token
    raise HTTPException(status_code=401, detail="Not authenticated")


async def _verify_token_version(payload: dict) -> None:
    """Rejects a token whose "tv" claim is behind the user's current
    users.token_version — that is how POST /logout invalidates tokens
    server-side instead of only clearing the cookie.

    Tokens without a "tv" claim are pre-upgrade and still accepted until they
    expire (so applying migration 009 does not log anyone out)."""
    user_id = payload.get("user_id")
    token_version = payload.get("tv")
    if user_id is None or token_version is None:
        return
    try:
        async with db.pool.acquire() as conn:
            current = await conn.fetchval(
                "SELECT token_version FROM users WHERE id = $1", user_id
            )
    except asyncpg.UndefinedColumnError:
        # Migration 009 not applied yet — degrade to the old behaviour (token
        # valid until it expires) rather than locking everyone out.
        logger.warning(
            "users.token_version is missing; run "
            "migrations/009_email_lower_unique_and_token_version.sql — "
            "logout session-invalidation is inactive"
        )
        return
    if current is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if int(current) != int(token_version):
        raise HTTPException(status_code=401, detail="Session expired, please log in again")


async def _auth_payload(
        request: Request,
        credentials:HTTPAuthorizationCredentials | None,
)->dict:
    """Decodes and verifies the request's token once per request, caching the
    result on request.state so the several get_current_* dependencies an
    endpoint may use don't each re-decode and re-query."""
    payload = getattr(request.state, "auth_payload", None)
    if payload is None:
        token = _get_token(request, credentials)
        payload = decode_access_token(token)
        if payload is None:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        request.state.auth_payload = payload
    if not getattr(request.state, "auth_version_checked", False):
        await _verify_token_version(payload)
        request.state.auth_version_checked = True
    return payload


async def get_current_user_id(
        request: Request,
        credentials:HTTPAuthorizationCredentials | None=Depends(bearer_scheme),)->str:
    payload = await _auth_payload(request, credentials)
    user_id=payload.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401,detail="Token missing user")
    return user_id

async def get_current_tenant(
        request: Request,
        credentials:HTTPAuthorizationCredentials | None=Depends(bearer_scheme),
        x_acting_tenant:str | None=Header(default=None,)
)->str:
    payload = await _auth_payload(request, credentials)
    tenant_id=payload.get("tenant_id")
    if tenant_id is None :
        raise HTTPException(status_code=401,detail="Token missing tenant ")
    role=payload.get("role")
    if role == "superadmin" and x_acting_tenant:
        return x_acting_tenant
    return tenant_id

async def get_current_role(
        request: Request,
        credentials:HTTPAuthorizationCredentials | None=Depends(bearer_scheme),
)->str:
    payload = await _auth_payload(request, credentials)
    role=payload.get("role")
    if role is None:
        raise HTTPException(status_code=401,detail="Token missing role")
    return role

def require_superadmin(
        role:str=Depends(get_current_role),
)-> None:
    if role!="superadmin":
        raise HTTPException(status_code=403,detail="superadmin access required")


def require_admin(
        tenant_id: str = Depends(get_current_tenant),
        role: str = Depends(get_current_role),
) -> str:
    # Same shape as get_current_tenant (returns tenant_id) so it's a drop-in
    # replacement wherever an endpoint currently does
    # `tenant_id: str = Depends(get_current_tenant)` but the action is
    # admin-only. A superadmin acting on a tenant (x-acting-tenant header,
    # already resolved into tenant_id by get_current_tenant) is allowed
    # through too, matching the frontend's adminGuard behavior.
    if role not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="admin access required")
    return tenant_id


async def get_current_company_id(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str | None:
    # Mirrors get_current_tenant/get_current_role: read straight off the JWT
    # (set at /login) rather than a fresh DB lookup, so it's "as of login
    # time" like role/tenant_id already are elsewhere in this file.
    payload = await _auth_payload(request, credentials)
    return payload.get("company_id")


@dataclass
class UserScope:
    tenant_id: str
    role: str
    company_id: str | None


def require_admin_or_company_admin(
        tenant_id: str = Depends(get_current_tenant),
        role: str = Depends(get_current_role),
        company_id: str | None = Depends(get_current_company_id),
) -> UserScope:
    """For the per-company user-management endpoints (routers/companies.py,
    the /users CRUD in main.py): a tenant 'admin'/'superadmin' manages every
    company's users, while a 'company_admin' is scoped to only their own
    company_id — callers must enforce that scoping themselves using the
    returned UserScope (this dependency only establishes who's allowed in at
    all, not what they can touch)."""
    if role not in ("admin", "superadmin", "company_admin"):
        raise HTTPException(status_code=403, detail="admin access required")
    if role == "company_admin" and not company_id:
        # Shouldn't happen in practice (company_admin is only ever assigned
        # together with a company_id), but a company_admin with no company
        # must not fall through to "sees everything".
        raise HTTPException(status_code=403, detail="No company assigned")
    return UserScope(tenant_id=tenant_id, role=role, company_id=company_id)



VITA_CARE_TENANT_ID = os.getenv("VITA_CARE_TENANT_ID")


def require_vita_care_tenant(
        tenant_id: str = Depends(get_current_tenant),
) -> str:
    if not VITA_CARE_TENANT_ID or str(tenant_id) != VITA_CARE_TENANT_ID:
        raise HTTPException(status_code=403, detail="Odoo insights are only available for Vita Care")
    return tenant_id


def require_vita_care_admin(
        tenant_id: str = Depends(require_admin),
) -> str:
    # The companies feature (routers/companies.py) is schema-generic but
    # only wired up/exposed for Vita Care for now — same "only this tenant"
    # gating pattern as require_vita_care_tenant above, composed with the
    # admin-role check instead of being open to every Vita Care member.
    if not VITA_CARE_TENANT_ID or str(tenant_id) != VITA_CARE_TENANT_ID:
        raise HTTPException(status_code=403, detail="Companies are only available for Vita Care")
    return tenant_id
