"""
FastAPI Server for YouTube Latam Dubbing.
Receives video text chunks, translates them to Latin American Spanish, and returns synthetic speech audio.
"""
import asyncio
import time
import base64
import os
from typing import Optional, Literal
import logging
from contextlib import asynccontextmanager
import local_translator
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
import uvicorn

from tts_service import generate_speech, LATAM_VOICES, DEFAULT_VOICE
from translator_service import translate_sentence, TranslationUnavailable

logger = logging.getLogger("uvicorn.error")

@asynccontextmanager
async def lifespan(app):
    if local_translator.available():
        await asyncio.to_thread(local_translator.warmup)
        logger.info("[YT-Dub] Traductor local inglés -> español listo")
    yield


app = FastAPI(
    lifespan=lifespan,
    title="YouTube Latam Dub Server",
    description="Backend for real-time translation & TTS dubbing into Latin American Spanish",
    version="1.3.0-beta.1"
)

# Enable CORS for Chrome Extension requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://www.youtube.com", "https://youtube.com", "https://m.youtube.com"],
    allow_origin_regex=r"chrome-extension://[a-p]{32}",
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    expose_headers=["Retry-After"],
)

class DubRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    source_lang: Literal["auto", "es", "en"] = "auto"
    context: str = Field(default="", max_length=2000)
    voice: Optional[str] = DEFAULT_VOICE
    rate: Optional[str] = Field(default="+0%", pattern=r"^[+-]\d{1,3}%$") #   # e.g., "+10%", "-5%"
    pitch: Optional[str] = Field(default="+0Hz", pattern=r"^[+-]\d{1,3}Hz$")
    api_key: Optional[str] = None # Optional Gemini API Key

    @field_validator("voice")
    @classmethod
    def supported_voice(cls, value):
        if value is not None and value not in LATAM_VOICES:
            raise ValueError("Seleccioná una de las voces disponibles")
        return value

    @field_validator("rate")
    @classmethod
    def supported_rate(cls, value):
        if value is not None and not -50 <= int(value[:-1]) <= 100:
            raise ValueError("La velocidad debe estar entre -50% y +100%")
        return value

    @field_validator("pitch")
    @classmethod
    def supported_pitch(cls, value):
        if value is not None and not -100 <= int(value[:-2]) <= 100:
            raise ValueError("El tono debe estar entre -100Hz y +100Hz")
        return value


class DubResponse(BaseModel):
    original_text: str
    translated_text: str
    audio_base64: str
    voice: str
    timings_ms: dict[str, float] = Field(default_factory=dict)

@app.get("/api/status")
async def status():
    return {
        "status": "online",
        "service": "youtube-latam-dub",
        "has_gemini_env": bool(os.environ.get("GEMINI_API_KEY")),
        "local_translation": local_translator.available(),
        "translation_pair": "en-es" if local_translator.available() else None,
        "version": "1.3.0-beta.1"
    }

@app.get("/api/voices")
async def get_voices():
    return {"voices": LATAM_VOICES, "default": DEFAULT_VOICE}

@app.post("/api/dub", response_model=DubResponse)
async def process_dub(request: DubRequest):
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    started = time.perf_counter()
    # Run blocking provider calls outside the server event loop.
    # 1. Translate text to Latam Spanish
    try:
        translated = await asyncio.wait_for(asyncio.to_thread(
            translate_sentence, text=request.text,
            api_key=request.api_key,
            target_lang="es", source_lang=request.source_lang, context=request.context
        ), timeout=5.0)
    except TranslationUnavailable as e:
        raise HTTPException(status_code=503,
            detail={"code": e.code, "message": str(e), "retry_after": e.retry_after},
            headers={"Retry-After": str(e.retry_after)})
    except asyncio.TimeoutError:
        logger.warning("[YT-Dub] La traducción superó el tiempo de espera")
        raise HTTPException(status_code=504,
            detail={"code": "translation_timeout", "message": "El traductor tardó demasiado. Se reintentará.", "retry_after": 10},
            headers={"Retry-After": "10"})
    except Exception as e:
        logger.error("[YT-Dub] Error inesperado de traducción: %s", type(e).__name__)
        raise HTTPException(status_code=500, detail={"code": "translation_error", "message": "Ocurrió un error de traducción.", "retry_after": 15})

    if not translated:
        translated = request.text

    translated_at = time.perf_counter()
    # 2. Generate Audio via Neural TTS
    try:
        audio_bytes = await asyncio.wait_for(generate_speech(
            text=translated,
            voice=request.voice or DEFAULT_VOICE,
            rate=request.rate or "+0%",
            pitch=request.pitch or "+0Hz"
        ), timeout=5.0)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Speech generation timed out")
    except Exception as e:
        logger.warning("[YT-Dub] Servicio de voz no disponible: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail={"code": "tts_unavailable", "message": "El servicio de voz no está disponible temporalmente.", "retry_after": 15}, headers={"Retry-After": "15"})

    finished = time.perf_counter()
    if not audio_bytes:
        raise HTTPException(status_code=502, detail="Speech provider returned empty audio")
    # 3. Encode to Base64 for fast Data-URL playback in Chrome
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

    return DubResponse(
        original_text=request.text,
        translated_text=translated,
        audio_base64=audio_b64,
        voice=request.voice or DEFAULT_VOICE,
        timings_ms={"translation": round((translated_at-started)*1000, 1),
                    "tts": round((finished-translated_at)*1000, 1),
                    "total": round((finished-started)*1000, 1)}
    )

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
