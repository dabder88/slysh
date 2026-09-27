import { t } from "./i18n.js";
export function parseClockToMs(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return null;
  }
  const parts = raw.split(":").map((part) => part.trim());
  if (parts.some((part) => part === "" || !/^\d+$/.test(part))) {
    throw new Error(t("mediaTime.clockFormat"));
  }
  const nums = parts.map((part) => Number(part));
  let seconds = 0;
  if (nums.length === 1) {
    seconds = nums[0];
  } else if (nums.length === 2) {
    seconds = nums[0] * 60 + nums[1];
  } else if (nums.length === 3) {
    seconds = nums[0] * 3600 + nums[1] * 60 + nums[2];
  } else {
    throw new Error(t("mediaTime.clockFormat"));
  }
  return seconds * 1000;
}

export function formatMsClock(ms) {
  if (ms == null || Number.isNaN(Number(ms))) {
    return "";
  }
  const total = Math.max(0, Math.round(Number(ms) / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function fillRangeInputs(startMs, endMs) {
  const startEl = document.getElementById("editor-range-start");
  const endEl = document.getElementById("editor-range-end");
  if (startEl) {
    startEl.value = startMs == null ? "" : formatMsClock(startMs);
  }
  if (endEl) {
    endEl.value = endMs == null ? "" : formatMsClock(endMs);
  }
}

export function readTranscribeRange(durationMs) {
  const startEl = document.getElementById("editor-range-start");
  const endEl = document.getElementById("editor-range-end");
  const startMs = parseClockToMs(startEl?.value);
  const endMs = parseClockToMs(endEl?.value);
  if (startMs != null && endMs != null && endMs <= startMs) {
    throw new Error(t("mediaTime.endBeforeStart"));
  }
  const limit = Number(durationMs);
  if (Number.isFinite(limit) && limit > 0) {
    if (startMs != null && startMs >= limit) {
      throw new Error(t("mediaTime.startPastEnd"));
    }
    if (endMs != null && endMs > limit) {
      throw new Error(t("mediaTime.endPastEnd"));
    }
  }
  return { start_ms: startMs, end_ms: endMs };
}

export function peekRange() {
  try {
    return readTranscribeRange();
  } catch {
    return { start_ms: null, end_ms: null };
  }
}
