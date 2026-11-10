import base64
import time

from google.genai import types
from loguru import logger

from core.ai_client import anthropic_client, gemini_client, extract_text, SONNET_MODEL, GEMINI_FLASH_MODEL
from services.ai_monitoring import log_ai_prediction

_IMAGE_MEDIA_TYPE_SNIFFERS: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def _detect_image_media_type(image_bytes: bytes) -> str:
    """
    Sniffs the real image format from its magic bytes rather than assuming
    one. extract_text_from_image is shared by multiple producers — PDF pages
    rasterized by pdf2image (JPEG, see services/extraction.py) and raw
    embedded PPTX picture blobs (whatever format was embedded — often JPEG,
    sometimes PNG) — that don't all emit the same format. A single hardcoded
    media_type here was wrong for at least one of them, and Claude's Vision
    API 400s if the declared media_type doesn't match the actual bytes.
    """
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    for magic, media_type in _IMAGE_MEDIA_TYPE_SNIFFERS:
        if image_bytes.startswith(magic):
            return media_type

    logger.warning(
        f"extract_text_from_image: unrecognized image format "
        f"(first bytes: {image_bytes[:12]!r}, len={len(image_bytes)}) — defaulting to image/jpeg"
    )
    return "image/jpeg"


def _log_call(fn, *, endpoint: str, model_used: str, summary: str, tenant_id: str | None):
    """Runs fn() (a zero-arg anthropic_client.messages.create call), logging a
    structured ai_predictions_log row alongside it. Re-raises on failure —
    never swallows an error the caller would otherwise have seen."""
    start_time = time.time()
    try:
        result = fn()
        log_ai_prediction(
            tenant_id=tenant_id, endpoint=endpoint, model_used=model_used,
            request_summary=summary, response_time_ms=round((time.time() - start_time) * 1000),
            status="success",
        )
        return result
    except Exception as e:
        log_ai_prediction(
            tenant_id=tenant_id, endpoint=endpoint, model_used=model_used,
            request_summary=summary, response_time_ms=round((time.time() - start_time) * 1000),
            status="timeout" if "timeout" in type(e).__name__.lower() else "error",
            error_message=str(e),
        )
        raise


def generate_answer(question: str, context_chunks: list[str], media_hint: str | None = None, history: list[dict] | None = None, tenant_id: str | None = None) -> str:
    context = "\n\n".join(context_chunks)

    system_prompt = (
        "You are a friendly, professional assistant for a company's support system. "
        "You can respond naturally to greetings, small talk, and general courtesy "
        "(e.g. 'hi', 'how are you', 'thank you') in a warm, brief, human way.\n\n"
        "CRITICAL FORMATTING RULE: Never use Markdown syntax in your response — no asterisks "
        "for bold/italic (**text** or *text*), no pound signs for headers (# Header), no "
        "markdown bullet points (- item or * item). Write in plain, natural text only. If you "
        "need to list items, use plain numbered lines (1. 2. 3.) followed by a period and "
        "space, or simple line breaks — never markdown formatting symbols.\n\n"
        "For questions about the company's information, services, or processes, answer "
        "ONLY based on the context provided below. If the answer to such a question is "
        "not in the context, politely say you don't have enough information about that "
        "specific topic, and if relevant suggest they rephrase or ask about something else.\n\n"
        "CRITICAL NO-INFO MARKER RULE: If, and only if, you are declining to answer because "
        "the information needed is genuinely missing from the context above, begin your "
        "ENTIRE response with the exact marker [[NO_INFO]] (no space after it), immediately "
        "followed by your short, polite decline message. Never use this marker when you are "
        "providing a real answer, even a partial one, from the context — only use it when you "
        "have no relevant information to give at all.\n\n"
        "CRITICAL NO-INVENTION RULE: The context below was retrieved by keyword matching, so it "
        "may contain excerpts that share a few words with the question but are not actually "
        "about the topic asked at all. If NONE of the excerpts genuinely discuss the topic the "
        "user asked about, you MUST respond with the [[NO_INFO]] marker — even if you personally "
        "know the general answer from your own training. Never fall back on your own world "
        "knowledge to fill the gap; a short definition you generate yourself, instead of from "
        "the context, is exactly the kind of answer this system must never give.\n\n"
        "CRITICAL SOURCE-INTEGRITY RULE: The context below may contain excerpts from "
        "multiple different documents covering different topics. Answer using ONLY the "
        "excerpts that are genuinely about the specific topic the user asked about. If "
        "some excerpts describe a different process or feature than what was asked, "
        "IGNORE them completely — do not merge them into your answer, do not continue a "
        "numbered list with steps from an unrelated process, and never invent connecting "
        "steps to make separate excerpts flow together. It is far better to give a short, "
        "complete answer from one relevant source than a longer answer that mixes "
        "unrelated procedures. If the relevant excerpts only describe 3 steps, your "
        "answer must have exactly those 3 steps — do not pad it.\n\n"
        "CRITICAL COMPLETENESS RULE: When answering from the context excerpts, you MUST include "
        "EVERY step, field name, option, and note/warning mentioned in the excerpt — do not "
        "summarize, shorten, or skip any part of it, even if it seems minor. If the excerpt "
        "describes more than one method or scenario, present all of them, not just the first "
        "one.\n\n"
        "CRITICAL NATURAL-ANSWER RULE: Never just copy-paste a raw label or bullet fragment from "
        "the excerpt as your entire answer (e.g. a slide title or a single short phrase with no "
        "verb). Write your answer as a complete, natural sentence (or a few sentences) that "
        "directly and fully addresses what the user asked, using only facts drawn from the "
        "excerpt — rephrasing and connecting them into real prose is expected and required, not "
        "optional, even when the excerpt itself is terse. This is about HOW you present the same "
        "facts, not about adding anything beyond them.\n\n"
        "CRITICAL CALCULATION RULE: If the user's question contains all the numeric inputs "
        "needed for a calculation (e.g. amounts, rates, dates, percentages, durations) AND "
        "the context below contains the calculation methodology or formula (even if it is "
        "illustrated with different example numbers than the user's), you MUST perform the "
        "calculation using the user's own numbers, showing your work step by step. Do NOT "
        "decline just because the user's numbers differ from the example in the context — "
        "applying a documented methodology to new numbers is expected and required. Only "
        "decline if the methodology or formula itself is genuinely absent from the context. "
        "If the user's inputs violate a stated rule or limit found in the context (e.g. a "
        "financing percentage above a documented maximum, or a duration exceeding a documented "
        "limit), still perform the calculation as requested AND explicitly point out the "
        "violation in your answer.\n\n"
        "Use the conversation history to understand follow-up questions (e.g. 'explain more', "
        "'put it in points', 'translate that') — they refer to your previous answer in the chat.\n\n"
        "Keep replies concise and helpful.\n\n"
        "CRITICAL VERBATIM-TERMS RULE: Technical terms, names, labels, and numbers in the context "
        "below must be copied EXACTLY as they appear there — never substitute a term with a "
        "different word that looks or sounds similar, even if it seems like a more natural or "
        "expected word. This applies especially to Arabic technical vocabulary, where visually or "
        "phonetically similar words can have completely different meanings. If a term in the "
        "context looks unclear, unusual, or possibly mistyped, still quote it exactly as written "
        "rather than guessing a cleaner-looking replacement — do not silently correct or normalize "
        "it. If the retrieved text is genuinely illegible or cut off such that you cannot tell what "
        "a term says, say so explicitly instead of guessing.\n\n"
        "CRITICAL LANGUAGE RULE: Always respond in the exact same language the user's question "
        "was asked in, regardless of what language the retrieved context/documents below are in. "
        "If the question is in English, answer in English even if all source material is in "
        "Arabic — translate the relevant information yourself. If the question is in Arabic, "
        "answer in Arabic even if sources are in English. The language of the context below must "
        "NEVER influence which language you reply in — only the user's own question decides that. "
        "Never translate or switch the user's own language.\n\n"
        f"Context:\n{context}\n\n"
        "(Reminder: your answer must be in the SAME language as the user's question above, "
        "not the language of the context you just read — translate as needed.)"
    )

    if media_hint:
        system_prompt += (
            f"\n\nNote: A helpful video titled '{media_hint}' is attached to your answer "
            "and will be shown to the user below your message. If your text context is not "
            "enough to fully answer, briefly and naturally invite the user to watch the attached "
            "video for the steps (in the user's language). Keep it short and helpful, not robotic."
        )
    else:
        system_prompt += (
            "\n\nCRITICAL NO-PHANTOM-ATTACHMENT RULE: No video, image, or other attachment is "
            "being shown alongside your answer this time. The context excerpts above may still "
            "contain a sentence referring to an attached video or 'see the attached file/video "
            "titled ...' — that sentence describes something attached to the ORIGINAL source "
            "document, not something available here. You MUST NOT tell the user to watch an "
            "attached video, see an attachment, or refer to any resource 'below' or 'attached' — "
            "omit any such sentence entirely from your answer. Answer using only the remaining "
            "textual steps/facts from the context; if removing that sentence leaves genuinely "
            "nothing else relevant, use the [[NO_INFO]] marker instead."
        )

    # Gemini uses 'model' for the assistant role (not 'assistant'), and takes
    # turns as Content objects rather than the Anthropic {"role","content"}
    # dicts the `history` rows are shaped as.
    contents = []
    for turn in (history or []):
        role = "model" if turn["role"] == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part(text=turn["content"])]))
    contents.append(types.Content(role="user", parts=[types.Part(text=question)]))

    start_time = time.time()
    try:
        # Switched from Anthropic (claude-sonnet-5) to Gemini — same context,
        # same system prompt (including the [[NO_INFO]] marker and the other
        # CRITICAL rules above), just a different model behind generate_answer.
        # Thinking is left at its default (not disabled) since this prompt's
        # multi-step rules (source-integrity, calculation) benefit from it,
        # unlike the mechanical translate_text/generate_no_info_response calls.
        response = gemini_client.models.generate_content(
            model=GEMINI_FLASH_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=4096,
            ),
        )
        answer = (response.text or "").strip()
        log_ai_prediction(
            tenant_id=tenant_id, endpoint="ask", model_used=GEMINI_FLASH_MODEL,
            request_summary=question, response_time_ms=round((time.time() - start_time) * 1000),
            status="success",
        )
        return answer
    except Exception as e:
        log_ai_prediction(
            tenant_id=tenant_id, endpoint="ask", model_used=GEMINI_FLASH_MODEL,
            request_summary=question, response_time_ms=round((time.time() - start_time) * 1000),
            status="timeout" if "timeout" in type(e).__name__.lower() else "error",
            error_message=str(e),
        )
        raise

def translate_text(text:str, tenant_id: str | None = None)->str:
    start_time = time.time()
    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_FLASH_MODEL,
            contents=text,
            config=types.GenerateContentConfig(
                system_instruction="Translate the given text to the other language (if English , translate to Arabic ; translate to english).Reply with ONLY the translation , nothing else",
                max_output_tokens=1024,
                # gemini-2.5-flash's default "thinking" eats into max_output_tokens
                # and can truncate short replies mid-sentence — not needed for a
                # mechanical translation task, so disabled here.
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        translation = (response.text or "").strip()
        log_ai_prediction(
            tenant_id=tenant_id, endpoint="translation", model_used=GEMINI_FLASH_MODEL,
            request_summary=text, response_time_ms=round((time.time() - start_time) * 1000),
            status="success",
        )
        return f"{text}{translation}"
    except Exception as e:
        log_ai_prediction(
            tenant_id=tenant_id, endpoint="translation", model_used=GEMINI_FLASH_MODEL,
            request_summary=text, response_time_ms=round((time.time() - start_time) * 1000),
            status="timeout" if "timeout" in type(e).__name__.lower() else "error",
            error_message=str(e),
        )
        raise


def extract_text_from_image(image_bytes: bytes, tenant_id: str | None = None) -> str:
    base64_image = base64.b64encode(image_bytes).decode("utf-8")
    media_type = _detect_image_media_type(image_bytes)
    start_time = time.time()
    logger.debug(f"OCR request: {len(image_bytes)} bytes, media_type={media_type}")
    try:
        response = anthropic_client.messages.create(
            model=SONNET_MODEL,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64_image,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Extract all the text from this image. Return only the raw text, no explanations.",
                        },
                    ],
                }
            ],
        )
        result = extract_text(response)
        print(f"OCR result length: {len(result)}, preview: {result[:200]}")
        log_ai_prediction(
            tenant_id=tenant_id, endpoint="ocr_extraction", model_used=SONNET_MODEL,
            request_summary=f"[image, {len(image_bytes)} bytes]",
            response_time_ms=round((time.time() - start_time) * 1000), status="success",
        )
        return result
    except Exception as e:
        # media_type/size included so a future format mismatch is diagnosable
        # straight from the ai_predictions_log/Loguru output, no repro needed.
        logger.exception(
            f"OCR failed: media_type={media_type}, size={len(image_bytes)} bytes, error={e}"
        )
        log_ai_prediction(
            tenant_id=tenant_id, endpoint="ocr_extraction", model_used=SONNET_MODEL,
            request_summary=f"[image, {len(image_bytes)} bytes, media_type={media_type}]",
            response_time_ms=round((time.time() - start_time) * 1000),
            status="timeout" if "timeout" in type(e).__name__.lower() else "error",
            error_message=f"[media_type={media_type}] {e}",
        )
        raise


def generate_admin_answer(question:str,admin_context:str, tenant_id: str | None = None)->str:
    system_prompt=(
        "You are an admin assistant for a knowledge-base management system. "
        "Answer the admin's question about THEIR data using ONLY the information below. "
        "The information contains their documents, media, and categories. "
        "Be precise with numbers and names. If asked something not in the data, say so.\n\n"
        "CRITICAL FORMATTING RULE: Never use Markdown syntax in your response — no asterisks "
        "for bold/italic (**text** or *text*), no pound signs for headers (# Header), no "
        "markdown bullet points (- item or * item). Write in plain, natural text only. If you "
        "need to list items, use plain numbered lines (1. 2. 3.) followed by a period and "
        "space, or simple line breaks — never markdown formatting symbols.\n\n"
        "CRITICAL LANGUAGE RULE: Reply in the SAME language as the admin's question. "
        "If the question is in English, reply ONLY in English. If in Arabic, reply ONLY "
        "in Arabic. Never reply in any other language (especially never French). "
        "Match the question's language exactly.\n\n"
        f"Admin's data:\n{admin_context}"
    )

    response = _log_call(
        lambda: anthropic_client.messages.create(
            model=SONNET_MODEL,
            max_tokens=2048,
            system=system_prompt,
            messages=[
                {"role":"user","content":question},
            ],
        ),
        endpoint="admin_assistant", model_used=SONNET_MODEL, summary=question, tenant_id=tenant_id,
    )
    return extract_text(response)

def generate_no_info_response(question: str, tenant_id: str | None = None) -> str:
    prompt = f"""The user asked: "{question}"

CRITICAL FORMATTING RULE: Never use Markdown syntax in your response — no asterisks for
bold/italic (**text** or *text*), no pound signs for headers (# Header), no markdown bullet
points (- item or * item). Write in plain, natural text only. If you need to list items, use
plain numbered lines (1. 2. 3.) followed by a period and space, or simple line breaks — never
markdown formatting symbols.

We don't have information about this in our knowledge base. Respond warmly and briefly:
1. Acknowledge you don't have specific information on this topic.
2. Offer to help with something else, in a friendly, natural tone.
Keep it short (1-2 sentences). Match the language the user wrote in (Arabic or English)."""

    response = _log_call(
        lambda: gemini_client.models.generate_content(
            model=GEMINI_FLASH_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=300,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        ),
        endpoint="no_info_response", model_used=GEMINI_FLASH_MODEL, summary=question, tenant_id=tenant_id,
    )
    return (response.text or "").strip()

def translate_to_english(text:str, tenant_id: str | None = None)->str:

    response = _log_call(
        lambda: gemini_client.models.generate_content(
            model=GEMINI_FLASH_MODEL,
            contents=text,
            config=types.GenerateContentConfig(
                system_instruction="Translate the given text to English.If it's already in English , return it exactly as-is. reply with only the translation, nothing else.",
                max_output_tokens=1024,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        ),
        endpoint="translation", model_used=GEMINI_FLASH_MODEL, summary=text, tenant_id=tenant_id,
    )
    return (response.text or "").strip()


def select_relevant_slides(question:str,slides:list[dict], tenant_id: str | None = None)->list[dict]:
    slides_preview="\n\n".join(
        f"---[slide{s['slide_number']}] ---\n"
        f"Title/Topic :{s.get('slide_title') or '(no clear title)'}\n"
        f"Content:{s['content'][:600]}"
        for s in slides
    )
    prompt=(
        "You are selecting which slide(s) from a PowerPoint deck actually answer a "
        "user's question. You are NOT answering the question yourself — only deciding "
        "which slide numbers are relevant.\n\n"
        "Guidelines:\n"
        "- If the answer is fully contained in one slide, return just that slide number.\n"
        "- If the answer spans multiple CONSECUTIVE slides that share the same topic/title "
        "(e.g. a multi-part explanation continued across slides), return all of them.\n"
        "- Do NOT include a slide just because it's topically related in a loose sense — "
        "only include slides that directly contain information needed to answer the "
        "specific question asked.\n"
        "- The question may be in a different language than the slide content (e.g. an "
        "Arabic question about English slides) — match by MEANING, not by matching language "
        "or exact wording.\n"
        "- If none of the provided slides actually answer the question, respond with 'NONE' "
        "rather than guessing or picking a loosely related slide.\n\n"
        f"User's question: {question}\n\n"
        f"Candidate slides:\n{slides_preview}\n\n"
        "Respond with ONLY a comma-separated list of relevant slide numbers "
        "(e.g. '13,14,15,16'), or exactly 'NONE' if none apply. No explanation, no other text."

    )
    response = _log_call(
        lambda: gemini_client.models.generate_content(
            model=GEMINI_FLASH_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=100, temperature=0,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        ),
        endpoint="slide_selection", model_used=GEMINI_FLASH_MODEL, summary=question, tenant_id=tenant_id,
    )
    raw=(response.text or "").strip()
    if raw.upper()=="NONE":
        return[]

    try:
        chosen_numbers={int(n.strip())for n in raw.split(",") if n.strip().isdigit()}

    except ValueError:
        return[]
    return[s for s in slides if s["slide_number"] in chosen_numbers]


def translate_verbatim(text: str, target_language: str, tenant_id: str | None = None) -> str:
    """
    Faithful, literal translation — no summarizing, no rephrasing, no adding
    or removing information. Used for PPTX slide content so the Arabic
    output stays a true 1:1 translation of the original slide text.
    """
    prompt = (
        f"Translate the following text into {target_language.upper()}. "
        f"The output MUST be entirely in {target_language} — do not use any "
        "other language, especially not French. "
        "This must be a faithful, literal translation — do not summarize, "
        "shorten, rephrase, reorganize, or add/remove any information. "
        "Preserve the exact structure, order, and level of detail of the "
        "original text. Reply with ONLY the translation, nothing else."
    )
    response = _log_call(
        lambda: gemini_client.models.generate_content(
            model=GEMINI_FLASH_MODEL,
            contents=text,
            config=types.GenerateContentConfig(
                system_instruction=prompt, max_output_tokens=2048, temperature=0,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        ),
        endpoint="translation", model_used=GEMINI_FLASH_MODEL, summary=text, tenant_id=tenant_id,
    )
    return (response.text or "").strip()
