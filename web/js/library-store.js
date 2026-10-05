import { api, showToast, formatDuration } from "./api.js";
import { reportError } from "./errors.js";
import { ensureIntakeAllowed } from "./intake-duplicate.js";
import { t, jobStatusLabel as baseJobStatusLabel } from "./i18n.js";
import { speakersProgressOverEstimate } from "./library-utils.js";

export const SELECTED_BATCH_KEY = "selected_batch_id";

let jobs = [];
let batches = [];
let orphans = [];
let selectedBatchId = null;
let afterRefreshHook = null;
let afterSelectionHook = null;
let refreshSeq = 0;

export function setLibraryRefreshHook(fn) {
  afterRefreshHook = fn;
}

export function setLibrarySelectionHook(fn) {
  afterSelectionHook = fn;
}

function loadSelectedBatchId() {
  try {
    const raw = localStorage.getItem(SELECTED_BATCH_KEY);
    if (!raw) {
      return batches.length ? batches[0].id : null;
    }
    const id = Number(raw);
    if (Number.isFinite(id) && batches.some((b) => b.id === id)) {
      return id;
    }
  } catch (_) {
    /* ignore */
  }
  return batches.length ? batches[0].id : null;
}

function saveSelectedBatchId(batchId) {
  selectedBatchId = batchId;
  if (batchId == null) {
    localStorage.removeItem(SELECTED_BATCH_KEY);
  } else {
    localStorage.setItem(SELECTED_BATCH_KEY, String(batchId));
  }
  if (afterSelectionHook) {
    afterSelectionHook();
  }
}

export function getSelectedBatchId() {
  return selectedBatchId;
}

export function markSelectedBatch(batchId) {
  saveSelectedBatchId(batchId);
}

export function setSelectedBatch(batchId) {
  saveSelectedBatchId(batchId);
}

export async function refreshLibrary() {
  const seq = ++refreshSeq;
  try {
    const data = await api("/api/library");
    if (seq !== refreshSeq) {
      return;
    }
    batches = data.batches || [];
    orphans = data.orphans || [];
    jobs = [...orphans, ...batches.flatMap((b) => b.jobs || [])];
    selectedBatchId = loadSelectedBatchId();
    if (afterRefreshHook) {
      try {
        afterRefreshHook();
      } catch (err) {
        console.error(err);
      }
    }
  } catch (err) {
    if (seq !== refreshSeq) {
      return;
    }
    reportError(t("libraryStore.loadFailed"), err);
    throw err;
  }
}

export function getLibrarySnapshot() {
  return { jobs, batches, orphans };
}

export function jobById(id) {
  return jobs.find((j) => j.id === id);
}

/** Merge fresh GET /api/jobs fields into the in-memory library snapshot. */
export function upsertJobInStore(patch) {
  const id = patch?.id;
  if (id == null) {
    return;
  }
  orphans = orphans.map((j) => (j.id === id ? { ...j, ...patch } : j));
  batches = batches.map((batch) => ({
    ...batch,
    jobs: (batch.jobs || []).map((j) => (j.id === id ? { ...j, ...patch } : j)),
  }));
  jobs = [...orphans, ...batches.flatMap((b) => b.jobs || [])];
}

export function batchById(id) {
  return batches.find((b) => b.id === id);
}

export function jobStatusTone(job) {
  if (job.speakers_running || job.engine_starting || job.status === "running") {
    return "run";
  }
  if (job.status === "queued") {
    return "queue";
  }
  if (job.status === "completed") {
    return "done";
  }
  if (job.status === "failed") {
    return "err";
  }
  if (job.status === "cancelled") {
    return "cancel";
  }
  return "idle";
}

export function jobStatusLabel(job) {
  if (job.speakers_running) {
    const wait =
      job.speakers_elapsed_s != null ? ` · ${formatDuration(job.speakers_elapsed_s)}` : "";
    if (speakersProgressOverEstimate(job)) {
      return t("jobStatus.runningSpeakersLong", { wait });
    }
    return t("jobStatus.runningSpeakers", { wait });
  }
  const processingWait =
    job.processing_s != null ? ` · ${formatDuration(job.processing_s)}` : "";
  if ((job.status === "queued" || job.status === "running") && job.engine_starting) {
    return t("jobStatus.engineStarting", { wait: processingWait });
  }
  if (job.status === "queued") {
    const base = baseJobStatusLabel(job.status);
    return processingWait ? `${base}${processingWait}` : base;
  }
  if (job.status === "running") {
    const pct = Math.round(Number(job.progress || 0) * 100);
    return t("jobStatus.runningPct", { pct, wait: processingWait });
  }
  return baseJobStatusLabel(job.status);
}

export function hasActiveLibraryJobs(list) {
  const all = list || jobs;
  if (batches.some((b) => b.running)) {
    return true;
  }
  if (all.some((j) => j.speakers_running || j.engine_starting)) {
    return true;
  }
  return all.some((j) => j.status === "queued" || j.status === "running");
}

export async function addToBatch(batchId, paths, recursive) {
  const unique = [...new Set((paths || []).filter(Boolean))];
  if (!unique.length) {
    return null;
  }
  const scan = await api("/api/batches/scan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paths: unique, recursive: Boolean(recursive) }),
  });
  const resolved = scan.paths || [];
  if (resolved.length) {
    const allowed = await ensureIntakeAllowed({ paths: resolved });
    if (!allowed) {
      return null;
    }
  }
  return api(`/api/batches/${batchId}/items`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paths: unique, recursive }),
  });
}

export async function reorderBatchJob(batchId, fromId, toId) {
  const batch = batchById(batchId);
  if (!batch) {
    return;
  }
  const ids = (batch.jobs || []).map((j) => j.id);
  const fromIdx = ids.indexOf(fromId);
  const toIdx = ids.indexOf(toId);
  if (fromIdx < 0 || toIdx < 0) {
    return;
  }
  ids.splice(fromIdx, 1);
  ids.splice(toIdx, 0, fromId);
  await api(`/api/batches/${batchId}/reorder`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_ids: ids }),
  });
  await refreshLibrary();
}

export async function startBatch(batchId) {
  await api(`/api/batches/${batchId}/start`, { method: "POST" });
  await refreshLibrary();
  showToast("libraryStore.batchStarted");
}

export async function pauseBatch(batchId) {
  await api(`/api/batches/${batchId}/pause`, { method: "POST" });
  await refreshLibrary();
  showToast("libraryStore.pauseAfterFile");
}

export async function cancelBatch(batchId) {
  await api(`/api/batches/${batchId}/cancel`, { method: "POST" });
  await refreshLibrary();
  showToast("libraryStore.batchStopped");
}

export async function deleteBatchApi(batchId) {
  await api(`/api/batches/${batchId}`, { method: "DELETE" });
  await refreshLibrary();
}

export async function patchBatchName(batchId, name) {
  const trimmed = (name || "").trim();
  if (!trimmed) {
    throw new Error(t("libraryStore.batchNameRequired"));
  }
  await api(`/api/batches/${batchId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: trimmed }),
  });
  await refreshLibrary();
}
