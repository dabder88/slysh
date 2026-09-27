import { initI18n, applyI18n, onLocaleChange } from "./i18n.js";
import { initRouter, onRouteChange, navigate, notifyCurrentRoute } from "./router.js";
import { initShell } from "./shell.js";
import { initSecretFields } from "./secret-field.js?v=1";
import { initDashboard, onDashboardShow } from "./dashboard.js";
import { initLive, onLiveShow } from "./live.js";
import { initMeeting, onMeetingShow } from "./meeting.js";
import { initYoutube, onYoutubeShow } from "./youtube.js";
import { initEditor, onEditorShow } from "./editor.js";
import { initQueue, onQueueShow, onQueueHide } from "./queue.js";
import { initArchive, onArchiveShow } from "./archive.js";
import { initTranscripts, onTranscriptsShow } from "./transcripts.js";
import { initLegacyWorkspace, onLegacyShow } from "./legacy.js";

function hideBootSplash() {
  document.body?.classList.remove("is-booting");
  const splash = document.getElementById("boot-splash");
  if (splash) {
    splash.hidden = true;
  }
}

function scheduleEngineSetupModal(status) {
  if (
    !status ||
    typeof window.openEngineSetupModalIfNeeded !== "function"
  ) {
    return;
  }
  window.openEngineSetupModalIfNeeded(status);
  requestAnimationFrame(() => {
    window.openEngineSetupModalIfNeeded(status);
  });
}

async function bootstrap() {
  const bootFallback = window.setTimeout(hideBootSplash, 15000);

  initSecretFields();
  await initI18n();
  initShell();
  let bootSetupStatus = null;
  try {
    if (typeof window.refreshEngineSetupUi === "function") {
      bootSetupStatus = await window.refreshEngineSetupUi();
    }
  } catch (err) {
    console.error(err);
  } finally {
    window.clearTimeout(bootFallback);
    hideBootSplash();
    scheduleEngineSetupModal(bootSetupStatus);
  }
  initRouter();

  let lastRoute = null;

  onLocaleChange(() => {
    applyI18n();
    notifyCurrentRoute();
  });

  onRouteChange((route, params) => {
    if (lastRoute === "queue" && route !== "queue") {
      onQueueHide();
    }
    lastRoute = route;

    if (route === "dashboard") {
      onDashboardShow();
    } else if (route === "queue") {
      onQueueShow();
    } else if (route === "archive") {
      onArchiveShow(params);
    } else if (route === "transcripts") {
      onTranscriptsShow(params);
    } else if (route === "live") {
      onLiveShow();
    } else if (route === "meeting") {
      onMeetingShow();
    } else if (route === "youtube") {
      onYoutubeShow();
    } else if (route === "editor") {
      onEditorShow(params.jobId);
    } else if (route === "legacy") {
      onLegacyShow(params);
    }
  });

  initDashboard();
  initQueue();
  initArchive();
  initTranscripts();
  initLive();
  initMeeting();
  initYoutube();
  initEditor();
  initLegacyWorkspace();

  document.querySelector("[data-go-legacy]")?.addEventListener("click", () => navigate("legacy"));

  notifyCurrentRoute();
}

bootstrap().catch((err) => {
  console.error(err);
  hideBootSplash();
  const banner = document.getElementById("boot-error");
  if (banner) {
    banner.hidden = false;
    banner.textContent = String(err?.message || err);
  }
});
