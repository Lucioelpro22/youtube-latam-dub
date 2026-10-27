"""Offline installation check; no external translation or speech requests."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main():
    import fastapi, edge_tts
    import local_translator
    if not local_translator.available():
        raise RuntimeError("Faltan dependencias o el modelo. Ejecutá install.bat.")
    result = local_translator.translate("Today we are learning how to build an application.")
    print("Traducción de prueba:", result)
    if not result or result.startswith("Today we"):
        raise RuntimeError("La comprobación de traducción no pasó.")
    print("Instalación local lista. La voz requiere Internet.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Diagnóstico:", exc, file=sys.stderr)
        sys.exit(1)
