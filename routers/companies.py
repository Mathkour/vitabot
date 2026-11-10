"""Companies: a layer of organizations inside a tenant, each with its own
users (see migrations/008_add_companies.sql). Built for Vita Care, whose own
customers are themselves companies — gated to that tenant via
require_vita_care_admin, though the schema itself is tenant-generic.

User management *within* a company (create/list/edit/delete users, assigning
them to a company) lives in main.py's /users endpoints, not here — this
router only owns the companies themselves (tenant admin only; a
company_admin manages their company's users but doesn't create companies).
"""
import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import db
from services.activity import label_for, log_detached
from core.auth import get_current_user_id, require_vita_care_admin
from services.company_slug import normalize_company_slug

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
            SELECT c.id, c.name, c.created_at, count(u.id) AS user_count
            FROM companies c
            LEFT JOIN users u ON u.company_id = c.id AND u.tenant_id = c.tenant_id
            WHERE c.tenant_id = $1
            GROUP BY c.id, c.name, c.created_at
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
