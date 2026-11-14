"""Companies: a layer of organizations inside a tenant, each with its own
users (see migrations/008_add_companies.sql). Built for Vita Care, whose own
customers are themselves companies — gated to that tenant via
require_vita_care_admin, though the schema itself is tenant-generic.

User management *within* a company (create/list/edit/delete users, assigning
them to a company) lives in main.py's /users endpoints, not here — this
router only owns the companies themselves (tenant admin only; a
company_admin manages their company's users but doesn't create companies).
"""
import uuid

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

import db
from services.activity import label_for, log_detached
from core.auth import get_current_user_id, require_vita_care_admin
from services.company_slug import normalize_company_slug
from services.crypto import decrypt_value, encrypt_value
from services.odoo_service import OdooError, check_odoo_login

router = APIRouter(prefix="/companies", tags=["companies"])


class CompanyRequest(BaseModel):
    name: str


@router.post("")
async def create_company(
    body: CompanyRequest,
    tenant_id: str = Depends(require_vita_care_admin),
    actor_id: str = Depends(get_current_user_id),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    # Auto-derived, same as any company created via the referral-link flow
    # (see /register's company_slug handling) — slug is immutable once set,
    # so a later rename (PATCH below) never touches it.
    slug = normalize_company_slug(name)
    if not slug:
        raise HTTPException(status_code=400, detail="Name must contain at least one letter or number")
    async with db.tenant_connection(tenant_id) as conn:
        try:
            row = await conn.fetchrow(
                "INSERT INTO companies (tenant_id, name, slug) VALUES ($1, $2, $3) RETURNING id, name, created_at",
                tenant_id, name, slug,
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(status_code=409, detail="A company with this name already exists")
    await log_detached(tenant_id, actor_id, 'company.create', name)
    return dict(row)


@router.get("")
async def list_companies(tenant_id: str = Depends(require_vita_care_admin)):
    async with db.tenant_connection(tenant_id) as conn:
        rows = await conn.fetch(
            """
            SELECT c.id, c.name, c.created_at, count(u.id) AS user_count,
                   c.ask_odoo_enabled, (c.odoo_connection_id IS NOT NULL) AS odoo_configured
            FROM companies c
            LEFT JOIN users u ON u.company_id = c.id AND u.tenant_id = c.tenant_id
            WHERE c.tenant_id = $1
            GROUP BY c.id, c.name, c.created_at, c.ask_odoo_enabled, c.odoo_connection_id
            ORDER BY c.name
            """,
            tenant_id,
        )
    return [dict(r) for r in rows]


@router.patch("/{company_id}")
async def rename_company(
    company_id: str,
    body: CompanyRequest,
    tenant_id: str = Depends(require_vita_care_admin),
    actor_id: str = Depends(get_current_user_id),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    async with db.tenant_connection(tenant_id) as conn:
        try:
            result = await conn.execute(
                "UPDATE companies SET name = $1 WHERE id = $2 AND tenant_id = $3",
                name, company_id, tenant_id,
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(status_code=409, detail="A company with this name already exists")
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Company not found")
    await log_detached(tenant_id, actor_id, 'company.rename', name)
    return {"status": "updated"}


@router.delete("/{company_id}")
async def delete_company(
    company_id: str,
    tenant_id: str = Depends(require_vita_care_admin),
    actor_id: str = Depends(get_current_user_id),
):
    # Users in this company are not deleted — company_id just falls back to
    # NULL (ON DELETE SET NULL, see the migration) so they become
    # "unassigned" rather than disappearing.
    _label = await label_for(tenant_id, "SELECT name FROM companies WHERE id = $1 AND tenant_id = $2", company_id, tenant_id)
    async with db.tenant_connection(tenant_id) as conn:
        result = await conn.execute(
            "DELETE FROM companies WHERE id = $1 AND tenant_id = $2",
            company_id, tenant_id,
        )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Company not found")
    await log_detached(tenant_id, actor_id, 'company.delete', _label)
    return {"status": "deleted"}


# ──────────── Ask Odoo per company ────────────
#
# Each company can have its own Odoo connection (a row of
# odoo_client_connections, password encrypted the same way the SSO setup
# stores it) and an on/off switch. main._resolve_odoo_access enforces both.
# The password is write-only: it's never sent back to the browser.

class CompanyOdooRequest(BaseModel):
    enabled: bool = False
    url: str = ""
    db: str = ""
    username: str = ""
    # Empty = keep the stored password (editing other fields shouldn't
    # require re-typing it).
    password: str | None = None


def _clean_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if url and not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="The Odoo URL must start with http:// or https://")
    return url


async def _odoo_settings(conn, tenant_id: str, company_id: str) -> dict:
    row = await conn.fetchrow(
        """
        SELECT c.ask_odoo_enabled, occ.id AS connection_id, occ.odoo_url, occ.odoo_db,
               occ.odoo_username, occ.client_key
        FROM companies c
        LEFT JOIN odoo_client_connections occ ON occ.id = c.odoo_connection_id AND occ.tenant_id = c.tenant_id
        WHERE c.id = $1 AND c.tenant_id = $2
        """,
        company_id, tenant_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Company not found")
    configured = row["connection_id"] is not None
    return {
        "enabled": row["ask_odoo_enabled"],
        "configured": configured,
        "url": row["odoo_url"] or "",
        "db": row["odoo_db"] or "",
        "username": row["odoo_username"] or "",
        "has_password": configured,
        "client_key": row["client_key"],
    }


async def _unique_client_key(conn, slug: str) -> str:
    base = f"company-{slug}"[:60]
    key = base
    while await conn.fetchval("SELECT 1 FROM odoo_client_connections WHERE client_key = $1", key):
        key = f"{base}-{uuid.uuid4().hex[:6]}"
    return key


@router.get("/{company_id}/odoo")
async def get_company_odoo(company_id: str, tenant_id: str = Depends(require_vita_care_admin)):
    async with db.tenant_connection(tenant_id) as conn:
        return await _odoo_settings(conn, tenant_id, company_id)


@router.put("/{company_id}/odoo")
async def save_company_odoo(
    company_id: str,
    body: CompanyOdooRequest,
    tenant_id: str = Depends(require_vita_care_admin),
    actor_id: str = Depends(get_current_user_id),
):
    url, odoo_db, username = _clean_url(body.url), body.db.strip(), body.username.strip()
    password = body.password or None
    has_fields = bool(url or odoo_db or username or password)
    if has_fields and not (url and odoo_db and username):
        raise HTTPException(status_code=400, detail="Odoo URL, database and username are all required")

    async with db.tenant_connection(tenant_id) as conn:
        company = await conn.fetchrow(
            "SELECT id, name, slug, odoo_connection_id FROM companies WHERE id = $1 AND tenant_id = $2 FOR UPDATE",
            company_id, tenant_id,
        )
        if company is None:
            raise HTTPException(status_code=404, detail="Company not found")
        connection_id = company["odoo_connection_id"]

        if has_fields:
            encrypted = encrypt_value(password) if password else None
            if connection_id is not None:
                # If some users also sign in through this connection via
                # Odoo SSO, they get the new details too: it's the same Odoo.
                await conn.execute(
                    """
                    UPDATE odoo_client_connections
                    SET odoo_url = $1, odoo_db = $2, odoo_username = $3,
                        odoo_password_encrypted = COALESCE($4, odoo_password_encrypted)
                    WHERE id = $5 AND tenant_id = $6
                    """,
                    url, odoo_db, username, encrypted, connection_id, tenant_id,
                )
            else:
                if not encrypted:
                    raise HTTPException(status_code=400, detail="The Odoo password is required")
                connection_id = await conn.fetchval(
                    """
                    INSERT INTO odoo_client_connections
                        (tenant_id, client_name, client_key, odoo_url, odoo_db, odoo_username, odoo_password_encrypted)
                    VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id
                    """,
                    tenant_id, company["name"], await _unique_client_key(conn, company["slug"]),
                    url, odoo_db, username, encrypted,
                )

        if body.enabled and connection_id is None:
            raise HTTPException(status_code=400, detail="Set up the Odoo connection before enabling Ask Odoo")

        await conn.execute(
            "UPDATE companies SET ask_odoo_enabled = $1, odoo_connection_id = $2 WHERE id = $3 AND tenant_id = $4",
            body.enabled, connection_id, company_id, tenant_id,
        )
        result = await _odoo_settings(conn, tenant_id, company_id)
    await log_detached(tenant_id, actor_id, 'company.odoo_update',
                       f"{company['name']} ({'on' if body.enabled else 'off'})")
    return result


@router.post("/{company_id}/odoo/test")
async def test_company_odoo(
    company_id: str,
    body: CompanyOdooRequest,
    tenant_id: str = Depends(require_vita_care_admin),
):
    """Tries logging in with the details in the form; blank fields (notably
    the password) fall back to what's saved. Nothing is saved."""
    async with db.tenant_connection(tenant_id) as conn:
        stored = await conn.fetchrow(
            """
            SELECT occ.odoo_url, occ.odoo_db, occ.odoo_username, occ.odoo_password_encrypted
            FROM companies c
            LEFT JOIN odoo_client_connections occ ON occ.id = c.odoo_connection_id AND occ.tenant_id = c.tenant_id
            WHERE c.id = $1 AND c.tenant_id = $2
            """,
            company_id, tenant_id,
        )
    if stored is None:
        raise HTTPException(status_code=404, detail="Company not found")
    url = _clean_url(body.url) or (stored["odoo_url"] or "")
    odoo_db = body.db.strip() or (stored["odoo_db"] or "")
    username = body.username.strip() or (stored["odoo_username"] or "")
    password = body.password or (
        decrypt_value(stored["odoo_password_encrypted"]) if stored["odoo_password_encrypted"] else ""
    )
    if not (url and odoo_db and username and password):
        raise HTTPException(status_code=400, detail="Fill in the Odoo URL, database, username and password first")
    try:
        await run_in_threadpool(check_odoo_login, url, odoo_db, username, password)
    except OdooError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "error": None}
