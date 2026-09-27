import { t } from "./i18n.js";

/** Known job kinds from SQLite `jobs.kind`. Extend when adding new capture sources. */
export function jobSourceKinds() {
  return {
    file: {
      label: t("jobSource.file.label"),
      title: t("jobSource.file.title"),
      tone: "file",
    },
    live: {
      label: t("live.title"),
      title: t("jobSource.live.title"),
      tone: "live",
    },
    meeting: {
      label: t("jobSource.meeting.label"),
      title: t("jobSource.meeting.title"),
      tone: "meeting",
    },
    youtube: {
      label: t("jobSource.youtube.label"),
      title: t("jobSource.youtube.title"),
      tone: "youtube",
    },
  };
}

export function jobSourceKind(job) {
  const raw = String(job?.kind || "file").trim().toLowerCase();
  return raw || "file";
}

export function jobSourceMeta(job) {
  const kind = jobSourceKind(job);
  const known = jobSourceKinds()[kind];
  if (known) {
    return { kind, ...known };
  }
  return {
    kind,
    label: kind,
    title: t("jobSource.unknown", { kind }),
    tone: "unknown",
  };
}

export function jobSourceLabel(job) {
  return jobSourceMeta(job).label;
}

export function jobSourceBadgeClass(job) {
  return `job-source-badge job-source-badge--${jobSourceMeta(job).tone}`;
}
