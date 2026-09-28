import { api, showToast, formatDuration, jobDisplayName, isYoutubeJob } from "./api.js";
import { reportError } from "./errors.js";
import { getLibrarySnapshot, jobStatusLabel, patchBatchName } from "./library-store.js";
import { refreshLibrary } from "./legacy.js";
import { getRoute, navigate } from "./router.js";
import { msIcon } from "./icons.js";
import { batchProgressItemLabel } from "./batch-kind.js";
import { t } from "./i18n.js";
import {
  isJobActive,
  isJobWaiting,
  isBatchActive,
  batchFileCount,
  batchDoneCount,
  formatBatchCountsSummary,
  jobProgressPct,
  jobProgressPctLabel,
  batchProgressPct,
  createProgressBar,
  updateProgressBarFill,
  isProgressIndeterminate,
} from "./library-utils.js";

let queueBound = false;
let queuePollTimer = null;
const expandedBatches = new Set();

function mediaIconName(job) {
  if (isYoutubeJob(job)) {
    return "video_library";
  }
  return /\.(mp4|mov|mkv|avi|webm)$/i.test(String(job?.source_path || "")) ? "video_file" : "audio_file";
}

function computeMetrics(jobs, batches) {
  const batchMap = new Map(batches.map((b) => [b.id, b]));
  const active = jobs.filter(isJobActive).length;
  const queued = jobs.filter((j) => isJobWaiting(j, batchMap)).length;
  const today = new Date().toDateString();
  const completedToday = jobs.filter(
    (j) => j.status === "completed" && new Date(j.created_at).toDateString() === today
  ).length;
  const completed = jobs.filter((j) => j.status === "completed" && j.duration_s != null);
  const avgDuration =
    completed.length > 0
      ? formatDuration(
          completed.reduce((sum, j) => sum + Number(j.duration_s || 0), 0) / completed.length
        )
      : t("common.dash");
  return { active, queued, completedToday, avgDuration };
}

function iconButton(icon, title, className = "") {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = `icon-btn ${className}`.trim();
  btn.title = title;
  btn.appendChild(msIcon(icon));
  return btn;
}

function renderMetricCard(label, value, iconName, iconClass = "") {
  const card = document.createElement("article");
  card.className = "queue-metric-card";
  card.innerHTML = `
    <span class="material-symbols-outlined queue-metric-icon ${iconClass}" aria-hidden="true">${iconName}</span>
    <div class="queue-metric-body">
      <span class="queue-metric-label">${label}</span>
      <span class="queue-metric-value">${value}</span>
    </div>`;
  return card;
}

function renderProgressBar(pct, tone = "primary", indeterminate = false) {
  return createProgressBar(pct, tone, "", indeterminate);
}

async function promptRenameBatch(batch) {
  const current = batch.name || t("legacy.batchNumber", { id: batch.id });
  const next = window.prompt(t("queue.batchNamePrompt"), current);
  if (next == null) {
    return;
  }
  const trimmed = next.trim();
  if (!trimmed || trimmed === current) {
    return;
  }
  try {
    await patchBatchName(batch.id, trimmed);
    showToast("queue.batchNameSaved");
    renderQueue();
  } catch (err) {
    showToast(err.message || String(err));
  }
}

function renderActiveJobCard(job) {
  const card = document.createElement("article");
  card.className = "queue-active-card";
  card.dataset.queueActiveJob = String(job.id);
  const pct = jobProgressPct(job);
  const topBar = document.createElement("div");
  topBar.className = "queue-active-card-bar";
  topBar.appendChild(renderProgressBar(pct, "primary", isProgressIndeterminate(job)));

  const body = document.createElement("div");
  body.className = "queue-active-card-body";
  const leading = document.createElement("div");
  leading.className = "queue-active-leading";
  const iconWrap = document.createElement("div");
  iconWrap.className = "queue-active-icon";
  iconWrap.appendChild(msIcon(mediaIconName(job), { size: "md" }));
  const meta = document.createElement("div");
  meta.className = "queue-active-meta";
  const title = document.createElement("h4");
  title.className = "queue-active-title";
  title.textContent = jobDisplayName(job);
  const sub = document.createElement("div");
  sub.className = "hint queue-active-sub";
  const parts = [];
  if (job.duration_s != null) {
    parts.push(formatDuration(job.duration_s));
  }
  if (job.speakers_running) {
    parts.push(t("common.diarization"));
  } else if (job.engine_starting) {
    parts.push(t("common.modelLoading"));
  }
  sub.textContent = parts.join(" · ") || jobStatusLabel(job);
  meta.appendChild(title);
  meta.appendChild(sub);
  leading.appendChild(iconWrap);
  leading.appendChild(meta);

  const trailing = document.createElement("div");
  trailing.className = "queue-active-trailing";
  const stats = document.createElement("div");
  stats.className = "queue-active-stats";
  stats.innerHTML = `<div class="queue-active-pct">${jobProgressPctLabel(job)}</div><div class="hint">${jobStatusLabel(job)}</div>`;
  const actions = document.createElement("div");
  actions.className = "queue-active-actions";
  const cancelBtn = iconButton("stop_circle", t("queue.abortTranscription"), "icon-btn--danger");
  cancelBtn.title = t("common.stop");
  cancelBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    cancelJob(job.id).catch((err) => showToast(err.message || String(err)));
  });
  actions.appendChild(cancelBtn);
  trailing.appendChild(stats);
  trailing.appendChild(actions);
  body.appendChild(leading);
  body.appendChild(trailing);
  card.appendChild(topBar);
  card.appendChild(body);
  card.addEventListener("click", () => navigate("editor", { jobId: job.id }));
  return card;
}

function updateActiveJobCardProgress(card, job) {
  const pct = jobProgressPct(job);
  const indeterminate = isProgressIndeterminate(job);
  const track = card.querySelector(".queue-active-card-bar .queue-progress-track");
  const fill = track?.querySelector(".queue-progress-fill");
  updateProgressBarFill(fill, pct, indeterminate, "primary", track);
  const pctEl = card.querySelector(".queue-active-pct");
  if (pctEl) {
    pctEl.textContent = jobProgressPctLabel(job);
  }
  const statHint = card.querySelector(".queue-active-stats .hint");
  if (statHint) {
    statHint.textContent = jobStatusLabel(job);
  }
}

function renderBatchSubItem(job) {
  const row = document.createElement("div");
  row.className = "queue-batch-item";
  const leading = document.createElement("div");
  leading.className = "queue-batch-item-leading";
  let icon = "schedule";
  let tone = "muted";
  if (job.status === "completed") {
    icon = "check_circle";
    tone = "done";
    row.classList.add("is-done");
  } else if (isJobActive(job)) {
    icon = "progress_activity";
    tone = "active";
    row.classList.add("is-active");
  }
  const iconEl = msIcon(icon, { size: "md" });
  iconEl.classList.add(`queue-batch-item-icon--${tone}`);
  if (isJobActive(job)) {
    iconEl.classList.add("queue-batch-item-icon--spin");
  }
  leading.appendChild(iconEl);
  const name = document.createElement("span");
  name.className = "queue-batch-item-name";
  name.textContent = jobDisplayName(job);
  leading.appendChild(name);

  const trailing = document.createElement("div");
  trailing.className = "queue-batch-item-trailing";
  if (isJobActive(job)) {
    const pct = jobProgressPct(job);
    trailing.appendChild(renderProgressBar(pct, "primary", isProgressIndeterminate(job)));
    const pctLabel = document.createElement("span");
    pctLabel.className = "hint queue-batch-item-pct";
    pctLabel.textContent = job.speakers_running
      ? jobProgressPctLabel(job)
      : isProgressIndeterminate(job)
        ? jobStatusLabel(job)
        : `${pct}%`;
    trailing.appendChild(pctLabel);
  } else if (job.status === "completed") {
    trailing.textContent = t("common.done");
    trailing.className = "hint queue-batch-item-trailing queue-batch-item-trailing--done";
  } else {
    trailing.textContent = job.status === "failed" ? t("common.error") : t("common.waiting");
    trailing.className = "hint queue-batch-item-trailing";
  }

  row.appendChild(leading);
  row.appendChild(trailing);
  row.addEventListener("click", (event) => {
    event.stopPropagation();
    navigate("editor", { jobId: job.id });
  });
  return row;
}

function renderActiveBatchCard(batch) {
  const card = document.createElement("article");
  card.className = "queue-active-card queue-active-card--batch";
  const pct = batchProgressPct(batch);
  const topBar = document.createElement("div");
  topBar.className = "queue-active-card-bar";
  topBar.appendChild(renderProgressBar(pct, "secondary"));

  const header = document.createElement("button");
  header.type = "button";
  header.className = "queue-batch-header";
  const leading = document.createElement("div");
  leading.className = "queue-active-leading";
  const iconWrap = document.createElement("div");
  iconWrap.className = "queue-active-icon queue-active-icon--batch";
  iconWrap.appendChild(msIcon("folder_zip", { size: "md" }));
  const meta = document.createElement("div");
  meta.className = "queue-active-meta";
  const titleRow = document.createElement("div");
  titleRow.className = "queue-batch-title-row";
  const title = document.createElement("h4");
  title.className = "queue-active-title";
  title.textContent = batch.name;
  const renameBtn = iconButton("edit", t("queue.renameBatch"));
  renameBtn.classList.add("queue-batch-rename-btn");
  renameBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    promptRenameBatch(batch).catch((err) => showToast(err.message || String(err)));
  });
  const badge = document.createElement("span");
  badge.className = "badge badge-secondary";
  badge.textContent = t("queue.batchLabel");
  titleRow.appendChild(title);
  titleRow.appendChild(renameBtn);
  titleRow.appendChild(badge);
  const sub = document.createElement("div");
  sub.className = "hint queue-active-sub";
  const current = (batch.jobs || []).find((j) => isJobActive(j));
  const total = batchFileCount(batch);
  const done = batchDoneCount(batch);
  sub.textContent = current
    ? t("queue.batchProgress", {
        item: batchProgressItemLabel(batch),
        current: done + 1,
        total,
        name: jobDisplayName(current),
        summary: formatBatchCountsSummary(batch, ", "),
      })
    : formatBatchCountsSummary(batch);
  meta.appendChild(titleRow);
  meta.appendChild(sub);
  leading.appendChild(iconWrap);
  leading.appendChild(meta);

  const trailing = document.createElement("div");
  trailing.className = "queue-active-trailing";
  const stats = document.createElement("div");
  stats.className = "queue-active-stats";
  stats.innerHTML = `<div class="queue-active-pct queue-active-pct--secondary">${pct}%</div><div class="hint">${t("common.overallProgress")}</div>`;
  const expandIcon = msIcon("expand_more");
  expandIcon.id = `queue-batch-icon-${batch.id}`;
  expandIcon.classList.add("queue-batch-expand-icon");
  if (expandedBatches.has(batch.id)) {
    expandIcon.classList.add("is-open");
  }
  trailing.appendChild(stats);
  trailing.appendChild(expandIcon);

  header.appendChild(leading);
  header.appendChild(trailing);

  const expanded = document.createElement("div");
  expanded.className = "queue-batch-expand";
  expanded.id = `queue-batch-body-${batch.id}`;
  if (expandedBatches.has(batch.id)) {
    expanded.classList.add("is-open");
  }
  const inner = document.createElement("div");
  inner.className = "queue-batch-expand-inner";
  for (const job of batch.jobs || []) {
    inner.appendChild(renderBatchSubItem(job));
  }
  expanded.appendChild(inner);

  header.addEventListener("click", () => {
    if (expandedBatches.has(batch.id)) {
      expandedBatches.delete(batch.id);
    } else {
      expandedBatches.add(batch.id);
    }
    renderQueue();
  });

  const actions = document.createElement("div");
  actions.className = "queue-batch-actions";
  if (batch.running) {
    const pauseBtn = iconButton("pause", t("queue.pauseAfterCurrent"));
    pauseBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      pauseBatch(batch.id).catch((err) => showToast(err.message || String(err)));
    });
    const cancelBtn = iconButton("close", t("queue.stopBatch"), "icon-btn--danger");
    cancelBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      cancelBatch(batch.id).catch((err) => showToast(err.message || String(err)));
    });
    actions.appendChild(pauseBtn);
    actions.appendChild(cancelBtn);
  } else {
    const startBtn = iconButton("play_arrow", t("queue.startBatch"));
    startBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      startBatch(batch.id).catch((err) => showToast(err.message || String(err)));
    });
    actions.appendChild(startBtn);
  }

  card.appendChild(topBar);
  card.appendChild(header);
  card.appendChild(expanded);
  card.appendChild(actions);
  return card;
}

export function renderQueue() {
  const metricsEl = document.getElementById("queue-metrics");
  const activeEl = document.getElementById("queue-active-list");
  if (!metricsEl || !activeEl) {
    return;
  }

  const { jobs, batches, orphans } = getLibrarySnapshot();
  const batchMap = new Map(batches.map((b) => [b.id, b]));
  const metrics = computeMetrics(jobs, batches);

  metricsEl.replaceChildren(
    renderMetricCard(t("queue.active"), metrics.active, "sync", "queue-metric-icon--primary"),
    renderMetricCard(t("queue.inQueue"), metrics.queued, "hourglass_empty"),
    renderMetricCard(t("queue.today"), metrics.completedToday, "check_circle", "queue-metric-icon--secondary"),
    renderMetricCard(t("queue.avgTime"), metrics.avgDuration, "timer")
  );

  const activeOrphans = orphans.filter(isJobActive);
  const activeBatches = batches.filter(isBatchActive);
  const orphanIds = new Set(activeOrphans.map((j) => j.id));
  const batchIds = new Set(activeBatches.map((b) => b.id));

  for (const el of [...activeEl.querySelectorAll("[data-queue-active-job]")]) {
    const id = Number(el.dataset.queueActiveJob);
    if (!orphanIds.has(id)) {
      el.remove();
    }
  }
  for (const el of [...activeEl.querySelectorAll("[data-queue-active-batch]")]) {
    const id = Number(el.dataset.queueActiveBatch);
    if (!batchIds.has(id)) {
      el.remove();
    }
  }
  activeEl.querySelector(".queue-active-empty")?.remove();

  if (!activeOrphans.length && !activeBatches.length) {
    const empty = document.createElement("p");
    empty.className = "hint queue-active-empty";
    empty.textContent = t("queue.empty");
    activeEl.appendChild(empty);
  } else {
    for (const job of activeOrphans) {
      let card = activeEl.querySelector(`[data-queue-active-job="${job.id}"]`);
      if (card) {
        updateActiveJobCardProgress(card, job);
      } else {
        card = renderActiveJobCard(job);
        activeEl.appendChild(card);
      }
    }
    for (const batch of activeBatches) {
      activeEl.querySelector(`[data-queue-active-batch="${batch.id}"]`)?.remove();
      const card = renderActiveBatchCard(batch);
      card.dataset.queueActiveBatch = String(batch.id);
      activeEl.appendChild(card);
    }
  }

  syncQueuePoll(jobs, batches);
}

async function refreshQueue() {
  await refreshLibrary();
  if (getRoute() === "queue") {
    renderQueue();
  }
}

function syncQueuePoll(jobs, batches) {
  const active =
    jobs.some(isJobActive) ||
    jobs.some((j) => j.status === "queued") ||
    batches.some(isBatchActive);
  if (getRoute() !== "queue") {
    return;
  }
  if (active && !queuePollTimer) {
    queuePollTimer = setInterval(() => {
      refreshQueue().catch((err) => reportError(t("queue.title"), err));
    }, 500);
  } else if (!active && queuePollTimer) {
    clearInterval(queuePollTimer);
    queuePollTimer = null;
  }
}

async function cancelJob(jobId) {
  await api(`/api/jobs/${jobId}/cancel`, { method: "POST" });
  await refreshQueue();
}

async function startBatch(batchId) {
  await api(`/api/batches/${batchId}/start`, { method: "POST" });
  await refreshQueue();
}

async function pauseBatch(batchId) {
  await api(`/api/batches/${batchId}/pause`, { method: "POST" });
  await refreshQueue();
}

async function cancelBatch(batchId) {
  await api(`/api/batches/${batchId}/cancel`, { method: "POST" });
  await refreshQueue();
}

async function pauseAllBatches() {
  const { batches } = getLibrarySnapshot();
  const running = batches.filter((b) => b.running);
  if (!running.length) {
    showToast("queue.noActiveBatches");
    return;
  }
  for (const batch of running) {
    await api(`/api/batches/${batch.id}/pause`, { method: "POST" });
  }
  await refreshQueue();
  showToast("queue.pauseAll");
}

export function initQueue() {
  if (queueBound) {
    return;
  }
  queueBound = true;
  document.getElementById("btn-queue-pause-all")?.addEventListener("click", () => {
    pauseAllBatches().catch((err) => showToast(err.message || String(err)));
  });
}

export function onQueueShow() {
  refreshQueue().catch((err) => reportError(t("queue.title"), err));
}

export function onQueueHide() {
  if (queuePollTimer) {
    clearInterval(queuePollTimer);
    queuePollTimer = null;
  }
}
