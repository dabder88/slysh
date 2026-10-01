import { fillRangeInputs, formatMsClock, peekRange } from "./media-time.js";
import { api, jobDisplayName, isYoutubeJob, formatDuration, showToast } from "./api.js";
import { jobSourceLabel } from "./job-source.js";
import { reportError } from "./errors.js";
import { getRoute, navigate } from "./router.js";
import { batchById, jobStatusLabel } from "./library-store.js";
import { localeDateTag, t } from "./i18n.js";
import {
  selectJob,
  setEditorRefreshHook,
  refreshLibrary,
  syncExportActions,
  openBatchExportModal,
} from "./legacy.js";

let editorBound = false;
let currentJobId = null;
let currentJob = null;
let editorMode = "view";
let searchQuery = "";
let activeSegmentIndex = -1;
let renderedSegmentCount = 0;
let renderedSegmentJobId = null;
let editorPollTimer = null;
let editorDraftDirty = false;
const editorDrafts = new Map();
let editorPollFetchId = 0;
let transcriptFollowTail = true;
const PLAYER_COLLAPSE_KEY = "editor-player-collapsed-v2";
const TRANSCRIPT_COLLAPSE_KEY = "editor-transcript-collapsed";
const PLAYER_WIDTH_KEY = "editor-player-width-v2";
const PLAYER_WIDTH_DEFAULT = 400;
const PLAYER_WIDTH_MIN = 240;
const PLAYER_WIDTH_MAX = 520;

let rangeFilledForJob = null;
const SPEAKER_TONES = ["primary", "secondary", "primary", "secondary"];

function formatClock(ms) {
  const total = Math.max(0, Math.floor(Number(ms || 0) / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  if (hours) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function formatPlayerTime(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${minutes}:${String(secs).padStart(2, "0")}`;
}

function segmentSpeakerKey(seg) {
  return seg.speaker_key ?? seg.speaker ?? "";
}

function segmentSpeakerDisplay(seg) {
  return seg.speaker || "";
}

function speakerLabel(speaker, index) {
  if (!speaker) {
    return t("editor.k3146264");
  }
  if (/^SPEAKER_/i.test(speaker)) {
    return t("editor.speakerN", { n: index + 1 });
  }
  return speaker;
}

function setPlayerCollapsed(collapsed, persist = true) {
  const panel = document.getElementById("editor-player-panel");
  const body = document.getElementById("editor-player-body");
  const compact = document.getElementById("editor-player-compact");
  const toggle = document.getElementById("editor-toggle-player");
  const icon = document.getElementById("editor-toggle-player-icon");
  if (!panel) {
    return;
  }
  panel.classList.toggle("is-collapsed", collapsed);
  if (body) {
    body.hidden = collapsed;
  }
  if (compact) {
    compact.hidden = !collapsed;
  }
  if (toggle) {
    toggle.title = collapsed ? t("editor.k5766080") : t("editor.k1001068");
    toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
  }
  if (icon) {
    icon.textContent = collapsed ? "expand_more" : "expand_less";
  }
  if (persist) {
    localStorage.setItem(PLAYER_COLLAPSE_KEY, collapsed ? "1" : "0");
  }
}

function setTranscriptCollapsed(collapsed, persist = true) {
  const layout = document.getElementById("editor-layout");
  const panel = document.getElementById("editor-transcript-panel");
  const body = document.getElementById("editor-transcript-body");
  const compact = document.getElementById("editor-transcript-compact");
  const toggle = document.getElementById("editor-toggle-transcript");
  const icon = document.getElementById("editor-toggle-transcript-icon");
  const resizer = document.getElementById("editor-resizer-player");
  if (!panel) {
    return;
  }
  layout?.classList.toggle("is-transcript-collapsed", collapsed);
  panel.classList.toggle("is-collapsed", collapsed);
  if (body) {
    body.hidden = collapsed;
  }
  if (compact) {
    compact.hidden = !collapsed;
  }
  if (resizer) {
    resizer.hidden = collapsed;
  }
  if (toggle) {
    toggle.hidden = collapsed;
    toggle.title = collapsed ? t("editor.k3189977") : t("editor.k5041225");
    toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
  }
  const head = panel.querySelector(".editor-panel-head");
  if (head) {
    head.hidden = collapsed;
  }
  if (icon) {
    icon.textContent = collapsed ? "expand_more" : "expand_less";
  }
  if (persist) {
    localStorage.setItem(TRANSCRIPT_COLLAPSE_KEY, collapsed ? "1" : "0");
  }
}

function applyDefaultPlayerCollapse() {
  const saved = localStorage.getItem(PLAYER_COLLAPSE_KEY);
  setPlayerCollapsed(saved === "1", false);
}

function applyDefaultTranscriptCollapse() {
  const saved = localStorage.getItem(TRANSCRIPT_COLLAPSE_KEY);
  setTranscriptCollapsed(saved === "1", false);
}

function syncSpeakersPanel() {
  const details = document.getElementById("editor-speakers-details");
  const rename = document.getElementById("speaker-rename");
  if (!details || !rename) {
    return;
  }
  const visible = !rename.hidden && rename.children.length > 0;
  details.hidden = !visible;
}

function setEditorMode(mode) {
  editorMode = mode;
  const panel = document.querySelector(".editor-panel--main");
  const segmentsEl = document.getElementById("editor-segments");
  const textarea = document.getElementById("transcript-edit");
  const hint = document.getElementById("transcript-hint");
  const saveBtn = document.getElementById("btn-save");
  const exportActions = document.getElementById("export-actions");
  document.getElementById("editor-mode-view")?.classList.toggle("is-active", mode === "view");
  document.getElementById("editor-mode-edit")?.classList.toggle("is-active", mode === "edit");
  panel?.classList.toggle("is-mode-view", mode === "view");
  panel?.classList.toggle("is-mode-edit", mode === "edit");
  if (segmentsEl) {
    segmentsEl.hidden = mode !== "view";
  }
  if (textarea) {
    textarea.hidden = mode !== "edit";
  }
  if (hint) {
    hint.hidden = mode !== "edit" || !textarea?.value;
  }
  const hasText = Boolean(textarea?.value) || Boolean(currentJob?.transcript);
  if (saveBtn) {
    saveBtn.hidden = mode !== "edit" || !hasText;
  }
  if (mode === "edit") {
    if (exportActions) {
      exportActions.hidden = true;
    }
  } else {
    syncExportActions(currentJob);
  }
  syncEditModeAvailability(currentJob);
}

function syncEditModeAvailability(job) {
  const editBtn = document.getElementById("editor-mode-edit");
  const runningFile =
    job?.kind === "file" && job?.status === "running" && !job?.speakers_running;
  if (editBtn) {
    editBtn.disabled = Boolean(runningFile);
    editBtn.title = runningFile ? t("editor.k5279584") : "";
  }
}

function shouldPollEditorJob(job) {
  if (!job) {
    return false;
  }
  if (isYoutubeJob(job)) {
    return job.status === "queued" || job.status === "running";
  }
  return job.kind === "file" && job.status === "running" && !job.speakers_running;
}

function stopEditorPoll() {
  if (editorPollTimer) {
    clearInterval(editorPollTimer);
    editorPollTimer = null;
  }
}

async function pollEditorJob() {
  if (!currentJobId || getRoute() !== "editor") {
    stopEditorPoll();
    return;
  }
  const jobId = currentJobId;
  const fetchId = ++editorPollFetchId;
  const job = await api(`/api/jobs/${jobId}`);
  if (jobId !== currentJobId || fetchId !== editorPollFetchId) {
    return;
  }
  currentJob = job;
  syncEditModeAvailability(job);
  if (editorMode === "view" && !editorDraftDirty) {
    renderSegments(job);
  }
  updateTransport(job);
  if (!shouldPollEditorJob(job)) {
    stopEditorPoll();
    if (job.status === "completed" || job.status === "failed" || job.status === "cancelled") {
      renderBatchPanel(job);
      syncSpeakersPanel();
      drawWaveform(job);
      await refreshLibrary();
    }
  }
}

function startEditorPoll() {
  stopEditorPoll();
  editorPollTimer = setInterval(() => {
    pollEditorJob().catch((err) => reportError(t("topbar.editor"), err));
  }, 400);
  pollEditorJob().catch((err) => reportError(t("topbar.editor"), err));
}

function mediaDurationSeconds(job) {
  const player = document.getElementById("player");
  const fromPlayer = Number(player?.duration);
  if (Number.isFinite(fromPlayer) && fromPlayer > 0) {
    return fromPlayer;
  }
  const segs = job?.segments || [];
  if (segs.length) {
    return Math.max(0, Number(segs[segs.length - 1].end_ms || 0) / 1000);
  }
  return 0;
}

function timeAtWaveformX(clientX) {
  const canvas = document.getElementById("editor-waveform");
  const player = document.getElementById("player");
  if (!canvas || !player) {
    return 0;
  }
  const rect = canvas.getBoundingClientRect();
  const width = rect.width || 1;
  const pct = Math.min(1, Math.max(0, (clientX - rect.left) / width));
  const total = mediaDurationSeconds(currentJob);
  return pct * total;
}

function drawWaveform(job) {
  const canvas = document.getElementById("editor-waveform");
  if (!canvas) {
    return;
  }
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    return;
  }
  const cssWidth = Math.max(1, Math.floor(canvas.clientWidth || canvas.width || 320));
  const cssHeight = Math.max(1, Math.floor(canvas.clientHeight || canvas.height || 56));
  if (canvas.width !== cssWidth || canvas.height !== cssHeight) {
    canvas.width = cssWidth;
    canvas.height = cssHeight;
  }
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  const rootStyle = getComputedStyle(document.documentElement);
  const colorPrimary = rootStyle.getPropertyValue("--primary").trim() || "#000666";
  const colorOutline = rootStyle.getPropertyValue("--outline-variant").trim() || "#c6c5d4";
  const colorSurface = rootStyle.getPropertyValue("--surface-container-low").trim() || "#f0f3ff";
  const colorError = rootStyle.getPropertyValue("--error").trim() || "#ba1a1a";
  const colorRange = "rgba(67, 85, 185, 0.22)";

  ctx.fillStyle = colorSurface;
  ctx.fillRect(0, 0, width, height);

  const player = document.getElementById("player");
  const totalS = mediaDurationSeconds(job);
  const totalMs = Math.max(totalS * 1000, 1);
  const range = peekRange();
  if (range.start_ms != null || range.end_ms != null) {
    const startPct = (range.start_ms || 0) / totalMs;
    const endPct = (range.end_ms == null ? totalMs : range.end_ms) / totalMs;
    ctx.fillStyle = colorRange;
    const x0 = Math.min(startPct, endPct) * width;
    const x1 = Math.max(startPct, endPct) * width;
    ctx.fillRect(x0, 0, Math.max(2, x1 - x0), height);
  }

  const segments = job?.segments || [];
  const barCount = Math.max(48, Math.floor(width / 6));
  const gap = 2;
  const barWidth = (width - gap * (barCount - 1)) / barCount;

  for (let i = 0; i < barCount; i += 1) {
    const t = ((i + 0.5) / barCount) * totalMs;
    const seg = segments.find((s) => s.start_ms <= t && t <= s.end_ms);
    const energy = seg ? 0.45 + ((i * 17) % 40) / 100 : 0.18 + ((i * 11) % 20) / 100;
    const barHeight = Math.max(6, height * energy);
    const x = i * (barWidth + gap);
    ctx.fillStyle = seg ? colorPrimary : colorOutline;
    ctx.fillRect(x, (height - barHeight) / 2, barWidth, barHeight);
  }

  if (player && totalS) {
    const pct = Math.min(1, Math.max(0, (player.currentTime || 0) / totalS));
    ctx.fillStyle = colorError;
    ctx.fillRect(pct * width, 0, 2, height);
  }
}

function updateTransport(job) {
  const player = document.getElementById("player");
  const currentEl = document.getElementById("editor-time-current");
  const totalEl = document.getElementById("editor-time-total");
  const icon = document.getElementById("editor-play-icon");
  if (!player) {
    return;
  }
  if (currentEl) {
    currentEl.textContent = formatPlayerTime(player.currentTime);
  }
  if (totalEl) {
    const total = player.duration || job?.duration_s || 0;
    totalEl.textContent = formatPlayerTime(total);
  }
  if (icon) {
    icon.textContent = player.paused ? "play_arrow" : "pause";
  }
  const compactIcon = document.querySelector("#editor-play-compact .material-symbols-outlined");
  if (compactIcon) {
    compactIcon.textContent = player.paused ? "play_arrow" : "pause";
  }
  const compactTime = document.getElementById("editor-time-compact");
  if (compactTime) {
    const total = player.duration || job?.duration_s || 0;
    compactTime.textContent = `${formatPlayerTime(player.currentTime)} / ${formatPlayerTime(total)}`;
  }
  drawWaveform(job || currentJob);
  highlightActiveSegment(player.currentTime * 1000);
}

function highlightActiveSegment(currentMs) {
  const blocks = document.querySelectorAll(".editor-segment");
  let nextActive = -1;
  blocks.forEach((block, index) => {
    const start = Number(block.dataset.startMs || 0);
    const end = Number(block.dataset.endMs || start + 1);
    const active = currentMs >= start && currentMs < end;
    block.classList.toggle("is-active", active);
    if (active) {
      nextActive = index;
    }
  });
  activeSegmentIndex = nextActive;
}

function findSegmentElementAtMs(startMs) {
  const target = Math.max(0, Number(startMs) || 0);
  const blocks = [...document.querySelectorAll(".editor-segment")];
  let best = null;
  let bestStart = -1;
  for (const block of blocks) {
    const start = Number(block.dataset.startMs || 0);
    if (start <= target && start >= bestStart) {
      bestStart = start;
      best = block;
    }
  }
  if (best) {
    return best;
  }
  return blocks.reduce((first, block) => {
    if (!first) {
      return block;
    }
    const a = Number(first.dataset.startMs || 0);
    const b = Number(block.dataset.startMs || 0);
    return b < a ? block : first;
  }, null);
}

function highlightSegmentBlock(block) {
  document.querySelectorAll(".editor-segment").forEach((el) => {
    el.classList.toggle("is-active", el === block);
  });
  activeSegmentIndex = block ? Number(block.dataset.index || -1) : -1;
}

function scrollToTranscriptMs(startMs, job = currentJob) {
  const block = findSegmentElementAtMs(startMs);
  if (!block) {
    if (searchQuery.trim() && job?.segments?.length) {
      const target = Math.max(0, Number(startMs) || 0);
      const hasTarget = job.segments.some((seg) => Number(seg.start_ms) <= target);
      if (hasTarget) {
        showToast("editor.k4078752");
        return false;
      }
    }
    showToast("editor.k7603758");
    return false;
  }
  block.scrollIntoView({ behavior: "smooth", block: "center" });
  highlightSegmentBlock(block);
  return true;
}

function collectSpeakers(segments) {
  const speakers = [];
  segments.forEach((seg) => {
    const key = segmentSpeakerKey(seg);
    if (key && !speakers.includes(key)) {
      speakers.push(key);
    }
  });
  return speakers;
}

function createSegmentBlock(seg, index, job, speakers, youtube) {
  const text = (seg.text || "").trim();
  const speakerIndex = speakers.indexOf(segmentSpeakerKey(seg));
  const tone = SPEAKER_TONES[speakerIndex >= 0 ? speakerIndex % SPEAKER_TONES.length : 0];

  const block = document.createElement("article");
  block.className = "editor-segment";
  block.dataset.startMs = String(seg.start_ms);
  block.dataset.endMs = String(seg.end_ms);
  block.dataset.index = String(index);

  const meta = document.createElement("div");
  meta.className = "editor-segment-meta";
  const speaker = document.createElement("span");
  speaker.className = `editor-segment-speaker editor-segment-speaker--${tone}`;
  speaker.textContent = speakerLabel(segmentSpeakerDisplay(seg), speakerIndex);
  const time = document.createElement("span");
  time.className = youtube
    ? "hint editor-segment-time editor-segment-time--jump"
    : "hint editor-segment-time";
  time.textContent = formatClock(seg.start_ms);
  if (youtube) {
    time.setAttribute("role", "button");
    time.tabIndex = 0;
  }
  meta.appendChild(speaker);
  meta.appendChild(time);

  const body = document.createElement("div");
  body.className = "editor-segment-body";
  const p = document.createElement("p");
  p.textContent = text || "…";
  body.appendChild(p);

  block.appendChild(meta);
  block.appendChild(body);
  const jumpToSegment = () => {
    scrollToTranscriptMs(seg.start_ms, job);
  };
  block.addEventListener("click", () => {
    if (youtube) {
      jumpToSegment();
      return;
    }
    const player = document.getElementById("player");
    if (player) {
      player.currentTime = Math.max(0, seg.start_ms / 1000);
      player.play().catch(() => {});
      updateTransport(job);
    }
  });
  if (youtube) {
    time.addEventListener("click", (event) => {
      event.stopPropagation();
      jumpToSegment();
    });
    time.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        event.stopPropagation();
        jumpToSegment();
      }
    });
  }
  return block;
}

function segmentMatchesSearch(seg, query) {
  if (!query) {
    return true;
  }
  const text = (seg.text || "").trim();
  return (
    text.toLowerCase().includes(query) ||
    String(seg.speaker || "").toLowerCase().includes(query)
  );
}

function renderSegments(job) {
  const container = document.getElementById("editor-segments");
  if (!container) {
    return;
  }
  const segments = job?.segments || [];
  const query = searchQuery.trim().toLowerCase();
  const jobId = job?.id ?? null;

  if (
    jobId === renderedSegmentJobId &&
    editorMode === "view" &&
    !query &&
    segments.length > renderedSegmentCount &&
    renderedSegmentCount > 0 &&
    container.querySelector(".editor-segment")
  ) {
    const speakers = collectSpeakers(segments);
    const youtube = isYoutubeJob(job);
    for (let index = renderedSegmentCount; index < segments.length; index += 1) {
      const seg = segments[index];
      if (!segmentMatchesSearch(seg, query)) {
        continue;
      }
      container.appendChild(createSegmentBlock(seg, index, job, speakers, youtube));
    }
    renderedSegmentCount = segments.length;
    const statusEl = container.querySelector(".editor-streaming-status");
    if (statusEl) {
      statusEl.textContent = streamingStatusText(job);
    }
    if (transcriptFollowTail) {
      const blocks = container.querySelectorAll(".editor-segment");
      blocks[blocks.length - 1]?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
    return;
  }

  container.replaceChildren();
  renderedSegmentJobId = jobId;
  renderedSegmentCount = segments.length;

  if (!segments.length) {
    const empty = document.createElement("p");
    empty.className = "hint editor-empty";
    if (job?.status === "completed") {
      empty.textContent = t("editor.k5875643");
    } else if (["running", "queued"].includes(job?.status || "")) {
      empty.textContent = streamingStatusText(job) || t("common.transcribingProgress");
    } else {
      empty.textContent = t("editor.k551014");
    }
    container.appendChild(empty);
    return;
  }

  const speakers = collectSpeakers(segments);
  const youtube = isYoutubeJob(job);

  segments.forEach((seg, index) => {
    if (!segmentMatchesSearch(seg, query)) {
      return;
    }
    container.appendChild(createSegmentBlock(seg, index, job, speakers, youtube));
  });

  if (shouldPollEditorJob(job)) {
    const status = document.createElement("p");
    status.className = "hint editor-streaming-status";
    status.textContent = streamingStatusText(job);
    container.appendChild(status);
  }
}

function streamingStatusText(job) {
  if (!job || job.status !== "running") {
    return "";
  }
  const n = (job.segments || []).length;
  if (isYoutubeJob(job) && n === 0) {
    return t("youtube.k4983190");
  }
  if (n > 0) {
    const pct = Math.round((Number(job.progress) || 0) * 100);
    return t("editor.transcribingSegments", { n, pct });
  }
  return t("common.transcribingProgress");
}

function batchJobStatusLabel(job, currentId) {
  if (job.id === currentId) {
    return t("editor.k996544");
  }
  if (job.status === "completed") {
    return t("common.done");
  }
  if (job.status === "running" || job.speakers_running) {
    return t("common.inProgress");
  }
  if (job.status === "queued") {
    return t("queue.inQueue");
  }
  return jobStatusLabel(job);
}

function renderBatchPanel(job) {
  const wrap = document.getElementById("editor-batch-in-source");
  const list = document.getElementById("editor-batch-list");
  const exportBtn = document.getElementById("btn-editor-batch-export");
  if (!wrap || !list) {
    return;
  }
  const batch = job?.batch_id != null ? batchById(job.batch_id) : null;
  if (!batch) {
    wrap.hidden = true;
    if (exportBtn) {
      exportBtn.hidden = true;
    }
    list.replaceChildren();
    return;
  }
  wrap.hidden = false;
  list.replaceChildren();
  for (const item of batch.jobs || []) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "editor-batch-item";
    if (item.id === job.id) {
      card.classList.add("is-current");
    }
    const name = document.createElement("span");
    name.className = "editor-batch-item-name";
    name.textContent = jobDisplayName(item);
    const status = document.createElement("span");
    status.className = "editor-batch-item-status";
    status.textContent = batchJobStatusLabel(item, job.id);
    const duration = document.createElement("span");
    duration.className = "hint editor-batch-item-duration";
    duration.textContent = item.duration_s != null ? formatDuration(item.duration_s) : t("common.dash");
    const meta = document.createElement("div");
    meta.className = "editor-batch-item-meta";
    meta.appendChild(duration);
    meta.appendChild(status);
    card.appendChild(name);
    card.appendChild(meta);
    card.addEventListener("click", () => navigate("editor", { jobId: item.id }));
    list.appendChild(card);
  }
  if (exportBtn) {
    exportBtn.hidden = !(batch.jobs || []).some((item) => item.status === "completed");
  }
}

function formatYoutubeDate(value) {
  const text = String(value || "").trim();
  if (!text) {
    return "";
  }
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!match) {
    return text;
  }
  const date = new Date(`${match[1]}-${match[2]}-${match[3]}T00:00:00`);
  if (Number.isNaN(date.getTime())) {
    return text;
  }
  return date.toLocaleDateString(localeDateTag(), {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function formatMsShort(ms) {
  const total = Math.max(0, Math.round(Number(ms) || 0) / 1000);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  if (hours) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function setMetaValue(element, value, { link = "", empty = t("common.dash") } = {}) {
  if (!element) {
    return;
  }
  element.replaceChildren();
  const text = String(value || "").trim();
  if (!text) {
    element.textContent = empty;
    return;
  }
  if (link) {
    const anchor = document.createElement("a");
    anchor.href = link;
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    anchor.textContent = text;
    element.appendChild(anchor);
    return;
  }
  element.textContent = text;
}

function syncYoutubeSource(job) {
  const wrap = document.getElementById("editor-youtube-source");
  const thumbLink = document.getElementById("editor-youtube-thumb-link");
  const thumb = document.getElementById("editor-youtube-thumb");
  const titleEl = document.getElementById("editor-youtube-title");
  const openLink = document.getElementById("editor-youtube-open");
  const channelEl = document.getElementById("editor-youtube-channel");
  const durationEl = document.getElementById("editor-youtube-duration");
  const uploadedEl = document.getElementById("editor-youtube-uploaded");
  const chaptersWrap = document.getElementById("editor-youtube-chapters");
  const chaptersList = document.getElementById("editor-youtube-chapters-list");
  const chaptersEmpty = document.getElementById("editor-youtube-chapters-empty");
  const waveform = document.getElementById("editor-waveform");
  const player = document.getElementById("player");
  const transport = document.querySelector(".editor-transport");
  const range = document.querySelector(".editor-range");
  const timeRow = document.querySelector(".editor-time-row");
  const youtube = isYoutubeJob(job);
  if (wrap) {
    wrap.hidden = !youtube;
  }
  if (waveform) {
    waveform.hidden = youtube;
  }
  if (player) {
    player.hidden = youtube;
  }
  if (transport) {
    transport.hidden = youtube;
  }
  if (range) {
    range.hidden = youtube;
  }
  if (timeRow) {
    timeRow.hidden = youtube;
  }
  if (!youtube) {
    return;
  }

  const video = job.youtube || {};
  const url = video.url || job.source_path || "#";
  const title = video.title || job.source_title || jobDisplayName(job);
  const channel = video.channel || "";
  const channelUrl = video.channel_url || "";
  const uploaded = formatYoutubeDate(video.upload_date);
  const durationValue =
    video.duration_s != null
      ? formatDuration(video.duration_s)
      : job.segments?.length
        ? formatDuration(
            Math.max(...job.segments.map((segment) => Number(segment.end_ms) || 0)) / 1000
          )
        : "";

  if (titleEl) {
    titleEl.textContent = title;
  }
  if (openLink) {
    openLink.href = url;
  }
  if (thumbLink && thumb) {
    const thumbnail = String(video.thumbnail_url || "").trim();
    if (thumbnail) {
      thumb.src = thumbnail;
      thumb.alt = title;
      thumbLink.href = url;
      thumbLink.hidden = false;
    } else {
      thumb.removeAttribute("src");
      thumbLink.hidden = true;
    }
  }

  setMetaValue(channelEl, channel, {
    link: channelUrl,
    empty: t("editor.k5211470"),
  });
  setMetaValue(durationEl, durationValue, { empty: t("editor.k5697974") });
  setMetaValue(uploadedEl, uploaded, { empty: t("editor.k5697974") });

  const chapters = Array.isArray(video.chapters) ? video.chapters : [];
  if (chaptersWrap && chaptersList) {
    chaptersList.replaceChildren();
    chaptersWrap.hidden = false;
    for (const chapter of chapters) {
      const titleText = String(chapter.title || "").trim();
      const startMs = Number(chapter.start_ms) || 0;
      if (!titleText) {
        continue;
      }
      const item = document.createElement("li");
      const link = document.createElement("button");
      link.type = "button";
      link.className = "editor-youtube-chapters-link";
      link.textContent = `${formatMsShort(startMs)} · ${titleText}`;
      link.addEventListener("click", () => {
        scrollToTranscriptMs(startMs, job);
      });
      item.appendChild(link);
      chaptersList.appendChild(item);
    }
    const hasChapters = chaptersList.children.length > 0;
    chaptersList.hidden = !hasChapters;
    if (chaptersEmpty) {
      chaptersEmpty.hidden = hasChapters;
    }
  }
}

function renderEditor(job) {
  if (!job) {
    return;
  }
  currentJob = job;
  currentJobId = job.id;

  const sourceName = document.getElementById("editor-source-name");
  if (sourceName) {
    sourceName.textContent = isYoutubeJob(job) ? jobSourceLabel(job) : jobDisplayName(job);
  }

  const titleEl = document.getElementById("topbar-title");
  if (titleEl && getRoute() === "editor") {
    titleEl.textContent = jobDisplayName(job);
  }

  syncYoutubeSource(job);

  if (editorMode === "view") {
    renderSegments(job);
  }
  renderBatchPanel(job);
  syncSpeakersPanel();
  drawWaveform(job);
  updateTransport(job);
  if (rangeFilledForJob !== job.id) {
    rangeFilledForJob = job.id;
    fillRangeInputs(job.range_start_ms, job.range_end_ms);
  }
  syncEditModeAvailability(job);
  if (shouldPollEditorJob(job)) {
    startEditorPoll();
  } else {
    stopEditorPoll();
  }
}

export function editorCurrentJobId() {
  return currentJobId;
}

export function markEditorDraftSaved() {
  editorDraftDirty = false;
  if (currentJobId != null && editorDrafts.has(currentJobId)) {
    const draft = editorDrafts.get(currentJobId);
    draft.dirty = false;
  }
}

if (typeof window !== "undefined") {
  window.__editorCurrentJobId = editorCurrentJobId;
  window.__editorMarkDraftSaved = markEditorDraftSaved;
}

function stashEditorDraft(jobId) {
  const textarea = document.getElementById("transcript-edit");
  if (jobId == null || !textarea || !editorDraftDirty) {
    return;
  }
  editorDrafts.set(jobId, {
    text: textarea.value,
    dirty: true,
    revision: Number(currentJob?.segments_revision) || 0,
  });
}

function restoreEditorDraft(job) {
  const draft = editorDrafts.get(job.id);
  const textarea = document.getElementById("transcript-edit");
  if (!draft?.dirty || !textarea) {
    return false;
  }
  textarea.value = draft.text;
  editorDraftDirty = true;
  return true;
}

export async function onEditorShow(jobId) {
  if (currentJobId !== jobId && currentJobId != null) {
    stashEditorDraft(currentJobId);
  }
  if (currentJobId !== jobId) {
    editorDraftDirty = false;
    editorPollFetchId += 1;
    rangeFilledForJob = null;
    renderedSegmentCount = 0;
    renderedSegmentJobId = null;
    transcriptFollowTail = true;
    stopEditorPoll();
  }
  currentJobId = jobId || null;
  applyEditorPanelWidths();
  applyDefaultPlayerCollapse();
  setEditorMode("view");
  if (!jobId) {
    renderSegments(null);
    return;
  }
  try {
    await refreshLibrary();
    const job = await selectJob(jobId);
    if (restoreEditorDraft(job)) {
      setEditorMode("edit");
    } else {
      setEditorMode("view");
    }
    renderEditor(job);
  } catch (err) {
    reportError(t("topbar.editor"), err);
    const container = document.getElementById("editor-segments");
    if (container) {
      container.replaceChildren();
      const error = document.createElement("p");
      error.className = "hint";
      error.textContent = err.message || String(err);
      container.appendChild(error);
    }
  }
}

function setRangeFromPlayer(which) {
  const player = document.getElementById("player");
  const startEl = document.getElementById("editor-range-start");
  const endEl = document.getElementById("editor-range-end");
  if (!player) {
    return;
  }
  const stamp = formatMsClock((Number(player.currentTime) || 0) * 1000);
  if (which === "start" && startEl) {
    startEl.value = stamp;
  }
  if (which === "end" && endEl) {
    endEl.value = stamp;
  }
  drawWaveform(currentJob);
}

function bindRangeControls() {
  const fromCursor = document.getElementById("editor-range-from-cursor");
  const toCursor = document.getElementById("editor-range-to-cursor");
  if (fromCursor && !fromCursor.dataset.bound) {
    fromCursor.dataset.bound = "1";
    fromCursor.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      setRangeFromPlayer("start");
    });
  }
  if (toCursor && !toCursor.dataset.bound) {
    toCursor.dataset.bound = "1";
    toCursor.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      setRangeFromPlayer("end");
    });
  }
  document.getElementById("editor-range-start")?.addEventListener("input", () => {
    drawWaveform(currentJob);
  });
  document.getElementById("editor-range-end")?.addEventListener("input", () => {
    drawWaveform(currentJob);
  });
}

function bindWaveform() {
  const canvas = document.getElementById("editor-waveform");
  const player = document.getElementById("player");
  if (!canvas || !player || canvas.dataset.bound) {
    return;
  }
  canvas.dataset.bound = "1";
  let drag = null;

  const finishDrag = (event) => {
    if (!drag) {
      return;
    }
    const t = timeAtWaveformX(event.clientX);
    const a = Math.min(drag.origin, t);
    const b = Math.max(drag.origin, t);
    if (Math.abs(b - a) < 0.4) {
      player.currentTime = t;
    } else {
      fillRangeInputs(a * 1000, b * 1000);
    }
    drag = null;
    drawWaveform(currentJob);
  };

  canvas.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) {
      return;
    }
    event.preventDefault();
    canvas.setPointerCapture?.(event.pointerId);
    const t = timeAtWaveformX(event.clientX);
    drag = { origin: t };
    player.currentTime = t;
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!drag) {
      return;
    }
    const t = timeAtWaveformX(event.clientX);
    fillRangeInputs(Math.min(drag.origin, t) * 1000, Math.max(drag.origin, t) * 1000);
    drawWaveform(currentJob);
  });
  canvas.addEventListener("pointerup", finishDrag);
  canvas.addEventListener("pointercancel", () => {
    drag = null;
  });
}

function bindPlayerControls() {
  const player = document.getElementById("player");
  if (!player || player.dataset.editorBound) {
    bindRangeControls();
    bindWaveform();
    return;
  }
  player.dataset.editorBound = "1";

  player.addEventListener("timeupdate", () => updateTransport(currentJob));
  player.addEventListener("loadedmetadata", () => updateTransport(currentJob));
  player.addEventListener("play", () => updateTransport(currentJob));
  player.addEventListener("pause", () => updateTransport(currentJob));

  document.getElementById("editor-play-toggle")?.addEventListener("click", () => {
    if (player.paused) {
      player.play().catch(() => {});
    } else {
      player.pause();
    }
  });
  document.getElementById("editor-skip-back")?.addEventListener("click", () => {
    player.currentTime = Math.max(0, player.currentTime - 10);
  });
  document.getElementById("editor-skip-forward")?.addEventListener("click", () => {
    player.currentTime = Math.min(player.duration || Infinity, player.currentTime + 10);
  });
  bindRangeControls();
  bindWaveform();
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function applyEditorPanelWidths() {
  const layout = document.getElementById("editor-layout");
  if (!layout) {
    return;
  }
  const stored = localStorage.getItem(PLAYER_WIDTH_KEY);
  let width = PLAYER_WIDTH_DEFAULT;
  if (stored != null) {
    const parsed = Number(stored);
    if (Number.isFinite(parsed)) {
      width = clamp(parsed, PLAYER_WIDTH_MIN, PLAYER_WIDTH_MAX);
    }
  }
  layout.style.setProperty("--editor-player-width", `${width}px`);
}

function bindPanelResizer(handle, onDrag) {
  if (!handle || handle.dataset.bound) {
    return;
  }
  handle.dataset.bound = "1";

  const startDrag = (clientX) => {
    let lastX = clientX;
    handle.classList.add("is-active");
    document.body.classList.add("is-resizing");

    const onMove = (event) => {
      const x = event.clientX ?? lastX;
      const delta = x - lastX;
      lastX = x;
      onDrag(delta);
    };

    const onUp = () => {
      handle.classList.remove("is-active");
      document.body.classList.remove("is-resizing");
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  handle.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) {
      return;
    }
    event.preventDefault();
    handle.setPointerCapture?.(event.pointerId);
    startDrag(event.clientX);
  });

  handle.addEventListener("keydown", (event) => {
    const step = event.shiftKey ? 24 : 8;
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      const delta = event.key === "ArrowRight" ? step : -step;
      onDrag(delta);
    }
  });
}

function initEditorResizers() {
  const layout = document.getElementById("editor-layout");
  const playerPanel = document.getElementById("editor-player-panel");
  const playerResizer = document.getElementById("editor-resizer-player");
  if (!layout || !playerPanel || !playerResizer) {
    return;
  }

  applyEditorPanelWidths();

  bindPanelResizer(playerResizer, (delta) => {
    const next = clamp(playerPanel.offsetWidth + delta, PLAYER_WIDTH_MIN, PLAYER_WIDTH_MAX);
    layout.style.setProperty("--editor-player-width", `${next}px`);
    localStorage.setItem(PLAYER_WIDTH_KEY, String(next));
  });
}

export function initEditor() {
  if (editorBound) {
    return;
  }
  editorBound = true;

  setEditorRefreshHook((job) => {
    if (getRoute() !== "editor" || job.id !== currentJobId) {
      return;
    }
    currentJob = job;
    if (editorMode === "view" && !editorDraftDirty) {
      renderSegments(job);
    }
    renderBatchPanel(job);
    syncSpeakersPanel();
    drawWaveform(job);
    updateTransport(job);
  });

  bindPlayerControls();
  initEditorResizers();
  applyDefaultPlayerCollapse();
  applyDefaultTranscriptCollapse();
  setEditorMode("view");

  document.getElementById("editor-toggle-player")?.addEventListener("click", () => {
    setPlayerCollapsed(!document.getElementById("editor-player-panel")?.classList.contains("is-collapsed"));
  });
  document.getElementById("editor-toggle-transcript")?.addEventListener("click", () => {
    setTranscriptCollapsed(!document.getElementById("editor-transcript-panel")?.classList.contains("is-collapsed"));
  });
  document.getElementById("editor-transcript-expand")?.addEventListener("click", () => {
    setTranscriptCollapsed(false);
  });
  document.getElementById("editor-play-compact")?.addEventListener("click", () => {
    document.getElementById("editor-play-toggle")?.click();
  });

  document.getElementById("editor-mode-view")?.addEventListener("click", () => {
    setEditorMode("view");
    if (currentJob) {
      renderSegments(currentJob);
    }
  });
  document.getElementById("editor-mode-edit")?.addEventListener("click", () => {
    if (currentJob && shouldPollEditorJob(currentJob)) {
      showToast("editor.k8301628");
      return;
    }
    setEditorMode("edit");
  });
  const segmentsContainer = document.getElementById("editor-segments");
  segmentsContainer?.addEventListener("scroll", () => {
    if (!segmentsContainer) {
      return;
    }
    const nearBottom =
      segmentsContainer.scrollHeight - segmentsContainer.scrollTop - segmentsContainer.clientHeight <
      80;
    transcriptFollowTail = nearBottom;
  });
  document.getElementById("editor-search")?.addEventListener("input", (event) => {
    searchQuery = event.target.value || "";
    if (currentJob) {
      renderSegments(currentJob);
    }
  });

  document.getElementById("btn-topbar-export")?.addEventListener("click", () => {
    document.getElementById("btn-export")?.click();
  });
  window.addEventListener("gigaam:job-exported", (event) => {
    const { jobId, path, paths } = event.detail || {};
    if (jobId == null || jobId !== currentJobId) {
      return;
    }
    const exportPaths = Array.isArray(paths) && paths.length ? paths : path ? [path] : null;
    syncExportActions(
      {
        ...(currentJob || {}),
        id: jobId,
        last_export_path: path || currentJob?.last_export_path,
        last_export_paths: exportPaths || currentJob?.last_export_paths,
      },
      exportPaths,
    );
  });
  document.getElementById("btn-editor-batch-export")?.addEventListener("click", () => {
    const batch = currentJob?.batch_id != null ? batchById(currentJob.batch_id) : null;
    openBatchExportModal(batch?.jobs || []);
  });

  const textarea = document.getElementById("transcript-edit");
  textarea?.addEventListener("input", () => {
    editorDraftDirty = true;
  });
  textarea?.addEventListener("click", () => {
    const pos = textarea.selectionStart;
    const before = textarea.value.slice(0, pos);
    const lineStart = before.lastIndexOf("\n") + 1;
    const line = textarea.value.slice(lineStart).split("\n", 1)[0] || "";
    const match = line.match(/^\[(\d{2}):(\d{2}):(\d{2})\]/);
    if (!match) {
      return;
    }
    const player = document.getElementById("player");
    if (!player) {
      return;
    }
    const ms = ((Number(match[1]) * 3600) + Number(match[2]) * 60 + Number(match[3])) * 1000;
    player.currentTime = ms / 1000;
    player.play().catch(() => {});
  });
}
