from services.extraction import extract_pdf_pages, extract_slides_from_pptx

WORDS_PER_TXT_CHUNK = 650


def split_txt_into_chunks(text: str, words_per_chunk: int = WORDS_PER_TXT_CHUNK) -> list[dict]:
    """Plain .txt files have no natural pages, so they're split into fixed-size
    word chunks, each numbered sequentially as a "page" (1-indexed)."""
    words = text.split()
    if not words:
        return []
    return [
        {"page_number": i, "text": " ".join(words[start:start + words_per_chunk])}
        for i, start in enumerate(range(0, len(words), words_per_chunk), start=1)
    ]


def extract_index_pages(filename: str, file_bytes: bytes) -> tuple[str, list[dict]]:
    """
    Returns (file_type, pages) where file_type is 'pdf' | 'pptx' and pages is
    [{"page_number": int, "text": str}, ...]. Raises ValueError if the file
    type isn't supported by the Document Index or nothing could be extracted.
    Plain .txt is handled separately by split_txt_into_chunks since the
    caller (main.py) already has the decoded text on hand in that case.
    """
    name = filename.lower()
    if name.endswith(".pdf"):
        return "pdf", extract_pdf_pages(file_bytes)
    if name.endswith((".pptx", ".ppt")):
        slides = extract_slides_from_pptx(file_bytes)
        return "pptx", [{"page_number": s["slide_number"], "text": s["text"]} for s in slides]
    raise ValueError(f"Unsupported file type for Document Index: {filename}")


async def index_document_pages(
    conn, tenant_id: str, document_id: str, file_name: str, file_type: str, pages: list[dict],
) -> int:
    """Inserts one document_index_pages row per page/slide/chunk. search_vector
    is populated automatically by a DB trigger (migrations/002_...sql) — never
    set it from Python."""
    for page in pages:
        await conn.execute(
            """
            INSERT INTO document_index_pages
                (tenant_id, document_id, file_name, file_type, page_number, text_content)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            tenant_id, document_id, file_name, file_type, page["page_number"], page["text"],
        )
    return len(pages)
