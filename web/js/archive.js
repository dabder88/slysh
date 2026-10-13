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

const STORAGE_KEY = "archive-library";

function archiveBulkActions() {
  return [
    ["unarchive", t("archive.unarchive")],
    ["export", t("common.export")],
    ["delete", t("common.delete")],
  ];
}

let archiveBound = false;
const expandedBatches = new Set();
const selectedKeys = new Set();

let libraryWrap = null;

function archivedJobStatusLabel() {
  return t("jobStatus.archived");
}

function archivedJobStatusTone() {
  return "done";
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

function runArchiveBulkAction(action, jobs, batchList) {
  const selectedJobs = selectedJobsFromKeys(selectedKeys, jobs);
  const selectedBatches = selectedBatchesFromKeys(selectedKeys, batchList);
  const tasks = [];
  if (selectedJobs.length) {
    tasks.push(
      runJobsBulkAction(selectedJobs, action, {
        onClear: () => {
          for (const job of selectedJobs) {
            selectedKeys.delete(`job:${job.id}`);
          }
        },
      })
    );
  }
  if (selectedBatches.length) {
    tasks.push(
      runBatchesBulkAction(selectedBatches, action, {
        onClear: () => {
          for (const batch of selectedBatches) {
            selectedKeys.delete(`batch:${batch.id}`);
          }
        },
      })
    );
  }
  if (!tasks.length) {
    return Promise.resolve();
  }
  return Promise.all(tasks).then(() => {
    if (!selectedKeys.size) {
      return;
    }
    renderArchive();
  });
}

export function renderArchive() {
  if (!libraryWrap) {
    return;
  }
  const { orphans, batches } = getLibrarySnapshot();
  const jobs = orphans.filter(isArchivedOrphan);
  const batchList = batches.filter(isArchivedBatch);
  const validKeys = new Set([
    ...jobs.map((job) => `job:${job.id}`),
    ...batchList.map((batch) => `batch:${batch.id}`),
  ]);
  pruneLibrarySelectedKeys(selectedKeys, validKeys);

  const hasAny = jobs.length > 0 || batchList.length > 0;
  mountLibraryTable(libraryWrap, {
    storageKey: STORAGE_KEY,
    jobs,
    batches: batchList,
    emptyMessage: hasAny ? t("libraryTable.noFilterMatch") : t("archive.emptyFiles"),
    jobStatusLabel: archivedJobStatusLabel,
    jobStatusTone: archivedJobStatusTone,
    expandedBatches,
    onExpandChange: () => renderArchive(),
    onJobClick: (job) => navigate("editor", { jobId: job.id }),
    onJobContextMenu: (event, job, batchId) => openContextMenu(event, job, batchId),
    onBatchClick: (batch) => toggleExpandedBatch(batch.id),
    onBatchContextMenu: (event, batch) => openBatchContextMenu(event, batch),
    selectable: true,
    selectedKeys,
    bulkActions: archiveBulkActions(),
    onBulkAction: (action) =>
      runArchiveBulkAction(action, jobs, batchList).catch((err) =>
        showToast(err.message || String(err))
      ),
  });
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
  libraryWrap = document.getElementById("archive-library-wrap");
}

export function onArchiveShow(params = {}) {
  refreshArchive()
    .then(() => {
      if (params.tab === "batches") {
        document
          .querySelector("#view-archive .library-table-row--batch")
          ?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    })
    .catch((err) => reportError(t("archive.title"), err));
}

export function onArchiveHide() {}
