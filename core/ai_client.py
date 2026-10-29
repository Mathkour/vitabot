import os
from anthropic import Anthropic
from google import genai

anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

SONNET_MODEL = "claude-sonnet-5"
HAIKU_MODEL = "claude-haiku-4-5-20251001"

GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"
GEMINI_TRANSCRIBE_MODEL = "gemini-2.5-flash"
GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"
# Same model as GEMINI_TRANSCRIBE_MODEL — named separately for the text-generation
# call sites migrated off claude-haiku-4-5-20251001 in services/llm.py and
# services/import_users.py, so the two use cases can be retuned independently later.
GEMINI_FLASH_MODEL = "gemini-2.5-flash"


def extract_text(response) -> str:
    return next((block.text for block in response.content if block.type == "text"), "")
