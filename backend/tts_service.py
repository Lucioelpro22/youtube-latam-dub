"""
TTS Service using edge-tts for high-quality Latin American neural voices.
"""
import io
import edge_tts

DEFAULT_VOICE = "es-MX-DaliaNeural"

LATAM_VOICES = {
    "es-MX-DaliaNeural": "México - Dalia (Femenina / Neutro)",
    "es-MX-JorgeNeural": "México - Jorge (Masculina / Neutro)",
    "es-AR-TomasNeural": "Argentina - Tomás (Masculino)",
    "es-AR-ElenaNeural": "Argentina - Elena (Femenina)",
    "es-CO-GonzaloNeural": "Colombia - Gonzalo (Masculino)",
    "es-CO-SalomeNeural": "Colombia - Salomé (Femenina)",
    "es-CL-LorenzoNeural": "Chile - Lorenzo (Masculino)",
    "es-PE-AlexNeural": "Perú - Alex (Masculino)",
    "es-ES-AlvaroNeural": "España - Álvaro (Castellano)",
}

async def generate_speech(text: str, voice: str = DEFAULT_VOICE, rate: str = "+0%", pitch: str = "+0Hz") -> bytes:
    """
    Synthesize speech for given text into MP3 bytes.
    rate can be e.g. "+15%" to match fast video pacing.
    """
    if voice not in LATAM_VOICES and not voice.startswith("es-"):
        voice = DEFAULT_VOICE
    
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    audio_buffer = io.BytesIO()
    
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_buffer.write(chunk["data"])
            
    audio_buffer.seek(0)
    return audio_buffer.read()
