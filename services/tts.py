import io
import re
import threading
import time
import wave

from google.genai import types
from google.genai.errors import ClientError

from core.ai_client import gemini_client, GEMINI_TTS_MODEL, GEMINI_TRANSCRIBE_MODEL

# Gemini's prebuilt TTS voices (see https://ai.google.dev/gemini-api/docs/speech-generation).
# Mirrors the old OpenAI voice slots 1:1 so the frontend keeps a 6-item picker;
# any of Gemini's ~30 prebuilt voices could be swapped in here.
VOICE_NAMES = {
    "zephyr": "Zephyr",  # bright
    "puck": "Puck",  # upbeat
    "kore": "Kore",  # firm
    "charon": "Charon",  # informative
    "leda": "Leda",  # youthful
    "fenrir": "Fenrir",  # excitable
}
DEFAULT_VOICE = "zephyr"

_PCM_MIME_RE = re.compile(r"^audio/L(?P<bits>\d+);codec=pcm;rate=(?P<rate>\d+)$")

_AUDIO_MIME_BY_EXT = {
    ".webm": "audio/webm",
    ".mp3": "audio/mp3",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
}


def _pcm_to_wav(pcm_bytes: bytes, mime_type: str) -> bytes:
    """Gemini TTS returns raw PCM (mime like "audio/L16;codec=pcm;rate=24000"),
    not a container format — wrap it in a WAV header so browsers can play it."""
    match = _PCM_MIME_RE.match(mime_type)
    sample_width_bytes = int(match.group("bits")) // 8 if match else 2
    sample_rate = int(match.group("rate")) if match else 24000

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(sample_width_bytes)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return buffer.getvalue()


class TTSRefusalError(RuntimeError):
    """The model declined to vocalize the text on this attempt (retryable)."""


class TTSGenerationFailed(RuntimeError):
    """All retry attempts were exhausted — the caller should fall back to
    get_fallback_audio() rather than surface this as a bare error, since a
    refusal is a property of this one call, not of the service being down."""


def _is_tts_refusal_error(error: ClientError) -> bool:
    # The model occasionally decides to answer/refuse instead of vocalizing
    # (observed non-deterministically — same input, same prompt, sometimes
    # 200s and sometimes 400s — confirmed against the live API), rather than
    # a stable property of the input text. Retrying is the correct fix, not
    # rewording the prompt further.
    return error.code == 400 and "should only be used for TTS" in (error.message or "")


def _extract_audio_part(response) -> types.Part:
    # A refusal doesn't always surface as an HTTP error: the model can also
    # return 200 with finish_reason=OTHER and candidates[0].content = None
    # (no parts at all) — confirmed against the live API. Treat that the same
    # as the 400 case above: retryable, not a crash.
    candidates = response.candidates or []
    content = candidates[0].content if candidates else None
    parts = content.parts if content else None
    if not parts:
        finish_reason = candidates[0].finish_reason if candidates else "unknown"
        raise TTSRefusalError(f"no audio content returned (finish_reason={finish_reason})")
    return parts[0]


def synthesize_speech(text: str, voice: str = DEFAULT_VOICE, max_retries: int = 5) -> bytes:
    voice_name = VOICE_NAMES.get(voice.lower(), VOICE_NAMES[DEFAULT_VOICE])
    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
            )
        ),
    )
    # Bare `text` as contents is unreliable on its own: text that reads as a
    # question or command sometimes gets answered or refused by the model
    # instead of vocalized (confirmed against the live API — bot answers are
    # arbitrary generated text, so this is not a corner case). This "TTS the
    # following:" prefix isn't itself spoken (verified by transcribing the
    # output) — response_modalities=["AUDIO"] means only audio comes back —
    # and speech_config's system_instruction equivalent isn't supported by
    # this preview model (it 500s), so the prefix has to ride inside
    # `contents` instead. The prefix reduces, but does not eliminate, the
    # failure (~1 in 4-5 calls for question-shaped text, observed live) —
    # see the retry loop below, which is the real mitigation.
    contents = f"TTS the following:\n{text}"

    last_error = None
    for attempt in range(max_retries):
        try:
            response = gemini_client.models.generate_content(
                model=GEMINI_TTS_MODEL, contents=contents, config=config,
            )
            part = _extract_audio_part(response)
            return _pcm_to_wav(part.inline_data.data, part.inline_data.mime_type)
        except ClientError as e:
            if not _is_tts_refusal_error(e):
                raise
            last_error = e
        except TTSRefusalError as e:
            last_error = e
        if attempt < max_retries - 1:
            time.sleep(0.5)
    raise TTSGenerationFailed(f"gave up after {max_retries} attempts: {last_error}") from last_error


# Declarative on purpose (no "?", no imperative framing) — the fallback text
# must not trigger the same refusal behavior it exists to work around.
FALLBACK_TEXT = "Sorry, I couldn't generate audio for that. Please try again."

_fallback_audio_cache: bytes | None = None
_fallback_lock = threading.Lock()


def _silent_wav_fallback() -> bytes:
    """Absolute last resort if even the fallback phrase can't be synthesized
    (e.g. Gemini itself is down) — a fixed 0.3s of silence, built locally
    with no network call, so callers never go without *some* audio."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(b"\x00\x00" * int(24000 * 0.3))
    return buffer.getvalue()


def get_fallback_audio() -> bytes:
    """Lazily synthesizes and caches FALLBACK_TEXT on first use (rather than
    at process startup, so a Gemini hiccup at boot can't block the app from
    starting) so a later TTS exhaustion never re-hits the network for it."""
    global _fallback_audio_cache
    if _fallback_audio_cache is not None:
        return _fallback_audio_cache

    with _fallback_lock:
        if _fallback_audio_cache is None:  # re-check: lost the race while waiting for the lock
            try:
                _fallback_audio_cache = synthesize_speech(FALLBACK_TEXT, DEFAULT_VOICE)
            except TTSGenerationFailed:
                # Don't cache this — a transient Gemini outage shouldn't
                # permanently downgrade every future request to silence.
                return _silent_wav_fallback()
    return _fallback_audio_cache


def _is_arabic_or_english(text: str) -> bool:
    if not text.strip():
        return True

    arabic_chars = len(re.findall(r'[؀-ۿ]', text))
    latin_chars = len(re.findall(r'[a-zA-Z]', text))
    total_chars = len(re.sub(r'\s', '', text))

    if total_chars == 0:
        return True

    recognized_ratio = (arabic_chars + latin_chars) / total_chars
    return recognized_ratio > 0.6


_TRANSCRIBE_LANGUAGE_HINTS = {
    "ar": "The speaker is most likely speaking Arabic.",
    "en": "The speaker is most likely speaking English, but may speak Arabic.",
}


def transcribe_audio(audio_bytes: bytes, filename: str = "audio.webm", language_hint: str | None = None) -> str:
    """language_hint: the user's UI language ("ar"/"en"), used only as a hint;
    whatever language is actually spoken is what gets transcribed."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mime_type = _AUDIO_MIME_BY_EXT.get(ext, "audio/webm")

    # Without the "never translate" rule Gemini sometimes returns an English
    # translation of Arabic (especially dialect) speech, which then makes the
    # bot answer and speak in English.
    prompt = (
        "Transcribe this audio verbatim, in the language actually spoken. Never translate: "
        "Arabic speech, including Egyptian, Gulf, Levantine or any other dialect, must be "
        "written in Arabic script exactly as said; English speech in English. Keep English "
        "words mixed into Arabic speech (system or menu names) as spoken. "
        "Return only the transcript text, with no explanations, labels, or extra commentary. "
        "If the audio has no speech, return an empty response."
    )
    hint = _TRANSCRIBE_LANGUAGE_HINTS.get((language_hint or "").lower())
    if hint:
        prompt += " " + hint

    response = gemini_client.models.generate_content(
        model=GEMINI_TRANSCRIBE_MODEL,
        contents=[
            prompt,
            types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
        ],
    )
    text = (response.text or "").strip()

    if not _is_arabic_or_english(text):
        return ""

    return text
