# Componentes de terceros

El modelo de traducción no se redistribuye en este repositorio ni en el ZIP del proyecto. El instalador lo descarga del proveedor y comprueba su SHA-256 antes de extraer los archivos necesarios.

- Modelo inglés-español: [Argos Translate](https://github.com/argosopentech/argos-translate), [índice de modelos](https://github.com/argosopentech/argospm-index).
- Archivo: `https://argos-net.com/v1/translate-en_es-1_0.argosmodel`.
- SHA-256: `d698d0ef87ad70d5d184b7fa6965905bf4368f09a2bb9ffb165a79bac96af0c4`.
- El README del modelo atribuye el entrenamiento a los corpus OpenSubtitles, ParaCrawl y UNPC de OPUS. Se conserva ese README durante la instalación.
- [CTranslate2](https://github.com/OpenNMT/CTranslate2) y [SentencePiece](https://github.com/google/sentencepiece): ejecución y tokenización.
- [edge-tts](https://github.com/rany2/edge-tts): síntesis de voz mediante un servicio externo. El proyecto no está afiliado a Microsoft ni garantiza la disponibilidad de ese servicio.
- FastAPI, Uvicorn, Pydantic, deep-translator, langdetect y google-generativeai mantienen sus propias licencias y condiciones.

YouTube es una marca de sus respectivos titulares. Este proyecto no es una extensión oficial de YouTube ni de Google.
