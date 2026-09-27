import { showToast, jobDisplayName } from "./api.js";
import { navigate } from "./router.js";
import {
  refreshLibrary,
  batchById,
  jobStatusLabel,
  jobStatusTone,
  markSelectedBatch,
  startBatch,
  pauseBatch,
  cancelBatch,
  reorderBatchJob,
  addToBatch,
} from "./library-store.js";
import {
  isJobActive,
  isBatchActive,
  batchFileCount,
  batchDoneCount,
  formatBatchCountsSummary,
  jobProgressPct,
  createProgressBar,
} from "./library-utils.js";
import { msIcon } from "./icons.js";
import { isYoutubeBatch } from "./batch-kind.js";
import { t } from "./i18n.js";

let dragJobId = null;
let didDrag = false;

async function moveJobInBatch(batchId, jobId, delta, onRefresh) {
  const batch = batchById(batchId);
  if (!batch || batch.running) {
    showToast("batch_panel.k3146508");
    return;
  }
  const jobs = batch.jobs || [];
  const ids = jobs.map((j) => j.id);
  const idx = ids.indexOf(jobId);
  const targetIdx = idx + delta;
  if (idx < 0 || targetIdx < 0 || targetIdx >= ids.length) {
    return;
  }
  await reorderBatchJob(batchId, jobId, ids[targetIdx]);
  onRefresh?.();
}

function renderJobRow(job, batchId, index, total, batchRunning, onRefresh, onContextMenu) {
  const li = document.createElement("li");
  li.className = "job-item package-job-item";
  li.dataset.id = String(job.id);

  const order = document.createElement("div");
  order.className = "package-job-order-col";

  const grip = document.createElement("span");
  grip.className = "package-job-order hint";
  grip.textContent = "⋮⋮";
  grip.title = t("batch_panel.k536542");
  if (!batchRunning) {
    grip.draggable = true;
    grip.addEventListener("dragstart", (event) => {
      didDrag = false;
      dragJobId = job.id;
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", String(job.id));
      li.classList.add("is-dragging");
    });
    grip.addEventListener("dragend", () => {
      dragJobId = null;
      li.classList.remove("is-dragging");
      didDrag = true;
      window.setTimeout(() => {
        didDrag = false;
      }, 0);
    });
  }

  const moveBtns = document.createElement("div");
  moveBtns.className = "package-job-move-btns";
  if (!batchRunning) {
    const upBtn = document.createElement("button");
    upBtn.type = "button";
    upBtn.className = "icon-btn";
    upBtn.title = t("batch_panel.k6469774");
    upBtn.disabled = index === 0;
    upBtn.appendChild(msIcon("arrow_upward"));
    upBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      moveJobInBatch(batchId, job.id, -1, onRefresh).catch((err) =>
        showToast(err.message || String(err))
      );
    });
    const downBtn = document.createElement("button");
    downBtn.type = "button";
    downBtn.className = "icon-btn";
    downBtn.title = t("batch_panel.k4727057");
    downBtn.disabled = index >= total - 1;
    downBtn.appendChild(msIcon("arrow_downward"));
    downBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      moveJobInBatch(batchId, job.id, 1, onRefresh).catch((err) =>
        showToast(err.message || String(err))
      );
    });
    moveBtns.appendChild(upBtn);
    moveBtns.appendChild(downBtn);
  }

  order.appendChild(grip);
  order.appendChild(moveBtns);

  const body = document.createElement("div");
  body.className = "package-job-body";

  const title = document.createElement("div");
  title.className = "job-name";
  title.textContent = jobDisplayName(job);
  title.title = job.source_path || "";

  const statusWrap = document.createElement("div");
  statusWrap.className = "package-job-status";
  const status = document.createElement("div");
  status.className = `job-status job-badge job-badge--${jobStatusTone(job)}`;
  status.textContent = jobStatusLabel(job);
  statusWrap.appendChild(status);

  if (isJobActive(job) || job.status === "queued") {
    const pct = jobProgressPct(job);
    const progressRow = document.createElement("div");
    progressRow.className = "package-job-progress";
    progressRow.appendChild(createProgressBar(pct, "primary", "progress-inline"));
    const pctLabel = document.createElement("span");
    pctLabel.className = "hint";
    pctLabel.textContent = `${pct}%`;
    progressRow.appendChild(pctLabel);
    statusWrap.appendChild(progressRow);
  }

  body.appendChild(title);
  body.appendChild(statusWrap);

  li.appendChild(order);
  li.appendChild(body);

  const errText = job.error_text || job.speakers_error;
  if (errText) {
    const err = document.createElement("div");
    err.className = "job-error";
    err.textContent = errText;
    li.appendChild(err);
  }

  if (!batchRunning) {
    li.addEventListener("dragover", (event) => {
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      li.classList.add("is-drop-target");
    });
    li.addEventListener("dragleave", () => li.classList.remove("is-drop-target"));
    li.addEventListener("drop", (event) => {
      event.preventDefault();
      event.stopPropagation();
      li.classList.remove("is-drop-target");
      didDrag = true;
      const fromId = dragJobId ?? Number(event.dataTransfer.getData("text/plain"));
      if (fromId && fromId !== job.id) {
        reorderBatchJob(batchId, fromId, job.id)
          .then(() => onRefresh?.())
          .catch((err) => showToast(err.message || String(err)));
      }
      dragJobId = null;
    });
  }

  li.addEventListener("click", (event) => {
    if (didDrag) {
      didDrag = false;
      return;
    }
    if (event.target.closest(".package-job-move-btns") || event.target.closest(".package-job-order")) {
      return;
    }
    navigate("editor", { jobId: job.id });
  });
  li.addEventListener("contextmenu", (event) => onContextMenu?.(event, job, batchId));
  return li;
}

export function renderBatchPanel(batch, containerEl, options = {}) {
  const {
    onRefresh,
    onOpenRules,
    onContextMenu,
    onAddFiles,
    onAddFolder,
    onDeleteBatch,
    pickFilePaths,
    pickFolderPath,
  } = options;
  if (!containerEl || !batch) {
    return;
  }

  const batchId = batch.id;
  markSelectedBatch(batchId);
  containerEl.replaceChildren();

  const panel = document.createElement("div");
  panel.className = "batch-panel";

  const hint = document.createElement("p");
  hint.className = "hint package-hint";
  hint.textContent = batch.running
    ? isYoutubeBatch(batch)
      ? t("batch_panel.k7572064")
      : t("batch_panel.k1807877")
    : isYoutubeBatch(batch)
      ? t("batch_panel.k8106687")
      : t("batch_panel.k2392114");
  panel.appendChild(hint);

  const toolbar = document.createElement("div");
  toolbar.className = "package-toolbar batch-panel-toolbar";

  const mkBtn = (label, titleText, onClick, className = "btn-outline btn-compact") => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = className;
    btn.textContent = label;
    btn.title = titleText;
    btn.addEventListener("click", onClick);
    return btn;
  };

  const refresh = () => onRefresh?.();
  const youtubeBatch = isYoutubeBatch(batch);

  if (batch.running) {
    toolbar.appendChild(
      mkBtn(t("batch_panel.k1098111"), t("queue.pauseAfterCurrent"), () =>
        pauseBatch(batchId).then(refresh).catch((e) => showToast(e.message)),
        "btn-outline btn-compact"
      )
    );
    toolbar.appendChild(
      mkBtn(t("common.stop"), t("queue.stopBatch"), () =>
        cancelBatch(batchId).then(refresh).catch((e) => showToast(e.message)),
        "btn-danger btn-compact"
      )
    );
  } else {
    toolbar.appendChild(
      mkBtn(t("batch_panel.k2124285"), t("queue.startBatch"), () =>
        startBatch(batchId).then(refresh).catch((e) => showToast(e.message)),
        "btn-primary btn-compact"
      )
    );
  }

  const addFilesHandler =
    onAddFiles ||
    (async () => {
      if (!pickFilePaths) {
        return;
      }
      const paths = await pickFilePaths();
      if (!paths.length) {
        return;
      }
      await addToBatch(batchId, paths, false);
      await refreshLibrary();
      refresh();
      showToast(t("batch_panel.filesAdded", { count: paths.length }));
    });

  const addFolderHandler =
    onAddFolder ||
    (async () => {
      if (!pickFolderPath) {
        return;
      }
      const folder = await pickFolderPath();
      if (!folder) {
        return;
      }
      showToast("batch_panel.k762274");
    });

  if (!youtubeBatch) {
    toolbar.appendChild(
      mkBtn(t("batch_panel.k4821326"), t("batch_panel.k3641316"), () =>
        addFilesHandler(batchId, refresh).catch((e) => showToast(e.message))
      )
    );
    toolbar.appendChild(
      mkBtn(t("batch_panel.k3757200"), t("batch_panel.k9813013"), () =>
        addFolderHandler(batchId).catch((e) => showToast(e.message))
      )
    );
  }
  toolbar.appendChild(
    mkBtn(t("batch_panel.k9623597"), t("batch_panel.k79311"), () => onOpenRules?.(batchId))
  );
  toolbar.appendChild(
    mkBtn(
      t("common.delete"),
      t("batch_panel.k6649058"),
      () =>
        (onDeleteBatch ? onDeleteBatch(batchId) : Promise.resolve())
          .then(() => navigate("legacy"))
          .catch((e) => showToast(e.message)),
      "btn-outline btn-compact"
    )
  );
  panel.appendChild(toolbar);

  const listEl = document.createElement("ul");
  listEl.className = "job-list package-job-list";
  listEl.ondragover = batch.running
    ? null
    : (event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
      };

  const jobs = batch.jobs || [];
  if (!jobs.length) {
    const empty = document.createElement("li");
    empty.className = "hint package-empty";
    empty.textContent = youtubeBatch
      ? t("batch_panel.k3205825")
      : t("batch_panel.k9026581");
    listEl.appendChild(empty);
  } else {
    jobs.forEach((job, index) => {
      listEl.appendChild(
        renderJobRow(job, batchId, index, jobs.length, batch.running, refresh, onContextMenu)
      );
    });
  }

  panel.appendChild(listEl);
  containerEl.appendChild(panel);

  if (isBatchActive(batch)) {
    containerEl.dataset.polling = "1";
  } else {
    delete containerEl.dataset.polling;
  }
}
