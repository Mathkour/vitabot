import asyncio
import math

from google.genai import types
from google.genai.errors import ClientError, ServerError

from core.ai_client import gemini_client, GEMINI_EMBEDDING_MODEL

GEMINI_EMBEDDING_DIM = 1536


def _l2_normalize(vec: list[float]) -> list[float]:
    # gemini-embedding-001 does not auto-normalize truncated
    # (non-native-3072) output — verified live during the migration backfill
    # (scripts/backfill_embeddings.py): an output_dimensionality=1536 vector
    # had L2 norm ~0.69, not 1.0. Normalizing here keeps get_embedding()'s
    # output consistent with every embedding scripts/backfill_embeddings.py
    # already wrote to this same column.
    norm = math.sqrt(sum(x * x for x in vec))
    return vec if norm == 0 else [x / norm for x in vec]


async def get_embedding(text: str, max_retries: int = 3) -> list[float]:
    last_error = None
    for attempt in range(max_retries):
        try:
            response = gemini_client.models.embed_content(
                model=GEMINI_EMBEDDING_MODEL,
                contents=text,
                config=types.EmbedContentConfig(
                    output_dimensionality=GEMINI_EMBEDDING_DIM,
                    task_type="RETRIEVAL_DOCUMENT",
                ),
            )
            return _l2_normalize(response.embeddings[0].values)
        except (ClientError, ServerError) as e:
            last_error = e
            if attempt < max_retries - 1:
                await asyncio.sleep(1.5 * (attempt + 1))
    raise last_error
