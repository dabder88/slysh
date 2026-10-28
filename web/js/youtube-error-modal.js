import { isYoutubeJob } from "./api.js";
import { t } from "./i18n.js";
import { navigate } from "./router.js";
import { openSettingsModal } from "./shell.js";

let lastShownErrorJobId = null;

function bindYoutubeErrorModalOnce() {
  const modal = document.getElementById("youtube-error-modal");
  if (!modal || modal.dataset.bound === "1") {
    return;
  }
  modal.dataset.bound = "1";
  document.getElementById("youtube-error-modal-close")?.addEventListener("click", () => {
    modal.hidden = true;
  });
  document.getElementById("youtube-error-modal-settings")?.addEventListener("click", () => {
    modal.hidden = true;
    openSettingsModal("proxy");
  });
  document.getElementById("youtube-error-modal-youtube")?.addEventListener("click", () => {
    modal.hidden = true;
    navigate("youtube");
  });
  modal.addEventListener("click", (event) => {
    if (event.target === modal) {
      modal.hidden = true;
    }
  });
}

export function showYoutubeErrorModal(job) {
  if (!job || job.status !== "failed" || !isYoutubeJob(job)) {
    return;
  }
  if (lastShownErrorJobId === job.id) {
    return;
  }
  lastShownErrorJobId = job.id;
  bindYoutubeErrorModalOnce();
  const modal = document.getElementById("youtube-error-modal");
  if (!modal) {
    return;
  }
  const titleEl = document.getElementById("youtube-error-modal-title");
  const leadEl = document.getElementById("youtube-error-modal-lead");
  const hintsEl = document.getElementById("youtube-error-modal-hints");
  const apifyEl = document.getElementById("youtube-error-modal-apify-note");
  if (titleEl) {
    titleEl.textContent = t("youtube.errorModalTitle");
  }
  if (leadEl) {
    leadEl.textContent = job.error_text || t("youtube.errorGeneric");
  }
  if (hintsEl) {
    hintsEl.replaceChildren();
    const hints = job.youtube_error?.hints;
    if (Array.isArray(hints) && hints.length) {
      const ul = document.createElement("ul");
      ul.className = "youtube-error-modal-hints";
      for (const hint of hints) {
        const li = document.createElement("li");
        li.textContent = hint;
        ul.appendChild(li);
      }
      hintsEl.appendChild(ul);
    }
  }
  if (apifyEl) {
    const code = job.youtube_error?.code || "";
    apifyEl.hidden = code !== "ip_blocked";
    apifyEl.textContent = t("youtube.errorApifyNote");
  }
  modal.hidden = false;
}

export function resetYoutubeErrorModalTracking() {
  lastShownErrorJobId = null;
}
