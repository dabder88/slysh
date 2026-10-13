import { api, showToast } from "./api.js";
import { reportError } from "./errors.js";
import {
  cancelJob,
  openJobExportModal,
  openLocalPath,
  refreshLibrary,
  startSpeakers,
  uniqueSpeakers,
  waitForSpeakers,
} from "./legacy.js";
import { speakerKeysForRename, speakerRenameLabel } from "./library-utils.js";
import { formatMsClock } from "./media-time.js";
import { t } from "./i18n.js";

const NO_OUTPUT_HINT =
  t("meeting.k4303073");
const TIMESTAMPS_KEY = "meeting-show-timestamps";
const AUTO_SPEAKERS_KEY = "meeting-auto-speakers";
const SAVE_AUDIO_KEY = "meeting-save-audio";

let meetingInitialized = false;
let meetingPollTimer = null;
let meetingJobId = null;
let meetingStarting = false;
let meetingLastSegments = [];
let meetingEditDirty = false;
let meetingSaveTimer = null;
let meetingTranscriptJobId = null;
let meetingLastExportPath = "";
let meetingLastRecordingPath = "";
let meetingLastSpeakersError = null;
let meetingSpeakerKeys = [];
let meetingEnginePackagesOk = true;
let meetingAwaitingTranscript = false;
let meetingSessionActiveFlag = false;

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

function formatElapsed(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const mm = String(Math.floor(total / 60)).padStart(2, "0");
  const ss = String(total % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

function showMeetingTimestamps() {
  const el = document.getElementById("meeting-show-timestamps");
  return Boolean(el && el.checked);
}

function loadTimestampsPreference() {
  const el = document.getElementById("meeting-show-timestamps");
  if (!el) {
    return;
  }
  el.checked = localStorage.getItem(TIMESTAMPS_KEY) === "1";
}

function saveTimestampsPreference() {
  const el = document.getElementById("meeting-show-timestamps");
  if (!el) {
    return;
  }
  localStorage.setItem(TIMESTAMPS_KEY, el.checked ? "1" : "0");
}

function loadAutoSpeakersPreference() {
  const el = document.getElementById("meeting-auto-speakers");
  if (!el) {
    return;
  }
  el.checked = localStorage.getItem(AUTO_SPEAKERS_KEY) === "1";
}

function saveAutoSpeakersPreference() {
  const el = document.getElementById("meeting-auto-speakers");
  if (!el) {
    return;
  }
  localStorage.setItem(AUTO_SPEAKERS_KEY, el.checked ? "1" : "0");
}

function loadSaveAudioPreference() {
  const el = document.getElementById("meeting-save-audio");
  if (!el) {
    return;
  }
  el.checked = localStorage.getItem(SAVE_AUDIO_KEY) !== "0";
}

function saveSaveAudioPreference() {
  const el = document.getElementById("meeting-save-audio");
  if (!el) {
    return;
  }
  localStorage.setItem(SAVE_AUDIO_KEY, el.checked ? "1" : "0");
}

function syncMeetingRecordingActions(path) {
  const panel = document.getElementById("meeting-recording-actions");
  const pathEl = document.getElementById("meeting-recording-path");
  if (!panel) {
    return;
  }
  const normalized = String(path || "").trim();
  meetingLastRecordingPath = normalized;
  panel.hidden = !normalized;
  if (pathEl) {
    pathEl.textContent = normalized ? t("meeting.recordingSaved", { path: normalized }) : "";
  }
}

async function loadMeetingSetupStatus() {
  try {
    const setup = await api("/api/setup");
    meetingEnginePackagesOk = Boolean(setup.engine_packages);
  } catch {
    meetingEnginePackagesOk = true;
  }
  const btn = document.getElementById("btn-meeting-speakers");
  if (btn && !meetingEnginePackagesOk) {
    btn.title = t("meeting.k607940");
  }
}

function formatSegmentBody(seg) {
  const text = String(seg.text || "").trim();
  if (!text) {
    return "";
  }
  return seg.speaker ? `${seg.speaker}: ${text}` : text;
}

function formatSegmentLine(seg, showTimestamps) {
  const body = formatSegmentBody(seg);
  if (!body) {
    return "";
  }
  if (showTimestamps && seg.start_ms != null) {
    return `[${formatMsClock(seg.start_ms)}] ${body}`;
  }
  return body;
}

function meetingTranscriptEl() {
  return document.getElementById("meeting-transcript");
}

function hasMeetingTranscriptText(segments) {
  if (meetingEditDirty) {
    return Boolean(meetingTranscriptText());
  }
  return (segments || []).some((seg) => Boolean(formatSegmentBody(seg)));
}

function meetingTranscriptText() {
  const el = meetingTranscriptEl();
  if (meetingEditDirty && el) {
    return String(el.value || "").trim();
  }
  return buildMeetingCopyText(meetingLastSegments);
}

function updateMeetingCounterStats() {
  const counterEl = document.getElementById("meeting-counter-stats");
  const el = meetingTranscriptEl();
  if (!counterEl || !el) {
    return;
  }
  const val = String(el.value || "").trim();
  const words = val ? val.split(/\s+/).filter(Boolean).length : 0;
  counterEl.textContent = t("live.counterStats", { words, chars: val.length });
}

function syncMeetingTranscriptFromSegments(segments, { force = false, jobId = null } = {}) {
  const el = meetingTranscriptEl();
  if (!el) {
    return;
  }
  if (jobId != null && meetingTranscriptJobId !== jobId) {
    meetingTranscriptJobId = jobId;
    force = true;
  }
  meetingLastSegments = segments || [];
  if (!meetingEditDirty || force) {
    el.value = buildMeetingCopyText(meetingLastSegments);
    if (force) {
      meetingEditDirty = false;
    }
    updateMeetingCounterStats();
    if (document.activeElement !== el) {
      el.scrollTop = el.scrollHeight;
    }
  }
}

async function saveMeetingTranscript() {
  if (meetingJobId == null) {
    return;
  }
  const el = meetingTranscriptEl();
  if (!el) {
    return;
  }
  const transcript = String(el.value || "");
  try {
    await api(`/api/jobs/${meetingJobId}/segments`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transcript }),
    });
    meetingEditDirty = false;
    const job = await api(`/api/jobs/${meetingJobId}`);
    meetingLastSegments = job.segments || [];
    updateMeetingCounterStats();
  } catch (err) {
    if (err.status === 409) {
      return;
    }
    reportError(t("jobSource.meeting.label"), err);
  }
}

function scheduleMeetingTranscriptSave() {
  if (meetingSaveTimer) {
    clearTimeout(meetingSaveTimer);
  }
  meetingSaveTimer = setTimeout(() => {
    meetingSaveTimer = null;
    saveMeetingTranscript().catch(() => {});
  }, 600);
}

function syncMeetingTranscriptWait({ sessionActive, segments, jobStatus, captureFinalizing }) {
  const wait = document.getElementById("meeting-transcript-wait");
  if (!wait) {
    return;
  }
  const hasText = hasMeetingTranscriptText(segments);
  const finalizing = Boolean(captureFinalizing);
  if (hasText) {
    meetingAwaitingTranscript = false;
  } else if ((jobStatus === "completed" || jobStatus === "failed") && !finalizing) {
    meetingAwaitingTranscript = false;
  } else if (finalizing) {
    meetingAwaitingTranscript = true;
  }
  const show =
    !hasText &&
    (Boolean(sessionActive) || meetingAwaitingTranscript || finalizing);
  wait.hidden = !show;
}

function syncMeetingPostActions({ sessionActive, segments }) {
  const panel = document.getElementById("meeting-post-actions");
  if (!panel) {
    return;
  }
  panel.hidden = Boolean(sessionActive) || !hasMeetingTranscriptText(segments);
}

function syncMeetingClearButton({ sessionActive, segments }) {
  const bar = document.getElementById("meeting-results-bar");
  if (!bar) {
    return;
  }
  const items = segments || meetingLastSegments;
  bar.hidden = Boolean(sessionActive) || !hasMeetingTranscriptText(items);
}

function syncMeetingExportActions(path) {
  const panel = document.getElementById("meeting-export-actions");
  const pathEl = document.getElementById("meeting-export-path");
  if (!panel) {
    return;
  }
  const normalized = String(path || "").trim();
  meetingLastExportPath = normalized;
  panel.hidden = !normalized;
  if (pathEl) {
    pathEl.textContent = normalized;
  }
}

function renderMeetingSpeakerRename(keys, names = {}) {
  const panel = document.getElementById("meeting-speaker-rename");
  if (!panel) {
    return;
  }
  const current = Array.from(panel.querySelectorAll("input")).map((input) => input.dataset.speakerKey);
  const same = current.length === keys.length && current.every((key, index) => key === keys[index]);
  if (same) {
    panel.hidden = keys.length === 0;
    return;
  }
  panel.innerHTML = "";
  if (!keys.length) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  const title = document.createElement("p");
  title.className = "meeting-speaker-rename-title";
  title.textContent = t("meeting.k7854836");
  panel.appendChild(title);
  const list = document.createElement("div");
  list.className = "meeting-speaker-rename-list";
  for (const key of keys) {
    const row = document.createElement("div");
    row.className = "meeting-speaker-row";
    const badge = document.createElement("span");
    badge.className = "meeting-speaker-key";
    badge.textContent = speakerRenameLabel(key);
    const input = document.createElement("input");
    input.type = "text";
    input.className = "meeting-speaker-input";
    input.dataset.speakerKey = key;
    input.value = names[key] || "";
    input.placeholder = t("meeting.k3979619");
    input.autocomplete = "off";
    input.addEventListener("change", () =>
      saveMeetingSpeakerNames().catch((err) => reportError(t("meeting.k7854836"), err))
    );
    row.appendChild(badge);
    row.appendChild(input);
    list.appendChild(row);
  }
  panel.appendChild(list);
}

function syncMeetingAutoSpeakersOption(sessionActive) {
  const autoCheckbox = document.getElementById("meeting-auto-speakers");
  if (autoCheckbox) {
    autoCheckbox.disabled = Boolean(sessionActive);
  }
}

const SPEAKER_CANCELLED_RU = "Остановлено пользователем";

function syncMeetingSpeakersUi(job, { sessionActive, segments } = {}) {
  const btn = document.getElementById("btn-meeting-speakers");
  const stopBtn = document.getElementById("btn-meeting-speakers-stop");
  const wait = document.getElementById("meeting-speakers-wait");
  const details = document.getElementById("meeting-speakers-details");
  const items = segments || job?.segments || [];
  const hasText = hasMeetingTranscriptText(items);
  const completed = job?.status === "completed";
  const running = Boolean(job?.speakers_running);
  const hasSpeakers = Boolean(job?.has_speakers) || uniqueSpeakers(items).length > 0;
  const showSpeakersSection = !sessionActive && hasText && completed;

  syncMeetingAutoSpeakersOption(sessionActive);
  if (details) {
    details.hidden = !showSpeakersSection;
    if (showSpeakersSection && (running || hasSpeakers)) {
      details.open = true;
    }
  }
  if (btn) {
    btn.hidden = Boolean(sessionActive) || !hasText || !completed || running;
    btn.disabled = running || !meetingEnginePackagesOk;
    if (!meetingEnginePackagesOk) {
      btn.title = t("meeting.k607940");
    } else {
      btn.removeAttribute("title");
    }
  }
  if (stopBtn) {
    stopBtn.hidden = Boolean(sessionActive) || !hasText || !completed || !running;
  }
  if (wait) {
    wait.hidden = !running;
    const label = wait.querySelector("span:not(.material-symbols-outlined)");
    if (label) {
      const elapsed = Number(job?.speakers_elapsed_s);
      label.textContent =
        running && Number.isFinite(elapsed) && elapsed > 0
          ? t("meeting.speakersElapsed", { elapsed: Math.floor(elapsed) })
          : t("meeting.k4461388");
    }
  }
  if (job?.speakers_error && job.speakers_error !== meetingLastSpeakersError) {
    meetingLastSpeakersError = job.speakers_error;
    if (job.speakers_error !== SPEAKER_CANCELLED_RU) {
      showToast(job.speakers_error);
    }
  }
  if (!sessionActive && hasSpeakers) {
    const keys = meetingSpeakerKeys.length ? meetingSpeakerKeys : speakerKeysForRename(items);
    renderMeetingSpeakerRename(keys, job?.speaker_names || {});
  } else if (!sessionActive) {
    renderMeetingSpeakerRename([]);
  }
}

async function saveMeetingSpeakerNames() {
  if (meetingJobId == null) {
    return;
  }
  const panel = document.getElementById("meeting-speaker-rename");
  if (!panel) {
    return;
  }
  const body = {};
  for (const input of panel.querySelectorAll("input")) {
    const name = input.value.trim();
    if (name) {
      body[input.dataset.speakerKey] = name;
    }
  }
  if (!Object.keys(body).length) {
    return;
  }
  await api(`/api/jobs/${meetingJobId}/speakers`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const job = await api(`/api/jobs/${meetingJobId}`);
  meetingSpeakerKeys = speakerKeysForRename(job.segments || []);
  syncMeetingTranscriptFromSegments(job.segments || [], { jobId: meetingJobId });
  syncMeetingSpeakersUi(job, { sessionActive: false, segments: job.segments || [] });
}

async function waitForMeetingCaptureFinalize(jobId) {
  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    const job = await api(`/api/jobs/${jobId}`);
    if (!job.capture_finalizing && job.status !== "running") {
      return job;
    }
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  return api(`/api/jobs/${jobId}`);
}

async function cancelMeetingSpeakers() {
  if (meetingJobId == null) {
    return;
  }
  try {
    await cancelJob(meetingJobId);
    const job = await api(`/api/jobs/${meetingJobId}`);
    syncMeetingSpeakersUi(job, { sessionActive: false, segments: job.segments || meetingLastSegments });
  } catch (err) {
    reportError(t("meeting.k3909903"), err);
  }
}

async function runMeetingSpeakers() {
  if (meetingJobId == null) {
    showToast("meeting.k7306115");
    return;
  }
  try {
    await startSpeakers(meetingJobId);
    meetingLastSpeakersError = null;
    showToast("meeting.k2351323");
    const job = await waitForSpeakers(meetingJobId, {
      intervalMs: 1000,
      onUpdate: (updated) => {
        syncMeetingSpeakersUi(updated, { sessionActive: false, segments: updated.segments || [] });
        syncMeetingTranscriptFromSegments(updated.segments || [], { jobId: meetingJobId });
      },
    });
    meetingSpeakerKeys = speakerKeysForRename(job.segments || []);
    syncMeetingTranscriptFromSegments(job.segments || [], { jobId: meetingJobId });
    syncMeetingSpeakersUi(job, { sessionActive: false, segments: job.segments || [] });
  } catch (err) {
    reportError(t("meeting.k3909903"), err);
  }
}

function buildMeetingCopyText(segments) {
  const showTimestamps = showMeetingTimestamps();
  return (segments || [])
    .map((seg) => formatSegmentLine(seg, showTimestamps))
    .filter(Boolean)
    .join("\n");
}

async function copyMeetingTranscript() {
  const text = meetingTranscriptText();
  if (!text) {
    showToast("meeting.k3160222");
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
    showToast("meeting.k8758450");
  } catch (err) {
    reportError(t("meeting.k804517"), err);
  }
}

async function exportMeetingTranscript() {
  if (meetingJobId == null) {
    showToast("meeting.k1267336");
    return;
  }
  const job = await api(`/api/jobs/${meetingJobId}`);
  await openJobExportModal(job);
}

async function clearMeetingView() {
  if (!window.confirm(t("meeting.k4303117"))) {
    return;
  }
  await api("/api/meeting/clear", { method: "POST" });
  meetingJobId = null;
  meetingSpeakerKeys = [];
  meetingLastSpeakersError = null;
  resetMeetingTranscript();
  const details = document.getElementById("meeting-speakers-details");
  if (details) {
    details.hidden = true;
    details.open = false;
  }
  syncMeetingSpeakersUi(null, { sessionActive: false, segments: [] });
  syncMeetingClearButton({ sessionActive: false, segments: [] });
  showToast("meeting.k2970777");
}

function selectedOptionName(selectEl) {
  const opt = selectEl && selectEl.selectedOptions && selectEl.selectedOptions[0];
  return opt ? opt.textContent : "";
}

function fillSelect(selectEl, items, selectedId, selectedName) {
  if (!selectEl) {
    return;
  }
  selectEl.innerHTML = "";
  for (const item of items || []) {
    const opt = document.createElement("option");
    opt.value = String(item.id);
    opt.textContent = item.name;
    selectEl.appendChild(opt);
  }
  const byId = selectedId != null && Array.from(selectEl.options).some((opt) => opt.value === String(selectedId));
  if (byId) {
    selectEl.value = String(selectedId);
    return;
  }
  if (selectedName) {
    const match = Array.from(selectEl.options).find((opt) => opt.textContent === selectedName);
    if (match) {
      selectEl.value = match.value;
    }
  }
}

function selectValue(selectEl) {
  if (!selectEl || selectEl.value === "") {
    return undefined;
  }
  const raw = selectEl.value;
  const asNum = Number(raw);
  if (Number.isFinite(asNum) && String(asNum) === raw) {
    return asNum;
  }
  return raw;
}

function syncMicEnabled() {
  const include = document.getElementById("meeting-include-mic");
  const micSelect = document.getElementById("meeting-mic-select");
  if (micSelect) {
    micSelect.disabled = !(include && include.checked) || micSelect.options.length === 0;
  }
}

function setRecordingChrome(
  sessionActive,
  { starting = false, paused = false, elapsed = 0, remaining = 0 } = {}
) {
  const panel = document.getElementById("view-meeting");
  const recBtn = document.getElementById("btn-meeting-rec");
  const pauseBtn = document.getElementById("btn-meeting-pause");
  const stopBtn = document.getElementById("btn-meeting-stop");
  const banner = document.getElementById("meeting-rec-banner");
  const bannerLabel = document.getElementById("meeting-rec-banner-label");
  const timer = document.getElementById("meeting-rec-timer");
  const countdown = document.getElementById("meeting-countdown");
  const capturing = Boolean(sessionActive) && !paused;
  const active = capturing || starting || (sessionActive && paused);
  panel?.classList.toggle("is-recording", capturing || starting);
  panel?.classList.toggle("is-paused", Boolean(sessionActive) && paused);
  if (recBtn) {
    recBtn.classList.toggle("is-recording", capturing || starting);
    setButtonLabelText(
      recBtn,
      "btn-meeting-rec-label",
      starting ? t("meeting.k9356652") : capturing ? t("meeting.k8798649") : t("meeting.k6860718")
    );
  }
  if (pauseBtn) {
    setButtonLabelText(
      pauseBtn,
      "btn-meeting-pause-label",
      paused ? t("meeting.k1581071") : t("batch_panel.k1098111")
    );
  }
  if (stopBtn) {
    stopBtn.classList.toggle("is-active-recording", Boolean(sessionActive));
  }
  if (banner) {
    banner.hidden = !active;
    banner.classList.toggle("is-paused", Boolean(sessionActive) && paused);
  }
  if (bannerLabel) {
    bannerLabel.textContent = paused ? t("batch_panel.k1098111") : t("meeting.k8798649");
  }
  if (timer) {
    timer.textContent = formatElapsed(elapsed);
  }
  if (countdown) {
    if (capturing) {
      const n = Math.max(0, Math.ceil(Number(remaining) || 0));
      countdown.textContent = t("meeting.nextChunkIn", { n });
    } else if (paused) {
      countdown.textContent = t("meeting.k9630112");
    } else if (starting) {
      countdown.textContent = t("meeting.k6194009");
    } else {
      countdown.textContent = "";
    }
  }
  syncMeetingStatusBadge({ sessionActive, paused, starting });
}

async function loadDevices({ refresh = false } = {}) {
  const outputSelect = document.getElementById("meeting-output-select");
  const micSelect = document.getElementById("meeting-mic-select");
  const recBtn = document.getElementById("btn-meeting-rec");
  const refreshBtn = document.getElementById("btn-meeting-refresh");
  const hint = document.getElementById("meeting-hint");
  if (!outputSelect || !recBtn) {
    return;
  }
  const prevOutId = outputSelect.value;
  const prevOutName = selectedOptionName(outputSelect);
  const prevMicId = micSelect ? micSelect.value : "";
  const prevMicName = selectedOptionName(micSelect);
  if (refresh && refreshBtn) {
    refreshBtn.disabled = true;
    setButtonLabelText(refreshBtn, "btn-meeting-refresh-label", t("meeting.k1772502"));
  }
  let payload = { outputs: [], mics: [], loopback_supported: true, default_output_id: null };
  try {
    payload = await api(refresh ? "/api/meeting/devices?refresh=1" : "/api/meeting/devices");
  } catch (err) {
    reportError(t("meeting.k7758738"), err);
  } finally {
    if (refreshBtn) {
      refreshBtn.disabled = false;
      setButtonLabelText(refreshBtn, "btn-meeting-refresh-label", t("meeting.k9872870"));
    }
  }
  const outputs = payload.outputs || [];
  const mics = payload.mics || [];
  fillSelect(outputSelect, outputs, prevOutId || payload.default_output_id, prevOutName);
  fillSelect(micSelect, mics, prevMicId || payload.default_input_id, prevMicName);
  const noLoopback = payload.loopback_supported === false;
  const emptyOut = outputs.length === 0 || noLoopback;
  recBtn.disabled = emptyOut || meetingStarting;
  outputSelect.disabled = emptyOut;
  syncMicEnabled();
  if (hint && !hint.dataset.stickyError) {
    if (noLoopback) {
      hint.textContent = t("meeting.k5273904");
    } else if (emptyOut) {
      hint.textContent = NO_OUTPUT_HINT;
    } else if (refresh) {
      hint.textContent = t("meeting.devicesRefreshed", {
        outputs: outputs.length,
        mics: mics.length,
      });
    } else {
      hint.textContent = "";
    }
  }
  if (refresh && !noLoopback && outputs.length) {
    showToast("meeting.k3118920");
  }
}

function resetMeetingTranscript() {
  meetingEditDirty = false;
  meetingTranscriptJobId = null;
  if (meetingSaveTimer) {
    clearTimeout(meetingSaveTimer);
    meetingSaveTimer = null;
  }
  meetingLastSegments = [];
  meetingSpeakerKeys = [];
  meetingLastSpeakersError = null;
  syncMeetingTranscriptFromSegments([], { force: true });
  syncMeetingPostActions({ sessionActive: false, segments: [] });
  syncMeetingTranscriptWait({ sessionActive: false, segments: [] });
  syncMeetingExportActions("");
  syncMeetingClearButton({ sessionActive: false, segments: [] });
  renderMeetingSpeakerRename([]);
}

function setMeter(id, rms, dbLabelId = null) {
  const el = document.getElementById(id);
  if (!el) {
    return;
  }
  const level = Number(rms) || 0;
  el.style.width = `${Math.min(100, Math.round(level * 400))}%`;
  if (dbLabelId) {
    const dbEl = document.getElementById(dbLabelId);
    if (dbEl) {
      dbEl.textContent = formatMeterDbLabel(level);
    }
  }
}

function syncMeetingStatusBadge({ sessionActive, paused, starting }) {
  const badge = document.getElementById("meeting-status-badge");
  if (!badge) {
    return;
  }
  if (starting) {
    badge.textContent = t("meeting.bentoStatusStarting");
  } else if (sessionActive && paused) {
    badge.textContent = t("meeting.bentoStatusPaused");
  } else if (sessionActive) {
    badge.textContent = t("meeting.bentoStatusRecording");
  } else {
    badge.textContent = t("meeting.bentoStatusIdle");
  }
}

async function pollMeeting() {
  const recBtn = document.getElementById("btn-meeting-rec");
  const pauseBtn = document.getElementById("btn-meeting-pause");
  const stopBtn = document.getElementById("btn-meeting-stop");
  const hint = document.getElementById("meeting-hint");
  const outputSelect = document.getElementById("meeting-output-select");
  const micSelect = document.getElementById("meeting-mic-select");
  const includeMic = document.getElementById("meeting-include-mic");
  const refreshBtn = document.getElementById("btn-meeting-refresh");

  const status = await api("/api/meeting/status");
  const sessionActive = Boolean(status.session_active);
  meetingSessionActiveFlag = sessionActive;
  const listening = Boolean(status.listening);
  const paused = Boolean(status.paused);
  const hasOutputs = outputSelect && outputSelect.options.length > 0;
  if (recBtn) {
    recBtn.disabled = !hasOutputs || sessionActive || meetingStarting;
  }
  if (pauseBtn) {
    pauseBtn.disabled = !sessionActive || meetingStarting;
  }
  if (stopBtn) {
    stopBtn.disabled = !sessionActive;
  }
  if (outputSelect) {
    outputSelect.disabled = sessionActive || !hasOutputs;
  }
  if (micSelect) {
    micSelect.disabled = sessionActive || !(includeMic && includeMic.checked) || micSelect.options.length === 0;
  }
  if (includeMic) {
    includeMic.disabled = sessionActive;
  }
  const saveAudio = document.getElementById("meeting-save-audio");
  if (saveAudio) {
    saveAudio.disabled = sessionActive;
  }
  if (refreshBtn) {
    refreshBtn.disabled = sessionActive || meetingStarting;
  }
  syncMicEnabled();
  setRecordingChrome(sessionActive, {
    starting: meetingStarting && !sessionActive,
    paused,
    elapsed: status.elapsed_s,
    remaining: status.remaining_s,
  });
  setMeter(
    "meeting-meter-system",
    listening ? status.rms_system : 0,
    "lbl-meter-system-val"
  );
  setMeter("meeting-meter-mic", listening ? status.rms_mic : 0, "lbl-meter-mic-val");
  syncMeetingStatusBadge({
    sessionActive,
    paused,
    starting: meetingStarting && !sessionActive,
  });
  if (hint && status.error) {
    hint.textContent = status.error;
    hint.dataset.stickyError = "1";
  }
  const jobId = status.job_id || meetingJobId;
  let captureFinalizing = Boolean(status.capture_finalizing);
  let jobStatus = "";
  if (jobId) {
    meetingJobId = jobId;
    let job = null;
    let segments = Array.isArray(status.segments) ? status.segments : null;
    if (!sessionActive) {
      job = await api(`/api/jobs/${jobId}`);
      jobStatus = job.status || "";
      captureFinalizing = captureFinalizing || Boolean(job.capture_finalizing);
      if (!segments) {
        segments = job.segments || [];
      }
      if (job.last_export_path) {
        syncMeetingExportActions(job.last_export_path);
      }
      syncMeetingRecordingActions(job.recording_path ? String(job.recording_path) : "");
      syncMeetingSpeakersUi(job, { sessionActive, segments });
      syncMeetingTranscriptFromSegments(segments || [], { jobId });
    } else if (segments) {
      syncMeetingTranscriptFromSegments(segments, { jobId });
    }
    const displaySegments = segments || meetingLastSegments;
    syncMeetingTranscriptWait({
      sessionActive,
      segments: displaySegments,
      jobStatus,
      captureFinalizing,
    });
    syncMeetingPostActions({ sessionActive, segments: displaySegments });
    syncMeetingClearButton({ sessionActive, segments: displaySegments });
  } else {
    syncMeetingTranscriptWait({
      sessionActive,
      segments: meetingLastSegments,
      jobStatus: "",
      captureFinalizing: false,
    });
    syncMeetingPostActions({ sessionActive, segments: meetingLastSegments });
    syncMeetingClearButton({ sessionActive, segments: meetingLastSegments });
    syncMeetingAutoSpeakersOption(sessionActive);
  }
  if (
    !sessionActive &&
    meetingPollTimer &&
    !meetingStarting &&
    !meetingAwaitingTranscript &&
    !captureFinalizing
  ) {
    clearInterval(meetingPollTimer);
    meetingPollTimer = null;
  }
  if (meetingAwaitingTranscript && !meetingPollTimer) {
    startMeetingPoll();
  }
  return status;
}

function startMeetingPoll() {
  if (!meetingPollTimer) {
    meetingPollTimer = setInterval(
      () => pollMeeting().catch((err) => reportError(t("jobSource.meeting.label"), err)),
      300
    );
  }
  pollMeeting().catch((err) => reportError(t("jobSource.meeting.label"), err));
}

async function startMeeting() {
  const hint = document.getElementById("meeting-hint");
  const recBtn = document.getElementById("btn-meeting-rec");
  const outputSelect = document.getElementById("meeting-output-select");
  const micSelect = document.getElementById("meeting-mic-select");
  const includeMic = document.getElementById("meeting-include-mic");
  if (meetingStarting) {
    return;
  }
  if (hint) {
    hint.textContent = "";
    delete hint.dataset.stickyError;
  }
  resetMeetingTranscript();
  meetingSpeakerKeys = [];
  meetingLastSpeakersError = null;
  meetingStarting = true;
  setRecordingChrome(false, { starting: true });
  syncMeetingTranscriptWait({ sessionActive: true, segments: [] });
  if (recBtn) {
    recBtn.disabled = true;
  }
  const saveAudioEl = document.getElementById("meeting-save-audio");
  const body = {
    include_mic: Boolean(includeMic && includeMic.checked),
    save_audio: saveAudioEl ? Boolean(saveAudioEl.checked) : true,
  };
  const outputId = selectValue(outputSelect);
  if (outputId !== undefined) {
    body.output_device_id = outputId;
  }
  if (body.include_mic) {
    const micId = selectValue(micSelect);
    if (micId !== undefined) {
      body.mic_device_id = micId;
    }
  }
  try {
    const job = await api("/api/meeting/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    meetingJobId = job.id;
    meetingAwaitingTranscript = false;
    showToast("meeting.k4613980");
    startMeetingPoll();
  } finally {
    meetingStarting = false;
  }
}

async function toggleMeetingPause() {
  const status = await api("/api/meeting/status");
  if (!status.session_active) {
    return;
  }
  if (status.paused) {
    await api("/api/meeting/resume", { method: "POST" });
    showToast("meeting.k1824371");
  } else {
    await api("/api/meeting/pause", { method: "POST" });
    showToast("meeting.k5172254");
  }
  await pollMeeting();
}

async function stopMeeting() {
  if (!window.confirm(t("meeting.k3917827"))) {
    return;
  }
  if (!hasMeetingTranscriptText(meetingLastSegments)) {
    meetingAwaitingTranscript = true;
    syncMeetingTranscriptWait({
      sessionActive: true,
      segments: meetingLastSegments,
      jobStatus: "running",
      captureFinalizing: false,
    });
  }
  const stopped = await api("/api/meeting/stop", { method: "POST" });
  if (stopped?.recording_path) {
    syncMeetingRecordingActions(stopped.recording_path);
  } else {
    syncMeetingRecordingActions("");
  }
  setRecordingChrome(false);
  showToast("meeting.k5299764");
  await pollMeeting();
  if (meetingEditDirty && meetingJobId != null) {
    await waitForMeetingCaptureFinalize(meetingJobId);
    await saveMeetingTranscript();
  }
  await refreshLibrary();
  if (document.getElementById("meeting-auto-speakers")?.checked && meetingJobId != null) {
    await waitForMeetingCaptureFinalize(meetingJobId);
    await runMeetingSpeakers();
  }
}

export function initMeeting() {
  if (meetingInitialized) {
    return;
  }
  meetingInitialized = true;
  loadTimestampsPreference();
  loadAutoSpeakersPreference();
  loadSaveAudioPreference();
  syncMeetingAutoSpeakersOption(false);
  loadMeetingSetupStatus().catch(() => {});
  document.getElementById("meeting-show-timestamps")?.addEventListener("change", () => {
    saveTimestampsPreference();
    if (!meetingEditDirty) {
      syncMeetingTranscriptFromSegments(meetingLastSegments, { jobId: meetingJobId });
    }
  });
  const transcript = meetingTranscriptEl();
  if (transcript) {
    transcript.setAttribute("aria-label", t("live.transcriptLabel"));
    transcript.addEventListener("input", () => {
      meetingEditDirty = true;
      scheduleMeetingTranscriptSave();
      updateMeetingCounterStats();
      const hasText = hasMeetingTranscriptText(meetingLastSegments);
      const panel = document.getElementById("meeting-post-actions");
      const copyBtn = document.getElementById("btn-meeting-copy");
      if (panel) {
        panel.hidden = Boolean(meetingSessionActiveFlag) || !hasText;
      }
      if (copyBtn) {
        copyBtn.disabled = !hasText;
      }
      syncMeetingClearButton({ sessionActive: meetingSessionActiveFlag, segments: meetingLastSegments });
    });
  }
  document.getElementById("meeting-auto-speakers")?.addEventListener("change", () => {
    saveAutoSpeakersPreference();
  });
  document.getElementById("meeting-save-audio")?.addEventListener("change", () => {
    saveSaveAudioPreference();
  });
  document.getElementById("btn-meeting-clear")?.addEventListener("click", () =>
    clearMeetingView().catch((err) => reportError(t("meeting.k5445934"), err))
  );
  document.getElementById("btn-meeting-speakers")?.addEventListener("click", () =>
    runMeetingSpeakers().catch((err) => reportError(t("meeting.k3909903"), err))
  );
  document.getElementById("btn-meeting-speakers-stop")?.addEventListener("click", () =>
    cancelMeetingSpeakers().catch((err) => reportError(t("meeting.k3909903"), err))
  );
  document.getElementById("btn-meeting-copy")?.addEventListener("click", () =>
    copyMeetingTranscript().catch((err) => reportError(t("meeting.k9147187"), err))
  );
  document.getElementById("btn-meeting-export")?.addEventListener("click", () =>
    exportMeetingTranscript().catch((err) => reportError(t("common.export"), err))
  );
  document.getElementById("btn-meeting-open-export")?.addEventListener("click", () =>
    openLocalPath(meetingLastExportPath, false).catch((err) => reportError(t("meeting.k8629842"), err))
  );
  document.getElementById("btn-meeting-open-export-folder")?.addEventListener("click", () =>
    openLocalPath(meetingLastExportPath, true).catch((err) => reportError(t("meeting.k864377"), err))
  );
  document.getElementById("btn-meeting-open-recording")?.addEventListener("click", () =>
    openLocalPath(meetingLastRecordingPath, false).catch((err) =>
      reportError(t("meeting.openRecording"), err)
    )
  );
  document.getElementById("btn-meeting-open-recording-folder")?.addEventListener("click", () =>
    openLocalPath(meetingLastRecordingPath, true).catch((err) =>
      reportError(t("meeting.openRecordingFolder"), err)
    )
  );
  window.addEventListener("gigaam:job-exported", (event) => {
    const { jobId, path } = event.detail || {};
    if (jobId != null && jobId === meetingJobId) {
      syncMeetingExportActions(path);
    }
  });
  document.getElementById("btn-meeting-rec")?.addEventListener("click", () =>
    startMeeting().catch((err) => {
      meetingStarting = false;
      setRecordingChrome(false);
      syncMeetingTranscriptWait({ sessionActive: false, segments: [] });
      const hint = document.getElementById("meeting-hint");
      if (hint) {
        hint.textContent = err.message || NO_OUTPUT_HINT;
        hint.dataset.stickyError = "1";
      }
      const recBtn = document.getElementById("btn-meeting-rec");
      if (recBtn) {
        recBtn.disabled = false;
        setButtonLabelText(recBtn, "btn-meeting-rec-label", t("meeting.k6860718"));
      }
    })
  );
  document.getElementById("btn-meeting-pause")?.addEventListener("click", () =>
    toggleMeetingPause().catch((err) => reportError(t("meeting.k4591805"), err))
  );
  document.getElementById("btn-meeting-stop")?.addEventListener("click", () =>
    stopMeeting().catch((err) => reportError(t("jobSource.meeting.label"), err))
  );
  document.getElementById("btn-meeting-refresh")?.addEventListener("click", () => {
    const hint = document.getElementById("meeting-hint");
    if (hint) {
      delete hint.dataset.stickyError;
    }
    loadDevices({ refresh: true }).catch((err) => reportError(t("meeting.k9267804"), err));
  });
  document.getElementById("meeting-include-mic")?.addEventListener("change", () => syncMicEnabled());
  const leadBtn = document.getElementById("btn-meeting-lead-toggle");
  const leadP = document.getElementById("meeting-lead");
  const leadLbl = document.getElementById("lbl-meeting-lead-toggle");
  const leadIcon = document.getElementById("icon-meeting-lead-toggle");
  if (leadBtn && leadP) {
    leadBtn.addEventListener("click", () => {
      const isHidden = leadP.classList.contains("hidden");
      leadP.classList.toggle("hidden", !isHidden);
      leadBtn.setAttribute("aria-expanded", String(isHidden));
      if (leadLbl) {
        leadLbl.textContent = isHidden ? t("meeting.leadToggleHide") : t("meeting.leadToggleMore");
      }
      if (leadIcon) {
        leadIcon.style.transform = isHidden ? "rotate(180deg)" : "rotate(0deg)";
      }
    });
  }
  loadDevices().catch((err) => reportError(t("meeting.k9267804"), err));
}

export async function onMeetingShow() {
  loadTimestampsPreference();
  loadAutoSpeakersPreference();
  loadSaveAudioPreference();
  await loadMeetingSetupStatus().catch(() => {});
  await loadDevices().catch((err) => reportError(t("meeting.k9267804"), err));
  const status = await pollMeeting().catch((err) => reportError(t("jobSource.meeting.label"), err));
  if (status && status.session_active) {
    startMeetingPoll();
  }
}
