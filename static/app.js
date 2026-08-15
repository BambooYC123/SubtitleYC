const state = {
  session: null,
  image: new Image(),
  imageReady: false,
  videoReady: false,
  previewTime: 0,
  previewPlaying: false,
  previewScrubbing: false,
  previewScrubWasPlaying: false,
  previewScrubSyncTimer: null,
  previewScrubPendingTime: null,
  previewScrubLastSyncAt: 0,
  previewScrubUiFrame: null,
  previewTimer: null,
  previewFrameToken: 0,
  previewFrameDebounce: null,
  previewFrameLoading: false,
  previewFrameQueuedTime: null,
  previewFrameCurrentIndex: null,
  previewFrameLastIndex: null,
  previewFrameCache: new Map(),
  previewFramePrefetches: new Map(),
  previewFramePrefetchTimer: null,
  previewWarmupJobId: null,
  previewPreparing: false,
  nativePreviewReady: false,
  nativePreviewVisible: null,
  videoLoadToken: 0,
  fileUploadActive: false,
  imageRect: { x: 0, y: 0, width: 0, height: 0, scale: 1 },
  crop: null,
  dragStart: null,
  pendingInitialPreviewSeek: false,
  videocrReady: false,
  system: null,
  subtitleUrl: null,
  subtitleFilename: "subtitles.srt",
  subtitleFormat: "srt",
  activities: new Map(),
  activityCounter: 0,
  logPollTimer: null,
  settings: null,
  defaultSettings: null,
  settingsSaveTimer: null,
  settingsApplying: false,
  storage: null,
  library: null,
  subtitleCues: [],
  subtitleDirty: false,
  subtitleUndoStack: [],
  subtitleRedoStack: [],
  subtitleHistoryLimit: 100,
  subtitleActiveIndex: -1,
  subtitleTracks: [],
  subtitleProbeUrl: "",
  subtitleProbeBusy: false,
  urlFormats: [],
  formatProbeUrl: "",
  formatProbeBusy: false,
  formatProbePending: false,
  formatProbeTimer: null,
  confirmDialogResolve: null,
  confirmDialogReturnFocus: null,
};

const SUBTITLE_FORMAT_LABELS = { srt: "SRT", txt: "TXT", ass: "ASS" };
const PREVIEW_PLAYBACK_FPS = 8;
const PREVIEW_FRAME_DEBOUNCE_MS = 16;
const PREVIEW_SCRUB_SYNC_MS = 80;
const PREVIEW_FRAME_CACHE_LIMIT = 180;
const PREVIEW_PREFETCH_DELAY_MS = 30;
const PREVIEW_MAX_PREFETCHES = 3;
const CUE_BOUNDARY_EPSILON_SECONDS = 0.000001;
const URL_FORMAT_PROBE_DEBOUNCE_MS = 900;
const SUBTITLE_OVERLAY_POSITION_STORAGE_KEY = "subtitleyc:subtitle-overlay-position";
const OCR_LANGUAGES = [
  ["ar", "Arabic"],
  ["chi_sim", "Chinese Simplified"],
  ["chi_tra", "Chinese Traditional"],
  ["eng", "English"],
  ["eng+chi_sim", "English + Chinese Simplified"],
  ["eng+chi_tra", "English + Chinese Traditional"],
  ["tl", "Filipino / Tagalog"],
  ["fr", "French"],
  ["de", "German"],
  ["hi", "Hindi"],
  ["id", "Indonesian"],
  ["it", "Italian"],
  ["japan", "Japanese"],
  ["kk", "Kazakh"],
  ["korean", "Korean"],
  ["ms", "Malay"],
  ["mr", "Marathi"],
  ["mn", "Mongolian"],
  ["ne", "Nepali"],
  ["fa", "Persian"],
  ["pt", "Portuguese"],
  ["ru", "Russian"],
  ["es", "Spanish"],
  ["ta", "Tamil"],
  ["te", "Telugu"],
  ["th", "Thai"],
  ["tr", "Turkish"],
  ["uk", "Ukrainian"],
  ["ur", "Urdu"],
  ["ug", "Uyghur"],
  ["vi", "Vietnamese"],
];
const OCR_SITE_SUBTITLE_LANGUAGES = {
  ar: "ar,en.*",
  de: "de,en.*",
  eng: "en.*",
  es: "es,en.*",
  fa: "fa,en.*",
  fr: "fr,en.*",
  hi: "hi,en.*",
  id: "id,en.*",
  it: "it,en.*",
  japan: "ja,en.*",
  kk: "kk,en.*",
  korean: "ko,en.*",
  mn: "mn,en.*",
  mr: "mr,en.*",
  ms: "ms,en.*",
  ne: "ne,en.*",
  pt: "pt,en.*",
  ru: "ru,en.*",
  ta: "ta,en.*",
  te: "te,en.*",
  th: "th,en.*",
  tl: "fil,tl,en.*",
  tr: "tr,en.*",
  ug: "ug,en.*",
  uk: "uk,en.*",
  ur: "ur,en.*",
  vi: "vi,en.*",
};

const reportedFrontendCrashes = new Set();

function populateOcrLanguageSelect(select) {
  if (!select) return;
  const selected = select.value || "eng+chi_sim";
  const fragment = document.createDocumentFragment();
  for (const [value, label] of OCR_LANGUAGES) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    fragment.append(option);
  }
  select.replaceChildren(fragment);
  const values = Array.from(select.options, (option) => option.value);
  select.value = values.includes(selected) ? selected : "eng+chi_sim";
}

function populateOcrLanguageSelects() {
  populateOcrLanguageSelect(elements.languageInput);
  populateOcrLanguageSelect(elements.settingLanguageInput);
}

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
  const payload = {
    source,
    message: stack.split("\n")[0] || source,
    stack,
    url: window.location.href,
    user_agent: navigator.userAgent,
  };
  fetch("/api/crashes/frontend", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    keepalive: true,
  }).catch(() => undefined);
}

window.addEventListener("error", (event) => {
  reportFrontendCrash("main-window-error", event.error || event.message);
});
window.addEventListener("unhandledrejection", (event) => {
  reportFrontendCrash("main-window-unhandledrejection", event.reason);
});

const elements = {
  urlInput: document.querySelector("#urlInput"),
  urlButton: document.querySelector("#urlButton"),
  downloadDirInput: document.querySelector("#downloadDirInput"),
  downloadDirButton: document.querySelector("#downloadDirButton"),
  settingsButton: document.querySelector("#settingsButton"),
  libraryButton: document.querySelector("#libraryButton"),
  formatInput: document.querySelector("#formatInput"),
  formatProbeButton: document.querySelector("#formatProbeButton"),
  formatProbeSkeleton: document.querySelector("#formatProbeSkeleton"),
  downloadSubtitlesInput: document.querySelector("#downloadSubtitlesInput"),
  subtitleProbeButton: document.querySelector("#subtitleProbeButton"),
  subtitleDownloadButton: document.querySelector("#subtitleDownloadButton"),
  subtitleSourceTools: document.querySelector("#subtitleSourceTools"),
  subtitleTrackRow: document.querySelector("#subtitleTrackRow"),
  subtitleTrackInput: document.querySelector("#subtitleTrackInput"),
  fileInput: document.querySelector("#fileInput"),
  videoOpenButton: document.querySelector("#videoOpenButton"),
  keepVideoCopyInput: document.querySelector("#keepVideoCopyInput"),
  runButton: document.querySelector("#runButton"),
  canvas: document.querySelector("#previewCanvas"),
  subtitlePreviewOverlay: document.querySelector("#subtitlePreviewOverlay"),
  video: document.querySelector("#videoPlayer"),
  seekSlider: document.querySelector("#seekSlider"),
  playButton: document.querySelector("#playButton"),
  prevFrameButton: document.querySelector("#prevFrameButton"),
  nextFrameButton: document.querySelector("#nextFrameButton"),
  previewCuePrevJumpButton: document.querySelector("#previewCuePrevJumpButton"),
  previewCueJumpButton: document.querySelector("#previewCueJumpButton"),
  previewCueStartBackButton: document.querySelector("#previewCueStartBackButton"),
  previewCueStartForwardButton: document.querySelector("#previewCueStartForwardButton"),
  previewCueEndBackButton: document.querySelector("#previewCueEndBackButton"),
  previewCueEndForwardButton: document.querySelector("#previewCueEndForwardButton"),
  timeIndicator: document.querySelector("#timeIndicator"),
  activityList: document.querySelector("#activityList"),
  videoMeta: document.querySelector("#videoMeta"),
  cropReadout: document.querySelector("#cropReadout"),
  removeSubtitlesButton: document.querySelector("#removeSubtitlesButton"),
  removeVideoButton: document.querySelector("#removeVideoButton"),
  downloadLink: document.querySelector("#downloadLink"),
  downloadLinkLabel: document.querySelector("#downloadLinkLabel"),
  storageButton: document.querySelector("#storageButton"),
  subtitleEditorButton: document.querySelector("#subtitleEditorButton"),
  subtitleUploadButton: document.querySelector("#subtitleUploadButton"),
  recentProjects: document.querySelector("#recentProjects"),
  recentProjectList: document.querySelector("#recentProjectList"),
  recentProjectsLibraryButton: document.querySelector("#recentProjectsLibraryButton"),
  logsButton: document.querySelector("#logsButton"),
  logsCloseButton: document.querySelector("#logsCloseButton"),
  logOverlay: document.querySelector("#logOverlay"),
  logDrawer: document.querySelector("#logDrawer"),
  logFilter: document.querySelector("#logFilter"),
  logRefreshButton: document.querySelector("#logRefreshButton"),
  logCopyButton: document.querySelector("#logCopyButton"),
  logSaveButton: document.querySelector("#logSaveButton"),
  logClearButton: document.querySelector("#logClearButton"),
  logOutput: document.querySelector("#logOutput"),
  logMeta: document.querySelector("#logMeta"),
  systemStatus: document.querySelector("#systemStatus"),
  languageInput: document.querySelector("#languageInput"),
  subtitleFormatInput: document.querySelector("#subtitleFormatInput"),
  frameStepInput: document.querySelector("#frameStepInput"),
  confidenceInput: document.querySelector("#confidenceInput"),
  confidenceValue: document.querySelector("#confidenceValue"),
  similarityInput: document.querySelector("#similarityInput"),
  similarityValue: document.querySelector("#similarityValue"),
  ssimInput: document.querySelector("#ssimInput"),
  ssimValue: document.querySelector("#ssimValue"),
  mergeGapInput: document.querySelector("#mergeGapInput"),
  brightnessInput: document.querySelector("#brightnessInput"),
  maxWidthInput: document.querySelector("#maxWidthInput"),
  minDurationInput: document.querySelector("#minDurationInput"),
  timingOffsetInput: document.querySelector("#timingOffsetInput"),
  snapToFrameInput: document.querySelector("#snapToFrameInput"),
  normalizeChineseInput: document.querySelector("#normalizeChineseInput"),
  useServerModelInput: document.querySelector("#useServerModelInput"),
  useGpuInput: document.querySelector("#useGpuInput"),
  useFullframeInput: document.querySelector("#useFullframeInput"),
  angleClsInput: document.querySelector("#angleClsInput"),
  postProcessingInput: document.querySelector("#postProcessingInput"),
  startInput: document.querySelector("#startInput"),
  endInput: document.querySelector("#endInput"),
  settingsCloseButton: document.querySelector("#settingsCloseButton"),
  settingsOverlay: document.querySelector("#settingsOverlay"),
  settingsDrawer: document.querySelector("#settingsDrawer"),
  settingsSaveButton: document.querySelector("#settingsSaveButton"),
  settingsResetButton: document.querySelector("#settingsResetButton"),
  settingUiLanguageInput: document.querySelector("#settingUiLanguageInput"),
  settingThemeInput: document.querySelector("#settingThemeInput"),
  settingDownloadDirInput: document.querySelector("#settingDownloadDirInput"),
  settingDownloadDirButton: document.querySelector("#settingDownloadDirButton"),
  settingLanguageInput: document.querySelector("#settingLanguageInput"),
  settingSubtitleFormatInput: document.querySelector("#settingSubtitleFormatInput"),
  settingConfidenceInput: document.querySelector("#settingConfidenceInput"),
  settingConfidenceValue: document.querySelector("#settingConfidenceValue"),
  settingSimilarityInput: document.querySelector("#settingSimilarityInput"),
  settingSimilarityValue: document.querySelector("#settingSimilarityValue"),
  settingSsimInput: document.querySelector("#settingSsimInput"),
  settingSsimValue: document.querySelector("#settingSsimValue"),
  settingFrameStepInput: document.querySelector("#settingFrameStepInput"),
  settingMergeGapInput: document.querySelector("#settingMergeGapInput"),
  settingMinDurationInput: document.querySelector("#settingMinDurationInput"),
  settingTimingOffsetInput: document.querySelector("#settingTimingOffsetInput"),
  settingSnapToFrameInput: document.querySelector("#settingSnapToFrameInput"),
  settingBrightnessInput: document.querySelector("#settingBrightnessInput"),
  settingMaxWidthInput: document.querySelector("#settingMaxWidthInput"),
  settingUseServerModelInput: document.querySelector("#settingUseServerModelInput"),
  settingUseGpuInput: document.querySelector("#settingUseGpuInput"),
  settingUseFullframeInput: document.querySelector("#settingUseFullframeInput"),
  settingAngleClsInput: document.querySelector("#settingAngleClsInput"),
  settingPostProcessingInput: document.querySelector("#settingPostProcessingInput"),
  settingNormalizeChineseInput: document.querySelector("#settingNormalizeChineseInput"),
  settingToolVersionGrid: document.querySelector("#settingToolVersionGrid"),
  settingAppVersion: document.querySelector("#settingAppVersion"),
  settingVideocrVersion: document.querySelector("#settingVideocrVersion"),
  settingYtdlpVersion: document.querySelector("#settingYtdlpVersion"),
  copySystemInfoButton: document.querySelector("#copySystemInfoButton"),
  storageCloseButton: document.querySelector("#storageCloseButton"),
  storageOverlay: document.querySelector("#storageOverlay"),
  storageDrawer: document.querySelector("#storageDrawer"),
  storageRefreshButton: document.querySelector("#storageRefreshButton"),
  storageClearButton: document.querySelector("#storageClearButton"),
  storageTotal: document.querySelector("#storageTotal"),
  storageCleanable: document.querySelector("#storageCleanable"),
  storageDataDir: document.querySelector("#storageDataDir"),
  storageList: document.querySelector("#storageList"),
  storageMeta: document.querySelector("#storageMeta"),
  libraryCloseButton: document.querySelector("#libraryCloseButton"),
  libraryOverlay: document.querySelector("#libraryOverlay"),
  libraryDrawer: document.querySelector("#libraryDrawer"),
  libraryRefreshButton: document.querySelector("#libraryRefreshButton"),
  libraryVideoList: document.querySelector("#libraryVideoList"),
  librarySubtitleList: document.querySelector("#librarySubtitleList"),
  libraryMeta: document.querySelector("#libraryMeta"),
  subtitleCloseButton: document.querySelector("#subtitleCloseButton"),
  subtitleOverlay: document.querySelector("#subtitleOverlay"),
  subtitleDrawer: document.querySelector("#subtitleDrawer"),
  subtitleRefreshButton: document.querySelector("#subtitleRefreshButton"),
  subtitleUndoButton: document.querySelector("#subtitleUndoButton"),
  subtitleRedoButton: document.querySelector("#subtitleRedoButton"),
  subtitleAddCueButton: document.querySelector("#subtitleAddCueButton"),
  subtitleSaveButton: document.querySelector("#subtitleSaveButton"),
  subtitleImportButton: document.querySelector("#subtitleImportButton"),
  subtitleImportInput: document.querySelector("#subtitleImportInput"),
  subtitleShiftFramesInput: document.querySelector("#subtitleShiftFramesInput"),
  subtitleNudgeAllBackButton: document.querySelector("#subtitleNudgeAllBackButton"),
  subtitleNudgeAllForwardButton: document.querySelector("#subtitleNudgeAllForwardButton"),
  subtitleSnapButton: document.querySelector("#subtitleSnapButton"),
  subtitleCueCount: document.querySelector("#subtitleCueCount"),
  subtitleEditorMeta: document.querySelector("#subtitleEditorMeta"),
  subtitleCueList: document.querySelector("#subtitleCueList"),
  confirmDialogOverlay: document.querySelector("#confirmDialogOverlay"),
  confirmDialog: document.querySelector("#confirmDialog"),
  confirmDialogTitle: document.querySelector("#confirmDialogTitle"),
  confirmDialogMessage: document.querySelector("#confirmDialogMessage"),
  confirmDialogCancelButton: document.querySelector("#confirmDialogCancelButton"),
  confirmDialogAcceptButton: document.querySelector("#confirmDialogAcceptButton"),
};

const ctx = elements.canvas.getContext("2d");

function messageText(value, fallback = "Unknown error") {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((item) => messageText(item, "")).filter(Boolean).join("\n") || fallback;
  }
  if (typeof value === "object") {
    if (value.msg) {
      const location = Array.isArray(value.loc) ? value.loc.join(".") : value.loc;
      return location ? `${location}: ${value.msg}` : value.msg;
    }
    if (value.message || value.error || value.detail) {
      return messageText(value.message || value.error || value.detail, fallback);
    }
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return fallback;
    }
  }
  return String(value);
}

function selectedSubtitleFormat() {
  return elements.subtitleFormatInput.value || "srt";
}

function subtitleFormatLabel(format) {
  return SUBTITLE_FORMAT_LABELS[format] || String(format || "srt").toUpperCase();
}

function safeSubtitleName(name, format = "srt") {
  const extension = String(format || "srt").replace(/^\.+/, "") || "srt";
  const base = String(name || "subtitles")
    .replace(/\.[^.]+$/, "")
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\s+-\s+subtitles$/i, "")
    .trim();
  return `${base || "subtitles"} - subtitles.${extension}`;
}
function clampProgress(value) {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.min(1, value));
}

function activeStatus(status) {
  return status === "queued" || status === "running";
}

function hasActiveJobKind(kind) {
  for (const activity of state.activities.values()) {
    if (activity.kind === kind && activeStatus(activity.status)) {
      return true;
    }
  }
  return false;
}

function removeActivity(id) {
  state.activities.delete(id);
  renderActivities();
  updateActionStates();
}

function scheduleActivityRemoval(id, delayMs = 12000) {
  const activity = state.activities.get(id);
  if (!activity) return;
  const finishedAt = Date.now();
  activity.finishedAt = finishedAt;
  setTimeout(() => {
    const latest = state.activities.get(id);
    if (latest?.finishedAt === finishedAt) {
      removeActivity(id);
    }
  }, delayMs);
}

function setActivity(id, updates) {
  const current = state.activities.get(id) || {
    id,
    createdAt: state.activityCounter++,
    kind: "notice",
    label: "Status",
    message: "Queued",
    progress: 0,
    status: "queued",
  };
  const next = { ...current, ...updates };
  if (Object.prototype.hasOwnProperty.call(updates, "status") && updates.status !== current.status) {
    delete next.finishedAt;
  }
  state.activities.set(id, next);
  renderActivities();
  updateActionStates();
}

function renderActivities() {
  elements.activityList.replaceChildren();
  const activities = Array.from(state.activities.values()).sort((a, b) => (b.createdAt ?? 0) - (a.createdAt ?? 0));
  if (!activities.length) {
    activities.push({
      id: "idle",
      label: "Ready",
      message: "No active jobs",
      progress: 0,
      status: "idle",
    });
  }

  for (const activity of activities) {
    const row = document.createElement("div");
    row.className = `activity-row is-${activity.status || "running"}`;

    const main = document.createElement("div");
    main.className = "activity-main";

    const top = document.createElement("div");
    top.className = "activity-top";

    const name = document.createElement("div");
    name.className = "activity-name";
    name.textContent = activity.label || "Job";

    const percent = document.createElement("div");
    percent.className = "activity-percent";
    percent.textContent = `${Math.round(clampProgress(activity.progress) * 100)}%`;

    const track = document.createElement("div");
    track.className = "activity-track";

    const bar = document.createElement("div");
    bar.className = "activity-bar";
    bar.style.width = `${Math.round(clampProgress(activity.progress) * 100)}%`;
    track.appendChild(bar);

    const message = document.createElement("div");
    message.className = "activity-message";
    message.textContent = messageText(activity.message, "Working");

    top.append(name, percent);
    main.append(top, track, message);
    row.appendChild(main);

    const controls = document.createElement("div");
    controls.className = "activity-actions";

    if (activity.cancelable && activeStatus(activity.status)) {
      const stop = document.createElement("button");
      stop.className = "activity-action danger-action";
      stop.type = "button";
      stop.textContent = "Stop";
      stop.addEventListener("click", () => cancelJob(activity.id));
      controls.appendChild(stop);
    }

    if (activity.actionLabel && typeof activity.action === "function") {
      const action = document.createElement("button");
      action.className = "activity-action";
      action.type = "button";
      action.textContent = activity.actionLabel;
      action.addEventListener("click", activity.action);
      controls.appendChild(action);
    }

    if (controls.childElementCount) {
      row.appendChild(controls);
    }

    elements.activityList.appendChild(row);
  }
}
function setStatus(message, progress = null) {
  const status = progress === 0 ? "failed" : "complete";
  setActivity("notice", {
    kind: "notice",
    label: "Status",
    message: messageText(message, "Ready"),
    progress: progress === null ? 1 : clampProgress(progress),
    status,
    actionLabel: null,
    action: null,
  });
  if (status === "complete") {
    scheduleActivityRemoval("notice", 7000);
  }
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(messageText(payload.detail || payload.error || payload.message, response.statusText));
  }
  return payload;
}

async function cancelJob(jobId) {
  const activity = state.activities.get(jobId);
  if (!activity || !activeStatus(activity.status)) return;
  setActivity(jobId, { message: "Cancelling...", cancelable: false });
  try {
    await fetchJson(`/api/jobs/${jobId}/cancel`, { method: "POST" });
  } catch (error) {
    setActivity(jobId, { message: messageText(error.message || error, "Could not stop job"), cancelable: true });
  }
}

async function pollJob(jobId, options = {}) {
  const label = options.label || "Job";
  const kind = options.kind || "job";
  setActivity(jobId, {
    kind,
    label,
    message: "Queued",
    progress: 0,
    status: "queued",
    cancelable: options.cancelable !== false,
    actionLabel: null,
    action: null,
  });

  while (true) {
    const job = await fetchJson(`/api/jobs/${jobId}`);
    const status = job.status || "running";
    setActivity(jobId, {
      kind: job.kind || kind,
      label,
      message: job.message || status,
      progress: job.progress || 0,
      status,
      cancelable: options.cancelable !== false && activeStatus(status),
    });
    if (status === "complete") {
      if (options.autoRemoveComplete !== false) {
        scheduleActivityRemoval(jobId, options.removeDelayMs || 12000);
      }
      return job.result;
    }
    if (status === "cancelled") {
      setActivity(jobId, { message: job.message || "Cancelled", progress: job.progress || 0, status: "cancelled", cancelable: false });
      scheduleActivityRemoval(jobId, 12000);
      const error = new Error("Job cancelled");
      error.cancelled = true;
      throw error;
    }
    if (status === "failed") {
      const errorMessage = messageText(job.error || job.message, "Job failed");
      setActivity(jobId, { message: errorMessage, progress: job.progress || 0, status: "failed", cancelable: false });
      scheduleActivityRemoval(jobId, 30000);
      throw new Error(errorMessage);
    }
    await new Promise((resolve) => setTimeout(resolve, 900));
  }
}
function logQueryParams() {
  const value = elements.logFilter.value;
  const params = new URLSearchParams({ limit: "500" });
  if (value === "ERROR") {
    params.set("category", "all");
    params.set("level", "ERROR");
  } else {
    params.set("category", value || "all");
    params.set("level", "all");
  }
  return params;
}

function formatLogTime(timestamp) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return String(timestamp || "");
  }
  return date.toLocaleTimeString([], { hour12: false });
}

function formatLogEntry(entry) {
  const level = String(entry.level || "INFO").padEnd(7, " ");
  const category = String(entry.category || "app").padEnd(8, " ");
  const job = entry.job_id ? ` ${entry.job_id.slice(0, 8)}` : "";
  return `[${formatLogTime(entry.timestamp)}] ${level} ${category}${job} ${messageText(entry.message, "")}`;
}

function renderLogs(logs, logDir = "", crashDir = "") {
  const lines = logs.map(formatLogEntry);
  elements.logOutput.textContent = lines.join("\n");
  const logText = logDir ? ` | ${logDir}` : "";
  const crashText = crashDir ? ` | crashes: ${crashDir}` : "";
  elements.logMeta.textContent = `${lines.length} lines${logText}${crashText}`;
}

async function refreshLogs(options = {}) {
  const output = elements.logOutput;
  const shouldStick = options.forceBottom || output.scrollTop + output.clientHeight >= output.scrollHeight - 24;
  const payload = await fetchJson(`/api/logs?${logQueryParams().toString()}`);
  renderLogs(payload.logs || [], payload.log_dir || "", payload.crash_dir || "");
  if (shouldStick) {
    output.scrollTop = output.scrollHeight;
  }
}

function setTopbarPanel(panel = "") {
  const buttons = {
    library: elements.libraryButton,
    logs: elements.logsButton,
    storage: elements.storageButton,
    settings: elements.settingsButton,
  };
  for (const [name, button] of Object.entries(buttons)) {
    const active = name === panel;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  }
}
function openLogs() {
  closeLibrary();
  closeSettings();
  closeStorage();
  closeSubtitleEditor();
  elements.logOverlay.hidden = false;
  elements.logDrawer.hidden = false;
  elements.logDrawer.setAttribute("aria-hidden", "false");
  setTopbarPanel("logs");
  requestNativePreviewSurfaceSync();
  refreshLogs({ forceBottom: true }).catch((error) => setStatus(error.message, 0));
  if (state.logPollTimer) {
    clearInterval(state.logPollTimer);
  }
  state.logPollTimer = setInterval(() => {
    refreshLogs().catch(() => undefined);
  }, 2500);
}

function closeLogs() {
  elements.logOverlay.hidden = true;
  elements.logDrawer.hidden = true;
  elements.logDrawer.setAttribute("aria-hidden", "true");
  setTopbarPanel();
  requestNativePreviewSurfaceSync();
  if (state.logPollTimer) {
    clearInterval(state.logPollTimer);
    state.logPollTimer = null;
  }
}

async function copyLogs() {
  const text = elements.logOutput.textContent || "";
  await navigator.clipboard.writeText(text);
  setStatus("Logs copied", 1);
}

function saveLogs() {
  const blob = new Blob([elements.logOutput.textContent || ""], { type: "text/plain;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "subtitleyc-logs.txt";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
  setStatus("Logs saved", 1);
}

function formatBytes(bytes) {
  const value = Math.max(0, Number(bytes || 0));
  if (value < 1024) return `${value} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let scaled = value / 1024;
  let index = 0;
  while (scaled >= 1024 && index < units.length - 1) {
    scaled /= 1024;
    index += 1;
  }
  return `${scaled >= 100 ? scaled.toFixed(0) : scaled >= 10 ? scaled.toFixed(1) : scaled.toFixed(2)} ${units[index]}`;
}

function toolText(value, fallback = "Unknown") {
  const text = String(value || "").trim();
  return text || fallback;
}

function renderSystemInfo(system) {
  state.system = system || null;
  state.videocrReady = Boolean(system?.videocr_cli);
  const gpuAvailable = Boolean(system?.videocr_gpu_cli);
  for (const control of [elements.useGpuInput, elements.settingUseGpuInput].filter(Boolean)) {
    if (!gpuAvailable) control.checked = false;
    control.disabled = !gpuAvailable;
    control.setAttribute(
      "aria-label",
      gpuAvailable ? "Use GPU Acceleration" : "Use GPU Acceleration (VideOCR GPU build not installed)",
    );
    control.closest(".checkbox-row")?.classList.toggle("is-unavailable", !gpuAvailable);
  }
  const missing = [];
  if (!system?.ffmpeg) missing.push("ffmpeg");
  if (!system?.ffprobe) missing.push("ffprobe");
  if (!system?.videocr_cli) missing.push("VideOCR CLI");
  if (missing.length) {
    elements.systemStatus.textContent = `Missing: ${missing.join(", ")}. Install VideOCR or set VIDEOCR_CLI.`;
  } else if (gpuAvailable) {
    elements.systemStatus.textContent = "ffmpeg, ffprobe, and VideOCR GPU acceleration ready.";
  } else {
    elements.systemStatus.textContent = "ffmpeg, ffprobe, and VideOCR CPU ready. GPU build not installed.";
  }

  if (elements.settingToolVersionGrid) {
    elements.settingToolVersionGrid.hidden = false;
  }
  if (elements.settingAppVersion) {
    elements.settingAppVersion.textContent = toolText(system?.release_label || system?.app_version);
  }
  if (elements.settingVideocrVersion) {
    const version = system?.videocr_cli ? toolText(system.videocr_cli_version, "Available") : "Not found";
    elements.settingVideocrVersion.textContent = system?.videocr_cli
      ? `${version} (${gpuAvailable ? "GPU" : "CPU"})`
      : version;
  }
  if (elements.settingYtdlpVersion) {
    elements.settingYtdlpVersion.textContent = toolText(system?.yt_dlp_version);
  }
  updateActionStates();
}

async function refreshSystemInfo({ announce = false } = {}) {
  const system = await fetchJson("/api/system");
  renderSystemInfo(system);
  if (announce) setStatus("Tool versions refreshed", 1);
  return system;
}

function systemInfoText(system = state.system) {
  const release = toolText(system?.release_label || system?.app_version);
  const edition = toolText(
    system?.videocr_build_variant || (system?.videocr_gpu_cli ? "gpu" : system?.videocr_cli ? "cpu" : "development"),
  );
  const videocrVersion = system?.videocr_cli ? toolText(system?.videocr_cli_version, "Available") : "Not found";
  const videocrMode = system?.videocr_gpu_cli ? "GPU" : "CPU";
  const language = currentUiLanguage() === "zh-CN" ? "Chinese Simplified" : "English";
  const theme = currentTheme() === "light" ? "Light" : "Dark";
  return [
    "SubtitleYC system information",
    `SubtitleYC: ${release}`,
    `Edition: ${edition}`,
    `VideOCR: ${videocrVersion}${system?.videocr_cli ? ` (${videocrMode})` : ""}`,
    `yt-dlp: ${toolText(system?.yt_dlp_version)}`,
    `ffmpeg: ${system?.ffmpeg ? "Available" : "Not found"}`,
    `ffprobe: ${system?.ffprobe ? "Available" : "Not found"}`,
    `Interface language: ${language}`,
    `Theme: ${theme}`,
    `Desktop shell: ${window.pywebview?.api ? "Yes" : "No"}`,
  ].join("\n");
}

async function copySystemInfo() {
  const system = state.system || await refreshSystemInfo();
  await navigator.clipboard.writeText(systemInfoText(system));
  setStatus("System information copied", 1);
}
function selectedStorageCategories() {
  return Array.from(elements.storageList.querySelectorAll('input[type="checkbox"]:checked')).map((input) => input.value);
}

function updateStorageClearButton() {
  elements.storageClearButton.disabled = selectedStorageCategories().length === 0;
}

function renderStorage(payload) {
  state.storage = payload;
  const categories = payload.categories || [];
  elements.storageTotal.textContent = formatBytes(payload.total_bytes || 0);
  elements.storageCleanable.textContent = formatBytes(payload.cleanable_bytes || 0);
  elements.storageDataDir.textContent = payload.data_dir || "";
  elements.storageList.replaceChildren();

  if (!categories.length) {
    const empty = document.createElement("div");
    empty.className = "storage-empty";
    empty.textContent = "No storage data";
    elements.storageList.appendChild(empty);
  }

  for (const category of categories) {
    const row = document.createElement("div");
    row.className = `storage-row${category.cleanable ? "" : " is-locked"}`;

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = category.key;
    checkbox.disabled = !category.cleanable || Number(category.bytes || 0) === 0;
    checkbox.addEventListener("change", updateStorageClearButton);

    const main = document.createElement("div");
    main.className = "storage-main";

    const name = document.createElement("div");
    name.className = "storage-name";
    name.textContent = category.label || category.key;

    const path = document.createElement("div");
    path.className = "storage-path";
    path.textContent = category.path || "";

    main.append(name);
    main.appendChild(path);

    const size = document.createElement("div");
    size.className = "storage-size";
    size.textContent = formatBytes(category.bytes || 0);

    const files = document.createElement("div");
    files.className = "storage-files";
    files.textContent = `${category.files || 0} files`;

    const open = document.createElement("button");
    open.type = "button";
    open.className = "storage-open-row section-toggle";
    open.textContent = "Open";
    open.disabled = !category.path;
    open.addEventListener("click", () => openStorageLocation(category.path));

    const clear = document.createElement("button");
    clear.type = "button";
    clear.className = "storage-clear-row danger-action";
    clear.textContent = "Delete";
    clear.disabled = !category.cleanable || Number(category.bytes || 0) === 0;
    clear.addEventListener("click", () => clearStorageCategories([category.key]));

    row.append(checkbox, main, size, files, open, clear);
    elements.storageList.appendChild(row);
  }

  const fileCount = categories.reduce((total, category) => total + Number(category.files || 0), 0);
  elements.storageMeta.textContent = `${fileCount} files | ${categories.length} categories`;
  updateStorageClearButton();
}

async function refreshStorage() {
  const payload = await fetchJson("/api/storage");
  renderStorage(payload);
  return payload;
}

async function openStorageLocation(targetPath) {
  if (!targetPath) {
    setStatus("No storage location is available", 0);
    return;
  }
  const openLocation = window.pywebview?.api?.open_file_location;
  if (!openLocation) {
    setStatus("Open location is available in the desktop app", 0);
    return;
  }
  const result = await openLocation(targetPath);
  if (result?.ok) {
    setStatus(`Opened ${result.path || targetPath}`, 1);
  } else {
    setStatus(result?.message || "Could not open storage location", 0);
  }
}

function finishConfirmation(confirmed) {
  const resolve = state.confirmDialogResolve;
  if (!resolve) return;

  state.confirmDialogResolve = null;
  elements.confirmDialogOverlay.hidden = true;
  elements.confirmDialog.setAttribute("aria-hidden", "true");
  resolve(Boolean(confirmed));

  const returnFocus = state.confirmDialogReturnFocus;
  state.confirmDialogReturnFocus = null;
  if (returnFocus?.isConnected) {
    requestAnimationFrame(() => returnFocus.focus());
  }
}

function showConfirmation({ title, message, confirmLabel = "Confirm" }) {
  if (state.confirmDialogResolve) finishConfirmation(false);

  state.confirmDialogReturnFocus = document.activeElement;
  elements.confirmDialogTitle.textContent = title;
  elements.confirmDialogMessage.textContent = message;
  elements.confirmDialogAcceptButton.textContent = confirmLabel;
  elements.confirmDialogOverlay.hidden = false;
  elements.confirmDialog.setAttribute("aria-hidden", "false");

  return new Promise((resolve) => {
    state.confirmDialogResolve = resolve;
    requestAnimationFrame(() => elements.confirmDialogCancelButton.focus());
  });
}

async function clearStorageCategories(categories = null) {
  const requested = categories || selectedStorageCategories();
  if (!requested.length) {
    setStatus("Choose storage rows to clear", 1);
    return;
  }

  const storageCategories = state.storage?.categories || [];
  const selected = storageCategories.filter((category) => requested.includes(category.key));
  const selectedNames = selected.map((category) => category.label || category.key);
  const selectedBytes = selected.reduce((total, category) => total + Number(category.bytes || 0), 0);
  const selectionLabel = selectedNames.length ? selectedNames.join(", ") : `${requested.length} selected areas`;
  const confirmed = await showConfirmation({
    title: "Delete files?",
    message: `Permanently delete ${selectionLabel} (${formatBytes(selectedBytes)})?`,
    confirmLabel: "Delete",
  });
  if (!confirmed) return;

  const payload = await fetchJson("/api/storage/clear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ categories: requested }),
  });
  renderStorage(payload.storage);
  setStatus(`Deleted files from ${requested.length} storage ${requested.length === 1 ? "area" : "areas"}`, 1);
}

function openStorage() {
  closeLibrary();
  closeLogs();
  closeSettings();
  closeSubtitleEditor();
  elements.storageOverlay.hidden = false;
  elements.storageDrawer.hidden = false;
  elements.storageDrawer.setAttribute("aria-hidden", "false");
  setTopbarPanel("storage");
  requestNativePreviewSurfaceSync();
  refreshStorage().catch((error) => setStatus(error.message || error, 0));
}

function closeStorage() {
  elements.storageOverlay.hidden = true;
  elements.storageDrawer.hidden = true;
  elements.storageDrawer.setAttribute("aria-hidden", "true");
  setTopbarPanel();
  requestNativePreviewSurfaceSync();
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
  return date.toLocaleString(currentUiLanguage(), { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function renderLibraryEmpty(container, message) {
  const empty = document.createElement("div");
  empty.className = "library-empty";
  empty.textContent = message;
  container.appendChild(empty);
}

function libraryRequestBody(item, extra = {}) {
  return JSON.stringify({
    category: item.category,
    relative_path: item.relative_path,
    ...extra,
  });
}

async function openLibraryVideo(item) {
  if (!item) return;
  setStatus(`Opening ${item.name || "saved video"}`, 0.2);
  const session = await fetchJson("/api/library/videos/open", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: libraryRequestBody(item),
  });
  await loadSession(session);
  closeLibrary();
  setStatus(`Loaded ${session.original_name || item.name}`, 1);
}

async function importLibrarySubtitle(item) {
  if (!state.session) {
    setStatus("Load a video before attaching a previous subtitle", 0);
    return;
  }
  const payload = await fetchJson("/api/library/subtitles/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: libraryRequestBody(item, { session_id: state.session.id }),
  });
  applySubtitlePayload(payload);
  localStorage.setItem("subtitleyc:subtitle-updated", JSON.stringify({ sessionId: state.session.id, at: Date.now() }));
  closeLibrary();
  setStatus(`Loaded subtitle ${item.name || "file"}`, 1);
}

function renderLibraryRow(item, type) {
  const row = document.createElement("div");
  row.className = "library-row";

  const main = document.createElement("div");
  main.className = "library-main";

  const name = document.createElement("div");
  name.className = "library-name";
  name.textContent = item.display_name || item.name || item.relative_path || "Project file";

  const meta = document.createElement("div");
  meta.className = "library-path";
  const details = [libraryCategoryLabel(item.category), formatBytes(item.bytes || 0), formatLibraryDate(item.modified_at)].filter(Boolean);
  meta.textContent = details.join(" | ");

  const path = document.createElement("div");
  path.className = "library-path";
  path.textContent = item.folder || item.path || "";

  main.append(name, meta, path);

  const button = document.createElement("button");
  button.type = "button";
  button.className = "library-open-row section-toggle";
  if (type === "video") {
    button.textContent = "Open";
    button.addEventListener("click", () => openLibraryVideo(item).catch((error) => setStatus(error.message || error, 0)));
  } else {
    button.textContent = "Attach";
    button.disabled = !state.session;
    button.title = state.session ? "Attach to the current video" : "Load a video first";
    button.addEventListener("click", () => importLibrarySubtitle(item).catch((error) => setStatus(error.message || error, 0)));
  }

  row.append(main, button);
  return row;
}

function renderLibrary(payload) {
  state.library = payload;
  const videos = Array.isArray(payload?.videos) ? payload.videos : [];
  const subtitles = Array.isArray(payload?.subtitles) ? payload.subtitles : [];
  renderRecentProjects(videos);
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

function renderRecentProjects(videos = []) {
  if (!elements.recentProjects || !elements.recentProjectList) return;
  elements.recentProjectList.replaceChildren();
  const recent = videos.slice(0, 5);
  if (!recent.length) {
    const empty = document.createElement("div");
    empty.className = "recent-project-empty";
    empty.textContent = "No recent videos";
    elements.recentProjectList.appendChild(empty);
  } else {
    for (const item of recent) {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "recent-project-row";

      const details = document.createElement("span");
      details.className = "recent-project-main";
      const name = document.createElement("strong");
      name.textContent = item.display_name || item.name || "Recent video";
      const meta = document.createElement("span");
      meta.textContent = [formatLibraryDate(item.modified_at), formatBytes(item.bytes || 0)].filter(Boolean).join(" | ");
      details.append(name, meta);

      const openLabel = document.createElement("span");
      openLabel.className = "recent-project-open";
      openLabel.textContent = "Open";

      row.append(details, openLabel);
      row.addEventListener("click", () => openLibraryVideo(item).catch((error) => setStatus(error.message || error, 0)));
      elements.recentProjectList.appendChild(row);
    }
  }
  elements.recentProjects.hidden = Boolean(state.session);
}

async function refreshLibrary() {
  const payload = await fetchJson("/api/library");
  renderLibrary(payload);
  return payload;
}

function openLibrary() {
  closeLogs();
  closeStorage();
  closeSettings();
  closeSubtitleEditor();
  elements.libraryOverlay.hidden = false;
  elements.libraryDrawer.hidden = false;
  elements.libraryDrawer.setAttribute("aria-hidden", "false");
  setTopbarPanel("library");
  requestNativePreviewSurfaceSync();
  refreshLibrary().catch((error) => setStatus(error.message || error, 0));
}

function closeLibrary() {
  elements.libraryOverlay.hidden = true;
  elements.libraryDrawer.hidden = true;
  elements.libraryDrawer.setAttribute("aria-hidden", "true");
  setTopbarPanel();
  requestNativePreviewSurfaceSync();
}
function setSelectValue(select, value, fallback) {
  const wanted = String(value || fallback || "");
  const hasOption = Array.from(select.options).some((option) => option.value === wanted);
  select.value = hasOption ? wanted : fallback;
}

function numberFromInput(input, fallback) {
  const value = Number(input.value);
  return Number.isFinite(value) ? value : fallback;
}

function brightnessValue(input) {
  const value = input.value.trim();
  return value ? Number(value) : null;
}

function normalizedTheme(value) {
  return value === "light" ? "light" : "dark";
}

function currentTheme() {
  return normalizedTheme(document.documentElement.dataset.theme || state.settings?.theme || state.defaultSettings?.theme || "dark");
}

function currentUiLanguage() {
  return window.SubtitleYCI18n?.current() || state.settings?.ui_language || state.defaultSettings?.ui_language || "en";
}

function applyUiLanguage(language) {
  const normalized = window.SubtitleYCI18n?.set(language) || "en";
  const setShellLanguage = window.pywebview?.api?.set_shell_language;
  if (setShellLanguage) setShellLanguage(normalized).catch(() => {});
  return normalized;
}

function syncShellTheme(theme = currentTheme()) {
  const normalized = normalizedTheme(theme);
  window.subtitleycPendingShellTheme = normalized;
  const setShellTheme = window.pywebview?.api?.set_shell_theme;
  if (setShellTheme) {
    setShellTheme(normalized).catch(() => {});
  }
}

function applyTheme(theme) {
  const normalized = normalizedTheme(theme);
  document.documentElement.dataset.theme = normalized;
  document.documentElement.style.colorScheme = normalized;
  syncShellTheme(normalized);
  try {
    localStorage.setItem("subtitleyc:theme", normalized);
    localStorage.setItem("subtitleyc:theme-updated", JSON.stringify({ theme: normalized, at: Date.now() }));
  } catch (_error) {
    // Theme still applies locally if storage is unavailable.
  }
  return normalized;
}

window.addEventListener("pywebviewready", () => {
  syncShellTheme(window.subtitleycPendingShellTheme || currentTheme());
  applyUiLanguage(currentUiLanguage());
});
function settingsFromControls() {
  return {
    theme: currentTheme(),
    ui_language: currentUiLanguage(),
    default_download_dir: selectedDownloadDir(),
    default_language: selectedLanguage(),
    default_subtitle_format: selectedSubtitleFormat(),
    confidence: Number(elements.confidenceInput.value || 65),
    similarity: Number(elements.similarityInput.value || 72),
    ssim: Number(elements.ssimInput.value || 88),
    frames_to_skip: Math.max(0, Number(elements.frameStepInput.value || 0)),
    merge_gap: Number(elements.mergeGapInput.value || 0),
    min_duration: Number(elements.minDurationInput.value || 0.04),
    timing_offset_frames: Number(elements.timingOffsetInput.value || 0),
    snap_to_frame: elements.snapToFrameInput.checked,
    brightness_threshold: brightnessValue(elements.brightnessInput),
    max_ocr_width: Number(elements.maxWidthInput.value || 1280),
    normalize_chinese: elements.normalizeChineseInput.checked,
    use_server_model: elements.useServerModelInput.checked,
    use_gpu: elements.useGpuInput.checked,
    use_fullframe: elements.useFullframeInput.checked,
    angle_cls: elements.angleClsInput.checked,
    post_processing: elements.postProcessingInput.checked,
  };
}

function applySettingsToControls(settings) {
  const safe = { ...(state.defaultSettings || {}), ...(settings || {}) };
  state.settingsApplying = true;
  try {
    applyUiLanguage(safe.ui_language || "en");
    applyTheme(safe.theme || "dark");
    elements.downloadDirInput.value = safe.default_download_dir || "";
    setSelectValue(elements.languageInput, safe.default_language, "eng+chi_sim");
    setSelectValue(elements.subtitleFormatInput, safe.default_subtitle_format, "srt");
    elements.confidenceInput.value = String(safe.confidence ?? 65);
    elements.similarityInput.value = String(safe.similarity ?? 72);
    elements.ssimInput.value = String(safe.ssim ?? 88);
    elements.frameStepInput.value = String(safe.frames_to_skip ?? 0);
    elements.mergeGapInput.value = String(safe.merge_gap ?? 0);
    elements.minDurationInput.value = String(safe.min_duration ?? 0.04);
    elements.timingOffsetInput.value = String(safe.timing_offset_frames ?? 0);
    elements.snapToFrameInput.checked = Boolean(safe.snap_to_frame ?? true);
    elements.brightnessInput.value = safe.brightness_threshold === null || safe.brightness_threshold === undefined ? "" : String(safe.brightness_threshold);
    elements.maxWidthInput.value = String(safe.max_ocr_width ?? 1280);
    elements.normalizeChineseInput.checked = Boolean(safe.normalize_chinese ?? true);
    elements.useServerModelInput.checked = Boolean(safe.use_server_model ?? true);
    elements.useGpuInput.checked = Boolean(safe.use_gpu ?? false);
    elements.useFullframeInput.checked = Boolean(safe.use_fullframe ?? false);
    elements.angleClsInput.checked = Boolean(safe.angle_cls ?? false);
    elements.postProcessingInput.checked = Boolean(safe.post_processing ?? false);
    setOcrRangeLabels();
    const format = selectedSubtitleFormat();
    clearSubtitleDownload(safeSubtitleName(state.session?.original_name || "subtitles", format), format);
    updateActionStates();
  } finally {
    state.settingsApplying = false;
  }
}

function settingsFormFromSettings(settings) {
  const safe = { ...(state.defaultSettings || {}), ...(settings || {}) };
  setSelectValue(elements.settingUiLanguageInput, safe.ui_language || "en", "en");
  setSelectValue(elements.settingThemeInput, safe.theme || "dark", "dark");
  elements.settingDownloadDirInput.value = safe.default_download_dir || "";
  setSelectValue(elements.settingLanguageInput, safe.default_language, "eng+chi_sim");
  setSelectValue(elements.settingSubtitleFormatInput, safe.default_subtitle_format, "srt");
  elements.settingConfidenceInput.value = String(safe.confidence ?? 65);
  elements.settingSimilarityInput.value = String(safe.similarity ?? 72);
  elements.settingSsimInput.value = String(safe.ssim ?? 88);
  setSettingsRangeLabels();
  elements.settingFrameStepInput.value = String(safe.frames_to_skip ?? 0);
  elements.settingMergeGapInput.value = String(safe.merge_gap ?? 0);
  elements.settingMinDurationInput.value = String(safe.min_duration ?? 0.04);
  elements.settingTimingOffsetInput.value = String(safe.timing_offset_frames ?? 0);
  elements.settingSnapToFrameInput.checked = Boolean(safe.snap_to_frame ?? true);
  elements.settingBrightnessInput.value = safe.brightness_threshold === null || safe.brightness_threshold === undefined ? "" : String(safe.brightness_threshold);
  elements.settingMaxWidthInput.value = String(safe.max_ocr_width ?? 1280);
  elements.settingNormalizeChineseInput.checked = Boolean(safe.normalize_chinese ?? true);
  elements.settingUseServerModelInput.checked = Boolean(safe.use_server_model ?? true);
  elements.settingUseGpuInput.checked = Boolean(safe.use_gpu ?? false);
  elements.settingUseFullframeInput.checked = Boolean(safe.use_fullframe ?? false);
  elements.settingAngleClsInput.checked = Boolean(safe.angle_cls ?? false);
  elements.settingPostProcessingInput.checked = Boolean(safe.post_processing ?? false);
}

function settingsFormFromControls() {
  settingsFormFromSettings(settingsFromControls());
}

function settingsFromForm() {
  return {
    theme: normalizedTheme(elements.settingThemeInput.value),
    ui_language: window.SubtitleYCI18n?.normalize(elements.settingUiLanguageInput.value) || "en",
    default_download_dir: elements.settingDownloadDirInput.value.trim() || null,
    default_language: elements.settingLanguageInput.value || "eng+chi_sim",
    default_subtitle_format: elements.settingSubtitleFormatInput.value || "srt",
    confidence: numberFromInput(elements.settingConfidenceInput, 65),
    similarity: numberFromInput(elements.settingSimilarityInput, 72),
    ssim: numberFromInput(elements.settingSsimInput, 88),
    frames_to_skip: numberFromInput(elements.settingFrameStepInput, 0),
    merge_gap: numberFromInput(elements.settingMergeGapInput, 0),
    min_duration: numberFromInput(elements.settingMinDurationInput, 0.04),
    timing_offset_frames: numberFromInput(elements.settingTimingOffsetInput, 0),
    snap_to_frame: elements.settingSnapToFrameInput.checked,
    brightness_threshold: brightnessValue(elements.settingBrightnessInput),
    max_ocr_width: numberFromInput(elements.settingMaxWidthInput, 1280),
    normalize_chinese: elements.settingNormalizeChineseInput.checked,
    use_server_model: elements.settingUseServerModelInput.checked,
    use_gpu: elements.settingUseGpuInput.checked,
    use_fullframe: elements.settingUseFullframeInput.checked,
    angle_cls: elements.settingAngleClsInput.checked,
    post_processing: elements.settingPostProcessingInput.checked,
  };
}

function clearSettingsSaveTimer() {
  if (state.settingsSaveTimer) {
    clearTimeout(state.settingsSaveTimer);
    state.settingsSaveTimer = null;
  }
}

function settingsPayloadFromActiveControls() {
  return elements.settingsDrawer.hidden ? settingsFromControls() : settingsFromForm();
}

async function persistSettings({ closeAfterSave = false, announce = false } = {}) {
  if (state.settingsApplying) return null;
  clearSettingsSaveTimer();
  const payload = await fetchJson("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settingsPayloadFromActiveControls()),
  });
  state.settings = payload.settings || null;
  state.defaultSettings = payload.defaults || state.defaultSettings;
  applySettingsToControls(state.settings);
  if (closeAfterSave) {
    closeSettings();
  }
  if (announce) {
    setStatus("Settings saved", 1);
  }
  return payload;
}

function scheduleSettingsAutosave({ delayMs = 700 } = {}) {
  if (state.settingsApplying) return;
  clearSettingsSaveTimer();
  state.settingsSaveTimer = setTimeout(() => {
    state.settingsSaveTimer = null;
    persistSettings().catch((error) => setStatus(error.message || error, 0));
  }, delayMs);
}

async function loadSettings() {
  const payload = await fetchJson("/api/settings");
  state.settings = payload.settings || null;
  state.defaultSettings = payload.defaults || null;
  applySettingsToControls(state.settings);
}

function openSettings() {
  closeLibrary();
  closeLogs();
  closeStorage();
  closeSubtitleEditor();
  settingsFormFromControls();
  elements.settingsOverlay.hidden = false;
  elements.settingsDrawer.hidden = false;
  elements.settingsDrawer.setAttribute("aria-hidden", "false");
  setTopbarPanel("settings");
  requestNativePreviewSurfaceSync();
}

function closeSettings() {
  elements.settingsOverlay.hidden = true;
  elements.settingsDrawer.hidden = true;
  elements.settingsDrawer.setAttribute("aria-hidden", "true");
  setTopbarPanel();
  requestNativePreviewSurfaceSync();
}

async function saveSettings() {
  await persistSettings({ closeAfterSave: true, announce: true });
}

async function resetSettings() {
  const defaults = state.defaultSettings || {};
  settingsFormFromSettings(defaults);
  clearSettingsSaveTimer();
  const payload = await fetchJson("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(defaults),
  });
  state.settings = payload.settings || null;
  state.defaultSettings = payload.defaults || state.defaultSettings;
  applySettingsToControls(state.settings);
  setStatus("Settings reset", 1);
}

function bindSettingsAutosave() {
  const controls = [
    elements.downloadDirInput,
    elements.languageInput,
    elements.subtitleFormatInput,
    elements.frameStepInput,
    elements.confidenceInput,
    elements.similarityInput,
    elements.ssimInput,
    elements.mergeGapInput,
    elements.brightnessInput,
    elements.maxWidthInput,
    elements.minDurationInput,
    elements.timingOffsetInput,
    elements.snapToFrameInput,
    elements.normalizeChineseInput,
    elements.useServerModelInput,
    elements.useGpuInput,
    elements.useFullframeInput,
    elements.angleClsInput,
    elements.postProcessingInput,
    elements.settingUiLanguageInput,
    elements.settingThemeInput,
    elements.settingDownloadDirInput,
    elements.settingLanguageInput,
    elements.settingSubtitleFormatInput,
    elements.settingConfidenceInput,
    elements.settingSimilarityInput,
    elements.settingSsimInput,
    elements.settingFrameStepInput,
    elements.settingMergeGapInput,
    elements.settingMinDurationInput,
    elements.settingTimingOffsetInput,
    elements.settingSnapToFrameInput,
    elements.settingBrightnessInput,
    elements.settingMaxWidthInput,
    elements.settingUseServerModelInput,
    elements.settingUseGpuInput,
    elements.settingUseFullframeInput,
    elements.settingAngleClsInput,
    elements.settingPostProcessingInput,
    elements.settingNormalizeChineseInput,
  ].filter(Boolean);

  elements.settingThemeInput?.addEventListener("change", () => applyTheme(elements.settingThemeInput.value));
  elements.settingUiLanguageInput?.addEventListener("change", () => applyUiLanguage(elements.settingUiLanguageInput.value));

  for (const control of controls) {
    control.addEventListener("change", () => scheduleSettingsAutosave());
    if (control.matches('input[type="number"], input[type="text"], input[type="range"]')) {
      control.addEventListener("input", () => scheduleSettingsAutosave({ delayMs: 900 }));
    }
  }
}

async function clearLogs() {
  await fetchJson("/api/logs", { method: "DELETE" });
  await refreshLogs({ forceBottom: true });
  setStatus("Logs cleared", 1);
}

function formatTime(seconds) {
  const safe = Number.isFinite(seconds) ? Math.max(0, seconds) : 0;
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const secs = Math.floor(safe % 60);
  const millis = Math.floor((safe - Math.floor(safe)) * 1000);
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}.${String(millis).padStart(3, "0")}`;
}

function formatIndicatorTime(seconds) {
  const safe = Number.isFinite(seconds) ? Math.max(0, seconds) : 0;
  const totalSeconds = Math.floor(safe);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;
  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function sameCueBoundaryTime(a, b) {
  return Math.abs(Number(a || 0) - Number(b || 0)) <= CUE_BOUNDARY_EPSILON_SECONDS;
}
function resetSubtitleCues() {
  state.subtitleCues = [];
  state.subtitleDirty = false;
  state.subtitleActiveIndex = -1;
  resetSubtitleHistory();
  if (elements.subtitlePreviewOverlay) {
    elements.subtitlePreviewOverlay.hidden = true;
    elements.subtitlePreviewOverlay.textContent = "";
  }
  renderSubtitleEditor();
}

function cloneSubtitleCue(cue) {
  return {
    start_seconds: Math.max(0, Number(cue?.start_seconds || 0)),
    end_seconds: Math.max(0.001, Number(cue?.end_seconds || 0.001)),
    text: String(cue?.text || ""),
  };
}

function subtitleHistorySnapshot() {
  return {
    cues: state.subtitleCues.map(cloneSubtitleCue),
    activeIndex: state.subtitleActiveIndex,
    subtitleFormat: state.subtitleFormat,
  };
}

function updateSubtitleHistoryButtons() {
  const canUndo = state.subtitleUndoStack.length > 0;
  const canRedo = state.subtitleRedoStack.length > 0;
  if (elements.subtitleUndoButton) elements.subtitleUndoButton.disabled = !canUndo;
  if (elements.subtitleRedoButton) elements.subtitleRedoButton.disabled = !canRedo;
}

function resetSubtitleHistory() {
  state.subtitleUndoStack = [];
  state.subtitleRedoStack = [];
  updateSubtitleHistoryButtons();
}

function pushSubtitleHistory() {
  state.subtitleUndoStack.push(subtitleHistorySnapshot());
  if (state.subtitleUndoStack.length > state.subtitleHistoryLimit) {
    state.subtitleUndoStack.shift();
  }
  state.subtitleRedoStack = [];
  updateSubtitleHistoryButtons();
}

function restoreSubtitleHistory(snapshot) {
  if (!snapshot) return;
  state.subtitleCues = (snapshot.cues || []).map(normalizeCue).sort((a, b) => a.start_seconds - b.start_seconds || a.end_seconds - b.end_seconds);
  state.subtitleFormat = snapshot.subtitleFormat || state.subtitleFormat || "srt";
  setSelectValue(elements.subtitleFormatInput, state.subtitleFormat, "srt");
  const snapshotIndex = Number(snapshot.activeIndex);
  state.subtitleActiveIndex = snapshotIndex >= 0 ? Math.min(snapshotIndex, state.subtitleCues.length - 1) : -1;
  if (!state.subtitleCues.length) state.subtitleActiveIndex = -1;
  markSubtitleDirty();
  renderSubtitleEditor();
  updateSubtitlePreview();
  updateActionStates();
  requestAnimationFrame(scrollActiveSubtitleIntoView);
}

function undoSubtitleEdit() {
  if (!state.subtitleUndoStack.length) return;
  state.subtitleRedoStack.push(subtitleHistorySnapshot());
  restoreSubtitleHistory(state.subtitleUndoStack.pop());
  updateSubtitleHistoryButtons();
  setStatus("Undid subtitle edit", 1);
}

function redoSubtitleEdit() {
  if (!state.subtitleRedoStack.length) return;
  state.subtitleUndoStack.push(subtitleHistorySnapshot());
  restoreSubtitleHistory(state.subtitleRedoStack.pop());
  updateSubtitleHistoryButtons();
  setStatus("Redid subtitle edit", 1);
}

function shouldUseSubtitleHistoryShortcut(event) {
  if (!(event.ctrlKey || event.metaKey) || event.altKey) return false;
  const key = event.key.toLowerCase();
  if (key !== "z" && key !== "y") return false;
  const target = event.target;
  return !target?.closest?.("input, textarea, select, [contenteditable]");
}
function shortcutTargetIsEditable(event) {
  return Boolean(event.target?.closest?.("input, textarea, select, button, a, [contenteditable]"));
}

function drawerIsOpen(element) {
  return Boolean(element && !element.hidden);
}

function anyDrawerOpen() {
  return [elements.libraryDrawer, elements.logDrawer, elements.settingsDrawer, elements.storageDrawer, elements.subtitleDrawer].some(drawerIsOpen);
}

function canUsePreviewShortcuts() {
  return Boolean(state.session && !state.previewPreparing && sessionDuration() > 0);
}

function stepPreviewByFrames(frames) {
  if (!canUsePreviewShortcuts()) return;
  stopPreviewPlayback();
  seekTo(state.previewTime + frameSeconds() * frames, { immediate: true });
}

function handleGlobalKeyboardShortcut(event) {
  const key = event.key.toLowerCase();
  const command = event.ctrlKey || event.metaKey;

  if (command && !event.altKey) {
    if (key === "s") {
      if (state.session && state.subtitleDirty) {
        event.preventDefault();
        saveSubtitleCues().catch((error) => setStatus(error.message || error, 0));
        return true;
      }
      return false;
    }
    if (key === "l") {
      event.preventDefault();
      if (!elements.videoOpenButton.disabled) chooseLocalVideoFile().catch((error) => setStatus(error.message || error, 0));
      return true;
    }
    if (key === "u") {
      event.preventDefault();
      if (!elements.subtitleUploadButton.disabled) openSubtitleImportPicker();
      return true;
    }
    if (key === "e") {
      event.preventDefault();
      if (!elements.subtitleEditorButton.disabled) {
        openSubtitleEditorTab().catch((error) => setStatus(error.message || "Could not open SubtitleYC Editor", 0));
      }
      return true;
    }
    if (key === ",") {
      event.preventDefault();
      openSettings();
      return true;
    }
  }

  if (shortcutTargetIsEditable(event) || anyDrawerOpen() || !canUsePreviewShortcuts()) {
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
      stepPreviewByFrames(event.key === "ArrowLeft" ? -1 : 1);
    }
    return true;
  }

  return false;
}

function normalizeCue(raw) {
  const start = Math.max(0, Number(raw.start_seconds || 0));
  const end = Math.max(start + 0.001, Number(raw.end_seconds || start + 0.001));
  return {
    start_seconds: start,
    end_seconds: end,
    text: String(raw.text || ""),
  };
}

function editableCues() {
  return state.subtitleCues
    .map(normalizeCue)
    .filter((cue) => cue.text.trim())
    .sort((a, b) => a.start_seconds - b.start_seconds || a.end_seconds - b.end_seconds);
}

function applySubtitlePayload(payload, options = {}) {
  if (payload.id && state.session?.id === payload.id) {
    state.session = { ...state.session, ...payload };
  }
  state.subtitleCues = (payload.cues || []).map(normalizeCue);
  state.subtitleDirty = false;
  state.subtitleActiveIndex = -1;
  state.subtitleFormat = payload.subtitle_format || state.subtitleFormat || "srt";
  setSelectValue(elements.subtitleFormatInput, state.subtitleFormat, "srt");
  state.subtitleFilename = payload.subtitle_filename || safeSubtitleName(state.session?.original_name || "subtitles", state.subtitleFormat);
  if (payload.subtitle_url) {
    state.subtitleUrl = payload.subtitle_url;
    elements.downloadLink.href = payload.subtitle_url;
    elements.downloadLink.setAttribute("download", state.subtitleFilename);
    elements.downloadLink.classList.remove("disabled");
    updateDownloadLinkLabel(state.subtitleFormat);
  }
  if (options.resetHistory !== false) resetSubtitleHistory();
  renderSubtitleEditor();
  updateSubtitlePreview();
  updateActionStates();
}

function markSubtitleDirty() {
  state.subtitleDirty = true;
  renderSubtitleEditorHeader();
  updateSubtitleHistoryButtons();
}

function renderSubtitleEditorHeader() {
  const count = state.subtitleCues.length;
  elements.subtitleCueCount.textContent = `${count} ${count === 1 ? "cue" : "cues"}`;
  elements.subtitleEditorMeta.textContent = state.subtitleDirty ? "Unsaved changes" : subtitleFormatLabel(state.subtitleFormat);
  elements.subtitleSaveButton.disabled = !state.subtitleDirty || !state.session;
  updateSubtitleHistoryButtons();
}

function subtitleCueAtTime(time, preferredIndex = state.subtitleActiveIndex) {
  const current = Number(time || 0);
  const preferredCue = state.subtitleCues[preferredIndex];

  if (preferredCue && sameCueBoundaryTime(preferredCue.start_seconds, current)) {
    return { cue: preferredCue, index: preferredIndex };
  }

  for (let index = 0; index < state.subtitleCues.length; index += 1) {
    const cue = state.subtitleCues[index];
    if (sameCueBoundaryTime(cue.start_seconds, current)) {
      return { cue, index };
    }
  }

  if (preferredCue && Number(preferredCue.start_seconds || 0) < current && current < Number(preferredCue.end_seconds || 0)) {
    return { cue: preferredCue, index: preferredIndex };
  }

  for (let index = 0; index < state.subtitleCues.length; index += 1) {
    const cue = state.subtitleCues[index];
    if (Number(cue.start_seconds || 0) < current && current < Number(cue.end_seconds || 0)) {
      return { cue, index };
    }
  }

  const lastIndex = state.subtitleCues.length - 1;
  const lastCue = state.subtitleCues[lastIndex];
  if (lastCue && sameCueBoundaryTime(lastCue.end_seconds, current)) {
    return { cue: lastCue, index: lastIndex };
  }

  return { cue: null, index: -1 };
}

function highlightSubtitleRows() {
  for (const row of elements.subtitleCueList.querySelectorAll(".subtitle-cue-row")) {
    row.classList.toggle("is-active", Number(row.dataset.index) === state.subtitleActiveIndex);
  }
}

function hideWebSubtitlePreview() {
  if (!elements.subtitlePreviewOverlay) return;
  elements.subtitlePreviewOverlay.hidden = true;
  elements.subtitlePreviewOverlay.textContent = "";
}

function updateSubtitlePreview() {
  if (!elements.subtitlePreviewOverlay) return;
  if (!state.session || !state.subtitleCues.length) {
    hideWebSubtitlePreview();
    state.subtitleActiveIndex = -1;
    highlightSubtitleRows();
    syncNativePreviewSurface();
    return;
  }
  const previousActiveIndex = state.subtitleActiveIndex;
  const { cue, index } = subtitleCueAtTime(state.previewTime);
  if (index >= 0) {
    state.subtitleActiveIndex = index;
  } else if (!elements.subtitleDrawer.hidden && previousActiveIndex >= 0 && previousActiveIndex < state.subtitleCues.length) {
    state.subtitleActiveIndex = previousActiveIndex;
  } else {
    state.subtitleActiveIndex = -1;
  }
  if (!cue || !cue.text.trim() || nativePreviewEnabled()) {
    hideWebSubtitlePreview();
  } else {
    elements.subtitlePreviewOverlay.textContent = cue.text.trim();
    elements.subtitlePreviewOverlay.hidden = false;
    applySubtitleOverlayPosition();
  }
  highlightSubtitleRows();
  updatePreviewSubtitleActionStates();
  syncNativePreviewSurface();
}

function updatePreviewSubtitleActionStates(canScrub = null) {
  const scrubbable = canScrub ?? Boolean(state.session && sessionDuration() > 0);
  const hasCues = state.subtitleCues.length > 0;
  const canNudgeVisibleCue = scrubbable && currentSubtitleCueIndex() >= 0;
  elements.previewCuePrevJumpButton.disabled = !scrubbable || !hasCues;
  elements.previewCueJumpButton.disabled = !scrubbable || !hasCues;
  elements.previewCueStartBackButton.disabled = !canNudgeVisibleCue;
  elements.previewCueStartForwardButton.disabled = !canNudgeVisibleCue;
  elements.previewCueEndBackButton.disabled = !canNudgeVisibleCue;
  elements.previewCueEndForwardButton.disabled = !canNudgeVisibleCue;
  updateSubtitleHistoryButtons();
}

function subtitleTimeCell(labelText, input, index, boundary) {
  const cell = document.createElement("div");
  cell.className = "subtitle-time-cell";

  const label = document.createElement("div");
  label.className = "subtitle-time-label";
  label.textContent = labelText;

  const nudges = document.createElement("div");
  nudges.className = "subtitle-time-nudge";

  const back = document.createElement("button");
  back.type = "button";
  back.className = "section-toggle";
  back.textContent = "-";
  back.title = `Move ${labelText.toLowerCase()} earlier`;
  back.addEventListener("click", () => nudgeSubtitleBoundary(index, boundary, -subtitleShiftFrameCount()));

  const forward = document.createElement("button");
  forward.type = "button";
  forward.className = "section-toggle";
  forward.textContent = "+";
  forward.title = `Move ${labelText.toLowerCase()} later`;
  forward.addEventListener("click", () => nudgeSubtitleBoundary(index, boundary, subtitleShiftFrameCount()));

  nudges.append(back, forward);
  cell.append(label, input, nudges);
  return cell;
}

function renderSubtitleEditor() {
  if (!elements.subtitleCueList) return;
  renderSubtitleEditorHeader();
  elements.subtitleCueList.replaceChildren();
  if (!state.subtitleCues.length) {
    const empty = document.createElement("div");
    empty.className = "subtitle-empty";
    empty.textContent = state.subtitleUrl ? "No subtitle cues" : "Load a subtitle file, add a cue, or run VideOCR.";
    elements.subtitleCueList.appendChild(empty);
    return;
  }

  state.subtitleCues.forEach((cue, index) => {
    const row = document.createElement("div");
    row.className = `subtitle-cue-row${index === state.subtitleActiveIndex ? " is-active" : ""}`;
    row.dataset.index = String(index);
    row.addEventListener("focusin", () => {
      state.subtitleActiveIndex = index;
      highlightSubtitleRows();
    });

    const number = document.createElement("div");
    number.className = "subtitle-cue-number";
    number.textContent = String(index + 1);

    const start = document.createElement("input");
    start.className = "subtitle-time-input";
    start.type = "number";
    start.min = "0";
    start.step = "0.001";
    start.value = Number(cue.start_seconds || 0).toFixed(3);

    const end = document.createElement("input");
    end.className = "subtitle-time-input";
    end.type = "number";
    end.min = "0";
    end.step = "0.001";
    end.value = Number(cue.end_seconds || 0).toFixed(3);

    const text = document.createElement("textarea");
    text.className = "subtitle-cue-text";
    text.rows = 2;
    text.value = cue.text || "";

    const seek = document.createElement("button");
    seek.className = "section-toggle";
    seek.type = "button";
    seek.textContent = "Seek";
    seek.addEventListener("click", () => seekTo(Number(state.subtitleCues[index].start_seconds || 0)));

    const remove = document.createElement("button");
    remove.className = "section-toggle danger-action";
    remove.type = "button";
    remove.textContent = "Delete";
    remove.addEventListener("click", () => {
      pushSubtitleHistory();
      state.subtitleCues.splice(index, 1);
      markSubtitleDirty();
      renderSubtitleEditor();
      updateSubtitlePreview();
    });

    let startHistoryCaptured = false;
    let endHistoryCaptured = false;
    let textHistoryCaptured = false;
    const captureStartHistory = () => {
      if (!startHistoryCaptured) {
        pushSubtitleHistory();
        startHistoryCaptured = true;
      }
    };
    const captureEndHistory = () => {
      if (!endHistoryCaptured) {
        pushSubtitleHistory();
        endHistoryCaptured = true;
      }
    };
    const captureTextHistory = () => {
      if (!textHistoryCaptured) {
        pushSubtitleHistory();
        textHistoryCaptured = true;
      }
    };

    start.addEventListener("input", () => {
      captureStartHistory();
      const next = Math.max(0, Number(start.value || 0));
      state.subtitleCues[index].start_seconds = next;
      if (Number(state.subtitleCues[index].end_seconds || 0) <= next) {
        state.subtitleCues[index].end_seconds = next + 0.001;
        end.value = state.subtitleCues[index].end_seconds.toFixed(3);
      }
      markSubtitleDirty();
      updateSubtitlePreview();
    });
    end.addEventListener("input", () => {
      captureEndHistory();
      state.subtitleCues[index].end_seconds = Math.max(Number(state.subtitleCues[index].start_seconds || 0) + 0.001, Number(end.value || 0));
      markSubtitleDirty();
      updateSubtitlePreview();
    });
    text.addEventListener("input", () => {
      captureTextHistory();
      state.subtitleCues[index].text = text.value;
      markSubtitleDirty();
      updateSubtitlePreview();
    });

    row.append(
      number,
      subtitleTimeCell("Start", start, index, "start"),
      subtitleTimeCell("End", end, index, "end"),
      text,
      seek,
      remove
    );
    elements.subtitleCueList.appendChild(row);
  });
}
function scrollActiveSubtitleIntoView() {
  if (elements.subtitleDrawer.hidden || state.subtitleActiveIndex < 0) return;
  const row = elements.subtitleCueList.querySelector(`[data-index="${state.subtitleActiveIndex}"]`);
  row?.scrollIntoView({ block: "center" });
}
function openSubtitleImportPicker() {
  if (!state.session) {
    setStatus("Load a video before uploading subtitles", 0);
    return;
  }
  elements.subtitleImportInput.click();
}
async function importSubtitleFile(file) {
  if (!state.session || !file) return;
  const formData = new FormData();
  formData.append("file", file);
  const payload = await fetchJson(`/api/videos/${state.session.id}/subtitles/import`, {
    method: "POST",
    body: formData,
  });
  pushSubtitleHistory();
  applySubtitlePayload(payload, { resetHistory: false });
  const current = subtitleCueAtTime(state.previewTime);
  if (current.index < 0 && state.subtitleCues.length) {
    seekTo(state.subtitleCues[0].start_seconds, { immediate: true });
  }
  setStatus(`Loaded ${payload.cue_count || 0} subtitle cues from ${file.name}`, 1);
}
async function loadSubtitleCues(options = {}) {
  if (!state.session || !state.subtitleUrl) {
    if (!options.silent) setStatus("No subtitle file is available", 0);
    return null;
  }
  const payload = await fetchJson(`/api/videos/${state.session.id}/subtitles`);
  applySubtitlePayload(payload);
  if (!options.silent) setStatus(`${payload.cue_count || 0} subtitle cues loaded`, 1);
  return payload;
}

function openSubtitleEditor() {
  closeLibrary();
  if (!state.session) {
    setStatus("Load a video before opening subtitles", 0);
    return;
  }
  closeLogs();
  closeSettings();
  closeStorage();
  elements.subtitleOverlay.hidden = false;
  elements.subtitleDrawer.hidden = false;
  elements.subtitleDrawer.setAttribute("aria-hidden", "false");
  requestNativePreviewSurfaceSync();

  const showCurrentCue = () => {
    renderSubtitleEditor();
    updateSubtitlePreview();
    requestAnimationFrame(scrollActiveSubtitleIntoView);
  };

  if (state.subtitleUrl && !state.subtitleCues.length && !state.subtitleDirty) {
    loadSubtitleCues({ silent: true })
      .then(showCurrentCue)
      .catch((error) => setStatus(error.message || error, 0));
  } else {
    showCurrentCue();
  }
}

function closeSubtitleEditor() {
  elements.subtitleOverlay.hidden = true;
  elements.subtitleDrawer.hidden = true;
  elements.subtitleDrawer.setAttribute("aria-hidden", "true");
  requestNativePreviewSurfaceSync();
}
async function openSubtitleEditorTab() {
  const hasSession = Boolean(state.session?.id);
  if (hasSession) publishSubtitleFormatUpdate(state.subtitleFormat);
  const editorUrl = hasSession
    ? `/editor?session=${encodeURIComponent(state.session.id)}&time=${encodeURIComponent(state.previewTime || 0)}`
    : "/editor";
  const api = window.pywebview?.api?.open_subtitle_editor;
  if (api) {
    try {
      const result = await api(hasSession ? state.session.id : "", hasSession ? Number(state.previewTime || 0) : 0);
      if (result?.ok) {
        setStatus("Opened SubtitleYC Editor", 1);
        return;
      }
      throw new Error(result?.message || "Could not open SubtitleYC Editor");
    } catch (error) {
      setStatus(error.message || "Could not open SubtitleYC Editor", 0);
    }
  }
  const opened = window.open(editorUrl, "_blank", "noopener");
  if (opened) {
    setStatus("Opened SubtitleYC Editor", 1);
    return;
  }
  if (hasSession) {
    openSubtitleEditor();
  } else {
    window.location.href = editorUrl;
  }
}
function addSubtitleCue() {
  if (!state.session) return;
  const start = Number(state.previewTime || elements.seekSlider.value || 0);
  const frame = frameSeconds();
  const duration = Number(state.session.metadata?.duration || start + 2);
  const end = Math.min(Math.max(start + 2, start + frame), Math.max(start + frame, duration));
  pushSubtitleHistory();
  state.subtitleCues.push({ start_seconds: start, end_seconds: end, text: "" });
  state.subtitleCues.sort((a, b) => a.start_seconds - b.start_seconds || a.end_seconds - b.end_seconds);
  markSubtitleDirty();
  renderSubtitleEditor();
  updateSubtitlePreview();
}

function formatFrameCount(frames) {
  const value = Math.abs(Number(frames || 0));
  return Number.isInteger(value) ? String(value) : value.toFixed(2).replace(/\.?0+$/, "");
}

function subtitleShiftFrameCount() {
  const value = Math.abs(Number(elements.subtitleShiftFramesInput?.value || 1));
  return Number.isFinite(value) && value > 0 ? value : 1;
}

function shiftCueObject(cue, deltaSeconds) {
  const start = Math.max(0, Number(cue.start_seconds || 0));
  const end = Math.max(start + 0.001, Number(cue.end_seconds || start + 0.001));
  const duration = Math.max(0.001, end - start);
  const nextStart = Math.max(0, start + deltaSeconds);
  cue.start_seconds = nextStart;
  cue.end_seconds = Math.max(nextStart + 0.001, nextStart + duration);
}

function shiftCueBoundary(cue, boundary, deltaSeconds) {
  const start = Math.max(0, Number(cue.start_seconds || 0));
  const end = Math.max(start + 0.001, Number(cue.end_seconds || start + 0.001));
  if (boundary === "start") {
    cue.start_seconds = Math.max(0, Math.min(end - 0.001, start + deltaSeconds));
    return;
  }
  cue.end_seconds = Math.max(start + 0.001, end + deltaSeconds);
}

function sortSubtitleCues(activeCue = null) {
  state.subtitleCues.sort((a, b) => a.start_seconds - b.start_seconds || a.end_seconds - b.end_seconds);
  state.subtitleActiveIndex = activeCue ? state.subtitleCues.indexOf(activeCue) : state.subtitleActiveIndex;
}

function currentSubtitleCueIndex() {
  const live = subtitleCueAtTime(state.previewTime);
  if (live.index >= 0) return live.index;
  return state.subtitleActiveIndex;
}

function sortedSubtitleCueItems() {
  return state.subtitleCues
    .map((cue, index) => ({ cue: normalizeCue(cue), index }))
    .sort((a, b) => a.cue.start_seconds - b.cue.start_seconds || a.cue.end_seconds - b.cue.end_seconds);
}

function nextSubtitleJumpTarget(time) {
  const current = Math.max(0, Number(time || 0));
  const minDelta = Math.max(0.001, Math.min(0.02, frameSeconds() / 10));
  const cues = sortedSubtitleCueItems();

  for (const item of cues) {
    if (current >= item.cue.start_seconds - minDelta && current < item.cue.end_seconds - minDelta) {
      return { time: item.cue.end_seconds, index: item.index, boundary: "end" };
    }
  }
  for (const item of cues) {
    if (item.cue.start_seconds > current + minDelta) {
      return { time: item.cue.start_seconds, index: item.index, boundary: "start" };
    }
  }
  return null;
}

function previousSubtitleJumpTarget(time) {
  const current = Math.max(0, Number(time || 0));
  const minDelta = Math.max(0.001, Math.min(0.02, frameSeconds() / 10));
  const cues = sortedSubtitleCueItems();

  for (let index = cues.length - 1; index >= 0; index -= 1) {
    const item = cues[index];
    if (current > item.cue.start_seconds + minDelta && current <= item.cue.end_seconds + minDelta) {
      return { time: item.cue.start_seconds, index: item.index, boundary: "start" };
    }
  }
  for (let index = cues.length - 1; index >= 0; index -= 1) {
    const item = cues[index];
    if (item.cue.end_seconds < current - minDelta) {
      return { time: item.cue.end_seconds, index: item.index, boundary: "end" };
    }
  }
  return null;
}

function jumpToSubtitleBoundary(target, emptyMessage) {
  if (!state.subtitleCues.length) {
    setStatus("No subtitle cues to jump through", 0);
    return;
  }
  if (!target) {
    setStatus(emptyMessage, 0);
    return;
  }
  stopPreviewPlayback();
  seekTo(target.time, { immediate: true });
  state.subtitleActiveIndex = target.index;
  renderSubtitleEditor();
  updateSubtitlePreview();
  requestAnimationFrame(scrollActiveSubtitleIntoView);
  const cueNumber = target.index + 1;
  setStatus(`Jumped to cue ${cueNumber} ${target.boundary}`, 1);
}

function jumpToNextSubtitleBoundary() {
  const target = nextSubtitleJumpTarget(state.previewTime);
  jumpToSubtitleBoundary(target, "No later subtitle cue");
}

function jumpToPreviousSubtitleBoundary() {
  const target = previousSubtitleJumpTarget(state.previewTime);
  jumpToSubtitleBoundary(target, "No earlier subtitle cue");
}

function nudgeSubtitleBoundary(index, boundary, frames) {
  if (index < 0 || !state.subtitleCues[index]) {
    setStatus("Choose a subtitle cue to nudge", 0);
    return;
  }
  const cue = state.subtitleCues[index];
  pushSubtitleHistory();
  shiftCueBoundary(cue, boundary, frames * frameSeconds());
  sortSubtitleCues(cue);
  const cueNumber = state.subtitleCues.indexOf(cue) + 1;
  markSubtitleDirty();
  renderSubtitleEditor();
  updateSubtitlePreview();
  const direction = frames > 0 ? "later" : "earlier";
  const label = boundary === "start" ? "start" : "end";
  setStatus(`Nudged cue ${cueNumber} ${label} ${direction} by ${formatFrameCount(frames)} frame${Math.abs(frames) === 1 ? "" : "s"}`, 1);
}

function nudgeCurrentSubtitleBoundary(boundary, frames) {
  const index = currentSubtitleCueIndex();
  if (index < 0 || !state.subtitleCues[index]) {
    setStatus("Move the playhead over a cue or focus a cue row before nudging it", 0);
    return;
  }
  nudgeSubtitleBoundary(index, boundary, frames);
}

function nudgeAllSubtitles(frames) {
  if (!state.subtitleCues.length) {
    setStatus("No subtitle cues to nudge", 0);
    return;
  }
  const delta = frames * frameSeconds();
  pushSubtitleHistory();
  for (const cue of state.subtitleCues) {
    shiftCueObject(cue, delta);
  }
  sortSubtitleCues();
  markSubtitleDirty();
  renderSubtitleEditor();
  updateSubtitlePreview();
  setStatus(`Nudged all cues ${frames > 0 ? "later" : "earlier"} by ${formatFrameCount(frames)} frame${Math.abs(frames) === 1 ? "" : "s"}`, 1);
}

function snapSubtitleCuesToFrames() {
  if (!state.subtitleCues.length) {
    setStatus("No subtitle cues to snap", 0);
    return;
  }
  const frame = frameSeconds();
  pushSubtitleHistory();
  for (const cue of state.subtitleCues) {
    const start = Math.max(0, Math.round(Number(cue.start_seconds || 0) / frame) * frame);
    const end = Math.round(Number(cue.end_seconds || start + frame) / frame) * frame;
    cue.start_seconds = start;
    cue.end_seconds = Math.max(start + 0.001, end, start + frame);
  }
  sortSubtitleCues();
  markSubtitleDirty();
  renderSubtitleEditor();
  updateSubtitlePreview();
  setStatus("Snapped subtitle timings to the video frame grid", 1);
}
async function saveSubtitleCues() {
  if (!state.session) return;
  const payload = await fetchJson(`/api/videos/${state.session.id}/subtitles`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subtitle_format: state.subtitleFormat, cues: editableCues() }),
  });
  applySubtitlePayload(payload, { resetHistory: false });
  setStatus(`Saved ${payload.cue_count || 0} subtitle cues`, 1);
}

function sourceSize() {
  const meta = state.session?.metadata || {};
  const width = Number(meta.width || 0);
  const height = Number(meta.height || 0);
  if (width && height) return { width, height };
  if (state.imageReady && state.image.naturalWidth && state.image.naturalHeight) {
    return { width: state.image.naturalWidth, height: state.image.naturalHeight };
  }
  return { width: 0, height: 0 };
}

function canDrawVideo() {
  return false;
}

function updateNativeVideoVisibility() {
  elements.video.classList.remove("is-visible");
}

function updateActionStates() {
  const hasSession = Boolean(state.session);
  const hasSubtitles = Boolean(state.subtitleUrl || state.subtitleCues.length);
  const hasCrop = Boolean(state.crop);
  const hasUrl = elements.urlInput.value.trim().length > 0;
  const videoBusy = state.previewPreparing || state.fileUploadActive;
  const canScrub = hasSession && !state.previewPreparing && sessionDuration() > 0;
  const downloadActive = hasActiveJobKind("download");
  const ocrActive = hasActiveJobKind("ocr");

  const subtitleDownloadActive = hasActiveJobKind("subtitle_download");
  const ytDlpActive = downloadActive || subtitleDownloadActive;
  syncSourceSubtitleControls();
  const hasSubtitleTrack = Boolean(selectedSubtitleTrack());

  elements.urlButton.disabled = !hasUrl || ytDlpActive || videoBusy;
  const formatButtonLabel = elements.formatProbeButton.querySelector("span");
  if (formatButtonLabel) {
    formatButtonLabel.textContent = state.formatProbeBusy ? "Checking..." : state.urlFormats.length ? "Refresh Formats" : "Check Formats";
  }
  elements.formatProbeButton.disabled = !hasUrl || ytDlpActive || videoBusy || state.formatProbeBusy;
  if (elements.formatProbeSkeleton) {
    elements.formatProbeSkeleton.hidden = !(state.formatProbePending || state.formatProbeBusy);
  }
  elements.subtitleProbeButton.disabled = !hasUrl || ytDlpActive || videoBusy || state.subtitleProbeBusy;
  elements.subtitleDownloadButton.disabled = !hasUrl || !hasSubtitleTrack || ytDlpActive || videoBusy;
  elements.fileInput.disabled = videoBusy || ocrActive;
  if (elements.videoOpenButton) elements.videoOpenButton.disabled = videoBusy || ocrActive;
  if (elements.keepVideoCopyInput) elements.keepVideoCopyInput.disabled = videoBusy || ocrActive;
  elements.runButton.disabled = !hasSession || !hasCrop || !state.videocrReady || ocrActive || state.previewPreparing;
  elements.seekSlider.disabled = !canScrub;
  elements.playButton.disabled = !canScrub;
  elements.prevFrameButton.disabled = !canScrub;
  elements.nextFrameButton.disabled = !canScrub;
  updatePreviewSubtitleActionStates(canScrub);
  elements.subtitleEditorButton.disabled = state.previewPreparing;
  elements.subtitleUploadButton.disabled = !hasSession || state.previewPreparing;
  if (elements.removeSubtitlesButton) elements.removeSubtitlesButton.disabled = !hasSession || !hasSubtitles || state.previewPreparing;
  if (elements.removeVideoButton) elements.removeVideoButton.disabled = !hasSession || videoBusy || ocrActive;
  if (elements.recentProjects) elements.recentProjects.hidden = hasSession;
}
function resizeCanvas() {
  const rect = elements.canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  elements.canvas.width = Math.max(1, Math.floor(rect.width * ratio));
  elements.canvas.height = Math.max(1, Math.floor(rect.height * ratio));
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  drawCanvas();
  syncNativePreviewSurface();
}

function drawCanvas() {
  const canvasRect = elements.canvas.getBoundingClientRect();
  updateNativeVideoVisibility();
  ctx.clearRect(0, 0, canvasRect.width, canvasRect.height);

  if (state.previewPreparing) {
    state.imageRect = { x: 0, y: 0, width: canvasRect.width, height: canvasRect.height, scale: 1 };
    ctx.fillStyle = "#111827";
    ctx.fillRect(0, 0, canvasRect.width, canvasRect.height);
    ctx.fillStyle = "#cbd5e1";
    ctx.font = "14px system-ui";
    ctx.textAlign = "center";
    ctx.fillText("Preparing preview...", canvasRect.width / 2, canvasRect.height / 2);
    return;
  }

  const size = sourceSize();
  if (!size.width || !size.height) {
    state.imageRect = { x: 0, y: 0, width: canvasRect.width, height: canvasRect.height, scale: 1 };
    const darkPreview = currentTheme() === "dark";
    ctx.fillStyle = darkPreview ? "#0b1118" : "#f5f7fb";
    ctx.fillRect(0, 0, canvasRect.width, canvasRect.height);
    ctx.fillStyle = darkPreview ? "#98a6b7" : "#646a73";
    ctx.font = "14px system-ui";
    ctx.textAlign = "center";
    ctx.fillText("Load a video", canvasRect.width / 2, canvasRect.height / 2);
    return;
  }

  const scale = Math.min(canvasRect.width / size.width, canvasRect.height / size.height);
  const width = size.width * scale;
  const height = size.height * scale;
  const x = (canvasRect.width - width) / 2;
  const y = (canvasRect.height - height) / 2;
  state.imageRect = { x, y, width, height, scale };

  ctx.fillStyle = "#111827";
  ctx.fillRect(0, 0, canvasRect.width, canvasRect.height);
  if (state.imageReady) {
    ctx.drawImage(state.image, x, y, width, height);
  }

  if (state.crop) {
    const rect = cropToCanvas(state.crop);
    ctx.save();
    ctx.fillStyle = "rgba(15, 118, 110, 0.14)";
    ctx.strokeStyle = "#0f766e";
    ctx.lineWidth = 2;
    ctx.fillRect(rect.x, rect.y, rect.width, rect.height);
    ctx.strokeRect(rect.x, rect.y, rect.width, rect.height);
    ctx.restore();
  }
}

function cropToCanvas(crop) {
  return {
    x: state.imageRect.x + crop.x * state.imageRect.scale,
    y: state.imageRect.y + crop.y * state.imageRect.scale,
    width: crop.width * state.imageRect.scale,
    height: crop.height * state.imageRect.scale,
  };
}

function pointerToVideo(event) {
  const bounds = elements.canvas.getBoundingClientRect();
  const size = sourceSize();
  const x = (event.clientX - bounds.left - state.imageRect.x) / state.imageRect.scale;
  const y = (event.clientY - bounds.top - state.imageRect.y) / state.imageRect.scale;
  return {
    x: Math.max(0, Math.min(size.width, Math.round(x))),
    y: Math.max(0, Math.min(size.height, Math.round(y))),
  };
}

function setCrop(crop, options = {}) {
  const size = sourceSize();
  if (!size.width || !size.height) return;
  const x = Math.max(0, Math.min(size.width - 1, Math.round(crop.x)));
  const y = Math.max(0, Math.min(size.height - 1, Math.round(crop.y)));
  const width = Math.max(1, Math.min(size.width - x, Math.round(crop.width)));
  const height = Math.max(1, Math.min(size.height - y, Math.round(crop.height)));
  state.crop = { x, y, width, height };
  elements.cropReadout.textContent = `Crop: x ${x}, y ${y}, w ${width}, h ${height}`;
  updateActionStates();
  drawCanvas();
  if (!options.fromNative) syncNativePreviewSurface();
}

function defaultCrop() {
  const size = sourceSize();
  if (!size.width || !size.height) return;
  setCrop({
    x: Math.round(size.width * 0.08),
    y: Math.round(size.height * 0.68),
    width: Math.round(size.width * 0.84),
    height: Math.round(size.height * 0.2),
  });
}

function updateVideoMeta() {
  if (!state.session) {
    elements.videoMeta.textContent = "No video loaded";
    return;
  }
  const meta = state.session.metadata;
  const duration = Number(meta.duration || 0).toFixed(2);
  const fps = Number(meta.fps || 0).toFixed(3);
  elements.videoMeta.textContent =
    `${state.session.original_name} | ${meta.width}x${meta.height} | ${fps} fps | ${duration}s`;
}

function sessionDuration(session = state.session) {
  const duration = Number(session?.metadata?.duration || 0);
  return Number.isFinite(duration) && duration > 0 ? duration : 0;
}

function updateTimeUI(options = {}) {
  const current = Number(state.previewTime || 0);
  const duration = sessionDuration();
  const totalFrames = state.session ? previewTotalFrameCount() : 0;
  const currentFrame = totalFrames > 0 ? Math.min(totalFrames, clampPreviewFrameIndex(previewFrameIndex(current)) + 1) : 0;
  elements.timeIndicator.textContent = `Frame: ${currentFrame} / ${totalFrames} | Time: ${formatIndicatorTime(current)} / ${formatIndicatorTime(duration)}`;
  if (!options.preserveSlider && !state.previewScrubbing && !elements.seekSlider.matches(":active")) {
    elements.seekSlider.value = String(current);
  }
  if (!options.lightweight) updateSubtitlePreview();
}

function previewFrameIndex(time) {
  const frame = frameSeconds();
  const value = Math.max(0, Number(time || 0));
  return frame > 0 ? Math.max(0, Math.round(value / frame)) : Math.round(value * 1000);
}

function maxPreviewFrameIndex() {
  const count = Number(state.session?.metadata?.frame_count || 0);
  if (Number.isFinite(count) && count > 0) return Math.max(0, Math.floor(count) - 1);
  const duration = sessionDuration();
  return duration > 0 ? previewFrameIndex(duration) : 0;
}

function previewTotalFrameCount() {
  const count = Number(state.session?.metadata?.frame_count || 0);
  if (Number.isFinite(count) && count > 0) return Math.max(1, Math.floor(count));
  const duration = sessionDuration();
  const fps = Number(state.session?.metadata?.fps || 0);
  if (duration > 0 && fps > 0) return Math.max(1, Math.ceil(duration * fps));
  const maxIndex = maxPreviewFrameIndex();
  return maxIndex > 0 ? maxIndex + 1 : 0;
}

function clampPreviewFrameIndex(index) {
  const value = Math.max(0, Math.round(Number(index || 0)));
  const maxIndex = maxPreviewFrameIndex();
  return maxIndex > 0 ? Math.min(value, maxIndex) : value;
}

function frameUrlForIndex(index) {
  if (!state.session) return "";
  const base = state.session.frame_url || `/api/videos/${state.session.id}/frame`;
  const separator = base.includes("?") ? "&" : "?";
  return `${base}${separator}frame_index=${encodeURIComponent(clampPreviewFrameIndex(index))}`;
}

function previewFrameUrl(time) {
  return frameUrlForIndex(previewFrameIndex(time));
}

function nativePreviewApi() {
  return window.pywebview?.api?.update_native_preview || null;
}

function nativePreviewEnabled() {
  return Boolean(nativePreviewApi());
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

function nativePreviewOccluders() {
  return [elements.logDrawer, elements.settingsDrawer, elements.libraryDrawer, elements.storageDrawer, elements.subtitleDrawer]
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

function requestNativePreviewSurfaceSync() {
  syncNativePreviewSurface();
  requestAnimationFrame(() => syncNativePreviewSurface());
}

function currentSubtitlePreviewText() {
  const { cue } = subtitleCueAtTime(state.previewTime);
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
    // Ignore storage failures; the drag still works for the current native frame.
  }
  applySubtitleOverlayPosition();
  if (options.sync !== false) syncNativePreviewSurface();
}

function subtitleOverlayPositionPayload() {
  return storedSubtitleOverlayPosition();
}

function applySubtitleOverlayPosition() {
  const overlay = elements.subtitlePreviewOverlay;
  const container = overlay?.parentElement;
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
  const overlay = elements.subtitlePreviewOverlay;
  const container = overlay?.parentElement;
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
function nativePreviewPayload() {
  const rect = elements.canvas.getBoundingClientRect();
  const occluders = nativePreviewOccluders();
  const showCrop = occluders.length === 0;
  return {
    session_id: state.session?.id || "",
    rect: {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
    },
    time_seconds: state.previewTime,
    cache_mode: state.previewScrubbing ? "active" : "idle",
    crop: showCrop || !state.crop ? state.crop : { x: 0, y: 0, width: 1, height: 1 },
    show_crop: showCrop,
    subtitle_text: currentSubtitlePreviewText(),
    subtitle_box: subtitleOverlayPositionPayload(),
    occluders,
  };
}

function syncNativePreviewSurface() {
  const api = nativePreviewApi();
  if (!api) return false;
  hideWebSubtitlePreview();
  if (!state.session) {
    setNativePreviewVisible(false);
    return true;
  }
  setNativePreviewVisible(true);
  api(nativePreviewPayload()).catch((error) => {
    if (state.nativePreviewReady) {
      setStatus(error.message || "Native preview failed", 0);
    }
  });
  return true;
}

window.subtitleycSyncNativePreview = syncNativePreviewSurface;

function cancelPreviewFrameDebounce() {
  if (state.previewFrameDebounce) {
    window.clearTimeout(state.previewFrameDebounce);
    state.previewFrameDebounce = null;
  }
}

function cancelPreviewFramePrefetches() {
  if (state.previewFramePrefetchTimer) {
    window.clearTimeout(state.previewFramePrefetchTimer);
    state.previewFramePrefetchTimer = null;
  }
  for (const image of state.previewFramePrefetches.values()) {
    image.onload = null;
    image.onerror = null;
    image.src = "";
  }
  state.previewFramePrefetches.clear();
}

function clearPreviewFrameCache() {
  cancelPreviewScrubSync();
  cancelPreviewFramePrefetches();
  state.previewFrameCache.clear();
  state.previewFrameCurrentIndex = null;
  state.previewFrameLastIndex = null;
}

function cachePreviewFrame(index, image) {
  const frameIndex = clampPreviewFrameIndex(index);
  if (state.previewFrameCache.has(frameIndex)) state.previewFrameCache.delete(frameIndex);
  state.previewFrameCache.set(frameIndex, image);
  while (state.previewFrameCache.size > PREVIEW_FRAME_CACHE_LIMIT) {
    const oldest = state.previewFrameCache.keys().next().value;
    state.previewFrameCache.delete(oldest);
  }
}

function showPreviewFrame(index, image) {
  const frameIndex = clampPreviewFrameIndex(index);
  if (state.previewFrameCurrentIndex !== frameIndex) {
    state.previewFrameLastIndex = state.previewFrameCurrentIndex;
    state.previewFrameCurrentIndex = frameIndex;
  }
  if (state.previewFrameCache.has(frameIndex)) {
    state.previewFrameCache.delete(frameIndex);
    state.previewFrameCache.set(frameIndex, image);
  }
  state.image = image;
  state.imageReady = true;
  if (!state.crop) defaultCrop();
  drawCanvas();
}

function schedulePreviewFramePrefetch(index) {
  cancelPreviewFramePrefetches();
  if (!state.session) return;
  state.previewFramePrefetchTimer = window.setTimeout(() => {
    state.previewFramePrefetchTimer = null;
    prefetchPreviewFrames(index);
  }, PREVIEW_PREFETCH_DELAY_MS);
}

function prefetchPreviewFrames(index) {
  if (!state.session || state.previewFrameLoading || state.previewFrameQueuedTime !== null) return;
  const center = clampPreviewFrameIndex(index);
  const previous = state.previewFrameLastIndex;
  const direction = previous === null || previous === undefined || center >= previous ? 1 : -1;
  const offsets = [direction, direction * 2, -direction, direction * 3, -direction * 2, direction * 4];
  let started = 0;
  for (const offset of offsets) {
    if (started >= PREVIEW_MAX_PREFETCHES || state.previewFramePrefetches.size >= PREVIEW_MAX_PREFETCHES) break;
    const frameIndex = clampPreviewFrameIndex(center + offset);
    if (frameIndex === center || state.previewFrameCache.has(frameIndex) || state.previewFramePrefetches.has(frameIndex)) continue;
    prefetchPreviewFrame(frameIndex);
    started += 1;
  }
}

function prefetchPreviewFrame(index) {
  if (!state.session) return;
  const frameIndex = clampPreviewFrameIndex(index);
  const url = frameUrlForIndex(frameIndex);
  if (!url) return;
  const sessionId = state.session.id;
  const image = new Image();
  state.previewFramePrefetches.set(frameIndex, image);
  image.onload = () => {
    state.previewFramePrefetches.delete(frameIndex);
    if (!state.session || state.session.id !== sessionId) return;
    cachePreviewFrame(frameIndex, image);
  };
  image.onerror = () => {
    state.previewFramePrefetches.delete(frameIndex);
  };
  image.src = url;
}

function loadPreviewFrameImage(frameIndex) {
  if (!state.session) return Promise.resolve(null);
  const target = clampPreviewFrameIndex(frameIndex);
  const cached = state.previewFrameCache.get(target);
  if (cached) {
    return Promise.resolve(cached);
  }
  const url = frameUrlForIndex(target);
  if (!url) return Promise.resolve(null);
  const sessionId = state.session.id;
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      if (!state.session || state.session.id !== sessionId) {
        resolve(null);
        return;
      }
      cachePreviewFrame(target, image);
      resolve(image);
    };
    image.onerror = () => reject(new Error("Could not load preview frame"));
    image.src = url;
  });
}
function loadPreviewFrame(time) {
  if (!state.session) return;
  const frameIndex = clampPreviewFrameIndex(previewFrameIndex(time));
  const cached = state.previewFrameCache.get(frameIndex);
  if (cached) {
    if (state.previewFrameLoading) {
      state.previewFrameToken += 1;
      state.previewFrameLoading = false;
      state.previewFrameQueuedTime = null;
    }
    showPreviewFrame(frameIndex, cached);
    schedulePreviewFramePrefetch(frameIndex);
    return;
  }
  if (state.previewFrameLoading) {
    state.previewFrameQueuedTime = time;
    return;
  }
  const url = frameUrlForIndex(frameIndex);
  if (!url) return;
  cancelPreviewFramePrefetches();
  const token = ++state.previewFrameToken;
  state.previewFrameLoading = true;
  state.previewFrameQueuedTime = null;
  const image = new Image();
  image.onload = () => {
    if (token !== state.previewFrameToken) return;
    const queuedTime = state.previewFrameQueuedTime;
    const queuedFrameIndex = queuedTime === null || queuedTime === undefined ? null : clampPreviewFrameIndex(previewFrameIndex(queuedTime));
    state.previewFrameLoading = false;
    cachePreviewFrame(frameIndex, image);
    if (queuedFrameIndex !== null && queuedFrameIndex !== frameIndex) {
      flushQueuedPreviewFrame();
      return;
    }
    showPreviewFrame(frameIndex, image);
    schedulePreviewFramePrefetch(frameIndex);
    flushQueuedPreviewFrame();
  };
  image.onerror = () => {
    if (token !== state.previewFrameToken) return;
    state.previewFrameLoading = false;
    setStatus("Could not load preview frame", 0);
    drawCanvas();
    flushQueuedPreviewFrame();
  };
  image.src = url;
}

function flushQueuedPreviewFrame() {
  const queuedTime = state.previewFrameQueuedTime;
  if (queuedTime === null || queuedTime === undefined) return;
  state.previewFrameQueuedTime = null;
  requestPreviewFrame(queuedTime, { immediate: true });
}

function cancelPreviewScrubSync() {
  if (state.previewScrubSyncTimer) {
    window.clearTimeout(state.previewScrubSyncTimer);
    state.previewScrubSyncTimer = null;
  }
  state.previewScrubPendingTime = null;
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
    updateTimeUI({ preserveSlider: true, lightweight: true });
  });
}

function schedulePreviewScrubSync(time) {
  state.previewScrubPendingTime = Number(time || 0);
  if (state.previewScrubSyncTimer) return;
  const elapsed = performance.now() - Number(state.previewScrubLastSyncAt || 0);
  const delay = Math.max(0, PREVIEW_SCRUB_SYNC_MS - elapsed);
  state.previewScrubSyncTimer = window.setTimeout(() => {
    state.previewScrubSyncTimer = null;
    const pending = state.previewScrubPendingTime;
    state.previewScrubPendingTime = null;
    state.previewScrubLastSyncAt = performance.now();
    requestPreviewFrame(pending ?? state.previewTime, { immediate: true, fromScrubThrottle: true });
  }, delay);
}

function flushPreviewScrubSync() {
  const pending = state.previewScrubPendingTime;
  cancelPreviewScrubSync();
  state.previewScrubLastSyncAt = performance.now();
  requestPreviewFrame(pending ?? state.previewTime, { immediate: true, fromScrubThrottle: true });
}

function requestPreviewFrame(time, options = {}) {
  if (nativePreviewEnabled() && state.previewScrubbing && !options.fromScrubThrottle && !options.immediate) {
    schedulePreviewScrubSync(time);
    return;
  }
  if (syncNativePreviewSurface()) return;
  cancelPreviewFrameDebounce();
  if (options.immediate) {
    loadPreviewFrame(time);
    return;
  }
  state.previewFrameDebounce = window.setTimeout(() => {
    state.previewFrameDebounce = null;
    loadPreviewFrame(time);
  }, PREVIEW_FRAME_DEBOUNCE_MS);
}

function seekTo(time, options = {}) {
  if (!state.session) return;
  const duration = sessionDuration();
  const upper = duration > 0 ? duration : Number(time || 0);
  const clamped = Math.max(0, Math.min(upper, Number(time || 0)));
  state.previewTime = clamped;
  const smoothScrub = state.previewScrubbing && !options.immediate;
  if (smoothScrub) {
    schedulePreviewScrubUi();
    if (options.refresh !== false) {
      if (nativePreviewEnabled()) syncNativePreviewSurface();
      else requestPreviewFrame(clamped);
    }
    return;
  }
  cancelPreviewScrubUi();
  elements.seekSlider.value = String(clamped);
  updateTimeUI();
  if (options.refresh !== false) {
    requestPreviewFrame(clamped, { immediate: Boolean(options.immediate) });
  }
}

function initialPreviewTime() {
  const duration = sessionDuration();
  return duration > 0 ? duration * 0.25 : 0;
}

function stopPreviewPlayback(updateButton = true) {
  if (state.previewTimer) {
    window.clearInterval(state.previewTimer);
    state.previewTimer = null;
  }
  state.previewPlaying = false;
  if (updateButton) {
    elements.playButton.textContent = "Play";
  }
}

function tickPreviewPlayback() {
  if (!state.previewPlaying || !state.session || state.previewFrameLoading) return;
  const duration = sessionDuration();
  const next = state.previewTime + 1 / PREVIEW_PLAYBACK_FPS;
  if (duration > 0 && next >= duration) {
    seekTo(duration, { immediate: true });
    stopPreviewPlayback();
    return;
  }
  seekTo(next, { immediate: true });
}

function startPreviewPlayback() {
  if (!state.session || sessionDuration() <= 0) return;
  if (state.previewTime >= sessionDuration()) {
    seekTo(0, { immediate: true });
  }
  state.previewPlaying = true;
  elements.playButton.textContent = "Pause";
  tickPreviewPlayback();
  state.previewTimer = window.setInterval(tickPreviewPlayback, Math.round(1000 / PREVIEW_PLAYBACK_FPS));
}

function togglePreviewPlayback() {
  if (state.previewPlaying) {
    stopPreviewPlayback();
  } else {
    startPreviewPlayback();
  }
}

function beginPreviewScrub() {
  if (!state.session || state.previewScrubbing) return;
  state.previewScrubbing = true;
  state.previewScrubWasPlaying = Boolean(state.previewPlaying);
  stopPreviewPlayback();
}

function finishPreviewScrub() {
  if (!state.previewScrubbing) return;
  const shouldResume = state.previewScrubWasPlaying;
  state.previewScrubbing = false;
  state.previewScrubWasPlaying = false;
  cancelPreviewScrubUi();
  updateTimeUI();
  cancelPreviewScrubSync();
  if (shouldResume && state.session && state.previewTime < sessionDuration()) {
    startPreviewPlayback();
  }
}

function sessionFrameSeconds(session = state.session) {
  const fps = Number(session?.metadata?.fps || 0);
  return fps > 0 ? 1 / fps : 1 / 24;
}

function frameSeconds() {
  return sessionFrameSeconds();
}

function formatMinDurationForSession(session = state.session) {
  const fps = Number(session?.metadata?.fps || 0);
  if (!fps || fps <= 0) return "0.04";
  const frameDuration = Math.max(0.0001, 1 / fps);
  return frameDuration.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
}

function setMinDurationFromSession(session = state.session) {
  elements.minDurationInput.value = formatMinDurationForSession(session);
}

function updateDownloadLinkLabel(format) {
  elements.downloadLinkLabel.textContent = `Download .${format || "srt"}`;
}

function publishSubtitleFormatUpdate(format = state.subtitleFormat) {
  if (!state.session) return;
  localStorage.setItem(
    "subtitleyc:subtitle-format-updated",
    JSON.stringify({
      sessionId: state.session.id,
      subtitle_format: format || "srt",
      subtitle_filename: state.subtitleFilename || safeSubtitleName(state.session.original_name || "subtitles", format || "srt"),
      at: Date.now(),
    })
  );
}

function clearSubtitleDownload(filename = "subtitles.srt", format = selectedSubtitleFormat()) {
  state.subtitleUrl = null;
  state.subtitleFormat = format || "srt";
  state.subtitleFilename = filename;
  elements.downloadLink.classList.add("disabled");
  elements.downloadLink.href = "#";
  elements.downloadLink.setAttribute("download", state.subtitleFilename);
  updateDownloadLinkLabel(state.subtitleFormat);
  resetSubtitleCues();
  updateActionStates();
}

function setSubtitleDownload(subtitleUrl, originalName, format = "srt", filename = null, options = {}) {
  state.subtitleUrl = subtitleUrl;
  state.subtitleFormat = format || "srt";
  state.subtitleFilename = filename || safeSubtitleName(originalName, state.subtitleFormat);
  elements.downloadLink.href = subtitleUrl;
  elements.downloadLink.setAttribute("download", state.subtitleFilename);
  elements.downloadLink.classList.remove("disabled");
  updateDownloadLinkLabel(state.subtitleFormat);
  updateActionStates();
  if (options.loadCues !== false && state.session) {
    loadSubtitleCues({ silent: true }).catch(() => undefined);
  }
}

function cancelPreviewWarmup() {
  const jobId = state.previewWarmupJobId;
  state.previewWarmupJobId = null;
  if (jobId) {
    fetch(`/api/jobs/${jobId}/cancel`, { method: "POST" }).catch(() => undefined);
  }
}

async function startPreviewWarmup(session, options = {}) {
  if (!session?.id) return null;
  let jobId = null;
  try {
    const payload = await fetchJson(`/api/videos/${session.id}/preview-cache`, { method: "POST" });
    jobId = payload.job_id;
    state.previewWarmupJobId = jobId;
    const result = await pollJob(jobId, {
      kind: "preview",
      label: options.label || "Preview cache",
      cancelable: options.cancelable !== false,
      removeDelayMs: options.removeDelayMs || 6000,
    });
    if (state.previewWarmupJobId === jobId) {
      state.previewWarmupJobId = null;
    }
    if (!options.silentStatus && state.session?.id === session.id && result?.cached_frames) {
      const limited = result.limited ? "sampled" : "ready";
      setStatus(`Preview cache ${limited}: ${result.cached_frames} frames`, 1);
    }
    return result || null;
  } catch (error) {
    if (state.previewWarmupJobId === jobId) {
      state.previewWarmupJobId = null;
    }
    if (error.cancelled) return null;
    if (!options.silentStatus) {
      setStatus(error.message || "Preview cache failed", 0);
    }
    return null;
  }
}

async function loadSession(session) {
  const loadToken = state.videoLoadToken + 1;
  state.videoLoadToken = loadToken;
  stopPreviewPlayback(false);
  cancelPreviewWarmup();
  cancelPreviewFrameDebounce();
  clearPreviewFrameCache();
  state.previewFrameToken += 1;
  state.previewFrameLoading = false;
  state.previewFrameQueuedTime = null;
  state.previewPreparing = false;
  state.previewScrubbing = false;
  state.previewScrubWasPlaying = false;
  state.session = session;
  state.crop = null;
  state.image = new Image();
  state.imageReady = false;
  state.videoReady = false;
  updateNativeVideoVisibility();
  state.dragStart = null;
  state.pendingInitialPreviewSeek = false;
  state.subtitleFormat = selectedSubtitleFormat();
  state.subtitleFilename = safeSubtitleName(session.original_name, state.subtitleFormat);
  setMinDurationFromSession(session);
  const initialTime = Math.max(0, Number(session.metadata.duration || 0) * 0.25);
  state.previewTime = initialTime;
  updateVideoMeta();
  resizeCanvas();
  defaultCrop();
  updateActionStates();
  setStatus("Video loaded", 1);

  if (session.subtitle_url) {
    setSubtitleDownload(
      session.subtitle_url,
      session.original_name,
      session.subtitle_format || state.subtitleFormat,
      session.subtitle_filename || null
    );
  } else {
    clearSubtitleDownload(state.subtitleFilename, state.subtitleFormat);
  }
  elements.startInput.value = "0";
  elements.endInput.value = "";
  elements.seekSlider.value = String(initialTime);
  elements.seekSlider.max = String(session.metadata.duration || 0);
  elements.seekSlider.step = "any";
  updateTimeUI();

  const initialFrameIndex = clampPreviewFrameIndex(previewFrameIndex(initialTime));
  requestPreviewFrame(initialTime, { immediate: true });
  schedulePreviewFramePrefetch(initialFrameIndex);
  drawCanvas();
  syncNativePreviewSurface();
  updateNativeVideoVisibility();
  updateActionStates();
  publishSubtitleFormatUpdate(state.subtitleFormat);

}

async function removeCurrentSubtitles() {
  if (!state.session || (!state.subtitleUrl && !state.subtitleCues.length)) return;
  if (state.subtitleDirty) {
    setStatus("Save or undo subtitle changes before removing subtitles", 0);
    openSubtitleEditor();
    return;
  }

  const sessionId = state.session.id;
  const originalName = state.session.original_name || "subtitles";
  const format = state.subtitleFormat || selectedSubtitleFormat();
  const session = await fetchJson(`/api/videos/${encodeURIComponent(sessionId)}/subtitles`, { method: "DELETE" });
  if (state.session?.id !== sessionId) return;

  state.session = session;
  closeSubtitleEditor();
  clearSubtitleDownload(safeSubtitleName(originalName, format), format);
  syncNativePreviewSurface();
  try {
    localStorage.setItem(
      "subtitleyc:subtitle-updated",
      JSON.stringify({ sessionId, detached: true, at: Date.now() }),
    );
  } catch (_error) {
    // Cross-window synchronization is best-effort.
  }
  await refreshLibrary().catch(() => undefined);
  setStatus("Subtitles removed from preview. They remain available in Previous Projects.", 1);
}

async function removeCurrentVideo() {
  if (!state.session) return;
  if (state.subtitleDirty) {
    setStatus("Save or undo subtitle changes before removing the video", 0);
    openSubtitleEditor();
    return;
  }

  stopPreviewPlayback(false);
  cancelPreviewWarmup();
  cancelPreviewFrameDebounce();
  clearPreviewFrameCache();
  state.videoLoadToken += 1;
  state.previewFrameToken += 1;
  state.previewFrameLoading = false;
  state.previewFrameQueuedTime = null;
  state.previewPreparing = false;
  state.previewScrubbing = false;
  state.previewScrubWasPlaying = false;
  state.session = null;
  state.crop = null;
  state.dragStart = null;
  state.previewTime = 0;
  state.image = new Image();
  state.imageReady = false;
  state.videoReady = false;
  closeSubtitleEditor();
  clearSubtitleDownload("subtitles.srt", selectedSubtitleFormat());
  elements.video.removeAttribute("src");
  try {
    elements.video.load();
  } catch (_error) {
    // Browser media teardown is best-effort.
  }
  elements.startInput.value = "0";
  elements.endInput.value = "";
  elements.seekSlider.value = "0";
  elements.seekSlider.max = "0";
  elements.cropReadout.textContent = "Crop: none";
  setMinDurationFromSession(null);
  updateVideoMeta();
  updateTimeUI();
  setNativePreviewVisible(false);
  resizeCanvas();
  updateActionStates();
  await refreshLibrary().catch(() => undefined);
  setStatus("Video removed from preview. It remains available in Previous Projects.", 1);
}

async function applyEditorSessionUpdate(payload = {}, options = {}) {
  const nextSessionId = String(payload.sessionId || "");
  if (!nextSessionId) return;

  if (state.session?.id && state.session.id !== nextSessionId) return;

  if (!state.session) {
    const session = await fetchJson(`/api/videos/${encodeURIComponent(nextSessionId)}`);
    if (state.session) return;
    await loadSession(session);
    setStatus("Loaded imported video copy", 1);
    setStatus("Loaded video from SubtitleYC Editor", 1);
  }

  if (options.loadSubtitles || payload.hasSubtitles) {
    await loadSubtitleCues({ silent: true }).catch(() => undefined);
  }
}

function showSelectedLanguageStatus() {
  if (!state.videocrReady) {
    setStatus("VideOCR CLI is missing. Install VideOCR or set VIDEOCR_CLI to videocr-cli.exe.", 0);
  }
}
function setHidden(element, hidden) {
  if (element) element.hidden = Boolean(hidden);
}

function syncSourceSubtitleControls() {
  const hasTrack = Boolean(selectedSubtitleTrack());
  setHidden(elements.subtitleSourceTools, false);
  setHidden(elements.subtitleTrackRow, !state.subtitleTracks.length);
  setHidden(elements.subtitleDownloadButton, !hasTrack);
}

function selectedFormatSelector() {
  return elements.formatInput.value.trim() || null;
}

function cancelFormatProbeTimer() {
  if (state.formatProbeTimer) {
    window.clearTimeout(state.formatProbeTimer);
    state.formatProbeTimer = null;
  }
}

function isValidDownloadUrl(value) {
  try {
    const parsed = new URL(String(value || "").trim());
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch (_error) {
    return false;
  }
}

function resetFormatOptions() {
  state.urlFormats = [];
  state.formatProbeUrl = "";
  elements.formatInput.replaceChildren(new Option("Best available", ""));
  elements.formatInput.removeAttribute("title");
}

function renderUrlFormats(payload, url) {
  const formats = Array.isArray(payload?.formats) ? payload.formats : [];
  state.urlFormats = formats;
  state.formatProbeUrl = url || elements.urlInput.value.trim();
  elements.formatInput.replaceChildren(new Option(formats.length ? "Best available (recommended)" : "Best available", ""));
  if (formats.length) {
    elements.formatInput.title = "Best available is recommended. Choose a listed format only when you need a specific quality.";
  } else {
    elements.formatInput.removeAttribute("title");
  }

  formats.forEach((format, index) => {
    const option = document.createElement("option");
    option.value = format.selector || format.id || "";
    const label = format.display || format.selector || format.id || "Format";
    option.textContent = index === 0 ? `Recommended: ${label}` : label;
    elements.formatInput.appendChild(option);
  });
  return formats.length;
}

function scheduleUrlFormatProbe() {
  cancelFormatProbeTimer();
  const url = elements.urlInput.value.trim();
  if (!isValidDownloadUrl(url)) {
    state.formatProbePending = false;
    updateActionStates();
    return;
  }
  state.formatProbePending = true;
  updateActionStates();
  state.formatProbeTimer = window.setTimeout(() => {
    state.formatProbeTimer = null;
    checkUrlFormats({ automatic: true }).catch((error) => setStatus(error.message || error, 0));
  }, URL_FORMAT_PROBE_DEBOUNCE_MS);
}

async function checkUrlFormats(options = {}) {
  const url = elements.urlInput.value.trim();
  if (!url || state.formatProbeBusy) {
    state.formatProbePending = false;
    updateActionStates();
    return;
  }
  cancelFormatProbeTimer();
  state.formatProbePending = false;
  state.formatProbeBusy = true;
  updateActionStates();
  setStatus(options.automatic ? "Checking formats for this URL" : "Checking available video formats", 0.2);
  try {
    const payload = await fetchJson("/api/videos/url/formats", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (elements.urlInput.value.trim() !== url) return;
    const count = renderUrlFormats(payload, url);
    if (count) {
      setStatus(`Ready to download. ${count} video format${count === 1 ? "" : "s"} found.`, 1);
    } else {
      setStatus("Ready to download with best available format", 1);
    }
  } catch (error) {
    if (elements.urlInput.value.trim() === url) {
      resetFormatOptions();
      setStatus(error.message || error, 0);
    }
  } finally {
    state.formatProbePending = false;
    state.formatProbeBusy = false;
    updateActionStates();
  }
}
function selectedMaxHeight() {
  return null;
}
function selectedDownloadDir() {
  const value = elements.downloadDirInput.value.trim();
  return value || null;
}
function selectedLanguage() {
  return elements.languageInput.value.trim() || "eng+chi_sim";
}

function selectedDownloadSubtitleLanguages() {
  const language = selectedLanguage();
  const wantsEnglish = language.includes("eng");
  const wantsTraditional = language.includes("chi_tra");
  const wantsSimplified = language.includes("chi_sim");
  if (wantsEnglish && wantsTraditional) return "en,zh-Hant,zh-TW";
  if (wantsEnglish && wantsSimplified) return "en,zh-Hans,zh-CN";
  if (wantsTraditional) return "zh-Hant,zh-TW,en.*";
  if (wantsSimplified) return "zh-Hans,zh-CN,en.*";
  return OCR_SITE_SUBTITLE_LANGUAGES[language] || "en.*";
}

function subtitleLanguageMatches(language, requested) {
  const actual = String(language || "").trim();
  const wanted = String(requested || "").trim();
  if (!actual || !wanted) return false;
  if (wanted === "all" || actual.toLowerCase() === wanted.toLowerCase()) return true;
  try {
    return new RegExp(`^${wanted}$`, "i").test(actual);
  } catch (_error) {
    return false;
  }
}

function subtitleTrackDisplay(track) {
  const label = track.label || track.language || "Subtitle";
  const source = track.source === "auto" ? "Auto" : "Manual";
  const language = track.language ? ` (${track.language})` : "";
  const formats = Array.isArray(track.formats) && track.formats.length ? ` - ${track.formats.slice(0, 3).join(", ")}` : "";
  return track.display || `${label}${language} - ${source}${formats}`;
}

function preferredSubtitleTrack(tracks) {
  const requested = selectedDownloadSubtitleLanguages()
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  let best = null;
  let bestScore = Number.MAX_SAFE_INTEGER;

  for (const track of tracks) {
    const sourcePenalty = track.source === "manual" ? 0 : 1;
    for (let index = 0; index < requested.length; index += 1) {
      if (subtitleLanguageMatches(track.language, requested[index])) {
        const score = index * 10 + sourcePenalty;
        if (score < bestScore) {
          best = track;
          bestScore = score;
        }
      }
    }
  }

  if (best) return best;
  return (
    tracks.find((track) => track.source === "manual" && subtitleLanguageMatches(track.language, "en.*")) ||
    tracks.find((track) => subtitleLanguageMatches(track.language, "en.*")) ||
    tracks[0] ||
    null
  );
}

function clearSubtitleTracks() {
  state.subtitleTracks = [];
  state.subtitleProbeUrl = "";
  elements.subtitleTrackInput.textContent = "";
  elements.subtitleTrackRow.hidden = true;
  elements.subtitleDownloadButton.hidden = true;
}

function renderSubtitleTracks(payload, url) {
  const tracks = Array.isArray(payload?.tracks) ? payload.tracks : [];
  state.subtitleTracks = tracks;
  state.subtitleProbeUrl = url || elements.urlInput.value.trim();
  elements.subtitleTrackInput.textContent = "";

  if (!tracks.length) {
    elements.subtitleTrackRow.hidden = true;
    return 0;
  }

  for (const track of tracks) {
    const option = document.createElement("option");
    option.value = track.id || `${track.source}:${track.language}`;
    option.textContent = subtitleTrackDisplay(track);
    elements.subtitleTrackInput.appendChild(option);
  }

  const preferred = preferredSubtitleTrack(tracks);
  if (preferred) {
    elements.subtitleTrackInput.value = preferred.id || `${preferred.source}:${preferred.language}`;
  }
  elements.subtitleTrackRow.hidden = false;
  elements.subtitleDownloadButton.hidden = false;
  elements.downloadSubtitlesInput.checked = true;
  return tracks.length;
}

function selectedSubtitleTrack() {
  const selectedId = elements.subtitleTrackInput.value;
  return state.subtitleTracks.find((track) => (track.id || `${track.source}:${track.language}`) === selectedId) || null;
}

function selectedSubtitleDownloadOptions() {
  const enabled = Boolean(elements.downloadSubtitlesInput?.checked);
  const track = enabled ? selectedSubtitleTrack() : null;
  return {
    download_subtitles: enabled,
    subtitle_languages: track ? track.language : selectedDownloadSubtitleLanguages(),
    subtitle_source: track ? track.source : null,
  };
}

async function checkUrlSubtitles() {
  const url = elements.urlInput.value.trim();
  if (!url || state.subtitleProbeBusy) return;
  state.subtitleProbeBusy = true;
  updateActionStates();
  setStatus("Checking available site subtitles", 0.2);
  try {
    const payload = await fetchJson("/api/videos/url/subtitles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const count = renderSubtitleTracks(payload, url);
    if (count) {
      setStatus(`Found ${count} site subtitle track${count === 1 ? "" : "s"}`, 1);
    } else {
      setStatus("No site subtitles found for this URL", 0);
    }
  } catch (error) {
    clearSubtitleTracks();
    setStatus(error.message || error, 0);
  } finally {
    state.subtitleProbeBusy = false;
    updateActionStates();
  }
}
function suggestedSiteSubtitleFilename(track) {
  const language = String(track?.language || "subtitle").replace(/[^A-Za-z0-9._-]+/g, "_") || "subtitle";
  const source = track?.source === "auto" ? "auto" : "manual";
  return safeSubtitleName(`site-${source}-${language}`, "srt");
}

async function chooseSiteSubtitleOutputPath(track) {
  const chooser = window.pywebview?.api?.choose_subtitle_save_path;
  if (!chooser) return null;
  setStatus("Choose where to save the subtitle file", 1);
  const result = await chooser(suggestedSiteSubtitleFilename(track));
  if (result?.ok) return result.path || null;
  if (result?.cancelled) return false;
  throw new Error(result?.message || "Could not choose subtitle save location");
}

async function downloadSelectedSubtitle() {
  const url = elements.urlInput.value.trim();
  const track = selectedSubtitleTrack();
  if (!url) {
    setStatus("Paste a URL before downloading subtitles", 0);
    return;
  }

  if (!track) {
    setStatus("Check subtitles and choose a track first", 0);
    return;
  }
  if (hasActiveJobKind("download") || hasActiveJobKind("subtitle_download")) return;

  const outputPath = await chooseSiteSubtitleOutputPath(track);
  if (outputPath === false) {
    setStatus("Subtitle download cancelled", 0);
    return;
  }

  const payload = await fetchJson("/api/videos/url/subtitle", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url,
      download_dir: outputPath ? null : selectedDownloadDir(),
      output_path: outputPath || null,
      subtitle_language: track.language,
      subtitle_source: track.source,
    }),
  });
  const jobId = payload.job_id;
  const result = await pollJob(jobId, {
    kind: "subtitle_download",
    label: `Subtitle: ${track.language}`,
    autoRemoveComplete: false,
  });
  setActivity(jobId, {
    message: `Saved ${result.filename || "subtitle file"}`,
    progress: 1,
    status: "complete",
    cancelable: false,
  });
  scheduleActivityRemoval(jobId, 12000);
  setStatus(`Subtitle saved: ${result.path || result.filename || "subtitle file"}`, 1);
}
function isChineseLanguage(language) {
  return language.includes("chi_") || language === "ch" || language === "chinese_cht";
}

function setOcrRangeLabels() {
  elements.confidenceValue.textContent = elements.confidenceInput.value;
  elements.similarityValue.textContent = (Number(elements.similarityInput.value) / 100).toFixed(2);
  elements.ssimValue.textContent = (Number(elements.ssimInput.value) / 100).toFixed(2);
}
function setSettingsRangeLabels() {
  elements.settingConfidenceValue.textContent = elements.settingConfidenceInput.value;
  elements.settingSimilarityValue.textContent = (Number(elements.settingSimilarityInput.value) / 100).toFixed(2);
  elements.settingSsimValue.textContent = (Number(elements.settingSsimInput.value) / 100).toFixed(2);
}

function applyLanguageDefaults() {
  elements.frameStepInput.value = "0";
  elements.confidenceInput.value = "65";
  elements.similarityInput.value = "72";
  elements.ssimInput.value = "88";
  elements.mergeGapInput.value = "0";
  elements.brightnessInput.value = "";
  elements.maxWidthInput.value = "1280";
  setMinDurationFromSession();
  elements.useServerModelInput.checked = true;
  elements.useFullframeInput.checked = false;
  elements.angleClsInput.checked = false;
  elements.postProcessingInput.checked = false;
  elements.normalizeChineseInput.checked = true;
  setOcrRangeLabels();
}
function currentOcrPayload() {
  const endValue = elements.endInput.value.trim();
  const brightnessValue = elements.brightnessInput.value.trim();
  const framesToSkip = Math.max(0, Number(elements.frameStepInput.value || 0));
  return {
    crop: state.crop,
    language: selectedLanguage(),
    subtitle_format: selectedSubtitleFormat(),
    frame_step: framesToSkip + 1,
    min_confidence: Number(elements.confidenceInput.value || 65),
    similarity: Number(elements.similarityInput.value || 72) / 100,
    max_gap_frames: 0,
    merge_gap_seconds: Number(elements.mergeGapInput.value || 0),
    start_seconds: Number(elements.startInput.value || 0),
    end_seconds: endValue ? Number(endValue) : null,
    brightness_threshold: brightnessValue ? Number(brightnessValue) : null,
    ssim_threshold: Number(elements.ssimInput.value || 88) / 100,
    max_image_width: Number(elements.maxWidthInput.value || 1280),
    min_subtitle_duration: Number(elements.minDurationInput.value || 0.04),
    timing_offset_seconds: Number(elements.timingOffsetInput.value || 0) * frameSeconds(),
    snap_to_frame: elements.snapToFrameInput.checked,
    normalize_chinese: elements.normalizeChineseInput.checked,
    use_server_model: elements.useServerModelInput.checked,
    use_gpu: elements.useGpuInput.checked,
    use_fullframe: elements.useFullframeInput.checked,
    use_angle_cls: elements.angleClsInput.checked,
    post_processing: elements.postProcessingInput.checked,
    subtitle_position: "center",
  };
}

elements.logsButton.addEventListener("click", openLogs);
elements.logsCloseButton.addEventListener("click", closeLogs);
elements.logOverlay.addEventListener("click", closeLogs);
elements.logFilter.addEventListener("change", () => {
  refreshLogs({ forceBottom: true }).catch((error) => setStatus(error.message, 0));
});
elements.logRefreshButton.addEventListener("click", () => {
  refreshLogs({ forceBottom: true }).catch((error) => setStatus(error.message, 0));
});
elements.logCopyButton.addEventListener("click", () => {
  copyLogs().catch((error) => setStatus(error.message || error, 0));
});
elements.logSaveButton.addEventListener("click", saveLogs);
elements.logClearButton.addEventListener("click", () => {
  clearLogs().catch((error) => setStatus(error.message || error, 0));
});
elements.libraryButton.addEventListener("click", openLibrary);
elements.recentProjectsLibraryButton?.addEventListener("click", openLibrary);
elements.libraryCloseButton.addEventListener("click", closeLibrary);
elements.libraryOverlay.addEventListener("click", closeLibrary);
elements.libraryRefreshButton.addEventListener("click", () => {
  refreshLibrary().catch((error) => setStatus(error.message || error, 0));
});
elements.storageButton.addEventListener("click", openStorage);
elements.storageCloseButton.addEventListener("click", closeStorage);
elements.storageOverlay.addEventListener("click", closeStorage);
elements.storageRefreshButton.addEventListener("click", () => {
  refreshStorage().catch((error) => setStatus(error.message || error, 0));
});
elements.storageClearButton.addEventListener("click", () => {
  clearStorageCategories().catch((error) => setStatus(error.message || error, 0));
});
elements.confirmDialogCancelButton.addEventListener("click", () => finishConfirmation(false));
elements.confirmDialogAcceptButton.addEventListener("click", () => finishConfirmation(true));
elements.confirmDialogOverlay.addEventListener("click", (event) => {
  if (event.target === elements.confirmDialogOverlay) finishConfirmation(false);
});
elements.subtitleEditorButton.addEventListener("click", () => {
  openSubtitleEditorTab().catch((error) => setStatus(error.message || "Could not open SubtitleYC Editor", 0));
});
elements.subtitleUploadButton.addEventListener("click", openSubtitleImportPicker);
elements.removeSubtitlesButton?.addEventListener("click", () => {
  removeCurrentSubtitles().catch((error) => setStatus(error.message || "Could not remove subtitles", 0));
});
elements.removeVideoButton?.addEventListener("click", () => {
  removeCurrentVideo().catch((error) => setStatus(error.message || "Could not remove video", 0));
});
elements.copySystemInfoButton?.addEventListener("click", () => {
  copySystemInfo().catch((error) => setStatus(error.message || "Could not copy system information", 0));
});
elements.subtitleCloseButton.addEventListener("click", closeSubtitleEditor);
elements.subtitleOverlay.addEventListener("click", closeSubtitleEditor);
elements.subtitleRefreshButton.addEventListener("click", () => {
  loadSubtitleCues().catch((error) => setStatus(error.message || error, 0));
});
elements.subtitleAddCueButton.addEventListener("click", addSubtitleCue);
elements.subtitleUndoButton.addEventListener("click", undoSubtitleEdit);
elements.subtitleRedoButton.addEventListener("click", redoSubtitleEdit);
elements.subtitleSaveButton.addEventListener("click", () => {
  saveSubtitleCues().catch((error) => setStatus(error.message || error, 0));
});
elements.subtitleImportButton.addEventListener("click", openSubtitleImportPicker);
elements.subtitleImportInput.addEventListener("change", () => {
  const file = elements.subtitleImportInput.files?.[0];
  elements.subtitleImportInput.value = "";
  if (file) {
    importSubtitleFile(file).catch((error) => setStatus(error.message || error, 0));
  }
});
elements.subtitleNudgeAllBackButton.addEventListener("click", () => nudgeAllSubtitles(-subtitleShiftFrameCount()));
elements.subtitleNudgeAllForwardButton.addEventListener("click", () => nudgeAllSubtitles(subtitleShiftFrameCount()));
elements.subtitleSnapButton.addEventListener("click", snapSubtitleCuesToFrames);
window.addEventListener("subtitleyc-native-preview-ready", () => {
  state.nativePreviewReady = true;
  updateSubtitlePreview();
  syncNativePreviewSurface();
});
window.addEventListener("subtitleyc-native-preview-crop", (event) => {
  if (event.detail) setCrop(event.detail, { fromNative: true });
});
window.addEventListener("subtitleyc-native-preview-subtitle-box", (event) => {
  if (event.detail) saveSubtitleOverlayPosition(event.detail, { sync: false });
});
window.addEventListener("resize", () => {
  applySubtitleOverlayPosition();
  syncNativePreviewSurface();
});
window.addEventListener("pointerup", finishPreviewScrub);
window.addEventListener("scroll", () => syncNativePreviewSurface(), true);
window.addEventListener("storage", (event) => {
  if (event.key === SUBTITLE_OVERLAY_POSITION_STORAGE_KEY) {
    applySubtitleOverlayPosition();
    syncNativePreviewSurface();
    return;
  }

  if (event.key === "subtitleyc:editor-session-updated") {
    try {
      const payload = JSON.parse(event.newValue || "{}");
      applyEditorSessionUpdate(payload, { loadSubtitles: payload.reason === "subtitles" || Boolean(payload.hasSubtitles) }).catch(() => undefined);
    } catch (_error) {
      // Ignore malformed cross-tab session notices.
    }
    return;
  }

  if (event.key !== "subtitleyc:subtitle-updated") return;
  try {
    const payload = JSON.parse(event.newValue || "{}");
    if (state.session?.id === payload.sessionId) {
      if (payload.detached) {
        state.session = {
          ...state.session,
          srt_path: null,
          subtitle_url: null,
          srt_url: null,
          subtitle_filename: null,
        };
        closeSubtitleEditor();
        clearSubtitleDownload(
          safeSubtitleName(state.session.original_name || "subtitles", state.subtitleFormat),
          state.subtitleFormat,
        );
        syncNativePreviewSurface();
        setStatus("Subtitles removed from preview. They remain available in Previous Projects.", 1);
      } else {
        loadSubtitleCues({ silent: true }).catch(() => undefined);
      }
    } else if (!state.session && payload.sessionId) {
      if (!payload.detached) applyEditorSessionUpdate(payload, { loadSubtitles: true }).catch(() => undefined);
    }
  } catch (_error) {
    // Ignore malformed cross-tab update notices.
  }
});
window.addEventListener("keydown", (event) => {
  if (state.confirmDialogResolve) {
    if (event.key === "Escape") {
      event.preventDefault();
      finishConfirmation(false);
    } else if (event.key === "Tab") {
      event.preventDefault();
      const actions = [elements.confirmDialogCancelButton, elements.confirmDialogAcceptButton];
      const currentIndex = actions.indexOf(document.activeElement);
      const step = event.shiftKey ? -1 : 1;
      const nextIndex = currentIndex < 0 ? 0 : (currentIndex + step + actions.length) % actions.length;
      actions[nextIndex].focus();
    }
    return;
  }
  if (shouldUseSubtitleHistoryShortcut(event)) {
    event.preventDefault();
    const key = event.key.toLowerCase();
    if (key === "y" || (key === "z" && event.shiftKey)) redoSubtitleEdit();
    else undoSubtitleEdit();
    return;
  }
  if (handleGlobalKeyboardShortcut(event)) return;
  if (event.key === "Escape" && !elements.libraryDrawer.hidden) {
    closeLibrary();
  }
  if (event.key === "Escape" && !elements.logDrawer.hidden) {
    closeLogs();
  }
  if (event.key === "Escape" && !elements.settingsDrawer.hidden) {
    closeSettings();
  }
  if (event.key === "Escape" && !elements.storageDrawer.hidden) {
    closeStorage();
  }
  if (event.key === "Escape" && !elements.subtitleDrawer.hidden) {
    closeSubtitleEditor();
  }
});
elements.settingsButton.addEventListener("click", openSettings);
elements.settingsCloseButton.addEventListener("click", closeSettings);
elements.settingsOverlay.addEventListener("click", closeSettings);
elements.settingsSaveButton.addEventListener("click", () => {
  saveSettings().catch((error) => setStatus(error.message || error, 0));
});

elements.settingsResetButton.addEventListener("click", () => {
  resetSettings().catch((error) => setStatus(error.message || error, 0));
});
elements.settingDownloadDirButton.addEventListener("click", async () => {
  if (!window.pywebview?.api?.choose_download_dir) {
    elements.settingDownloadDirInput.focus();
    return;
  }

  try {
    const result = await window.pywebview.api.choose_download_dir(elements.settingDownloadDirInput.value.trim());
    if (result?.ok) {
      elements.settingDownloadDirInput.value = result.path || "";
      scheduleSettingsAutosave();
    } else if (result && !result.cancelled) {
      setStatus(result.message || "Could not choose folder", 0);
    }
  } catch (error) {
    setStatus(error.message || error, 0);
  }
});
elements.urlInput.addEventListener("input", () => {
  clearSubtitleTracks();
  resetFormatOptions();
  updateActionStates();
  scheduleUrlFormatProbe();
});
elements.formatProbeButton.addEventListener("click", () => {
  checkUrlFormats().catch((error) => setStatus(error.message || error, 0));
});
elements.downloadSubtitlesInput.addEventListener("change", updateActionStates);
elements.subtitleProbeButton.addEventListener("click", () => {
  checkUrlSubtitles();
});
elements.subtitleDownloadButton.addEventListener("click", () => {
  downloadSelectedSubtitle().catch((error) => setStatus(error.message || error, 0));
});
elements.subtitleTrackInput.addEventListener("change", () => {
  elements.downloadSubtitlesInput.checked = true;
  updateActionStates();
});
elements.downloadDirInput.addEventListener("input", updateActionStates);
elements.videoOpenButton.addEventListener("click", () => {
  chooseLocalVideoFile().catch((error) => setStatus(error.message || error, 0));
});
elements.fileInput.addEventListener("change", () => {
  updateActionStates();
  const file = elements.fileInput.files?.[0];
  if (file) {
    uploadLocalVideoFile(file);
  }
});
elements.subtitleFormatInput.addEventListener("change", () => {
  const format = selectedSubtitleFormat();
  clearSubtitleDownload(safeSubtitleName(state.session?.original_name || "subtitles", format), format);
  publishSubtitleFormatUpdate(format);
  updateActionStates();
});
elements.downloadDirButton.addEventListener("click", async () => {
  if (!window.pywebview?.api?.choose_download_dir) {
    elements.downloadDirInput.focus();
    return;
  }

  try {
    const result = await window.pywebview.api.choose_download_dir(elements.downloadDirInput.value.trim());
    if (result?.ok) {
      elements.downloadDirInput.value = result.path || "";
      updateActionStates();
      scheduleSettingsAutosave();
    } else if (result && !result.cancelled) {
      setStatus(result.message || "Could not choose folder", 0);
    }
  } catch (error) {
    setStatus(error.message || error, 0);
  }
});
elements.urlButton.addEventListener("click", async () => {
  try {
    const url = elements.urlInput.value.trim();
    if (!url || hasActiveJobKind("download") || hasActiveJobKind("subtitle_download")) return;
    const subtitleOptions = selectedSubtitleDownloadOptions();
    const payload = await fetchJson("/api/videos/url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url,
        max_height: selectedMaxHeight(),
        format_selector: selectedFormatSelector(),
        download_dir: selectedDownloadDir(),
        download_subtitles: subtitleOptions.download_subtitles,
        subtitle_languages: subtitleOptions.subtitle_languages,
        subtitle_source: subtitleOptions.subtitle_source,
      }),
    });
    const jobId = payload.job_id;
    const result = await pollJob(jobId, {
      kind: "download",
      label: "yt-dlp download",
      autoRemoveComplete: false,
    });

    if (!hasActiveJobKind("ocr")) {
      await loadSession(result);
      setActivity(jobId, { message: "Video loaded", progress: 1, status: "complete" });
      scheduleActivityRemoval(jobId, 7000);
      return;
    }

    setActivity(jobId, {
      message: "Download ready",
      progress: 1,
      status: "complete",
      actionLabel: "Load",
      action: async () => {
        await loadSession(result);
        removeActivity(jobId);
      },
    });
    scheduleActivityRemoval(jobId, 60000);
  } catch (error) {
    if (error.cancelled) return;
    setStatus(error.message, 0);
  }
});

async function openLocalVideoPath(path, options = {}) {
  const cleanPath = String(path || "").trim();
  if (!cleanPath || state.fileUploadActive || hasActiveJobKind("ocr")) return;
  state.fileUploadActive = true;
  updateActionStates();
  try {
    setStatus(options.keepCopy ? "Copying video into SubtitleYC" : "Opening video", options.keepCopy ? 0.12 : 0.18);
    const session = await fetchJson("/api/videos/open", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: cleanPath, keep_copy: Boolean(options.keepCopy) }),
    });
    await loadSession(session);
    setStatus(options.keepCopy ? "Loaded stored video copy" : "Loaded video without copying", 1);
  } finally {
    state.fileUploadActive = false;
    updateActionStates();
  }
}

async function chooseLocalVideoFile() {
  const chooser = window.pywebview?.api?.choose_video_file;
  if (!chooser) {
    elements.fileInput.click();
    return;
  }
  const result = await chooser("");
  if (result?.ok && result.path) {
    await openLocalVideoPath(result.path, { keepCopy: Boolean(elements.keepVideoCopyInput?.checked) });
  } else if (result && !result.cancelled) {
    setStatus(result.message || "Could not choose video", 0);
  }
}

async function uploadLocalVideoFile(file) {
  if (!file || state.fileUploadActive || hasActiveJobKind("ocr")) return;
  state.fileUploadActive = true;
  updateActionStates();
  try {
    const form = new FormData();
    form.append("file", file);
    setStatus("Importing video copy", 0.08);
    const session = await fetchJson("/api/videos/upload", {
      method: "POST",
      body: form,
    });
    await loadSession(session);
    setStatus("Loaded imported video copy", 1);
  } catch (error) {
    setStatus(error.message || error, 0);
  } finally {
    state.fileUploadActive = false;
    elements.fileInput.value = "";
    updateActionStates();
  }
}


elements.runButton.addEventListener("click", async () => {
  try {
    if (!state.session || !state.crop || hasActiveJobKind("ocr")) return;
    const sourceSessionId = state.session.id;
    const sourceName = state.session.original_name;
    const outputFormat = selectedSubtitleFormat();
    clearSubtitleDownload(safeSubtitleName(sourceName, outputFormat), outputFormat);
    const payload = await fetchJson(`/api/videos/${sourceSessionId}/ocr`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentOcrPayload()),
    });
    const jobId = payload.job_id;
    const result = await pollJob(jobId, {
      kind: "ocr",
      label: `VideOCR: ${sourceName}`,
      autoRemoveComplete: false,
    });
    const resultFormat = result.subtitle_format || outputFormat;
    const resultLabel = subtitleFormatLabel(resultFormat);
    const resultUrl = result.subtitle_url || result.srt_url;
    const resultFilename = result.subtitle_filename || safeSubtitleName(sourceName, resultFormat);
    const attachSubtitle = () => {
      if (result.session && state.session?.id === sourceSessionId) {
        state.session = result.session;
      }
      setSubtitleDownload(resultUrl, sourceName, resultFormat, resultFilename);
      setStatus(`${resultLabel} ready: ${result.cue_count} cues`, 1);
    };

    const shouldOpenEditor = state.session?.id === sourceSessionId;
    if (shouldOpenEditor) {
      attachSubtitle();
    }

    setActivity(jobId, {
      message: `Ready: ${result.cue_count} cues`,
      progress: 1,
      status: "complete",
      actionLabel: resultLabel,
      action: attachSubtitle,
    });
    scheduleActivityRemoval(jobId, 60000);
    if (shouldOpenEditor) {
      await openSubtitleEditorTab();
    }
  } catch (error) {
    if (error.cancelled) return;
    setStatus(error.message, 0);
  }
});

elements.downloadLink.addEventListener("click", async (event) => {
  if (elements.downloadLink.classList.contains("disabled") || !state.subtitleUrl) {
    event.preventDefault();
    return;
  }

  if (!window.pywebview?.api?.save_subtitle && !window.pywebview?.api?.save_srt) {
    return;
  }

  event.preventDefault();
  try {
    setStatus(`Choose where to save the ${subtitleFormatLabel(state.subtitleFormat)} file`, 1);
    const saveSubtitle = window.pywebview.api.save_subtitle || window.pywebview.api.save_srt;
    const result = await saveSubtitle(state.subtitleUrl, state.subtitleFilename);
    if (result?.ok) {
      setStatus(`Saved ${subtitleFormatLabel(state.subtitleFormat)} to ${result.path}`, 1);
    } else if (result?.cancelled) {
      setStatus(`${subtitleFormatLabel(state.subtitleFormat)} save cancelled`, 1);
    } else {
      setStatus(result?.message || "Could not save subtitle file", 0);
    }
  } catch (error) {
    setStatus(error.message || error, 0);
  }
});

elements.canvas.addEventListener("pointerdown", (event) => {
  if (state.previewPreparing) return;
  const size = sourceSize();
  if (!size.width || !size.height) return;
  state.dragStart = pointerToVideo(event);
  elements.canvas.setPointerCapture(event.pointerId);
});

elements.canvas.addEventListener("pointermove", (event) => {
  if (state.previewPreparing || !state.dragStart) return;
  const point = pointerToVideo(event);
  setCrop({
    x: Math.min(state.dragStart.x, point.x),
    y: Math.min(state.dragStart.y, point.y),
    width: Math.abs(point.x - state.dragStart.x),
    height: Math.abs(point.y - state.dragStart.y),
  });
});

elements.canvas.addEventListener("pointerup", (event) => {
  state.dragStart = null;
  elements.canvas.releasePointerCapture(event.pointerId);
});

elements.seekSlider.addEventListener("pointerdown", beginPreviewScrub);
elements.seekSlider.addEventListener("pointerup", finishPreviewScrub);
elements.seekSlider.addEventListener("pointercancel", finishPreviewScrub);
elements.seekSlider.addEventListener("blur", finishPreviewScrub);

elements.seekSlider.addEventListener("input", () => {
  beginPreviewScrub();
  seekTo(Number(elements.seekSlider.value || 0));
});

elements.seekSlider.addEventListener("change", () => {
  seekTo(Number(elements.seekSlider.value || 0), { immediate: true });
  finishPreviewScrub();
});

elements.playButton.addEventListener("click", () => {
  togglePreviewPlayback();
});

elements.prevFrameButton.addEventListener("click", () => {
  stopPreviewPlayback();
  seekTo(state.previewTime - frameSeconds(), { immediate: true });
});

elements.nextFrameButton.addEventListener("click", () => {
  stopPreviewPlayback();
  seekTo(state.previewTime + frameSeconds(), { immediate: true });
});


elements.previewCuePrevJumpButton.addEventListener("click", jumpToPreviousSubtitleBoundary);
elements.previewCueJumpButton.addEventListener("click", jumpToNextSubtitleBoundary);
elements.previewCueStartBackButton.addEventListener("click", () => nudgeCurrentSubtitleBoundary("start", -subtitleShiftFrameCount()));
elements.previewCueStartForwardButton.addEventListener("click", () => nudgeCurrentSubtitleBoundary("start", subtitleShiftFrameCount()));
elements.previewCueEndBackButton.addEventListener("click", () => nudgeCurrentSubtitleBoundary("end", -subtitleShiftFrameCount()));
elements.previewCueEndForwardButton.addEventListener("click", () => nudgeCurrentSubtitleBoundary("end", subtitleShiftFrameCount()));
elements.languageInput.addEventListener("change", () => {
  applyLanguageDefaults();
  if (state.subtitleTracks.length) {
    const preferred = preferredSubtitleTrack(state.subtitleTracks);
    if (preferred) {
      elements.subtitleTrackInput.value = preferred.id || `${preferred.source}:${preferred.language}`;
    }
  }
  updateActionStates();
  showSelectedLanguageStatus();
});
elements.confidenceInput.addEventListener("input", setOcrRangeLabels);
elements.similarityInput.addEventListener("input", setOcrRangeLabels);
elements.ssimInput.addEventListener("input", setOcrRangeLabels);
elements.settingConfidenceInput.addEventListener("input", setSettingsRangeLabels);
elements.settingSimilarityInput.addEventListener("input", setSettingsRangeLabels);
elements.settingSsimInput.addEventListener("input", setSettingsRangeLabels);

window.addEventListener("resize", resizeCanvas);
window.addEventListener("subtitleyc-language-changed", () => {
  renderActivities();
  if (state.library) renderLibrary(state.library);
  renderSubtitleEditor();
});

setupDraggableSubtitleOverlay();

bindSettingsAutosave();

async function init() {
  populateOcrLanguageSelects();
  renderActivities();
  resizeCanvas();
  applyLanguageDefaults();
  await loadSettings().catch((error) => setStatus(error.message || error, 0));
  await refreshLibrary().catch(() => renderRecentProjects([]));
  try {
    await refreshSystemInfo();
  } catch {
    state.videocrReady = false;
    renderSystemInfo(null);
    elements.systemStatus.textContent = "Tool check unavailable";
  }
  updateActionStates();
}

init();
