import { basename } from "./api.js";
import { t } from "./i18n.js";
import { setSelectedBatch } from "./library-store.js";

/** @typedef {{ kind: "orphans", jobIds: number[], primaryJobId?: number, fileName?: string, fileCount?: number }} OrphansIntakeResult */
/** @typedef {{ kind: "batch", batchId: number, jobIds: number[], fileCount?: number }} BatchIntakeResult */
/** @typedef {OrphansIntakeResult | BatchIntakeResult} IntakeResult */

let bound = false;
let resolveFollowup = null;

/**
 * @param {Array<{ id?: number, source_path?: string }>} jobs
 * @returns {OrphansIntakeResult | null}
 */
export function orphansIntakeResult(jobs) {
  const list = (jobs || []).filter((j) => j?.id != null);
  if (!list.length) {
    return null;
  }
  const jobIds = list.map((j) => j.id);
  const fileName = list.length === 1 ? basename(list[0].source_path) : undefined;
  return {
    kind: "orphans",
    jobIds,
    primaryJobId: jobIds[0],
    fileName,
    fileCount: list.length,
  };
}

/**
 * @param {{ id?: number, jobs?: Array<{ id?: number }> }} batch
 * @param {number} [fileCount]
 * @returns {BatchIntakeResult | null}
 */
export function batchIntakeResult(batch, fileCount) {
  if (batch?.id == null) {
    return null;
  }
  const jobs = batch.jobs || [];
  const jobIds = jobs.map((j) => j.id).filter((id) => id != null);
  if (!jobIds.length && !fileCount) {
    return null;
  }
  return {
    kind: "batch",
    batchId: batch.id,
    jobIds,
    fileCount: fileCount ?? jobIds.length,
  };
}

function closeIntakeFollowupModal() {
  const modal = document.getElementById("intake-followup-modal");
  if (modal) {
    modal.hidden = true;
  }
  if (resolveFollowup) {
    resolveFollowup(null);
    resolveFollowup = null;
  }
}

function finishIntakeFollowup(choice) {
  const modal = document.getElementById("intake-followup-modal");
  if (modal) {
    modal.hidden = true;
  }
  if (resolveFollowup) {
    resolveFollowup(choice);
    resolveFollowup = null;
  }
}

function syncFollowupCopy(result) {
  const bodyEl = document.getElementById("intake-followup-body");
  if (!bodyEl || !result) {
    return;
  }
  if (result.kind === "batch") {
    const count = result.fileCount ?? result.jobIds.length;
    bodyEl.textContent = t("intake.followup.bodyBatch", { count });
    return;
  }
  const count = result.fileCount ?? result.jobIds.length;
  if (count === 1 && result.fileName) {
    bodyEl.textContent = t("intake.followup.bodyOneNamed", { name: result.fileName });
  } else if (count === 1) {
    bodyEl.textContent = t("intake.followup.bodyOne");
  } else {
    bodyEl.textContent = t("intake.followup.bodyMany", { count });
  }
}

async function applyFollowupChoice(result, choice) {
  if (!choice || !result) {
    return;
  }
  const { navigate } = await import("./router.js");
  if (choice === "later") {
    if (result.kind === "batch" && result.batchId != null) {
      const { expandLegacyBatch } = await import("./legacy.js");
      setSelectedBatch(result.batchId);
      expandLegacyBatch(result.batchId);
      navigate("legacy", { tab: "batches", batchId: result.batchId });
      return;
    }
    const id = result.primaryJobId ?? result.jobIds[0];
    const { selectJob } = await import("./legacy.js");
    navigate("legacy", { tab: "files" });
    if (id != null) {
      await selectJob(id);
    }
    return;
  }
  if (result.kind === "batch" && result.batchId != null) {
    const { expandLegacyBatch } = await import("./legacy.js");
    setSelectedBatch(result.batchId);
    expandLegacyBatch(result.batchId);
    navigate("legacy", { tab: "batches", batchId: result.batchId });
    return;
  }
  const id = result.primaryJobId ?? result.jobIds[0];
  if (id != null) {
    navigate("editor", { jobId: id });
  }
}

function bindIntakeFollowupModal() {
  if (bound) {
    return;
  }
  bound = true;
  const modal = document.getElementById("intake-followup-modal");
  if (!modal) {
    return;
  }
  document.getElementById("intake-followup-now")?.addEventListener("click", () => {
    finishIntakeFollowup("now");
  });
  document.getElementById("intake-followup-later")?.addEventListener("click", () => {
    finishIntakeFollowup("later");
  });
  modal.addEventListener("click", (event) => {
    if (event.target === modal) {
      closeIntakeFollowupModal();
    }
  });
}

/**
 * @param {IntakeResult | null | undefined} result
 * @returns {Promise<"now" | "later" | null>}
 */
export async function openIntakeFollowup(result) {
  if (!result) {
    return null;
  }
  const hasJobs =
    result.kind === "orphans"
      ? (result.jobIds?.length ?? 0) > 0
      : result.batchId != null && (result.fileCount ?? result.jobIds?.length ?? 0) > 0;
  if (!hasJobs) {
    return null;
  }
  bindIntakeFollowupModal();
  const modal = document.getElementById("intake-followup-modal");
  if (!modal) {
    return null;
  }
  syncFollowupCopy(result);
  modal.hidden = false;
  const choice = await new Promise((resolve) => {
    resolveFollowup = resolve;
  });
  if (choice) {
    await applyFollowupChoice(result, choice);
  }
  return choice;
}
