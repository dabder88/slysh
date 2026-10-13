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

const STORAGE_KEY = "transcripts-library";

function transcriptsBulkActions() {
  return [
    ["archive", t("transcripts.toArchive")],
    ["export", t("common.export")],
    ["delete", t("common.delete")],
  ];
}

let transcriptsBound = false;
const expandedBatches = new Set();
const selectedKeys = new Set();

let libraryWrap = null;

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

function runTranscriptsBulkAction(action, jobs, batchList) {
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
    renderTranscripts();
  });
}

export function renderTranscripts() {
  if (!libraryWrap) {
    return;
  }
  const { orphans, batches } = getLibrarySnapshot();
  const jobs = orphans.filter(isTranscriptJob);
  const batchList = batches.filter(isTranscriptBatch);
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
    emptyMessage: hasAny ? t("libraryTable.noFilterMatch") : t("transcripts.emptyFiles"),
    jobStatusLabel,
    jobStatusTone,
    expandedBatches,
    onExpandChange: () => renderTranscripts(),
    onJobClick: (job) => navigate("editor", { jobId: job.id }),
    onJobContextMenu: (event, job, batchId) => openContextMenu(event, job, batchId),
    onBatchClick: (batch) => toggleExpandedBatch(batch.id),
    onBatchContextMenu: (event, batch) => openBatchContextMenu(event, batch),
    selectable: true,
    selectedKeys,
    bulkActions: transcriptsBulkActions(),
    onBulkAction: (action) =>
      runTranscriptsBulkAction(action, jobs, batchList).catch((err) =>
        showToast(err.message || String(err))
      ),
  });
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
  libraryWrap = document.getElementById("transcripts-library-wrap");
}

export function onTranscriptsShow(params = {}) {
  refreshTranscripts()
    .then(() => {
      if (params.tab === "batches") {
        document
          .querySelector("#view-transcripts .library-table-row--batch")
          ?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    })
    .catch((err) => reportError(t("transcripts.title"), err));
}
