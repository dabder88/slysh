import { api, showToast } from "./api.js";
import { reportError } from "./errors.js";
import { openJobExportModal, openLocalPath, refreshLibrary, startSpeakers, uniqueSpeakers, waitForSpeakers } from "./legacy.js";
import { speakerDisplayName, speakerKeysForRename } from "./library-utils.js";
import { formatMsClock } from "./media-time.js";
import { t } from "./i18n.js";

const NO_OUTPUT_HINT =
  t("meeting.k4303073");
const TIMESTAMPS_KEY = "meeting-show-timestamps";
const AUTO_SPEAKERS_KEY = "meeting-auto-speakers";

let meetingInitialized = false;
let meetingPollTimer = null;
let meetingJobId = null;
let meetingStarting = false;
let meetingRenderedCount = 0;
let meetingRenderedJobId = null;
let meetingLastSegments = [];
let meetingLastExportPath = "";
let meetingLastSpeakersError = null;
let meetingSpeakerKeys = [];
let meetingEnginePackagesOk = true;

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

function hasMeetingTranscriptText(segments) {
  return (segments || []).some((seg) => Boolean(formatSegmentBody(seg)));
}

function createSegmentParagraph(seg, showTimestamps) {
  const p = document.createElement("p");
  const line = formatSegmentLine(seg, showTimestamps);
  if (!line) {
    return p;
  }
  if (showTimestamps && seg.start_ms != null) {
    const time = document.createElement("span");
    time.className = "seg-time";
    time.textContent = `[${formatMsClock(seg.start_ms)}]`;
    p.appendChild(time);
    p.appendChild(document.createTextNode(formatSegmentBody(seg)));
  } else {
    p.textContent = line;
  }
  return p;
}

function hasTextSelection() {
  const sel = window.getSelection();
  return Boolean(sel && sel.toString().trim());
}

function syncMeetingTranscriptWait({ sessionActive, segments }) {
  const wait = document.getElementById("meeting-transcript-wait");
  if (!wait) {
    return;
  }
  const show = Boolean(sessionActive) && !hasMeetingTranscriptText(segments);
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
    badge.textContent = speakerDisplayName(key, names[key]);
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

function syncMeetingSpeakersUi(job, { sessionActive, segments } = {}) {
  const btn = document.getElementById("btn-meeting-speakers");
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
    btn.hidden = Boolean(sessionActive) || !hasText || !completed;
    btn.disabled = running || !meetingEnginePackagesOk;
    if (!meetingEnginePackagesOk) {
      btn.title = t("meeting.k607940");
    } else {
      btn.removeAttribute("title");
    }
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
    showToast(job.speakers_error);
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
  renderMeetingTranscript(job.segments || [], meetingJobId);
  syncMeetingSpeakersUi(job, { sessionActive: false, segments: job.segments || [] });
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
      },
    });
    meetingSpeakerKeys = speakerKeysForRename(job.segments || []);
    renderMeetingTranscript(job.segments || [], meetingJobId);
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
  const text = buildMeetingCopyText(meetingLastSegments);
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
  openJobExportModal(job);
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
    recBtn.textContent = starting ? t("meeting.k9356652") : capturing ? t("meeting.k8798649") : t("meeting.k6860718");
  }
  if (pauseBtn) {
    pauseBtn.textContent = paused ? t("meeting.k1581071") : t("batch_panel.k1098111");
  }
  if (stopBtn) {
    stopBtn.classList.toggle("btn-danger", Boolean(sessionActive));
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
    refreshBtn.textContent = t("meeting.k1772502");
  }
  let payload = { outputs: [], mics: [], loopback_supported: true, default_output_id: null };
  try {
    payload = await api(refresh ? "/api/meeting/devices?refresh=1" : "/api/meeting/devices");
  } catch (err) {
    reportError(t("meeting.k7758738"), err);
  } finally {
    if (refreshBtn) {
      refreshBtn.disabled = false;
      refreshBtn.textContent = t("meeting.k9872870");
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
  const box = document.getElementById("meeting-transcript");
  if (box) {
    box.innerHTML = "";
  }
  meetingRenderedCount = 0;
  meetingRenderedJobId = null;
  meetingLastSegments = [];
  meetingSpeakerKeys = [];
  meetingLastSpeakersError = null;
  syncMeetingPostActions({ sessionActive: false, segments: [] });
  syncMeetingTranscriptWait({ sessionActive: false, segments: [] });
  syncMeetingExportActions("");
  syncMeetingClearButton({ sessionActive: false, segments: [] });
  renderMeetingSpeakerRename([]);
}

function renderMeetingTranscript(segments, jobId) {
  const box = document.getElementById("meeting-transcript");
  if (!box) {
    return;
  }
  if (jobId != null && meetingRenderedJobId !== jobId) {
    box.innerHTML = "";
    meetingRenderedCount = 0;
    meetingRenderedJobId = jobId;
  }
  const items = segments || [];
  meetingLastSegments = items;
  const showTimestamps = showMeetingTimestamps();
  box.innerHTML = "";
  for (const seg of items) {
    const p = createSegmentParagraph(seg, showTimestamps);
    if (p.textContent || p.childNodes.length) {
      box.appendChild(p);
    }
  }
  meetingRenderedCount = items.length;
  if (!hasTextSelection()) {
    box.scrollTop = box.scrollHeight;
  }
}

function appendMeetingSegments(segments, jobId) {
  const box = document.getElementById("meeting-transcript");
  if (!box) {
    return;
  }
  if (jobId != null && meetingRenderedJobId !== jobId) {
    box.innerHTML = "";
    meetingRenderedCount = 0;
    meetingRenderedJobId = jobId;
  }
  const items = segments || [];
  meetingLastSegments = items;
  const showTimestamps = showMeetingTimestamps();
  if (items.length < meetingRenderedCount) {
    renderMeetingTranscript(items, jobId);
    return;
  }
  if (items.length === meetingRenderedCount) {
    return;
  }
  for (let i = meetingRenderedCount; i < items.length; i += 1) {
    const p = createSegmentParagraph(items[i], showTimestamps);
    if (p.textContent || p.childNodes.length) {
      box.appendChild(p);
    }
  }
  meetingRenderedCount = items.length;
  if (!hasTextSelection()) {
    box.scrollTop = box.scrollHeight;
  }
}

function setMeter(id, rms) {
  const el = document.getElementById(id);
  if (!el) {
    return;
  }
  el.style.width = `${Math.min(100, Math.round((Number(rms) || 0) * 400))}%`;
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
  setMeter("meeting-meter-system", listening ? status.rms_system : 0);
  setMeter("meeting-meter-mic", listening ? status.rms_mic : 0);
  if (hint && status.error) {
    hint.textContent = status.error;
    hint.dataset.stickyError = "1";
  }
  const jobId = status.job_id || meetingJobId;
  if (jobId) {
    meetingJobId = jobId;
    let job = null;
    let segments = Array.isArray(status.segments) ? status.segments : null;
    if (!sessionActive) {
      job = await api(`/api/jobs/${jobId}`);
      if (!segments) {
        segments = job.segments || [];
      }
      if (job.last_export_path) {
        syncMeetingExportActions(job.last_export_path);
      }
      syncMeetingSpeakersUi(job, { sessionActive, segments });
      const needsFullRender =
        job.speakers_running || job.has_speakers || (segments || []).some((seg) => seg.speaker);
      if (needsFullRender) {
        renderMeetingTranscript(segments, jobId);
      } else {
        appendMeetingSegments(segments, jobId);
      }
    } else if (segments) {
      appendMeetingSegments(segments, jobId);
    }
    const displaySegments = segments || meetingLastSegments;
    syncMeetingTranscriptWait({ sessionActive, segments: displaySegments });
    syncMeetingPostActions({ sessionActive, segments: displaySegments });
    syncMeetingClearButton({ sessionActive, segments: displaySegments });
  } else {
    syncMeetingTranscriptWait({ sessionActive, segments: meetingLastSegments });
    syncMeetingPostActions({ sessionActive, segments: meetingLastSegments });
    syncMeetingClearButton({ sessionActive, segments: meetingLastSegments });
    syncMeetingAutoSpeakersOption(sessionActive);
  }
  if (!sessionActive && meetingPollTimer && !meetingStarting) {
    clearInterval(meetingPollTimer);
    meetingPollTimer = null;
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
  const body = {
    include_mic: Boolean(includeMic && includeMic.checked),
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
  await api("/api/meeting/stop", { method: "POST" });
  setRecordingChrome(false);
  showToast("meeting.k5299764");
  await pollMeeting();
  await refreshLibrary();
  if (document.getElementById("meeting-auto-speakers")?.checked) {
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
  syncMeetingAutoSpeakersOption(false);
  loadMeetingSetupStatus().catch(() => {});
  document.getElementById("meeting-show-timestamps")?.addEventListener("change", () => {
    saveTimestampsPreference();
    renderMeetingTranscript(meetingLastSegments, meetingRenderedJobId);
  });
  document.getElementById("meeting-auto-speakers")?.addEventListener("change", () => {
    saveAutoSpeakersPreference();
  });
  document.getElementById("btn-meeting-clear")?.addEventListener("click", () =>
    clearMeetingView().catch((err) => reportError(t("meeting.k5445934"), err))
  );
  document.getElementById("btn-meeting-speakers")?.addEventListener("click", () =>
    runMeetingSpeakers().catch((err) => reportError(t("meeting.k3909903"), err))
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
        recBtn.textContent = t("meeting.k6860718");
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
  loadDevices().catch((err) => reportError(t("meeting.k9267804"), err));
}

export async function onMeetingShow() {
  loadTimestampsPreference();
  loadAutoSpeakersPreference();
  await loadMeetingSetupStatus().catch(() => {});
  await loadDevices().catch((err) => reportError(t("meeting.k9267804"), err));
  const status = await pollMeeting().catch((err) => reportError(t("jobSource.meeting.label"), err));
  if (status && status.session_active) {
    startMeetingPoll();
  }
}
