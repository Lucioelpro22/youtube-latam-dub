"""
Translation service supporting Google Gemini API and zero-config Fallback.
"""
import os
import re
import threading
import hashlib
import time
import math
import logging
from typing import Optional
import local_translator

try:
    from langdetect import detect_langs, DetectorFactory
    DetectorFactory.seed = 0
except ImportError:
    detect_langs = None

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

try:
    from deep_translator import MyMemoryTranslator, GoogleTranslator
    from deep_translator.exceptions import TooManyRequests
    DEEP_TRANSLATOR_AVAILABLE = True
except ImportError:
    DEEP_TRANSLATOR_AVAILABLE = False
    class TooManyRequests(Exception):
        pass

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

# In-memory translation cache to avoid re-translating same sentences
TRANSLATION_CACHE = {}
CACHE_LOCK = threading.Lock()
GEMINI_LOCK = threading.Lock()
PROVIDER_SLOTS = threading.BoundedSemaphore(2)
PROVIDER_LOCK = threading.Lock()
PROVIDER_COOLDOWNS = {}
logger = logging.getLogger("uvicorn.error")


class TranslationUnavailable(RuntimeError):
    def __init__(self, message, code="translation_unavailable", retry_after=15):
        super().__init__(message)
        self.code = code
        self.retry_after = max(1, int(retry_after))


def call_provider(name, operation):
    # Cooldown is shared across requests/tabs. Do not keep hitting a limited provider.
    with PROVIDER_LOCK:
        until, code, message = PROVIDER_COOLDOWNS.get(name, (0, "", ""))
        remaining = until - time.monotonic()
    if remaining > 0:
        raise TranslationUnavailable(message, code, math.ceil(remaining))
    try:
        result = operation()
        if not result:
            raise RuntimeError("empty provider response")
        return result
    except Exception as exc:
        limited = isinstance(exc, TooManyRequests) or getattr(exc, "code", None) == 429
        code = "rate_limited" if limited else "translation_unavailable"
        seconds = 60 if limited else 15
        message = ("El traductor alcanzó su límite de uso. Se reintentará automáticamente."
                   if limited else "El servicio de traducción no está disponible temporalmente.")
        with PROVIDER_LOCK:
            if len(PROVIDER_COOLDOWNS) >= 128:
                PROVIDER_COOLDOWNS.pop(next(iter(PROVIDER_COOLDOWNS)))
            PROVIDER_COOLDOWNS[name] = (time.monotonic() + seconds, code, message)
        # No API keys, caption text or raw provider errors in the log.
        logger.warning("[YT-Dub] Traducción: %s; espera %ss (%s)", code, seconds, type(exc).__name__)
        raise TranslationUnavailable(message, code, seconds) from exc


def clean_text(text: str) -> str:
    """Strip extra whitespaces and newlines."""
    return re.sub(r'\s+', ' ', text).strip()

def translate_with_gemini(text: str, api_key: str, target_lang_name: str = "español latinoamericano") -> str:
    """Translate using Gemini model with prompt fine-tuned for spoken video dubbing."""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = (
        f"Eres un traductor y adaptador de doblaje profesional. "
        f"Traduce el siguiente texto al {target_lang_name} natural, conciso y fluido, "
        f"apropiado para ser leído en voz alta por un narrador. "
        f"Devuelve ÚNICAMENTE la traducción directa sin comillas ni explicaciones:\n\n{text}"
    )
    response = model.generate_content(prompt, request_options={"timeout": 4.0})
    return response.text.strip()

def detect_source(text: str) -> Optional[str]:
    # Short isolated words are ambiguous; do not guess their source language.
    if detect_langs is None or len(text.split()) < 5:
        return None
    try:
        guesses = detect_langs(text)
        if guesses and guesses[0].prob >= 0.95:
            return guesses[0].lang
    except Exception:
        pass
    return None


def resolve_source(text: str, source_lang: str = "auto", context: str = "") -> Optional[str]:
    # Prefer current caption evidence over a saved setting from a previous video.
    # Use recent words to avoid retaining the language of an older caption track.
    recent = " ".join((context or text).split()[-25:])
    detected = detect_source(recent)
    if detected in ("en", "es"):
        return detected
    if source_lang in ("en", "es"):
        return source_lang
    return detected


def translate_fallback(text: str, source_lang: str = "auto", context: str = "") -> str:
    """Auto-detect first; use MyMemory only when the source is confidently English."""
    source = resolve_source(text, source_lang, context)
    if source == "es":
        return text
    if not DEEP_TRANSLATOR_AVAILABLE:
        raise TranslationUnavailable("Falta instalar el servicio de traducción.", retry_after=60)
    try:
        result = call_provider("google", lambda: GoogleTranslator(source="auto", target="es").translate(text))
    except TranslationUnavailable as google_error:
        if source != "en":
            raise
        try:
            result = call_provider("mymemory", lambda: MyMemoryTranslator(source="english", target="spanish latin america").translate(text))
        except TranslationUnavailable as memory_error:
            # Retry when at least one applicable provider becomes available again.
            retry = min(google_error.retry_after, memory_error.retry_after)
            code = "rate_limited" if google_error.code == memory_error.code == "rate_limited" else "translation_unavailable"
            raise TranslationUnavailable(memory_error.args[0], code, retry) from memory_error
    if not result:
        raise RuntimeError("Translation provider returned empty text")
    return result


def _translate_sentence(text: str, api_key: Optional[str] = None, target_lang: str = "es", source_lang: str = "auto", context: str = "") -> str:
    """Main translation function with caching and fallback."""
    cleaned = clean_text(text)
    if not cleaned:
        return ""
        
    source = resolve_source(cleaned, source_lang, context)
    if source == "es":
        return cleaned
    api_key_to_use = api_key or os.environ.get("GEMINI_API_KEY")
    use_local = source in (None, "en") and local_translator.available()
    provider_id = "local-en-es-v1" if use_local else (hashlib.sha256(api_key_to_use.encode()).hexdigest() if api_key_to_use else "auto")
    cache_key = (target_lang, provider_id, source, cleaned)
    with CACHE_LOCK:
        if cache_key in TRANSLATION_CACHE:
            return TRANSLATION_CACHE[cache_key]
    result = ""

    if use_local:
        result = local_translator.translate(cleaned)
    elif api_key_to_use and GENAI_AVAILABLE:
        try:
            # The legacy SDK configures a global API key; serialize this section.
            if not GEMINI_LOCK.acquire(timeout=0.5):
                raise RuntimeError("Gemini is busy")
            try:
                result = call_provider("gemini:" + provider_id, lambda: translate_with_gemini(cleaned, api_key_to_use))
            finally:
                GEMINI_LOCK.release()
        except Exception as e:
            result = translate_fallback(cleaned, source or "auto", context)
    else:
        result = translate_fallback(cleaned, source or "auto", context)

    with CACHE_LOCK:
        if len(TRANSLATION_CACHE) >= 512:
            TRANSLATION_CACHE.pop(next(iter(TRANSLATION_CACHE)))
        TRANSLATION_CACHE[cache_key] = result
    return result

def translate_sentence(text: str, api_key: Optional[str] = None, target_lang: str = "es", source_lang: str = "auto", context: str = "") -> str:
    # Reading Spanish captions needs no translation worker or provider availability.
    source = resolve_source(text, source_lang, context)
    if source == "es":
        return clean_text(text)
    if not PROVIDER_SLOTS.acquire(blocking=False):
        raise TranslationUnavailable("El traductor está ocupado. Se reintentará en unos segundos.", code="provider_busy", retry_after=3)
    try:
        return _translate_sentence(text, api_key, target_lang, source_lang, context)
    finally:
        PROVIDER_SLOTS.release()
