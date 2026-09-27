import { t } from "./i18n.js";
/** Batch rules.batch_type helpers (mirror backend batch_rules.py). */

export function batchRules(batch) {
  return batch?.rules || {};
}

export function isYoutubeBatch(batch) {
  return batchRules(batch).batch_type === "youtube";
}

export function batchItemCountLabel(batch) {
  const count = batch?.total_count ?? (batch?.jobs || []).length;
  const n = Number(count) || 0;
  if (isYoutubeBatch(batch)) {
    return pluralRu(n, t("libraryUtils.video"), t("libraryUtils.video"), t("libraryUtils.video"));
  }
  return pluralRu(n, t("libraryUtils.file"), t("libraryUtils.files2"), t("libraryUtils.files5"));
}

export function batchProgressItemLabel(batch) {
  return isYoutubeBatch(batch) ? t("batchKind.videoItem") : t("batchKind.fileItem");
}

function pluralRu(n, one, few, many) {
  const abs = Math.abs(n) % 100;
  const n10 = abs % 10;
  if (abs > 10 && abs < 20) {
    return `${n} ${many}`;
  }
  if (n10 > 1 && n10 < 5) {
    return `${n} ${few}`;
  }
  if (n10 === 1) {
    return `${n} ${one}`;
  }
  return `${n} ${many}`;
}

export function youtubeBatchSourceLabel(batch) {
  const method = batchRules(batch).youtube_method || "apify";
  return method === "ytdlp" ? t("batchKind.youtubeYtdlp") : t("batchKind.youtubeApify");
}
