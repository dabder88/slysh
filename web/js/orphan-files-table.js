import { jobDisplayName, formatDuration } from "./api.js";
import { msIcon } from "./icons.js";
import {
  isJobTranscribing,
  jobProgressPct,
  jobProgressPctLabel,
  createProgressBar,
  isProgressIndeterminate,
  speakersBadgeClass,
  speakersStatusLabel,
} from "./library-utils.js";
import { localeDateTag, t } from "./i18n.js";

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

function mediaIconName(path) {
  return /\.(mp4|mov|mkv|avi|webm)$/i.test(String(path || "")) ? "video_file" : "audio_file";
}

function iconButton(icon, title, className = "") {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = `icon-btn ${className}`.trim();
  btn.title = title;
  btn.appendChild(msIcon(icon));
  return btn;
}

function statusLabel(job, statusLabelFn) {
  if (job.status === "queued") {
    return t("queue.inQueue");
  }
  if (job.status === "running" || job.speakers_running) {
    return t("common.inProgress");
  }
  return statusLabelFn(job);
}

function renderStatusCell(job, statusLabelFn) {
  const statusCell = document.createElement("td");
  const wrap = document.createElement("div");
  wrap.className = "table-status-cell";
  const statusBadge = document.createElement("span");
  statusBadge.className = "badge";
  statusBadge.textContent = statusLabel(job, statusLabelFn);
  wrap.appendChild(statusBadge);
  if (isJobTranscribing(job)) {
    const pct = jobProgressPct(job);
    const indeterminate = isProgressIndeterminate(job);
    const progressRow = document.createElement("div");
    progressRow.className = "table-progress-row";
    progressRow.appendChild(createProgressBar(pct, "primary", "progress-inline", indeterminate));
    const pctLabel = document.createElement("span");
    pctLabel.className = "hint table-progress-pct";
    pctLabel.textContent = jobProgressPctLabel(job);
    progressRow.appendChild(pctLabel);
    wrap.appendChild(progressRow);
  }
  statusCell.appendChild(wrap);
  return statusCell;
}

export function renderOrphanFilesTable(jobs, options) {
  const {
    emptyMessage = t("orphanFiles.emptyDefault"),
    jobStatusLabel,
    onRowClick,
    onContextMenu,
    onDelete,
    limit = 100,
  } = options;

  if (!jobs.length) {
    const empty = document.createElement("p");
    empty.className = "hint queue-table-empty";
    empty.textContent = emptyMessage;
    return empty;
  }

  const table = document.createElement("table");
  table.className = "queue-table";
  table.innerHTML = `
    <thead>
      <tr>
        <th>${t("orphanFiles.fileName")}</th>
        <th>${t("libraryTable.duration")}</th>
        <th>${t("libraryTable.status")}</th>
        <th>${t("libraryTable.identifySpeakers")}</th>
        <th>${t("orphanFiles.added")}</th>
        <th class="queue-table-actions-head">${t("orphanFiles.actions")}</th>
      </tr>
    </thead>`;
  const tbody = document.createElement("tbody");
  for (const job of jobs.slice(0, limit)) {
    const tr = document.createElement("tr");
    tr.className = "queue-table-row";
    const nameCell = document.createElement("td");
    nameCell.className = "queue-table-name";
    const nameLeading = document.createElement("div");
    nameLeading.className = "queue-table-name-inner";
    nameLeading.appendChild(msIcon(mediaIconName(job.source_path)));
    nameLeading.appendChild(document.createTextNode(jobDisplayName(job)));
    nameCell.appendChild(nameLeading);
    const durationCell = document.createElement("td");
    durationCell.className = "hint";
    durationCell.textContent = job.duration_s != null ? formatDuration(job.duration_s) : t("common.dash");
    const statusCell = renderStatusCell(job, jobStatusLabel);
    const speakersCell = document.createElement("td");
    const speakersBadge = document.createElement("span");
    speakersBadge.className = `speakers-badge ${speakersBadgeClass(job)}`;
    speakersBadge.textContent = speakersStatusLabel(job);
    speakersCell.appendChild(speakersBadge);
    const timeCell = document.createElement("td");
    timeCell.className = "hint";
    timeCell.textContent = formatRelativeTime(job.created_at);
    const actionsCell = document.createElement("td");
    actionsCell.className = "queue-table-actions";
    const deleteBtn = iconButton("delete", t("common.delete"), "icon-btn--danger");
    deleteBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      onDelete(job);
    });
    actionsCell.appendChild(deleteBtn);
    tr.appendChild(nameCell);
    tr.appendChild(durationCell);
    tr.appendChild(statusCell);
    tr.appendChild(speakersCell);
    tr.appendChild(timeCell);
    tr.appendChild(actionsCell);
    tr.addEventListener("click", () => onRowClick(job));
    tr.addEventListener("contextmenu", (event) => onContextMenu(event, job));
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  return table;
}
