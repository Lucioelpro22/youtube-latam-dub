# Privacidad

- La extensión lee los subtítulos visibles de YouTube y los envía al servidor en `127.0.0.1:8000`.
- Inglés → español se traduce localmente si está instalado el modelo.
- El texto que se convierte en voz se envía al servicio utilizado por **Edge TTS**. La voz no es offline.
- Para otros idiomas, o si falta el modelo local, el programa puede consultar Google/MyMemory. Si configurás una clave de Gemini, puede usar ese servicio en los recorridos externos.
- No hay cuentas propias, analítica ni envío de historial por parte del proyecto. Las preferencias se almacenan en `chrome.storage.sync`; una clave opcional guardada ahí puede sincronizarse mediante tu cuenta del navegador. No se recomienda usar una clave sensible en una computadora compartida.
- No publiques claves, logs privados, grabaciones ni archivos `.env` en un repositorio.
