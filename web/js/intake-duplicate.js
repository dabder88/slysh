import { api, showToast } from "./api.js";
import { t } from "./i18n.js";

function matchTitle(match) {
  const title = (match?.source_title || "").trim();
  if (title) {
    return title;
  }
  if (match?.kind === "youtube" && match?.video_id) {
    return `YouTube ${match.video_id}`;
  }
  const path = (match?.source_path || match?.input_key || "").trim();
  if (path) {
    const parts = path.split(/[/\\]/);
    return parts[parts.length - 1] || path;
  }
  return t("common.noTitle");
}

export async function fetchExistingMatches({ paths, youtubeUrls } = {}) {
  const files = [...new Set((paths || []).filter(Boolean))];
  const youtube_urls = [...new Set((youtubeUrls || []).filter(Boolean))];
  if (!files.length && !youtube_urls.length) {
    return [];
  }
  const body = await api("/api/library/check-existing", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      files: files.length ? files : undefined,
      youtube_urls: youtube_urls.length ? youtube_urls : undefined,
    }),
  });
  return body.matches || [];
}

export function confirmReingest(matches) {
  const list = matches || [];
  if (!list.length) {
    return true;
  }
  if (list.length === 1) {
    return window.confirm(t("intake.reingestOne", { title: matchTitle(list[0]) }));
  }
  const sample = list
    .slice(0, 3)
    .map((m) => matchTitle(m))
    .join("; ");
  const suffix = list.length > 3 ? "…" : "";
  return window.confirm(
    t("intake.reingestMany", { count: list.length, sample, suffix })
  );
}

export async function ensureIntakeAllowed({ paths, youtubeUrls } = {}) {
  const matches = await fetchExistingMatches({ paths, youtubeUrls });
  if (!matches.length) {
    return true;
  }
  const ok = confirmReingest(matches);
  if (!ok) {
    showToast("intake.cancelled");
  }
  return ok;
}
