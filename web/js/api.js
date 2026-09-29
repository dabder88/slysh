import { t, resolveMessageChain } from "./i18n.js";

export function translateKnownApiError(message, status) {
  const text = String(message || "").trim();
  if (status === 405 || text === "Method Not Allowed") {
    return t("apiErrors.http405");
  }
  return message;
}

export function api(path, options) {
  return fetch(path, options).then(async (r) => {
    if (!r.ok) {
      const raw = await r.text();
      let message = raw;
      if (r.status === 405 || raw.trim() === "Method Not Allowed") {
        message = translateKnownApiError(message, r.status);
      } else {
        try {
          const parsed = JSON.parse(raw);
          if (typeof parsed.detail === "string") {
            message = parsed.detail;
          } else if (typeof parsed.error === "string") {
            message = parsed.error;
          }
        } catch (_) {
          /* keep raw body */
        }
      }
      const err = new Error(message);
      err.status = r.status;
      throw err;
    }
    const type = r.headers.get("content-type") || "";
    if (type.includes("application/json")) {
      return r.json();
    }
    return r;
  });
}

let toastTimer = null;

function resolveToastMessage(message) {
  if (typeof message !== "string") {
    return String(message);
  }
  const keyLike = /^[a-z][\w\u0400-\u04FF]*(?:\.[\w\u0400-\u04FF]+)+$/i;
  if (keyLike.test(message)) {
    return t(message);
  }
  return resolveMessageChain(message);
}

export function showToast(message) {
  const toastEl = document.getElementById("toast");
  if (!toastEl) {
    return;
  }
  toastEl.textContent = resolveToastMessage(message);
  toastEl.hidden = false;
  if (toastTimer) {
    clearTimeout(toastTimer);
  }
  toastTimer = setTimeout(() => {
    toastEl.hidden = true;
  }, 5000);
}

/** Перезагружает окно приложения, обходя кэш HTML (удобно после правок в web/). */
export function reloadAppInterface() {
  const url = new URL(window.location.href);
  url.searchParams.set("_", String(Date.now()));
  window.location.replace(url.toString());
}

export function formatDuration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours) {
    return t("common.durationHours", { hours, minutes });
  }
  if (minutes) {
    return t("common.durationMinutes", { minutes, secs });
  }
  return t("common.durationSeconds", { secs });
}

export function basename(path) {
  return String(path || "").split(/[/\\]/).pop() || "";
}

export function jobDisplayName(job) {
  const title = String(job?.source_title || "").trim();
  if (title) {
    return title;
  }
  const kind = String(job?.kind || "file").trim().toLowerCase();
  if (kind === "youtube") {
    return job?.source_path || t("jobSource.youtube.label");
  }
  return basename(job?.source_path);
}

export function isYoutubeJob(job) {
  return String(job?.kind || "").trim().toLowerCase() === "youtube";
}

export function isAbsolutePath(path) {
  return /^(?:[A-Za-z]:[\\/]|\\\\|\/|file:)/i.test(String(path || "").trim());
}

export function pathsFromDrop(event) {
  const files = Array.from(event.dataTransfer.files || []);
  const fromFiles = files
    .map((f) => f.pywebviewFullPath || f.path)
    .filter((path) => path && isAbsolutePath(path));
  const uriList = (event.dataTransfer.getData("text/uri-list") || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#") && isAbsolutePath(line));
  const plain = (event.dataTransfer.getData("text/plain") || "").trim();
  const merged = [...fromFiles, ...uriList];
  if (plain && isAbsolutePath(plain)) {
    merged.push(plain);
  }
  return [...new Set(merged)];
}

export function pathLooksLikeFolder(path) {
  const base = String(path).split(/[/\\]/).pop() || "";
  return !/\.(wav|mp3|m4a|flac|ogg|opus|webm|mp4|mkv|avi)$/i.test(base);
}
