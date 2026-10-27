document.addEventListener("DOMContentLoaded", () => {
  const statusBadge = document.getElementById("status-badge");
  const statusText = document.getElementById("status-text");
  const sourceLanguageSelect = document.getElementById("source-language");
  const voiceSelect = document.getElementById("voice-select");
  const rateSlider = document.getElementById("rate-slider");
  const rateLabel = document.getElementById("rate-label");
  const volSlider = document.getElementById("vol-slider");
  const volLabel = document.getElementById("vol-label");
  const apiKeyInput = document.getElementById("api-key");
  const btnSave = document.getElementById("btn-save");

  const backendUrl = "http://127.0.0.1:8000";

  // Check backend server status
  fetch(`${backendUrl}/api/status`)
    .then((res) => res.json())
    .then((data) => {
      if (data.status === "online") {
        statusBadge.className = "status-badge status-online";
        statusText.innerText = data.local_translation ? "Conectado · traducción local inglés → español" : "Servidor Conectado (127.0.0.1:8000)";
      }
    })
    .catch(() => {
      statusBadge.className = "status-badge status-offline";
      statusText.innerText = "Servidor Desconectado (Inicia run_server.bat)";
    });

  // Load saved preferences
  chrome.storage.sync.get(
    ["voice", "rate", "bgVolume", "apiKey", "sourceLanguage", "languageSettingsVersion"],
    (items) => {
      if (items.languageSettingsVersion !== 2) {
        chrome.storage.sync.set({ sourceLanguage: "auto", languageSettingsVersion: 2 });
        items.sourceLanguage = "auto";
      }
      sourceLanguageSelect.value = items.sourceLanguage || "auto";
      if (items.voice) voiceSelect.value = items.voice;
      if (items.apiKey) apiKeyInput.value = items.apiKey;

      if (items.rate) {
        const val = parseInt(items.rate.replace("%", "").replace("+", ""), 10) || 0;
        rateSlider.value = val;
        updateRateLabel(val);
      }

      if (items.bgVolume !== undefined) {
        const volVal = Math.round(items.bgVolume * 100);
        volSlider.value = volVal;
        volLabel.innerText = `${volVal}%`;
      }
    }
  );

  function updateRateLabel(val) {
    if (val === 0) rateLabel.innerText = "Normal";
    else if (val > 0) rateLabel.innerText = `+${val}% (Más rápido)`;
    else rateLabel.innerText = `${val}% (Más lento)`;
  }

  rateSlider.addEventListener("input", (e) => {
    updateRateLabel(parseInt(e.target.value, 10));
  });

  volSlider.addEventListener("input", (e) => {
    volLabel.innerText = `${e.target.value}%`;
  });

  btnSave.addEventListener("click", () => {
    const rateVal = parseInt(rateSlider.value, 10);
    const rateStr = rateVal >= 0 ? `+${rateVal}%` : `${rateVal}%`;
    const bgVolRatio = parseInt(volSlider.value, 10) / 100.0;

    chrome.storage.sync.set(
      {
        sourceLanguage: sourceLanguageSelect.value,
        languageSettingsVersion: 2,
        voice: voiceSelect.value,
        rate: rateStr,
        bgVolume: bgVolRatio,
        apiKey: apiKeyInput.value.trim()
      },
      () => {
        btnSave.innerText = "¡Guardado con éxito! ✅";
        setTimeout(() => {
          btnSave.innerText = "Guardar Configuración";
        }, 1500);
      }
    );
  });
});
