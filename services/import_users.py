import openpyxl
import io
import json
import re

from google.genai import types
from loguru import logger

from core.ai_client import gemini_client, GEMINI_FLASH_MODEL


async def parse_excel(file_bytes: bytes) -> tuple[list[str], list[list[str]]]:
    """يقرأ الـ Excel ويرجّع headers + كل الصفوف"""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
    except Exception:
        raise ValueError("Could not read Excel file")

    if not rows or len(rows) < 2:
        raise ValueError("Excel file is empty or has no data rows")

    headers = [str(h) if h is not None else "" for h in rows[0]]
    data_rows = []
    for row in rows[1:]:
        converted = [str(c) if c is not None else "" for c in row]
        # openpyxl's used range often extends past the real data (formatting
        # dragged down/across empty cells), so iter_rows() can report far more
        # rows than actually contain data. Drop any row that's entirely blank
        # here so every caller (xlsx document upload, error-solutions import,
        # user import) gets only real rows.
        if any(cell.strip() for cell in converted):
            data_rows.append(converted)

    return headers, data_rows


async def detect_mapping(headers: list[str]) -> dict:
    """يبعت الـ headers للموديل ويرجّع الـ mapping"""
    prompt = f"""You are a data mapping assistant. Given these Excel column headers, identify which column index (0-based) corresponds to each required field.

Headers: {headers}

Required fields:
- email: the user's email address
- username: the user's display name or full name
- role: the user's role (admin/editor/member/auditor) — if not found, use null

Respond ONLY with a valid JSON object like this (no markdown, no explanation):
{{"email": 0, "username": 1, "role": null}}

Rules:
- Use null if a field cannot be confidently identified
- Use the 0-based column index
- email is required, username is required, role is optional"""

    response = gemini_client.models.generate_content(
        model=GEMINI_FLASH_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            max_output_tokens=300, temperature=0,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    raw_text = (response.text or "").strip()
    # The model sometimes wraps JSON in a ```json ... ``` fence despite being told not to.
    unfenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text, flags=re.IGNORECASE).strip()

    try:
        return json.loads(unfenced)
    except Exception:
        logger.exception(f"AI mapping response was not valid JSON: {raw_text!r}")
        raise ValueError("AI could not determine column mapping")

