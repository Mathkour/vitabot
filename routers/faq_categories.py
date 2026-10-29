"""FAQ categories: admin CRUD, an admin "uncategorized" filter, and the
member-facing category-grouped FAQ listing.

Existing FAQ CRUD (POST/PUT/DELETE /faq, GET /faq) stays in main.py — only
the category_id field was added there (see migrations/006_add_faq_categories.sql
and _validate_category_id below, imported from there). This router only
owns the new, category-specific endpoints.
"""
import asyncpg
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException

import db
from core.auth import get_current_tenant, require_vita_care_tenant, VITA_CARE_TENANT_ID

router = APIRouter(tags=["faq-categories"])


class FaqCategoryRequest(BaseModel):
    name_ar: str
    name_en: str
    display_order: int | None = None


@router.get("/admin/faq-categories")
async def list_faq_categories(tenant_id: str = Depends(get_current_tenant)):
    async with db.tenant_connection(tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT id, name_ar, name_en, display_order, created_at FROM faq_categories "
            "WHERE tenant_id = $1 ORDER BY display_order, created_at",
            tenant_id,
        )
    return [dict(r) for r in rows]


@router.post("/admin/faq-categories")
async def create_faq_category(
    body: FaqCategoryRequest,
    tenant_id: str = Depends(get_current_tenant),
):
    async with db.tenant_connection(tenant_id) as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO faq_categories (tenant_id, name_ar, name_en, display_order)
            VALUES (
                $1, $2, $3,
                COALESCE($4, (SELECT COALESCE(MAX(display_order), -1) + 1 FROM faq_categories WHERE tenant_id = $1))
            )
            RETURNING id, name_ar, name_en, display_order, created_at
            """,
            tenant_id, body.name_ar, body.name_en, body.display_order,
        )
    return dict(row)


@router.put("/admin/faq-categories/{category_id}")
async def update_faq_category(
    category_id: str,
    body: FaqCategoryRequest,
    tenant_id: str = Depends(get_current_tenant),
):
    async with db.tenant_connection(tenant_id) as conn:
        row = await conn.fetchrow(
            """
            UPDATE faq_categories
            SET name_ar = $1, name_en = $2, display_order = COALESCE($3, display_order)
            WHERE id = $4 AND tenant_id = $5
            RETURNING id, name_ar, name_en, display_order, created_at
            """,
            body.name_ar, body.name_en, body.display_order, category_id, tenant_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="FAQ category not found")
    return dict(row)


@router.delete("/admin/faq-categories/{category_id}")
async def delete_faq_category(
    category_id: str,
    tenant_id: str = Depends(get_current_tenant),
):
    # Any faq_items pointing at this category fall back to uncategorized
    # automatically via its ON DELETE SET NULL FK (migrations/006) — no
    # explicit UPDATE needed here.
    async with db.tenant_connection(tenant_id) as conn:
        result = await conn.execute(
            "DELETE FROM faq_categories WHERE id = $1 AND tenant_id = $2",
            category_id, tenant_id,
        )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="FAQ category not found")
    return {"status": "deleted"}


@router.get("/admin/faqs")
async def list_faqs_admin(uncategorized: bool = False, tenant_id: str = Depends(get_current_tenant)):
    """Admin's FAQ list, same row shape as GET /faq plus category_id.
    ?uncategorized=true restricts to FAQs with no category assigned yet, so
    the admin can find and triage them."""
    async with db.tenant_connection(tenant_id) as conn:
        if uncategorized:
            rows = await conn.fetch(
                "SELECT id, question, answer, question_ar, answer_ar, category_id FROM faq_items "
                "WHERE tenant_id = $1 AND category_id IS NULL ORDER BY created_at",
                tenant_id,
            )
        else:
            rows = await conn.fetch(
                "SELECT id, question, answer, question_ar, answer_ar, category_id FROM faq_items "
                "WHERE tenant_id = $1 ORDER BY created_at",
                tenant_id,
            )
    return [dict(r) for r in rows]


@router.get("/admin/error-solutions")
async def list_error_solutions_admin(
    uncategorized: bool = False, tenant_id: str = Depends(require_vita_care_tenant)
):
    """Error Solutions equivalent of GET /admin/faqs — kept as its own
    endpoint (not merged into /admin/faqs) rather than mixing two resource
    types with different ids/edit-delete endpoints into one admin list."""
    async with db.tenant_connection(tenant_id) as conn:
        if uncategorized:
            rows = await conn.fetch(
                "SELECT id, error_text, solution_text, error_text_ar, solution_text_ar, category_id "
                "FROM error_solutions WHERE tenant_id = $1 AND category_id IS NULL ORDER BY created_at",
                tenant_id,
            )
        else:
            rows = await conn.fetch(
                "SELECT id, error_text, solution_text, error_text_ar, solution_text_ar, category_id "
                "FROM error_solutions WHERE tenant_id = $1 ORDER BY created_at",
                tenant_id,
            )
    return [dict(r) for r in rows]


def _is_vita_care(tenant_id: str) -> bool:
    return str(tenant_id) == str(VITA_CARE_TENANT_ID)


async def _error_solution_count(conn, tenant_id: str, category_id) -> int:
    """0 if not Vita Care, or if migrations/007 hasn't added category_id to
    error_solutions yet on this environment — same degrade-gracefully
    reasoning as the try/except blocks elsewhere in this file."""
    if not _is_vita_care(tenant_id):
        return 0
    try:
        return await conn.fetchval(
            "SELECT count(*) FROM error_solutions WHERE category_id = $1 AND tenant_id = $2",
            category_id, tenant_id,
        )
    except asyncpg.UndefinedColumnError:
        return 0


@router.get("/faq/grouped")
async def list_faq_grouped(
    category_id: str | None = None,
    page: int = 1,
    page_size: int = 10,
    tenant_id: str = Depends(get_current_tenant),
):
    """Member-facing FAQ listing, in two modes:

    - No category_id (default): lightweight category *summary* — id, bilingual
      name, display_order, and `total` item count — so the accordion can show
      every category (with its count) up front without fetching any FAQ text.
      A category with total=0 is never returned.
    - category_id given: that one category's FAQs (plus, for Vita Care,
      categorized Error Solutions merged in — see _error_solution_count),
      paginated at page_size per page, fetched lazily only when the admin
      opens that accordion section rather than bulk-loading every category's
      FAQs up front.
    """
    page = max(page, 1)
    page_size = max(1, min(page_size, 50))

    async with db.tenant_connection(tenant_id) as conn:
        if category_id is None:
            categories = await conn.fetch(
                "SELECT id, name_ar, name_en, display_order FROM faq_categories "
                "WHERE tenant_id = $1 ORDER BY display_order, created_at",
                tenant_id,
            )
            summaries = []
            for c in categories:
                faq_count = await conn.fetchval(
                    "SELECT count(*) FROM faq_items WHERE category_id = $1 AND tenant_id = $2",
                    c["id"], tenant_id,
                )
                total = faq_count + await _error_solution_count(conn, tenant_id, c["id"])
                if total == 0:
                    continue
                summaries.append({
                    "category_id": str(c["id"]),
                    "name_ar": c["name_ar"],
                    "name_en": c["name_en"],
                    "display_order": c["display_order"],
                    "total": total,
                })
            return summaries

        category = await conn.fetchrow(
            "SELECT id, name_ar, name_en, display_order FROM faq_categories WHERE id = $1 AND tenant_id = $2",
            category_id, tenant_id,
        )
        if category is None:
            raise HTTPException(status_code=404, detail="FAQ category not found")

        rows = await conn.fetch(
            "SELECT id, question, answer, question_ar, answer_ar, created_at, 'faq' AS source "
            "FROM faq_items WHERE category_id = $1 AND tenant_id = $2",
            category_id, tenant_id,
        )
        if _is_vita_care(tenant_id):
            try:
                rows += await conn.fetch(
                    "SELECT id, error_text AS question, solution_text AS answer, "
                    "error_text_ar AS question_ar, solution_text_ar AS answer_ar, created_at, "
                    "'error_solution' AS source FROM error_solutions WHERE category_id = $1 AND tenant_id = $2",
                    category_id, tenant_id,
                )
            except asyncpg.UndefinedColumnError:
                pass  # migrations/007 not applied yet — FAQ-only for now

    rows = sorted(rows, key=lambda r: r["created_at"])
    total = len(rows)
    total_pages = max(1, -(-total // page_size))
    start = (page - 1) * page_size
    page_rows = rows[start:start + page_size]

    return {
        "category_id": str(category["id"]),
        "name_ar": category["name_ar"],
        "name_en": category["name_en"],
        "display_order": category["display_order"],
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "faqs": [
            {
                "id": str(r["id"]),
                "question": r["question"],
                "answer": r["answer"],
                "question_ar": r["question_ar"],
                "answer_ar": r["answer_ar"],
                "source": r["source"],
            }
            for r in page_rows
        ],
    }


@router.get("/faq/search-corpus")
async def faq_search_corpus(tenant_id: str = Depends(get_current_tenant)):
    """Every categorized FAQ (and, for Vita Care, categorized Error Solution)
    as a flat, unpaginated list — fetched lazily by the frontend only once
    the member actually starts typing into search, so client-side fuzzy
    search (Fuse.js, unchanged from before the accordion) keeps working over
    the full corpus without GET /faq/grouped having to bulk-load everything
    just to support search."""
    async with db.tenant_connection(tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT id, question, answer, question_ar, answer_ar, created_at, 'faq' AS source "
            "FROM faq_items WHERE tenant_id = $1 AND category_id IS NOT NULL",
            tenant_id,
        )
        if _is_vita_care(tenant_id):
            try:
                rows += await conn.fetch(
                    "SELECT id, error_text AS question, solution_text AS answer, "
                    "error_text_ar AS question_ar, solution_text_ar AS answer_ar, created_at, "
                    "'error_solution' AS source FROM error_solutions "
                    "WHERE tenant_id = $1 AND category_id IS NOT NULL",
                    tenant_id,
                )
            except asyncpg.UndefinedColumnError:
                pass

    rows = sorted(rows, key=lambda r: r["created_at"])
    return [
        {
            "id": str(r["id"]),
            "question": r["question"],
            "answer": r["answer"],
            "question_ar": r["question_ar"],
            "answer_ar": r["answer_ar"],
            "source": r["source"],
        }
        for r in rows
    ]


async def validate_category_id(conn, tenant_id: str, category_id: str | None) -> None:
    """Defends against a cross-tenant category_id: faq_items.category_id's FK
    only checks that the row exists in faq_categories *somewhere*, not that
    it belongs to this tenant — RLS would normally be the second guard here,
    but the DB role in use is known to bypass RLS (see the embeddings
    migration's RLS investigation earlier in this project), so this check
    must not depend on RLS either."""
    if category_id is None:
        return
    exists = await conn.fetchval(
        "SELECT 1 FROM faq_categories WHERE id = $1 AND tenant_id = $2",
        category_id, tenant_id,
    )
    if not exists:
        raise HTTPException(status_code=400, detail="Unknown category_id for this tenant")
