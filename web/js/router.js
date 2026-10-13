import { t } from "./i18n.js";
import { openSettingsModal } from "./shell.js";
import { setAsrContextBarRouteVisible } from "./asr-context-bar.js";
const routes = {
  dashboard: { view: "view-dashboard", nav: "nav-dashboard", topbar: "dashboard" },
  queue: { view: "view-queue", nav: "nav-queue", topbar: "queue" },
  transcripts: { view: "view-transcripts", nav: "nav-editor", topbar: "transcripts" },
  editor: { view: "view-editor", nav: "nav-editor", topbar: "editor" },
  archive: { view: "view-archive", nav: "nav-archive", topbar: "archive" },
  live: { view: "view-live", nav: "nav-live", topbar: "live" },
  meeting: { view: "view-meeting", nav: "nav-meeting", topbar: "meeting" },
  youtube: { view: "view-youtube", nav: "nav-youtube", topbar: "youtube" },
  legacy: { view: "view-legacy", nav: "nav-legacy", topbar: "legacy" },
};

let currentRoute = "dashboard";
let editorJobId = null;
let legacyBatchId = null;
let suppressNextHashChange = false;
const listeners = new Set();
const NAV_STACK_KEY = "nav-stack";

export function getRoute() {
  return currentRoute;
}

export function getEditorJobId() {
  return editorJobId;
}

export function getLegacyBatchId() {
  return legacyBatchId;
}

export function onRouteChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function readNavStack() {
  try {
    return JSON.parse(sessionStorage.getItem(NAV_STACK_KEY) || "[]");
  } catch (_) {
    return [];
  }
}

function writeNavStack(stack) {
  sessionStorage.setItem(NAV_STACK_KEY, JSON.stringify(stack.slice(-20)));
}

function pushNavStack() {
  const stack = readNavStack();
  stack.push({
    name: currentRoute,
    jobId: editorJobId,
    batchId: legacyBatchId,
    hash: location.hash,
  });
  writeNavStack(stack);
}

function parseHash() {
  const raw = (location.hash || "#/dashboard").replace(/^#/, "");
  const parts = raw.split("/").filter(Boolean);
  if (!parts.length) {
    return { name: "dashboard", params: {} };
  }
  if (parts[0] === "editor" && parts[1]) {
    const id = Number(parts[1]);
    return { name: "editor", params: { jobId: Number.isFinite(id) ? id : null } };
  }
  if (parts[0] === "package" && parts[1]) {
    const id = Number(parts[1]);
    return {
      name: "legacy",
      params: {
        batchId: Number.isFinite(id) ? id : null,
        tab: "batches",
        redirectFromPackage: true,
      },
    };
  }
  if (parts[0] === "legacy" && parts[1] === "batch" && parts[2]) {
    const id = Number(parts[2]);
    return {
      name: "legacy",
      params: {
        batchId: Number.isFinite(id) ? id : null,
        tab: "batches",
      },
    };
  }
  if (parts[0] === "legacy" && (parts[1] === "files" || parts[1] === "batches")) {
    return { name: "legacy", params: { tab: parts[1] } };
  }
  if (parts[0] === "transcripts" && (parts[1] === "files" || parts[1] === "batches")) {
    return { name: "transcripts", params: { tab: parts[1] } };
  }
  if (parts[0] === "transcripts") {
    return { name: "transcripts", params: { tab: "files" } };
  }
  if (parts[0] === "archive" && (parts[1] === "files" || parts[1] === "batches")) {
    return { name: "archive", params: { tab: parts[1] } };
  }
  if (parts[0] === "archive") {
    return { name: "archive", params: { tab: "files" } };
  }
  const name = parts[0];
  if (routes[name]) {
    return { name, params: {} };
  }
  return { name: "dashboard", params: {} };
}

function setTopbar(mode, params = {}) {
  const topbarEl = document.getElementById("topbar");
  if (topbarEl) {
    topbarEl.dataset.mode = mode || "";
  }
  const tabsEl = document.getElementById("topbar-tabs");
  const actionsEl = document.getElementById("topbar-actions");
  const titleEl = document.getElementById("topbar-title");
  const backBtn = document.getElementById("btn-topbar-back");
  const pauseAllBtn = document.getElementById("btn-queue-pause-all");
  const resumeAllBtn = document.getElementById("btn-queue-resume-all");
  const stopAllBtn = document.getElementById("btn-queue-stop-all");
  const exportBtn = document.getElementById("btn-topbar-export");
  if (!tabsEl || !actionsEl) {
    return;
  }
  setAsrContextBarRouteVisible(mode);
  tabsEl.hidden = mode !== "dashboard";
  actionsEl.hidden = mode !== "queue" && mode !== "editor";
  if (backBtn) {
    backBtn.hidden = mode === "dashboard";
  }
  if (pauseAllBtn) {
    pauseAllBtn.hidden = mode !== "queue";
  }
  if (resumeAllBtn) {
    resumeAllBtn.hidden = mode !== "queue";
  }
  if (stopAllBtn) {
    stopAllBtn.hidden = mode !== "queue";
  }
  if (exportBtn) {
    exportBtn.hidden = mode !== "editor";
  }
  const transcribeTop = document.getElementById("btn-topbar-transcribe");
  const stopTop = document.getElementById("btn-topbar-stop");
  if (transcribeTop) {
    transcribeTop.hidden = mode !== "editor";
    if (mode !== "editor") {
      transcribeTop.disabled = true;
    }
  }
  if (stopTop && mode !== "editor") {
    stopTop.hidden = true;
  }
  const subtitlePill = document.getElementById("topbar-subtitle-pill");
  if (subtitlePill) {
    subtitlePill.hidden = true;
    subtitlePill.textContent = "";
  }
  if (titleEl) {
    if (mode === "editor" && params.jobId) {
      titleEl.textContent = t("topbar.editor");
      titleEl.hidden = false;
    } else if (mode === "queue") {
      titleEl.textContent = t("topbar.queue");
      titleEl.hidden = false;
    } else if (mode === "transcripts") {
      titleEl.textContent = t("transcripts.title");
      titleEl.hidden = false;
    } else if (mode === "archive") {
      titleEl.textContent = t("archive.title");
      titleEl.hidden = false;
    } else if (mode === "live") {
      titleEl.textContent = t("live.title");
      titleEl.hidden = false;
      if (subtitlePill) {
        subtitlePill.textContent = t("live.topbarSubtitle");
        subtitlePill.hidden = false;
      }
    } else if (mode === "meeting") {
      titleEl.textContent = t("topbar.meeting");
      titleEl.hidden = false;
      if (subtitlePill) {
        subtitlePill.textContent = t("meeting.topbarSubtitle");
        subtitlePill.hidden = false;
      }
    } else if (mode === "youtube") {
      titleEl.textContent = t("topbar.youtube");
      titleEl.hidden = false;
    } else if (mode === "legacy") {
      titleEl.textContent = t("topbar.legacy");
      titleEl.hidden = false;
    } else {
      titleEl.hidden = true;
    }
  }
}

export function navigate(name, params = {}, options = {}) {
  const push = options.push !== false;
  if (push && currentRoute && currentRoute !== name) {
    pushNavStack();
  }
  if (name === "editor" && params.jobId != null) {
    const next = `#/editor/${params.jobId}`;
    if (location.hash === next) {
      applyRoute(parseHash());
      return;
    }
    suppressNextHashChange = true;
    location.hash = next;
    applyRoute(parseHash());
    return;
  }
  if (name === "package" && params.batchId != null) {
    navigate("legacy", { batchId: params.batchId, tab: "batches" }, options);
    return;
  }
  if (name === "legacy" && params.batchId != null) {
    const next = `#/legacy/batch/${params.batchId}`;
    if (location.hash === next) {
      applyRoute(parseHash());
      return;
    }
    location.hash = next;
    return;
  }
  if (name === "legacy" && (params.tab === "files" || params.tab === "batches")) {
    const next = `#/legacy/${params.tab}`;
    if (location.hash === next) {
      applyRoute(parseHash());
      return;
    }
    location.hash = next;
    return;
  }
  if (name === "transcripts" && (params.tab === "files" || params.tab === "batches")) {
    const next = `#/transcripts/${params.tab}`;
    if (location.hash === next) {
      applyRoute(parseHash());
      return;
    }
    location.hash = next;
    return;
  }
  if (name === "archive" && (params.tab === "files" || params.tab === "batches")) {
    const next = `#/archive/${params.tab}`;
    if (location.hash === next) {
      applyRoute(parseHash());
      return;
    }
    location.hash = next;
    return;
  }
  const next = `#/${name}`;
  if (location.hash === next) {
    applyRoute(parseHash());
    return;
  }
  location.hash = next;
}

export function navigateBack() {
  const stack = readNavStack();
  const prev = stack.pop();
  writeNavStack(stack);
  if (!prev) {
    navigate("dashboard", {}, { push: false });
    return;
  }
  if (prev.name === "editor" && prev.jobId != null) {
    navigate("editor", { jobId: prev.jobId }, { push: false });
    return;
  }
  if (prev.name === "package" && prev.batchId != null) {
    navigate("legacy", { batchId: prev.batchId, tab: "batches" }, { push: false });
    return;
  }
  if (prev.name === "legacy" && prev.batchId != null) {
    navigate("legacy", { batchId: prev.batchId, tab: "batches" }, { push: false });
    return;
  }
  navigate(prev.name || "dashboard", {}, { push: false });
}

function applyRoute(parsed) {
  const { name, params } = parsed;
  currentRoute = name;
  editorJobId = name === "editor" ? params.jobId : null;
  legacyBatchId = name === "legacy" ? params.batchId ?? null : null;

  if (params.redirectFromPackage && params.batchId != null) {
    const canonical = `#/legacy/batch/${params.batchId}`;
    if (location.hash !== canonical) {
      location.replace(canonical);
      return;
    }
  }

  document.querySelectorAll(".view").forEach((el) => el.classList.remove("is-active"));
  const route = routes[name] || routes.dashboard;
  const viewEl = document.getElementById(route.view);
  if (viewEl) {
    viewEl.classList.add("is-active");
  }

  const viewPort = document.getElementById("view-port");
  if (viewPort) {
    viewPort.scrollTop = 0;
  }

  document.querySelectorAll("[data-nav]").forEach((el) => {
    el.classList.toggle("is-active", el.dataset.nav === route.nav);
  });

  setTopbar(route.topbar, { ...params, batchId: legacyBatchId });

  for (const fn of listeners) {
    fn(name, params);
  }
}

export function notifyCurrentRoute() {
  applyRoute(parseHash());
}

export function initRouter() {
  window.addEventListener("hashchange", () => {
    if (suppressNextHashChange) {
      suppressNextHashChange = false;
      return;
    }
    applyRoute(parseHash());
  });

  document.getElementById("btn-topbar-back")?.addEventListener("click", () => {
    navigateBack();
  });

  document.querySelectorAll("[data-nav]").forEach((el) => {
    el.addEventListener("click", (event) => {
      event.preventDefault();
      if (el.classList.contains("is-disabled")) {
        return;
      }
      const target = el.dataset.nav;
      const map = {
        "nav-dashboard": "dashboard",
        "nav-queue": "queue",
        "nav-editor": "transcripts",
        "nav-archive": "archive",
        "nav-legacy": "legacy",
        "nav-live": "live",
        "nav-meeting": "meeting",
        "nav-youtube": "youtube",
        "nav-settings": "settings",
      };
      const route = map[target];
      if (route === "settings") {
        openSettingsModal();
        return;
      }
      if (route) {
        navigate(route);
      }
    });
  });

  document.getElementById("btn-upload-cta")?.addEventListener("click", () => {
    navigate("dashboard");
    document.getElementById("btn-dashboard-pick-files")?.click();
  });

  document.getElementById("topbar-tab-single")?.addEventListener("click", () => {
    document.getElementById("dashboard-single-card")?.scrollIntoView({ behavior: "smooth" });
    document.querySelectorAll(".topbar-tab").forEach((el) => {
      el.classList.toggle("is-active", el.id === "topbar-tab-single");
    });
  });

  document.getElementById("topbar-tab-batch")?.addEventListener("click", () => {
    document.getElementById("dashboard-batch-card")?.scrollIntoView({ behavior: "smooth" });
    document.querySelectorAll(".topbar-tab").forEach((el) => {
      el.classList.toggle("is-active", el.id === "topbar-tab-batch");
    });
  });

  document.getElementById("btn-view-all")?.addEventListener("click", (event) => {
    event.preventDefault();
    navigate("legacy", { tab: "files" });
  });

  if (!location.hash || location.hash === "#") {
    location.hash = "#/dashboard";
  } else {
    applyRoute(parseHash());
  }
}
