"""
Self-test script for translation and Latin American TTS audio synthesis.
"""
import asyncio
import os
import sys

# Ensure backend folder is in sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from translator_service import translate_sentence
from tts_service import generate_speech, LATAM_VOICES

async def run_test():
    test_english_sentence = "Welcome back everyone. Today we are going to explore how neural dubbing works in real time."
    print("1. Texto de prueba en inglÃ©s:")
    print(f"   \"{test_english_sentence}\"\n")

    print("2. Probando traducciÃ³n al espaÃ±ol latino...")
    translated = translate_sentence(test_english_sentence)
    print(f"   TraducciÃ³n obtenida: \"{translated}\"\n")

    voice = "es-MX-DaliaNeural"
    print(f"3. Generando audio con voz neuronal '{voice}' ({LATAM_VOICES.get(voice)})...")
    audio_bytes = await generate_speech(translated, voice=voice)
    print(f"   Â¡Audio generado con Ã©xito! TamaÃ±o: {len(audio_bytes)} bytes.\n")

    out_file = os.path.join(os.path.dirname(__file__), "sample_output.mp3")
    with open(out_file, "wb") as f:
        f.write(audio_bytes)
    print(f"4. Archivo de prueba guardado en:\n   {out_file}")
    print("\n[OK] El pipeline de traducciÃ³n y sÃ­ntesis de voz funciona perfectamente.")

if __name__ == "__main__":
    asyncio.run(run_test())
