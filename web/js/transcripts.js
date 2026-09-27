import { showToast } from "./api.js";
import { reportError } from "./errors.js";
import { getLibrarySnapshot, jobStatusLabel, jobStatusTone } from "./library-store.js";
import {
  refreshLibrary,
  openContextMenu,
  openBatchContextMenu,
  pruneLibrarySelectedKeys,
  runJobsBulkAction,
  runBatchesBulkAction,
} from "./legacy.js";
import { getRoute, navigate } from "./router.js";
import { isTranscriptJob, isTranscriptBatch } from "./library-utils.js";
import { mountLibraryTable } from "./library-table.js";
import { t } from "./i18n.js";

function transcriptsFileBulk() {
  return [
    ["archive", t("transcripts.toArchive")],
    ["export", t("common.export")],
    ["delete", t("common.delete")],
  ];
}

function transcriptsBatchBulk() {
  return [
    ["archive", t("transcripts.toArchive")],
    ["export", t("common.export")],
    ["delete", t("common.delete")],
  ];
}

let transcriptsBound = false;
let activeTab = "files";
const expandedBatches = new Set();
const selectedFileKeys = new Set();
const selectedBatchKeys = new Set();

let filesWrap = null;
let batchesWrap = null;

function applyTranscriptsTabUi(tab) {
  activeTab = tab === "batches" ? "batches" : "files";
  document.querySelectorAll("#view-transcripts .legacy-tab").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.tab === activeTab);
  });
  if (filesWrap) {
    filesWrap.hidden = activeTab !== "files";
  }
  if (batchesWrap) {
    batchesWrap.hidden = activeTab !== "batches";
  }
}

function toggleExpandedBatch(batchId) {
  if (expandedBatches.has(batchId)) {
    expandedBatches.delete(batchId);
  } else {
    expandedBatches.add(batchId);
  }
  renderTranscripts();
}

function selectedJobsFromKeys(keys, jobs) {
  return jobs.filter((job) => keys.has(`job:${job.id}`));
}

function selectedBatchesFromKeys(keys, batchList) {
  return batchList.filter((batch) => keys.has(`batch:${batch.id}`));
}

function renderTranscriptsFiles() {
  if (!filesWrap) {
    return;
  }
  const { orphans } = getLibrarySnapshot();
  const jobs = orphans.filter(isTranscriptJob);
  pruneLibrarySelectedKeys(selectedFileKeys, new Set(jobs.map((job) => `job:${job.id}`)));

  mountLibraryTable(filesWrap, {
    storageKey: "transcripts-files",
    jobs,
    batches: [],
    emptyMessage:
      t("transcripts.emptyFiles"),
    jobStatusLabel,
    jobStatusTone,
    expandedBatches,
    onExpandChange: () => renderTranscripts(),
    onJobClick: (job) => navigate("editor", { jobId: job.id }),
    onJobContextMenu: (event, job, batchId) => openContextMenu(event, job, batchId),
    onBatchClick: () => {},
    onBatchContextMenu: () => {},
    selectable: true,
    selectedKeys: selectedFileKeys,
    bulkActions: transcriptsFileBulk(),
    onBulkAction: (action) =>
      runJobsBulkAction(selectedJobsFromKeys(selectedFileKeys, jobs), action, {
        onClear: () => selectedFileKeys.clear(),
      }).catch((err) => showToast(err.message || String(err))),
  });
}

function renderTranscriptsBatches() {
  if (!batchesWrap) {
    return;
  }
  const { batches } = getLibrarySnapshot();
  const batchList = batches.filter(isTranscriptBatch);
  pruneLibrarySelectedKeys(selectedBatchKeys, new Set(batchList.map((batch) => `batch:${batch.id}`)));

  mountLibraryTable(batchesWrap, {
    storageKey: "transcripts-batches",
    jobs: [],
    batches: batchList,
    emptyMessage:
      t("transcripts.emptyBatches"),
    jobStatusLabel,
    jobStatusTone,
    expandedBatches,
    onExpandChange: () => renderTranscripts(),
    onJobClick: (job) => navigate("editor", { jobId: job.id }),
    onJobContextMenu: (event, job, batchId) => openContextMenu(event, job, batchId),
    onBatchClick: (batch) => toggleExpandedBatch(batch.id),
    onBatchContextMenu: (event, batch) => openBatchContextMenu(event, batch),
    selectable: true,
    selectedKeys: selectedBatchKeys,
    bulkActions: transcriptsBatchBulk(),
    onBulkAction: (action) =>
      runBatchesBulkAction(selectedBatchesFromKeys(selectedBatchKeys, batchList), action, {
        onClear: () => selectedBatchKeys.clear(),
      }).catch((err) => showToast(err.message || String(err))),
  });
}

export function renderTranscripts() {
  if (activeTab === "batches") {
    renderTranscriptsBatches();
  } else {
    renderTranscriptsFiles();
  }
}

export async function refreshTranscripts() {
  await refreshLibrary();
  if (getRoute() === "transcripts") {
    renderTranscripts();
  }
}

export function initTranscripts() {
  if (transcriptsBound) {
    return;
  }
  transcriptsBound = true;
  filesWrap = document.getElementById("transcripts-files-wrap");
  batchesWrap = document.getElementById("transcripts-batches-wrap");
  document.querySelectorAll("#view-transcripts .legacy-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      navigate("transcripts", { tab: btn.dataset.tab });
    });
  });
}

export function onTranscriptsShow(params = {}) {
  applyTranscriptsTabUi(params.tab === "batches" ? "batches" : "files");
  refreshTranscripts().catch((err) => reportError(t("transcripts.title"), err));
}
