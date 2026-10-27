# YouTube Latam Dub

**Escuchá en español latino los subtítulos de videos de YouTube.**

Extensión para Chrome/Edge y servidor local para Windows. Traduce inglés → español en tu computadora y genera voz con Edge TTS. Primera versión pública **beta 1.3.0-beta.1**.

[Descargar versión para Windows](https://github.com/Lucioelpro22/youtube-latam-dub/releases/tag/v1.3.0-beta.1) · [Reportar un problema](https://github.com/Lucioelpro22/youtube-latam-dub/issues) · [Privacidad](PRIVACY.md)

## Instalación

Necesitás **Windows de 64 bits**, **Python 3.11–3.14 de 64 bits** y Chrome o Edge. La instalación descarga dependencias y un modelo de aproximadamente 84 MB. Dejá al menos 1 GB libre. No necesitás una clave API para inglés → español.

1. Instalá Python desde [python.org](https://www.python.org/downloads/windows/) y marcá **Add Python to PATH**.
2. Descargá `youtube-latam-dub-v1.3.0-beta.1-windows.zip` desde la versión publicada y **extraelo** en una carpeta.
3. Abrí **`install.bat`**. Esperá hasta que indique que terminó la instalación.
4. Abrí **`run_server.bat`** y dejá esa ventana abierta.
5. En Chrome, abrí `chrome://extensions` (en Edge, `edge://extensions`). Activá **Modo desarrollador**, elegí **Cargar descomprimida** y seleccioná la carpeta **`extension`** del proyecto.
6. Abrí o recargá un video de YouTube, activá los subtítulos y dejá **Doblaje Latino: ON**.

En el popup de la extensión debería aparecer **Conectado · traducción local inglés → español**. Usá **Automático → audio en español** al cambiar de video.

## Qué incluye

- Traducción local de inglés a español; el modelo se precarga al iniciar.
- Voces latinoamericanas y ajuste de velocidad y volumen de fondo.
- Respuestas ordenadas, cola limitada y cancelación de frases anteriores al adelantar o cambiar de video.
- Pausa y reanudación junto al video, y adaptación a su velocidad.
- Detección de subtítulos ya escritos en español.
- Mensajes y espera entre reintentos cuando un servicio externo falla.
- Instalación aislada en `.venv`, descarga verificada del modelo y diagnóstico local.

## Límites de la beta

**No es sincronización labial ni doblaje completo sin pérdidas.** El programa trabaja después de que aparecen los subtítulos. Puede existir demora. Los fragmentos con más de seis segundos de antigüedad se descartan, incluso si se estaban reproduciendo, para evitar que crezca el atraso. En habla rápida puede omitir o cortar frases.

La voz **necesita Internet** y su proveedor puede limitar solicitudes. Inglés → español funciona localmente; otros idiomas no tienen esa garantía. La traducción automática puede equivocarse, especialmente con nombres, jerga y frases cortas. Depende de la estructura de la página de YouTube, que puede cambiar.

Esta beta fue verificada con pruebas automatizadas y solicitudes reales de traducción y voz. No se afirma compatibilidad universal ni validación completa en todas las versiones de navegador. No está publicada en Chrome Web Store.

## Problemas frecuentes

- **Servidor desconectado:** abrí `run_server.bat`. Si el puerto 8000 está ocupado, cerrá la otra instancia del servidor.
- **No está el modelo:** ejecutá `install.bat` de nuevo. Se comprueba el archivo descargado antes de instalar.
- **No hay voz:** activá los subtítulos, comprobá Internet y que la pestaña no esté silenciada. Si hay una cuenta regresiva, esperá al próximo intento.
- **Actualizaste archivos:** reiniciá el servidor, recargá la extensión y recargá YouTube.
- **Diagnóstico:** ejecutá `.venv\Scripts\python.exe scripts\diagnose.py` desde la carpeta del proyecto.

## Desarrollo

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.venv\Scripts\python.exe scripts\download_model.py
.venv\Scripts\python.exe backend\server.py
```

Pruebas (Python y Node.js; no requieren voz externa):

```powershell
.venv\Scripts\python.exe -m pip install httpx
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
node --test tests/sync.test.cjs
```

Las pruebas de traducción local se omiten si no está instalado el modelo. El script `test_pipeline.py` consulta el servicio de voz y guarda una muestra: no mide sincronización en YouTube.

## Privacidad y licencia

Leé [PRIVACY.md](PRIVACY.md) y [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). El servidor solo escucha en `127.0.0.1`. El código de este proyecto se publica bajo [MIT](LICENSE); los componentes y modelos de terceros conservan sus propias condiciones.
