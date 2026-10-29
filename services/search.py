async def search_chunk(
    conn,
    query_embedding,
    tenant_id,
    category_id=None,
    limit: int = 3,
    threshold: float = 0.85,
) -> list[dict]:
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    rows = await conn.fetch(
        """
        SELECT content, document_id, slide_number, slide_title, embedding <=> $1 AS distance
        FROM chunks
        WHERE tenant_id = $2
          AND ($3::uuid IS NULL OR category_id = $3)
        ORDER BY embedding <=> $1
        LIMIT $4
        """,
        embedding_str, tenant_id, category_id, limit,
    )

    return [dict(r) for r in rows if r["distance"] < threshold]

async def search_media(
    conn,
    query_embedding,
    tenant_id,
    category_id=None,
    threshold: float = 0.20,
):
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    row = await conn.fetchrow(
        """
        SELECT id, filename, display_name, file_path, media_type, description, url,
               embedding <=> $1 AS distance
        FROM media
        WHERE tenant_id = $2
          AND ($3::uuid IS NULL OR category_id = $3)
        ORDER BY embedding <=> $1
        LIMIT 1
        """,
        embedding_str, tenant_id, category_id,
    )

    if row and row["distance"] < threshold:
        return dict(row)
    return None