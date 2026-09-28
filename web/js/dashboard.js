import { msIcon } from "./icons.js";
import { api, showToast, formatDuration, pathsFromDrop, jobDisplayName } from "./api.js";
import { reportError } from "./errors.js";
import { getLibrarySnapshot, jobStatusLabel, jobStatusTone } from "./library-store.js";
import {
  refreshLibrary,
  resolveUploadTarget,
  addFolder,
  openNewBatchModal,
  addPathsForDashboard,
} from "./legacy.js";
import { navigate } from "./router.js";
import { formatBatchCountsSummary, isLibraryOrphan, isArchiveBatch } from "./library-utils.js";
import { localeDateTag, t } from "./i18n.js";

let dashboardBound = false;

function formatRelativeTime(iso) {
  if (!iso) {
    return "";
  }
  const date = new Date(iso);
  const now = new Date();
  const diffMs = now - date;
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) {
    return t("common.justNow");
  }
  if (mins < 60) {
    return t("common.minutesAgo", { mins });
  }
  const hours = Math.floor(mins / 60);
  if (hours < 24) {
    return t("common.hoursAgo", { hours });
  }
  return date.toLocaleDateString(localeDateTag(), { day: "numeric", month: "short" });
}

function statusPillClass(job) {
  const tone = jobStatusTone(job);
  if (tone === "done") {
    return "status-pill status-pill--done";
  }
  if (tone === "run" || tone === "queue") {
    return "status-pill status-pill--run";
  }
  return "status-pill";
}

function statusPillText(job) {
  if (job.status === "running" || job.speakers_running) {
    return t("common.inProgress");
  }
  if (job.status === "completed") {
    return t("common.done");
  }
  if (job.status === "queued") {
    return t("queue.inQueue");
  }
  if (job.status === "failed") {
    return t("common.error");
  }
  if (job.status === "idle") {
    return t("common.notTranscribed");
  }
  if (job.status === "cancelled") {
    return t("intake.cancelled");
  }
  return jobStatusLabel(job);
}

function renderRecentCardFixed(item) {
  const card = document.createElement("article");
  card.className = "recent-card";
  const isBatch = item.kind === "batch";
  const name = isBatch ? item.name : jobDisplayName(item);
  const created = item.created_at;

  const header = document.createElement("div");
  header.className = "recent-card-head";

  const leading = document.createElement("div");
  leading.className = "recent-card-leading";

  const iconWrap = document.createElement("div");
  iconWrap.className = "recent-card-icon";
  iconWrap.appendChild(msIcon(isBatch ? "folder_zip" : "audio_file", { size: "md" }));

  const meta = document.createElement("div");
  meta.className = "recent-card-meta";
  const title = document.createElement("div");
  title.className = "recent-card-title";
  title.title = name;
  title.textContent = name;
  const time = document.createElement("div");
  time.className = "hint recent-card-time";
  time.textContent = formatRelativeTime(created);
  meta.appendChild(title);
  meta.appendChild(time);

  leading.appendChild(iconWrap);
  leading.appendChild(meta);
  header.appendChild(leading);

  const pill = document.createElement("span");
  pill.className = isBatch
    ? statusPillClass({ status: item.running ? "running" : item.status })
    : statusPillClass(item);
  pill.textContent = isBatch
    ? item.running
      ? t("common.inProgress")
      : item.status === "completed"
        ? t("common.done")
        : t("queue.batchLabel")
    : statusPillText(item);
  header.appendChild(pill);
  card.appendChild(header);

  const footer = document.createElement("div");
  footer.className = "recent-card-foot";
  if (!isBatch && (item.status === "running" || item.speakers_running)) {
    const pct = Math.round(Number(item.progress || 0) * 100);
    footer.innerHTML = `
      <div class="progress-track"><div class="progress-fill is-animated" style="width:${pct}%"></div></div>
      <div class="progress-meta">
        <span class="hint">${t("common.transcribing")}</span>
        <span class="hint">${pct}%</span>
      </div>`;
  } else if (isBatch) {
    footer.className = "recent-card-foot recent-card-foot--border hint";
    footer.textContent = formatBatchCountsSummary(item);
  } else if (item.status === "completed" && item.duration_s != null) {
    footer.className = "recent-card-foot recent-card-foot--border hint";
    footer.textContent = formatDuration(item.duration_s);
  } else {
    footer.className = "recent-card-foot hint";
    footer.style.fontSize = "12px";
    footer.textContent = jobStatusLabel(item);
  }
  card.appendChild(footer);

  card.addEventListener("click", () => {
    if (isBatch) {
      navigate("legacy", { batchId: item.id, tab: "batches" });
      return;
    }
    navigate("editor", { jobId: item.id });
  });
  return card;
}

export function paintRecent() {
  const grid = document.getElementById("recent-grid");
  if (!grid) {
    return;
  }
  const { jobs, batches } = getLibrarySnapshot();
  const items = [];
  for (const job of jobs) {
    if (!isLibraryOrphan(job)) {
      continue;
    }
    items.push({ ...job, kind: "job", sortKey: job.created_at });
  }
  for (const batch of batches) {
    if (isArchiveBatch(batch)) {
      continue;
    }
    items.push({ ...batch, kind: "batch", sortKey: batch.created_at });
  }
  items.sort((a, b) => String(b.sortKey).localeCompare(String(a.sortKey)));
  grid.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "hint";
    empty.textContent = t("dashboard.emptyRecent");
    grid.appendChild(empty);
    return;
  }
  for (const item of items.slice(0, 6)) {
    grid.appendChild(renderRecentCardFixed(item));
  }
}

export async function renderRecent() {
  await refreshLibrary();
  paintRecent();
}

async function pickFilePaths() {
  if (window.pywebview && window.pywebview.api && window.pywebview.api.open_files) {
    return window.pywebview.api.open_files() || [];
  }
  const input = document.createElement("input");
  input.type = "file";
  input.multiple = true;
  input.accept = "audio/*,video/*";
  await new Promise((resolve) => {
    input.addEventListener("change", () => resolve());
    input.click();
  });
  return Array.from(input.files || [])
    .map((f) => f.pywebviewFullPath || f.path)
    .filter(Boolean);
}

export function initDashboard() {
  if (dashboardBound) {
    return;
  }
  dashboardBound = true;

  const dropZone = document.getElementById("dashboard-drop-zone");
  const pickBtn = document.getElementById("btn-dashboard-pick-files");
  const batchFolderBtn = document.getElementById("btn-dashboard-batch-folder");
  const batchFilesBtn = document.getElementById("btn-dashboard-batch-files");
  const newBatchBtn = document.getElementById("btn-dashboard-new-batch");

  pickBtn?.addEventListener("click", async () => {
    const paths = await pickFilePaths();
    if (paths.length) {
      await resolveUploadTarget(paths);
      await renderRecent();
    }
  });

  batchFolderBtn?.addEventListener("click", () =>
    addFolder().catch((err) => showToast(err.message || String(err)))
  );
  batchFilesBtn?.addEventListener("click", async () => {
    const paths = await pickFilePaths();
    if (paths.length) {
      await addPathsForDashboard("batch", paths);
      await renderRecent();
    }
  });
  newBatchBtn?.addEventListener("click", () =>
    openNewBatchModal((batch) => {
      if (batch?.id != null) {
        navigate("legacy", { batchId: batch.id, tab: "batches" });
      }
    }).catch((err) => showToast(err.message || String(err)))
  );

  const handleDrop = async (event) => {
    event.preventDefault();
    document.body.classList.remove("is-drop");
    const paths = pathsFromDrop(event);
    if (!paths.length) {
      if (window.pywebview) {
        return;
      }
      showToast("dashboard.dropNoPath");
      return;
    }
    const target = event.currentTarget?.dataset?.dropTarget || "single";
    if (target === "batch") {
      await addPathsForDashboard("batch", paths);
    } else {
      await resolveUploadTarget(paths);
    }
    await renderRecent();
  };

  dropZone?.addEventListener("dragover", (e) => {
    e.preventDefault();
    document.body.classList.add("is-drop");
  });
  dropZone?.addEventListener("dragleave", () => document.body.classList.remove("is-drop"));
  dropZone?.addEventListener("drop", handleDrop);

  document.getElementById("dashboard-batch-drop")?.addEventListener("dragover", (e) => {
    e.preventDefault();
    document.body.classList.add("is-drop");
  });
  document.getElementById("dashboard-batch-drop")?.addEventListener("drop", async (e) => {
    e.preventDefault();
    document.body.classList.remove("is-drop");
    const paths = pathsFromDrop(e);
    if (paths.length) {
      await addPathsForDashboard("batch", paths);
      await renderRecent();
    }
  });

  renderRecent().catch((err) => reportError(t("topbar.dashboard"), err));
}

export function onDashboardShow() {
  renderRecent().catch((err) => reportError(t("topbar.dashboard"), err));
}
