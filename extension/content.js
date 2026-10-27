/** Live captions dubbing with ordered, bounded work and media-time expiry. */
(function () {
  let isEnabled = true;
  let backendUrl = "http://127.0.0.1:8000";
  let selectedVoice = "es-MX-DaliaNeural";
  let voiceRate = "+0%";
  let bgVolumeRatio = 0.18;
  let geminiApiKey = "";
  let sourceLanguage = "auto";
  let retryUntil = 0, failureCount = 0, serviceMessage = "";
  const MAX_LAG = 6; // Media seconds; prefer current speech over a growing backlog.
  const MAX_JOBS = 3;
  const MAX_REQUESTS = 2;
  let currentVideo = null, videoListeners = null;
  let savedVideoVolume = 1, isDucking = false;
  let generation = 0, nextId = 0;
  let jobs = [], active = new Set(), currentJob = null;
  let audioPlayer = new Audio();
  let spokenHistory = "", pendingWordBuffer = "", lastRawText = "";
  let pendingAt = 0, debounceTimer = null, maxWaitTimer = null;

  function loadSettings() {
    if (typeof chrome === "undefined" || !chrome.storage?.sync) return;
    chrome.storage.sync.get(["enabled", "voice", "rate", "bgVolume", "apiKey", "backendUrl", "sourceLanguage", "languageSettingsVersion"], (s) => {
      if (s.languageSettingsVersion !== 2) {
        chrome.storage.sync.set({ sourceLanguage: "auto", languageSettingsVersion: 2 });
        s.sourceLanguage = "auto";
      }
      const wasEnabled = isEnabled;
      isEnabled = s.enabled ?? true;
      selectedVoice = s.voice || "es-MX-DaliaNeural";
      voiceRate = s.rate || "+0%";
      bgVolumeRatio = s.bgVolume ?? 0.18;
      geminiApiKey = s.apiKey || "";
      sourceLanguage = ["auto", "es", "en"].includes(s.sourceLanguage) ? s.sourceLanguage : "auto";
      backendUrl = s.backendUrl || "http://127.0.0.1:8000";
      if (wasEnabled !== isEnabled || jobs.length || currentJob) resetSession();
      updatePillUI();
      if (isEnabled) autoEnableCaptions();
    });
  }

  function restoreVolume() {
    if (currentVideo && isDucking) currentVideo.volume = savedVideoVolume;
    isDucking = false;
  }

  function resetSession() {
    generation++;
    clearTimeout(debounceTimer);
    clearTimeout(maxWaitTimer);
    debounceTimer = maxWaitTimer = null;
    pendingWordBuffer = spokenHistory = lastRawText = "";
    for (const job of active) job.controller.abort();
    active.clear();
    jobs = [];
    currentJob = null;
    audioPlayer.onended = audioPlayer.onerror = null;
    audioPlayer.pause();
    audioPlayer.removeAttribute("src");
    audioPlayer.load();
    restoreVolume();
    const box = document.getElementById("yt-latam-subtitle-box");
    if (box) { clearTimeout(box.hideTimeout); box.classList.remove("visible"); }
  }

  function findVideoElement() {
    const video = document.querySelector("video.html5-main-video");
    if (video === currentVideo) return video;
    resetSession();
    videoListeners?.abort();
    currentVideo = video;
    if (!video) return null;
    savedVideoVolume = video.volume;
    videoListeners = new AbortController();
    const options = { signal: videoListeners.signal };
    video.addEventListener("pause", () => { audioPlayer.pause(); restoreVolume(); }, options);
    video.addEventListener("play", () => {
      if (currentJob) resumeAudio(currentJob); else pump();
      lastRawText = ""; readCaptions();
    }, options);
    for (const event of ["seeking", "emptied", "ended"]) video.addEventListener(event, resetSession, options);
    video.addEventListener("ratechange", updatePlaybackRate, options);
    video.addEventListener("seeked", () => { lastRawText = ""; readCaptions(); }, options);
    return video;
  }

  // Inject UI Pill into YouTube Player
  function injectPill() {
    if (document.getElementById("yt-latam-dub-pill")) return;

    const playerContainer = document.querySelector("#movie_player");
    if (!playerContainer) return;

    const pill = document.createElement("div");
    pill.id = "yt-latam-dub-pill";
    pill.innerHTML = `
      <span class="yt-dub-dot ${isEnabled ? 'active' : ''}"></span>
      <span id="yt-dub-label">Doblaje Latino</span>
      <button class="yt-dub-toggle-btn ${isEnabled ? '' : 'off'}" id="yt-dub-toggle">
        ${isEnabled ? 'ON' : 'OFF'}
      </button>
    `;

    playerContainer.appendChild(pill);

    // Subtitle preview banner
    const subBox = document.createElement("div");
    subBox.id = "yt-latam-subtitle-box";
    playerContainer.appendChild(subBox);

    document.getElementById("yt-dub-toggle").addEventListener("click", (e) => {
      e.stopPropagation();
      isEnabled = !isEnabled;
      if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.sync) {
        chrome.storage.sync.set({ enabled: isEnabled });
      }
      updatePillUI();
      if (!isEnabled) {
        resetSession();
        spokenHistory = "";
      } else {
        resetSession();
        autoEnableCaptions();
      }
    });
  }

  function updatePillUI() {
    const pill = document.getElementById("yt-latam-dub-pill");
    const dot = pill?.querySelector(".yt-dub-dot");
    const btn = document.getElementById("yt-dub-toggle");
    if (!pill || !dot || !btn) return;
    const seconds = Math.max(0, Math.ceil((retryUntil - performance.now()) / 1000));
    const label = document.getElementById("yt-dub-label");
    if (label) label.textContent = isEnabled && seconds ? `Doblaje: espera ${seconds} s` : "Doblaje Latino";
    pill.title = isEnabled && seconds ? serviceMessage : "";

    if (isEnabled) {
      pill.classList.add("active");
      dot.classList.add("active");
      btn.classList.remove("off");
      btn.innerText = "ON";
    } else {
      pill.classList.remove("active");
      dot.classList.remove("active");
      btn.classList.add("off");
      btn.innerText = "OFF";
    }
  }

  function showSubtitleTranslation(text) {
    const box = document.getElementById("yt-latam-subtitle-box");
    if (box) {
      box.innerText = "🎙️ " + text;
      box.classList.add("visible");
      clearTimeout(box.hideTimeout);
      box.hideTimeout = setTimeout(() => {
        box.classList.remove("visible");
      }, 4500);
    }
  }

  // Automatically enable YouTube captions if they are off
  function autoEnableCaptions() {
    const ccBtn = document.querySelector(".ytp-subtitles-button");
    if (ccBtn && ccBtn.getAttribute("aria-pressed") === "false") {
      ccBtn.click();
    }
  }

  function stale(job) {
    return job.generation !== generation || !isEnabled || !currentVideo ||
      currentVideo.currentTime - job.at > MAX_LAG || currentVideo.currentTime < job.at - 0.5;
  }

  function updatePlaybackRate() {
    if (!currentJob || !currentVideo) return;
    const lag = Math.max(0, currentVideo.currentTime - currentJob.at);
    audioPlayer.playbackRate = Math.min(4, currentVideo.playbackRate * (1 + Math.min(0.35, lag * 0.06)));
    audioPlayer.preservesPitch = true;
  }

  function resumeAudio(job) {
    if (currentJob !== job) return;
    if (stale(job)) { finishAudio(job); return; }
    if (currentVideo.paused || currentVideo.seeking) return;
    if (!isDucking) { savedVideoVolume = currentVideo.volume; isDucking = true; }
    currentVideo.volume = savedVideoVolume * bgVolumeRatio;
    updatePlaybackRate();
    audioPlayer.play().catch((err) => {
      if (currentJob !== job || currentVideo?.paused) return;
      console.warn("[YT-Dub] No se pudo reproducir el audio:", err);
      finishAudio(job);
    });
  }

  function finishAudio(job) {
    if (currentJob !== job) return;
    audioPlayer.onended = audioPlayer.onerror = null;
    audioPlayer.pause();
    currentJob = null;
    restoreVolume();
    const box = document.getElementById("yt-latam-subtitle-box");
    if (box) box.classList.remove("visible");
    pump();
  }

  function pump() {
    for (const job of jobs) {
      if (stale(job)) { job.state = "discarded"; job.controller?.abort(); }
    }
    jobs = jobs.filter(j => j.state !== "discarded" && j.state !== "failed");
    if (!isEnabled || !currentVideo || currentVideo.paused || currentVideo.seeking) return;
    for (const job of jobs) {
      if (performance.now() < retryUntil || active.size >= (failureCount ? 1 : MAX_REQUESTS)) break;
      if (job.state === "waiting") startRequest(job);
    }
    // Consume only the oldest remaining job; response completion order cannot reorder speech.
    if (!currentJob && jobs[0]?.state === "ready") {
      const job = jobs.shift();
      currentJob = job;
      audioPlayer.src = `data:audio/mp3;base64,${job.data.audio_base64}`;
      audioPlayer.onended = audioPlayer.onerror = () => finishAudio(job);
      showSubtitleTranslation(job.data.translated_text);
      resumeAudio(job);
    }
    if (currentJob) updatePlaybackRate();
  }

  async function startRequest(job) {
    job.state = "loading";
    job.controller = new AbortController();
    active.add(job);
    const started = performance.now();
    const timeout = setTimeout(() => job.controller.abort(), 8000);
    try {
      const resp = await fetch(`${backendUrl}/api/dub`, {
        method: "POST", signal: job.controller.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: job.text, context: job.context, source_lang: sourceLanguage, voice: selectedVoice, rate: voiceRate, api_key: geminiApiKey || null })
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        const detail = body.detail;
        const message = detail && typeof detail === "object" ? detail.message : null;
        const error = new Error(message || `El servidor no pudo procesar la frase (${resp.status}).`);
        error.retryAfter = Number(resp.headers?.get?.("Retry-After") || detail?.retry_after || 0);
        error.status = resp.status;
        throw error;
      }
      const data = await resp.json();
      if (stale(job) || job.state === "discarded") return;
      failureCount = 0; serviceMessage = "";
      job.data = data;
      job.state = "ready";
      console.debug("[YT-Dub]", { id: job.id, request_ms: Math.round(performance.now() - started),
        lag_s: currentVideo.currentTime - job.at, timings: data.timings_ms });
    } catch (err) {
      if (job.generation !== generation || job.state === "discarded") return;
      job.state = "failed";
      // A request timeout also needs backoff; user cancellation is ignored above.
      failureCount++;
      const suggested = Number.isFinite(err.retryAfter) ? err.retryAfter : 0;
      const seconds = Math.min(300, Math.max(suggested, Math.min(60, 2 ** Math.min(failureCount, 6))));
      retryUntil = Math.max(retryUntil, performance.now() + seconds * 1000);
      serviceMessage = err.name === "AbortError" ? "El servicio tardó demasiado." : err.message;
      // Drop queued phrases instead of replaying them after the cooldown.
      for (const pending of jobs) {
        if (pending !== job) { pending.state = "discarded"; pending.controller?.abort(); }
      }
      jobs = [];
      console.warn("[YT-Dub]", serviceMessage, `Reintento en ${seconds} s`);
      if (!currentJob) showSubtitleTranslation(`${serviceMessage} Reintento en ${seconds} s.`);
      updatePillUI();
    } finally {
      clearTimeout(timeout);
      active.delete(job);
      if (job.generation === generation) pump();
    }
  }

  function enqueue(text, at) {
    if (!isEnabled || !currentVideo || performance.now() < retryUntil) return;
    while (jobs.length >= MAX_JOBS) {
      const old = jobs.shift(); old.state = "discarded"; old.controller?.abort();
    }
    jobs.push({ id: nextId++, generation, text, context: spokenHistory.slice(-2000), at, state: "waiting" });
    pump();
  }

  function extractOnlyNewWords(history, text) {
    const tokens = s => (s.match(/\S+/gu) || []).map(w => w.toLocaleLowerCase().replace(/[^\p{L}\p{N}]/gu, ""));
    const previous = tokens(history), current = tokens(text), raw = text.match(/\S+/gu) || [];
    let overlap = 0;
    for (let n = 1; n <= Math.min(previous.length, current.length); n++) {
      if (previous.slice(-n).join(" ") === current.slice(0, n).join(" ")) overlap = n;
    }
    // Do not suppress intentional repetitions merely because they occurred somewhere in history.
    return raw.slice(overlap).join(" ");
  }

  function flushCaption() {
    clearTimeout(debounceTimer); clearTimeout(maxWaitTimer);
    debounceTimer = maxWaitTimer = null;
    const text = pendingWordBuffer.trim(), at = pendingAt;
    pendingWordBuffer = "";
    if (!text || !isEnabled || !currentVideo || currentVideo.seeking) return;
    enqueue(text, at);
  }

  function handleCaptionUpdate(text) {
    if (!isEnabled || !currentVideo || currentVideo.paused || currentVideo.seeking) return;
    const words = extractOnlyNewWords(spokenHistory, text);
    if (!words) return;
    if (!pendingWordBuffer) pendingAt = currentVideo.currentTime;
    pendingWordBuffer = (pendingWordBuffer + " " + words).trim();
    spokenHistory = (spokenHistory + " " + words).trim().split(/\s+/).slice(-60).join(" ");
    clearTimeout(debounceTimer);
    if (!maxWaitTimer) maxWaitTimer = setTimeout(flushCaption, 700);
    if (/[.!?]$/.test(pendingWordBuffer) || pendingWordBuffer.split(/\s+/).length >= 12) flushCaption();
    else debounceTimer = setTimeout(flushCaption, 220);
  }

  function readCaptions() {
    if (!isEnabled) return;
    const text = Array.from(document.querySelectorAll(".ytp-caption-segment"))
      .map(s => s.textContent.trim()).join(" ").replace(/\s+/g, " ").trim();
    if (!text) { lastRawText = ""; return; }
    if (text === lastRawText) return;
    lastRawText = text;
    handleCaptionUpdate(text);
  }

  function init() {
    findVideoElement(); injectPill(); loadSettings();
    new MutationObserver(readCaptions).observe(document.body, { childList: true, subtree: true, characterData: true });
    document.addEventListener("yt-navigate-start", resetSession);
    document.addEventListener("yt-navigate-finish", () => { resetSession(); findVideoElement(); injectPill(); if (isEnabled) autoEnableCaptions(); });
    if (typeof chrome !== "undefined") chrome.storage?.onChanged?.addListener((changes, area) => {
      if (area === "sync") {
        if (changes.sourceLanguage || changes.apiKey || changes.backendUrl) {
          retryUntil = 0; failureCount = 0; serviceMessage = "";
        }
        resetSession(); loadSettings();
      }
    });
    setInterval(() => {
      findVideoElement(); injectPill();
      if (currentJob && stale(currentJob)) finishAudio(currentJob);
      pump(); readCaptions(); updatePillUI();
    }, 200);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
