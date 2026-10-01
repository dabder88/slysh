import { t } from "./i18n.js";
export function isJobActive(job) {
  return Boolean(
    job.speakers_running || job.engine_starting || job.status === "running"
  );
}

export function isJobWaiting(job, batchMap) {
  if (job.status === "queued") {
    return true;
  }
  if (job.status === "idle" && job.batch_id != null) {
    const batch = batchMap.get(job.batch_id);
    return Boolean(batch && batch.running);
  }
  return false;
}

export function isBatchActive(batch) {
  return Boolean(batch.running || batch.active_count > 0);
}

export function isJobCompleted(job) {
  return job.status === "completed";
}

export function isJobArchived(job) {
  return Boolean(job.archived);
}

export function isTranscriptJob(job) {
  return isJobCompleted(job) && !isJobArchived(job);
}

export function isQueueOrphan(job) {
  return job.status !== "completed";
}

export function isLibraryOrphan(job) {
  return !isJobArchived(job) && job.batch_id == null;
}

export function isArchivedOrphan(job) {
  return isJobCompleted(job) && isJobArchived(job);
}

export function isArchiveBatch(batch) {
  return Boolean(batch.archived);
}

export function isTranscriptBatch(batch) {
  return !isArchiveBatch(batch) && batchDoneCount(batch) >= 1;
}

export function isArchivedBatch(batch) {
  return isArchiveBatch(batch);
}

function ruPlural(n, one, few, many) {
  const abs = Math.abs(Number(n) || 0) % 100;
  const n10 = abs % 10;
  if (abs > 10 && abs < 20) {
    return many;
  }
  if (n10 > 1 && n10 < 5) {
    return few;
  }
  if (n10 === 1) {
    return one;
  }
  return many;
}

export function batchFileCount(batch) {
  if (batch?.total_count != null) {
    return Number(batch.total_count) || 0;
  }
  return (batch?.jobs || []).length;
}

export function batchDoneCount(batch) {
  if (batch?.done_count != null) {
    return Number(batch.done_count) || 0;
  }
  return (batch?.jobs || []).filter((job) => job.status === "completed").length;
}

export function formatBatchFilesLabel(batch) {
  const count = batchFileCount(batch);
  const rules = batch?.rules || {};
  if (rules.batch_type === "youtube") {
    return `${count} ${ruPlural(count, t("libraryUtils.video"), t("libraryUtils.video"), t("libraryUtils.video"))}`;
  }
  return `${count} ${ruPlural(count, t("libraryUtils.file"), t("libraryUtils.files2"), t("libraryUtils.files5"))}`;
}

export function formatBatchTranscriptsLabel(batch) {
  const count = batchDoneCount(batch);
  return `${count} ${ruPlural(count, t("libraryUtils.transcript1"), t("libraryUtils.transcript2"), t("libraryUtils.transcript5"))}`;
}

export function speakersStatusLabel(job) {
  if (!job) {
    return t("common.dash");
  }
  if (String(job.kind || "").toLowerCase() === "youtube") {
    return t("common.dash");
  }
  if (job.speakers_running) {
    return t("libraryTable.running");
  }
  if (job.speakers_error) {
    return t("common.error");
  }
  const count = Number(job.speaker_count || 0);
  if (count > 0 || job.has_speakers) {
    return count > 0 ? t("libraryUtils.yesCount", { count }) : t("common.yes");
  }
  if (job.status === "completed") {
    return t("common.no");
  }
  return t("common.dash");
}

export function speakersStatusHint(job) {
  if (!job) {
    return "";
  }
  if (job.speakers_running) {
    return t("libraryUtils.speakersRunning");
  }
  if (job.speakers_error) {
    return t("libraryUtils.speakersError");
  }
  const count = Number(job.speaker_count || 0);
  if (count > 0 || job.has_speakers) {
    if (count > 0) {
      return t("libraryUtils.speakersCount", {
        count,
        word: ruPlural(
          count,
          t("libraryUtils.speaker1"),
          t("libraryUtils.speaker2"),
          t("libraryUtils.speaker5")
        ),
      });
    }
    return t("libraryUtils.speakersMarked");
  }
  if (job.status === "completed") {
    return t("libraryUtils.speakersNotMarked");
  }
  return "";
}

export function speakersBadgeClass(job) {
  if (!job) {
    return "speakers-badge--empty";
  }
  if (job.speakers_running) {
    return "speakers-badge--run";
  }
  if (job.speakers_error) {
    return "speakers-badge--err";
  }
  if (job.has_speakers || Number(job.speaker_count || 0) > 0) {
    return "speakers-badge--yes";
  }
  if (job.status === "completed") {
    return "speakers-badge--no";
  }
  return "speakers-badge--empty";
}

export function formatBatchCountsSummary(batch, separator = " · ") {
  return `${formatBatchFilesLabel(batch)}${separator}${formatBatchTranscriptsLabel(batch)}`;
}

export function estimateSpeakerWorkSeconds(job) {
  const dur = Number(job?.duration_s);
  if (Number.isFinite(dur) && dur > 0) {
    // NeMo MSDD often runs longer than realtime on CPU; avoid capping at 10 min for long meetings.
    return Math.max(90, Math.min(7200, dur * 1.2));
  }
  return 180;
}

export function speakersProgressOverEstimate(job) {
  if (!job?.speakers_running) {
    return false;
  }
  const elapsed = Number(job.speakers_elapsed_s);
  if (!Number.isFinite(elapsed) || elapsed < 0) {
    return false;
  }
  return elapsed > estimateSpeakerWorkSeconds(job);
}

export function speakerProgressPct(job) {
  if (!job?.speakers_running) {
    return null;
  }
  const elapsed = Number(job.speakers_elapsed_s);
  if (!Number.isFinite(elapsed) || elapsed < 0) {
    return 0;
  }
  if (speakersProgressOverEstimate(job)) {
    return null;
  }
  const estimate = estimateSpeakerWorkSeconds(job);
  return Math.min(90, Math.round((elapsed / estimate) * 100));
}

export function jobProgressPct(job) {
  const speakerPct = speakerProgressPct(job);
  if (job?.speakers_running) {
    if (speakerPct != null) {
      return speakerPct;
    }
    return 90;
  }
  if (speakerPct != null) {
    return speakerPct;
  }
  return Math.round(Number(job.progress || 0) * 100);
}

export function jobProgressPctLabel(job) {
  if (isProgressIndeterminate(job)) {
    const pct = jobProgressPct(job);
    if (job?.speakers_running || pct <= 0) {
      return "…";
    }
  }
  const pct = jobProgressPct(job);
  return `${pct}%`;
}

export function isProgressIndeterminate(job) {
  if (!job) {
    return false;
  }
  if (job.status === "queued" || job.engine_starting) {
    return true;
  }
  if (job.speakers_running && speakersProgressOverEstimate(job)) {
    return true;
  }
  return job.status === "running" && jobProgressPct(job) <= 0;
}

export function batchProgressPct(batch) {
  const total = batchFileCount(batch);
  if (!total) {
    return 0;
  }
  const done = batchDoneCount(batch);
  let pct = Math.round((done / total) * 100);
  const current = (batch.jobs || []).find((j) => isJobActive(j));
  if (current) {
    const slot = 100 / total;
    const currentPct = jobProgressPct(current);
    pct = Math.min(99, Math.round(done * slot + (currentPct / 100) * slot));
  }
  return pct;
}

export function updateProgressBarFill(fill, pct, indeterminate, tone = "primary", wrap = null) {
  if (!fill) {
    return;
  }
  const value = Math.max(0, Math.min(100, Number(pct) || 0));
  if (wrap) {
    wrap.setAttribute("aria-valuenow", indeterminate ? "0" : String(value));
  }
  fill.className = `queue-progress-fill queue-progress-fill--${tone}`;
  if (indeterminate) {
    fill.classList.add("progress-bar-stripes", "is-indeterminate");
    fill.style.width = fill.closest(".job-progress") ? "" : "34%";
    fill.style.transform = "";
  } else {
    fill.classList.remove("progress-bar-stripes", "is-indeterminate");
    fill.style.width = `${value}%`;
    fill.style.transform = "none";
  }
}

export function createProgressBar(pct, tone = "primary", className = "", indeterminate = false) {
  const wrap = document.createElement("div");
  wrap.className = `queue-progress-track ${className}`.trim();
  wrap.setAttribute("role", "progressbar");
  wrap.setAttribute("aria-valuemin", "0");
  wrap.setAttribute("aria-valuemax", "100");
  const fill = document.createElement("div");
  wrap.appendChild(fill);
  updateProgressBarFill(fill, pct, indeterminate, tone, wrap);
  return wrap;
}

export function isJobTranscribing(job) {
  return Boolean(
    job &&
      (job.status === "queued" || job.status === "running" || job.speakers_running || job.engine_starting)
  );
}

export const RENAME_MIN_SPEAKER_DURATION_MS = 5000;

export function parseSpeakerOrdinal(key) {
  const match = /^SPEAKER_(\d+)$/i.exec(String(key || "").trim());
  return match ? parseInt(match[1], 10) : null;
}

export function segmentSpeakerKeyFromSeg(seg) {
  return seg?.speaker_key ?? seg?.speaker ?? "";
}

export function speakerDurationByKey(segments) {
  const map = new Map();
  for (const seg of segments || []) {
    const key = segmentSpeakerKeyFromSeg(seg);
    if (!key) {
      continue;
    }
    const dur = Math.max(0, Number(seg.end_ms) - Number(seg.start_ms));
    map.set(key, (map.get(key) || 0) + dur);
  }
  return map;
}

function compareSpeakerKeys(a, b) {
  const na = parseSpeakerOrdinal(a);
  const nb = parseSpeakerOrdinal(b);
  if (na != null && nb != null) {
    return na - nb;
  }
  if (na != null) {
    return -1;
  }
  if (nb != null) {
    return 1;
  }
  return String(a).localeCompare(String(b), undefined, { numeric: true });
}

export function orderedSpeakerKeys(segments, options = {}) {
  const { renameMinDurationMs = 0 } = options;
  const durations = speakerDurationByKey(segments);
  let keys = [...durations.keys()];
  if (renameMinDurationMs > 0) {
    keys = keys.filter((key) => (durations.get(key) || 0) >= renameMinDurationMs);
  }
  keys.sort(compareSpeakerKeys);
  return keys;
}

export function speakerKeysForRename(segments) {
  return orderedSpeakerKeys(segments, {
    renameMinDurationMs: RENAME_MIN_SPEAKER_DURATION_MS,
  });
}

export function speakerDisplayName(key, customName) {
  const name = String(customName || "").trim();
  if (name) {
    return name;
  }
  if (!key) {
    return t("editor.k3146264");
  }
  const ordinal = parseSpeakerOrdinal(key);
  if (ordinal != null) {
    return t("editor.speakerN", { n: ordinal + 1 });
  }
  return String(key);
}
