import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

import db
from core.auth import require_housing_bank_tenant
from services.llm import generate_answer, generate_no_info_response

router = APIRouter(prefix="/index", tags=["document-index"])

ASK_CONTEXT_PAGES_LIMIT = 8
ASK_CONTEXT_CHARS_PER_PAGE = 4000

_WORD_RE = re.compile(r"\w+", re.UNICODE)

# Common filler/question words in both languages — stripped before building
# the OR-tsquery so a question like "شو يعني incoterms؟" doesn't pull in
# every page that merely contains "شو" or "يعني" (extremely common Arabic
# words) while having nothing to do with "incoterms" itself. Conservative by
# design: it only drops words that carry no topical meaning on their own.
_STOPWORDS = {
    "شو", "ما", "ماذا", "هل", "كيف", "متى", "أين", "وين", "ليش", "لماذا",
    "هي", "هو", "هم", "انت", "أنت", "انا", "أنا", "يعني", "عن", "مع", "او",
    "أو", "في", "من", "الى", "إلى", "على", "كل", "بس", "فقط", "ممكن", "بدي",
    "لو", "اذا", "إذا", "ان", "أن", "كان", "يكون",
    "a", "an", "the", "is", "are", "was", "were", "what", "how", "when",
    "where", "why", "who", "which", "does", "do", "did", "of", "in", "on",
    "at", "to", "for", "with", "and", "or", "but", "about", "please", "can",
    "you", "me", "tell", "explain",
}


def _any_word_tsquery(text: str) -> str | None:
    """Builds an OR-of-every-word tsquery string (e.g. "foo | bar | baz") so a
    natural-language question matches any page containing at least one of its
    words, instead of plainto_tsquery's AND-of-every-word semantics (which
    would require one single page to contain every word in the question,
    including filler words like "what"/"is" — almost never true for a real
    question). Filler words are stripped first (see _STOPWORDS) so they don't
    drag in pages that share only a common word with the question. Ranking
    (ts_rank) still favors pages matching more words, and generate_answer's
    own source-integrity/no-invention rules are what actually catch any
    remaining irrelevant excerpts. Returns None if nothing is left to query."""
    words = _WORD_RE.findall(text)
    meaningful = [w for w in words if w.lower() not in _STOPWORDS]
    words = meaningful or words
    if not words:
        return None
    return " | ".join(words)


class AskIndexRequest(BaseModel):
    question: str


@router.get("/search")
async def search_index(
    q: str = Query(..., min_length=1),
    limit: int = Query(30, ge=1, le=200),
    tenant_id: str = Depends(require_housing_bank_tenant),
):
    query = q.strip()
    if not query:
        return []

    async with db.tenant_connection(tenant_id) as conn:
        rows = await conn.fetch(
            """
            SELECT id, file_name, file_type, page_number,
                   ts_rank(search_vector, plainto_tsquery('simple', $1)) AS rank,
                   ts_headline(
                       'simple', text_content, plainto_tsquery('simple', $1),
                       'StartSel=<mark>, StopSel=</mark>, MaxWords=40, MinWords=15, MaxFragments=1'
                   ) AS snippet
            FROM document_index_pages
            WHERE tenant_id = $2 AND search_vector @@ plainto_tsquery('simple', $1)
            ORDER BY rank DESC
            LIMIT $3
            """,
            query, tenant_id, limit,
        )

    return [
        {
            "page_id": str(r["id"]),
            "file_name": r["file_name"],
            "file_type": r["file_type"],
            "page_number": r["page_number"],
            "snippet": r["snippet"],
        }
        for r in rows
    ]


@router.get("/pages/{page_id}")
async def get_index_page(
    page_id: str,
    tenant_id: str = Depends(require_housing_bank_tenant),
):
    async with db.tenant_connection(tenant_id) as conn:
        row = await conn.fetchrow(
            """
            SELECT id, file_name, file_type, page_number, text_content, created_at
            FROM document_index_pages
            WHERE id = $1 AND tenant_id = $2
            """,
            page_id, tenant_id,
        )

    if row is None:
        raise HTTPException(status_code=404, detail="Page not found")

    return {
        "page_id": str(row["id"]),
        "file_name": row["file_name"],
        "file_type": row["file_type"],
        "page_number": row["page_number"],
        "text_content": row["text_content"],
        "created_at": row["created_at"],
    }


@router.post("/ask")
async def ask_index(
    body: AskIndexRequest,
    tenant_id: str = Depends(require_housing_bank_tenant),
):
    """AI-generated answer for Housing Bank, built ONLY from the indexed
    documents' own text (same table/search as GET /index/search) — never
    from the model's general knowledge. The system prompt in generate_answer
    already enforces "answer only from context" + the [[NO_INFO]] marker, so
    this reuses that exact same no-invention guarantee as the main chatbot."""
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

    tsquery_str = _any_word_tsquery(question)
    rows = []
    if tsquery_str:
        async with db.tenant_connection(tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT file_name, file_type, page_number, text_content,
                       ts_rank(search_vector, to_tsquery('simple', $1)) AS rank
                FROM document_index_pages
                WHERE tenant_id = $2 AND search_vector @@ to_tsquery('simple', $1)
                ORDER BY rank DESC
                LIMIT $3
                """,
                tsquery_str, tenant_id, ASK_CONTEXT_PAGES_LIMIT,
            )

    if not rows:
        return {
            "answer": generate_no_info_response(question, tenant_id=tenant_id),
            "sources": [],
            "offer_support": True,
        }

    context_chunks = [r["text_content"][:ASK_CONTEXT_CHARS_PER_PAGE] for r in rows]
    answer = generate_answer(question, context_chunks, None, None, tenant_id=tenant_id)

    offer_support = False
    if answer.startswith("[[NO_INFO]]"):
        answer = answer[len("[[NO_INFO]]"):].strip()
        offer_support = True

    # No sources shown when the model declined — the retrieved pages weren't
    # actually used for the answer, so listing them alongside a "don't have
    # info" reply would misleadingly suggest they were.
    sources = [] if offer_support else [
        {"file_name": r["file_name"], "file_type": r["file_type"], "page_number": r["page_number"]}
        for r in rows
    ]
    return {"answer": answer, "sources": sources, "offer_support": offer_support}
