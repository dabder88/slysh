import { navigate, getRoute, getEditorJobId } from "./router.js";
import { mountLibraryTable } from "./library-table.js";
import {
  isLibraryOrphan,
  isArchiveBatch,
  createProgressBar,
  updateProgressBarFill,
  isJobTranscribing,
  jobProgressPct,
  jobProgressPctLabel,
  isProgressIndeterminate,
  orderedSpeakerKeys,
  speakerDisplayName,
  speakerKeysForRename,
} from "./library-utils.js";
import { api, showToast, jobDisplayName, isYoutubeJob } from "./api.js";
import { readTranscribeRange } from "./media-time.js";
import { msIcon } from "./icons.js";
import { isYoutubeBatch } from "./batch-kind.js";
import { reportError } from "./errors.js";
import { ensureIntakeAllowed } from "./intake-duplicate.js";
import { getLocale, localeDateTag, t } from "./i18n.js";
import {
  SELECTED_BATCH_KEY,
  refreshLibrary as storeRefreshLibrary,
  getLibrarySnapshot as readLibrarySnapshot,
  setLibraryRefreshHook,
  setLibrarySelectionHook,
  getSelectedBatchId,
  jobById,
  upsertJobInStore,
  batchById,
  jobStatusLabel,
  jobStatusTone,
  markSelectedBatch,
  setSelectedBatch,
  hasActiveLibraryJobs,
  addToBatch,
  reorderBatchJob,
  startBatch,
  pauseBatch,
  cancelBatch,
  deleteBatchApi,
} from "./library-store.js";

const legacyWorkspace = document.getElementById("legacy-workspace");
const filesChrome = document.getElementById("files-chrome");
const batchesChrome = document.getElementById("batches-chrome");
const legacyFilesWrap = document.getElementById("legacy-files-wrap");
const legacyBatchesWrap = document.getElementById("legacy-batches-wrap");
const transcriptEl = document.getElementById("transcript-edit");
const transcriptHintEl = document.getElementById("transcript-hint");
const playerEl = document.getElementById("player");
const saveBtn = document.getElementById("btn-save");
const speakersBtn = document.getElementById("btn-speakers");
const transcribeBtn = document.getElementById("btn-transcribe");
const cancelBtn = document.getElementById("btn-cancel");
const retranscribeBtn = document.getElementById("btn-retranscribe");
const speakerRenameEl = document.getElementById("speaker-rename");
const toastEl = document.getElementById("toast");
const exportModal = document.getElementById("export-modal");
const exportNameEl = document.getElementById("export-name");
const exportDirsListEl = document.getElementById("export-dirs-list");
const exportDirAddBtn = document.getElementById("export-dir-add");
const exportFmtEl = document.getElementById("export-fmt");
const exportActionsEl = document.getElementById("export-actions");
const exportActionsPathEl = document.getElementById("export-actions-path");
const ctxMenu = document.getElementById("ctx-menu");
const jobBannerEl = document.getElementById("job-banner");
let jobBannerViewMode = null;
let jobBannerProgressStage = null;
/** @type {{ row: HTMLElement, stageText: Text, pctEl: HTMLElement, hint: HTMLElement, fill: HTMLElement, track: HTMLElement } | null} */
let jobBannerProgressRefs = null;
const batchTargetSelectEl = document.getElementById("batch-target-select");
const folderAddModal = document.getElementById("folder-add-modal");
const folderAddCountEl = document.getElementById("folder-add-count");
const folderAddNameEl = document.getElementById("folder-add-name");
const folderAddNameWrap = document.getElementById("folder-add-name-wrap");
const folderAddRecursiveEl = document.getElementById("folder-add-recursive");
const folderAddTitleEl = document.getElementById("folder-add-title");
const batchRulesModal = document.getElementById("batch-rules-modal");

const BATCH_TARGET_NEW = "__new__";
const EXPANDED_BATCHES_KEY = "legacy-expanded-batches";

let activeMainTab = "files";
let expandedLegacyBatches = loadExpandedLegacyBatches();
const selectedFileKeys = new Set();
const selectedBatchKeys = new Set();
let pendingMoveJobs = [];
let pendingExportJobs = null;
let exportTargetJobId = null;

let selectedId = null;

export function syncSelectedJobId(id) {
  if (id !== selectedId) {
    speakerKeys = [];
  }
  selectedId = id;
}

let segmentsRevision = 0;
let pollTimer = null;
let jobs = [];
let batches = [];
let orphans = [];
let selectedBatchId = null;
let speakerKeys = [];
let ctxJobId = null;
let ctxBatchId = null;
let rulesBatchId = null;
let rulesDraftMode = false;
let pendingUploadPaths = [];
let pendingUploadRules = null;
let uploadTargetResolve = null;
let dragJobId = null;
let lastSpeakersError = null;
let pendingFolderPaths = [];
let pendingFolderBatchId = null;
let stopArmJobId = null;
let stopArmTimer = null;
let modalBackdropSuppressUntil = 0;

function suppressModalBackdrop(ms = 400) {
  modalBackdropSuppressUntil = Math.max(modalBackdropSuppressUntil, Date.now() + ms);
}

function isModalBackdropSuppressed() {
  return Date.now() < modalBackdropSuppressUntil;
}

async function pickFolderWithGhostClickGuard(current = "", modalEl = null) {
  suppressModalBackdrop(500);
  const prevPointerEvents = modalEl?.style.pointerEvents ?? "";
  if (modalEl) {
    modalEl.style.pointerEvents = "none";
  }
  try {
    if (!window.pywebview?.api?.pick_folder) {
      return null;
    }
    const folder = await window.pywebview.api.pick_folder(current);
    suppressModalBackdrop(500);
    return folder || null;
  } finally {
    if (modalEl) {
      modalEl.style.pointerEvents = prevPointerEvents;
    }
  }
}

function syncLocalLibraryState() {
  const snap = readLibrarySnapshot();
  jobs = snap.jobs;
  batches = snap.batches;
  orphans = snap.orphans;
  selectedBatchId = getSelectedBatchId();
}

function loadExpandedLegacyBatches() {
  try {
    return new Set(JSON.parse(localStorage.getItem(EXPANDED_BATCHES_KEY) || "[]").map(Number));
  } catch (_) {
    return new Set();
  }
}

function saveExpandedLegacyBatches() {
  localStorage.setItem(EXPANDED_BATCHES_KEY, JSON.stringify([...expandedLegacyBatches]));
}

export function expandLegacyBatch(batchId) {
  if (batchId == null) {
    return;
  }
  expandedLegacyBatches.add(batchId);
  saveExpandedLegacyBatches();
}

function switchLegacyTab(name) {
  activeMainTab = name;
  document.querySelectorAll("#view-legacy .legacy-tab").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.tab === name);
  });
  if (filesChrome) {
    filesChrome.hidden = name !== "files";
  }
  if (batchesChrome) {
    batchesChrome.hidden = name !== "batches";
  }
  if (legacyFilesWrap) {
    legacyFilesWrap.hidden = name !== "files";
  }
  if (legacyBatchesWrap) {
    legacyBatchesWrap.hidden = name !== "batches";
  }
  renderLibrary();
}

function hasActiveJobs(list) {
  return hasActiveLibraryJobs(list);
}

function selectedBatchLabel(batchId = selectedBatchId) {
  const batch = batchById(batchId);
  return batch ? batch.name : t("queue.batchLabel");
}

/** File/folder intake target: null if none selected or YouTube batch is selected. */
function fileBatchTargetId() {
  const id = getSelectedBatchId();
  if (id == null) {
    return null;
  }
  const batch = batchById(id);
  if (batch && isYoutubeBatch(batch)) {
    return null;
  }
  return id;
}

function syncBatchTargetSelect() {
  if (!batchTargetSelectEl) {
    return;
  }
  const current = selectedBatchId == null ? "" : String(selectedBatchId);
  batchTargetSelectEl.innerHTML = "";
  const liveBatches = batches.filter((batch) => !isArchiveBatch(batch));
  if (!liveBatches.length) {
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = t("legacy.createBatchFirst");
    batchTargetSelectEl.appendChild(empty);
    batchTargetSelectEl.value = "";
    return;
  }
  for (const batch of liveBatches) {
    const opt = document.createElement("option");
    opt.value = String(batch.id);
    opt.textContent = batch.name;
    batchTargetSelectEl.appendChild(opt);
  }
  const newOpt = document.createElement("option");
  newOpt.value = BATCH_TARGET_NEW;
  newOpt.textContent = t("legacy.createNewBatch");
  batchTargetSelectEl.appendChild(newOpt);
  if ([...batchTargetSelectEl.options].some((opt) => opt.value === current)) {
    batchTargetSelectEl.value = current;
  } else if (liveBatches.length) {
    setSelectedBatch(liveBatches[0].id);
    batchTargetSelectEl.value = String(getSelectedBatchId());
  }
  syncBatchesChrome();
}

function syncBatchesChrome() {
  const batchId = getSelectedBatchId();
  const batch = batchById(batchId);
  const youtube = batch && isYoutubeBatch(batch);
  const addFiles = document.getElementById("btn-batch-add-files");
  const addFolder = document.getElementById("btn-batch-add-folder");
  const hint = document.querySelector("#batches-chrome .hint");
  if (addFiles) {
    addFiles.disabled = Boolean(youtube);
    addFiles.title = youtube
      ? t("legacy.k4921597")
      : "";
  }
  if (addFolder) {
    addFolder.disabled = Boolean(youtube);
    addFolder.title = youtube
      ? t("legacy.k4921597")
      : "";
  }
  if (hint && youtube) {
    hint.textContent =
      t("legacy.youtubeBatchNoFiles");
  } else if (hint) {
    hint.textContent =
      t("legacy.allBatchesHint");
  }
}

function defaultBatchName(paths) {
  for (const path of paths || []) {
    const base = String(path).split(/[/\\]/).pop() || "";
    if (!base.includes(".")) {
      return base || t("queue.batchLabel");
    }
  }
  const first = (paths && paths[0]) || "";
  const stem = first.split(/[/\\]/).pop() || t("queue.batchLabel");
  return stem.replace(/\.[^.]+$/, "") || t("queue.batchLabel");
}

function pathLooksLikeFolder(path) {
  const base = String(path).split(/[/\\]/).pop() || "";
  return !/\.(wav|mp3|m4a|flac|ogg|opus|webm|mp4|mkv|avi)$/i.test(base);
}

async function refreshLibrary() {
  await storeRefreshLibrary();
}

async function refreshJobs() {
  await refreshLibrary();
}

function progressStageLabel(job) {
  if (job.speakers_running) {
    return t("legacy.stageSpeakers");
  }
  if (job.engine_starting) {
    return t("legacy.stageModelLoad");
  }
  if (job.status === "queued") {
    return t("queue.inQueue");
  }
  return t("legacy.stageTranscribe");
}

function jobBannerProgressStageKey(job) {
  if (job.speakers_running) {
    return "speakers";
  }
  if (job.engine_starting) {
    return "engine";
  }
  if (job.status === "queued") {
    return "queued";
  }
  return "transcribe";
}

function resetJobBannerDom() {
  if (!jobBannerEl) {
    return;
  }
  jobBannerEl.replaceChildren();
  jobBannerViewMode = null;
  jobBannerProgressStage = null;
  jobBannerProgressRefs = null;
}

function buildJobBannerProgressDom(job) {
  const row = document.createElement("div");
  row.className = "job-progress";

  const meta = document.createElement("div");
  meta.className = "job-progress-meta";
  const label = document.createElement("span");
  label.className = "job-progress-label";
  const icon = msIcon(job.speakers_running ? "record_voice_over" : "graphic_eq");
  icon.classList.add("job-progress-icon");
  label.appendChild(icon);
  const stageText = document.createTextNode(progressStageLabel(job));
  label.appendChild(stageText);
  const pctEl = document.createElement("span");
  pctEl.className = "job-progress-pct";
  meta.appendChild(label);
  meta.appendChild(pctEl);

  const bar = createProgressBar(
    jobProgressPct(job),
    "primary",
    "progress-bar--lg",
    isProgressIndeterminate(job),
  );
  const fill = bar.querySelector(".queue-progress-fill");
  const hint = document.createElement("p");
  hint.className = "hint job-progress-hint";

  row.appendChild(meta);
  row.appendChild(bar);
  row.appendChild(hint);

  return {
    row,
    stageText,
    pctEl,
    hint,
    fill,
    track: bar,
  };
}

export function hideEditorJobBanner() {
  syncJobBanner(null);
}

function syncJobBanner(job) {
  if (!jobBannerEl) {
    return;
  }
  if (!job) {
    jobBannerEl.hidden = true;
    resetJobBannerDom();
    return;
  }
  const tone = jobStatusTone(job);
  const transcribing = isJobTranscribing(job);
  jobBannerEl.hidden = false;
  jobBannerEl.className = `job-banner editor-banner job-badge--${tone}${
    transcribing ? " job-banner--progress" : ""
  }`;

  if (!transcribing) {
    if (jobBannerViewMode !== "text") {
      resetJobBannerDom();
      jobBannerViewMode = "text";
    }
    let text = jobStatusLabel(job);
    if (job.status === "failed" && job.error_text) {
      text = `${text}: ${job.error_text}`;
    } else if (job.speakers_error) {
      text = `${text} · ${job.speakers_error}`;
    }
    jobBannerEl.textContent = text;
    return;
  }

  const stage = jobBannerProgressStageKey(job);
  if (jobBannerViewMode !== "progress" || jobBannerProgressStage !== stage) {
    resetJobBannerDom();
    jobBannerViewMode = "progress";
    jobBannerProgressStage = stage;
    jobBannerProgressRefs = buildJobBannerProgressDom(job);
    jobBannerEl.appendChild(jobBannerProgressRefs.row);
  }

  const refs = jobBannerProgressRefs;
  if (!refs) {
    return;
  }
  const pct = jobProgressPct(job);
  const indeterminate = isProgressIndeterminate(job);
  refs.stageText.textContent = progressStageLabel(job);
  refs.pctEl.textContent = jobProgressPctLabel(job);
  refs.hint.textContent = jobStatusLabel(job);
  updateProgressBarFill(refs.fill, pct, indeterminate, "primary", refs.track);
}

function legacyNeedsPoll() {
  if (hasActiveJobs(jobs)) {
    return true;
  }
  for (const batchId of expandedLegacyBatches) {
    const panel = document.getElementById(`legacy-batch-panel-${batchId}`);
    if (panel?.dataset?.polling === "1") {
      return true;
    }
  }
  return false;
}

function syncPoll() {
  if (legacyNeedsPoll()) {
    if (!pollTimer) {
      pollTimer = setInterval(() => pollJobs(), 500);
    }
  } else {
    stopPoll();
  }
}

function pruneSelectedKeys(set, valid) {
  for (const key of [...set]) {
    if (!valid.has(key)) {
      set.delete(key);
    }
  }
}

export function pruneLibrarySelectedKeys(set, valid) {
  pruneSelectedKeys(set, valid);
}

function selectedJobsFromKeys() {
  return orphans.filter((job) => selectedFileKeys.has(`job:${job.id}`));
}

function selectedBatchesFromKeys() {
  return batches.filter((batch) => selectedBatchKeys.has(`batch:${batch.id}`));
}

function toastBulkResult(ok, errors, doneLabel) {
  if (errors.length && ok) {
    showToast(t("legacy.bulkErrors", { doneLabel, ok, error: errors[0] }));
    return;
  }
  if (errors.length) {
    showToast(errors[0]);
    return;
  }
  showToast(doneLabel);
}

async function runEach(items, fn) {
  let ok = 0;
  const errors = [];
  for (const item of items) {
    try {
      await fn(item);
      ok += 1;
    } catch (err) {
      errors.push(err.message || String(err));
    }
  }
  return { ok, errors };
}

function canStartJob(job) {
  return ["idle", "failed", "cancelled"].includes(job.status);
}

function isJobBusy(job) {
  return (
    job.status === "queued" ||
    job.status === "running" ||
    job.speakers_running ||
    job.engine_starting
  );
}

async function bulkExportJobs(jobsToExport) {
  openBatchExportModal(jobsToExport);
}

function closeMoveToBatchModal() {
  const modal = document.getElementById("move-to-batch-modal");
  if (modal) {
    modal.hidden = true;
  }
  pendingMoveJobs = [];
}

function syncMoveToBatchNameWrap() {
  const selectEl = document.getElementById("move-to-batch-select");
  const wrap = document.getElementById("move-to-batch-name-wrap");
  if (!wrap || !selectEl) {
    return;
  }
  wrap.hidden = selectEl.value !== BATCH_TARGET_NEW;
}

function openMoveToBatchModal(jobsToMove) {
  const modal = document.getElementById("move-to-batch-modal");
  const selectEl = document.getElementById("move-to-batch-select");
  const countEl = document.getElementById("move-to-batch-count");
  const nameEl = document.getElementById("move-to-batch-name");
  if (!modal || !selectEl) {
    showToast("common.restartApp");
    return;
  }
  pendingMoveJobs = jobsToMove;
  if (countEl) {
    countEl.textContent = t("legacy.filesCount", { count: jobsToMove.length });
  }
  const live = batches.filter((batch) => !isArchiveBatch(batch));
  selectEl.replaceChildren();
  const newOpt = document.createElement("option");
  newOpt.value = BATCH_TARGET_NEW;
  newOpt.textContent = t("legacy.k7672425");
  selectEl.appendChild(newOpt);
  for (const batch of live) {
    const opt = document.createElement("option");
    opt.value = String(batch.id);
    opt.textContent = batch.name || t("legacy.batchNumber", { id: batch.id });
    selectEl.appendChild(opt);
  }
  if (live.length && selectedBatchId != null && live.some((b) => b.id === selectedBatchId)) {
    selectEl.value = String(selectedBatchId);
  } else {
    selectEl.value = BATCH_TARGET_NEW;
  }
  if (nameEl) {
    nameEl.value = defaultBatchName(jobsToMove.map((job) => job.source_path));
  }
  syncMoveToBatchNameWrap();
  modal.hidden = false;
}

async function confirmMoveToBatch() {
  const selectEl = document.getElementById("move-to-batch-select");
  const nameEl = document.getElementById("move-to-batch-name");
  const jobsToMove = [...pendingMoveJobs];
  const paths = jobsToMove.map((job) => job.source_path).filter(Boolean);
  if (!paths.length) {
    closeMoveToBatchModal();
    return;
  }
  try {
    if (!selectEl || selectEl.value === BATCH_TARGET_NEW) {
      const name = (nameEl?.value || "").trim() || defaultBatchName(paths);
      const batch = await createBatchNamed(name, paths);
      closeMoveToBatchModal();
      selectedFileKeys.clear();
      if (batch?.id != null) {
        navigate("legacy", { batchId: batch.id, tab: "batches" });
      }
      return;
    }
    const batchId = Number(selectEl.value);
    await addToBatch(batchId, paths, false);
    closeMoveToBatchModal();
    selectedFileKeys.clear();
    await refreshLibrary();
    showToast(t("legacy.addedToBatch", { name: selectedBatchLabel(batchId) }));
    navigate("legacy", { batchId, tab: "batches" });
  } catch (err) {
    showToast(err.message || String(err));
  }
}

export async function runJobsBulkAction(jobs, action, { onClear } = {}) {
  const selected = jobs || [];
  if (!selected.length) {
    showToast("legacy.selectFilesFirst");
    return;
  }
  if (action === "start") {
    const targets = selected.filter(canStartJob);
    if (!targets.length) {
      showToast("legacy.noFilesToStart");
      return;
    }
    const { ok, errors } = await runEach(targets, (job) =>
      api(`/api/jobs/${job.id}/start`, { method: "POST" })
    );
    onClear?.();
    await refreshJobs();
    toastBulkResult(ok, errors, t("legacy.startedCount", { count: ok }));
    return;
  }
  if (action === "cancel") {
    const targets = selected.filter(isJobBusy);
    if (!targets.length) {
      showToast("legacy.noQueuedFiles");
      return;
    }
    const { ok, errors } = await runEach(targets, (job) =>
      api(`/api/jobs/${job.id}/cancel`, { method: "POST" })
    );
    onClear?.();
    await refreshJobs();
    toastBulkResult(ok, errors, t("legacy.stoppedCount", { count: ok }));
    return;
  }
  if (action === "archive") {
    const targets = selected.filter((job) => job.status === "completed" && !job.archived);
    if (!targets.length) {
      showToast("legacy.archiveOnlyCompleted");
      return;
    }
    if (!window.confirm(t("legacy.confirmArchive", { count: targets.length }))) {
      return;
    }
    const { ok, errors } = await runEach(targets, (job) =>
      api(`/api/jobs/${job.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ archived: true }),
      })
    );
    onClear?.();
    await refreshJobs();
    toastBulkResult(ok, errors, t("legacy.archivedCount", { count: ok }));
    refreshLibraryViews();
    return;
  }
  if (action === "unarchive") {
    const targets = selected.filter((job) => job.archived);
    if (!targets.length) {
      showToast("legacy.noArchiveRestore");
      return;
    }
    if (!window.confirm(t("legacy.confirmUnarchive", { count: targets.length }))) {
      return;
    }
    const { ok, errors } = await runEach(targets, (job) =>
      api(`/api/jobs/${job.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ archived: false }),
      })
    );
    onClear?.();
    await refreshJobs();
    toastBulkResult(ok, errors, t("legacy.restoredCount", { count: ok }));
    refreshLibraryViews();
    return;
  }
  if (action === "delete") {
    if (!window.confirm(t("legacy.confirmDeleteJobs", { count: selected.length }))) {
      return;
    }
    const { ok, errors } = await runEach(selected, (job) =>
      api(`/api/jobs/${job.id}`, { method: "DELETE" })
    );
    onClear?.();
    await refreshJobs();
    toastBulkResult(ok, errors, t("legacy.deletedCount", { count: ok }));
    refreshLibraryViews();
    return;
  }
  if (action === "export") {
    await bulkExportJobs(selected);
    return;
  }
  if (action === "to-batch") {
    openMoveToBatchModal(selected);
  }
}

export async function runBatchesBulkAction(batchList, action, { onClear } = {}) {
  const selected = batchList || [];
  if (!selected.length) {
    showToast("legacy.selectBatchesFirst");
    return;
  }
  if (action === "start") {
    const targets = selected.filter((batch) => !batch.running && batch.total_count > 0);
    if (!targets.length) {
      showToast("legacy.noBatchesToStart");
      return;
    }
    const { ok, errors } = await runEach(targets, (batch) =>
      api(`/api/batches/${batch.id}/start`, { method: "POST" })
    );
    onClear?.();
    await refreshJobs();
    toastBulkResult(ok, errors, t("legacy.batchesStarted", { count: ok }));
    return;
  }
  if (action === "cancel") {
    const targets = selected.filter((batch) => batch.running);
    if (!targets.length) {
      showToast("legacy.noRunningBatches");
      return;
    }
    const { ok, errors } = await runEach(targets, (batch) =>
      api(`/api/batches/${batch.id}/cancel`, { method: "POST" })
    );
    onClear?.();
    await refreshJobs();
    toastBulkResult(ok, errors, t("legacy.stoppedCount", { count: ok }));
    return;
  }
  if (action === "archive") {
    const targets = selected.filter((batch) => !batch.running && !batch.archived);
    if (!targets.length) {
      showToast("legacy.cannotArchiveRunning");
      return;
    }
    if (!window.confirm(t("legacy.confirmArchiveBatches", { count: targets.length }))) {
      return;
    }
    const { ok, errors } = await runEach(targets, (batch) =>
      api(`/api/batches/${batch.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ archived: true }),
      })
    );
    onClear?.();
    await refreshJobs();
    toastBulkResult(ok, errors, t("legacy.archivedCount", { count: ok }));
    refreshLibraryViews();
    return;
  }
  if (action === "unarchive") {
    const targets = selected.filter((batch) => batch.archived);
    if (!targets.length) {
      showToast("legacy.noBatchesRestore");
      return;
    }
    if (!window.confirm(t("legacy.confirmUnarchiveBatches", { count: targets.length }))) {
      return;
    }
    const { ok, errors } = await runEach(targets, (batch) =>
      api(`/api/batches/${batch.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ archived: false }),
      })
    );
    onClear?.();
    await refreshJobs();
    toastBulkResult(ok, errors, t("legacy.batchesRestored", { count: ok }));
    refreshLibraryViews();
    return;
  }
  if (action === "delete") {
    if (!window.confirm(t("legacy.confirmDeleteBatches", { count: selected.length }))) {
      return;
    }
    const { ok, errors } = await runEach(selected, (batch) =>
      api(`/api/batches/${batch.id}`, { method: "DELETE" })
    );
    onClear?.();
    await refreshJobs();
    toastBulkResult(ok, errors, t("legacy.batchesDeleted", { count: ok }));
    refreshLibraryViews();
    return;
  }
  if (action === "export") {
    const jobsToExport = selected.flatMap((batch) => batch.jobs || []);
    if (!jobsToExport.some((job) => job.status === "completed")) {
      showToast("legacy.k4272074");
      return;
    }
    await bulkExportJobs(jobsToExport);
  }
}

async function runFilesBulk(action) {
  await runJobsBulkAction(selectedJobsFromKeys(), action, {
    onClear: () => selectedFileKeys.clear(),
  });
}

async function runBatchesBulk(action) {
  await runBatchesBulkAction(selectedBatchesFromKeys(), action, {
    onClear: () => selectedBatchKeys.clear(),
  });
}

function renderFilesList() {
  if (!legacyFilesWrap) {
    return;
  }
  const list = orphans.filter(isLibraryOrphan);
  pruneSelectedKeys(selectedFileKeys, new Set(list.map((job) => `job:${job.id}`)));
  mountLibraryTable(legacyFilesWrap, {
      storageKey: "files",
      jobs: list,
      batches: [],
      emptyMessage: t("legacy.k2031857"),
      jobStatusLabel,
      jobStatusTone,
      expandedBatches: expandedLegacyBatches,
      onExpandChange: () => renderLibrary(),
      onJobClick: (job) => navigate("editor", { jobId: job.id }),
      onJobContextMenu: (event, job) => openContextMenu(event, job, null),
      onBatchClick: () => {},
      onBatchContextMenu: () => {},
      selectable: true,
      selectedKeys: selectedFileKeys,
      bulkKind: "files",
      onBulkAction: (action) =>
        runFilesBulk(action).catch((err) => showToast(err.message || String(err))),
  });
}

function renderBatchesList() {
  if (!legacyBatchesWrap) {
    return;
  }
  const pending = batches.filter((b) => !isArchiveBatch(b));
  pruneSelectedKeys(selectedBatchKeys, new Set(pending.map((batch) => `batch:${batch.id}`)));
  mountLibraryTable(legacyBatchesWrap, {
      storageKey: "batches",
      jobs: [],
      batches: pending,
      emptyMessage: t("legacy.k7955166"),
      jobStatusLabel,
      jobStatusTone,
      expandedBatches: expandedLegacyBatches,
      onExpandChange: () => {
        saveExpandedLegacyBatches();
        renderLibrary();
      },
      onJobClick: (job) => navigate("editor", { jobId: job.id }),
      onJobContextMenu: (event, job, batchId) => openContextMenu(event, job, batchId),
      onBatchClick: (batch) => setSelectedBatch(batch.id),
      onBatchContextMenu: (event, batch) => openBatchContextMenu(event, batch),
      selectable: true,
      selectedKeys: selectedBatchKeys,
      bulkKind: "batches",
      onBulkAction: (action) =>
        runBatchesBulk(action).catch((err) => showToast(err.message || String(err))),
  });
}

function renderLibrary() {
  try {
    renderFilesList();
    renderBatchesList();
  } catch (err) {
    reportError(t("legacy.k4826940"), err);
  }
}

function renderJobs() {
  renderLibrary();
}

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function isEditingTranscript() {
  if (getRoute() === "editor" && window.__editorIsDraftDirty?.()) {
    return true;
  }
  return document.activeElement === transcriptEl;
}

async function selectJob(id) {
  syncSelectedJobId(id);
  renderLibrary();
  const job = await api(`/api/jobs/${id}`);
  upsertJobInStore(job);
  if (getRoute() !== "editor") {
    return job;
  }
  if (playerEl) {
    if (isYoutubeJob(job)) {
      playerEl.removeAttribute("src");
      playerEl.load();
    } else {
      playerEl.src = `/api/jobs/${id}/media`;
    }
  }
  if (!isEditingTranscript()) {
    segmentsRevision = Number(job.segments_revision) || 0;
    renderTranscript(job.transcript || "");
  }
  syncSpeakersUi(job);
  syncExportActions(job);
  syncTranscribeUi(job);
  syncJobBanner(job);
  if (job.speakers_error && job.speakers_error !== lastSpeakersError) {
    lastSpeakersError = job.speakers_error;
    showToast(job.speakers_error);
  }
  syncPoll();
  if (editorRefreshHook) {
    editorRefreshHook(job);
  }
  return job;
}

async function pollJobs() {
  await refreshLibrary();
  let pollId = selectedId;
  if (getRoute() === "editor") {
    const editorId = getEditorJobId();
    if (editorId != null) {
      pollId = editorId;
      if (selectedId !== editorId) {
        syncSelectedJobId(editorId);
      }
    }
  }
  if (pollId != null) {
    const job = await api(`/api/jobs/${pollId}`);
    if (!isEditingTranscript()) {
      renderTranscript(job.transcript || "");
    }
    syncSpeakersUi(job);
    syncExportActions(job);
    syncTranscribeUi(job);
    syncJobBanner(job);
    if (job.speakers_error && job.speakers_error !== lastSpeakersError) {
      lastSpeakersError = job.speakers_error;
      showToast(job.speakers_error);
    }
    upsertJobInStore(job);
    syncLocalLibraryState();
    renderLibrary();
    if (editorRefreshHook) {
      editorRefreshHook(job);
    }
  }
  syncPoll();
}

function syncTranscribeUi(job) {
  const youtube = isYoutubeJob(job);
  const isActive = Boolean(
    job &&
      (job.status === "queued" ||
        job.status === "running" ||
        job.speakers_running ||
        job.engine_starting)
  );
  const completed = job?.status === "completed";
  const canStart = Boolean(
    job &&
      (["idle", "failed", "cancelled"].includes(job.status) ||
        (youtube && completed && !isActive))
  );
  const inEditor = getRoute() === "editor";
  const topTranscribe = document.getElementById("btn-topbar-transcribe");
  const topStop = document.getElementById("btn-topbar-stop");

  if (transcribeBtn) {
    transcribeBtn.hidden = false;
    transcribeBtn.disabled = !canStart;
    transcribeBtn.textContent = youtube
      ? t("common.refreshTranscript")
      : t("common.transcribe");
  }
  if (cancelBtn) {
    cancelBtn.hidden = !isActive;
    cancelBtn.textContent = t("common.stop");
    if (!isActive) {
      cancelBtn.disabled = true;
    }
  }
  if (retranscribeBtn) {
    retranscribeBtn.hidden = !completed || youtube;
  }
  if (topTranscribe) {
    topTranscribe.hidden = !inEditor;
    topTranscribe.disabled = !canStart;
    const topLabel = topTranscribe.querySelector("span:last-child");
    if (topLabel) {
      topLabel.textContent = youtube && completed ? t("common.refreshTranscript") : t("common.transcribe");
    }
  }
  if (topStop) {
    topStop.hidden = !inEditor || !isActive;
    if (!isActive) {
      topStop.disabled = true;
    }
  }

  const armId = isActive && job ? job.id : null;
  if (armId !== stopArmJobId) {
    stopArmJobId = armId;
    if (stopArmTimer) {
      clearTimeout(stopArmTimer);
      stopArmTimer = null;
    }
    if (armId != null) {
      if (cancelBtn) {
        cancelBtn.disabled = true;
      }
      if (topStop) {
        topStop.disabled = true;
      }
      stopArmTimer = setTimeout(() => {
        if (cancelBtn && !cancelBtn.hidden) {
          cancelBtn.disabled = false;
        }
        if (topStop && !topStop.hidden) {
          topStop.disabled = false;
        }
      }, 700);
    }
  }
}

export function syncExportActions(job, exportPaths = null) {
  if (!exportActionsEl || !exportActionsPathEl) {
    return;
  }
  const editActive = document.getElementById("editor-mode-edit")?.classList.contains("is-active");
  const path = job && job.last_export_path;
  let paths =
    Array.isArray(exportPaths) && exportPaths.length
      ? exportPaths.filter(Boolean)
      : Array.isArray(job?.last_export_paths) && job.last_export_paths.length
        ? job.last_export_paths.filter(Boolean)
        : path
          ? [path]
          : [];
  const displayPath = paths.length ? paths[paths.length - 1] : path;
  if (editActive || !displayPath) {
    exportActionsEl.hidden = true;
    if (!displayPath) {
      exportActionsPathEl.textContent = "";
      delete exportActionsPathEl.dataset.exportPath;
      delete exportActionsPathEl.dataset.exportPaths;
      exportActionsPathEl.removeAttribute("title");
    }
    return;
  }
  exportActionsEl.hidden = false;
  exportActionsPathEl.textContent = displayPath;
  exportActionsPathEl.dataset.exportPath = displayPath;
  if (paths.length > 1) {
    exportActionsPathEl.dataset.exportPaths = JSON.stringify(paths);
    exportActionsPathEl.title = paths.join("\n");
  } else {
    delete exportActionsPathEl.dataset.exportPaths;
    exportActionsPathEl.title = displayPath;
  }
}

function activeJobIdForExport() {
  if (selectedId != null) {
    return selectedId;
  }
  if (getRoute() === "editor") {
    return getEditorJobId();
  }
  return null;
}

function pathFromExportActionsDom() {
  if (!exportActionsEl || exportActionsEl.hidden) {
    return "";
  }
  const fromDataset = exportActionsPathEl?.dataset?.exportPath?.trim();
  if (fromDataset) {
    return fromDataset;
  }
  return (exportActionsPathEl?.textContent || "").trim();
}

async function resolveExportOpenPaths() {
  if (exportActionsPathEl?.dataset?.exportPaths) {
    try {
      const parsed = JSON.parse(exportActionsPathEl.dataset.exportPaths);
      if (Array.isArray(parsed) && parsed.length) {
        return parsed.map((p) => String(p).trim()).filter(Boolean);
      }
    } catch {
      /* ignore */
    }
  }
  const domPath = pathFromExportActionsDom();
  if (domPath) {
    return [domPath];
  }
  const id = activeJobIdForExport();
  if (id == null) {
    return [];
  }
  const job = jobById(id);
  if (Array.isArray(job?.last_export_paths) && job.last_export_paths.length) {
    return job.last_export_paths.filter(Boolean);
  }
  if (job?.last_export_path) {
    return [job.last_export_path];
  }
  if (getRoute() === "editor" && getEditorJobId() === id) {
    try {
      const fresh = await api(`/api/jobs/${id}`);
      upsertJobInStore(fresh);
      if (Array.isArray(fresh.last_export_paths) && fresh.last_export_paths.length) {
        return fresh.last_export_paths;
      }
      return fresh.last_export_path ? [fresh.last_export_path] : [];
    } catch {
      return [];
    }
  }
  return [];
}

function uniqueSpeakers(segments) {
  return orderedSpeakerKeys(segments);
}

export async function startSpeakers(jobId) {
  const setup = await api("/api/setup");
  if (setup.cloud_only) {
    showToast("legacy.k6956190");
    return;
  }
  await api(`/api/jobs/${jobId}/speakers`, { method: "POST" });
}

export async function waitForSpeakers(jobId, { intervalMs = 1000, onUpdate } = {}) {
  let job;
  while (true) {
    job = await api(`/api/jobs/${jobId}`);
    if (onUpdate) {
      onUpdate(job);
    }
    if (!job.speakers_running) {
      return job;
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

function syncSpeakersUi(job) {
  const completed = job && job.status === "completed";
  const youtube = isYoutubeJob(job);
  if (speakersBtn) {
    speakersBtn.hidden = !completed || youtube;
    speakersBtn.disabled = Boolean(job && job.speakers_running);
  }
  const keys = speakerKeys.length
    ? speakerKeys
    : speakerKeysForRename(job.segments || []);
  const names = job?.speaker_names || {};
  renderSpeakerRename(completed && !youtube ? keys : [], names);
}

function renderSpeakerRename(keys, names = {}) {
  if (!speakerRenameEl) {
    return;
  }
  const current = Array.from(speakerRenameEl.querySelectorAll("input")).map(
    (input) => input.dataset.speakerKey
  );
  const same =
    current.length === keys.length && current.every((key, index) => key === keys[index]);
  if (same) {
    speakerRenameEl.hidden = keys.length === 0;
    return;
  }
  speakerRenameEl.innerHTML = "";
  if (!keys.length) {
    speakerRenameEl.hidden = true;
    return;
  }
  speakerRenameEl.hidden = false;
  for (const key of keys) {
    const label = document.createElement("label");
    label.textContent = speakerDisplayName(key, names[key]);
    const input = document.createElement("input");
    input.dataset.speakerKey = key;
    input.value = names[key] || "";
    input.placeholder = t("common.name");
    input.addEventListener("change", () => saveSpeakerNames().catch((err) => showToast(err.message)));
    label.appendChild(input);
    speakerRenameEl.appendChild(label);
  }
}

async function saveSpeakerNames() {
  if (selectedId == null) {
    return;
  }
  const body = {};
  for (const input of speakerRenameEl.querySelectorAll("input")) {
    const name = input.value.trim();
    if (name) {
      body[input.dataset.speakerKey] = name;
    }
  }
  if (!Object.keys(body).length) {
    return;
  }
  await api(`/api/jobs/${selectedId}/speakers`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await selectJob(selectedId);
}

async function runSpeakers() {
  if (selectedId == null) {
    return;
  }
  try {
    await startSpeakers(selectedId);
    lastSpeakersError = null;
    showToast("meeting.k2351323");
    await refreshJobs();
    await waitForSpeakers(selectedId);
    await selectJob(selectedId);
  } catch (err) {
    showToast(err.message || String(err));
  }
}

function renderTranscript(text) {
  if (!transcriptEl || !transcriptHintEl) {
    return;
  }
  const value = text || "";
  const hasText = Boolean(value);
  const editorEditActive = document.getElementById("editor-mode-edit")?.classList.contains("is-active");
  const hideForEditorView = getRoute() === "editor" && !editorEditActive;
  transcriptEl.hidden = !hasText || hideForEditorView;
  transcriptHintEl.hidden = !hasText || hideForEditorView;
  if (transcriptEl.value !== value) {
    transcriptEl.value = value;
  }
}

function seekTo(ms) {
  try {
    playerEl.currentTime = Math.max(0, Number(ms) / 1000);
    playerEl.play().catch(() => {});
  } catch (_) {
    /* ignore */
  }
}

function seekFromTranscriptClick() {
  const pos = transcriptEl.selectionStart;
  const before = transcriptEl.value.slice(0, pos);
  const lineStart = before.lastIndexOf("\n") + 1;
  const rest = transcriptEl.value.slice(lineStart);
  const line = rest.split("\n", 1)[0] || "";
  const match = line.match(/^\[(\d{2}):(\d{2}):(\d{2})\]/);
  if (!match) {
    return;
  }
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  const seconds = Number(match[3]);
  seekTo(((hours * 3600) + (minutes * 60) + seconds) * 1000);
}

function isAbsolutePath(path) {
  return /^(?:[A-Za-z]:[\\/]|\\\\|\/|file:)/i.test(String(path || "").trim());
}

function pathsFromDrop(event) {
  const files = Array.from(event.dataTransfer.files || []);
  const fromFiles = files
    .map((f) => f.pywebviewFullPath || f.path)
    .filter((path) => path && isAbsolutePath(path));
  const uriList = (event.dataTransfer.getData("text/uri-list") || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#") && isAbsolutePath(line));
  const plain = (event.dataTransfer.getData("text/plain") || "").trim();
  const merged = [...fromFiles, ...uriList];
  if (plain && isAbsolutePath(plain)) {
    merged.push(plain);
  }
  return [...new Set(merged)];
}

async function addOrphanFiles(paths) {
  const unique = [...new Set((paths || []).filter(Boolean))];
  if (!unique.length) {
    return;
  }
  const scan = await api("/api/batches/scan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paths: unique, recursive: false }),
  });
  const pathsToAdd = scan.paths || [];
  if (pathsToAdd.length) {
    const allowed = await ensureIntakeAllowed({ paths: pathsToAdd });
    if (!allowed) {
      return;
    }
  }
  for (const path of pathsToAdd) {
    await api("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
  }
  await refreshLibrary();
  showToast(t("legacy.filesAdded", { count: pathsToAdd.length }));
}

async function addFilesToSelectedBatch(paths, batchId = selectedBatchId) {
  if (batchId == null) {
    showToast("legacy.k7264921");
    switchLegacyTab("batches");
    return;
  }
  const batch = batchById(batchId);
  if (batch && isYoutubeBatch(batch)) {
    showToast(t("legacy.youtubeBatchNoFiles"));
    return;
  }
  const unique = [...new Set((paths || []).filter(Boolean))];
  if (!unique.length) {
    return;
  }
  if (unique.some(pathLooksLikeFolder)) {
    showToast("legacy.k3602429");
    return;
  }
  try {
    await addToBatch(batchId, unique, false);
    await refreshLibrary();
    showToast(t("legacy.addedToBatch", { name: selectedBatchLabel(batchId) }));
  } catch (err) {
    showToast(err.message || String(err));
    await refreshLibrary();
  }
}

async function addPathsForCurrentTab(paths) {
  const unique = [...new Set((paths || []).filter(Boolean))];
  if (!unique.length) {
    return;
  }
  const onlyFolders = unique.every(pathLooksLikeFolder);
  if (onlyFolders) {
    if (activeMainTab === "files") {
      showToast("legacy.k3247797");
      switchLegacyTab("batches");
      return;
    }
    if (selectedBatchId == null) {
      await openFolderAddModal(unique, null);
      return;
    }
    await openFolderAddModal(unique, selectedBatchId);
    return;
  }
  if (unique.some(pathLooksLikeFolder)) {
    showToast("legacy.k6822704");
    return;
  }
  if (activeMainTab === "batches") {
    await addFilesToSelectedBatch(unique);
  } else {
    try {
      await addOrphanFiles(unique);
    } catch (err) {
      showToast(err.message || String(err));
      await refreshLibrary();
    }
  }
}

async function enqueueDropped(paths) {
  await addPathsForCurrentTab(paths);
}

function closeFolderAddModal() {
  if (folderAddModal) {
    folderAddModal.hidden = true;
  }
  pendingFolderPaths = [];
  pendingFolderBatchId = null;
}

async function openFolderAddModal(paths, batchId) {
  if (!folderAddModal) {
    showToast("common.restartApp");
    return;
  }
  pendingFolderPaths = [...new Set((paths || []).filter(Boolean))];
  pendingFolderBatchId = batchId;
  if (!pendingFolderPaths.length) {
    return;
  }
  const creating = batchId == null;
  if (folderAddTitleEl) {
    folderAddTitleEl.textContent = creating ? t("legacy.k7009704") : t("legacy.k988828");
  }
  if (folderAddNameWrap) {
    folderAddNameWrap.hidden = !creating;
  }
  if (folderAddNameEl) {
    folderAddNameEl.value = defaultBatchName(pendingFolderPaths);
  }
  if (folderAddRecursiveEl) {
    folderAddRecursiveEl.checked = false;
  }
  try {
    const scan = await api("/api/batches/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paths: pendingFolderPaths, recursive: false }),
    });
    const label = creating
      ? t("legacy.packageCreateFiles", { count: scan.count })
      : t("legacy.packageAddFiles", { name: selectedBatchLabel(batchId), count: scan.count });
    if (folderAddCountEl) {
      folderAddCountEl.textContent = label;
    }
  } catch (err) {
    if (folderAddCountEl) {
      folderAddCountEl.textContent = err.message || String(err);
    }
  }
  folderAddModal.hidden = false;
}

async function confirmFolderAdd() {
  const paths = pendingFolderPaths;
  const batchId = pendingFolderBatchId;
  const recursive = Boolean(folderAddRecursiveEl && folderAddRecursiveEl.checked);
  closeFolderAddModal();
  if (!paths.length) {
    return;
  }
  try {
    if (batchId == null) {
      const name =
        (folderAddNameEl && folderAddNameEl.value.trim()) || defaultBatchName(paths);
      const batch = await api("/api/batches", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      await addToBatch(batch.id, paths, recursive);
      setSelectedBatch(batch.id);
      switchLegacyTab("batches");
      await refreshLibrary();
      showToast(t("legacy.batchCreatedNamed", { name }));
    } else {
      const batch = batchById(batchId);
      if (batch && isYoutubeBatch(batch)) {
        showToast(t("legacy.youtubeBatchNoFiles"));
        return;
      }
      await addToBatch(batchId, paths, recursive);
      await refreshLibrary();
      showToast(t("legacy.folderAddedToBatch", { name: selectedBatchLabel(batchId) }));
    }
  } catch (err) {
    showToast(err.message || String(err));
    await refreshLibrary();
  }
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
  const paths = Array.from(input.files || [])
    .map((f) => f.pywebviewFullPath || f.path)
    .filter((path) => path && isAbsolutePath(path));
  if (!paths.length && (input.files || []).length) {
    showToast("legacy.k442945");
  }
  return paths;
}

async function pickFolderPath() {
  if (window.pywebview && window.pywebview.api && window.pywebview.api.pick_folder) {
    const folder = await window.pywebview.api.pick_folder();
    return folder || "";
  }
  showToast("legacy.k379087");
  return "";
}

async function addFiles() {
  const paths = await pickFilePaths();
  if (!paths.length) {
    return;
  }
  await addPathsForCurrentTab(paths);
}

async function addFolder() {
  const folder = await pickFolderPath();
  if (!folder) {
    return;
  }
  const targetId = fileBatchTargetId();
  await openFolderAddModal([folder], targetId);
}

async function createEmptyBatch() {
  await openNewBatchModal();
}

export async function openNewBatchModal(onCreated) {
  const modal = document.getElementById("new-batch-modal");
  const nameEl = document.getElementById("new-batch-name");
  const addFilesEl = document.getElementById("new-batch-add-files");
  if (!modal || !nameEl) {
    showToast("common.restartApp");
    return null;
  }
  const stamp = new Date();
  nameEl.value = t("legacy.batchDefaultName", {
    date: stamp.toLocaleDateString(localeDateTag(), {
      day: "2-digit",
      month: "2-digit",
    }),
  });
  if (addFilesEl) {
    addFilesEl.checked = false;
  }
  modal.hidden = false;
  nameEl.focus();
  nameEl.select();
  return new Promise((resolve) => {
    modal.dataset.resolve = "pending";
    modal._resolve = resolve;
    if (onCreated) {
      modal._onCreated = onCreated;
    }
  });
}

export async function createBatchNamed(name, paths = null) {
  const batchName = (name || "").trim() || defaultBatchName([]);
  const batch = await api("/api/batches", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: batchName }),
  });
  if (paths?.length) {
    await addToBatch(batch.id, paths, false);
  }
  setSelectedBatch(batch.id);
  await refreshLibrary();
  showToast(t("legacy.batchCreatedNamed", { name: batchName }));
  return batch;
}

async function confirmNewBatchModal() {
  const modal = document.getElementById("new-batch-modal");
  const nameEl = document.getElementById("new-batch-name");
  const addFilesEl = document.getElementById("new-batch-add-files");
  if (!modal || !nameEl) {
    return;
  }
  const name = nameEl.value.trim();
  let paths = [];
  if (addFilesEl?.checked) {
    paths = await pickFilePaths();
  }
  modal.hidden = true;
  try {
    const batch = await createBatchNamed(name, paths.length ? paths : null);
    if (modal._onCreated) {
      modal._onCreated(batch);
    } else if (batch?.id != null) {
      navigate("legacy", { batchId: batch.id, tab: "batches" });
    }
    if (modal._resolve) {
      modal._resolve(batch);
      modal._resolve = null;
      modal._onCreated = null;
    }
  } catch (err) {
    showToast(err.message || String(err));
    if (modal._resolve) {
      modal._resolve(null);
      modal._resolve = null;
      modal._onCreated = null;
    }
  }
}

function closeNewBatchModal() {
  const modal = document.getElementById("new-batch-modal");
  if (modal) {
    modal.hidden = true;
    if (modal._resolve) {
      modal._resolve(null);
      modal._resolve = null;
      modal._onCreated = null;
    }
  }
}

function handleBatchTargetSelectChange() {
  if (!batchTargetSelectEl) {
    return;
  }
  const value = batchTargetSelectEl.value;
  if (value === BATCH_TARGET_NEW) {
    createEmptyBatch().catch((err) => showToast(err.message || String(err)));
    return;
  }
  const id = Number(value);
  if (Number.isFinite(id)) {
    setSelectedBatch(id);
    renderLibrary();
  }
}

async function deleteBatch(batchId) {
  const batch = batchById(batchId);
  const name = batch ? batch.name : String(batchId);
  if (!window.confirm(t("legacy.confirmDeleteBatchNamed", { name }))) {
    return;
  }
  await deleteBatchApi(batchId);
  if (selectedId != null) {
    const job = jobById(selectedId);
    if (!job) {
      selectedId = null;
      if (transcriptEl) {
        transcriptEl.value = "";
        transcriptEl.hidden = true;
      }
      if (transcriptHintEl) {
        transcriptHintEl.hidden = true;
      }
      if (saveBtn) {
        saveBtn.hidden = true;
      }
      if (speakersBtn) {
        speakersBtn.hidden = true;
      }
      if (exportActionsEl) {
        exportActionsEl.hidden = true;
      }
      if (speakerRenameEl) {
        speakerRenameEl.hidden = true;
      }
      if (playerEl) {
        playerEl.removeAttribute("src");
      }
      syncJobBanner(null);
    }
  }
}

function readBatchRulesFromForm() {
  return {
    speakers: document.getElementById("rule-speakers").checked,
    export: document.getElementById("rule-export").checked,
    export_fmt: document.getElementById("rule-export-fmt").value,
    export_dir_mode: document.getElementById("rule-export-dir-mode").value,
    export_dir: document.getElementById("rule-export-dir").value.trim(),
    skip_completed: document.getElementById("rule-skip-completed").checked,
    on_error: "continue",
  };
}

function writeBatchRulesToForm(rules = {}) {
  document.getElementById("rule-speakers").checked = Boolean(rules.speakers);
  document.getElementById("rule-export").checked = Boolean(rules.export);
  document.getElementById("rule-export-fmt").value = rules.export_fmt || "srt";
  document.getElementById("rule-export-dir-mode").value = rules.export_dir_mode || "beside_source";
  document.getElementById("rule-export-dir").value = rules.export_dir || "";
  document.getElementById("rule-skip-completed").checked = rules.skip_completed !== false;
  syncRuleExportDirUi();
}

function openBatchRulesModal(batchId) {
  if (batchId != null) {
    const batch = batchById(batchId);
    if (!batch) {
      return;
    }
    rulesBatchId = batchId;
    rulesDraftMode = false;
    writeBatchRulesToForm(batch.rules || {});
  } else {
    rulesBatchId = null;
    rulesDraftMode = true;
    writeBatchRulesToForm(pendingUploadRules || {});
  }
  batchRulesModal.hidden = false;
}

function closeBatchRulesModal() {
  batchRulesModal.hidden = true;
  if (!rulesDraftMode) {
    rulesBatchId = null;
  }
  rulesDraftMode = false;
}

function syncRuleExportDirUi() {
  const mode = document.getElementById("rule-export-dir-mode").value;
  document.getElementById("rule-export-dir-wrap").hidden = mode !== "fixed";
}

async function saveBatchRules() {
  const rules = readBatchRulesFromForm();
  if (rulesDraftMode) {
    pendingUploadRules = rules;
    rulesDraftMode = false;
    batchRulesModal.hidden = true;
    showToast("legacy.k878494");
    return;
  }
  if (rulesBatchId == null) {
    return;
  }
  await api(`/api/batches/${rulesBatchId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rules }),
  });
  closeBatchRulesModal();
  await refreshLibrary();
  showToast("legacy.k3520995");
}

function closeUploadTargetModal() {
  const modal = document.getElementById("upload-target-modal");
  if (!modal) {
    return;
  }
  modal.hidden = true;
  document.getElementById("upload-target-choice")?.removeAttribute("hidden");
  document.getElementById("upload-target-batch-form")?.setAttribute("hidden", "");
  pendingUploadPaths = [];
  pendingUploadRules = null;
  if (uploadTargetResolve) {
    uploadTargetResolve(null);
    uploadTargetResolve = null;
  }
}

async function confirmUploadAsOrphans() {
  const paths = [...pendingUploadPaths];
  if (!paths.length) {
    closeUploadTargetModal();
    return;
  }
  try {
    await addOrphanFiles(paths);
  } finally {
    closeUploadTargetModal();
  }
}

async function confirmUploadAsBatch() {
  const paths = [...pendingUploadPaths];
  const nameEl = document.getElementById("upload-target-batch-name");
  const name = (nameEl?.value || "").trim() || defaultBatchName(paths);
  closeUploadTargetModal();
  if (!paths.length) {
    return;
  }
  try {
    const batch = await api("/api/batches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, rules: pendingUploadRules || undefined }),
    });
    await addToBatch(batch.id, paths, false);
    setSelectedBatch(batch.id);
    await refreshLibrary();
    showToast(t("legacy.batchCreatedNamed", { name }));
    navigate("legacy", { batchId: batch.id, tab: "batches" });
  } catch (err) {
    showToast(err.message || String(err));
    await refreshLibrary();
  }
}

export async function resolveUploadTarget(paths) {
  const unique = [...new Set((paths || []).filter(Boolean))];
  if (!unique.length) {
    return;
  }
  if (unique.length === 1) {
    await addOrphanFiles(unique);
    return;
  }
  const modal = document.getElementById("upload-target-modal");
  const countEl = document.getElementById("upload-target-count");
  const nameEl = document.getElementById("upload-target-batch-name");
  if (!modal) {
    await addOrphanFiles(unique);
    return;
  }
  pendingUploadPaths = unique;
  pendingUploadRules = null;
  if (countEl) {
    countEl.textContent = t("legacy.filesSelectedWhere", { count: unique.length });
  }
  if (nameEl) {
    nameEl.value = defaultBatchName(unique);
  }
  document.getElementById("upload-target-choice")?.removeAttribute("hidden");
  document.getElementById("upload-target-batch-form")?.setAttribute("hidden", "");
  modal.hidden = false;
  return new Promise((resolve) => {
    uploadTargetResolve = resolve;
  });
}

async function archiveSelectedBatch() {
  if (ctxBatchId == null) {
    return;
  }
  const batch = batchById(ctxBatchId);
  const name = batch?.name || t("legacy.batchNumber", { id: ctxBatchId });
  if (!window.confirm(t("legacy.confirmArchiveBatchNamed", { name }))) {
    return;
  }
  await api(`/api/batches/${ctxBatchId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ archived: true }),
  });
  await refreshJobs();
  showToast("legacy.k474832");
  refreshLibraryViews();
}

async function unarchiveSelectedBatch() {
  if (ctxBatchId == null) {
    return;
  }
  await api(`/api/batches/${ctxBatchId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ archived: false }),
  });
  await refreshJobs();
  showToast("legacy.k2571148");
  refreshLibraryViews();
}

function refreshLibraryViews() {
  const route = getRoute();
  if (route === "dashboard") {
    import("./dashboard.js").then((m) => m.paintRecent());
  } else if (route === "legacy") {
    renderLibrary();
  } else if (route === "transcripts") {
    import("./transcripts.js").then((m) => m.renderTranscripts());
  } else if (route === "archive") {
    import("./archive.js").then((m) => m.renderArchive());
  } else if (route === "queue") {
    import("./queue.js").then((m) => m.renderQueue());
  }
}

async function saveSegments() {
  const jobId = getRoute() === "editor" ? window.__editorCurrentJobId?.() ?? selectedId : selectedId;
  if (jobId == null) {
    return;
  }
  const payload = {
    transcript: transcriptEl.value,
    expected_revision: segmentsRevision,
  };
  try {
    const res = await api(`/api/jobs/${jobId}/segments`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res?.segments_revision != null) {
      segmentsRevision = Number(res.segments_revision) || segmentsRevision;
    }
    window.__editorMarkDraftSaved?.();
    showToast("common.saved");
  } catch (err) {
    if (err.status === 409) {
      showToast(err.message || String(err));
      const job = await api(`/api/jobs/${jobId}`);
      segmentsRevision = Number(job.segments_revision) || segmentsRevision;
      if (!isEditingTranscript()) {
        renderTranscript(job.transcript || "");
      }
      return;
    }
    throw err;
  }
}

function sourceStem(sourcePath) {
  const base = (sourcePath || "").split(/[/\\]/).pop() || "transcript";
  return base.replace(/\.[^.]+$/, "") || "transcript";
}

function sourceDir(sourcePath) {
  return (sourcePath || "").replace(/[/\\][^/\\]+$/, "");
}

function closeExportModal() {
  if (!exportModal) {
    return;
  }
  exportModal.hidden = true;
  pendingExportJobs = null;
  exportTargetJobId = null;
  resetExportDirs("");
}

function createExportDirRow(value = "") {
  const row = document.createElement("div");
  row.className = "export-dir-row field-row";

  const input = document.createElement("input");
  input.type = "text";
  input.className = "export-dir-input";
  input.spellcheck = false;
  input.value = value;

  const browseBtn = document.createElement("button");
  browseBtn.type = "button";
  browseBtn.className = "btn-outline btn-compact";
  browseBtn.dataset.act = "browse";
  browseBtn.title = t("common.browse");
  browseBtn.setAttribute("aria-label", t("common.browse"));
  browseBtn.innerHTML = '<span class="material-symbols-outlined" aria-hidden="true">folder_open</span>';

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "btn-outline btn-compact export-dir-remove";
  removeBtn.dataset.act = "remove";
  removeBtn.title = t("common.delete");
  removeBtn.setAttribute("aria-label", t("common.delete"));
  removeBtn.innerHTML = '<span class="material-symbols-outlined" aria-hidden="true">close</span>';

  row.append(input, browseBtn, removeBtn);
  return row;
}

function syncExportDirRemoveButtons() {
  if (!exportDirsListEl) {
    return;
  }
  const rows = exportDirsListEl.querySelectorAll(".export-dir-row");
  const hideRemove = rows.length <= 1;
  rows.forEach((row) => {
    const removeBtn = row.querySelector('[data-act="remove"]');
    if (removeBtn) {
      removeBtn.hidden = hideRemove;
    }
  });
}

function addExportDirRow(value = "") {
  if (!exportDirsListEl) {
    return null;
  }
  const row = createExportDirRow(value);
  exportDirsListEl.appendChild(row);
  syncExportDirRemoveButtons();
  return row;
}

function resetExportDirs(initialPath = "") {
  if (!exportDirsListEl) {
    return;
  }
  exportDirsListEl.replaceChildren();
  addExportDirRow(initialPath);
}

function removeExportDirRow(row) {
  if (!exportDirsListEl || !row) {
    return;
  }
  if (exportDirsListEl.querySelectorAll(".export-dir-row").length <= 1) {
    return;
  }
  row.remove();
  syncExportDirRemoveButtons();
}

function collectExportDirectories() {
  if (!exportDirsListEl) {
    return [];
  }
  const seen = new Set();
  const unique = [];
  for (const input of exportDirsListEl.querySelectorAll(".export-dir-input")) {
    const value = (input.value || "").trim();
    if (!value) {
      continue;
    }
    const key = value.toLowerCase();
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    unique.push(value);
  }
  return unique;
}

async function browseExportFolderInput(inputEl) {
  if (!inputEl) {
    return;
  }
  if (window.pywebview?.api?.pick_folder) {
    const folder = await pickFolderWithGhostClickGuard(inputEl.value || "", exportModal);
    if (folder) {
      inputEl.value = folder;
    }
    return;
  }
  showToast("legacy.k4514159");
}

function currentExportFmt() {
  return (exportFmtEl?.value || "srt").toLowerCase();
}

function syncExportNameExtension() {
  if (pendingExportJobs || !exportNameEl) {
    return;
  }
  const fmt = currentExportFmt();
  const raw = (exportNameEl.value || "").trim() || "transcript";
  const stem = raw.replace(/\.[^.\\/]+$/, "") || "transcript";
  exportNameEl.value = `${stem}.${fmt}`;
}

function setExportModalMode(mode, count) {
  const nameField = document.getElementById("export-name-field");
  const hint = document.getElementById("export-batch-hint");
  const title = document.getElementById("export-title");
  const confirm = document.getElementById("export-confirm");
  const isBatch = mode === "batch";
  if (title) {
    title.textContent = isBatch ? t("legacy.k2384665") : t("common.export");
  }
  if (nameField) {
    nameField.hidden = isBatch;
  }
  if (hint) {
    hint.hidden = !isBatch;
    if (isBatch) {
      hint.textContent =
        t("legacy.exportWillSave", { count });
    }
  }
  if (confirm) {
    confirm.textContent = isBatch ? t("legacy.k6769186") : t("common.save");
  }
}

async function openExportModal() {
  let id = selectedId;
  if (id == null && getRoute() === "editor") {
    id = getEditorJobId();
  }
  if (id == null) {
    showToast("legacy.k9064548");
    return;
  }
  let job = jobById(id);
  if (!job) {
    try {
      job = await api(`/api/jobs/${id}`);
      upsertJobInStore(job);
    } catch {
      job = null;
    }
  }
  openJobExportModal(job);
}

function openJobExportModal(job) {
  if (!job) {
    showToast("legacy.k8638182");
    return;
  }
  if (job.status !== "completed") {
    showToast("legacy.k9486817");
    return;
  }
  if (!exportModal || !exportFmtEl || !exportNameEl || !exportDirsListEl) {
    showToast("common.restartApp");
    return;
  }
  exportTargetJobId = job.id;
  pendingExportJobs = null;
  setExportModalMode("single");
  exportFmtEl.value = "srt";
  exportNameEl.value = `${sourceStem(job.source_path)}.srt`;
  resetExportDirs(sourceDir(job.source_path));
  exportModal.hidden = false;
  requestAnimationFrame(() => {
    exportNameEl?.focus();
    exportNameEl?.select();
  });
}

function openBatchExportModal(jobsToExport) {
  const completed = (jobsToExport || []).filter((job) => job.status === "completed");
  if (!completed.length) {
    showToast("legacy.k1604307");
    return;
  }
  if (!exportModal || !exportFmtEl || !exportDirsListEl) {
    showToast("common.restartApp");
    return;
  }
  exportTargetJobId = null;
  pendingExportJobs = completed;
  setExportModalMode("batch", completed.length);
  exportFmtEl.value = "srt";
  resetExportDirs(sourceDir(completed[0].source_path));
  exportModal.hidden = false;
}

function joinExportPath(directory, filename) {
  const name = String(filename || "").split(/[/\\]/).pop();
  const dir = String(directory || "").replace(/[/\\]+$/, "");
  if (!dir) {
    return name;
  }
  return `${dir}\\${name}`;
}

function uniqueExportFilename(stem, fmt, used) {
  const base = (stem || "transcript").trim() || "transcript";
  let index = 1;
  while (true) {
    const name = index === 1 ? `${base}.${fmt}` : `${base}_${index}.${fmt}`;
    const key = name.toLowerCase();
    if (!used.has(key)) {
      used.add(key);
      return name;
    }
    index += 1;
  }
}

async function confirmExport() {
  const fmt = currentExportFmt();
  const directories = collectExportDirectories();
  if (!directories.length) {
    showToast("legacy.k6393359");
    return;
  }
  if (pendingExportJobs) {
    const jobs = pendingExportJobs;
    closeExportModal();
    let totalOk = 0;
    const errors = [];
    for (const directory of directories) {
      const used = new Set();
      const result = await runEach(jobs, async (job) => {
        const filename = uniqueExportFilename(sourceStem(job.source_path), fmt, used);
        const path = joinExportPath(directory, filename);
        await api(`/api/jobs/${job.id}/export`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ fmt, path }),
        });
      });
      totalOk += result.ok;
      errors.push(...result.errors);
    }
    toastBulkResult(totalOk, errors, t("legacy.exportedCount", { count: totalOk }));
    await refreshJobs();
    return;
  }
  if (selectedId == null && exportTargetJobId == null) {
    return;
  }
  syncExportNameExtension();
  const filename = (exportNameEl?.value || "").trim();
  if (!filename) {
    showToast("legacy.k9791863");
    return;
  }
  const jobId = exportTargetJobId ?? selectedId;
  closeExportModal();
  const exportedPaths = [];
  const errors = [];
  for (const directory of directories) {
    const path = joinExportPath(directory, filename);
    try {
      const result = await api(`/api/jobs/${jobId}/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fmt, path }),
      });
      exportedPaths.push(result.path || path);
    } catch (err) {
      errors.push(err.message || String(err));
    }
  }
  if (!exportedPaths.length) {
    showToast(errors[0] || t("legacy.k9779480"));
    return;
  }
  const exportedPath = exportedPaths[exportedPaths.length - 1];
  if (directories.length > 1) {
    showToast(t("legacy.savedToFolders", { count: exportedPaths.length }));
  } else {
    showToast(t("legacy.savedToPath", { path: exportedPath }));
  }
  window.dispatchEvent(
    new CustomEvent("gigaam:job-exported", {
      detail: { jobId, path: exportedPath, paths: exportedPaths },
    })
  );
  try {
    await api(`/api/jobs/${jobId}/last-export-paths`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paths: exportedPaths }),
    });
  } catch (err) {
    showToast(err.message || String(err));
  }
  await refreshJobs();
  const editorJobId = getEditorJobId();
  if ((getRoute() === "editor" && editorJobId === jobId) || selectedId === jobId) {
    const job = await selectJob(jobId);
    if (exportedPaths.length > 1) {
      syncExportActions(job, exportedPaths);
    }
  }
}

async function exportSelected() {
  await openExportModal();
}

async function openLocalPath(path, reveal) {
  const normalized = String(path || "").trim();
  if (!normalized) {
    showToast("legacy.k3235582");
    return;
  }
  if (window.pywebview?.api?.open_path) {
    try {
      await window.pywebview.api.open_path(normalized, reveal);
      return;
    } catch (err) {
      try {
        await api("/api/open-path", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: normalized, reveal }),
        });
        return;
      } catch (fallbackErr) {
        showToast(fallbackErr.message || err.message || String(fallbackErr));
        throw fallbackErr;
      }
    }
  }
  try {
    await api("/api/open-path", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: normalized, reveal }),
    });
  } catch (err) {
    showToast(err.message || String(err));
    throw err;
  }
}

function firstBatchExportPath(batch) {
  const job = (batch?.jobs || []).find((item) => item.last_export_path);
  return job ? job.last_export_path : "";
}

async function openSavedExport(reveal) {
  const paths = await resolveExportOpenPaths();
  if (!paths.length) {
    showToast("legacy.k8610333");
    return;
  }
  let ok = 0;
  const errors = [];
  for (const path of paths) {
    try {
      await openLocalPath(path, reveal);
      ok += 1;
    } catch (err) {
      errors.push(err.message || String(err));
    }
  }
  if (ok === 0) {
    showToast(errors[0] || t("legacy.k3235582"));
    return;
  }
  if (errors.length) {
    showToast(t("legacy.exportOpenPartial", { ok, total: paths.length }));
  }
}

async function openSourceFolder(jobId) {
  const job = jobId == null ? null : jobById(jobId);
  const path = job && job.source_path;
  if (!path) {
    showToast("legacy.k7484426");
    return;
  }
  await openLocalPath(path, true);
}

async function openBatchSavedExport(batchId, reveal) {
  const path = firstBatchExportPath(batchById(batchId));
  if (!path) {
    showToast("legacy.k7540563");
    return;
  }
  await openLocalPath(path, reveal);
}

async function transcribeRangeBody() {
  const editor = document.getElementById("view-editor");
  if (!editor?.classList.contains("is-active")) {
    return {};
  }
  const player = document.getElementById("player");
  const durationMs = player?.duration ? player.duration * 1000 : null;
  return readTranscribeRange(durationMs);
}

async function startSelected() {
  if (selectedId == null) {
    showToast("legacy.k9064548");
    return;
  }
  let body = {};
  try {
    body = await transcribeRangeBody();
  } catch (err) {
    showToast(err.message || String(err));
    return;
  }
  await api(`/api/jobs/${selectedId}/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await selectJob(selectedId);
  await refreshJobs();
}

async function retranscribeSelected() {
  if (selectedId == null) {
    return;
  }
  let body = {};
  try {
    body = await transcribeRangeBody();
  } catch (err) {
    showToast(err.message || String(err));
    return;
  }
  await api(`/api/jobs/${selectedId}/retranscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await selectJob(selectedId);
  await refreshJobs();
}

async function cancelSelected() {
  if (selectedId == null) {
    return;
  }
  await api(`/api/jobs/${selectedId}/cancel`, { method: "POST" });
  await refreshJobs();
  if (selectedId != null) {
    await selectJob(selectedId);
  }
  refreshLibraryViews();
}

async function archiveSelectedJob() {
  if (selectedId == null) {
    return;
  }
  const job = jobById(selectedId);
  const name = job ? job.source_path.split(/[/\\]/).pop() : String(selectedId);
  if (!window.confirm(t("legacy.confirmArchiveItem", { name }))) {
    return;
  }
  await api(`/api/jobs/${selectedId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ archived: true }),
  });
  await refreshJobs();
  showToast("legacy.k8505079");
  refreshLibraryViews();
}

async function unarchiveSelectedJob() {
  if (selectedId == null) {
    return;
  }
  await api(`/api/jobs/${selectedId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ archived: false }),
  });
  await refreshJobs();
  showToast("legacy.k7003274");
  refreshLibraryViews();
}

async function deleteSelected(id) {
  const jobId = id == null ? selectedId : id;
  if (jobId == null) {
    return;
  }
  const job = jobById(jobId);
  const name = job ? job.source_path.split(/[/\\]/).pop() : String(jobId);
  if (!window.confirm(t("legacy.confirmDeleteItem", { name }))) {
    return;
  }
  await api(`/api/jobs/${jobId}`, { method: "DELETE" });
  if (selectedId === jobId) {
    selectedId = null;
    if (transcriptEl) {
      transcriptEl.value = "";
      transcriptEl.hidden = true;
    }
    if (transcriptHintEl) {
      transcriptHintEl.hidden = true;
    }
    if (saveBtn) {
      saveBtn.hidden = true;
    }
    if (speakersBtn) {
      speakersBtn.hidden = true;
    }
    if (exportActionsEl) {
      exportActionsEl.hidden = true;
    }
    if (speakerRenameEl) {
      speakerRenameEl.hidden = true;
    }
    if (playerEl) {
      playerEl.removeAttribute("src");
    }
    syncJobBanner(null);
  }
  await refreshJobs();
}

function hideContextMenu() {
  ctxMenu.hidden = true;
  ctxJobId = null;
  ctxBatchId = null;
}

function openBatchContextMenu(event, batch) {
  event.preventDefault();
  ctxBatchId = batch.id;
  ctxJobId = null;
  const running = Boolean(batch.running);
  ctxMenu.querySelector('[data-act="batch-start"]').hidden = running || !(batch.total_count > 0);
  ctxMenu.querySelector('[data-act="batch-pause"]').hidden = !running;
  ctxMenu.querySelector('[data-act="batch-cancel"]').hidden = !running;
  ctxMenu.querySelector('[data-act="batch-rules"]').hidden = false;
  ctxMenu.querySelector('[data-act="batch-add"]').hidden = false;
  ctxMenu.querySelector('[data-act="batch-add-folder"]').hidden = false;
  ctxMenu.querySelector('[data-act="batch-delete"]').hidden = running;
  ctxMenu.querySelector('[data-act="batch-archive"]').hidden = running || Boolean(batch.archived);
  ctxMenu.querySelector('[data-act="batch-unarchive"]').hidden = !Boolean(batch.archived);
  const hasCompleted = (batch.jobs || []).some((job) => job.status === "completed");
  const hasExport = (batch.jobs || []).some((job) => job.last_export_path);
  ctxMenu.querySelector('[data-act="batch-export"]').hidden = !hasCompleted;
  ctxMenu.querySelector('[data-act="batch-open-export"]').hidden = !hasExport;
  ctxMenu.querySelector('[data-act="batch-open-export-folder"]').hidden = !hasExport;
  ctxMenu.querySelector('[data-act="remove-from-batch"]').hidden = true;
  ctxMenu.querySelector('[data-act="transcribe"]').hidden = true;
  ctxMenu.querySelector('[data-act="export"]').hidden = true;
  ctxMenu.querySelector('[data-act="open-export"]').hidden = true;
  ctxMenu.querySelector('[data-act="open-export-folder"]').hidden = true;
  ctxMenu.querySelector('[data-act="open-source-folder"]').hidden = true;
  ctxMenu.querySelector('[data-act="archive"]').hidden = true;
  ctxMenu.querySelector('[data-act="unarchive"]').hidden = true;
  ctxMenu.querySelector('[data-act="speakers"]').hidden = true;
  ctxMenu.querySelector('[data-act="retranscribe"]').hidden = true;
  ctxMenu.querySelector('[data-act="cancel"]').hidden = true;
  ctxMenu.querySelector('[data-act="delete"]').hidden = true;
  ctxMenu.hidden = false;
  ctxMenu.style.left = `${event.clientX}px`;
  ctxMenu.style.top = `${event.clientY}px`;
}

function openContextMenu(event, job, batchId) {
  event.preventDefault();
  ctxJobId = job.id;
  ctxBatchId = batchId;
  selectedId = job.id;
  const completed = job.status === "completed";
  const active =
    job.status === "queued" ||
    job.status === "running" ||
    job.speakers_running ||
    job.engine_starting;
  const canStart = ["idle", "failed", "cancelled"].includes(job.status);
  ctxMenu.querySelector('[data-act="batch-start"]').hidden = true;
  ctxMenu.querySelector('[data-act="batch-pause"]').hidden = true;
  ctxMenu.querySelector('[data-act="batch-cancel"]').hidden = true;
  ctxMenu.querySelector('[data-act="batch-rules"]').hidden = true;
  ctxMenu.querySelector('[data-act="batch-add"]').hidden = true;
  ctxMenu.querySelector('[data-act="batch-add-folder"]').hidden = true;
  ctxMenu.querySelector('[data-act="batch-delete"]').hidden = true;
  ctxMenu.querySelector('[data-act="batch-archive"]').hidden = true;
  ctxMenu.querySelector('[data-act="batch-unarchive"]').hidden = true;
  ctxMenu.querySelector('[data-act="batch-export"]').hidden = true;
  ctxMenu.querySelector('[data-act="batch-open-export"]').hidden = true;
  ctxMenu.querySelector('[data-act="batch-open-export-folder"]').hidden = true;
  ctxMenu.querySelector('[data-act="remove-from-batch"]').hidden = batchId == null;
  ctxMenu.querySelector('[data-act="transcribe"]').hidden = !canStart;
  ctxMenu.querySelector('[data-act="export"]').hidden = !completed;
  ctxMenu.querySelector('[data-act="open-export"]').hidden = !job.last_export_path;
  ctxMenu.querySelector('[data-act="open-export-folder"]').hidden = !job.last_export_path;
  ctxMenu.querySelector('[data-act="open-source-folder"]').hidden = !job.source_path || isYoutubeJob(job);
  ctxMenu.querySelector('[data-act="archive"]').hidden = !completed || Boolean(job.archived);
  ctxMenu.querySelector('[data-act="unarchive"]').hidden = !Boolean(job.archived);
  ctxMenu.querySelector('[data-act="speakers"]').hidden = !completed || isYoutubeJob(job);
  ctxMenu.querySelector('[data-act="retranscribe"]').hidden = active || isYoutubeJob(job);
  const cancelAct = ctxMenu.querySelector('[data-act="cancel"]');
  cancelAct.hidden = !active;
  if (!cancelAct.hidden) {
    cancelAct.textContent = t("common.stop");
  }
  ctxMenu.querySelector('[data-act="delete"]').hidden = false;
  ctxMenu.hidden = false;
  ctxMenu.style.left = `${event.clientX}px`;
  ctxMenu.style.top = `${event.clientY}px`;
}

function bindClick(id, handler) {
  const el = document.getElementById(id);
  if (el) {
    el.addEventListener("click", handler);
  }
}

function bindLegacyEvents() {
  bindClick("btn-add-files", () =>
    addFiles().catch((err) => showToast(err.message || String(err)))
  );
  bindClick("btn-batch-add-files", () =>
    addFiles().catch((err) => showToast(err.message || String(err)))
  );
  bindClick("btn-batch-add-folder", () =>
    addFolder().catch((err) => showToast(err.message || String(err)))
  );
  bindClick("btn-batch-new", () =>
    createEmptyBatch().catch((err) => showToast(err.message || String(err)))
  );
  if (batchTargetSelectEl) {
    batchTargetSelectEl.addEventListener("change", handleBatchTargetSelectChange);
  }
  document.getElementById("btn-transcribe")?.addEventListener("click", () =>
    startSelected().catch((err) => showToast(err.message || String(err)))
  );
  document.getElementById("btn-topbar-transcribe")?.addEventListener("click", () =>
    startSelected().catch((err) => showToast(err.message || String(err)))
  );
  document.getElementById("btn-topbar-stop")?.addEventListener("click", () =>
    cancelSelected().catch((err) => showToast(err.message || String(err)))
  );
  document.getElementById("btn-export")?.addEventListener("click", () =>
    exportSelected().catch((err) => showToast(err.message || String(err)))
  );
  document.getElementById("btn-retranscribe")?.addEventListener("click", () =>
    retranscribeSelected().catch((err) => showToast(err.message || String(err)))
  );
  document.getElementById("btn-cancel")?.addEventListener("click", () =>
    cancelSelected().catch((err) => showToast(err.message || String(err)))
  );
  speakersBtn?.addEventListener("click", () => runSpeakers());
  saveBtn?.addEventListener("click", () =>
    saveSegments().catch((err) => showToast(err.message || String(err)))
  );
  transcriptEl?.addEventListener("click", () => seekFromTranscriptClick());

  document.getElementById("export-close")?.addEventListener("click", () => closeExportModal());
  document.getElementById("export-cancel")?.addEventListener("click", () => closeExportModal());
  document.getElementById("export-confirm")?.addEventListener("click", () =>
    confirmExport().catch((err) => showToast(err.message || String(err)))
  );
  exportDirAddBtn?.addEventListener("click", () => {
    const row = addExportDirRow("");
    const input = row?.querySelector(".export-dir-input");
    input?.focus();
  });
  exportDirsListEl?.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-act]");
    if (!btn) {
      return;
    }
    const row = btn.closest(".export-dir-row");
    if (btn.dataset.act === "browse") {
      const input = row?.querySelector(".export-dir-input");
      browseExportFolderInput(input).catch((err) => showToast(err.message || String(err)));
      return;
    }
    if (btn.dataset.act === "remove") {
      removeExportDirRow(row);
    }
  });
  exportFmtEl?.addEventListener("change", () => syncExportNameExtension());
  document.getElementById("btn-open-export")?.addEventListener("click", () =>
    openSavedExport(false).catch((err) => showToast(err.message || String(err)))
  );
  document.getElementById("btn-open-export-folder")?.addEventListener("click", () =>
    openSavedExport(true).catch((err) => showToast(err.message || String(err)))
  );

  ctxMenu?.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-act]");
    if (!btn) {
      return;
    }
    const act = btn.dataset.act;
    const jobId = ctxJobId;
    const batchId = ctxBatchId;
    hideContextMenu();
    if (jobId != null) {
      selectedId = jobId;
    }
    const run = {
      transcribe: startSelected,
      export: exportSelected,
      "open-export": () => openSavedExport(false),
      "open-export-folder": () => openSavedExport(true),
      "open-source-folder": () => openSourceFolder(jobId),
      archive: archiveSelectedJob,
      unarchive: unarchiveSelectedJob,
      speakers: runSpeakers,
      retranscribe: retranscribeSelected,
      cancel: cancelSelected,
      delete: () => deleteSelected(jobId),
      "batch-start": () => startBatch(batchId),
      "batch-pause": () => pauseBatch(batchId),
      "batch-cancel": () => cancelBatch(batchId),
      "batch-rules": () => openBatchRulesModal(batchId),
      "batch-add": () => {
        setSelectedBatch(batchId);
        if (getRoute() === "legacy") {
          switchLegacyTab("batches");
        }
        return addFiles();
      },
      "batch-add-folder": () => {
        setSelectedBatch(batchId);
        if (getRoute() === "legacy") {
          switchLegacyTab("batches");
        }
        return addFolder();
      },
      "batch-delete": () => deleteBatch(batchId),
      "batch-archive": archiveSelectedBatch,
      "batch-unarchive": unarchiveSelectedBatch,
      "batch-export": () => {
        const batch = batchById(batchId);
        openBatchExportModal(batch?.jobs || []);
      },
      "batch-open-export": () => openBatchSavedExport(batchId, false),
      "batch-open-export-folder": () => openBatchSavedExport(batchId, true),
      "remove-from-batch": async () => {
        await api(`/api/jobs/${jobId}/remove-from-batch`, { method: "POST" });
        await refreshLibrary();
      },
    }[act];
    if (run) {
      Promise.resolve(run()).catch((err) => showToast(err.message || String(err)));
    }
  });

  document.addEventListener("click", (event) => {
    if (ctxMenu && !ctxMenu.hidden && !ctxMenu.contains(event.target)) {
      hideContextMenu();
    }
  });
}

let legacyDropBound = false;

function bindLegacyDrop() {
  if (legacyDropBound) {
    return;
  }
  legacyDropBound = true;
  window.addEventListener("dragover", (e) => {
    e.preventDefault();
    document.body.classList.add("is-drop");
  });
  window.addEventListener("dragleave", () => document.body.classList.remove("is-drop"));
  window.addEventListener("drop", (e) => {
    e.preventDefault();
    document.body.classList.remove("is-drop");
    if (window.pywebview) {
      return;
    }
    const paths = pathsFromDrop(e);
    if (!paths.length) {
      showToast("dashboard.dropNoPath");
      return;
    }
    enqueueDropped(paths).catch((err) => showToast(err.message || String(err)));
  });
}

let legacyInitialized = false;
let editorRefreshHook = null;

export function setEditorRefreshHook(fn) {
  editorRefreshHook = fn;
}

export function initLegacyWorkspace() {
  if (legacyInitialized) {
    return;
  }
  legacyInitialized = true;

  bindLegacyEvents();
  bindLegacyDrop();

  setLibraryRefreshHook(() => {
    syncLocalLibraryState();
    syncBatchTargetSelect();
    renderLibrary();
    syncPoll();
    if (getRoute() === "dashboard") {
      import("./dashboard.js").then((m) => m.paintRecent());
    }
  });
  setLibrarySelectionHook(() => {
    syncLocalLibraryState();
    syncBatchTargetSelect();
  });

  function pruneExpandedLegacyBatches() {
    syncLocalLibraryState();
    const valid = new Set(batches.map((batch) => batch.id));
    let changed = false;
    for (const id of [...expandedLegacyBatches]) {
      if (!valid.has(id)) {
        expandedLegacyBatches.delete(id);
        changed = true;
      }
    }
    if (changed) {
      saveExpandedLegacyBatches();
    }
  }

  window.enqueueDropped = enqueueDropped;

  document.querySelectorAll("#view-legacy .legacy-tab").forEach((btn) => {
    btn.addEventListener("click", () => switchLegacyTab(btn.dataset.tab));
  });

  refreshLibrary()
    .then(() => {
      pruneExpandedLegacyBatches();
    })
    .catch((err) => reportError(t("libraryStore.loadFailed"), err));
  syncBatchTargetSelect();
  switchLegacyTab("files");

  if (folderAddModal) {
    const folderAddCancel = document.getElementById("folder-add-cancel");
    const folderAddConfirm = document.getElementById("folder-add-confirm");
    if (folderAddCancel) {
      folderAddCancel.addEventListener("click", closeFolderAddModal);
    }
    if (folderAddConfirm) {
      folderAddConfirm.addEventListener("click", () =>
        confirmFolderAdd().catch((err) => showToast(err.message || String(err)))
      );
    }
    folderAddModal.addEventListener("click", (event) => {
      if (event.target === folderAddModal) {
        closeFolderAddModal();
      }
    });
  }

  const newBatchModal = document.getElementById("new-batch-modal");
  if (newBatchModal) {
    document.getElementById("new-batch-cancel")?.addEventListener("click", closeNewBatchModal);
    document.getElementById("new-batch-confirm")?.addEventListener("click", () =>
      confirmNewBatchModal().catch((err) => showToast(err.message || String(err)))
    );
    newBatchModal.addEventListener("click", (event) => {
      if (event.target === newBatchModal) {
        closeNewBatchModal();
      }
    });
  }

  const moveToBatchModal = document.getElementById("move-to-batch-modal");
  if (moveToBatchModal) {
    document.getElementById("move-to-batch-cancel")?.addEventListener("click", closeMoveToBatchModal);
    document.getElementById("move-to-batch-confirm")?.addEventListener("click", () =>
      confirmMoveToBatch().catch((err) => showToast(err.message || String(err)))
    );
    document.getElementById("move-to-batch-select")?.addEventListener("change", syncMoveToBatchNameWrap);
    moveToBatchModal.addEventListener("click", (event) => {
      if (event.target === moveToBatchModal) {
        closeMoveToBatchModal();
      }
    });
  }

  const uploadTargetModal = document.getElementById("upload-target-modal");
  if (uploadTargetModal) {
    document.getElementById("upload-target-orphans")?.addEventListener("click", () =>
      confirmUploadAsOrphans().catch((err) => showToast(err.message || String(err)))
    );
    document.getElementById("upload-target-batch")?.addEventListener("click", () => {
      document.getElementById("upload-target-choice")?.setAttribute("hidden", "");
      document.getElementById("upload-target-batch-form")?.removeAttribute("hidden");
    });
    document.getElementById("upload-target-back")?.addEventListener("click", () => {
      document.getElementById("upload-target-choice")?.removeAttribute("hidden");
      document.getElementById("upload-target-batch-form")?.setAttribute("hidden", "");
    });
    document.getElementById("upload-target-batch-rules")?.addEventListener("click", () =>
      openBatchRulesModal(null)
    );
    document.getElementById("upload-target-batch-confirm")?.addEventListener("click", () =>
      confirmUploadAsBatch().catch((err) => showToast(err.message || String(err)))
    );
    document.getElementById("upload-target-cancel")?.addEventListener("click", closeUploadTargetModal);
    uploadTargetModal.addEventListener("click", (event) => {
      if (event.target === uploadTargetModal) {
        closeUploadTargetModal();
      }
    });
  }

  if (batchRulesModal) {
    const batchRulesCancel = document.getElementById("batch-rules-cancel");
    const batchRulesSave = document.getElementById("batch-rules-save");
    if (batchRulesCancel) {
      batchRulesCancel.addEventListener("click", closeBatchRulesModal);
    }
    if (batchRulesSave) {
      batchRulesSave.addEventListener("click", () =>
        saveBatchRules().catch((err) => showToast(err.message || String(err)))
      );
    }
    const ruleExportDirMode = document.getElementById("rule-export-dir-mode");
    if (ruleExportDirMode) {
      ruleExportDirMode.addEventListener("change", syncRuleExportDirUi);
    }
    const ruleExportBrowse = document.getElementById("rule-export-browse");
    if (ruleExportBrowse) {
      ruleExportBrowse.addEventListener("click", async () => {
        const dirEl = document.getElementById("rule-export-dir");
        const folder = await pickFolderWithGhostClickGuard(dirEl?.value || "", batchRulesModal);
        if (folder && dirEl) {
          dirEl.value = folder;
        }
      });
    }
    batchRulesModal.addEventListener("click", (event) => {
      if (event.target !== batchRulesModal || isModalBackdropSuppressed()) {
        return;
      }
      closeBatchRulesModal();
    });
  }
}

export function onLegacyShow(params = {}) {
  refreshLibrary()
    .then(() => {
      if (params.tab === "batches" || params.batchId != null) {
        switchLegacyTab("batches");
      } else if (params.tab === "files") {
        switchLegacyTab("files");
      }
      if (params.batchId != null) {
        expandLegacyBatch(params.batchId);
        setSelectedBatch(params.batchId);
      }
      renderLibrary();
    })
    .catch((err) => reportError(t("legacy.k6072561"), err));
}

export async function addPathsForDashboard(target, paths) {
  const unique = [...new Set((paths || []).filter(Boolean))];
  if (!unique.length) {
    return;
  }
  const onlyFolders = unique.every(pathLooksLikeFolder);
  if (onlyFolders) {
    await openFolderAddModal(unique, fileBatchTargetId());
    return;
  }
  if (unique.some(pathLooksLikeFolder)) {
    showToast("legacy.k6822704");
    return;
  }
  if (target === "batch") {
    const targetId = fileBatchTargetId();
    if (targetId == null) {
      const batch = await createBatchNamed(defaultBatchName(unique), unique);
      if (batch?.id != null) {
        navigate("legacy", { batchId: batch.id, tab: "batches" });
      }
      return;
    }
    await addFilesToSelectedBatch(unique, targetId);
  } else {
    await resolveUploadTarget(unique);
  }
}

export {
  refreshLibrary,
  addOrphanFiles,
  addFiles,
  addFolder,
  createEmptyBatch,
  selectJob,
  deleteBatch,
  openBatchRulesModal,
  openFolderAddModal,
  openContextMenu,
  openBatchContextMenu,
  openBatchExportModal,
  openJobExportModal,
  openLocalPath,
  uniqueSpeakers,
  archiveSelectedJob,
  unarchiveSelectedJob,
  pickFilePaths,
  pickFolderPath,
};
