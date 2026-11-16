from fastapi import FastAPI, HTTPException,Depends, UploadFile,File,Form,Response,Header, Request
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from contextlib import asynccontextmanager
from collections import Counter
from datetime import datetime, timedelta, timezone
import asyncio
import hashlib
import hmac
import json
import mimetypes
import asyncpg
import db
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from core.security import hash_password
from core.security import hash_password,verify_password,ALGO,create_access_token,decode_access_token,set_auth_cookie,clear_auth_cookie,ACCESS_TOKEN_COOKIE_NAME
from core.auth import get_current_tenant , get_current_user_id , get_current_role , require_superadmin , require_admin ,require_vita_care_tenant , require_vita_care_admin , VITA_CARE_TENANT_ID , require_admin_or_company_admin , UserScope
from services.import_users import parse_excel, detect_mapping
from services.extraction import extract_text,extract_slides_from_pptx
from services.chunking import chunck_text
from services.embeddings import get_embedding
from services.llm import generate_answer , translate_text , generate_admin_answer,generate_no_info_response,translate_to_english,select_relevant_slides,translate_verbatim,select_matching_video
from services.search import search_chunk , search_media
from services.company_slug import normalize_company_slug, slug_to_display_name
from fastapi.middleware.cors import CORSMiddleware
import os
import secrets
import uuid as uuid_lib
from fastapi.responses import FileResponse
from services.tts import synthesize_speech , transcribe_audio, get_fallback_audio, TTSGenerationFailed
from services.odoo_service import get_sales_summary,get_top_products,get_customer_summary,OdooError,build_odoo_context,OdooClient
from services import odoo_service
from services import storage
from services.odoo_agent import odoo_agent_ask
from routers.ai_monitoring import router as ai_monitoring_router
from routers.faq_categories import router as faq_categories_router, validate_category_id
from routers.tenant_analytics import router as tenant_analytics_router
from routers.companies import router as companies_router
from routers.support_tickets import router as support_tickets_router
from routers.answer_feedback import router as answer_feedback_router
from routers.admin_overview import router as admin_overview_router
from routers.unanswered_questions import (
    router as unanswered_questions_router, record_unanswered_question, ANSWERS_DOC_FILENAME,
)
import time
from services.migrations import apply_pending_migrations
from services.faq_index import FAQ_INDEX_DOC_FILENAME, index_entry, delete_chunk, backfill_unindexed
from services.activity import log_detached, label_for
from loguru import logger
import re
from pydantic import BaseModel , EmailStr


@asynccontextmanager
async def lifespan(app:FastAPI):
    await db.init_pool()
    # Applies migrations/*.sql not applied yet; never blocks startup.
    await apply_pending_migrations(db.pool)
    # Indexes FAQ items / error solutions for chat in the background: it
    # calls the embedding API per entry, so it mustn't delay startup.
    backfill_task = asyncio.create_task(backfill_unindexed())
    yield
    backfill_task.cancel()
    await db.close_pool()

app=FastAPI(lifespan=lifespan)

# Rate limiting (per-request IP by default; /ask uses a tenant+user key
# instead, see _ask_rate_limit_key below, so one abusive IP behind a shared
# NAT doesn't throttle every other tenant's users).
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(asyncpg.DataError)
async def _invalid_value_handler(request: Request, exc: asyncpg.DataError):
    # A malformed id/value in the URL or body (e.g. "not-a-uuid" where the
    # column is uuid) is the client's mistake: answer 400, not a 500 crash.
    logger.info(f"Rejected invalid value on {request.method} {request.url.path}: {exc}")
    return JSONResponse(status_code=400, content={"detail": "Invalid value in the request"})


def _ask_rate_limit_key(request: Request) -> str:
    token = request.cookies.get(ACCESS_TOKEN_COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
    if token:
        payload = decode_access_token(token)
        if payload and payload.get("tenant_id") and payload.get("user_id"):
            return f"{payload['tenant_id']}:{payload['user_id']}"
    return get_remote_address(request)


@app.middleware("http")
async def log_request(request,call_next):
    start_time=time.time()
    try:
        response=await call_next(request)
        duration=round((time.time()-start_time)*1000)
        logger.info(f"{request.method} {request.url.path}->{response.status_code}({duration}ms)")
        return response
    except Exception as e:
        duration=round((time.time()-start_time)*1000)
        logger.exception(f"{request.method}{request.url.path} ->EXCEPTION:{e} ({duration}ms)")
        raise


CSP_POLICY = (
    "default-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: blob:; "
    "media-src 'self' blob:; "
    "frame-src https://www.youtube-nocookie.com; "
    "connect-src 'self'; "
    "script-src 'self'"
)

# Swagger UI (/docs) and ReDoc (/redoc) load their JS/CSS bundle from a CDN and
# run an inline bootstrap script — the strict CSP_POLICY above blocks all of
# that, leaving the page blank. This relaxed policy applies ONLY to the
# doc-rendering routes below; every other endpoint keeps CSP_POLICY untouched.
DOCS_CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline' https://fonts.googleapis.com; "
    "img-src 'self' data: blob: https://fastapi.tiangolo.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "connect-src 'self'"
)

_DOCS_PATHS = {"/docs", "/redoc", "/openapi.json"}


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        DOCS_CSP_POLICY if request.url.path in _DOCS_PATHS else CSP_POLICY
    )
    return response


_cors_allowed_origins_env = os.getenv("CORS_ALLOWED_ORIGINS")
_cors_allowed_origins = (
    [o.strip() for o in _cors_allowed_origins_env.split(",") if o.strip()]
    if _cors_allowed_origins_env
    else ["http://localhost:4200", "http://127.0.0.1:4200"]
)
_cors_allowed_origin_regex = os.getenv(
    "CORS_ALLOWED_ORIGIN_REGEX",
    r"https://([a-z0-9-]+\.)*vitacareonline\.com",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allowed_origins,
    allow_origin_regex=_cors_allowed_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ai_monitoring_router)
app.include_router(faq_categories_router)
app.include_router(tenant_analytics_router)
app.include_router(companies_router)
app.include_router(support_tickets_router)
app.include_router(unanswered_questions_router)
app.include_router(answer_feedback_router)
app.include_router(admin_overview_router)

@app.get("/health")

def health():
    return{"status":"ok"}


@app.get("/tenants")

async def list_tenants():
    async with db.pool.acquire()as conn:
        rows = await conn.fetch("SELECT id , name FROM tenants ORDER BY created_at")
        return[dict(r) for r in rows]
    
@app.get("/users")
async def list_users(
    scope: UserScope = Depends(require_admin_or_company_admin),
    search: str = "",
    company_id: str | None = None,
    page: int = 1,
    page_size: int = 50,
):
    tenant_id = scope.tenant_id
    # A company_admin only ever sees their own company's users, regardless
    # of what (if anything) they pass as ?company_id= — a tenant admin/
    # superadmin can optionally filter by any company, or omit it for every
    # user in the tenant.
    effective_company_id = scope.company_id if scope.role == "company_admin" else company_id

    offset = (page - 1) * page_size
    async with db.tenant_connection(tenant_id) as conn:
        rows = await conn.fetch(
            """
            SELECT u.id, u.username, u.email, u.role, u.phone, u.country_code,
                   u.company_id, c.name AS company_name
            FROM users u
            LEFT JOIN companies c ON c.id = u.company_id
            WHERE u.tenant_id = $1
            AND ($2 = '' OR u.username ILIKE $3)
            AND ($4::uuid IS NULL OR u.company_id = $4)
            ORDER BY u.created_at DESC
            LIMIT $5 OFFSET $6
            """,
            tenant_id, search, f"%{search}%", effective_company_id, page_size, offset,
        )
        total = await conn.fetchval(
            """
            SELECT COUNT(*) FROM users
            WHERE tenant_id = $1
            AND ($2 = '' OR username ILIKE $3)
            AND ($4::uuid IS NULL OR company_id = $4)
            """,
            tenant_id, search, f"%{search}%", effective_company_id,
        )
    return {
        "users": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": -(-total // page_size),
    }


class CreateUserRequest(BaseModel):
    email: EmailStr
    username: str
    password: str
    role: str = "member"
    company_id: str | None = None


_ADMIN_ASSIGNABLE_ROLES = {"admin", "company_admin", "member"}


@app.post("/users/create")
@limiter.limit("20/minute")
async def create_user(
    request: Request,
    body: CreateUserRequest,
    scope: UserScope = Depends(require_admin_or_company_admin),
    actor_id: str = Depends(get_current_user_id),
):
    """Authenticated user creation for admins — the counterpart to the
    public POST /register (which is unauthenticated and therefore now
    hardcodes role='member', see that endpoint's comment). This is the only
    way to create a user with an elevated role, and the only way to assign
    a user to a company."""
    tenant_id = scope.tenant_id

    if scope.role == "company_admin":
        role = "member"  # a company_admin can only ever create plain members
        company_id = scope.company_id  # ...and only within their own company
    else:
        role = body.role
        if role not in _ADMIN_ASSIGNABLE_ROLES:
            raise HTTPException(status_code=400, detail=f"role must be one of {sorted(_ADMIN_ASSIGNABLE_ROLES)}")
        company_id = body.company_id
        if role == "company_admin" and not company_id:
            raise HTTPException(status_code=400, detail="company_admin requires a company_id")

    hashed = hash_password(body.password)
    async with db.tenant_connection(tenant_id) as conn:
        if company_id:
            owner = await conn.fetchval(
                "SELECT 1 FROM companies WHERE id = $1 AND tenant_id = $2", company_id, tenant_id,
            )
            if owner is None:
                raise HTTPException(status_code=404, detail="Company not found")
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO users (tenant_id, email, password_hash, role, username, company_id)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id, email, role, username, company_id
                """,
                tenant_id, body.email.lower(), hashed, role, body.username, company_id,
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(status_code=409, detail="Email or username already exist")
    await log_detached(scope.tenant_id, actor_id, 'user.create', f'{body.email} ({body.role})')
    return dict(row)


class UpdateUserRequest(BaseModel):
    role: str | None = None
    company_id: str | None = None


@app.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    body: UpdateUserRequest,
    scope: UserScope = Depends(require_admin_or_company_admin),
    current_user_id: str = Depends(get_current_user_id),
):
    _label = await label_for(scope.tenant_id, "SELECT COALESCE(username, email) FROM users WHERE id = $1 AND tenant_id = $2", user_id, scope.tenant_id)
    tenant_id = scope.tenant_id
    async with db.tenant_connection(tenant_id) as conn:
        target = await conn.fetchrow(
            "SELECT id, role, company_id FROM users WHERE id = $1 AND tenant_id = $2",
            user_id, tenant_id,
        )
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")

        # model_fields_set (not "is not None") distinguishes a field the
        # caller never sent at all from one explicitly sent as null — the
        # earlier "is not None" check could never clear a value back to
        # NULL: PATCH {"company_id": null} and simply omitting company_id
        # both look identical as `None` on the Pydantic model, so unassigning
        # a user from their company silently fell through to "keep the old
        # value" every time, even though the request itself succeeded (200).
        fields_sent = body.model_fields_set

        if scope.role == "company_admin":
            # Only ever touches members already inside their own company —
            # never another company's users, and never promotes/demotes
            # anyone's role.
            if str(target["company_id"]) != str(scope.company_id):
                raise HTTPException(status_code=403, detail="Not a member of your company")
            if "role" in fields_sent or "company_id" in fields_sent:
                raise HTTPException(status_code=403, detail="company_admin cannot change role or company")
            return {"status": "unchanged"}

        # Deliberately excludes 'superadmin': a tenant admin must never be
        # able to promote anyone to a platform-wide role through this
        # endpoint — that only happens via POST /admin/tenants. Only
        # validated when actually being changed, so this endpoint can still
        # update company_id alone without tripping over some other row's
        # pre-existing (unrelated) role value.
        if body.role is not None and body.role not in _ADMIN_ASSIGNABLE_ROLES:
            raise HTTPException(status_code=400, detail=f"role must be one of {sorted(_ADMIN_ASSIGNABLE_ROLES)}")
        role = body.role if "role" in fields_sent else target["role"]
        company_id = body.company_id if "company_id" in fields_sent else target["company_id"]
        if role != target["role"]:
            # Guards against an admin locking the tenant out of its own
            # admin pages: never your own role, never the last admin.
            if str(target["id"]) == str(current_user_id):
                raise HTTPException(status_code=400, detail="You can't change your own role")
            if target["role"] == "admin":
                other_admins = await conn.fetchval(
                    "SELECT count(*) FROM users WHERE tenant_id = $1 AND role = 'admin' AND id <> $2",
                    tenant_id, user_id,
                )
                if not other_admins:
                    raise HTTPException(status_code=400, detail="This is the only admin; make someone else admin first")
        if role == "company_admin" and not company_id:
            raise HTTPException(status_code=400, detail="A company admin must belong to a company")
        if company_id:
            owner = await conn.fetchval(
                "SELECT 1 FROM companies WHERE id = $1 AND tenant_id = $2", company_id, tenant_id,
            )
            if owner is None:
                raise HTTPException(status_code=404, detail="Company not found")

        # The role (and a company_admin's company, which scopes what they
        # see) is carried in the login token, so changing either bumps
        # token_version: existing sessions stop working and the user signs in
        # again with the new access (a demoted admin must not keep admin
        # rights until a long-lived token expires).
        await conn.execute(
            "UPDATE users SET role = $1, company_id = $2, "
            "token_version = token_version + CASE WHEN role <> $1 "
            "  OR (role = 'company_admin' AND company_id IS DISTINCT FROM $2::uuid) THEN 1 ELSE 0 END "
            "WHERE id = $3 AND tenant_id = $4",
            role, company_id, user_id, tenant_id,
        )
    await log_detached(scope.tenant_id, current_user_id, 'user.update', _label + (f' → role {body.role}' if body.role else '') + (' → company changed' if 'company_id' in body.model_fields_set else ''))
    return {"status": "updated"}


@app.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    scope: UserScope = Depends(require_admin_or_company_admin),
    actor_id: str = Depends(get_current_user_id),
):
    _label = await label_for(scope.tenant_id, "SELECT COALESCE(username, email) FROM users WHERE id = $1 AND tenant_id = $2", user_id, scope.tenant_id)
    tenant_id = scope.tenant_id
    async with db.tenant_connection(tenant_id) as conn:
        target = await conn.fetchrow(
            "SELECT id, company_id FROM users WHERE id = $1 AND tenant_id = $2",
            user_id, tenant_id,
        )
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")
        if scope.role == "company_admin" and str(target["company_id"]) != str(scope.company_id):
            raise HTTPException(status_code=403, detail="Not a member of your company")

        result = await conn.execute(
            "DELETE FROM users WHERE id = $1 AND tenant_id = $2", user_id, tenant_id,
        )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="User not found")
    await log_detached(scope.tenant_id, actor_id, 'user.delete', _label)
    return {"status": "deleted"}


class ResetPasswordRequest(BaseModel):
    password: str


MIN_PASSWORD_LENGTH = 8


@app.post("/users/{user_id}/password")
@limiter.limit("20/minute")
async def reset_user_password(
    request: Request,
    user_id: str,
    body: ResetPasswordRequest,
    scope: UserScope = Depends(require_admin_or_company_admin),
    actor_id: str = Depends(get_current_user_id),
):
    """An admin sets a new password for a user (the app has no self-service
    reset). Same reach as editing users: a tenant admin for anyone in the
    tenant except a superadmin; a company_admin only for plain members of
    their own company. Signs the user out everywhere (token_version)."""
    password = body.password or ""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    try:
        hashed = hash_password(password)
    except ValueError:
        raise HTTPException(status_code=400, detail="Password is too long")

    tenant_id = scope.tenant_id
    async with db.tenant_connection(tenant_id) as conn:
        target = await conn.fetchrow(
            "SELECT id, role, company_id, COALESCE(username, email) AS label FROM users WHERE id = $1 AND tenant_id = $2",
            user_id, tenant_id,
        )
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")
        if target["role"] == "superadmin":
            raise HTTPException(status_code=403, detail="A superadmin's password can't be reset here")
        if scope.role == "company_admin" and (
            str(target["company_id"]) != str(scope.company_id) or target["role"] != "member"
        ):
            raise HTTPException(status_code=403, detail="You can only reset passwords of members of your company")
        await conn.execute(
            "UPDATE users SET password_hash = $1, token_version = token_version + 1 WHERE id = $2 AND tenant_id = $3",
            hashed, user_id, tenant_id,
        )
    await log_detached(tenant_id, actor_id, 'user.password_reset', target["label"])
    return {"status": "updated", "signed_out": str(user_id) == str(actor_id)}
    

class RegisterRequest(BaseModel):
    tenant_id:str
    email:EmailStr
    password:str
    username:str
    role:str ="member"
    # Explicit, not derived from the Host header (which a client can spoof
    # and a backend-to-backend call wouldn't even have set meaningfully) —
    # extracted by the caller from a referral link like
    # {company-slug}.vitacareonline.com and sent as a real request field.
    # Optional: registering without one leaves the user unassigned, same as
    # always.
    company_slug: str | None = None


# Default status for a company auto-created by the referral-link flow below
# (every *existing* company, and any created through the admin Companies UI,
# is 'active' — this only governs the brand-new-via-referral case). Nothing
# in the codebase currently gates behavior on 'pending_approval' yet — this
# is purely the on/off switch for that to be built later without a schema
# change; flipping it today has no visible effect beyond the stored value.
COMPANY_AUTO_CREATE_STATUS = os.getenv("COMPANY_AUTO_CREATE_STATUS", "active")
if COMPANY_AUTO_CREATE_STATUS not in ("active", "pending_approval"):
    raise RuntimeError(
        f"COMPANY_AUTO_CREATE_STATUS must be 'active' or 'pending_approval', got {COMPANY_AUTO_CREATE_STATUS!r}"
    )


async def _resolve_or_create_company(conn, tenant_id: str, raw_slug: str) -> str:
    """Looks up a company by slug, creating it if this is the first referral
    signup for it. Race-safe: if two requests for the same brand-new slug
    land concurrently, the loser's INSERT is a no-op (ON CONFLICT DO
    NOTHING) and it then re-SELECTs to pick up the winner's row — exactly
    one company ever gets created either way."""
    slug = normalize_company_slug(raw_slug)
    if not slug:
        raise HTTPException(status_code=400, detail="Invalid company slug")

    existing = await conn.fetchval(
        "SELECT id FROM companies WHERE tenant_id = $1 AND slug = $2", tenant_id, slug,
    )
    if existing is not None:
        return str(existing)

    display_name = slug_to_display_name(slug)
    try:
        # db.tenant_connection() (every caller of this function) already
        # holds one open transaction for its whole `async with` block — a
        # bare try/except around this INSERT would, on conflict, leave that
        # outer transaction aborted (InFailedSQLTransactionError) for
        # anything run after it, including the retry INSERT right below and
        # whatever the caller does with `conn` afterward (e.g. the INSERT
        # INTO users right after this returns). Nesting conn.transaction()
        # makes asyncpg issue a SAVEPOINT instead of BEGIN, so a failure
        # only rolls back to it, not the whole transaction.
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO companies (tenant_id, name, slug, status)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (tenant_id, slug) DO NOTHING
                RETURNING id
                """,
                tenant_id, display_name, slug, COMPANY_AUTO_CREATE_STATUS,
            )
    except asyncpg.UniqueViolationError:
        # Not a slug conflict (that's handled by ON CONFLICT above without
        # raising) — this is the rarer case of display_name colliding with
        # a *different* company's current name (e.g. that company was
        # manually renamed later to something that happens to match).
        # Disambiguate and retry once rather than failing the signup.
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO companies (tenant_id, name, slug, status)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (tenant_id, slug) DO NOTHING
                RETURNING id
                """,
                tenant_id, f"{display_name} ({slug})", slug, COMPANY_AUTO_CREATE_STATUS,
            )

    if row is not None:
        return str(row["id"])

    # ON CONFLICT fired — another request just created this slug. Its row
    # must exist now.
    existing = await conn.fetchval(
        "SELECT id FROM companies WHERE tenant_id = $1 AND slug = $2", tenant_id, slug,
    )
    if existing is not None:
        return str(existing)
    raise HTTPException(status_code=500, detail="Could not resolve company")


@app.post("/register")
@limiter.limit("5/minute")
async def register (request: Request, body:RegisterRequest):
    # SECURITY: this endpoint has no auth — anyone can call it for any
    # tenant_id they can guess (tenant IDs are visible via GET /tenants).
    # role is therefore hardcoded to 'member' here, ignoring whatever the
    # caller sent in body.role (previously inserted as-is, letting anyone
    # mint themselves an 'admin' or 'superadmin' account on any tenant with
    # zero authentication). Creating a user with a higher role now requires
    # going through an authenticated admin, via POST /users/create.
    hashed=hash_password(body.password)
    async with db.tenant_connection(body.tenant_id)as conn:
        company_id = None
        if body.company_slug:
            company_id = await _resolve_or_create_company(conn, body.tenant_id, body.company_slug)
        try:
            row=await conn.fetchrow(
                """
                INSERT INTO users (tenant_id, email, password_hash, role,username,company_id)
                VALUES ($1, $2, $3, 'member',$4,$5)
                RETURNING id, email, role,username,company_id
                """,
                body.tenant_id,body.email.lower(),hashed,body.username,company_id,
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(status_code=409,detail="Email or username already exist")
        return dict(row)


class RegisterCompanyRequest(BaseModel):
    company_name: str
    email: EmailStr
    password: str



@app.get("/admin/tenants")
async def list_all_tenants(_:None=Depends(require_superadmin)):
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, name, primary_color, action_color, logo_path, created_at FROM tenants ORDER BY created_at DESC"
        )
        return [dict(r) for r in rows]
@app.post("/admin/tenants")
async def create_tenant_admin(
    body:RegisterCompanyRequest,
    _:None=Depends(require_superadmin),
):
    hashed=hash_password(body.password)
    async with db.pool.acquire() as conn:
        try:
            async with conn.transaction():
                tenant=await conn.fetchrow(
                    "INSERT INTO tenants (name) VALUES ($1) RETURNING id",
                    body.company_name,
                )
                tenant_id=tenant["id"]
                await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(tenant_id))
                user=await conn.fetchrow(
                    """
                    INSERT INTO users (tenant_id, email, password_hash, role)
                    VALUES ($1, $2, $3, 'admin')
                    RETURNING id, role
                    """,
                    tenant_id, body.email.lower(), hashed,
                )
                await conn.execute(
                    "INSERT INTO bots (tenant_id, name) VALUES ($1, $2)",
                    tenant_id,f"{body.company_name} Assistant",

                )
        except asyncpg.UniqueViolationError:
            raise HTTPException(status_code=409,detail="Email already registered")
    return {"tenant_id":str(tenant_id),"status":"created"}   
 
class LoginRequest(BaseModel):
    email:str
    password:str

@app.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, response: Response):
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT id, tenant_id, role, password_hash, username, company_id, token_version FROM users WHERE LOWER(email) = LOWER($1)",
            body.email,
        )
        if user is None or not verify_password(body.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        tenant = await conn.fetchrow(
            "SELECT name, primary_color, action_color, logo_path FROM tenants WHERE id = $1",
            user["tenant_id"],
        )

    token = create_access_token({
        "user_id": str(user["id"]),
        "tenant_id": str(user["tenant_id"]),
        "role": user["role"],
        "company_id": str(user["company_id"]) if user["company_id"] else None,
        # Snapshot of users.token_version so POST /logout (which bumps the
        # column) can invalidate this token before its "exp".
        "tv": user["token_version"],
    })
    set_auth_cookie(response, token)
    return {
        "role": user["role"],
        "username": user["username"],
        "tenant_id": str(user["tenant_id"]),
        "company_id": str(user["company_id"]) if user["company_id"] else None,
        "tenant": {
            "name": tenant["name"],
            "primary_color": tenant["primary_color"],
            "action_color": tenant["action_color"],
            "logo_path": tenant["logo_path"],
        },
    }


class OdooSSORequest(BaseModel):
    email: EmailStr
    username: str
    client_key: str | None = None  # اختياري للتوافق مع الاستخدام الحالي بدون عميل محدد
    # Only sent by an Odoo module already updated to the hardened scheme —
    # None means "an older module is calling, use the legacy scheme below".
    odoo_user_id: int | None = None
    company_slug: str | None = None


# ~10 years — effectively non-expiring for Vita Care's Odoo-SSO users, who
# have no password login to fall back on if this token dies. Overridable via
# env without a code change; does not affect ACCESS_TOKEN_EXPIRE_MINUTES used
# by every other login path.
ODOO_SSO_TOKEN_EXPIRE_MINUTES = int(os.getenv("ODOO_SSO_TOKEN_EXPIRE_MINUTES", str(10 * 365 * 24 * 60)))

# Separate from any per-client secret in odoo_client_connections — this one
# authenticates Vita Care's OWN internal Odoo instance (no client_key) on
# the hardened (signed) path. No fallback to Vita Care's own Odoo data if
# it's unset or a client_key is missing on that path — see the hardened
# branch below.
ODOO_SSO_INTERNAL_SECRET = os.getenv("ODOO_SSO_INTERNAL_SECRET", "")

# How old a signed request's timestamp may be (either direction, to tolerate
# some clock skew) before it's rejected — bounds how long a captured
# request could be replayed if it ever leaked.
ODOO_SSO_SIGNATURE_MAX_AGE_SECONDS = 300

# How long an exchange code is redeemable for before it expires unused —
# just long enough for the browser to follow the redirect and the frontend
# to immediately call /auth/odoo-sso/exchange, nothing more.
SSO_EXCHANGE_CODE_TTL_SECONDS = 60


def _verify_odoo_sso_signature(body: OdooSSORequest, timestamp: str, signature: str, secret: str) -> None:
    """Raises HTTPException(403) on a bad/stale signature. The canonical
    string covers every field that determines WHO this request claims to be
    and WHEN it was made — client_key and odoo_user_id especially, since
    those are exactly what an attacker would need to forge to take over a
    different user's identity (the vulnerability this scheme replaces plain
    -email matching to close)."""
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        logger.warning(f"SSO rejected (bad timestamp format): client_key={body.client_key!r} timestamp={timestamp!r}")
        raise HTTPException(status_code=403, detail="Invalid SSO timestamp")
    if abs(time.time() - ts) > ODOO_SSO_SIGNATURE_MAX_AGE_SECONDS:
        logger.warning(
            f"SSO rejected (stale timestamp): client_key={body.client_key!r} "
            f"age_seconds={abs(time.time() - ts):.0f} max={ODOO_SSO_SIGNATURE_MAX_AGE_SECONDS}"
        )
        raise HTTPException(status_code=403, detail="SSO request expired")

    # Two canonical formats are accepted: the current one (includes
    # company_slug) and the one from the hardened module version that
    # predates the company-auto-detect feature (no company_slug segment at
    # all — not even an empty placeholder). An Odoo module on that earlier
    # version signs the 5-field form, which otherwise always fails
    # verification even with a perfectly correct secret.
    canonical_current = f"{body.client_key or ''}\n{body.odoo_user_id}\n{body.email.lower()}\n{body.username}\n{body.company_slug or ''}\n{timestamp}"
    canonical_pre_company_slug = f"{body.client_key or ''}\n{body.odoo_user_id}\n{body.email.lower()}\n{body.username}\n{timestamp}"
    expected_current = hmac.new(secret.encode(), canonical_current.encode(), hashlib.sha256).hexdigest()
    expected_legacy = hmac.new(secret.encode(), canonical_pre_company_slug.encode(), hashlib.sha256).hexdigest()
    if not (
        secrets.compare_digest(expected_current, signature or "")
        or secrets.compare_digest(expected_legacy, signature or "")
    ):
        # Never log the secret or the real signature — only enough to tell
        # a misconfigured client apart from a stale/garbled request.
        logger.warning(
            f"SSO rejected (signature mismatch): client_key={body.client_key!r} "
            f"odoo_user_id={body.odoo_user_id!r} email={body.email!r} "
            f"received_sig_len={len(signature or '')} expected_sig_len={len(expected_current)}"
        )
        raise HTTPException(status_code=403, detail="Invalid SSO signature")


@app.post("/auth/odoo-sso")
async def odoo_sso(
    body: OdooSSORequest,
    x_odoo_sso_secret: str | None = Header(None),
    x_odoo_sso_timestamp: str | None = Header(None),
    x_odoo_sso_signature: str | None = Header(None),
):
    """Accepts BOTH the legacy single-shared-secret scheme (older installed
    cpbot_vita_bot_link modules) and the hardened per-client-signed scheme
    (newer ones), branching on which headers/fields the caller actually
    sent — so every already-installed Odoo module keeps working regardless
    of which version it is, with no coordinated reinstall needed. Which
    branch a given Odoo instance hits depends only on its own module
    version, never on anything configured here."""
    hardened_request = body.odoo_user_id is not None and x_odoo_sso_timestamp and x_odoo_sso_signature

    if hardened_request:
        if body.client_key:
            secret = await odoo_service.get_client_sso_secret(body.client_key)
            if not secret:
                logger.warning(f"SSO rejected (unknown/unconfigured client_key): client_key={body.client_key!r}")
                raise HTTPException(status_code=403, detail="Unknown or unconfigured client_key")
        else:
            if not ODOO_SSO_INTERNAL_SECRET:
                logger.warning("SSO rejected: ODOO_SSO_INTERNAL_SECRET is not configured on this server")
                raise HTTPException(status_code=503, detail="Internal SSO secret not configured")
            secret = ODOO_SSO_INTERNAL_SECRET

        _verify_odoo_sso_signature(body, x_odoo_sso_timestamp, x_odoo_sso_signature, secret)

        tenant_id = VITA_CARE_TENANT_ID
        # Stable even if this Odoo user's login/email is later renamed —
        # unlike email, which is exactly what the legacy scheme below
        # trusts and what let one Odoo admin silently take over a different
        # user's cpbot account by renaming a login to match.
        odoo_identity = f"{body.client_key or 'internal'}:{body.odoo_user_id}"

        async with db.tenant_connection(tenant_id) as conn:
            company_id = None
            if body.company_slug:
                company_id = await _resolve_or_create_company(conn, tenant_id, body.company_slug)
            logger.info(
                f"Odoo SSO: odoo_identity={odoo_identity!r} company_slug={body.company_slug!r} company_id={company_id!r}"
            )

            user = await conn.fetchrow(
                "SELECT id, tenant_id, role, username, token_version FROM users WHERE tenant_id = $1 AND odoo_identity = $2",
                tenant_id, odoo_identity,
            )
            if user is None:
                # One-time transition for accounts provisioned by the legacy
                # scheme (matched by email back then) — claim the existing
                # row by email exactly once, then pin odoo_identity so every
                # future request matches on that instead. A row that
                # already has an odoo_identity is never touched by this
                # lookup, so this can't hijack an already-migrated account.
                # A row still without a company is claimable too (the UPDATE
                # further down then assigns this request's company) — but
                # only one last used from this same Odoo instance (same
                # odoo_client_key). A client instance (client_key set) may
                # only claim a plain member: otherwise any client's Odoo admin
                # could create a user whose login matches e.g. a Vita Care
                # admin's email and claim that account, role and all. Vita
                # Care's own internal instance (no client_key, signed with
                # ODOO_SSO_INTERNAL_SECRET) is trusted to claim any role, so
                # staff promoted to admin before migrating aren't locked out.
                user = await conn.fetchrow(
                    "SELECT id, tenant_id, role, username, token_version FROM users "
                    "WHERE tenant_id = $1 AND LOWER(email) = LOWER($2) AND odoo_identity IS NULL "
                    "AND odoo_client_key IS NOT DISTINCT FROM $4 "
                    "AND ($4::text IS NULL OR role = 'member') "
                    "AND (company_id IS NULL OR company_id IS NOT DISTINCT FROM $3)",
                    tenant_id, body.email, company_id, body.client_key,
                )
                if user is not None:
                    await conn.execute(
                        "UPDATE users SET odoo_identity = $1, odoo_client_key = $2 WHERE id = $3",
                        odoo_identity, body.client_key, user["id"],
                    )

            if user is None:
                # This is a brand-new odoo_identity. If the email already
                # belongs to a DIFFERENT account, refuse rather than
                # silently creating a second, colliding account — one real
                # email maps to exactly one cpbot account, full stop.
                email_taken = await conn.fetchval(
                    "SELECT 1 FROM users WHERE tenant_id = $1 AND LOWER(email) = LOWER($2)",
                    tenant_id, body.email,
                )
                if email_taken:
                    raise HTTPException(status_code=409, detail="This email is already associated with a different account")

                random_password = secrets.token_urlsafe(32)
                hashed = hash_password(random_password)
                username_to_use = body.username
                for attempt in range(2):
                    try:
                        # db.tenant_connection() already holds one open
                        # transaction for this whole `async with` block — a
                        # bare try/except around this INSERT would, on
                        # conflict, leave that outer transaction aborted
                        # (InFailedSQLTransactionError). Nesting
                        # conn.transaction() makes asyncpg issue a SAVEPOINT
                        # instead of BEGIN, so a failure only rolls back to
                        # it, not the whole transaction.
                        async with conn.transaction():
                            user = await conn.fetchrow(
                                """
                                INSERT INTO users (tenant_id, email, password_hash, role, username, odoo_client_key, odoo_identity, company_id)
                                VALUES ($1, $2, $3, 'member', $4, $5, $6, $7)
                                RETURNING id, tenant_id, role, username, token_version
                                """,
                                tenant_id, body.email.lower(), hashed, username_to_use, body.client_key, odoo_identity, company_id,
                            )
                        break
                    except asyncpg.UniqueViolationError as e:
                        if e.constraint_name == "users_tenant_odoo_identity_uniq":
                            user = await conn.fetchrow(
                                "SELECT id, tenant_id, role, username, token_version FROM users WHERE tenant_id = $1 AND odoo_identity = $2",
                                tenant_id, odoo_identity,
                            )
                            break
                        if attempt == 0:
                            username_to_use = f"{body.username}-{secrets.token_hex(3)}"
                            continue
                        raise HTTPException(status_code=500, detail="Could not create user") from e
            else:
                # company_id only overwritten when this request actually
                # resolved one — COALESCE leaves their existing assignment
                # alone otherwise, rather than blanking it out.
                await conn.execute(
                    "UPDATE users SET odoo_client_key = $1, email = $2, company_id = COALESCE($3, company_id) WHERE id = $4",
                    body.client_key, body.email.lower(), company_id, user["id"],
                )

        token = create_access_token(
            {
                "user_id": str(user["id"]),
                "tenant_id": str(user["tenant_id"]),
                "role": user["role"],
                "username": user["username"],
                "email": body.email.lower(),
                "tv": user["token_version"],
            },
            expire_minutes=ODOO_SSO_TOKEN_EXPIRE_MINUTES,
        )

        # The real access token never rides in a URL from here on — handed
        # back only in this server-to-server response. The Odoo controller
        # redirects the browser with a short-lived, single-use code
        # instead; the frontend exchanges it via POST
        # /auth/odoo-sso/exchange (request body, not a URL).
        code = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=SSO_EXCHANGE_CODE_TTL_SECONDS)
        async with db.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO sso_exchange_codes (code, access_token, expires_at) VALUES ($1, $2, $3)",
                code, token, expires_at,
            )
        return {"code": code}

    # --- Legacy scheme: one shared secret for every Odoo instance,
    # matching by bare email, token handed back directly. Kept alongside
    # the hardened branch above for as long as any older module version is
    # still installed anywhere.
    if not x_odoo_sso_secret or not secrets.compare_digest(x_odoo_sso_secret, os.getenv("ODOO_SSO_SECRET", "")):
        logger.warning(
            f"SSO rejected (legacy path, secret mismatch): client_key={body.client_key!r} "
            f"email={body.email!r} odoo_user_id_present={body.odoo_user_id is not None} "
            f"has_timestamp_header={bool(x_odoo_sso_timestamp)} has_signature_header={bool(x_odoo_sso_signature)}"
        )
        raise HTTPException(status_code=403, detail="Invalid SSO secret")

    tenant_id = VITA_CARE_TENANT_ID

    async with db.tenant_connection(tenant_id) as conn:
        user = await conn.fetchrow(
            "SELECT id, tenant_id, role, username, token_version FROM users WHERE LOWER(email) = LOWER($1) AND tenant_id = $2",
            body.email, tenant_id,
        )
        if user is None:
            random_password = secrets.token_urlsafe(32)
            hashed = hash_password(random_password)
            username_to_use = body.username
            try:
                async with conn.transaction():
                    user = await conn.fetchrow(
                        """
                        INSERT INTO users (tenant_id, email, password_hash, role, username, odoo_client_key)
                        VALUES ($1, $2, $3, 'member', $4, $5)
                        RETURNING id, tenant_id, role, username, token_version
                        """,
                        tenant_id, body.email.lower(), hashed, username_to_use, body.client_key,
                    )
            except asyncpg.UniqueViolationError:
                user = await conn.fetchrow(
                    "SELECT id, tenant_id, role, username, token_version FROM users WHERE LOWER(email) = LOWER($1) AND tenant_id = $2",
                    body.email, tenant_id,
                )
                if user is None:
                    fallback_username = f"{body.username}-{secrets.token_hex(3)}"
                    async with conn.transaction():
                        user = await conn.fetchrow(
                            """
                            INSERT INTO users (tenant_id, email, password_hash, role, username, odoo_client_key)
                            VALUES ($1, $2, $3, 'member', $4, $5)
                            RETURNING id, tenant_id, role, username, token_version
                            """,
                            tenant_id, body.email.lower(), hashed, fallback_username, body.client_key,
                        )
                else:
                    await conn.execute(
                        "UPDATE users SET odoo_client_key = $1 WHERE id = $2",
                        body.client_key, user["id"],
                    )
        else:
            await conn.execute(
                "UPDATE users SET odoo_client_key = $1 WHERE id = $2",
                body.client_key, user["id"],
            )

        tenant = await conn.fetchrow(
            "SELECT name, primary_color, action_color, logo_path FROM tenants WHERE id = $1",
            tenant_id,
        )

    token = create_access_token(
        {
            "user_id": str(user["id"]),
            "tenant_id": str(user["tenant_id"]),
            "role": user["role"],
            "username": user["username"],
            "email": body.email.lower(),
            "tv": user["token_version"],
        },
        expire_minutes=ODOO_SSO_TOKEN_EXPIRE_MINUTES,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user["role"],
        "username": user["username"],
        "tenant": {
            "name": tenant["name"],
            "primary_color": tenant["primary_color"],
            "action_color": tenant["action_color"],
            "logo_path": tenant["logo_path"],
        },
    }


class SSOExchangeRequest(BaseModel):
    code: str


@app.post("/auth/odoo-sso/exchange")
@limiter.limit("20/minute")
async def odoo_sso_exchange(request: Request, body: SSOExchangeRequest):
    # Single UPDATE ... RETURNING, atomic: under concurrent redemption
    # attempts for the same code, exactly one can ever flip used=false ->
    # true and get the token back — the classic race-safe single-use-token
    # pattern, same spirit as the company-slug lookup-or-create elsewhere in
    # this codebase.
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE sso_exchange_codes SET used = true "
            "WHERE code = $1 AND used = false AND expires_at > now() "
            "RETURNING access_token",
            body.code,
        )
    if row is None:
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    return {"access_token": row["access_token"], "token_type": "bearer"}


class SessionFromTokenRequest(BaseModel):
    token: str


@app.post("/auth/session")
async def session_from_token(body: SessionFromTokenRequest, response: Response):
    # /auth/odoo-sso above is called server-to-server (Odoo -> backend), so
    # its response never reaches the browser and any Set-Cookie on it would
    # be dropped. The bare token instead rides in the redirect URL to the
    # SSO landing page, which calls this endpoint from the browser itself
    # so the httpOnly cookie actually gets set on the user's browser.
    if decode_access_token(body.token) is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    set_auth_cookie(response, body.token)
    return {"status": "ok"}


@app.post("/logout")
async def logout(request: Request, response: Response):
    # Bump the caller's token_version so the token being discarded (and any
    # other copy of it) stops working immediately instead of staying valid
    # until its "exp" — the stateless-JWT equivalent of deleting a server-side
    # session. Best-effort: a missing/invalid token or an unapplied migration
    # must never stop the cookie itself from being cleared.
    token = request.cookies.get(ACCESS_TOKEN_COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
    if token:
        payload = decode_access_token(token)
        if payload and payload.get("user_id"):
            try:
                async with db.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE users SET token_version = token_version + 1 WHERE id = $1",
                        payload["user_id"],
                    )
            except asyncpg.UndefinedColumnError:
                logger.warning(
                    "users.token_version is missing; run "
                    "migrations/009_email_lower_unique_and_token_version.sql — "
                    "logout cannot invalidate tokens server-side"
                )
    clear_auth_cookie(response)
    return {"status": "ok"}


@app.get("/auth/me")
async def me(
    user_id: str = Depends(get_current_user_id),
    tenant_id: str = Depends(get_current_tenant),
    role: str = Depends(get_current_role),
):
    # Lightweight session-verify endpoint: the dependencies above already
    # raise 401 if the cookie is missing/invalid/expired, which is what the
    # frontend calls on boot to confirm the session cookie is still valid
    # server-side before rendering any authenticated route.
    async with db.tenant_connection(tenant_id) as conn:
        user = await conn.fetchrow(
            "SELECT username FROM users WHERE id = $1 AND tenant_id = $2",
            user_id, tenant_id,
        )
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"role": role, "username": user["username"], "tenant_id": str(tenant_id)}


@app.get("/tenants/me/branding")
async def tenant_branding(tenant_id: str = Depends(get_current_tenant)):
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT name, primary_color, action_color, logo_path FROM tenants WHERE id = $1",
            tenant_id,
        )
    return dict(row)

DOCS_DIR = "uploads/documents"

MAX_DOCUMENT_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB
MAX_MEDIA_UPLOAD_SIZE = 200 * 1024 * 1024  # 200MB
_UPLOAD_READ_CHUNK_SIZE = 1024 * 1024  # 1MB


async def _read_upload_with_limit(file: UploadFile, max_size: int) -> bytes:
    """Reads an UploadFile in chunks, rejecting it with 413 as soon as the
    running total exceeds max_size, instead of buffering an unbounded file
    fully into memory first (main.py previously did `await file.read()` with
    no limit at all)."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_READ_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_size:
            raise HTTPException(
                status_code=413,
                detail=f"File too large (max {max_size // (1024 * 1024)}MB)",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@app.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    category_id:str=Form(...),
    linked_media_id: str | None = Form(None),
    display_name: str | None = Form(None),
    tenant_id: str = Depends(require_admin),
    actor_id: str = Depends(get_current_user_id),
):
    allowed = (".pdf",".docx",".xlsx",".txt",".pptx",".ppt")
    if not file.filename.lower().endswith(allowed):
        raise HTTPException(
            status_code=400,
            detail="Only PDF, Word (.docx), and Excel (.xlsx) files are supported",
        )

    async with db.tenant_connection(tenant_id) as conn:
        existing = await conn.fetchval(
            "SELECT 1 FROM documents WHERE tenant_id = $1 AND category_id = $2 AND filename = $3",
            tenant_id, category_id, file.filename,
        )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="A file with this name already exists in this category",
        )

    file_bytes = await _read_upload_with_limit(file, MAX_DOCUMENT_UPLOAD_SIZE)

    doc_ext = os.path.splitext(file.filename)[1]
    if storage.is_configured():
        # Persisted off-box (Cloudinary) so a redeploy can't wipe it. Stored as
        # "cloudinary:<public_id>" in file_path (see services/storage.py).
        stored = await storage.upload_bytes(
            file_bytes,
            folder=f"documents/{tenant_id}",
            resource_type="raw",
            filename=file.filename,
            public_id=f"{uuid_lib.uuid4()}{doc_ext}",
        )
        doc_file_path = storage.cloud_ref(stored["public_id"])
    else:
        os.makedirs(DOCS_DIR, exist_ok=True)
        doc_unique_name = f"{uuid_lib.uuid4()}{doc_ext}"
        doc_file_path = os.path.join(DOCS_DIR, doc_unique_name)
        with open(doc_file_path, "wb") as f:
            f.write(file_bytes)

    if file.filename.lower().endswith((".pptx",".ppt")):
        slides=extract_slides_from_pptx(file_bytes)
        async with db.tenant_connection(tenant_id)as conn:
            doc=await conn.fetchrow(
                "INSERT INTO documents (tenant_id,filename,status,category_id,file_path,linked_media_id,display_name)"
                "VALUES ($1,$2,'processing',$3,$4,$5,$6)  RETURNING id",
                tenant_id,file.filename,category_id,doc_file_path,linked_media_id,display_name,
            )
            document_id=doc["id"]
            for s in slides:
                content=s["text"]
                embedding=await get_embedding(content)
                embedding_str = "[" + ",".join(f"{x:.10f}" for x in embedding) + "]"
                await conn.execute(
                    """
                    INSERT INTO chunks
                        (tenant_id, document_id, content, embedding, category_id,
                         slide_number, slide_title)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    tenant_id,document_id,content,embedding_str,category_id,
                    s["slide_number"],s["title"],
                )
            await conn.execute(
                "UPDATE documents SET status = 'ready' WHERE id = $1 AND tenant_id = $2",
                document_id,tenant_id,
            )

        await log_detached(tenant_id, actor_id, 'document.upload', file.filename)
        return{
            "document_id":str(document_id),
            "filename":file.filename,
            "display_name":display_name,
            "chuncks_created":len(slides),
            "status":"ready",
        }

    if file.filename.lower().endswith(".xlsx"):
        try:
            headers, data_rows = await parse_excel(file_bytes)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        rows_data = []
        for row in data_rows:
            row_data = {headers[i]: (row[i] if i < len(row) else "") for i in range(len(headers))}
            content = " | ".join(f"{header}: {value}" for header, value in row_data.items())
            rows_data.append((row_data, content))

        # Embeddings are pure Gemini API calls with no shared DB connection, so
        # they're safe to fan out concurrently. Batched to avoid hitting
        # Gemini rate limits on large spreadsheets.
        EMBEDDING_BATCH_SIZE = 12
        embeddings: list[list[float]] = []
        for batch_start in range(0, len(rows_data), EMBEDDING_BATCH_SIZE):
            batch = rows_data[batch_start:batch_start + EMBEDDING_BATCH_SIZE]
            batch_embeddings = await asyncio.gather(
                *(get_embedding(content) for _, content in batch)
            )
            embeddings.extend(batch_embeddings)

        async with db.tenant_connection(tenant_id) as conn:
            doc = await conn.fetchrow(
                "INSERT INTO documents (tenant_id,filename,status,category_id,file_path,linked_media_id,display_name,is_spreadsheet,excel_columns)"
                "VALUES ($1,$2,'processing',$3,$4,$5,$6,true,$7::jsonb)  RETURNING id",
                tenant_id,file.filename,category_id,doc_file_path,linked_media_id,display_name,json.dumps(headers),
            )
            document_id=doc["id"]
            # asyncpg connections can't be shared across concurrent coroutines,
            # so these inserts stay sequential now that the slow embedding
            # calls have already completed above.
            for (row_data, content), embedding in zip(rows_data, embeddings):
                embedding_str = "[" + ",".join(f"{x:.10f}" for x in embedding) + "]"
                chunk = await conn.fetchrow(
                    """
                    INSERT INTO chunks (tenant_id, document_id, content, embedding, category_id)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id
                    """,
                    tenant_id, document_id, content, embedding_str, category_id,
                )
                await conn.execute(
                    """
                    INSERT INTO excel_rows (tenant_id, document_id, chunk_id, row_data)
                    VALUES ($1, $2, $3, $4::jsonb)
                    """,
                    tenant_id, document_id, chunk["id"], json.dumps(row_data),
                )
            await conn.execute(
                "UPDATE documents SET status = 'ready' WHERE id = $1 AND tenant_id = $2",
                document_id,tenant_id,
            )
        await log_detached(tenant_id, actor_id, 'document.upload', file.filename)
        return{
            "document_id":str(document_id),
            "filename":file.filename,
            "display_name":display_name,
            "chunks_created":len(data_rows),
            "status":"ready",
        }

    text = extract_text(file.filename,file_bytes)

    if not text.strip():
        raise HTTPException(
            status_code=400,
            detail="Could not extract any text from this PDF",
        )

    chunks = chunck_text(text)

    async with db.tenant_connection(tenant_id) as conn:
        doc = await conn.fetchrow(
            """
            INSERT INTO documents (tenant_id, filename, status,category_id,file_path,linked_media_id,display_name)
            VALUES ($1, $2, 'processing',$3,$4,$5,$6)
            RETURNING id
            """,
            tenant_id, file.filename,category_id,doc_file_path,linked_media_id,display_name,
        )
        document_id = doc["id"]

        for chunk in chunks:
            embedding = await get_embedding(chunk)
            embedding_str = "[" + ",".join(f"{x:.10f}" for x in embedding) + "]"
            await conn.execute(
                """
                INSERT INTO chunks (tenant_id, document_id, content, embedding,category_id)
                VALUES ($1, $2, $3, $4,$5)
                """,
                tenant_id, document_id, chunk, embedding_str,category_id,
            )

        await conn.execute(
            "UPDATE documents SET status = 'ready' WHERE id = $1 AND tenant_id = $2",
            document_id, tenant_id,
        )

    await log_detached(tenant_id, actor_id, 'document.upload', file.filename)
    return {
        "document_id": str(document_id),
        "filename": file.filename,
        "display_name": display_name,
        "chunks_created": len(chunks),
        "status": "ready",
    }
@app.get("/documents")
async def list_documents(tenant_id:str=Depends(get_current_tenant)):
    async with db.tenant_connection(tenant_id) as conn:
        rows = await conn.fetch(
            # The Unanswered Questions answers and FAQ index documents are
            # managed from their own pages; listing them here would let them
            # be deleted (taking every learned answer with them) by accident.
            "SELECT id, filename, display_name, status, created_at FROM documents "
            "WHERE tenant_id = $1 AND filename <> ALL($2::text[]) ORDER BY created_at DESC",
            tenant_id, [ANSWERS_DOC_FILENAME, FAQ_INDEX_DOC_FILENAME],
        )
        return [dict(r) for r in  rows]
def _format_slide_range(slide_numbers:list[int])->str:
    nums=sorted(set(slide_numbers))
    if len(nums)==1:
        return str(nums[0])
    if nums==list(range(nums[0],nums[-1]+1)):
        return f"{nums[0]}-{nums[-1]}"
    return ",".join(str(n) for n in nums)

def _contains_arabic(text:str)->bool:
    return bool(re.search(r'[\u0600-\u06FF]',text))

# Safety net for the [[NO_INFO]] marker: the system prompt in generate_answer
# instructs the model to always lead with that exact marker when declining,
# but it occasionally declines in its own words instead (especially in
# Arabic) without the marker \u2014 which would otherwise slip through as a
# normal "ask" answer and pollute the Most Frequent Questions analytics
# instead of landing in Weak Answers. Only matched against the start of the
# answer, same as the marker itself, to avoid false-positives on a real
# answer that merely mentions uncertainty mid-sentence.
_NO_INFO_LEAD_PATTERNS = (
    "i don't have enough information",
    "i do not have enough information",
    "i don't have specific information",
    "i don't have that information",
    "i don't have information about",
    "i'm sorry, but i don't have",
    "i'm sorry, i don't have",
    "unfortunately, i don't have",
    "i don't have details about",
    "\u0644\u0627 \u0623\u0645\u0644\u0643 \u0645\u0639\u0644\u0648\u0645\u0627\u062A",
    "\u0644\u0627 \u0627\u0645\u0644\u0643 \u0645\u0639\u0644\u0648\u0645\u0627\u062A",
    "\u0644\u064A\u0633 \u0644\u062F\u064A \u0645\u0639\u0644\u0648\u0645\u0627\u062A",
    "\u0644\u064A\u0633\u062A \u0644\u062F\u064A \u0645\u0639\u0644\u0648\u0645\u0627\u062A",
    "\u0644\u0627 \u062A\u062A\u0648\u0641\u0631 \u0644\u062F\u064A \u0645\u0639\u0644\u0648\u0645\u0627\u062A",
    "\u0644\u0627 \u064A\u0648\u062C\u062F \u0644\u062F\u064A \u0645\u0639\u0644\u0648\u0645\u0627\u062A",
    "\u0644\u0644\u0623\u0633\u0641 \u0644\u0627 \u0623\u0645\u0644\u0643",
    "\u0644\u0644\u0627\u0633\u0641 \u0644\u0627 \u0627\u0645\u0644\u0643",
    "\u0644\u0644\u0623\u0633\u0641 \u0644\u064A\u0633 \u0644\u062F\u064A",
    "\u0639\u0630\u0631\u0627\u064B\u060C \u0644\u0627 \u0623\u0645\u0644\u0643",
    "\u0639\u0630\u0631\u0627 \u0644\u0627 \u0627\u0645\u0644\u0643",
    "\u0644\u0627 \u0623\u0645\u0644\u0643 \u0647\u0630\u0647 \u0627\u0644\u0645\u0639\u0644\u0648\u0645\u0629",
)

def _looks_like_no_info(answer: str) -> bool:
    lead = answer.strip().lower()[:160]
    return any(pattern in lead for pattern in _NO_INFO_LEAD_PATTERNS)

def _translate_verbatim_to_arabic(text: str, tenant_id: str | None = None) -> str:
    """
    translate_verbatim's system prompt already says "reply with ONLY the
    translation, nothing else," but for short question-shaped input (e.g.
    "How to dispose a products?") Claude Haiku sometimes answers the
    question instead of translating it, despite that instruction —
    confirmed reproducible (same bad output on retry at temperature=0) for
    real FAQ/suggested-question rows, not a one-off fluke. Wrapping the
    input in literal quotes empirically fixes it, by making it visually
    unambiguous that this is a string to transform rather than a live
    question directed at the assistant; the wrapping quotes are stripped
    back off the result since the model sometimes echoes them into its
    output.
    """
    result = translate_verbatim(f'"{text}"', "Arabic", tenant_id=tenant_id)
    return result.strip().strip('"').strip("'").strip()


def _translate_ar_safe(text: str | None, tenant_id: str | None = None) -> str | None:
    """
    Best-effort English->Arabic translation for admin-authored content that
    gets a stored, translate-once Arabic column — FAQ/error-solution text,
    and media/document display names & descriptions. Unlike
    _translate_question_pair below (suggested questions), this never raises:
    a failed translation just leaves the _ar column null so the frontend
    falls back to displaying the English original, rather than blocking the
    admin's save on an LLM hiccup.
    """
    if not text or not text.strip():
        return None
    try:
        return _translate_verbatim_to_arabic(text, tenant_id=tenant_id)
    except Exception as e:
        logger.warning(f"Arabic translation failed, leaving _ar column null: {e}")
        return None


def _translate_question_pair(question: str, answer: str, tenant_id: str | None = None) -> tuple[str, str, str, str]:
    """Given a question/answer in either language, returns (question_en, answer_en, question_ar, answer_ar)."""
    if _contains_arabic(question):
        question_ar, answer_ar = question, answer
        question_en = translate_to_english(question, tenant_id=tenant_id)
        answer_en = translate_to_english(answer, tenant_id=tenant_id) if answer else ""
    else:
        question_en, answer_en = question, answer
        question_ar = _translate_verbatim_to_arabic(question, tenant_id=tenant_id)
        answer_ar = _translate_verbatim_to_arabic(answer, tenant_id=tenant_id) if answer else ""
    return question_en, answer_en, question_ar, answer_ar


def _resolve_faq_bilingual_fields(
    question: str | None, answer: str | None,
    question_ar: str | None, answer_ar: str | None,
    tenant_id: str | None = None,
) -> tuple[str, str, str, str]:
    """FaqItemRequest's 4 fields are each independently optional — the admin
    fills whichever language(s) they want per field, and whichever side is
    left blank gets auto-translated from the side they did fill. A field
    with BOTH sides blank is rejected (400); a field with both sides filled
    is kept exactly as the admin typed it — their own wording is never
    silently overwritten by a translation."""
    question = (question or "").strip()
    question_ar = (question_ar or "").strip()
    answer = (answer or "").strip()
    answer_ar = (answer_ar or "").strip()

    if not question and not question_ar:
        raise HTTPException(status_code=400, detail="Provide the question in English or Arabic")
    if not answer and not answer_ar:
        raise HTTPException(status_code=400, detail="Provide the answer in English or Arabic")

    if not question:
        question = translate_to_english(question_ar, tenant_id=tenant_id)
    elif not question_ar:
        question_ar = _translate_verbatim_to_arabic(question, tenant_id=tenant_id)

    if not answer:
        answer = translate_to_english(answer_ar, tenant_id=tenant_id)
    elif not answer_ar:
        answer_ar = _translate_verbatim_to_arabic(answer, tenant_id=tenant_id)

    return question, answer, question_ar, answer_ar


class AskRequest(BaseModel):
    question: str
    conversation_id: str | None = None
    category_id: str | None = None


MEDIA_ATTACH_MAX_DISTANCE = 0.70

# search_chunk returns up to `limit` chunks regardless of how much weaker the
# later ones are than the best match, which lets content from an unrelated
# document (a topic that just happens to clear search_chunk's own threshold)
# leak into the answer alongside the real match. Chunks whose distance is
# more than this much worse than the best chunk's distance are treated as a
# different topic and dropped before building the answer.
RELEVANCE_MARGIN = 0.12

# Both embedding-similarity (search_media) and document-linkage
# (linked_media_id) attachment repeatedly attached the wrong video, since
# neither approach is something the admin can predict or control. Video
# attachment is instead decided by plain keyword overlap between the
# question and a media item's own description/display name — a single
# incidental shared word isn't enough to trigger it.
MIN_KEYWORD_MATCHES = 2

# Short/common words in either language that don't carry topical meaning, so
# they're ignored when comparing a question against a media description.
# Extend this list as needed — it only needs to cover words common enough to
# otherwise cause false-positive keyword matches.
MEDIA_KEYWORD_STOPWORDS = {
    # English
    "how", "what", "when", "where", "why", "who", "which",
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "i", "my", "me", "you", "your", "it", "its",
    "to", "for", "in", "on", "at", "of", "and", "or", "with", "this", "that",
    "can", "could", "should", "would", "please", "want", "need", "about",
    # Arabic
    "كيف", "شو", "ايش", "إيش", "ما", "ماذا", "هل", "متى", "اين", "أين",
    "من", "الى", "إلى", "عن", "في", "على", "بدي", "بدى", "أبي", "ابي",
    "اعمل", "أعمل", "ممكن", "لو", "انا", "أنا", "احنا", "إحنا",
    "هاد", "هاي", "هذا", "هذه", "ذلك", "تلك", "يلي", "الذي", "التي",
    "و", "او", "أو", "مع", "ال", "لا", "لأ", "نعم", "يا",
}


def _video_only_answer(media: dict, arabic: bool) -> str:
    if arabic:
        title = media.get("display_name_ar") or media.get("description_ar") or media.get("display_name") or media.get("description") or ""
        return f"ما عندي خطوات مكتوبة لهذا، لكن هذا الفيديو يشرح الطريقة: {title}".strip()
    title = media.get("display_name") or media.get("description") or media.get("display_name_ar") or ""
    return f"I don't have written steps for this, but this video shows how: {title}".strip()


def _extract_media_keywords(text: str | None) -> set[str]:
    """Lowercases, strips punctuation, and returns the meaningful (non-stopword) words in text."""
    if not text:
        return set()
    words = re.findall(r"\w+", text.lower(), re.UNICODE)
    return {w for w in words if len(w) > 1 and w not in MEDIA_KEYWORD_STOPWORDS}


@app.delete("/documents/{document_id}")
async def delete_document(
    document_id:str,
    tenant_id:str=Depends(require_admin),
    actor_id: str = Depends(get_current_user_id),

):
    _label = await label_for(tenant_id, "SELECT COALESCE(display_name, filename) FROM documents WHERE id = $1 AND tenant_id = $2", document_id, tenant_id)
    async with db.tenant_connection(tenant_id) as conn:
        row = await conn.fetchrow(
            "DELETE FROM documents WHERE id = $1 AND tenant_id = $2 RETURNING file_path",
            document_id, tenant_id,
        )
    if row is None:
        raise HTTPException (status_code=404,detail="Document not found")
    if storage.is_cloud_ref(row["file_path"]):
        await storage.delete(row["file_path"], "raw")
    await log_detached(tenant_id, actor_id, 'document.delete', _label)
    return{"status":"deleted"}

class RenameRequest(BaseModel):
    display_name: str

@app.patch("/documents/{document_id}/name")
async def rename_document(
    document_id: str,
    body: RenameRequest,
    tenant_id: str = Depends(require_admin),
    actor_id: str = Depends(get_current_user_id),
):
    display_name_ar = _translate_ar_safe(body.display_name, tenant_id=tenant_id)
    async with db.tenant_connection(tenant_id) as conn:
        result = await conn.execute(
            "UPDATE documents SET display_name = $1, display_name_ar = $2 WHERE id = $3 AND tenant_id = $4",
            body.display_name, display_name_ar, document_id, tenant_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Document not found")
    await log_detached(tenant_id, actor_id, 'document.rename', body.display_name)
    return {"status": "updated"}

@app.get("/documents/file/{document_id}")
async def get_document_file(
    request: Request,
    document_id: str,
    tenant_id: str = Depends(get_current_tenant),
):
    async with db.tenant_connection(tenant_id) as conn:
        row = await conn.fetchrow(
            "SELECT file_path, filename FROM documents WHERE id = $1 AND tenant_id = $2",
            document_id, tenant_id,
        )

    if row is None or not row["file_path"]:
        raise HTTPException(status_code=404, detail="File not available for this document")

    if storage.is_cloud_ref(row["file_path"]):
        # Ensure PDFs/office files open inline with the right MIME type rather
        # than being served as a generic octet-stream download.
        content_type = mimetypes.guess_type(row["filename"])[0] or "application/octet-stream"
        return await storage.proxy(
            row["file_path"],
            "raw",
            range_header=request.headers.get("range"),
            filename=row["filename"],
            content_type=content_type,
        )

    if not os.path.exists(row["file_path"]):
        raise HTTPException(status_code=404, detail="File missing on server")

    return FileResponse(
        row["file_path"],
        filename=row["filename"],
        content_disposition_type="inline",
    )

@app.get("/documents/{document_id}/excel")
async def get_document_excel(
    document_id: str,
    tenant_id: str = Depends(get_current_tenant),
):
    async with db.tenant_connection(tenant_id) as conn:
        doc = await conn.fetchrow(
            "SELECT excel_columns FROM documents WHERE id = $1 AND tenant_id = $2 AND is_spreadsheet = true",
            document_id, tenant_id,
        )
        if doc is None:
            raise HTTPException(status_code=404, detail="Spreadsheet document not found")

        rows = await conn.fetch(
            "SELECT id, row_data FROM excel_rows WHERE document_id = $1 AND tenant_id = $2 ORDER BY created_at",
            document_id, tenant_id,
        )

    columns = json.loads(doc["excel_columns"]) if doc["excel_columns"] else []
    return {
        "columns": columns,
        "rows": [{"id": r["id"], "row_data": json.loads(r["row_data"])} for r in rows],
    }

class ExcelRowRequest(BaseModel):
    row_data: dict

@app.post("/documents/{document_id}/excel/rows")
async def create_excel_row(
    document_id: str,
    body: ExcelRowRequest,
    tenant_id: str = Depends(require_admin),
):
    async with db.tenant_connection(tenant_id) as conn:
        doc = await conn.fetchrow(
            "SELECT category_id FROM documents WHERE id = $1 AND tenant_id = $2 AND is_spreadsheet = true",
            document_id, tenant_id,
        )
        if doc is None:
            raise HTTPException(status_code=404, detail="Spreadsheet document not found")

        content = " | ".join(f"{header}: {value}" for header, value in body.row_data.items())
        embedding = await get_embedding(content)
        embedding_str = "[" + ",".join(f"{x:.10f}" for x in embedding) + "]"

        chunk = await conn.fetchrow(
            """
            INSERT INTO chunks (tenant_id, document_id, content, embedding, category_id)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            tenant_id, document_id, content, embedding_str, doc["category_id"],
        )
        row = await conn.fetchrow(
            """
            INSERT INTO excel_rows (tenant_id, document_id, chunk_id, row_data)
            VALUES ($1, $2, $3, $4::jsonb)
            RETURNING id, row_data
            """,
            tenant_id, document_id, chunk["id"], json.dumps(body.row_data),
        )
    return {"id": row["id"], "row_data": json.loads(row["row_data"])}

@app.put("/excel-rows/{row_id}")
async def update_excel_row(
    row_id: str,
    body: ExcelRowRequest,
    tenant_id: str = Depends(require_admin),
):
    async with db.tenant_connection(tenant_id) as conn:
        existing = await conn.fetchrow(
            "SELECT chunk_id FROM excel_rows WHERE id = $1 AND tenant_id = $2",
            row_id, tenant_id,
        )
        if existing is None:
            raise HTTPException(status_code=404, detail="Row not found")

        content = " | ".join(f"{header}: {value}" for header, value in body.row_data.items())
        embedding = await get_embedding(content)
        embedding_str = "[" + ",".join(f"{x:.10f}" for x in embedding) + "]"

        await conn.execute(
            "UPDATE chunks SET content = $1, embedding = $2 WHERE id = $3 AND tenant_id = $4",
            content, embedding_str, existing["chunk_id"], tenant_id,
        )
        row = await conn.fetchrow(
            """
            UPDATE excel_rows SET row_data = $1::jsonb WHERE id = $2 AND tenant_id = $3
            RETURNING id, row_data
            """,
            json.dumps(body.row_data), row_id, tenant_id,
        )
    return {"id": row["id"], "row_data": json.loads(row["row_data"])}

@app.delete("/excel-rows/{row_id}")
async def delete_excel_row(
    row_id: str,
    tenant_id: str = Depends(require_admin),
):
    async with db.tenant_connection(tenant_id) as conn:
        existing = await conn.fetchrow(
            "SELECT chunk_id FROM excel_rows WHERE id = $1 AND tenant_id = $2",
            row_id, tenant_id,
        )
        if existing is None:
            raise HTTPException(status_code=404, detail="Row not found")

        await conn.execute(
            "DELETE FROM excel_rows WHERE id = $1 AND tenant_id = $2",
            row_id, tenant_id,
        )
        await conn.execute(
            "DELETE FROM chunks WHERE id = $1 AND tenant_id = $2",
            existing["chunk_id"], tenant_id,
        )
    return {"status": "deleted"}

@app.post("/ask")
@limiter.limit("30/minute", key_func=_ask_rate_limit_key)
async def ask(
    request: Request,
    body: AskRequest,
    tenant_id: str = Depends(get_current_tenant),
    user_id:str=Depends(get_current_user_id),
):
    async with db.tenant_connection(tenant_id) as conn:
        conversation_id = body.conversation_id
        if not conversation_id or conversation_id == "string":
            bot = await conn.fetchrow("SELECT id FROM bots WHERE tenant_id = $1 LIMIT 1", tenant_id)
            if bot is None:
                raise HTTPException(status_code=400, detail="No bot found for this tenant")
            # A newly created conversation is always linked to the caller's own
            # user_id + tenant_id (both taken from the token/session, never
            # from the request body).
            convo = await conn.fetchrow(
                "INSERT INTO conversations (tenant_id, bot_id, user_id) VALUES ($1, $2, $3) RETURNING id",
                tenant_id, bot["id"], user_id,
            )
            conversation_id = str(convo["id"])
        else:
            # SECURITY (IDOR): conversation_id comes from the client, so it
            # must be proven to belong to the authenticated user *and* tenant
            # before it is used for anything — the history lookup just below
            # filters only on conversation_id + tenant_id, so without this any
            # member could pass another user's conversation_id (e.g. an
            # admin's) and read that user's messages back AND keep writing to
            # their thread. Same user_id + tenant_id scoping as
            # GET /conversations/me; a conversation that does not exist, was
            # deleted, or belongs to someone else is a 404 (not 403) so it is
            # not enumerable.
            try:
                conversation_uuid = str(uuid_lib.UUID(str(conversation_id)))
            except (ValueError, TypeError, AttributeError):
                raise HTTPException(status_code=404, detail="Conversation not found")
            owned_conversation_id = await conn.fetchval(
                "SELECT id FROM conversations WHERE id = $1 AND tenant_id = $2 AND user_id = $3",
                conversation_uuid, tenant_id, user_id,
            )
            if owned_conversation_id is None:
                raise HTTPException(status_code=404, detail="Conversation not found")
            conversation_id = str(owned_conversation_id)

        # Fetched BEFORE inserting the current question below — this used to
        # run after, which meant the just-inserted current user message was
        # itself the most recent row and got pulled into its own "history",
        # then appended a second time in generate_answer's messages list.
        # Claude would see that duplicated/malformed turn sitting right next
        # to the previous turn's full answer and sometimes respond by
        # re-addressing the previous topic before the new one — the
        # "leftover previous answer" bug.
        history_rows = await conn.fetch(
            """
            SELECT role, content FROM messages
            WHERE conversation_id = $1 AND tenant_id = $2
            ORDER BY created_at DESC
            LIMIT 6
            """,
            conversation_id, tenant_id,
        )
        history = [{"role": r["role"], "content": r["content"]} for r in reversed(history_rows)]

        # created_at's column default is now(), which Postgres freezes at
        # transaction start — every row inserted in this same transaction
        # (the user question below and the assistant answer further down)
        # gets the IDENTICAL timestamp. ORDER BY created_at above then has no
        # way to break the tie between a turn's own user/assistant rows,
        # so their relative order was undefined (and in practice sometimes
        # inverted) once they later showed up in another request's history
        # fetch. clock_timestamp() returns the real, advancing wall-clock
        # time even mid-transaction, so the assistant row inserted further
        # down is always ordered strictly after this user row.
        await conn.execute(
            "INSERT INTO messages (tenant_id, conversation_id, role, content, created_at) VALUES ($1, $2, 'user', $3, clock_timestamp())",
            tenant_id, conversation_id, body.question,
        )

        question_embedding = await get_embedding(body.question)
        translated_question=translate_to_english(body.question, tenant_id=tenant_id)
        embeddings_to_search=[question_embedding]
        if translated_question.strip().lower() != body.question.strip().lower():
            translated_embiddings=await get_embedding(translated_question)
            embeddings_to_search.append(translated_embiddings)

        seen_content=set()
        results=[]
        for emb in embeddings_to_search:
            chuncks=await search_chunk(conn,emb,tenant_id,body.category_id,limit=5)
            for c in chuncks:
                if c["content"] not in seen_content:
                    results.append(c)
                    seen_content.add(c["content"])

        # Restrict what actually builds the answer to chunks close to the
        # best match's distance, so a strong match on the right document
        # doesn't get diluted with weaker chunks from an unrelated one that
        # merely cleared search_chunk's own (more lenient) threshold. The
        # media-attachment logic below intentionally keeps using the full,
        # unfiltered `results` — this filtering is answer-content only.
        if results:
            best_overall_distance = min(r["distance"] for r in results)
            relevant_results = [
                r for r in results if r["distance"] <= best_overall_distance + RELEVANCE_MARGIN
            ]
            if not relevant_results:
                relevant_results = results
        else:
            relevant_results = results

        media = None

        # Superseded by keyword matching below: this resolved a video via
        # whichever document contributed the most chunks to the answer, then
        # followed that document's linked_media_id. Kept here (disabled) for
        # reference — it, like the embedding-similarity search_media fallback
        # further down, kept attaching videos the admin didn't intend.
        #
        # doc_chunk_counts = Counter(r["document_id"] for r in results if r.get("document_id"))
        #
        # doc_best_distance: dict = {}
        # for r in results:
        #     doc_id = r.get("document_id")
        #     if not doc_id or "distance" not in r:
        #         continue
        #     distance = r["distance"]
        #     if doc_id not in doc_best_distance or distance < doc_best_distance[doc_id]:
        #         doc_best_distance[doc_id] = distance
        #
        # if doc_chunk_counts:
        #     dominant_doc_id = max(
        #         doc_chunk_counts,
        #         key=lambda doc_id: (doc_chunk_counts[doc_id], -doc_best_distance.get(doc_id, float("inf"))),
        #     )
        #     best_distance = doc_best_distance.get(dominant_doc_id)
        #
        #     if best_distance is not None and best_distance < MEDIA_ATTACH_MAX_DISTANCE:
        #         linked_media_id = await conn.fetchval(
        #             "SELECT linked_media_id FROM documents WHERE id = $1 AND tenant_id = $2",
        #             dominant_doc_id, tenant_id,
        #         )
        #         if linked_media_id:
        #             row = await conn.fetchrow(
        #                 "SELECT id, filename, display_name, file_path, media_type, description, url FROM media WHERE id = $1 AND tenant_id = $2",
        #                 linked_media_id, tenant_id,
        #             )
        #             if row:
        #                 media = dict(row)

        # Disabled: embedding-based media fallback was returning irrelevant videos.
        # if media is None:
        #     media = await search_media(conn, question_embedding, tenant_id, body.category_id)

        # Which video to attach is decided by the model from the admin's own
        # titles/descriptions (select_matching_video), matching by meaning so
        # Arabic word forms, dialect and English questions work. Plain keyword
        # overlap (below) missed most of those and is now only the fallback
        # for when that call fails.
        if body.category_id:
            media_rows = await conn.fetch(
                "SELECT id, filename, display_name, display_name_ar, media_type, description, description_ar, url, category_id "
                "FROM media WHERE tenant_id = $1 AND category_id = $2",
                tenant_id, body.category_id,
            )
        else:
            media_rows = await conn.fetch(
                "SELECT id, filename, display_name, display_name_ar, media_type, description, description_ar, url, category_id "
                "FROM media WHERE tenant_id = $1",
                tenant_id,
            )

        try:
            picked = select_matching_video(body.question, [dict(r) for r in media_rows], tenant_id=tenant_id)
            if picked is not None:
                media = picked
        except Exception:
            logger.exception("Video selection failed; falling back to keyword matching")
            # Match against both language versions of the question so an English
            # question can still match an Arabic-only description and vice versa.
            # translated_question (computed above for search) already gives the
            # English form when the question is Arabic. When the question is
            # already English, translate it into Arabic too — reusing
            # translated_question there would just be the question again, since
            # translate_to_english leaves English text unchanged. Skipped
            # entirely for Arabic questions so they don't pay an extra API call.
            arabic_question = (
                None if _contains_arabic(body.question) else translate_verbatim(body.question, "Arabic", tenant_id=tenant_id)
            )

            question_keywords = _extract_media_keywords(body.question) | _extract_media_keywords(translated_question)
            if arabic_question:
                question_keywords |= _extract_media_keywords(arabic_question)

            best_media_row = None
            best_score = 0
            best_ratio = -1.0

            if question_keywords:
                for row in media_rows:
                    searchable_text = " ".join(
                        part for part in (row["description"], row["display_name"]) if part
                    )
                    description_keywords = _extract_media_keywords(searchable_text)
                    if not description_keywords:
                        continue

                    score = len(question_keywords & description_keywords)
                    if score < MIN_KEYWORD_MATCHES:
                        continue

                    ratio = score / len(description_keywords)
                    if score > best_score or (score == best_score and ratio > best_ratio):
                        best_media_row = row
                        best_score = score
                        best_ratio = ratio

            if best_media_row is not None:
                media = dict(best_media_row)

        media_hint = media["description"] if media else None

        pptx_results = [r for r in relevant_results if r.get("slide_number") is not None]
        slide_source = None
        offer_support = False

        if pptx_results:
            relevant_slides = select_relevant_slides(body.question, pptx_results, tenant_id=tenant_id)
            if relevant_slides:
                relevant_slides.sort(key=lambda r: r["slide_number"])
                merged_text = "\n\n".join(r["content"] for r in relevant_slides)
                is_arabic_question = _contains_arabic(body.question)
                if is_arabic_question:
                    merged_text=translate_verbatim(merged_text,"Arabic", tenant_id=tenant_id)
                slide_numbers = [r["slide_number"] for r in relevant_slides]
                answer = merged_text
                slide_source = {
                    "slide_numbers": slide_numbers,
                    "slide_range": _format_slide_range(slide_numbers),
                }
            else:
                answer = generate_no_info_response(body.question, tenant_id=tenant_id)
                offer_support = True
        elif not relevant_results and not media:
            answer=generate_no_info_response(body.question, tenant_id=tenant_id)
            offer_support = True
        else:
            context_chuncks=[r["content"]for r in relevant_results] if relevant_results else[]
            answer=generate_answer(body.question,context_chuncks,media_hint,history,tenant_id=tenant_id)
            # Routed through generate_no_info_response (rather than keeping
            # the model's own wording) so it logs the 'no_info_response' row
            # that Weak Answers analytics reads — see tenant_analytics.py.
            if answer.startswith("[[NO_INFO]]") or _looks_like_no_info(answer):
                if media:
                    # No written steps, but the attached video covers it:
                    # point to it rather than saying "I don't know" above it.
                    answer = _video_only_answer(media, _contains_arabic(body.question))
                else:
                    answer = generate_no_info_response(body.question, tenant_id=tenant_id)
                    offer_support = True
        msg=await conn.fetchrow("INSERT INTO messages (tenant_id, conversation_id, role, content, created_at) VALUES ($1, $2, 'assistant', $3, clock_timestamp()) RETURNING id",
            tenant_id, conversation_id, answer,)
        message_id=str(msg["id"])
        if offer_support:
            # Lands in the admin's Unanswered Questions page; never raises.
            await record_unanswered_question(
                conn, tenant_id, user_id, conversation_id, message_id, body.question, body.category_id,
            )

    response= {
        "conversation_id": conversation_id,
        "message_id":message_id,
        "answer": answer,
        "sources": [r["content"][:150] for r in relevant_results],
        "slide_source": slide_source,
        "offer_support": offer_support,
        "media":None
    }
    if media:
        if media["media_type"] == "link":
            response["media"] = {
                "type": "link",
                "filename": media["description"],
                "display_name": media.get("display_name"),
                "display_name_ar": media.get("display_name_ar"),
                "description_ar": media.get("description_ar"),
                "url": media["url"],
            }
        else:
            response["media"] = {
                "type": media["media_type"],
                "filename": media["filename"],
                "display_name": media.get("display_name"),
                "display_name_ar": media.get("display_name_ar"),
                "description_ar": media.get("description_ar"),
                "url": f"/media/file/{str(media['id'])}",
            }
    return response

class RateRequest(BaseModel):
    message_id:str
    score:int
    feedback:str | None=None

@app.post("/rate")
async def rate(
    body:RateRequest,
    tenant_id:str=Depends(get_current_tenant),

):
    if body.score not in (1 , -1):
        raise HTTPException(status_code=400,detail="Score must be 1 or -1")
    # One rating per message: a user changing their mind (👍 then 👎) must
    # overwrite the existing row, not add a second one (which used to double
    # count in the satisfaction analytics). UPDATE-then-INSERT instead of
    # INSERT so this also works before migration 010's unique index exists;
    # once it does, the INSERT's UniqueViolation is caught and retried as an
    # UPDATE (covers a concurrent re-rate). Only score/feedback change —
    # created_at stays put so the analytics time series isn't reshuffled.
    async with db.tenant_connection(tenant_id) as conn:
        # A changed rating is new feedback: clear any earlier admin review so
        # a fresh 👎 on an answer once marked fine shows up for review again.
        # Savepoint + except: the review columns only exist once migration
        # 2026-11-10b is applied, and rating must never fail because of it.
        try:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE ratings SET review_status = NULL, reviewed_by = NULL, reviewed_at = NULL "
                    "WHERE tenant_id = $1 AND message_id = $2 AND score <> $3",
                    tenant_id, body.message_id, body.score,
                )
        except asyncpg.UndefinedColumnError:
            pass
        updated = await conn.execute(
            "UPDATE ratings SET score = $3, feedback = COALESCE($4, feedback) "
            "WHERE tenant_id = $1 AND message_id = $2",
            tenant_id, body.message_id, body.score, body.feedback,
        )
        if updated == "UPDATE 0":
            try:
                await conn.execute(
                    "INSERT INTO ratings (tenant_id, message_id, score, feedback) VALUES ($1, $2, $3, $4)",
                    tenant_id, body.message_id, body.score, body.feedback,
                )
            except asyncpg.UniqueViolationError:
                await conn.execute(
                    "UPDATE ratings SET score = $3, feedback = COALESCE($4, feedback) "
                    "WHERE tenant_id = $1 AND message_id = $2",
                    tenant_id, body.message_id, body.score, body.feedback,
                )
    return {"status":"ok"}

MEDIA_DIR = "uploads/media"

@app.post("/media/upload")
async def upload_media(
    file : UploadFile = File (...),
    description:str = Form(...),
    category_id:str = Form(...),
    display_name: str | None = Form(None),
    tenant_id:str =Depends(require_admin),
    actor_id: str = Depends(get_current_user_id)
):
    name = file.filename.lower()
    if name.endswith((".mp4",".mov",".webm",".vid")):
        media_type="video"
    elif name.endswith((".jpg",".jpeg",".png",".gif","webp")):
        media_type="image"
    else:
        raise HTTPException(status_code=400,detail="Only video or image you can upload")

    async with db.tenant_connection(tenant_id) as conn:
        existing = await conn.fetchval(
            "SELECT 1 FROM media WHERE tenant_id = $1 AND category_id = $2 AND filename = $3",
            tenant_id, category_id, file.filename,
        )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="A file with this name already exists in this category",
        )

    ext = os.path.splitext(file.filename)[1]
    file_bytes = await _read_upload_with_limit(file, MAX_MEDIA_UPLOAD_SIZE)

    if storage.is_configured():
        # Persisted off-box (Cloudinary) so a redeploy can't wipe it.
        stored = await storage.upload_bytes(
            file_bytes,
            folder=f"media/{tenant_id}",
            resource_type="video" if media_type == "video" else "image",
            filename=file.filename,
            public_id=f"{uuid_lib.uuid4()}{ext}",
        )
        file_path = storage.cloud_ref(stored["public_id"])
    else:
        os.makedirs(MEDIA_DIR,exist_ok=True)
        unique_name=f"{uuid_lib.uuid4()}{ext}"
        file_path = os.path.join(MEDIA_DIR,unique_name)
        with open(file_path,"wb") as f:
            f.write(file_bytes)

    bilingual_description=translate_text(description, tenant_id=tenant_id)
    embedding = await get_embedding(bilingual_description)
    embedding_str="["+",".join(str(x)for x in embedding)+"]"

    description_ar = _translate_ar_safe(description, tenant_id=tenant_id)
    display_name_ar = _translate_ar_safe(display_name, tenant_id=tenant_id)

    async with db.tenant_connection(tenant_id) as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO media (tenant_id, filename, file_path, media_type, description, embedding,category_id,display_name,description_ar,display_name_ar)
            VALUES ($1, $2, $3, $4, $5, $6,$7,$8,$9,$10)
            RETURNING id, filename, media_type, description, display_name, description_ar, display_name_ar
            """,

            tenant_id,file.filename,file_path,media_type,description,embedding_str,category_id,display_name,description_ar,display_name_ar,
        )
    await log_detached(tenant_id, actor_id, 'media.upload', file.filename)
    return dict(row)

@app.get("/media/file/{media_id}")
async def get_media_file(
    request: Request,
    media_id :str,
    tenant_id :str =Depends(get_current_tenant),
):
    async with db.tenant_connection(tenant_id) as conn: 
        row = await conn.fetchrow(
            "SELECT file_path, filename, media_type FROM media WHERE id = $1 AND tenant_id = $2",
            media_id, tenant_id,
        )

    if row is None or not row["file_path"]:
        raise HTTPException(status_code=404,detail="media not found")

    if storage.is_cloud_ref(row["file_path"]):
        resource_type = "video" if row["media_type"] == "video" else "image"
        return await storage.proxy(
            row["file_path"],
            resource_type,
            range_header=request.headers.get("range"),
            filename=row["filename"],
        )

    if not os.path.exists(row["file_path"]):
        raise HTTPException(status_code=404,detail="file missing on server")
    
    return FileResponse(row["file_path"],filename=row["filename"])

class SpeakRequest(BaseModel):
    text: str


@app.post("/speak")
async def speak(
    body: SpeakRequest,
    tenant_id: str = Depends(get_current_tenant),
):
    # Gemini TTS returns raw PCM, which synthesize_speech wraps in a WAV
    # container (see services/tts.py) — was audio/mpeg back when this was MP3
    # from OpenAI's TTS.
    try:
        audio_bytes = synthesize_speech(body.text)
    except TTSGenerationFailed as e:
        # synthesize_speech already retried 5x — this is a real, if rare,
        # exhaustion (short/question-shaped text), not a transient blip.
        # Play back a canned "sorry" instead of a bare 500 so the user still
        # gets audible feedback.
        logger.warning(f"TTS exhausted retries for tenant {tenant_id}: {e}")
        audio_bytes = get_fallback_audio()
    return Response(content=audio_bytes, media_type="audio/wav")

class CategoryRequest(BaseModel):
    name:str

@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language: str | None = Form(None),
    tenant_id: str = Depends(get_current_tenant),
):
    audio_bytes = await file.read()
    text = transcribe_audio(audio_bytes, file.filename, language_hint=language)
    return {"text": text}

@app.post("/categories")
async def create_category(
    body:CategoryRequest,
    tenant_id:str=Depends(require_admin),
    actor_id: str = Depends(get_current_user_id),

):
    async with db.tenant_connection(tenant_id) as conn :
        try:
            row = await conn.fetchrow(
                "INSERT INTO categories (tenant_id, name) VALUES ($1, $2) RETURNING id, name",
                tenant_id,body.name,

            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(status_code=409,detail="Category already exists")
        await log_detached(tenant_id, actor_id, 'category.create', body.name)
        return dict(row)
    
@app.get("/categories")
async def list_categories(
    tenant_id: str = Depends(get_current_tenant),
    role: str = Depends(get_current_role),
):
    # The admin Knowledge Base UI shows drafts; a member's chat UI must not.
    # The frontend already hides unpublished categories, but the API returned
    # them to everyone, so a member could still list (and open) drafts.
    async with db.tenant_connection(tenant_id) as conn:
        if role in ("admin", "superadmin"):
            rows = await conn.fetch(
                "SELECT id, name, is_published FROM categories WHERE tenant_id = $1 ORDER BY name",
                tenant_id,
            )
        else:
            rows = await conn.fetch(
                "SELECT id, name, is_published FROM categories WHERE tenant_id = $1 AND is_published = true ORDER BY name",
                tenant_id,
            )
        return [dict(r) for r in rows]
    
@app.delete("/categories/{category_id}")
async def delete_category(
    category_id:str,
    tenant_id:str=Depends(require_admin),
    actor_id: str = Depends(get_current_user_id),
):
    _label = await label_for(tenant_id, "SELECT name FROM categories WHERE id = $1 AND tenant_id = $2", category_id, tenant_id)
    async with db.tenant_connection(tenant_id) as conn:

        media_rows=await conn.fetch(
            "SELECT file_path, media_type FROM media WHERE category_id=$1 AND tenant_id = $2",category_id, tenant_id,
        )
        result=await conn.execute(
            "DELETE FROM categories WHERE id = $1 AND tenant_id = $2",category_id, tenant_id,
        )
    if result =="DELETE 0":
        raise HTTPException(status_code=404,detail="Category not found")
    for row in media_rows:
        path = row["file_path"]
        if not path:
            continue
        if storage.is_cloud_ref(path):
            await storage.delete(path, "video" if row["media_type"] == "video" else "image")
        elif os.path.exists(path):
            os.remove(path)

    await log_detached(tenant_id, actor_id, 'category.delete', _label)
    return {"status":"deleted"}

@app.get("/categories/{category_id}/content")
async def category_content(
    category_id: str,
    tenant_id: str = Depends(get_current_tenant),
    role: str = Depends(get_current_role),
):
    async with db.tenant_connection(tenant_id) as conn:
        if role not in ("admin", "superadmin"):
            # Members may only read published categories; a draft (or any
            # unknown id) is a 404 so drafts aren't enumerable.
            published = await conn.fetchval(
                "SELECT is_published FROM categories WHERE id = $1 AND tenant_id = $2",
                category_id, tenant_id,
            )
            if not published:
                raise HTTPException(status_code=404, detail="Category not found")
        documents = await conn.fetch(
            "SELECT id, filename, display_name, display_name_ar, status, file_path, is_spreadsheet FROM documents WHERE category_id = $1 AND tenant_id = $2 ORDER BY created_at DESC",
            category_id, tenant_id,
        )
        media = await conn.fetch(
            "SELECT id, filename, display_name, display_name_ar, media_type, description, description_ar, url, link_type, category_id FROM media WHERE category_id = $1 AND tenant_id = $2 ORDER BY created_at DESC",
            category_id, tenant_id,
        )

    doc_list = []
    for r in documents:
        d = dict(r)
        d["has_file"] = d.pop("file_path") is not None
        doc_list.append(d)

    return {
        "documents": doc_list,
        "media": [dict(r) for r in media],
    }

@app.patch("/categories/{category_id}")
async def rename_category(
    category_id:str,
    data:dict,
    tenant_id:str = Depends(require_admin),
):
    name=data.get("name","").strip()
    if not name:
        raise HTTPException(status_code=400,detail="Name is required")
    async with db.tenant_connection(tenant_id) as conn :
        await conn.execute(
            "UPDATE categories SET name = $1 WHERE id = $2 AND tenant_id = $3",
            name,category_id,tenant_id,
        )
    return {"status":"updated"}

@app.get("/categories/published")
async def list_published_categories(tenant_id: str = Depends(get_current_tenant)):
    async with db.tenant_connection(tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT id, name FROM categories WHERE is_published = true AND tenant_id = $1 ORDER BY name",
            tenant_id,
        )
        return [dict(r) for r in rows]


# Cards on the /chat welcome screen; also the most an admin can star.
MAX_FEATURED_QUESTIONS = 6


@app.get("/suggested-questions/featured")
async def list_featured_suggested_questions(tenant_id: str = Depends(get_current_tenant)):
    # Starter prompts for the /chat welcome screen, picked from two pools:
    # Knowledge Base suggested questions (published categories only) and
    # categorized FAQ items. Order: the questions a tenant admin starred
    # ("Show on home" in Knowledge Base), then the most clicked, then ones
    # with a saved answer (they reply instantly), then a shuffle that changes
    # daily so unclicked questions all get a turn at being discovered.
    async with db.tenant_connection(tenant_id) as conn:
        rows = await conn.fetch(
            """
            SELECT id, source, category_id, category_name, category_name_ar,
                   question, answer, question_ar, answer_ar
            FROM (
                SELECT sq.id, 'suggested' AS source, sq.category_id,
                       c.name AS category_name, NULL::text AS category_name_ar,
                       sq.question, sq.answer, sq.question_ar, sq.answer_ar,
                       sq.is_featured, sq.click_count
                FROM suggested_questions sq
                JOIN categories c ON c.id = sq.category_id AND c.tenant_id = sq.tenant_id
                WHERE sq.tenant_id = $1 AND c.is_published = true
                UNION ALL
                SELECT f.id, 'faq' AS source, NULL::uuid AS category_id,
                       fc.name_en AS category_name, fc.name_ar AS category_name_ar,
                       f.question, f.answer, f.question_ar, f.answer_ar,
                       false AS is_featured, f.click_count
                FROM faq_items f
                JOIN faq_categories fc ON fc.id = f.category_id AND fc.tenant_id = f.tenant_id
                WHERE f.tenant_id = $1
            ) q
            ORDER BY is_featured DESC,
                     CASE WHEN is_featured THEN 0 ELSE click_count END DESC,
                     (coalesce(answer, '') <> '') DESC,
                     md5(id::text || current_date::text)
            LIMIT $2
            """,
            tenant_id, MAX_FEATURED_QUESTIONS,
        )
        return [dict(r) for r in rows]


@app.post("/suggested-questions/{question_id}/click", status_code=204)
async def record_suggested_question_click(
    question_id: str,
    source: str = "suggested",
    tenant_id: str = Depends(get_current_tenant),
):
    # Usage signal for the welcome screen's auto-filled slots. Clicks with a
    # saved answer never reach /ask, so the chat page reports them here.
    # source=faq: the card came from the FAQ pool rather than Knowledge Base.
    async with db.tenant_connection(tenant_id) as conn:
        if source == "faq":
            await conn.execute(
                "UPDATE faq_items SET click_count = click_count + 1 WHERE id = $1 AND tenant_id = $2",
                question_id, tenant_id,
            )
            return
        await conn.execute(
            """
            UPDATE suggested_questions sq SET click_count = click_count + 1
            FROM categories c
            WHERE sq.id = $1 AND sq.tenant_id = $2
              AND c.id = sq.category_id AND c.is_published = true
            """,
            question_id, tenant_id,
        )


class FeatureQuestionRequest(BaseModel):
    is_featured: bool


@app.put("/suggested-questions/{question_id}/featured")
async def set_suggested_question_featured(
    question_id: str,
    body: FeatureQuestionRequest,
    tenant_id: str = Depends(require_admin),
):
    async with db.tenant_connection(tenant_id) as conn:
        if body.is_featured:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM suggested_questions WHERE tenant_id = $1 AND is_featured AND id <> $2",
                tenant_id, question_id,
            )
            if count >= MAX_FEATURED_QUESTIONS:
                raise HTTPException(
                    status_code=409,
                    detail=f"You can show up to {MAX_FEATURED_QUESTIONS} questions on the home screen. Remove one first.",
                )
        result = await conn.execute(
            "UPDATE suggested_questions SET is_featured = $1 WHERE id = $2 AND tenant_id = $3",
            body.is_featured, question_id, tenant_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Question not found")
    return {"status": "updated", "is_featured": body.is_featured}


@app.get("/categories/{category_id}/suggested-questions")
async def list_suggested_questions(
    category_id: str,
    tenant_id: str = Depends(get_current_tenant),
    role: str = Depends(get_current_role),
):
    # Any logged-in tenant member, not admin-only: the regular /chat page
    # (chat-page.ts -> SuggestedQuestionsService.list()) calls this to show
    # clickable prompts under a category, not just the admin management UI.
    # Mistakenly gated behind require_admin in an earlier security pass,
    # which broke suggested questions for every non-admin member — writes
    # (POST/PUT/DELETE below) correctly stay admin-only; only this read path
    # needed loosening back up. Members are still limited to published
    # categories, same as the /categories listing.
    async with db.tenant_connection(tenant_id) as conn:
        if role not in ("admin", "superadmin"):
            published = await conn.fetchval(
                "SELECT is_published FROM categories WHERE id = $1 AND tenant_id = $2",
                category_id, tenant_id,
            )
            if not published:
                raise HTTPException(status_code=404, detail="Category not found")
        rows = await conn.fetch(
            "SELECT id, question, answer, question_ar, answer_ar, is_featured FROM suggested_questions WHERE category_id = $1 AND tenant_id = $2 ORDER BY is_featured DESC, created_at",
            category_id, tenant_id,
        )
        return [dict(r) for r in rows]


@app.delete("/suggested-questions/{question_id}")
async def delete_suggested_question(
    question_id: str,
    tenant_id: str = Depends(require_admin),
):
    async with db.tenant_connection(tenant_id) as conn:
        result = await conn.execute(
            "DELETE FROM suggested_questions WHERE id = $1 AND tenant_id = $2",
            question_id, tenant_id,
        )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Question not found")
    return {"status": "deleted"}

class EditQuestionRequest(BaseModel):
    question: str
    answer:str

@app.put("/suggested-questions/{question_id}")
async def edit_suggested_question(
    question_id: str,
    body: EditQuestionRequest,
    tenant_id: str = Depends(require_admin),
):
    question_en, answer_en, question_ar, answer_ar = _translate_question_pair(body.question, body.answer, tenant_id=tenant_id)
    async with db.tenant_connection(tenant_id) as conn:
        result = await conn.execute(
            "UPDATE suggested_questions SET question = $1, answer = $2, question_ar = $3, answer_ar = $4 WHERE id = $5 AND tenant_id = $6",
            question_en, answer_en, question_ar, answer_ar, question_id, tenant_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Question not found")
    return {"status": "updated"}


@app.delete("/media/{media_id}")
async def delete_media(
    media_id: str,
    tenant_id: str = Depends(require_admin),
    actor_id: str = Depends(get_current_user_id),
):
    _label = await label_for(tenant_id, "SELECT COALESCE(display_name, filename, description) FROM media WHERE id = $1 AND tenant_id = $2", media_id, tenant_id)
    async with db.tenant_connection(tenant_id) as conn:
        row = await conn.fetchrow(
            "SELECT file_path, media_type FROM media WHERE id = $1 AND tenant_id = $2",
            media_id, tenant_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Media not found")
        await conn.execute("DELETE FROM media WHERE id = $1 AND tenant_id = $2", media_id, tenant_id)

    path = row["file_path"]
    if storage.is_cloud_ref(path):
        await storage.delete(path, "video" if row["media_type"] == "video" else "image")
    elif path and os.path.exists(path):
        os.remove(path)

    await log_detached(tenant_id, actor_id, 'media.delete', _label)
    return {"status": "deleted"}


@app.patch("/media/{media_id}/name")
async def rename_media(
    media_id: str,
    body: RenameRequest,
    tenant_id: str = Depends(require_admin),
):
    display_name_ar = _translate_ar_safe(body.display_name, tenant_id=tenant_id)
    async with db.tenant_connection(tenant_id) as conn:
        result = await conn.execute(
            "UPDATE media SET display_name = $1, display_name_ar = $2 WHERE id = $3 AND tenant_id = $4",
            body.display_name, display_name_ar, media_id, tenant_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Media not found")
    return {"status": "updated"}


@app.post("/categories/{category_id}/publish")
async def publish_category(
    category_id: str,
    tenant_id: str = Depends(require_admin),
    actor_id: str = Depends(get_current_user_id),
):
    _label = await label_for(tenant_id, "SELECT name FROM categories WHERE id = $1 AND tenant_id = $2", category_id, tenant_id)
    async with db.tenant_connection(tenant_id) as conn:
        docs = await conn.fetchval(
            "SELECT COUNT(*) FROM documents WHERE category_id = $1 AND tenant_id = $2", category_id, tenant_id,
        )
        media = await conn.fetchval(
            "SELECT COUNT(*) FROM media WHERE category_id = $1 AND tenant_id = $2", category_id, tenant_id,
        )
        questions = await conn.fetchval(
            "SELECT COUNT(*) FROM suggested_questions WHERE category_id = $1 AND tenant_id = $2", category_id, tenant_id,
        )

        if docs == 0 and media == 0 and questions == 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot publish an empty category. Add content first.",
            )

        await conn.execute(
            "UPDATE categories SET is_published = true WHERE id = $1 AND tenant_id = $2", category_id, tenant_id,
        )
    await log_detached(tenant_id, actor_id, 'category.publish', _label)
    return {"status": "published"}


@app.post("/categories/{category_id}/unpublish")
async def unpublish_category(
    category_id: str,
    tenant_id: str = Depends(require_admin),
    actor_id: str = Depends(get_current_user_id),
):
    _label = await label_for(tenant_id, "SELECT name FROM categories WHERE id = $1 AND tenant_id = $2", category_id, tenant_id)
    async with db.tenant_connection(tenant_id) as conn:
        await conn.execute(
            "UPDATE categories SET is_published = false WHERE id = $1 AND tenant_id = $2", category_id, tenant_id,
        )
    await log_detached(tenant_id, actor_id, 'category.unpublish', _label)
    return {"status": "unpublished"}

class SuggestedQuestionRequest(BaseModel):
    category_id:str 
    question:str
    answer:str = ""


class FaqItemRequest(BaseModel):
    # Each pair is independently optional now — the admin can fill either
    # language (or both) per field; whichever side is left blank gets
    # auto-translated from the other (see _resolve_faq_bilingual_fields).
    # Both sides of a given pair blank is the only rejected case.
    question: str | None = None
    answer: str | None = None
    question_ar: str | None = None
    answer_ar: str | None = None
    category_id: str | None = None


class ErrorSolutionRequest(BaseModel):
    error_text: str
    solution_text: str
    category_id: str | None = None

@app.post("/suggested-questions")
async def add_suggested_question(
    body:SuggestedQuestionRequest,
    tenant_id:str = Depends(require_admin),
):
    question_en, answer_en, question_ar, answer_ar = _translate_question_pair(body.question, body.answer, tenant_id=tenant_id)

    async with db.tenant_connection(tenant_id) as conn:
        row=await conn.fetchrow(
            """
            INSERT INTO suggested_questions(tenant_id,category_id,question,answer,question_ar,answer_ar)
            VALUES ($1,$2,$3,$4,$5,$6)
            RETURNING id,question,answer,question_ar,answer_ar
            """,
            tenant_id,body.category_id,question_en,answer_en,question_ar,answer_ar
        )
        return dict(row)
    

class AdminAskRequest(BaseModel):
    question: str


@app.post("/admin/ask")
async def admin_ask(
    body: AdminAskRequest,
    tenant_id: str = Depends(require_admin),
):
    async with db.tenant_connection(tenant_id) as conn:
        docs = await conn.fetch(
            """
            SELECT d.filename, d.status, c.name AS category_name
            FROM documents d
            LEFT JOIN categories c ON d.category_id = c.id AND c.tenant_id = $1
            WHERE d.tenant_id = $1
            ORDER BY d.created_at DESC
            """,
            tenant_id,
        )
        media = await conn.fetch(
            """
            SELECT m.filename, m.media_type, m.description, m.url, c.name AS category_name
            FROM media m
            LEFT JOIN categories c ON m.category_id = c.id AND c.tenant_id = $1
            WHERE m.tenant_id = $1
            ORDER BY m.created_at DESC
            """,
            tenant_id,
        )
        categories = await conn.fetch(
            "SELECT name, is_published FROM categories WHERE tenant_id = $1 ORDER BY name",
            tenant_id,
        )
        suggested_questions = await conn.fetch(
            """
            SELECT sq.question, sq.answer, c.name AS category_name
            FROM suggested_questions sq
            LEFT JOIN categories c ON sq.category_id = c.id AND c.tenant_id = $1
            WHERE sq.tenant_id = $1
            ORDER BY c.name NULLS LAST, sq.created_at
            """,
            tenant_id,
        )
        recent_user_questions = await conn.fetch(
            """
            SELECT content, created_at
            FROM messages
            WHERE tenant_id = $1 AND role = 'user'
            ORDER BY created_at DESC
            LIMIT 15
            """,
            tenant_id,
        )

    info = []
    info.append(f"TOTAL documents: {len(docs)}")
    info.append(f"TOTAL media files: {len(media)}")
    info.append(f"TOTAL categories: {len(categories)}")
    info.append(f"TOTAL suggested questions: {len(suggested_questions)}")

    info.append("\nDocuments list:")
    for d in docs:
        cat = d["category_name"] or "no category"
        info.append(f"- {d['filename']} (status: {d['status']}, category: {cat})")

    info.append("\nMedia list:")
    for m in media:
        cat = m["category_name"] or "no category"
        if m["media_type"] == "link":
            info.append(f"- LINK: {m['description']} -> {m['url']} (category: {cat})")
        else:
            info.append(f"- {m['filename']} (type: {m['media_type']}, category: {cat})")

    info.append("\nCategories:")
    for c in categories:
        state = "published" if c["is_published"] else "draft"
        info.append(f"- {c['name']} ({state})")

    info.append("\nSuggested questions by category:")
    if suggested_questions:
        for q in suggested_questions:
            cat = q["category_name"] or "no category"
            has_fixed_answer = "yes" if q["answer"] else "no"
            info.append(f"- [{cat}] \"{q['question']}\" (has fixed answer: {has_fixed_answer})")
    else:
        info.append("- none configured")

    info.append("\nMost recent questions asked by end users (most recent first):")
    if recent_user_questions:
        for rq in recent_user_questions:
            info.append(f"- \"{rq['content']}\" ({rq['created_at']})")
    else:
        info.append("- no user questions yet")

    admin_context = "\n".join(info)

    answer=generate_admin_answer(body.question,admin_context,tenant_id=tenant_id)
    return{"answer":answer}


class UpdateUsernameRequest(BaseModel):
    username:str

@app.put("/users/username")
async def update_username(
    body:UpdateUsernameRequest,
    tenant_id:str = Depends(get_current_tenant),
    user_id:str = Depends(get_current_user_id),

):
    async with db.tenant_connection(tenant_id)as conn:
        try:
            await conn.execute(
                "UPDATE users SET username = $1 where id = $2 AND tenant_id = $3",
                body.username,user_id, tenant_id,
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(status_code=409,detail="Username already taken")
    return{"status":"updated","username":body.username}

@app.get("/version")
def version():
    return {"version": "isolation-fix-v1"}


class UpdatePhoneRequest(BaseModel):
    phone:str | None=None
    country_code:str | None=None


@app.put("/users/phone")
async def update_phone(
    body:UpdatePhoneRequest,
    tenant_id:str = Depends(get_current_tenant),
    user_id:str = Depends(get_current_user_id),

):
    async with db.tenant_connection(tenant_id) as conn:
        await conn.execute("UPDATE users SET phone = $1, country_code = $2 WHERE id = $3 AND tenant_id = $4",
                           body.phone,body.country_code,user_id,tenant_id,)
    return{"status":"updated","phone":body.phone,"country_code":body.country_code}

@app.post("/users/import/preview")
async def import_users_preview(
    file: UploadFile = File(...),
    tenant_id: str = Depends(require_admin),
):
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only Excel files (.xlsx) are supported")

    file_bytes = await file.read()

    try:
        headers, data_rows = await parse_excel(file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        mapping = await detect_mapping(headers)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

    if mapping.get("email") is None or mapping.get("username") is None:
        raise HTTPException(
            status_code=422,
            detail="Could not identify email or username columns. Please check your Excel headers."
        )

    return {
        "headers": headers,
        "mapping": mapping,
        "preview": data_rows[:5],
        "total_rows": len(data_rows),
    }

class MediaLinkRequest(BaseModel):
    url:str
    description:str
    category_id:str
    link_type:str = "other"
    display_name: str | None = None

@app.post("/media/link")
async def add_media_link(
    body:MediaLinkRequest,
    tenant_id:str = Depends(require_admin),
    actor_id: str = Depends(get_current_user_id),
):
    bilingual_description =translate_text(body.description, tenant_id=tenant_id)
    embedding=await get_embedding(bilingual_description)
    embedding_str="["+",".join(str(x)for x in embedding)+"]"

    description_ar = _translate_ar_safe(body.description, tenant_id=tenant_id)
    display_name_ar = _translate_ar_safe(body.display_name, tenant_id=tenant_id)

    async with db.tenant_connection(tenant_id) as conn :
        row=await conn.fetchrow(
            """
            INSERT INTO media (tenant_id, filename, file_path, media_type, description, embedding, category_id, url, link_type, display_name, description_ar, display_name_ar)
            VALUES ($1, $2, $3, 'link', $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING id, description, url, link_type, display_name, description_ar, display_name_ar
            """,
            tenant_id,"external_link","",body.description,embedding_str,body.category_id,body.url,body.link_type,body.display_name,description_ar,display_name_ar,
        )
        await log_detached(tenant_id, actor_id, 'media.add_link', body.description or body.url)
        return dict(row)
    
class ImportMapping(BaseModel):
    email:int
    username:int
    role:int | None=None

class ImportConfirmRequest(BaseModel):
    mapping:ImportMapping
    rows:list[list[str]]


@app.post("/users/import/confirm")
async def import_users_confirm(
    body:ImportConfirmRequest,
    tenant_id:str = Depends(require_admin),
    actor_id: str = Depends(get_current_user_id),
):
    default_password="Welcom123!"
    hashed=hash_password(default_password)

    valid_roles={"admin","editor","member","auditor"}
    default_role="member"

    created=0
    skipped=0

    async with db.tenant_connection(tenant_id)as conn:
        for row in body.rows:
            try:
                email=row[body.mapping.email].strip().lower() if body.mapping.email<len(row)else""
                username=row[body.mapping.username].strip() if body.mapping.username<len(row)else""

                if not email or not username:
                    skipped+=1
                    continue

                role=default_role
                if body.mapping.role is not None and body.mapping.role< len(row):
                    row_role=row[body.mapping.role].strip().lower()
                    if row_role in valid_roles:
                        role=row_role

                await conn.execute(
                    """
                    INSERT INTO users (tenant_id, email, password_hash, role, username)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (tenant_id, email) DO NOTHING
                    """,
                    tenant_id,email,hashed,role,username,


                )
                created +=1
            except Exception:
                skipped +=1

        await log_detached(tenant_id, actor_id, 'user.import', f'{len(body.rows)} rows')
        return{
            "status":"done",
            "created":created,
            "skipped":skipped,
            "default_password":default_password
        }


@app.get("/admin/users/{user_id}/conversations")
async def get_user_conversations(
    user_id:str,
    tenant_id:str=Depends(require_admin),
    page: int = 1,
    page_size: int = 20,

):
    offset = (page - 1) * page_size
    async with db.tenant_connection(tenant_id) as conn:

        user=await conn.fetchrow(
            "SELECT username, email FROM users WHERE id = $1 AND tenant_id = $2",
            user_id,tenant_id,
        )
        if user is None:
            raise HTTPException(status_code=404,detail="user not found")

        conversations=await conn.fetch(
            """
            SELECT id, created_at
            FROM conversations
            WHERE user_id = $1 AND tenant_id = $2
            ORDER BY created_at DESC
            LIMIT $3 OFFSET $4
            """,
            user_id,tenant_id,page_size,offset,
        )
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM conversations WHERE user_id = $1 AND tenant_id = $2",
            user_id, tenant_id,
        )

        result=[]
        for convo in conversations:
            messages=await conn.fetch(
                """
                SELECT role, content, created_at
                FROM messages
                WHERE conversation_id = $1 AND tenant_id = $2
                ORDER BY created_at ASC
                """,
                convo["id"],tenant_id,
            )
            result.append({
                "conversation_id":str(convo["id"]),
                "started_at":convo["created_at"],
                "messages":[
                    {"role":m["role"],"content":m["content"],"created_at":m["created_at"]}
                    for m in messages
                ],
            })
        return{
            "user":{"username":user["username"],"email":user["email"]},
            "conversations":result,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": -(-total // page_size),
        }


@app.get("/conversations/me")
async def get_my_conversations(
    tenant_id: str = Depends(get_current_tenant),
    user_id: str = Depends(get_current_user_id),
    page: int = 1,
    page_size: int = 20,
):
    offset = (page - 1) * page_size
    async with db.tenant_connection(tenant_id) as conn:
        conversations = await conn.fetch(
            """
            SELECT id, created_at
            FROM conversations
            WHERE user_id = $1 AND tenant_id = $2
            ORDER BY created_at DESC
            LIMIT $3 OFFSET $4
            """,
            user_id, tenant_id, page_size, offset,
        )
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM conversations WHERE user_id = $1 AND tenant_id = $2",
            user_id, tenant_id,
        )

        result = []
        for convo in conversations:
            messages = await conn.fetch(
                """
                SELECT role, content, created_at
                FROM messages
                WHERE conversation_id = $1 AND tenant_id = $2
                ORDER BY created_at ASC
                """,
                convo["id"], tenant_id,
            )
            result.append({
                "conversation_id": str(convo["id"]),
                "started_at": convo["created_at"],
                "messages": [
                    {"role": m["role"], "content": m["content"], "created_at": m["created_at"]}
                    for m in messages
                ],
            })
        return {
            "conversations": result,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": -(-total // page_size),
        }



@app.get("/faq")
async def list_faq(tenant_id: str = Depends(get_current_tenant)):
    async with db.tenant_connection(tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT id, question, answer, question_ar, answer_ar, category_id FROM faq_items WHERE tenant_id = $1 ORDER BY created_at",
            tenant_id,
        )
        return [dict(r) for r in rows]


@app.post("/faq")
async def create_faq_item(
    body: FaqItemRequest,
    tenant_id: str = Depends(require_admin),
    actor_id: str = Depends(get_current_user_id),
):
    question, answer, question_ar, answer_ar = _resolve_faq_bilingual_fields(
        body.question, body.answer, body.question_ar, body.answer_ar, tenant_id=tenant_id,
    )
    async with db.tenant_connection(tenant_id) as conn:
        await validate_category_id(conn, tenant_id, body.category_id)
        row = await conn.fetchrow(
            """
            INSERT INTO faq_items (tenant_id, question, answer, question_ar, answer_ar, category_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, question, answer, question_ar, answer_ar, category_id
            """,
            tenant_id, question, answer, question_ar, answer_ar, body.category_id,
        )
    await index_entry("faq_items", tenant_id, row["id"])
    await log_detached(tenant_id, actor_id, 'faq.create', (body.question or body.question_ar or ''))
    return dict(row)


@app.put("/faq/{faq_id}")
async def update_faq_item(
    faq_id: str,
    body: FaqItemRequest,
    tenant_id: str = Depends(require_admin),
    actor_id: str = Depends(get_current_user_id),
):
    question, answer, question_ar, answer_ar = _resolve_faq_bilingual_fields(
        body.question, body.answer, body.question_ar, body.answer_ar, tenant_id=tenant_id,
    )
    async with db.tenant_connection(tenant_id) as conn:
        await validate_category_id(conn, tenant_id, body.category_id)
        result = await conn.execute(
            "UPDATE faq_items SET question = $1, answer = $2, question_ar = $3, answer_ar = $4, category_id = $5 WHERE id = $6 AND tenant_id = $7",
            question, answer, question_ar, answer_ar, body.category_id, faq_id, tenant_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="FAQ item not found")
    await index_entry("faq_items", tenant_id, faq_id)
    await log_detached(tenant_id, actor_id, 'faq.update', (body.question or body.question_ar or ''))
    return {"status": "updated"}


@app.delete("/faq/{faq_id}")
async def delete_faq_item(
    faq_id: str,
    tenant_id: str = Depends(require_admin),
    actor_id: str = Depends(get_current_user_id),
):
    _label = await label_for(tenant_id, "SELECT COALESCE(question, question_ar) FROM faq_items WHERE id = $1 AND tenant_id = $2", faq_id, tenant_id)
    async with db.tenant_connection(tenant_id) as conn:
        deleted = await conn.fetchrow(
            "DELETE FROM faq_items WHERE id = $1 AND tenant_id = $2 RETURNING chunk_id",
            faq_id, tenant_id,
        )
        if deleted is not None:
            await delete_chunk(conn, tenant_id, deleted["chunk_id"])
    if deleted is None:
        raise HTTPException(status_code=404, detail="FAQ item not found")
    await log_detached(tenant_id, actor_id, 'faq.delete', _label)
    return {"status": "deleted"}


@app.get("/error-solutions")
async def list_error_solutions(tenant_id: str = Depends(require_vita_care_tenant)):
    async with db.tenant_connection(tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT id, error_text, solution_text, error_text_ar, solution_text_ar, category_id FROM error_solutions WHERE tenant_id = $1 ORDER BY created_at",
            tenant_id,
        )
        return [dict(r) for r in rows]


@app.post("/error-solutions")
async def create_error_solution(
    body: ErrorSolutionRequest,
    tenant_id: str = Depends(require_vita_care_admin),
    actor_id: str = Depends(get_current_user_id),
):
    error_text_ar = _translate_ar_safe(body.error_text, tenant_id=tenant_id)
    solution_text_ar = _translate_ar_safe(body.solution_text, tenant_id=tenant_id)
    async with db.tenant_connection(tenant_id) as conn:
        await validate_category_id(conn, tenant_id, body.category_id)
        row = await conn.fetchrow(
            """
            INSERT INTO error_solutions (tenant_id, error_text, solution_text, error_text_ar, solution_text_ar, category_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, error_text, solution_text, error_text_ar, solution_text_ar, category_id
            """,
            tenant_id, body.error_text, body.solution_text, error_text_ar, solution_text_ar, body.category_id,
        )
    await index_entry("error_solutions", tenant_id, row["id"])
    await log_detached(tenant_id, actor_id, 'error_solution.create', body.error_text)
    return dict(row)


@app.put("/error-solutions/{error_solution_id}")
async def update_error_solution(
    error_solution_id: str,
    body: ErrorSolutionRequest,
    tenant_id: str = Depends(require_vita_care_admin),
    actor_id: str = Depends(get_current_user_id),
):
    error_text_ar = _translate_ar_safe(body.error_text, tenant_id=tenant_id)
    solution_text_ar = _translate_ar_safe(body.solution_text, tenant_id=tenant_id)
    async with db.tenant_connection(tenant_id) as conn:
        await validate_category_id(conn, tenant_id, body.category_id)
        result = await conn.execute(
            "UPDATE error_solutions SET error_text = $1, solution_text = $2, error_text_ar = $3, solution_text_ar = $4, category_id = $5 WHERE id = $6 AND tenant_id = $7",
            body.error_text, body.solution_text, error_text_ar, solution_text_ar, body.category_id, error_solution_id, tenant_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Error solution not found")
    await index_entry("error_solutions", tenant_id, error_solution_id)
    await log_detached(tenant_id, actor_id, 'error_solution.update', body.error_text)
    return {"status": "updated"}


@app.delete("/error-solutions/{error_solution_id}")
async def delete_error_solution(
    error_solution_id: str,
    tenant_id: str = Depends(require_vita_care_admin),
    actor_id: str = Depends(get_current_user_id),
):
    _label = await label_for(tenant_id, "SELECT error_text FROM error_solutions WHERE id = $1 AND tenant_id = $2", error_solution_id, tenant_id)
    async with db.tenant_connection(tenant_id) as conn:
        deleted = await conn.fetchrow(
            "DELETE FROM error_solutions WHERE id = $1 AND tenant_id = $2 RETURNING chunk_id",
            error_solution_id, tenant_id,
        )
        if deleted is not None:
            await delete_chunk(conn, tenant_id, deleted["chunk_id"])
    if deleted is None:
        raise HTTPException(status_code=404, detail="Error solution not found")
    await log_detached(tenant_id, actor_id, 'error_solution.delete', _label)
    return {"status": "deleted"}


@app.post("/error-solutions/import-excel")
async def import_error_solutions_excel(
    file: UploadFile = File(...),
    tenant_id: str = Depends(require_vita_care_admin),
    actor_id: str = Depends(get_current_user_id),
):
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only Excel files (.xlsx) are supported")

    file_bytes = await file.read()

    try:
        _headers, data_rows = await parse_excel(file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    created_ids = []
    skipped = 0

    async with db.tenant_connection(tenant_id) as conn:
        for row in data_rows:
            try:
                error_text = row[0].strip() if len(row) > 0 else ""
                solution_text = row[1].strip() if len(row) > 1 else ""

                if not error_text or not solution_text:
                    skipped += 1
                    continue

                created_ids.append(await conn.fetchval(
                    "INSERT INTO error_solutions (tenant_id, error_text, solution_text) VALUES ($1, $2, $3) RETURNING id",
                    tenant_id, error_text, solution_text,
                ))
            except Exception:
                skipped += 1

    for entry_id in created_ids:
        await index_entry("error_solutions", tenant_id, entry_id)
    await log_detached(tenant_id, actor_id, 'error_solution.import', file.filename)
    return {
        "status": "done",
        "created": len(created_ids),
        "skipped": skipped,
    }


@app.get("/faq/combined")
async def list_faq_combined(tenant_id: str = Depends(require_vita_care_tenant)):
    async with db.tenant_connection(tenant_id) as conn:
        faq_rows = await conn.fetch(
            "SELECT id, question, answer, question_ar, answer_ar FROM faq_items WHERE tenant_id = $1 ORDER BY created_at",
            tenant_id,
        )
        error_rows = await conn.fetch(
            "SELECT id, error_text, solution_text, error_text_ar, solution_text_ar FROM error_solutions WHERE tenant_id = $1 ORDER BY created_at",
            tenant_id,
        )

    combined = [
        {
            "id": r["id"], "question": r["question"], "answer": r["answer"],
            "question_ar": r["question_ar"], "answer_ar": r["answer_ar"], "source": "faq",
        }
        for r in faq_rows
    ]
    combined.extend(
        {
            "id": r["id"], "question": r["error_text"], "answer": r["solution_text"],
            "question_ar": r["error_text_ar"], "answer_ar": r["solution_text_ar"], "source": "error_solution",
        }
        for r in error_rows
    )
    return combined


@app.get("/videos")
async def list_videos(tenant_id: str = Depends(require_vita_care_tenant)):
    # Member-facing: the admin's uploaded YouTube links (media_type='link',
    # link_type='youtube'), restricted to published categories only — same
    # visibility rule member-facing FAQ/document browsing already uses
    # (categories.is_published), so a video filed under a still-draft
    # category doesn't leak to members before the admin is ready.
    async with db.tenant_connection(tenant_id) as conn:
        rows = await conn.fetch(
            """
            SELECT m.id, m.display_name, m.display_name_ar, m.description, m.description_ar,
                   m.url, m.category_id, c.name AS category_name
            FROM media m
            JOIN categories c ON c.id = m.category_id
            WHERE m.tenant_id = $1 AND m.media_type = 'link' AND m.link_type = 'youtube'
                  AND c.is_published = true
            ORDER BY c.name, m.created_at DESC
            """,
            tenant_id,
        )
    return [dict(r) for r in rows]


ODOO_NOT_CONFIGURED_FOR_COMPANY = "Ask Odoo isn't set up for your company yet"
ODOO_DISABLED_FOR_COMPANY = "Ask Odoo is turned off for your company"
NOT_AN_ODOO_USER = "Your email isn't registered as a user in Odoo, so Ask Odoo can't answer for you"
ODOO_USER_CHECK_FAILED = "Ask Odoo couldn't connect to your company's Odoo. Please ask your administrator to check the Odoo connection"


async def _resolve_odoo_access(tenant_id: str, user_id: str) -> tuple[str, dict | None]:
    """Decides which Odoo (if any) this user's Odoo data comes from:

      - ("company", connection): a company user whose company has Ask Odoo
        enabled (admin portal, Companies page) -> the company's own Odoo
        connection, or failing that the client connection the user signed
        in through via Odoo SSO (odoo_client_key). Never Vita Care's.
      - ("company", connection): no company but a client key with a
        connection on file (an SSO user whose company was lost).
      - ("vita_care", None): no company and no client key, i.e. Vita Care's
        own staff -> Vita Care's own Odoo (the env default).

    Anyone else is refused with 403 rather than falling back to Vita
    Care's Odoo: a company with Ask Odoo turned off or not configured, or a
    client key with no connection on file. That fallback used to hand Vita
    Care's internal sales/customer data to any company user who happened
    to lack a client key (e.g. a company sign-up, or an SSO with no
    client_key)."""
    async with db.tenant_connection(tenant_id) as conn:
        user = await conn.fetchrow(
            """
            SELECT u.email, u.company_id, u.odoo_client_key, c.ask_odoo_enabled, c.odoo_connection_id
            FROM users u
            LEFT JOIN companies c ON c.id = u.company_id AND c.tenant_id = u.tenant_id
            WHERE u.id = $1 AND u.tenant_id = $2
            """,
            user_id, tenant_id,
        )
    if user is None:
        raise HTTPException(status_code=403, detail="Ask Odoo is not available for this account")
    if user["company_id"]:
        if not user["ask_odoo_enabled"]:
            raise HTTPException(status_code=403, detail=ODOO_DISABLED_FOR_COMPANY)
        connection = None
        if user["odoo_connection_id"]:
            connection = await odoo_service.get_odoo_connection_by_id(user["odoo_connection_id"])
        if connection is None and user["odoo_client_key"]:
            connection = await odoo_service.get_client_odoo_connection(user["odoo_client_key"])
        if not connection:
            raise HTTPException(status_code=403, detail=ODOO_NOT_CONFIGURED_FOR_COMPANY)
        source = "company"
    elif user["odoo_client_key"]:
        connection = await odoo_service.get_client_odoo_connection(user["odoo_client_key"])
        if not connection:
            raise HTTPException(status_code=403, detail=ODOO_NOT_CONFIGURED_FOR_COMPANY)
        source = "company"
    else:
        source, connection = "vita_care", None
    await _require_odoo_user(user_id, user["email"], connection)
    return source, connection


# Ask Odoo only answers people who are themselves users of that Odoo (an
# active res.users whose login/email is exactly their email): anyone else
# gets nothing from it. Cached briefly because the frontend checks
# /odoo/access several times per page load; a removed Odoo user loses
# access within this many seconds.
ODOO_USER_CHECK_TTL_SECONDS = 300
_odoo_user_check_cache: dict[tuple, tuple[float, bool]] = {}


async def _require_odoo_user(user_id: str, email: str | None, connection: dict | None) -> None:
    odoo_key = (connection["url"].rstrip("/"), connection["db"]) if connection else ("vita_care",)
    cache_key = (user_id, (email or "").lower(), odoo_key)
    cached = _odoo_user_check_cache.get(cache_key)
    if cached and time.monotonic() - cached[0] < ODOO_USER_CHECK_TTL_SECONDS:
        is_user = cached[1]
    else:
        client = odoo_service.OdooClient(**connection) if connection else None
        try:
            is_user = bool(email) and await run_in_threadpool(odoo_service.is_odoo_user, email, client)
        except odoo_service.OdooError as e:
            logger.warning(f"Ask Odoo user check failed: {e}")
            raise HTTPException(status_code=503, detail=ODOO_USER_CHECK_FAILED)
        _odoo_user_check_cache[cache_key] = (time.monotonic(), is_user)
    if not is_user:
        raise HTTPException(status_code=403, detail=NOT_AN_ODOO_USER)


@app.get("/odoo/access")
async def odoo_access(
    tenant_id: str = Depends(require_vita_care_tenant),
    user_id: str = Depends(get_current_user_id),
):
    """Lets the frontend show Ask Odoo only to users /odoo/ask would serve —
    same rule, never the connection details themselves."""
    try:
        source, _ = await _resolve_odoo_access(tenant_id, user_id)
    except HTTPException as e:
        return {"allowed": False, "source": None, "reason": e.detail}
    return {"allowed": True, "source": source, "reason": None}


@app.get("/odoo/dashboard")
async def odoo_dashboard(
    tenant_id: str = Depends(require_vita_care_tenant),
    user_id: str = Depends(get_current_user_id),
):
    _, connection = await _resolve_odoo_access(tenant_id, user_id)
    client = OdooClient(**connection) if connection else None
    try:
        return{
            "sales":get_sales_summary(client=client),
            "top_products":get_top_products(client=client),
            "customers":get_customer_summary(client=client),
        }
    except OdooError as e:
        raise HTTPException(status_code=503,detail=str(e))

class OdooAskRequest(BaseModel):
    question: str
    history: list[dict] = []

@app.post("/odoo/ask")
async def odoo_ask(
    body: OdooAskRequest,
    tenant_id: str = Depends(require_vita_care_tenant),
    user_id: str = Depends(get_current_user_id),
):
    # Checked first, before any embedding/LLM work: a company user only
    # ever reaches their own company's Odoo, and only Vita Care's own staff
    # (no company, no client key) reach Vita Care's — see
    # _resolve_odoo_access. client_connection None = Vita Care's Odoo.
    _, client_connection = await _resolve_odoo_access(tenant_id, user_id)

    async with db.tenant_connection(tenant_id) as conn:
        current_user = await conn.fetchrow(
            "SELECT email, username FROM users WHERE id = $1 AND tenant_id = $2",
            user_id, tenant_id,
        )
        question_embedding = await get_embedding(body.question)
        kb_chunks = await search_chunk(conn, question_embedding, tenant_id, None, limit=3)

    current_user_email = current_user["email"] if current_user else None
    current_username = current_user["username"] if current_user else None
    kb_context = [c["content"] for c in kb_chunks] if kb_chunks else []

    result = odoo_agent_ask(
        body.question,
        history=body.history,
        current_user_email=current_user_email,
        current_username=current_username,
        kb_context=kb_context,
        client_connection=client_connection,
        tenant_id=tenant_id,
    )
    return {"answer": result["answer"], "chart": result["chart"]}


class OdooSuggestedQuestionRequest(BaseModel):
    question: str
    question_ar: str | None = None


@app.get("/odoo/suggested-questions")
async def list_odoo_suggested_questions(tenant_id: str = Depends(require_vita_care_tenant)):
    async with db.tenant_connection(tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT id, question, question_ar FROM odoo_suggested_questions WHERE tenant_id = $1 ORDER BY created_at",
            tenant_id,
        )
        return [dict(r) for r in rows]


@app.post("/odoo/suggested-questions")
async def add_odoo_suggested_question(
    body: OdooSuggestedQuestionRequest,
    tenant_id: str = Depends(require_vita_care_admin),
):
    question_en, _, auto_question_ar, _ = _translate_question_pair(body.question, "", tenant_id=tenant_id)
    question_ar = body.question_ar or auto_question_ar

    async with db.tenant_connection(tenant_id) as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO odoo_suggested_questions (tenant_id, question, question_ar)
            VALUES ($1, $2, $3)
            RETURNING id, question, question_ar
            """,
            tenant_id, question_en, question_ar,
        )
        return dict(row)


@app.delete("/odoo/suggested-questions/{question_id}")
async def delete_odoo_suggested_question(
    question_id: str,
    tenant_id: str = Depends(require_vita_care_admin),
):
    async with db.tenant_connection(tenant_id) as conn:
        result = await conn.execute(
            "DELETE FROM odoo_suggested_questions WHERE id = $1 AND tenant_id = $2",
            question_id, tenant_id,
        )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Question not found")
    return {"status": "deleted"}