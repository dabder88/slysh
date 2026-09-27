import { api, showToast } from "./api.js";
import { reportError } from "./errors.js";
import { openJobExportModal, refreshLibrary } from "./legacy.js";
import { t } from "./i18n.js";

function noMicHint() {
  return t("live.noMic");
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
}

function syncLiveTranscriptWait({ sessionActive, segments, jobStatus }) {
  const wait = document.getElementById("live-transcript-wait");
  if (!wait) {
    return;
  }
  const hasText = hasLiveTranscriptText(segments);
  if (hasText) {
    liveAwaitingTranscript = false;
  } else if (jobStatus === "completed" || jobStatus === "failed") {
    liveAwaitingTranscript = false;
  }
  const show = !hasText && (Boolean(sessionActive) || liveAwaitingTranscript);
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
  openJobExportModal(job);
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
    pauseBtn.textContent = paused ? t("live.resume") : t("live.pause");
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
  if (liveMeter) {
    const rms = listening ? Number(status.rms) || 0 : 0;
    liveMeter.style.width = `${Math.min(100, Math.round(rms * 400))}%`;
  }
  if (liveHint && status.error) {
    liveHint.textContent = status.error;
  }
  const jobId = status.job_id || liveJobId;
  let jobStatus = "";
  let segments = [];
  if (jobId) {
    liveJobId = jobId;
    const job = await api(`/api/jobs/${jobId}`);
    jobStatus = job.status || "";
    segments = Array.isArray(status.segments) ? status.segments : job.segments || [];
    syncLiveTranscriptFromSegments(segments);
    syncLivePostActions({ listening, sessionActive, segments, jobStatus });
    syncLiveClearBar({ sessionActive, segments });
    syncLiveTranscriptWait({ sessionActive, segments, jobStatus });
  } else {
    liveJobId = null;
    if (!liveEditDirty) {
      syncLiveTranscriptFromSegments([]);
    }
    syncLivePostActions({ listening, sessionActive, segments: [], jobStatus: "" });
    syncLiveClearBar({ sessionActive, segments: [] });
    syncLiveTranscriptWait({ sessionActive, segments: [], jobStatus: "" });
  }
  if (!sessionActive && livePollTimer && !liveAwaitingTranscript) {
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
  const body = {};
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
  await api("/api/live/stop", { method: "POST" });
  await pollLive();
  await refreshLibrary();
}

export function initLive() {
  if (liveInitialized) {
    return;
  }
  liveInitialized = true;
  const transcript = liveTranscriptEl();
  if (transcript) {
    transcript.setAttribute("aria-label", t("live.transcriptLabel"));
    transcript.addEventListener("input", () => {
      liveEditDirty = true;
      scheduleLiveTranscriptSave();
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
