import { showToast } from "./api.js";
import { reportError } from "./errors.js";
import { getLibrarySnapshot } from "./library-store.js";
import {
  refreshLibrary,
  openContextMenu,
  openBatchContextMenu,
  pruneLibrarySelectedKeys,
  runJobsBulkAction,
  runBatchesBulkAction,
} from "./legacy.js";
import { getRoute, navigate } from "./router.js";
import { isArchivedOrphan, isArchivedBatch } from "./library-utils.js";
import { mountLibraryTable } from "./library-table.js";
import { t } from "./i18n.js";

function archiveFileBulk() {
  return [
    ["unarchive", t("archive.unarchive")],
    ["export", t("common.export")],
    ["delete", t("common.delete")],
  ];
}

function archiveBatchBulk() {
  return [
    ["unarchive", t("archive.unarchive")],
    ["export", t("common.export")],
    ["delete", t("common.delete")],
  ];
}

let archiveBound = false;
let activeTab = "files";
const expandedBatches = new Set();
const selectedFileKeys = new Set();
const selectedBatchKeys = new Set();

let filesWrap = null;
let batchesWrap = null;

function archivedJobStatusLabel() {
  return t("jobStatus.archived");
}

function archivedJobStatusTone() {
  return "done";
}

function applyArchiveTabUi(tab) {
  activeTab = tab === "batches" ? "batches" : "files";
  document.querySelectorAll("#view-archive .legacy-tab").forEach((btn) => {
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
  renderArchive();
}

function selectedJobsFromKeys(keys, jobs) {
  return jobs.filter((job) => keys.has(`job:${job.id}`));
}

function selectedBatchesFromKeys(keys, batchList) {
  return batchList.filter((batch) => keys.has(`batch:${batch.id}`));
}

function renderArchiveFiles() {
  if (!filesWrap) {
    return;
  }
  const { orphans } = getLibrarySnapshot();
  const jobs = orphans.filter(isArchivedOrphan);
  pruneLibrarySelectedKeys(selectedFileKeys, new Set(jobs.map((job) => `job:${job.id}`)));

  mountLibraryTable(filesWrap, {
    storageKey: "archive-files",
    jobs,
    batches: [],
    emptyMessage:
      t("archive.emptyFiles"),
    jobStatusLabel: archivedJobStatusLabel,
    jobStatusTone: archivedJobStatusTone,
    expandedBatches,
    onExpandChange: () => renderArchive(),
    onJobClick: (job) => navigate("editor", { jobId: job.id }),
    onJobContextMenu: (event, job, batchId) => openContextMenu(event, job, batchId),
    onBatchClick: () => {},
    onBatchContextMenu: () => {},
    selectable: true,
    selectedKeys: selectedFileKeys,
    bulkActions: archiveFileBulk(),
    onBulkAction: (action) =>
      runJobsBulkAction(selectedJobsFromKeys(selectedFileKeys, jobs), action, {
        onClear: () => selectedFileKeys.clear(),
      }).catch((err) => showToast(err.message || String(err))),
  });
}

function renderArchiveBatches() {
  if (!batchesWrap) {
    return;
  }
  const { batches } = getLibrarySnapshot();
  const batchList = batches.filter(isArchivedBatch);
  pruneLibrarySelectedKeys(selectedBatchKeys, new Set(batchList.map((batch) => `batch:${batch.id}`)));

  mountLibraryTable(batchesWrap, {
    storageKey: "archive-batches",
    jobs: [],
    batches: batchList,
    emptyMessage:
      t("archive.emptyBatches"),
    jobStatusLabel: archivedJobStatusLabel,
    jobStatusTone: archivedJobStatusTone,
    expandedBatches,
    onExpandChange: () => renderArchive(),
    onJobClick: (job) => navigate("editor", { jobId: job.id }),
    onJobContextMenu: (event, job, batchId) => openContextMenu(event, job, batchId),
    onBatchClick: (batch) => toggleExpandedBatch(batch.id),
    onBatchContextMenu: (event, batch) => openBatchContextMenu(event, batch),
    selectable: true,
    selectedKeys: selectedBatchKeys,
    bulkActions: archiveBatchBulk(),
    onBulkAction: (action) =>
      runBatchesBulkAction(selectedBatchesFromKeys(selectedBatchKeys, batchList), action, {
        onClear: () => selectedBatchKeys.clear(),
      }).catch((err) => showToast(err.message || String(err))),
  });
}

export function renderArchive() {
  if (activeTab === "batches") {
    renderArchiveBatches();
  } else {
    renderArchiveFiles();
  }
}

export async function refreshArchive() {
  await refreshLibrary();
  if (getRoute() === "archive") {
    renderArchive();
  }
}

export function initArchive() {
  if (archiveBound) {
    return;
  }
  archiveBound = true;
  filesWrap = document.getElementById("archive-files-wrap");
  batchesWrap = document.getElementById("archive-batches-wrap");
  document.querySelectorAll("#view-archive .legacy-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      navigate("archive", { tab: btn.dataset.tab });
    });
  });
}

export function onArchiveShow(params = {}) {
  applyArchiveTabUi(params.tab === "batches" ? "batches" : "files");
  refreshArchive().catch((err) => reportError(t("archive.title"), err));
}

export function onArchiveHide() {}
