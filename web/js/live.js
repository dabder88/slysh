import { api, showToast } from "./api.js";
import { reportError } from "./errors.js";
import { openJobExportModal, openLocalPath, refreshLibrary } from "./legacy.js";
import { t } from "./i18n.js";

const SAVE_AUDIO_KEY = "live-save-audio";

let liveLastRecordingPath = "";

function noMicHint() {
  return t("live.noMic");
}

function loadSaveAudioPreference() {
  const el = document.getElementById("live-save-audio");
  if (!el) {
    return;
  }
  el.checked = localStorage.getItem(SAVE_AUDIO_KEY) !== "0";
}

function saveSaveAudioPreference() {
  const el = document.getElementById("live-save-audio");
  if (!el) {
    return;
  }
  localStorage.setItem(SAVE_AUDIO_KEY, el.checked ? "1" : "0");
}

function syncLiveRecordingActions(path) {
  const panel = document.getElementById("live-recording-actions");
  const pathEl = document.getElementById("live-recording-path");
  if (!panel) {
    return;
  }
  const normalized = String(path || "").trim();
  liveLastRecordingPath = normalized;
  panel.hidden = !normalized;
  if (pathEl) {
    pathEl.textContent = normalized ? t("live.recordingSaved", { path: normalized }) : "";
  }
}

function setButtonLabelText(buttonEl, labelId, text) {
  const labelEl = labelId ? document.getElementById(labelId) : null;
  if (labelEl) {
    labelEl.textContent = text;
    return;
  }
  if (buttonEl) {
    buttonEl.textContent = text;
  }
}

function formatMeterDbLabel(rms) {
  const value = Number(rms) || 0;
  if (value <= 0.0001) {
    return "-∞ dB";
  }
  const db = 20 * Math.log10(Math.min(1, value * 2.5));
  return `${db >= -0.05 ? 0 : db.toFixed(0)} dB`;
}

function updateLiveCounterStats() {
  const counterEl = document.getElementById("live-counter-stats");
  const el = liveTranscriptEl();
  if (!counterEl || !el) {
    return;
  }
  const val = String(el.value || "").trim();
  const words = val ? val.split(/\s+/).filter(Boolean).length : 0;
  counterEl.textContent = t("live.counterStats", { words, chars: val.length });
}

function syncLiveSessionChrome({ sessionActive, paused, listening, rms }) {
  const recBtn = document.getElementById("btn-rec");
  const badge = document.getElementById("live-session-badge");
  const badgeText = document.getElementById("live-session-badge-text");
  const timerWrap = document.getElementById("live-rec-timer");
  if (recBtn) {
    recBtn.classList.toggle("is-recording", Boolean(sessionActive) && !paused);
  }
  if (badge && badgeText) {
    if (sessionActive && paused) {
      badge.className = "live-session-badge-paused";
      badgeText.textContent = t("live.bentoStatusPaused");
    } else if (sessionActive) {
      badge.className = "live-session-badge-active";
      badgeText.textContent = listening ? t("live.bentoStatusListening") : t("live.bentoStatusRecording");
    } else {
      badge.className = "live-session-badge-idle";
      badgeText.textContent = t("live.bentoStatusIdle");
    }
  }
  if (timerWrap) {
    timerWrap.classList.toggle("hidden", !sessionActive);
  }
  const dbEl = document.getElementById("live-meter-db");
  if (dbEl) {
    dbEl.textContent = formatMeterDbLabel(listening ? rms : 0);
  }
}

let liveInitialized = false;
let livePollTimer = null;
let liveJobId = null;
let liveLastSegments = [];
let liveEditDirty = false;
let liveSaveTimer = null;
let liveSessionActive = false;
let liveAwaitingTranscript = false;

function liveTranscriptEl() {
  return document.getElementById("live-transcript");
}

function liveTranscriptText() {
  const el = liveTranscriptEl();
  if (liveEditDirty && el) {
    return String(el.value || "").trim();
  }
  return buildLiveCopyText(liveLastSegments);
}

function liveSegmentBody(seg) {
  const text = String(seg?.text || "").trim();
  if (!text) {
    return "";
  }
  return seg.speaker ? `${seg.speaker}: ${text}` : text;
}

function hasLiveTranscriptText(segments) {
  if (liveEditDirty) {
    return Boolean(liveTranscriptText());
  }
  return (segments || []).some((seg) => Boolean(liveSegmentBody(seg)));
}

function buildLiveCopyText(segments) {
  return (segments || [])
    .map((seg) => liveSegmentBody(seg))
    .filter(Boolean)
    .join("\n");
}

function syncLiveTranscriptFromSegments(segments, { force = false } = {}) {
  const el = liveTranscriptEl();
  if (!el) {
    return;
  }
  liveLastSegments = segments || [];
  if (!liveEditDirty || force) {
    el.value = buildLiveCopyText(liveLastSegments);
    if (force) {
      liveEditDirty = false;
    }
  }
  updateLiveCounterStats();
}

function syncLiveTranscriptWait({ sessionActive, segments, jobStatus, captureFinalizing }) {
  const wait = document.getElementById("live-transcript-wait");
  if (!wait) {
    return;
  }
  const hasText = hasLiveTranscriptText(segments);
  const finalizing = Boolean(captureFinalizing);
  if (hasText) {
    liveAwaitingTranscript = false;
  } else if ((jobStatus === "completed" || jobStatus === "failed") && !finalizing) {
    liveAwaitingTranscript = false;
  } else if (finalizing) {
    liveAwaitingTranscript = true;
  }
  const show = !hasText && (Boolean(sessionActive) || liveAwaitingTranscript || finalizing);
  wait.hidden = !show;
}

function syncLiveClearBar({ sessionActive, segments }) {
  const bar = document.getElementById("live-results-bar");
  if (!bar) {
    return;
  }
  const hasText = hasLiveTranscriptText(segments);
  bar.hidden = Boolean(sessionActive) || !hasText;
}

function syncLivePostActions({ listening, sessionActive, segments, jobStatus }) {
  const panel = document.getElementById("live-post-actions");
  const copyBtn = document.getElementById("btn-live-copy");
  const exportBtn = document.getElementById("btn-live-export");
  if (!panel) {
    return;
  }
  const hasText = hasLiveTranscriptText(segments);
  panel.hidden = !hasText;
  if (copyBtn) {
    copyBtn.disabled = !hasText;
  }
  if (exportBtn) {
    exportBtn.disabled = !hasText || Boolean(listening) || Boolean(sessionActive) || jobStatus !== "completed";
  }
}

async function saveLiveTranscript() {
  if (liveJobId == null) {
    return;
  }
  const el = liveTranscriptEl();
  if (!el) {
    return;
  }
  const transcript = String(el.value || "");
  await api(`/api/jobs/${liveJobId}/segments`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript }),
  });
  liveEditDirty = false;
  const job = await api(`/api/jobs/${liveJobId}`);
  liveLastSegments = job.segments || [];
}

function scheduleLiveTranscriptSave() {
  if (liveSaveTimer) {
    clearTimeout(liveSaveTimer);
  }
  liveSaveTimer = setTimeout(() => {
    liveSaveTimer = null;
    saveLiveTranscript().catch((err) => reportError(t("live.title"), err));
  }, 600);
}

async function loadMics(refresh = false) {
  const micSelect = document.getElementById("mic-select");
  const recBtn = document.getElementById("btn-rec");
  const liveHint = document.getElementById("live-hint");
  if (!micSelect || !recBtn) {
    return;
  }
  let mics = [];
  try {
    mics = await api(refresh ? "/api/mics?refresh=1" : "/api/mics");
  } catch (err) {
    reportError(t("live.loadMicsFailed"), err);
    mics = [];
  }
  micSelect.innerHTML = "";
  for (const mic of mics) {
    const opt = document.createElement("option");
    opt.value = String(mic.id);
    opt.textContent = mic.name;
    micSelect.appendChild(opt);
  }
  const empty = mics.length === 0;
  recBtn.disabled = empty;
  micSelect.disabled = empty;
  if (liveHint) {
    liveHint.textContent = empty
      ? t("live.noMicsHint")
      : "";
  }
}

async function copyLiveTranscript() {
  const text = liveTranscriptText();
  if (!text) {
    showToast(t("live.copyEmpty"));
    return;
  }
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.left = "-9999px";
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    showToast(t("live.copied"));
  } catch (err) {
    reportError(t("live.copyEmpty"), err);
  }
}

async function exportLiveTranscript() {
  if (liveJobId == null) {
    showToast(t("live.noExport"));
    return;
  }
  const job = await api(`/api/jobs/${liveJobId}`);
  await openJobExportModal(job);
}

async function toggleLivePause() {
  const status = await api("/api/live/status");
  if (!status.session_active) {
    return;
  }
  if (status.paused) {
    await api("/api/live/resume", { method: "POST" });
    showToast(t("live.resumed"));
  } else {
    if (!hasLiveTranscriptText(liveLastSegments)) {
      liveAwaitingTranscript = true;
      syncLiveTranscriptWait({
        sessionActive: true,
        segments: liveLastSegments,
        jobStatus: "running",
      });
    }
    await api("/api/live/pause", { method: "POST" });
    showToast(t("live.pausedToast"));
  }
  await pollLive();
}

async function clearLiveView() {
  if (!window.confirm(t("live.clearConfirm"))) {
    return;
  }
  await api("/api/live/clear", { method: "POST" });
  liveJobId = null;
  liveLastSegments = [];
  liveEditDirty = false;
  syncLiveTranscriptFromSegments([], { force: true });
  liveAwaitingTranscript = false;
  syncLiveTranscriptWait({ sessionActive: false, segments: [], jobStatus: "" });
  syncLivePostActions({ listening: false, sessionActive: false, segments: [], jobStatus: "" });
  syncLiveClearBar({ sessionActive: false, segments: [] });
  showToast(t("live.cleared"));
}

async function pollLive() {
  const micSelect = document.getElementById("mic-select");
  const recBtn = document.getElementById("btn-rec");
  const pauseBtn = document.getElementById("btn-live-pause");
  const stopBtn = document.getElementById("btn-stop");
  const refreshMicsBtn = document.getElementById("btn-refresh-mics");
  const liveHint = document.getElementById("live-hint");
  const liveCountdown = document.getElementById("live-countdown");
  const liveMeter = document.getElementById("live-meter");

  const status = await api("/api/live/status");
  const sessionActive = Boolean(status.session_active);
  liveSessionActive = sessionActive;
  const paused = Boolean(status.paused);
  const listening = Boolean(status.listening);
  const hasMics = micSelect && micSelect.options.length > 0;
  if (recBtn) {
    recBtn.disabled = !hasMics || sessionActive;
  }
  if (pauseBtn) {
    pauseBtn.disabled = !sessionActive;
    setButtonLabelText(
      pauseBtn,
      "btn-live-pause-label",
      paused ? t("live.resume") : t("live.pause")
    );
  }
  if (stopBtn) {
    stopBtn.disabled = !sessionActive;
  }
  if (micSelect) {
    micSelect.disabled = !hasMics || sessionActive;
  }
  if (refreshMicsBtn) {
    refreshMicsBtn.disabled = sessionActive;
  }
  if (liveCountdown) {
    if (listening) {
      const n = Math.max(0, Math.ceil(Number(status.remaining_s) || 0));
      liveCountdown.textContent = t("live.listening", { n });
    } else if (paused) {
      liveCountdown.textContent = t("live.paused");
    } else {
      liveCountdown.textContent = "";
    }
  }
  const rms = listening ? Number(status.rms) || 0 : 0;
  if (liveMeter) {
    liveMeter.style.width = `${Math.min(100, Math.round(rms * 400))}%`;
  }
  syncLiveSessionChrome({ sessionActive, paused, listening, rms });
  if (liveHint && status.error) {
    liveHint.textContent = status.error;
  }
  const jobId = status.job_id || liveJobId;
  let jobStatus = "";
  let segments = [];
  let captureFinalizing = Boolean(status.capture_finalizing);
  if (jobId) {
    liveJobId = jobId;
    const job = await api(`/api/jobs/${jobId}`);
    jobStatus = job.status || "";
    captureFinalizing = captureFinalizing || Boolean(job.capture_finalizing);
    segments = Array.isArray(status.segments) ? status.segments : job.segments || [];
    const recPath =
      status.recording_path || job.recording_path || (!sessionActive ? job.source_path : "");
    if (!sessionActive && recPath) {
      syncLiveRecordingActions(String(recPath));
    }
    syncLiveTranscriptFromSegments(segments);
    syncLivePostActions({ listening, sessionActive, segments, jobStatus });
    syncLiveClearBar({ sessionActive, segments });
    syncLiveTranscriptWait({ sessionActive, segments, jobStatus, captureFinalizing });
  } else {
    liveJobId = null;
    if (!liveEditDirty) {
      syncLiveTranscriptFromSegments([]);
    }
    syncLivePostActions({ listening, sessionActive, segments: [], jobStatus: "" });
    syncLiveClearBar({ sessionActive, segments: [] });
    syncLiveTranscriptWait({ sessionActive, segments: [], jobStatus: "", captureFinalizing: false });
  }
  if (!sessionActive && livePollTimer && !liveAwaitingTranscript && !captureFinalizing) {
    clearInterval(livePollTimer);
    livePollTimer = null;
  }
  if (liveAwaitingTranscript && !livePollTimer) {
    startLivePoll();
  }
}

function startLivePoll() {
  if (!livePollTimer) {
    livePollTimer = setInterval(() => pollLive().catch((err) => reportError(t("live.title"), err)), 400);
  }
  pollLive().catch((err) => reportError(t("live.title"), err));
}

async function startLive() {
  const liveHint = document.getElementById("live-hint");
  const micSelect = document.getElementById("mic-select");
  if (liveHint) {
    liveHint.textContent = "";
  }
  liveEditDirty = false;
  const deviceId = micSelect && micSelect.value === "" ? undefined : Number(micSelect.value);
  const saveAudioEl = document.getElementById("live-save-audio");
  const body = {
    save_audio: saveAudioEl ? Boolean(saveAudioEl.checked) : true,
  };
  if (Number.isFinite(deviceId)) {
    body.device_id = deviceId;
  }
  const job = await api("/api/live/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  liveJobId = job.id;
  liveAwaitingTranscript = false;
  syncLiveTranscriptFromSegments([], { force: true });
  syncLiveTranscriptWait({ sessionActive: true, segments: [], jobStatus: "running" });
  startLivePoll();
}

async function stopLive() {
  if (!hasLiveTranscriptText(liveLastSegments)) {
    liveAwaitingTranscript = true;
    syncLiveTranscriptWait({
      sessionActive: liveSessionActive,
      segments: liveLastSegments,
      jobStatus: "running",
    });
  }
  const stopped = await api("/api/live/stop", { method: "POST" });
  if (stopped?.recording_path) {
    syncLiveRecordingActions(stopped.recording_path);
  }
  await pollLive();
  await refreshLibrary();
}

export function initLive() {
  if (liveInitialized) {
    return;
  }
  liveInitialized = true;
  loadSaveAudioPreference();
  document.getElementById("live-save-audio")?.addEventListener("change", () => {
    saveSaveAudioPreference();
  });
  document.getElementById("btn-live-open-recording")?.addEventListener("click", () =>
    openLocalPath(liveLastRecordingPath, false).catch((err) =>
      reportError(t("live.openRecording"), err)
    )
  );
  document.getElementById("btn-live-open-recording-folder")?.addEventListener("click", () =>
    openLocalPath(liveLastRecordingPath, true).catch((err) =>
      reportError(t("live.openRecordingFolder"), err)
    )
  );
  const transcript = liveTranscriptEl();
  if (transcript) {
    transcript.setAttribute("aria-label", t("live.transcriptLabel"));
    transcript.addEventListener("input", () => {
      liveEditDirty = true;
      scheduleLiveTranscriptSave();
      updateLiveCounterStats();
      syncLiveClearBar({ sessionActive: liveSessionActive, segments: liveLastSegments });
      const hasText = hasLiveTranscriptText(liveLastSegments);
      const panel = document.getElementById("live-post-actions");
      const copyBtn = document.getElementById("btn-live-copy");
      if (panel) {
        panel.hidden = !hasText;
      }
      if (copyBtn) {
        copyBtn.disabled = !hasText;
      }
    });
  }
  document.getElementById("btn-rec")?.addEventListener("click", () =>
    startLive().catch((err) => {
      const liveHint = document.getElementById("live-hint");
      if (liveHint) {
        liveHint.textContent = err.message || noMicHint();
      }
    })
  );
  document.getElementById("btn-live-pause")?.addEventListener("click", () =>
    toggleLivePause().catch((err) => reportError(t("live.title"), err))
  );
  document.getElementById("btn-stop")?.addEventListener("click", () =>
    stopLive().catch((err) => reportError(t("live.title"), err))
  );
  document.getElementById("btn-refresh-mics")?.addEventListener("click", () =>
    loadMics(true).catch((err) => reportError(t("live.mics"), err))
  );
  document.getElementById("btn-live-copy")?.addEventListener("click", () =>
    copyLiveTranscript().catch((err) => reportError(t("live.title"), err))
  );
  document.getElementById("btn-live-export")?.addEventListener("click", () =>
    exportLiveTranscript().catch((err) => reportError(t("live.title"), err))
  );
  document.getElementById("btn-live-clear")?.addEventListener("click", () =>
    clearLiveView().catch((err) => reportError(t("live.title"), err))
  );
  loadMics().catch((err) => reportError(t("live.mics"), err));
  syncLiveTranscriptWait({ sessionActive: false, segments: [], jobStatus: "" });
  syncLivePostActions({ listening: false, sessionActive: false, segments: [], jobStatus: "" });
  syncLiveClearBar({ sessionActive: false, segments: [] });
}

export async function onLiveShow() {
  loadMics().catch((err) => reportError(t("live.mics"), err));
  const status = await api("/api/live/status").catch((err) => {
    reportError(t("live.title"), err);
    return null;
  });
  if (status?.session_active) {
    startLivePoll();
  } else {
    pollLive().catch((err) => reportError(t("live.title"), err));
  }
}
