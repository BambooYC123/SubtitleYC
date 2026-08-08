const params = new URLSearchParams(window.location.search);
let sessionId = params.get("session") || params.get("session_id") || "";
let initialTime = Number(params.get("time") || params.get("time_seconds") || 0);
const PREVIEW_PLAYBACK_FPS = 8;
const PREVIEW_SCRUB_SYNC_MS = 80;
const CUE_BOUNDARY_EPSILON_SECONDS = 0.000001;
const EDITOR_SUBTITLE_FORMAT = "srt";
const SUBTITLE_OVERLAY_POSITION_STORAGE_KEY = "subtitleyc:subtitle-overlay-position";
const reportedFrontendCrashes = new Set();

function normalizeCrashText(value) {
  if (value instanceof Error) return value.stack || value.message || String(value);
  if (value && typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value || "Unknown frontend error");
}

function reportFrontendCrash(source, value) {
  const stack = normalizeCrashText(value);
  const key = `${source}:${stack.slice(0, 600)}`;
  if (reportedFrontendCrashes.has(key)) return;
  reportedFrontendCrashes.add(key);
  fetch("/api/crashes/frontend", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source,
      message: stack.split("\n")[0] || source,
      stack,
      url: window.location.href,
      user_agent: navigator.userAgent,
    }),
    keepalive: true,
  }).catch(() => undefined);
}

window.addEventListener("error", (event) => {
  reportFrontendCrash("subtitle-editor-error", event.error || event.message);
});
window.addEventListener("unhandledrejection", (event) => {
  reportFrontendCrash("subtitle-editor-unhandledrejection", event.reason);
});

const state = {
  session: null,
  cues: [],
  subtitleFormat: "srt",
  subtitleUrl: null,
  subtitleFilename: "subtitles.srt",
  selectedIndex: -1,
  activeIndex: -1,
  dirty: false,
  undoStack: [],
  redoStack: [],
  historyLimit: 100,
  suppressSlider: false,
  fallbackTime: Math.max(0, Number(initialTime || 0)),
  fallbackFrameIndex: null,
  fallbackImageToken: 0,
  useFrameFallback: false,
  nativePreviewReady: false,
  nativePreviewVisible: null,
  useNativePreview: false,
  previewPlaying: false,
  previewScrubbing: false,
  previewScrubWasPlaying: false,
  previewScrubSyncTimer: null,
  previewScrubPending: false,
  previewScrubLastSyncAt: 0,
  previewScrubUiFrame: null,
  previewTimer: null,
  fallbackProbeTimer: 0,
  videoUploadActive: false,
  library: null,
};

const elements = {
  status: document.querySelector("#editorStatus"),
  videoTitle: document.querySelector("#videoTitle"),
  timeIndicator: document.querySelector("#timeIndicator"),
  videoFrame: document.querySelector(".video-frame"),
  video: document.querySelector("#editorVideo"),
  frameFallback: document.querySelector("#editorFrameFallback"),
  subtitleOverlay: document.querySelector("#subtitleOverlay"),
  playButton: document.querySelector("#playButton"),
  prevFrameButton: document.querySelector("#prevFrameButton"),
  nextFrameButton: document.querySelector("#nextFrameButton"),
  seekSlider: document.querySelector("#seekSlider"),
  prevSubtitleButton: document.querySelector("#prevSubtitleButton"),
  nextSubtitleButton: document.querySelector("#nextSubtitleButton"),
  frameStepInput: document.querySelector("#frameStepInput"),
  visibleStartBackButton: document.querySelector("#visibleStartBackButton"),
  visibleStartForwardButton: document.querySelector("#visibleStartForwardButton"),
  visibleEndBackButton: document.querySelector("#visibleEndBackButton"),
  visibleEndForwardButton: document.querySelector("#visibleEndForwardButton"),
  cueCount: document.querySelector("#cueCount"),
  cueMeta: document.querySelector("#cueMeta"),
  cueList: document.querySelector("#cueList"),
  startInput: document.querySelector("#startInput"),
  endInput: document.querySelector("#endInput"),
  textInput: document.querySelector("#textInput"),
  cueForm: document.querySelector("#cueForm"),
  applyCueButton: document.querySelector("#applyCueButton"),
  addCueButton: document.querySelector("#addCueButton"),
  deleteCueButton: document.querySelector("#deleteCueButton"),
  undoButton: document.querySelector("#undoButton"),
  redoButton: document.querySelector("#redoButton"),
  saveButton: document.querySelector("#saveButton"),
  downloadButton: document.querySelector("#downloadButton"),
  reloadButton: document.querySelector("#reloadButton"),
  videoUploadButton: document.querySelector("#videoUploadButton"),
  videoKeepCopyInput: document.querySelector("#videoKeepCopyInput"),
  videoInput: document.querySelector("#videoInput"),
  previousButton: document.querySelector("#previousButton"),
  uploadButton: document.querySelector("#uploadButton"),
  subtitleImportInput: document.querySelector("#subtitleImportInput"),
  libraryOverlay: document.querySelector("#libraryOverlay"),
  libraryDrawer: document.querySelector("#libraryDrawer"),
  libraryCloseButton: document.querySelector("#libraryCloseButton"),
  libraryRefreshButton: document.querySelector("#libraryRefreshButton"),
  libraryVideoList: document.querySelector("#libraryVideoList"),
  librarySubtitleList: document.querySelector("#librarySubtitleList"),
  libraryMeta: document.querySelector("#libraryMeta"),
};

function setStatus(message, ok = true) {
  elements.status.textContent = message;
  elements.status.title = message;
  elements.status.style.color = ok ? "" : "#b42318";
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = response.statusText || `HTTP ${response.status}`;
    try {
      const payload = await response.json();
      message = payload.detail || payload.message || message;
    } catch (_error) {
      // Keep the HTTP message.
    }
    throw new Error(message);
  }
  return response.status === 204 ? {} : response.json();
}

function normalizedTheme(value) {
  return value === "light" ? "light" : "dark";
}

function syncShellTheme(theme) {
  const normalized = normalizedTheme(theme || document.documentElement.dataset.theme || "dark");
  window.subtitleycPendingShellTheme = normalized;
  const setShellTheme = window.pywebview?.api?.set_shell_theme;
  if (setShellTheme) {
    setShellTheme(normalized).catch(() => {});
  }
}

function applyTheme(theme, options = {}) {
  const normalized = normalizedTheme(theme);
  document.documentElement.dataset.theme = normalized;
  document.documentElement.style.colorScheme = normalized;
  if (options.syncShell !== false) syncShellTheme(normalized);
}

function applyUiLanguage(language, options = {}) {
  const normalized = window.SubtitleYCI18n?.set(language, { broadcast: options.broadcast !== false }) || "en";
  if (options.syncShell !== false) {
    const setShellLanguage = window.pywebview?.api?.set_shell_language;
    if (setShellLanguage) setShellLanguage(normalized).catch(() => {});
  }
  return normalized;
}

window.subtitleycApplyExternalTheme = (theme) => applyTheme(theme, { syncShell: false });
window.subtitleycApplyExternalLanguage = (language) => applyUiLanguage(language, { syncShell: false, broadcast: false });
window.addEventListener("pywebviewready", () => syncShellTheme(window.subtitleycPendingShellTheme || document.documentElement.dataset.theme || "dark"));
window.addEventListener("subtitleyc-language-changed", () => {
  renderCueList();
  if (state.library) renderLibrary(state.library);
});
window.addEventListener("storage", (event) => {
  if (event.key === SUBTITLE_OVERLAY_POSITION_STORAGE_KEY) {
    applySubtitleOverlayPosition();
    requestNativePreviewSurfaceSync();
    return;
  }

  if (event.key === "subtitleyc:theme-updated") {
    try {
      const payload = JSON.parse(event.newValue || "{}");
      if (payload.theme) applyTheme(payload.theme, { syncShell: false });
    } catch (_error) {
      // Ignore malformed cross-tab theme updates.
    }
    return;
  }

  if (event.key === "subtitleyc:subtitle-format-updated") {
    try {
      applyExternalSubtitleFormat(JSON.parse(event.newValue || "{}"));
    } catch (_error) {
      // Ignore malformed cross-tab format updates.
    }
  }
});

async function loadAppearance() {
  try {
    const payload = await fetchJson("/api/settings");
    applyTheme(payload.settings?.theme || payload.defaults?.theme || "dark");
    applyUiLanguage(payload.settings?.ui_language || payload.defaults?.ui_language || "en");
  } catch (_error) {
    applyTheme("dark");
    applyUiLanguage("en");
  }
}
function fps() {
  return Math.max(1, Number(state.session?.metadata?.fps || 24));
}

function frameSeconds() {
  return 1 / fps();
}

function duration() {
  return Math.max(0, Number(state.session?.metadata?.duration || elements.video.duration || 0));
}

function frameCount() {
  const explicit = Number(state.session?.metadata?.frame_count || 0);
  if (explicit > 0) return explicit;
  return Math.max(1, Math.round(duration() * fps()));
}

function currentTime() {
  if (state.useNativePreview || state.useFrameFallback) return Math.max(0, Number(state.fallbackTime || 0));
  return Math.max(0, Number(elements.video.currentTime || state.fallbackTime || 0));
}

function frameIndexForTime(seconds) {
  return Math.max(0, Math.min(frameCount() - 1, Math.round(Math.max(0, Number(seconds || 0)) * fps())));
}

function timeForFrame(frameIndex) {
  return Math.max(0, Number(frameIndex || 0)) / fps();
}

function clampTime(seconds) {
  return Math.max(0, Math.min(duration() || Number.MAX_SAFE_INTEGER, Number(seconds || 0)));
}

function sameCueBoundaryTime(a, b) {
  return Math.abs(Number(a || 0) - Number(b || 0)) <= CUE_BOUNDARY_EPSILON_SECONDS;
}

function framePreviewUrl(seconds = currentTime(), frameIndex = frameIndexForTime(seconds)) {
  return `/api/videos/${encodeURIComponent(sessionId)}/frame?frame_index=${encodeURIComponent(frameIndex)}`;
}

function updateFrameFallback(seconds = currentTime()) {
  if (!elements.frameFallback || !sessionId || state.useNativePreview) return;
  const frameIndex = frameIndexForTime(seconds);
  if (state.fallbackFrameIndex === frameIndex && elements.frameFallback.getAttribute("src")) return;
  const url = framePreviewUrl(seconds, frameIndex);
  const token = ++state.fallbackImageToken;
  const image = new Image();
  image.onload = () => {
    if (token !== state.fallbackImageToken) return;
    elements.frameFallback.src = url;
    state.fallbackFrameIndex = frameIndex;
  };
  image.onerror = () => {
    if (token === state.fallbackImageToken) setStatus("Could not load preview frame", false);
  };
  image.src = url;
}

function setFrameFallback(enabled, message = "") {
  if (enabled && state.useNativePreview) return;
  state.useFrameFallback = Boolean(enabled);
  if (elements.frameFallback) {
    elements.frameFallback.hidden = !state.useFrameFallback;
    if (state.useFrameFallback) updateFrameFallback();
  }
  elements.video.classList.toggle("is-hidden", state.useFrameFallback || state.useNativePreview);
  if (message) setStatus(message);
  updateTransportState();
}

function nativePreviewApi() {
  return window.pywebview?.api?.update_native_preview || null;
}

function setNativePreviewVisible(visible) {
  const setVisible = window.pywebview?.api?.set_native_preview_visible;
  if (!setVisible) return false;
  const nextVisible = Boolean(visible);
  if (state.nativePreviewVisible === nextVisible) return true;
  state.nativePreviewVisible = nextVisible;
  setVisible(nextVisible).catch(() => {
    state.nativePreviewVisible = null;
  });
  return true;
}

function setNativePreviewEnabled(enabled) {
  const next = Boolean(enabled && nativePreviewApi());
  if (state.useNativePreview === next) {
    if (next) setNativePreviewVisible(true);
    return;
  }
  state.useNativePreview = next;
  elements.videoFrame.classList.toggle("is-native", next);
  if (next) {
    elements.video.pause();
    elements.video.classList.add("is-hidden");
    if (elements.frameFallback) elements.frameFallback.hidden = true;
    elements.subtitleOverlay.hidden = true;
    setNativePreviewVisible(true);
  } else {
    setNativePreviewVisible(false);
    elements.video.classList.toggle("is-hidden", state.useFrameFallback);
  }
  updateTransportState();
}

function activeSubtitleText() {
  const { cue } = cueAtTime(currentTime());
  return cue?.text?.trim() || "";
}

function clampSubtitleOverlayValue(value, min, max) {
  if (!Number.isFinite(value)) return min;
  return Math.max(min, Math.min(max, value));
}

function normalizeSubtitleOverlayPosition(position) {
  if (!position || typeof position !== "object") return null;
  const left = clampSubtitleOverlayValue(Number(position.left), 0, 1);
  const top = clampSubtitleOverlayValue(Number(position.top), 0, 1);
  return { left, top };
}

function storedSubtitleOverlayPosition() {
  try {
    return normalizeSubtitleOverlayPosition(JSON.parse(localStorage.getItem(SUBTITLE_OVERLAY_POSITION_STORAGE_KEY) || "null"));
  } catch (_error) {
    return null;
  }
}

function saveSubtitleOverlayPosition(position, options = {}) {
  const next = normalizeSubtitleOverlayPosition(position);
  if (!next) return;
  try {
    localStorage.setItem(SUBTITLE_OVERLAY_POSITION_STORAGE_KEY, JSON.stringify(next));
  } catch (_error) {
    // Keep the current native drag usable even if storage is unavailable.
  }
  applySubtitleOverlayPosition();
  if (options.sync !== false) requestNativePreviewSurfaceSync();
}

function subtitleOverlayPositionPayload() {
  return storedSubtitleOverlayPosition();
}

function applySubtitleOverlayPosition() {
  const overlay = elements.subtitleOverlay;
  const container = elements.videoFrame;
  if (!overlay || overlay.hidden || !container) return;
  const position = storedSubtitleOverlayPosition();
  if (!position) return;
  requestAnimationFrame(() => {
    if (overlay.hidden) return;
    const containerRect = container.getBoundingClientRect();
    const overlayRect = overlay.getBoundingClientRect();
    const maxLeft = Math.max(0, containerRect.width - overlayRect.width);
    const maxTop = Math.max(0, containerRect.height - overlayRect.height);
    overlay.style.left = `${Math.round(position.left * maxLeft)}px`;
    overlay.style.right = "auto";
    overlay.style.top = `${Math.round(position.top * maxTop)}px`;
    overlay.style.bottom = "auto";
  });
}

function setupDraggableSubtitleOverlay() {
  const overlay = elements.subtitleOverlay;
  const container = elements.videoFrame;
  if (!overlay || !container) return;

  overlay.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || overlay.hidden) return;
    event.preventDefault();
    event.stopPropagation();
    const containerRect = container.getBoundingClientRect();
    const overlayRect = overlay.getBoundingClientRect();
    const offsetX = event.clientX - overlayRect.left;
    const offsetY = event.clientY - overlayRect.top;
    overlay.classList.add("is-dragging");
    overlay.setPointerCapture?.(event.pointerId);

    const move = (moveEvent) => {
      const currentRect = overlay.getBoundingClientRect();
      const maxLeft = Math.max(0, containerRect.width - currentRect.width);
      const maxTop = Math.max(0, containerRect.height - currentRect.height);
      const left = clampSubtitleOverlayValue(moveEvent.clientX - containerRect.left - offsetX, 0, maxLeft);
      const top = clampSubtitleOverlayValue(moveEvent.clientY - containerRect.top - offsetY, 0, maxTop);
      overlay.style.left = `${Math.round(left)}px`;
      overlay.style.right = "auto";
      overlay.style.top = `${Math.round(top)}px`;
      overlay.style.bottom = "auto";
    };

    const stop = () => {
      overlay.classList.remove("is-dragging");
      overlay.releasePointerCapture?.(event.pointerId);
      overlay.removeEventListener("pointermove", move);
      overlay.removeEventListener("pointerup", stop);
      overlay.removeEventListener("pointercancel", stop);
      const currentRect = overlay.getBoundingClientRect();
      const maxLeft = Math.max(0, containerRect.width - currentRect.width);
      const maxTop = Math.max(0, containerRect.height - currentRect.height);
      saveSubtitleOverlayPosition({
        left: maxLeft > 0 ? (currentRect.left - containerRect.left) / maxLeft : 0.5,
        top: maxTop > 0 ? (currentRect.top - containerRect.top) / maxTop : 1,
      });
    };

    overlay.addEventListener("pointermove", move);
    overlay.addEventListener("pointerup", stop);
    overlay.addEventListener("pointercancel", stop);
  });
}
function nativePreviewOccluders() {
  return [elements.libraryDrawer]
    .filter((element) => element && !element.hidden)
    .map((element) => {
      const rect = element.getBoundingClientRect();
      return {
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: rect.height,
      };
    })
    .filter((rect) => rect.width > 0 && rect.height > 0);
}

function nativePreviewPayload() {
  const rect = elements.videoFrame.getBoundingClientRect();
  return {
    session_id: sessionId,
    rect: {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
    },
    time_seconds: currentTime(),
    cache_mode: state.previewScrubbing ? "active" : "idle",
    crop: null,
    show_crop: false,
    subtitle_text: activeSubtitleText(),
    subtitle_box: subtitleOverlayPositionPayload(),
    occluders: nativePreviewOccluders(),
  };
}

function syncNativePreviewSurface() {
  const api = nativePreviewApi();
  if (!api) return false;
  if (!state.session) {
    setNativePreviewVisible(false);
    return true;
  }
  const rect = elements.videoFrame.getBoundingClientRect();
  if (rect.width <= 1 || rect.height <= 1) return true;
  setNativePreviewEnabled(true);
  api(nativePreviewPayload()).catch((error) => {
    setNativePreviewEnabled(false);
    if (state.nativePreviewReady) setStatus(error.message || "Native preview failed", false);
  });
  return true;
}

function requestNativePreviewSurfaceSync() {
  syncNativePreviewSurface();
  requestAnimationFrame(() => syncNativePreviewSurface());
}

function cancelPreviewScrubSync() {
  if (state.previewScrubSyncTimer) {
    window.clearTimeout(state.previewScrubSyncTimer);
    state.previewScrubSyncTimer = null;
  }
  state.previewScrubPending = false;
  cancelPreviewScrubUi();
}

function cancelPreviewScrubUi() {
  if (state.previewScrubUiFrame !== null) {
    window.cancelAnimationFrame(state.previewScrubUiFrame);
    state.previewScrubUiFrame = null;
  }
}

function schedulePreviewScrubUi() {
  if (state.previewScrubUiFrame !== null) return;
  state.previewScrubUiFrame = window.requestAnimationFrame(() => {
    state.previewScrubUiFrame = null;
    if (!state.session) return;
    const current = currentTime();
    const totalFrames = frameCount();
    const frame = frameIndexForTime(current);
    elements.timeIndicator.textContent =
      "Frame: " + Math.min(totalFrames, frame + 1) + " / " + totalFrames +
      " | Time: " + formatTime(current) + " / " + formatTime(duration());
  });
}

function schedulePreviewScrubSync() {
  state.previewScrubPending = true;
  if (state.previewScrubSyncTimer) return;
  const elapsed = performance.now() - Number(state.previewScrubLastSyncAt || 0);
  const delay = Math.max(0, PREVIEW_SCRUB_SYNC_MS - elapsed);
  state.previewScrubSyncTimer = window.setTimeout(() => {
    state.previewScrubSyncTimer = null;
    state.previewScrubPending = false;
    state.previewScrubLastSyncAt = performance.now();
    syncNativePreviewSurface();
  }, delay);
}

function syncPreviewSurfaceForCurrentTime(options = {}) {
  if (state.useNativePreview && state.previewScrubbing && !options.immediate) {
    schedulePreviewScrubSync();
    return;
  }
  syncNativePreviewSurface();
}

function flushPreviewScrubSync() {
  cancelPreviewScrubSync();
  state.previewScrubLastSyncAt = performance.now();
  syncNativePreviewSurface();
}

window.subtitleycSyncNativePreview = syncNativePreviewSurface;

function frameStepFrames() {
  const value = Math.abs(Number(elements.frameStepInput.value || 1));
  return Number.isFinite(value) && value > 0 ? value : 1;
}

function formatTime(seconds) {
  const safe = Math.max(0, Number(seconds || 0));
  const minutes = Math.floor(safe / 60);
  const secs = Math.floor(safe % 60);
  const millis = Math.round((safe - Math.floor(safe)) * 1000);
  return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}.${String(millis).padStart(3, "0")}`;
}

function subtitleFormatLabel(_format) {
  return "SRT";
}
function subtitleExtension(_format = EDITOR_SUBTITLE_FORMAT) {
  return EDITOR_SUBTITLE_FORMAT;
}

function cleanSubtitleStem(value) {
  return String(value || "subtitles")
    .replace(/\.[^.\\/]+$/, "")
    .replace(/[<>:"/\\|?*\x00-\x1f]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\s+-\s+subtitles$/i, "")
    .trim() || "subtitles";
}

function defaultSubtitleFilename() {
  return `${cleanSubtitleStem(state.session?.original_name || "subtitles")} - subtitles.srt`;
}

function srtSubtitleFilename(filename = defaultSubtitleFilename()) {
  return `${cleanSubtitleStem(filename || "subtitles")} - subtitles.srt`;
}

function editorSubtitleDownloadUrl() {
  return sessionId ? `/api/videos/${encodeURIComponent(sessionId)}/subtitle.srt` : state.subtitleUrl;
}

function updateDownloadButton() {
  if (!elements.downloadButton) return;
  elements.downloadButton.textContent = "Download .srt";
  elements.downloadButton.disabled = state.dirty || !state.subtitleUrl;
  elements.downloadButton.title = state.dirty ? "Save changes before downloading" : "Download the saved SRT file";
}

function applySubtitleDownloadPayload(payload = {}) {
  state.subtitleFormat = EDITOR_SUBTITLE_FORMAT;
  const nextUrl = payload.subtitle_url || payload.srt_url || state.subtitleUrl || null;
  state.subtitleUrl = nextUrl && sessionId ? editorSubtitleDownloadUrl() : nextUrl;
  state.subtitleFilename = srtSubtitleFilename(payload.subtitle_filename || state.subtitleFilename || defaultSubtitleFilename());
  updateDownloadButton();
}

function applyExternalSubtitleFormat(payload = {}) {
  const payloadSessionId = String(payload.sessionId || "");
  if (payloadSessionId && sessionId && payloadSessionId !== sessionId) return;
  const previousUrl = state.subtitleUrl;
  const sameSession = Boolean(sessionId) && (!payloadSessionId || payloadSessionId === sessionId);
  state.subtitleFormat = EDITOR_SUBTITLE_FORMAT;
  if (sameSession && (payload.subtitle_url || payload.srt_url || state.subtitleUrl)) {
    state.subtitleUrl = editorSubtitleDownloadUrl();
  } else if (!sameSession) {
    state.subtitleUrl = null;
  }
  state.subtitleFilename = srtSubtitleFilename(payload.subtitle_filename || payload.subtitleFilename || state.subtitleFilename || defaultSubtitleFilename());
  if (state.cues.length && previousUrl !== state.subtitleUrl) {
    markDirty();
  } else if (state.dirty) {
    markDirty();
  } else {
    setClean();
  }
  updateDownloadButton();
}

function applyStoredSubtitleFormat() {
  try {
    const payload = JSON.parse(localStorage.getItem("subtitleyc:subtitle-format-updated") || "{}");
    applyExternalSubtitleFormat(payload);
  } catch (_error) {
    // Ignore malformed cross-tab format updates.
  }
}

function publishEditorSessionUpdate(reason = "video") {
  if (!sessionId) return;
  try {
    localStorage.setItem(
      "subtitleyc:editor-session-updated",
      JSON.stringify({ sessionId, reason, hasSubtitles: Boolean(state.subtitleUrl), at: Date.now() })
    );
  } catch (_error) {
    // Cross-tab sync is best-effort.
  }
}

function publishSubtitleUpdated() {
  if (!sessionId) return;
  try {
    localStorage.setItem("subtitleyc:subtitle-updated", JSON.stringify({ sessionId, at: Date.now() }));
  } catch (_error) {
    // Cross-tab sync is best-effort.
  }
  publishEditorSessionUpdate("subtitles");
}

function normalizeCue(raw) {
  const start = Math.max(0, Number(raw.start_seconds || 0));
  const end = Math.max(start + 0.001, Number(raw.end_seconds || start + 0.001));
  return { start_seconds: start, end_seconds: end, text: String(raw.text || "") };
}

function cloneCue(cue) {
  return {
    start_seconds: Math.max(0, Number(cue?.start_seconds || 0)),
    end_seconds: Math.max(0.001, Number(cue?.end_seconds || 0.001)),
    text: String(cue?.text || ""),
  };
}

function cueSnapshot() {
  return {
    cues: state.cues.map(cloneCue),
    selectedIndex: state.selectedIndex,
    subtitleFormat: state.subtitleFormat,
  };
}

function updateHistoryButtons() {
  if (elements.undoButton) elements.undoButton.disabled = state.undoStack.length === 0;
  if (elements.redoButton) elements.redoButton.disabled = state.redoStack.length === 0;
}

function resetHistory() {
  state.undoStack = [];
  state.redoStack = [];
  updateHistoryButtons();
}

function pushHistory() {
  state.undoStack.push(cueSnapshot());
  if (state.undoStack.length > state.historyLimit) {
    state.undoStack.shift();
  }
  state.redoStack = [];
  updateHistoryButtons();
}

function restoreHistory(snapshot) {
  if (!snapshot) return;
  state.cues = (snapshot.cues || []).map(normalizeCue).sort((a, b) => a.start_seconds - b.start_seconds || a.end_seconds - b.end_seconds);
  state.subtitleFormat = snapshot.subtitleFormat || state.subtitleFormat || "srt";
  const snapshotIndex = Number(snapshot.selectedIndex);
  state.selectedIndex = snapshotIndex >= 0 ? Math.min(snapshotIndex, state.cues.length - 1) : -1;
  if (!state.cues.length) state.selectedIndex = -1;
  renderCueList();
  if (state.selectedIndex >= 0) selectCue(state.selectedIndex);
  markDirty();
  updatePreview();
}

function undoEdit() {
  if (!state.undoStack.length) return;
  state.redoStack.push(cueSnapshot());
  restoreHistory(state.undoStack.pop());
  updateHistoryButtons();
  setStatus("Undid subtitle edit");
}

function redoEdit() {
  if (!state.redoStack.length) return;
  state.undoStack.push(cueSnapshot());
  restoreHistory(state.redoStack.pop());
  updateHistoryButtons();
  setStatus("Redid subtitle edit");
}

function shouldUseHistoryShortcut(event) {
  if (!(event.ctrlKey || event.metaKey) || event.altKey) return false;
  const key = event.key.toLowerCase();
  if (key !== "z" && key !== "y") return false;
  const target = event.target;
  return !target?.closest?.("input, textarea, select, [contenteditable]");
}
function shortcutTargetIsEditable(event) {
  return Boolean(event.target?.closest?.("input, textarea, select, button, a, [contenteditable]"));
}

function handleEditorKeyboardShortcut(event) {
  const key = event.key.toLowerCase();
  const command = event.ctrlKey || event.metaKey;

  if (command && !event.altKey) {
    if (key === "s") {
      event.preventDefault();
      if (!elements.saveButton.disabled) saveCues().catch((error) => setStatus(error.message || "Save failed", false));
      return true;
    }
    if (key === "o") {
      event.preventDefault();
      if (!elements.videoUploadButton.disabled) chooseVideoFile().catch((error) => setStatus(error.message || "Open video failed", false));
      return true;
    }
    if (key === "u") {
      event.preventDefault();
      if (!elements.uploadButton.disabled) elements.subtitleImportInput.click();
      return true;
    }
    if (key === "r") {
      event.preventDefault();
      loadCues().catch((error) => setStatus(error.message || "Reload failed", false));
      return true;
    }
  }

  if (shortcutTargetIsEditable(event) || !state.session) {
    return false;
  }

  if (event.key === " " || event.code === "Space") {
    event.preventDefault();
    togglePreviewPlayback();
    return true;
  }

  if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
    event.preventDefault();
    if (event.shiftKey) {
      if (event.key === "ArrowLeft") jumpToPreviousSubtitleBoundary();
      else jumpToNextSubtitleBoundary();
    } else {
      seekFrame(event.key === "ArrowLeft" ? -1 : 1);
    }
    return true;
  }

  if (event.key === "Delete" && state.selectedIndex >= 0) {
    event.preventDefault();
    deleteSelectedCue();
    return true;
  }

  return false;
}

function sortCues() {
  state.cues.sort((a, b) => a.start_seconds - b.start_seconds || a.end_seconds - b.end_seconds);
}

function cueAtTime(time, preferredIndex = state.selectedIndex) {
  const current = Number(time || 0);
  const preferredCue = state.cues[preferredIndex];

  if (preferredCue && sameCueBoundaryTime(preferredCue.start_seconds, current)) {
    return { cue: preferredCue, index: preferredIndex };
  }

  for (let index = 0; index < state.cues.length; index += 1) {
    const cue = state.cues[index];
    if (sameCueBoundaryTime(cue.start_seconds, current)) {
      return { cue, index };
    }
  }

  if (preferredCue && preferredCue.start_seconds < current && current < preferredCue.end_seconds) {
    return { cue: preferredCue, index: preferredIndex };
  }

  for (let index = 0; index < state.cues.length; index += 1) {
    const cue = state.cues[index];
    if (cue.start_seconds < current && current < cue.end_seconds) {
      return { cue, index };
    }
  }

  const lastIndex = state.cues.length - 1;
  const lastCue = state.cues[lastIndex];
  if (lastCue && sameCueBoundaryTime(lastCue.end_seconds, current)) {
    return { cue: lastCue, index: lastIndex };
  }

  return { cue: null, index: -1 };
}

function markDirty() {
  state.dirty = true;
  elements.saveButton.disabled = false;
  elements.cueMeta.textContent = `${subtitleFormatLabel(state.subtitleFormat)} - Unsaved`;
  updateDownloadButton();
  updateHistoryButtons();
}

function setClean() {
  state.dirty = false;
  elements.saveButton.disabled = true;
  elements.cueMeta.textContent = subtitleFormatLabel(state.subtitleFormat);
  updateDownloadButton();
  updateHistoryButtons();
}

function renderCueList() {
  elements.cueCount.textContent = `${state.cues.length} ${state.cues.length === 1 ? "cue" : "cues"}`;
  elements.cueList.replaceChildren();
  if (!state.cues.length) {
    const empty = document.createElement("div");
    empty.className = "cue-empty";
    empty.textContent = "No subtitle cues loaded";
    elements.cueList.appendChild(empty);
    updateFormState();
    return;
  }
  state.cues.forEach((cue, index) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "cue-row";
    row.dataset.index = String(index);
    row.setAttribute("role", "option");

    const number = document.createElement("span");
    number.className = "cue-number";
    number.textContent = String(index + 1).padStart(3, "0");
    const main = document.createElement("span");
    main.className = "cue-main";
    const time = document.createElement("span");
    time.className = "cue-time";
    time.textContent = `${formatTime(cue.start_seconds)} -> ${formatTime(cue.end_seconds)}`;
    const text = document.createElement("span");
    text.className = "cue-text";
    text.textContent = cue.text.trim() || "Empty subtitle";
    main.append(time, text);
    row.append(number, main);
    row.addEventListener("click", () => selectCue(index, { seek: true }));
    elements.cueList.appendChild(row);
  });
  updateCueRowStates({ scroll: true });
}

function updateCueRowStates(options = {}) {
  elements.cueList.querySelectorAll(".cue-row").forEach((row) => {
    const index = Number(row.dataset.index || -1);
    const selected = index === state.selectedIndex;
    row.classList.toggle("is-selected", selected);
    row.classList.toggle("is-active", index === state.activeIndex);
    row.setAttribute("aria-selected", selected ? "true" : "false");
  });
  if (options.scroll) scrollActiveCueIntoView();
  updateFormState();
}

function updateFormState() {
  const cue = state.cues[state.selectedIndex];
  const hasCue = Boolean(cue);
  elements.applyCueButton.disabled = !hasCue;
  elements.deleteCueButton.disabled = !hasCue;
  elements.startInput.disabled = !hasCue;
  elements.endInput.disabled = !hasCue;
  elements.textInput.disabled = !hasCue;
  if (!hasCue) {
    elements.startInput.value = "";
    elements.endInput.value = "";
    elements.textInput.value = "";
  }
}

function selectCue(index, options = {}) {
  if (index < 0 || index >= state.cues.length) {
    state.selectedIndex = -1;
    updateCueRowStates({ scroll: true });
    return;
  }
  state.selectedIndex = index;
  const cue = state.cues[index];
  elements.startInput.value = cue.start_seconds.toFixed(3);
  elements.endInput.value = cue.end_seconds.toFixed(3);
  elements.textInput.value = cue.text;
  if (options.seek) {
    seekTo(cue.start_seconds);
  } else {
    updateCueRowStates({ scroll: true });
  }
}

function scrollActiveCueIntoView() {
  const index = state.selectedIndex >= 0 ? state.selectedIndex : state.activeIndex;
  if (index < 0) return;
  const row = elements.cueList.querySelector(`[data-index="${index}"]`);
  row?.scrollIntoView({ block: "nearest" });
}

function updateTransportState() {
  const hasVideo = Boolean(state.session);
  const hasCues = state.cues.length > 0;
  const visibleCue = hasVideo && cueAtTime(currentTime()).index >= 0;
  elements.videoUploadButton.disabled = state.videoUploadActive;
  if (elements.videoKeepCopyInput) elements.videoKeepCopyInput.disabled = state.videoUploadActive;
  elements.previousButton.disabled = state.videoUploadActive;
  elements.reloadButton.disabled = !hasVideo;
  elements.playButton.disabled = !hasVideo;
  elements.prevFrameButton.disabled = !hasVideo;
  elements.nextFrameButton.disabled = !hasVideo;
  elements.seekSlider.disabled = !hasVideo;
  elements.prevSubtitleButton.disabled = !hasVideo || !hasCues;
  elements.nextSubtitleButton.disabled = !hasVideo || !hasCues;
  elements.visibleStartBackButton.disabled = !visibleCue;
  elements.visibleStartForwardButton.disabled = !visibleCue;
  elements.visibleEndBackButton.disabled = !visibleCue;
  elements.visibleEndForwardButton.disabled = !visibleCue;
  elements.addCueButton.disabled = !hasVideo;
  elements.uploadButton.disabled = !hasVideo;
}

function updatePreview() {
  if (!state.session) {
    state.activeIndex = -1;
    state.fallbackTime = 0;
    elements.timeIndicator.textContent = "Frame: 0 / 0 | Time: 00:00.000 / 00:00.000";
    elements.seekSlider.value = "0";
    elements.seekSlider.max = "0";
    elements.subtitleOverlay.textContent = "";
    elements.subtitleOverlay.hidden = true;
    updateTransportState();
    updateCueRowStates({ scroll: false });
    return;
  }
  const previousActive = state.activeIndex;
  const current = currentTime();
  state.fallbackTime = current;
  if (state.useFrameFallback && !state.useNativePreview) updateFrameFallback(current);
  const totalFrames = frameCount();
  const frame = frameIndexForTime(current);
  elements.timeIndicator.textContent = `Frame: ${Math.min(totalFrames, frame + 1)} / ${totalFrames} | Time: ${formatTime(current)} / ${formatTime(duration())}`;
  if (!state.suppressSlider) {
    elements.seekSlider.value = String(current);
  }

  const { cue, index } = cueAtTime(current);
  state.activeIndex = index;
  const subtitleText = cue?.text?.trim() || "";
  if (subtitleText && !state.useNativePreview) {
    elements.subtitleOverlay.textContent = subtitleText;
    elements.subtitleOverlay.hidden = false;
    applySubtitleOverlayPosition();
  } else {
    elements.subtitleOverlay.textContent = "";
    elements.subtitleOverlay.hidden = true;
  }
  updateTransportState();
  if (state.useNativePreview) syncPreviewSurfaceForCurrentTime();
  if (previousActive !== state.activeIndex) updateCueRowStates({ scroll: true });
}

function applyCueForm(options = {}) {
  const cue = state.cues[state.selectedIndex];
  if (!cue) return false;
  const start = Math.max(0, Number(elements.startInput.value || cue.start_seconds));
  const end = Math.max(start + 0.001, Number(elements.endInput.value || cue.end_seconds));
  const text = elements.textInput.value.trim();
  const changed = !sameCueBoundaryTime(cue.start_seconds, start) || !sameCueBoundaryTime(cue.end_seconds, end) || cue.text !== text;
  if (!changed) return false;
  pushHistory();
  cue.start_seconds = start;
  cue.end_seconds = end;
  cue.text = text;
  const cueRef = cue;
  sortCues();
  state.selectedIndex = state.cues.indexOf(cueRef);
  markDirty();
  renderCueList();
  updatePreview();
  if (!options.silent) setStatus("Cue updated");
  return true;
}

function nudgeCue(index, boundary, frames) {
  const cue = state.cues[index];
  if (!cue) return;
  const delta = frames * frameSeconds();
  pushHistory();
  if (boundary === "start") {
    cue.start_seconds = Math.max(0, Math.min(cue.end_seconds - 0.001, cue.start_seconds + delta));
  } else {
    cue.end_seconds = Math.max(cue.start_seconds + 0.001, cue.end_seconds + delta);
  }
  state.selectedIndex = index;
  elements.startInput.value = cue.start_seconds.toFixed(3);
  elements.endInput.value = cue.end_seconds.toFixed(3);
  markDirty();
  renderCueList();
  updatePreview();
}

function nudgeVisible(boundary, frames) {
  const index = cueAtTime(currentTime()).index;
  if (index < 0) return;
  selectCue(index);
  nudgeCue(index, boundary, frames);
}

function stopPreviewPlayback(updateButton = true) {
  if (state.previewTimer) {
    window.clearInterval(state.previewTimer);
    state.previewTimer = null;
  }
  state.previewPlaying = false;
  if (updateButton) elements.playButton.textContent = "Play";
  if (!state.useNativePreview && !state.useFrameFallback) elements.video.pause();
}

function tickPreviewPlayback() {
  if (!state.previewPlaying || !state.session) return;
  const next = currentTime() + 1 / PREVIEW_PLAYBACK_FPS;
  if (duration() > 0 && next >= duration()) {
    seekTo(duration(), { keepPlaying: true });
    stopPreviewPlayback();
    return;
  }
  seekTo(next, { keepPlaying: true });
}

function startPreviewPlayback() {
  if (!state.session || duration() <= 0) return;
  state.previewPlaying = true;
  elements.playButton.textContent = "Pause";
  tickPreviewPlayback();
  state.previewTimer = window.setInterval(tickPreviewPlayback, Math.round(1000 / PREVIEW_PLAYBACK_FPS));
}

function togglePreviewPlayback() {
  if (state.useNativePreview || state.useFrameFallback) {
    if (state.previewPlaying) stopPreviewPlayback();
    else startPreviewPlayback();
    return;
  }
  if (elements.video.paused) {
    elements.video.play().catch((error) => setStatus(error.message || "Could not play video", false));
  } else {
    elements.video.pause();
  }
}

function previewIsPlaying() {
  if (state.useNativePreview || state.useFrameFallback) return Boolean(state.previewPlaying);
  return !elements.video.paused;
}

function resumePreviewPlayback() {
  if (state.useNativePreview || state.useFrameFallback) {
    startPreviewPlayback();
    return;
  }
  elements.video.play().catch((error) => setStatus(error.message || "Could not play video", false));
}

function beginPreviewScrub() {
  if (!state.session || state.previewScrubbing) return;
  state.previewScrubbing = true;
  state.previewScrubWasPlaying = previewIsPlaying();
  stopPreviewPlayback();
}

function finishPreviewScrub() {
  if (!state.previewScrubbing) return;
  const shouldResume = state.previewScrubWasPlaying;
  state.previewScrubbing = false;
  state.previewScrubWasPlaying = false;
  cancelPreviewScrubUi();
  updatePreview();
  cancelPreviewScrubSync();
  if (shouldResume && state.session && currentTime() < duration()) {
    resumePreviewPlayback();
  }
}
function seekTo(seconds, options = {}) {
  const target = clampTime(seconds);
  if (!options.keepPlaying) stopPreviewPlayback();
  state.fallbackTime = target;
  if (state.useNativePreview && state.previewScrubbing && !options.immediate) {
    schedulePreviewScrubUi();
    syncPreviewSurfaceForCurrentTime();
    return;
  }
  cancelPreviewScrubUi();
  if (!state.useNativePreview && !state.useFrameFallback) {
    try {
      elements.video.currentTime = target;
    } catch (_error) {
      setFrameFallback(true, "Using frame preview");
    }
  }
  if (state.useFrameFallback && !state.useNativePreview) updateFrameFallback(target);
  updatePreview();
}

function seekFrame(deltaFrames) {
  seekTo(timeForFrame(frameIndexForTime(currentTime()) + deltaFrames));
}

function jumpToNextSubtitleBoundary() {
  const current = currentTime();
  for (let index = 0; index < state.cues.length; index += 1) {
    const cue = state.cues[index];
    if (cue.start_seconds <= current && current < cue.end_seconds) {
      selectCue(index);
      seekTo(cue.end_seconds);
      return;
    }
    if (current < cue.start_seconds) {
      selectCue(index);
      seekTo(cue.start_seconds);
      return;
    }
  }
}

function jumpToPreviousSubtitleBoundary() {
  const current = currentTime();
  for (let index = state.cues.length - 1; index >= 0; index -= 1) {
    const cue = state.cues[index];
    if (cue.start_seconds < current && current <= cue.end_seconds) {
      selectCue(index);
      seekTo(cue.start_seconds);
      return;
    }
    if (cue.end_seconds < current) {
      selectCue(index);
      seekTo(cue.end_seconds);
      return;
    }
  }
}

function addCue() {
  const start = currentTime();
  const cue = { start_seconds: start, end_seconds: Math.min(duration() || start + 2, start + Math.max(1, frameSeconds())), text: "" };
  pushHistory();
  state.cues.push(cue);
  sortCues();
  state.selectedIndex = state.cues.indexOf(cue);
  markDirty();
  selectCue(state.selectedIndex);
  elements.textInput.focus();
}

function deleteSelectedCue() {
  if (state.selectedIndex < 0) return;
  pushHistory();
  state.cues.splice(state.selectedIndex, 1);
  state.selectedIndex = Math.min(state.selectedIndex, state.cues.length - 1);
  markDirty();
  renderCueList();
  if (state.selectedIndex >= 0) selectCue(state.selectedIndex);
  updatePreview();
}

function updateSessionUrl(timeSeconds = state.fallbackTime) {
  if (!sessionId) {
    window.history.replaceState(null, "", "/editor");
    return;
  }
  const params = new URLSearchParams({ session: sessionId, time: Number(timeSeconds || 0).toFixed(6) });
  window.history.replaceState(null, "", `/editor?${params.toString()}`);
}

function clearEditorSession() {
  stopPreviewPlayback(false);
  sessionId = "";
  state.session = null;
  state.cues = [];
  state.selectedIndex = -1;
  state.activeIndex = -1;
  state.subtitleUrl = null;
  state.subtitleFilename = defaultSubtitleFilename();
  state.fallbackTime = 0;
  state.fallbackFrameIndex = null;
  state.fallbackImageToken += 1;
  state.useFrameFallback = false;
  state.useNativePreview = false;
  elements.videoTitle.textContent = "No video loaded";
  elements.videoTitle.removeAttribute("title");
  elements.video.removeAttribute("src");
  elements.video.removeAttribute("poster");
  try {
    elements.video.load();
  } catch (_error) {
    // Browser media element may be unavailable during teardown.
  }
  if (elements.frameFallback) {
    elements.frameFallback.removeAttribute("src");
    elements.frameFallback.hidden = true;
  }
  setNativePreviewVisible(false);
  setClean();
  resetHistory();
  renderCueList();
  updatePreview();
  updateSessionUrl(0);
}

async function loadSession(session = null, options = {}) {
  let loadedSession = session;
  if (!loadedSession) {
    if (!sessionId) {
      clearEditorSession();
      if (!options.silentNoSession) setStatus("Upload a video or open Previous Projects");
      return null;
    }
    loadedSession = await fetchJson(`/api/videos/${encodeURIComponent(sessionId)}`);
  }
  if (!loadedSession?.id) {
    clearEditorSession();
    return null;
  }

  stopPreviewPlayback(false);
  setNativePreviewVisible(false);
  sessionId = String(loadedSession.id);
  state.session = loadedSession;
  state.cues = [];
  state.selectedIndex = -1;
  state.activeIndex = -1;
  state.subtitleFormat = EDITOR_SUBTITLE_FORMAT;
  state.subtitleUrl = loadedSession.subtitle_url || null;
  state.subtitleFilename = loadedSession.subtitle_filename || defaultSubtitleFilename();
  applySubtitleDownloadPayload(loadedSession);
  const videoTitle = loadedSession.original_name || "Video";
  elements.videoTitle.textContent = videoTitle;
  elements.videoTitle.title = videoTitle;
  const nextTime = clampTime(Number(options.time ?? initialTime ?? 0));
  initialTime = nextTime;
  state.fallbackTime = nextTime;
  state.fallbackFrameIndex = null;
  elements.video.poster = framePreviewUrl(state.fallbackTime);
  updateFrameFallback(state.fallbackTime);
  setFrameFallback(true);
  requestNativePreviewSurfaceSync();
  elements.video.src = `/api/videos/${encodeURIComponent(sessionId)}/media`;
  elements.seekSlider.max = String(duration());
  elements.seekSlider.step = "any";
  updateSessionUrl(state.fallbackTime);
  updateTransportState();
  window.clearTimeout(state.fallbackProbeTimer);
  state.fallbackProbeTimer = window.setTimeout(() => {
    if (!elements.video.videoWidth) setFrameFallback(true, "Using frame preview");
  }, 1200);
  return loadedSession;
}
async function loadCues(options = {}) {
  if (!sessionId) {
    state.cues = [];
    state.selectedIndex = -1;
    state.activeIndex = -1;
    setClean();
    resetHistory();
    renderCueList();
    updatePreview();
    if (!options.silent) setStatus("Load a video before loading subtitles", false);
    return null;
  }
  try {
    const payload = await fetchJson(`/api/videos/${encodeURIComponent(sessionId)}/subtitles`);
    state.subtitleFormat = EDITOR_SUBTITLE_FORMAT;
    applySubtitleDownloadPayload(payload);
    state.cues = (payload.cues || []).map(normalizeCue).sort((a, b) => a.start_seconds - b.start_seconds || a.end_seconds - b.end_seconds);
    state.selectedIndex = cueAtTime(currentTime()).index;
    setClean();
    resetHistory();
    renderCueList();
    if (state.selectedIndex >= 0) selectCue(state.selectedIndex);
    updatePreview();
    if (!options.silent) setStatus(`${state.cues.length} subtitle cues loaded`);
  } catch (error) {
    if (!options.silent) setStatus(error.message || "No subtitle cues loaded", false);
    state.cues = [];
    setClean();
    resetHistory();
    renderCueList();
    updatePreview();
  }
}

async function saveCues() {
  if (!sessionId) {
    setStatus("Load a video before saving subtitles", false);
    return;
  }
  applyCueForm({ silent: true });
  const payload = await fetchJson(`/api/videos/${encodeURIComponent(sessionId)}/subtitles`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subtitle_format: EDITOR_SUBTITLE_FORMAT, cues: state.cues.filter((cue) => cue.text.trim()) }),
  });
  state.subtitleFormat = EDITOR_SUBTITLE_FORMAT;
  applySubtitleDownloadPayload(payload);
  state.cues = (payload.cues || []).map(normalizeCue);
  setClean();
  renderCueList();
  updatePreview();
  publishSubtitleUpdated();
  setStatus(`Saved ${state.cues.length} cues`);
}

async function downloadSavedSubtitle() {
  if (!sessionId) {
    setStatus("Load a video before downloading subtitles", false);
    return;
  }
  if (state.dirty) {
    setStatus("Save changes before downloading", false);
    return;
  }
  const subtitleUrl = editorSubtitleDownloadUrl();
  const filename = srtSubtitleFilename(state.subtitleFilename || defaultSubtitleFilename());
  if (!subtitleUrl) {
    setStatus("No saved subtitle file is available", false);
    return;
  }
  const saveSubtitle = window.pywebview?.api?.save_subtitle || window.pywebview?.api?.save_srt;
  if (saveSubtitle) {
    const result = await saveSubtitle(subtitleUrl, filename);
    if (result?.ok) {
      setStatus(`Saved SRT to ${result.path}`);
    } else if (result?.cancelled) {
      setStatus("Subtitle save cancelled");
    } else {
      setStatus(result?.message || "Could not save subtitle file", false);
    }
    return;
  }
  const link = document.createElement("a");
  link.href = subtitleUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setStatus(`Downloading ${filename}`);
}
async function importSubtitleFile(file) {
  if (!file) return;
  if (!sessionId) {
    setStatus("Load a video before uploading subtitles", false);
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  const payload = await fetchJson(`/api/videos/${encodeURIComponent(sessionId)}/subtitles/import`, {
    method: "POST",
    body: formData,
  });
  state.subtitleFormat = EDITOR_SUBTITLE_FORMAT;
  applySubtitleDownloadPayload(payload);
  state.cues = (payload.cues || []).map(normalizeCue);
  state.selectedIndex = cueAtTime(currentTime()).index;
  setClean();
  resetHistory();
  renderCueList();
  updatePreview();
  publishSubtitleUpdated();
  setStatus(`Loaded ${state.cues.length} cues from ${file.name}`);
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  const units = ["B", "KiB", "MiB", "GiB"];
  let size = value;
  let unit = units[0];
  for (const nextUnit of units) {
    unit = nextUnit;
    if (size < 1024 || unit === units[units.length - 1]) break;
    size /= 1024;
  }
  return unit === "B" ? `${Math.round(size)} ${unit}` : `${size.toFixed(1)} ${unit}`;
}

function libraryCategoryLabel(category) {
  const labels = {
    local: "Original file",
    uploads: "Stored video copy",
    downloads: "URL download",
    results: "Saved subtitle output",
  };
  return labels[category] || String(category || "Project file");
}

function formatLibraryDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(window.SubtitleYCI18n?.current() || "en", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function libraryRequestBody(item, extra = {}) {
  return JSON.stringify({
    category: item.category,
    relative_path: item.relative_path,
    ...extra,
  });
}

function renderLibraryEmpty(container, message) {
  const empty = document.createElement("div");
  empty.className = "editor-library-empty";
  empty.textContent = message;
  container.appendChild(empty);
}

async function openVideoPath(path, options = {}) {
  const cleanPath = String(path || "").trim();
  if (!cleanPath || state.videoUploadActive) return;
  state.videoUploadActive = true;
  updateTransportState();
  try {
    setStatus(options.keepCopy ? "Copying video into SubtitleYC" : "Opening video");
    const session = await fetchJson("/api/videos/open", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: cleanPath, keep_copy: Boolean(options.keepCopy) }),
    });
    await loadSession(session, { time: 0 });
    publishEditorSessionUpdate("video");
    await loadCues({ silent: true });
    setStatus(options.keepCopy ? "Loaded stored video copy" : "Loaded video without copying");
  } finally {
    state.videoUploadActive = false;
    updateTransportState();
  }
}

async function chooseVideoFile() {
  const chooser = window.pywebview?.api?.choose_video_file;
  if (!chooser) {
    elements.videoInput.click();
    return;
  }
  const result = await chooser("");
  if (result?.ok && result.path) {
    await openVideoPath(result.path, { keepCopy: Boolean(elements.videoKeepCopyInput?.checked) });
  } else if (result && !result.cancelled) {
    setStatus(result.message || "Could not choose video", false);
  }
}

async function uploadVideoFile(file) {
  if (!file || state.videoUploadActive) return;
  state.videoUploadActive = true;
  updateTransportState();
  try {
    const form = new FormData();
    form.append("file", file);
    setStatus("Importing video copy");
    const session = await fetchJson("/api/videos/upload", {
      method: "POST",
      body: form,
    });
    await loadSession(session, { time: 0 });
    publishEditorSessionUpdate("video");
    await loadCues({ silent: true });
    setStatus(`Loaded ${session.original_name || file.name}`);
  } finally {
    state.videoUploadActive = false;
    updateTransportState();
  }
}

async function openLibraryVideo(item) {
  if (!item) return;
  setStatus(`Opening ${item.name || "previous video"}`);
  const session = await fetchJson("/api/library/videos/open", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: libraryRequestBody(item),
  });
  await loadSession(session, { time: 0 });
  await loadCues({ silent: true });
  closeLibrary();
  setStatus(`Loaded ${session.original_name || item.name || "video"}`);
}

async function importLibrarySubtitle(item) {
  if (!sessionId) {
    setStatus("Load a video before attaching a previous subtitle", false);
    return;
  }
  const payload = await fetchJson("/api/library/subtitles/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: libraryRequestBody(item, { session_id: sessionId }),
  });
  state.subtitleFormat = EDITOR_SUBTITLE_FORMAT;
  applySubtitleDownloadPayload(payload);
  state.cues = (payload.cues || []).map(normalizeCue).sort((a, b) => a.start_seconds - b.start_seconds || a.end_seconds - b.end_seconds);
  state.selectedIndex = cueAtTime(currentTime()).index;
  setClean();
  resetHistory();
  renderCueList();
  if (state.selectedIndex >= 0) selectCue(state.selectedIndex);
  updatePreview();
  publishSubtitleUpdated();
  closeLibrary();
  setStatus(`Loaded subtitle ${item.name || "file"}`);
}

function renderLibraryRow(item, type) {
  const row = document.createElement("div");
  row.className = "editor-library-row";

  const main = document.createElement("div");
  main.className = "editor-library-main";

  const name = document.createElement("div");
  name.className = "editor-library-name";
  name.textContent = item.display_name || item.name || item.relative_path || "Project file";

  const meta = document.createElement("div");
  meta.className = "editor-library-path";
  meta.textContent = [libraryCategoryLabel(item.category), formatBytes(item.bytes || 0), formatLibraryDate(item.modified_at)].filter(Boolean).join(" | ");

  const folder = document.createElement("div");
  folder.className = "editor-library-path";
  folder.textContent = item.folder || item.path || "";
  main.append(name, meta, folder);

  const action = document.createElement("button");
  action.type = "button";
  if (type === "video") {
    action.textContent = "Open";
    action.addEventListener("click", () => openLibraryVideo(item).catch((error) => setStatus(error.message || "Could not open video", false)));
  } else {
    action.textContent = "Attach";
    action.disabled = !sessionId;
    action.title = sessionId ? "Attach to the current video" : "Load a video first";
    action.addEventListener("click", () => importLibrarySubtitle(item).catch((error) => setStatus(error.message || "Could not attach subtitles", false)));
  }

  row.append(main, action);
  return row;
}

function renderLibrary(payload) {
  state.library = payload || null;
  const videos = Array.isArray(payload?.videos) ? payload.videos : [];
  const subtitles = Array.isArray(payload?.subtitles) ? payload.subtitles : [];
  elements.libraryVideoList.replaceChildren();
  elements.librarySubtitleList.replaceChildren();

  if (videos.length) {
    for (const item of videos) elements.libraryVideoList.appendChild(renderLibraryRow(item, "video"));
  } else {
    renderLibraryEmpty(elements.libraryVideoList, "No previous videos yet");
  }

  if (subtitles.length) {
    for (const item of subtitles) elements.librarySubtitleList.appendChild(renderLibraryRow(item, "subtitle"));
  } else {
    renderLibraryEmpty(elements.librarySubtitleList, "No previous timed subtitles yet");
  }

  const total = videos.length + subtitles.length;
  elements.libraryMeta.textContent = `${total} previous project ${total === 1 ? "file" : "files"}`;
}

async function refreshLibrary() {
  const payload = await fetchJson("/api/library");
  renderLibrary(payload);
  return payload;
}

function openLibrary() {
  elements.libraryOverlay.hidden = false;
  elements.libraryDrawer.hidden = false;
  elements.libraryDrawer.setAttribute("aria-hidden", "false");
  requestNativePreviewSurfaceSync();
  refreshLibrary().catch((error) => setStatus(error.message || "Could not load previous projects", false));
}

function closeLibrary() {
  elements.libraryOverlay.hidden = true;
  elements.libraryDrawer.hidden = true;
  elements.libraryDrawer.setAttribute("aria-hidden", "true");
  requestNativePreviewSurfaceSync();
}

function bindEvents() {
  elements.video.addEventListener("loadedmetadata", () => {
    window.clearTimeout(state.fallbackProbeTimer);
    if (elements.video.videoWidth && !state.useNativePreview) setFrameFallback(false);
    elements.seekSlider.max = String(duration());
    elements.seekSlider.step = "any";
    if (initialTime > 0) elements.video.currentTime = Math.min(initialTime, duration() || initialTime);
    updatePreview();
  });
  elements.video.addEventListener("error", () => {
    setFrameFallback(true, "Using frame preview");
  });
  elements.video.addEventListener("timeupdate", updatePreview);
  elements.video.addEventListener("seeked", updatePreview);
  elements.video.addEventListener("play", () => {
    elements.playButton.textContent = "Pause";
  });
  elements.video.addEventListener("pause", () => {
    elements.playButton.textContent = "Play";
  });

  elements.playButton.addEventListener("click", togglePreviewPlayback);
  elements.prevFrameButton.addEventListener("click", () => seekFrame(-1));
  elements.nextFrameButton.addEventListener("click", () => seekFrame(1));
  elements.seekSlider.addEventListener("pointerdown", beginPreviewScrub);
  elements.seekSlider.addEventListener("pointerup", finishPreviewScrub);
  elements.seekSlider.addEventListener("pointercancel", finishPreviewScrub);
  elements.seekSlider.addEventListener("blur", finishPreviewScrub);
  elements.seekSlider.addEventListener("input", () => {
    beginPreviewScrub();
    state.suppressSlider = true;
    seekTo(Number(elements.seekSlider.value || 0), { keepPlaying: true });
    state.suppressSlider = false;
  });
  elements.seekSlider.addEventListener("change", () => {
    state.suppressSlider = true;
    seekTo(Number(elements.seekSlider.value || 0), { keepPlaying: true, immediate: true });
    state.suppressSlider = false;
    finishPreviewScrub();
  });
  elements.prevSubtitleButton.addEventListener("click", jumpToPreviousSubtitleBoundary);
  elements.nextSubtitleButton.addEventListener("click", jumpToNextSubtitleBoundary);
  elements.visibleStartBackButton.addEventListener("click", () => nudgeVisible("start", -frameStepFrames()));
  elements.visibleStartForwardButton.addEventListener("click", () => nudgeVisible("start", frameStepFrames()));
  elements.visibleEndBackButton.addEventListener("click", () => nudgeVisible("end", -frameStepFrames()));
  elements.visibleEndForwardButton.addEventListener("click", () => nudgeVisible("end", frameStepFrames()));

  elements.cueForm.addEventListener("submit", (event) => {
    event.preventDefault();
    saveCues().catch((error) => setStatus(error.message || "Save failed", false));
  });
  elements.addCueButton.addEventListener("click", addCue);
  elements.deleteCueButton.addEventListener("click", deleteSelectedCue);
  elements.undoButton.addEventListener("click", undoEdit);
  elements.redoButton.addEventListener("click", redoEdit);
  elements.videoUploadButton.addEventListener("click", () => {
    chooseVideoFile().catch((error) => setStatus(error.message || "Open video failed", false));
  });
  elements.videoInput.addEventListener("change", () => {
    const file = elements.videoInput.files?.[0];
    elements.videoInput.value = "";
    uploadVideoFile(file).catch((error) => setStatus(error.message || "Video upload failed", false));
  });
  elements.previousButton.addEventListener("click", openLibrary);
  elements.libraryCloseButton.addEventListener("click", closeLibrary);
  elements.libraryOverlay.addEventListener("click", closeLibrary);
  elements.libraryRefreshButton.addEventListener("click", () => refreshLibrary().catch((error) => setStatus(error.message || "Refresh failed", false)));
  elements.saveButton.addEventListener("click", () => saveCues().catch((error) => setStatus(error.message || "Save failed", false)));
  elements.downloadButton.addEventListener("click", () => downloadSavedSubtitle().catch((error) => setStatus(error.message || "Download failed", false)));
  elements.reloadButton.addEventListener("click", () => loadCues().catch((error) => setStatus(error.message || "Reload failed", false)));
  elements.uploadButton.addEventListener("click", () => elements.subtitleImportInput.click());
  elements.subtitleImportInput.addEventListener("change", () => {
    const file = elements.subtitleImportInput.files?.[0];
    elements.subtitleImportInput.value = "";
    importSubtitleFile(file).catch((error) => setStatus(error.message || "Subtitle upload failed", false));
  });

  window.addEventListener("pywebviewready", () => {
    state.nativePreviewReady = true;
    requestNativePreviewSurfaceSync();
  });
  window.addEventListener("subtitleyc-native-preview-subtitle-box", (event) => {
    if (event.detail) saveSubtitleOverlayPosition(event.detail, { sync: false });
  });
  window.addEventListener("subtitleyc-native-preview-ready", () => {
    state.nativePreviewReady = true;
    requestNativePreviewSurfaceSync();
  });
  window.addEventListener("resize", () => {
    applySubtitleOverlayPosition();
    requestNativePreviewSurfaceSync();
  });
  window.addEventListener("pointerup", finishPreviewScrub);
  window.addEventListener("scroll", requestNativePreviewSurfaceSync, true);
  window.addEventListener("keydown", (event) => {
    if (shouldUseHistoryShortcut(event)) {
      event.preventDefault();
      const key = event.key.toLowerCase();
      if (key === "y" || (key === "z" && event.shiftKey)) redoEdit();
      else undoEdit();
      return;
    }
    handleEditorKeyboardShortcut(event);
  });
  window.addEventListener("beforeunload", (event) => {
    setNativePreviewVisible(false);
    if (!state.dirty) return;
    event.preventDefault();
    event.returnValue = "";
  });
}

async function init() {
  bindEvents();
  setupDraggableSubtitleOverlay();
  await loadAppearance();
  try {
    applyStoredSubtitleFormat();
    const loadedSession = await loadSession(null, { silentNoSession: true, time: initialTime });
    if (loadedSession) {
      await loadCues({ silent: true });
      setStatus("Ready");
    } else {
      setStatus("Upload a video or open Previous Projects");
    }
  } catch (error) {
    setStatus(error.message || "Editor failed to load", false);
  }
}
init();
