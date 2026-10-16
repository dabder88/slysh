import { api, showToast, reloadAppInterface } from "./api.js";
import { reportError } from "./errors.js";
import { SELECTED_BATCH_KEY } from "./library-store.js";
import { getLocale, setLocale, t, onLocaleChange } from "./i18n.js";
import { resolveMarketingUrlsFromApi } from "./marketing-urls.js";
import { bindSecretInput, readSecretForSave } from "./secret-field.js";
import { updateAsrContextBar } from "./asr-context-bar.js";
import {
  addExportDirRowToList,
  collectDirsFromList,
  fetchExportFavoriteDirs,
  fillExportDirsList,
  saveExportFavoriteDirs,
} from "./export-favorites.js";
import { bindPanelResizer } from "./panel-resize.js";

const GIGAAM_MODEL_ID = "gigaam";

/** EN UI: hide GigaAM download row; keep installed weights. */
export function filterLocalModelsForUi(items, locale = getLocale()) {
  const list = items || [];
  if (locale !== "en") {
    return list;
  }
  return list.filter(
    (item) =>
      !(
        item.id === GIGAAM_MODEL_ID &&
        item.ready === false &&
        item.downloadable === true
      ),
  );
}

function applyProviderSecretField(input, provider) {
  if (!input) {
    return;
  }
  const p = provider || {};
  bindSecretInput(input, {
    full: p.api_key || "",
    masked: p.api_key_masked || p.api_key_tail || "",
    isSet: Boolean(p.api_key_set),
  });
}

function secretBodyPatch(input) {
  const key = readSecretForSave(input);
  if (key === undefined) {
    return {};
  }
  return { api_key: key };
}

const NAV_STACK_KEY = "nav-stack";

function formatGiBApprox(bytes) {
  const n = Number(bytes) || 0;
  if (n <= 0) {
    return "0";
  }
  const gib = n / 1024 ** 3;
  if (gib >= 10) {
    return String(Math.round(gib));
  }
  return gib.toFixed(1);
}

function formatModelVolumePair(bytesDone, bytesTotal) {
  const bt = Number(bytesTotal) || 0;
  const bd = Number(bytesDone) || 0;
  if (bt <= 0) {
    return "";
  }
  if (bt < 1024 ** 3) {
    const doneMiB = bd / 1024 ** 2;
    const totalMiB = bt / 1024 ** 2;
    const fmt = (v) => (v >= 10 ? String(Math.round(v)) : v.toFixed(1));
    return t("modelSetup.progressVolumeMiB", {
      done: fmt(doneMiB),
      total: fmt(totalMiB),
    });
  }
  return t("modelSetup.progressVolumeGiB", {
    done: formatGiBApprox(bd),
    total: formatGiBApprox(bt),
  });
}

function formatModelProgressSummary(prog) {
  const p = prog || {};
  const parts = [];
  const vol = formatModelVolumePair(p.bytes_done, p.bytes_total);
  if (vol) {
    parts.push(vol);
  }
  if (p.fraction != null && p.indeterminate === false) {
    parts.push(
      t("modelSetup.progressPercent", {
        percent: Math.round(Number(p.fraction) * 100),
      }),
    );
  }
  return parts.join(" · ");
}

function modelDownloadDetailLine(prog, summaryLine) {
  const msg = String(prog?.message || "").trim();
  if (!msg || msg === summaryLine) {
    return "";
  }
  if (summaryLine && summaryLine.includes(msg)) {
    return "";
  }
  if (summaryLine && summaryLine.includes("%") && /^.+:\s*\d+%$/.test(msg)) {
    return "";
  }
  return msg;
}

function formatModelDownloadActiveLine(prog) {
  const summary = formatModelProgressSummary(prog);
  return summary || String(prog?.message || "").trim() || t("settings.downloadingModel");
}

function splitModelCatalogLabel(label) {
  const text = String(label || "").trim();
  const sep = text.indexOf(" · ");
  if (sep > 0) {
    return { title: text.slice(0, sep), meta: text.slice(sep + 3) };
  }
  return { title: text, meta: "" };
}

function applyModelDownloadProgress(md, ui) {
  const active = Boolean(md?.active);
  const prog = md?.progress || {};
  const summary = formatModelProgressSummary(prog);
  const activeLine = formatModelDownloadActiveLine(prog);
  if (ui.progressEl) {
    ui.progressEl.hidden = !active;
    if (active && prog.fraction != null && prog.indeterminate === false) {
      ui.progressEl.indeterminate = false;
      ui.progressEl.value = Math.round(Number(prog.fraction) * 100);
    } else if (active) {
      ui.progressEl.removeAttribute("value");
      ui.progressEl.indeterminate = true;
    }
  }
  if (ui.progressFillEl) {
    ui.progressFillEl.hidden = !active;
    if (active && prog.fraction != null && prog.indeterminate === false) {
      ui.progressFillEl.style.width = `${Math.round(Number(prog.fraction) * 100)}%`;
    } else if (active) {
      ui.progressFillEl.style.width = "35%";
    }
  }
  if (ui.progressPctEl) {
    ui.progressPctEl.hidden = !active || !summary;
    ui.progressPctEl.textContent = summary;
  }
  if (ui.progressLabelEl) {
    ui.progressLabelEl.hidden = !active;
    ui.progressLabelEl.textContent = active ? t("settings.downloadingModel") : "";
  }
  if (ui.summaryEl) {
    const detail = modelDownloadDetailLine(prog, activeLine);
    ui.summaryEl.hidden = !active || !detail;
    ui.summaryEl.textContent = detail;
  }
  if (ui.statusEl) {
    if (active) {
      if (ui.summaryEl) {
        ui.statusEl.hidden = true;
        ui.statusEl.textContent = "";
      } else {
        const detail = modelDownloadDetailLine(prog, formatModelDownloadActiveLine(prog));
        ui.statusEl.hidden = !detail;
        ui.statusEl.textContent = detail;
      }
    }
  }
  if (ui.stalledEl) {
    const stalled = Boolean(active && prog.stalled);
    ui.stalledEl.hidden = !stalled;
    ui.stalledEl.textContent = stalled
      ? t("settings.modelDownloadStalled") || t("firstRun.engineProgressStalledVpn")
      : "";
  }
  if (ui.waitHintEl) {
    ui.waitHintEl.hidden = !active;
    if (active) {
      ui.waitHintEl.textContent = t("modelSetup.downloadWaitHint");
    }
  }
  return summary;
}

let lastProxySettings = null;

const PROXY_ROUTE_TARGETS = [
  ["openrouter", "#spoiler-openrouter"],
  ["groq", '[data-http-preset="groq"]'],
  ["openai", '[data-http-preset="openai"]'],
  ["gladia", '[data-http-preset="gladia"]'],
  ["deepgram", '[data-http-preset="deepgram"]'],
  ["custom", "#spoiler-custom"],
  ["gemini", "#spoiler-gemini"],
  ["youtube", "#spoiler-apify"],
];

function updateProxyServiceBadges(cfg) {
  lastProxySettings = cfg || null;
  const enabled = Boolean(cfg?.enabled);
  const targets = cfg?.targets || {};
  for (const [targetId, selector] of PROXY_ROUTE_TARGETS) {
    const root = document.querySelector(selector);
    if (!root) {
      continue;
    }
    const summary = root.querySelector("summary");
    if (!summary) {
      continue;
    }
    let badge = summary.querySelector(".proxy-route-badge");
    if (!badge) {
      badge = document.createElement("span");
      badge.className = "proxy-route-badge material-symbols-outlined";
      badge.setAttribute("aria-label", t("settings.proxyAria"));
      badge.title = t("settings.proxyTitle");
      badge.textContent = "vpn_lock";
      const wrap = summary.querySelector(".spoiler-meta-wrap");
      if (wrap) {
        summary.insertBefore(badge, wrap);
      } else {
        summary.appendChild(badge);
      }
    }
    badge.hidden = !(enabled && targets[targetId]);
  }
}

export function openSettingsModal(spoilerId = "") {
  const settingsModal = document.getElementById("settings-modal");
  if (settingsModal) {
    settingsModal.hidden = false;
  }
  if (spoilerId) {
    const tab = settingsTabForSpoiler(spoilerId);
    if (tab) {
      setSettingsBentoTab(tab, { persist: false });
    }
    const spoiler =
      document.getElementById(`spoiler-${spoilerId}`) ||
      document.querySelector(`[data-http-preset="${spoilerId}"]`);
    if (spoiler) {
      if (spoiler.tagName === "DETAILS") {
        spoiler.open = true;
      }
      window.requestAnimationFrame(() => {
        spoiler.scrollIntoView({ block: "nearest", behavior: "smooth" });
      });
    }
  } else {
    restoreSettingsBentoTab();
  }
  refreshSettingsCloudTabMeta();
  refreshExportFavoriteDirsSettings().catch((err) =>
    reportError(t("settings.exportFavoriteDirsTitle"), err)
  );
  const refresh = window.refreshSetupAndDownloadUi;
  if (typeof refresh === "function") {
    refresh().catch((err) => reportError(t("nav.settings"), err));
  }
}

const SETTINGS_BENTO_TAB_KEY = "settings-bento-tab";
const SETTINGS_BENTO_DEFAULT_TAB = "asr";

const SETTINGS_SPOILER_TAB = {
  proxy: "proxy",
  apify: "youtube",
  openrouter: "cloud",
  gemini: "cloud",
  custom: "cloud",
  gladia: "cloud",
  groq: "cloud",
  deepgram: "cloud",
  openai: "cloud",
};

function settingsTabForSpoiler(spoilerId) {
  const key = String(spoilerId || "").trim().toLowerCase();
  if (!key) {
    return null;
  }
  return SETTINGS_SPOILER_TAB[key] || "cloud";
}

export function setSettingsBentoTab(tabId, options = {}) {
  const tab = String(tabId || SETTINGS_BENTO_DEFAULT_TAB);
  const panes = document.querySelectorAll(".settings-bento-pane");
  const buttons = document.querySelectorAll(".settings-bento-tab");
  panes.forEach((pane) => {
    const match = pane.id === `settings-pane-${tab}`;
    pane.hidden = !match;
  });
  buttons.forEach((btn) => {
    const match = btn.getAttribute("data-settings-tab") === tab;
    btn.classList.toggle("is-active", match);
    btn.setAttribute("aria-selected", match ? "true" : "false");
  });
  if (options.persist !== false) {
    try {
      sessionStorage.setItem(SETTINGS_BENTO_TAB_KEY, tab);
    } catch {
      /* ignore */
    }
  }
}

function restoreSettingsBentoTab() {
  let tab = SETTINGS_BENTO_DEFAULT_TAB;
  try {
    tab = sessionStorage.getItem(SETTINGS_BENTO_TAB_KEY) || SETTINGS_BENTO_DEFAULT_TAB;
  } catch {
    /* ignore */
  }
  if (!document.getElementById(`settings-pane-${tab}`)) {
    tab = SETTINGS_BENTO_DEFAULT_TAB;
  }
  setSettingsBentoTab(tab, { persist: false });
}

function refreshSettingsCloudTabMeta() {
  const meta = document.getElementById("settings-tab-cloud-meta");
  const pane = document.getElementById("settings-pane-cloud");
  if (!meta || !pane) {
    return;
  }
  const n = pane.querySelectorAll(
    "[data-http-preset], #spoiler-openrouter, #spoiler-gemini, #spoiler-custom",
  ).length;
  meta.textContent = n > 0 ? `(${n})` : "";
}

function initSettingsBentoTabs() {
  const nav = document.querySelector(".settings-bento-tabs");
  const modal = document.getElementById("settings-modal");
  if (!nav) {
    return;
  }
  modal?.addEventListener("click", (event) => {
    const jump = event.target.closest("[data-settings-tab-jump]");
    if (!jump) {
      return;
    }
    const tab = jump.getAttribute("data-settings-tab-jump");
    if (tab) {
      setSettingsBentoTab(tab);
    }
  });
  nav.addEventListener("click", (event) => {
    const btn = event.target.closest(".settings-bento-tab");
    if (!btn) {
      return;
    }
    const tab = btn.getAttribute("data-settings-tab");
    if (tab) {
      setSettingsBentoTab(tab);
    }
  });
  restoreSettingsBentoTab();
  refreshSettingsCloudTabMeta();
}

function syncLocaleRadios() {
  const locale = getLocale();
  document.querySelectorAll('input[name="ui-locale"]').forEach((input) => {
    input.checked = input.value === locale;
  });
}

function refreshLocaleSettingsUi() {
  const block = document.getElementById("ui-locale-settings");
  if (!block) {
    return;
  }
  const legend = block.querySelector("legend");
  if (legend) {
    legend.textContent = t("settings.languageTitle");
  }
  block.querySelectorAll(".ui-locale-opt").forEach((label) => {
    const input = label.querySelector('input[name="ui-locale"]');
    const span = label.querySelector("span");
    if (!input || !span) {
      return;
    }
    const key = input.value === "en" ? "settings.languageEn" : "settings.languageRu";
    span.textContent = t(key);
  });
}

function initLocaleSettings() {
  const mount = document.getElementById("ui-locale-settings-mount");
  const asrField = document.getElementById("asr-source-field");
  if ((!mount && !asrField) || document.getElementById("ui-locale-settings")) {
    syncLocaleRadios();
    return;
  }
  const block = document.createElement(mount ? "div" : "fieldset");
  block.id = "ui-locale-settings";
  block.className = mount ? "ui-locale-settings" : "ui-locale-settings asr-source";
  if (!mount) {
    const legend = document.createElement("legend");
    legend.className = "asr-source-legend";
    legend.textContent = t("settings.languageTitle");
    block.appendChild(legend);
  }
  const row = document.createElement("div");
  row.className = "ui-locale-row";
  for (const [value, labelKey] of [
    ["ru", "settings.languageRu"],
    ["en", "settings.languageEn"],
  ]) {
    const label = document.createElement("label");
    label.className = "asr-source-opt ui-locale-opt";
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "ui-locale";
    input.value = value;
    input.addEventListener("change", () => {
      if (input.checked) {
        setLocale(value).catch((err) => reportError(t("settings.settingsError"), err));
      }
    });
    const span = document.createElement("span");
    span.textContent = t(labelKey);
    label.appendChild(input);
    label.appendChild(span);
    row.appendChild(label);
  }
  block.appendChild(row);
  if (mount) {
    mount.appendChild(block);
  } else {
    asrField.parentNode?.insertBefore(block, asrField);
  }
  syncLocaleRadios();
}

function initAppUpdates() {
  const wrap = document.getElementById("nav-check-updates-wrap");
  const openBtn = document.getElementById("btn-check-updates");
  const modal = document.getElementById("update-modal");
  const statusEl = document.getElementById("update-modal-status");
  const versionLine = document.getElementById("update-modal-version-line");
  const notesEl = document.getElementById("update-modal-notes");
  const progressEl = document.getElementById("update-modal-progress");
  const progressLabel = document.getElementById("update-modal-progress-label");
  const downloadBtn = document.getElementById("update-modal-download");
  const applyBtn = document.getElementById("update-modal-apply");
  const githubBtn = document.getElementById("update-modal-github");
  const closeBtn = document.getElementById("update-modal-close");
  const versionSettings = document.getElementById("settings-app-version");
  const sidebarVersion = document.getElementById("sidebar-app-version");
  const aboutLink = document.getElementById("nav-about");
  const supportLink = document.getElementById("nav-support");
  let pollTimer = null;
  let lastCheck = null;
  let releasesUrl = "";

  function wireExternalNavLink(link, url) {
    if (!link) {
      return;
    }
    const trimmed = String(url || "").trim();
    if (trimmed) {
      link.href = trimmed;
      link.classList.remove("is-disabled");
      link.removeAttribute("aria-disabled");
    } else {
      link.href = "#";
      link.classList.add("is-disabled");
      link.setAttribute("aria-disabled", "true");
    }
  }

  function bindExternalNavClick(link, titleKey) {
    link?.addEventListener("click", async (event) => {
      const url = String(link.getAttribute("href") || "").trim();
      if (!url || url === "#") {
        event.preventDefault();
        return;
      }
      const bridge = window.pywebview?.api;
      if (bridge?.open_url) {
        event.preventDefault();
        try {
          await bridge.open_url(url);
        } catch (err) {
          reportError(t(titleKey), err);
        }
      }
    });
  }

  function stopPoll() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function resetModalUi() {
    stopPoll();
    if (progressEl) {
      progressEl.hidden = true;
      progressEl.value = 0;
    }
    if (progressLabel) {
      progressLabel.hidden = true;
      progressLabel.textContent = "";
    }
    if (notesEl) {
      notesEl.hidden = true;
      notesEl.textContent = "";
    }
    if (versionLine) {
      versionLine.hidden = true;
    }
    downloadBtn?.setAttribute("hidden", "");
    applyBtn?.setAttribute("hidden", "");
    githubBtn?.setAttribute("hidden", "");
  }

  function closeModal() {
    resetModalUi();
    if (modal) {
      modal.hidden = true;
    }
  }

  function syncProgress(status) {
    const phase = status?.phase || "idle";
    const total = Number(status?.bytes_total) || 0;
    const done = Number(status?.bytes_done) || 0;
    if (phase === "downloading" && progressEl) {
      progressEl.hidden = false;
      if (total > 0) {
        progressEl.indeterminate = false;
        progressEl.value = Math.min(100, Math.round((done / total) * 100));
      } else {
        progressEl.indeterminate = true;
      }
      if (progressLabel) {
        progressLabel.hidden = false;
        progressLabel.textContent = t("updates.downloading");
      }
    }
    if (phase === "ready") {
      stopPoll();
      if (progressEl) {
        progressEl.hidden = false;
        progressEl.indeterminate = false;
        progressEl.value = 100;
      }
      if (progressLabel) {
        progressLabel.hidden = false;
        progressLabel.textContent = t("updates.downloadReady");
      }
      if (statusEl) {
        statusEl.textContent = t("updates.readyToInstall");
      }
      downloadBtn?.setAttribute("hidden", "");
      applyBtn?.removeAttribute("hidden");
    }
    if (phase === "error" && statusEl) {
      stopPoll();
      statusEl.textContent = status.error || t("updates.checkFailed");
      downloadBtn?.removeAttribute("hidden");
    }
  }

  function startPoll() {
    stopPoll();
    pollTimer = window.setInterval(async () => {
      try {
        const status = await api("/api/updates/status");
        syncProgress(status);
      } catch (err) {
        reportError(t("updates.title"), err);
        stopPoll();
      }
    }, 800);
  }

  async function runCheck() {
    resetModalUi();
    if (modal) {
      modal.hidden = false;
    }
    if (statusEl) {
      statusEl.textContent = t("updates.checking");
    }
    try {
      const result = await api("/api/updates/check", { method: "POST" });
      lastCheck = result;
      if (versionLine) {
        versionLine.hidden = false;
        versionLine.textContent = t("updates.currentVersion", {
          version: result.current_version,
        });
      }
      if (result.has_update) {
        if (statusEl) {
          statusEl.textContent = t("updates.available", { version: result.latest_version });
        }
        if (notesEl && result.release_notes) {
          notesEl.hidden = false;
          notesEl.textContent = result.release_notes;
        }
        if (result.expected_sha256) {
          downloadBtn?.removeAttribute("hidden");
        } else if (statusEl) {
          statusEl.textContent = t("updates.missingSha256");
          downloadBtn?.setAttribute("hidden", "");
        }
        githubBtn?.removeAttribute("hidden");
      } else if (result.newer_than_release) {
        if (statusEl) {
          statusEl.textContent = t("updates.newerThanRelease");
        }
      } else {
        if (statusEl) {
          statusEl.textContent = t("updates.upToDate", { version: result.current_version });
        }
      }
    } catch (err) {
      if (statusEl) {
        statusEl.textContent = err?.message || t("updates.checkFailed");
      }
    }
  }

  const devToolsBlock = document.getElementById("settings-dev-tools");
  const installedActionsBlock = document.getElementById("settings-installed-actions");
  const settingsCheckUpdatesBtn = document.getElementById("btn-settings-check-updates");
  const settingsAboutBtn = document.getElementById("btn-settings-about");
  const settingsSupportBtn = document.getElementById("btn-settings-support");
  let aboutUrl = "";
  let supportUrl = "";

  function syncSystemSettingsActions(info) {
    const installed = info?.install_kind === "installed";
    if (devToolsBlock) {
      devToolsBlock.hidden = installed;
    }
    if (installedActionsBlock) {
      installedActionsBlock.hidden = !installed;
    }
    if (settingsCheckUpdatesBtn) {
      settingsCheckUpdatesBtn.disabled = !info?.updates_enabled;
    }
    if (settingsAboutBtn) {
      settingsAboutBtn.disabled = !aboutUrl;
      settingsAboutBtn.setAttribute("aria-disabled", aboutUrl ? "false" : "true");
    }
    if (settingsSupportBtn) {
      settingsSupportBtn.disabled = !supportUrl;
      settingsSupportBtn.setAttribute("aria-disabled", supportUrl ? "false" : "true");
    }
  }

  async function openExternalUrl(url, titleKey) {
    const trimmed = String(url || "").trim();
    if (!trimmed || trimmed === "#") {
      return;
    }
    const bridge = window.pywebview?.api;
    if (bridge?.open_url) {
      try {
        await bridge.open_url(trimmed);
        return;
      } catch (err) {
        reportError(t(titleKey), err);
        return;
      }
    }
    window.open(trimmed, "_blank", "noopener");
  }

  async function bootstrapInfo() {
    try {
      const loc = getLocale();
      const info = await api(`/api/app/info?ui_locale=${encodeURIComponent(loc)}`);
      releasesUrl = info.releases_url || "";
      const marketing = resolveMarketingUrlsFromApi(info, loc);
      aboutUrl = marketing.about;
      supportUrl = marketing.support;
      if (wrap && openBtn) {
        wrap.hidden = !info.updates_enabled;
      }
      if (versionSettings && info.version) {
        versionSettings.hidden = false;
        versionSettings.textContent = t("updates.currentVersion", { version: info.version });
      }
      if (sidebarVersion && info.version) {
        sidebarVersion.hidden = false;
        sidebarVersion.textContent = t("common.appVersionShort", { version: info.version });
      }
      wireExternalNavLink(aboutLink, aboutUrl);
      wireExternalNavLink(supportLink, supportUrl);
      syncSystemSettingsActions(info);
    } catch (err) {
      console.error(err);
    }
  }

  openBtn?.addEventListener("click", () => {
    runCheck().catch((err) => reportError(t("updates.title"), err));
  });
  settingsCheckUpdatesBtn?.addEventListener("click", () => {
    runCheck().catch((err) => reportError(t("updates.title"), err));
  });
  settingsAboutBtn?.addEventListener("click", () => {
    openExternalUrl(aboutUrl, "nav.about");
  });
  settingsSupportBtn?.addEventListener("click", () => {
    openExternalUrl(supportUrl, "nav.supportThanks");
  });
  closeBtn?.addEventListener("click", () => closeModal());
  modal?.addEventListener("click", (event) => {
    if (event.target === modal) {
      closeModal();
    }
  });
  downloadBtn?.addEventListener("click", async () => {
    try {
      if (statusEl) {
        statusEl.textContent = t("updates.downloading");
      }
      downloadBtn.setAttribute("hidden", "");
      applyBtn?.setAttribute("hidden", "");
      await api("/api/updates/download", { method: "POST" });
      startPoll();
    } catch (err) {
      reportError(t("updates.title"), err);
    }
  });
  applyBtn?.addEventListener("click", async () => {
    const ok = window.confirm(t("updates.installConfirm"));
    if (!ok) {
      return;
    }
    try {
      await api("/api/updates/apply", { method: "POST" });
      showToast("updates.installLaunching");
    } catch (err) {
      reportError(t("updates.title"), err);
    }
  });
  githubBtn?.addEventListener("click", async () => {
    const url = lastCheck?.html_url || releasesUrl;
    if (!url) {
      return;
    }
    const bridge = window.pywebview?.api;
    if (bridge?.open_url) {
      try {
        await bridge.open_url(url);
        return;
      } catch (err) {
        reportError(t("updates.title"), err);
      }
    }
    window.open(url, "_blank", "noopener");
  });

  bindExternalNavClick(aboutLink, "nav.about");
  bindExternalNavClick(supportLink, "nav.supportThanks");

  onLocaleChange(() => {
    bootstrapInfo();
  });

  bootstrapInfo();
}

export function initShell() {
  onLocaleChange(() => {
    refreshLocaleSettingsUi();
  });
  initSidebarToggle();
  initSidebarResize();
  initLocaleSettings();
  initSettingsBentoTabs();
  initAppUpdates();

  const settingsModal = document.getElementById("settings-modal");
  const settingsClose = document.getElementById("settings-close");
  if (settingsClose && settingsModal) {
    settingsClose.addEventListener("click", () => {
      settingsModal.hidden = true;
    });
    settingsModal.addEventListener("click", (event) => {
      if (event.target === settingsModal) {
        settingsModal.hidden = true;
      }
    });
  }

  document.getElementById("btn-reload-ui")?.addEventListener("click", () => {
    showToast("settings.reloadingUi");
    window.setTimeout(() => reloadAppInterface(), 120);
  });
  document.getElementById("btn-reset-ui-cache")?.addEventListener("click", () => {
    localStorage.removeItem("legacy-expanded-batches");
    localStorage.removeItem(SELECTED_BATCH_KEY);
    localStorage.removeItem(NAV_STACK_KEY);
    showToast("settings.cacheCleared");
    window.setTimeout(() => reloadAppInterface(), 120);
  });
  document.getElementById("btn-open-logs")?.addEventListener("click", async () => {
    const bridge = window.pywebview?.api;
    if (!bridge?.open_logs_folder) {
      showToast("settings.logsDesktopOnly");
      return;
    }
    try {
      await bridge.open_logs_folder();
    } catch (err) {
      reportError(t("settings.openLogsFailed"), err);
    }
  });
  initComputeSettings();
  initAsrModelSettings();
  initProxySettings();
  initProvidersSettings();
  initExportFavoriteDirsSettings();
}

async function browseSettingsExportDir(input) {
  const bridge = window.pywebview?.api;
  if (!bridge?.pick_folder) {
    showToast("settings.exportFavoriteDirsDesktopOnly");
    return;
  }
  const folder = await bridge.pick_folder(input?.value || "");
  if (folder && input) {
    input.value = folder;
  }
}

function updateSettingsExportFavoritesCount() {
  const badge = document.getElementById("settings-export-favorites-count");
  const list = document.getElementById("settings-export-favorite-dirs");
  if (!badge || !list) {
    return;
  }
  badge.textContent = String(list.querySelectorAll(".export-dir-row").length);
}

async function refreshExportFavoriteDirsSettings() {
  const list = document.getElementById("settings-export-favorite-dirs");
  if (!list) {
    return;
  }
  const dirs = await fetchExportFavoriteDirs({ fresh: true });
  fillExportDirsList(list, dirs.length ? dirs : [""], {
    onBrowse: browseSettingsExportDir,
  });
  updateSettingsExportFavoritesCount();
}

function initExportFavoriteDirsSettings() {
  const list = document.getElementById("settings-export-favorite-dirs");
  const addBtn = document.getElementById("settings-export-favorite-add");
  const saveBtn = document.getElementById("settings-export-favorite-save");
  if (!list || !saveBtn) {
    return;
  }
  const observer = new MutationObserver(() => updateSettingsExportFavoritesCount());
  observer.observe(list, { childList: true });
  addBtn?.addEventListener("click", () => {
    addExportDirRowToList(list, "", { onBrowse: browseSettingsExportDir });
    list.querySelector(".export-dir-row:last-child .export-dir-input")?.focus();
    updateSettingsExportFavoritesCount();
  });
  saveBtn.addEventListener("click", () => {
    const dirs = collectDirsFromList(list);
    saveExportFavoriteDirs(dirs)
      .then(() => showToast("settings.exportFavoriteDirsSaved"))
      .catch((err) => reportError(t("settings.exportFavoriteDirsTitle"), err));
  });
}

function providerShortLabel(label) {
  const text = String(label || "").trim();
  if (!text) {
    return "";
  }
  const sep = text.indexOf(" · ");
  return sep > 0 ? text.slice(0, sep) : text;
}

function localModelReadySvg() {
  return `<svg class="local-model-status-icon local-model-status-ready" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>`;
}

function localModelPendingSvg() {
  return `<svg class="local-model-status-icon local-model-status-pending" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M6 2h12v3l-4 4 4 4v3H6v-3l4-4-4-4V2zm2 2v1.5l3 3.5 3-3.5V4H8zm8 16v-1.5l-3-3.5-3 3.5V20h8z"/></svg>`;
}

function localModelStatusSvg(ready) {
  return ready ? localModelReadySvg() : localModelPendingSvg();
}

function syncLocalModelPickerUi(picker, items, selectedId) {
  if (!picker?.btn || !picker.icon || !picker.label || !picker.list) {
    return;
  }
  const sublabelEl = document.getElementById("local-model-picker-sublabel");
  const selected =
    items.find((item) => item.id === selectedId) ||
    items.find((item) => item.ready) ||
    items[0] ||
    null;
  if (!selected) {
    picker.icon.innerHTML = "";
    picker.label.textContent = t("settings.noModels");
    if (sublabelEl) {
      sublabelEl.hidden = true;
      sublabelEl.textContent = "";
    }
    picker.btn.disabled = true;
    picker.list.replaceChildren();
    return;
  }
  picker.btn.disabled = false;
  picker.icon.innerHTML = localModelStatusSvg(Boolean(selected.ready));
  const parts = splitModelCatalogLabel(selected.label);
  picker.label.textContent = parts.title;
  if (sublabelEl) {
    if (parts.meta) {
      sublabelEl.hidden = false;
      sublabelEl.textContent = `· ${parts.meta}`;
    } else {
      sublabelEl.hidden = true;
      sublabelEl.textContent = "";
    }
  }
  picker.list.replaceChildren();
  for (const item of items) {
    const notReady = item.ready === false;
    const downloadable = item.downloadable === true;
    const li = document.createElement("li");
    li.className = "local-model-picker-option";
    li.setAttribute("role", "option");
    li.dataset.modelId = item.id;
    if (item.id === selected.id) {
      li.classList.add("is-selected");
      li.setAttribute("aria-selected", "true");
    } else {
      li.setAttribute("aria-selected", "false");
    }
    if (notReady && !downloadable) {
      li.classList.add("is-disabled");
    }
    const icon = document.createElement("span");
    icon.className = "local-model-picker-icon";
    icon.innerHTML = localModelStatusSvg(Boolean(item.ready));
    const body = document.createElement("div");
    body.className = "local-model-picker-option-body";
    const title = document.createElement("span");
    title.className = "local-model-picker-option-title";
    const labelParts = splitModelCatalogLabel(item.label);
    title.textContent = labelParts.title;
    body.appendChild(title);
    if (labelParts.meta) {
      const meta = document.createElement("span");
      meta.className = "local-model-picker-option-meta";
      meta.textContent = labelParts.meta;
      body.appendChild(meta);
    }
    const badge = document.createElement("span");
    badge.className = item.ready
      ? "local-model-picker-option-badge local-model-picker-option-badge-ready"
      : downloadable
        ? "local-model-picker-option-badge local-model-picker-option-badge-dl"
        : "local-model-picker-option-badge local-model-picker-option-badge-dl";
    badge.textContent = item.ready ? t("settings.modelReady") : t("settings.downloadModel");
    li.appendChild(icon);
    li.appendChild(body);
    li.appendChild(badge);
    picker.list.appendChild(li);
  }
}

function fillModelSelect(selectEl, items, selectedId, picker = null) {
  selectEl.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = t("settings.noModels");
    selectEl.appendChild(empty);
    selectEl.disabled = true;
    return;
  }
  selectEl.disabled = false;
  for (const item of items) {
    const opt = document.createElement("option");
    opt.value = item.id;
    const notReady = item.ready === false;
    const downloadable = item.downloadable === true;
    opt.textContent = item.label;
    opt.disabled = notReady && !downloadable;
    selectEl.appendChild(opt);
  }
  const match = [...selectEl.options].find((opt) => opt.value === selectedId && !opt.disabled);
  if (match) {
    selectEl.value = selectedId;
  } else {
    const ready = items.find((item) => item.ready);
    selectEl.value = ready ? ready.id : items[0]?.id || "";
  }
  if (picker) {
    syncLocalModelPickerUi(picker, items, selectEl.value);
  }
}

function setProviderReady(detailsEl, ready) {
  if (!detailsEl) {
    return;
  }
  const check = detailsEl.querySelector(".provider-ready-check");
  if (check) {
    check.hidden = !ready;
  }
  detailsEl.classList.toggle("provider-ready", Boolean(ready));
}

function pickRemoteModelId(data) {
  const items = data.items || [];
  const remoteItems = items.filter((item) => item.kind !== "local");
  const ready = remoteItems.filter((item) => item.ready);
  const selectedId = data.selected || "";
  const current = items.find((item) => item.id === selectedId);
  if (current && current.kind !== "local" && current.ready) {
    return current.id;
  }
  const remoteSelected = data.selected_remote || "";
  if (remoteSelected && ready.some((item) => item.id === remoteSelected)) {
    return remoteSelected;
  }
  return ready[0]?.id || "";
}

function initAsrModelSettings() {
  const localSelect = document.getElementById("asr-model-select-local");
  const providerField = document.getElementById("asr-provider-field");
  const providerLabel = document.getElementById("asr-provider-label");
  const providerSelectHint = document.getElementById("asr-provider-select-hint");
  const localFolderHint = document.getElementById("asr-local-folder-hint");
  const localModelPickerRoot = document.getElementById("local-model-picker");
  const localModelPicker = {
    btn: document.getElementById("local-model-picker-btn"),
    icon: document.getElementById("local-model-picker-icon"),
    label: document.getElementById("local-model-picker-label"),
    list: document.getElementById("local-model-picker-list"),
    dropdown: document.getElementById("local-model-picker-dropdown"),
  };
  const computeWrap = document.getElementById("compute-settings-wrap");
  const cloudBanner = document.getElementById("cloud-only-banner");
  const enableLocalBtn = document.getElementById("btn-enable-local-asr");
  const localRadio = document.querySelector('input[name="asr-source"][value="local"]');
  const downloadBtn = document.getElementById("btn-download-model");
  const downloadStatus = document.getElementById("model-download-status");
  const downloadProgressWrap = document.getElementById("settings-model-download-progress-wrap");
  const downloadProgressEl = document.getElementById("settings-model-download-progress");
  const downloadProgressFill = document.getElementById("settings-model-download-progress-fill");
  const downloadProgressPct = document.getElementById("settings-model-download-progress-pct");
  const downloadProgressLabel = document.getElementById("settings-model-download-progress-label");
  const downloadSummaryEl = document.getElementById("settings-model-download-summary");
  const downloadStalledEl = document.getElementById("settings-model-download-stalled");
  const downloadWaitHintEl = document.getElementById("settings-model-download-wait-hint");
  const gigaamVpnHint = document.getElementById("asr-model-gigaam-vpn-hint");
  const packagesHint = document.getElementById("asr-engine-packages-hint");
  const readyBadge = document.getElementById("asr-model-ready-badge");
  if (!localSelect) {
    return;
  }

  let lastModelsData = null;
  let lastProjectModelsPath = "";
  let lastStatusPayload = null;
  let lastSetupPayload = null;
  let modelPollTimer = null;
  let downloadTargetId = null;

  function localItemById(id) {
    const items = lastModelsData?.items || [];
    return items.find((item) => item.id === id && item.kind === "local");
  }

  function stopModelPoll() {
    if (modelPollTimer) {
      clearInterval(modelPollTimer);
      modelPollTimer = null;
    }
  }

  function clearSettingsDownloadProgressUi() {
    if (downloadProgressWrap) {
      downloadProgressWrap.hidden = true;
    }
    if (downloadProgressEl) {
      downloadProgressEl.hidden = true;
    }
    if (downloadProgressFill) {
      downloadProgressFill.hidden = true;
      downloadProgressFill.style.width = "0%";
    }
    if (downloadProgressPct) {
      downloadProgressPct.hidden = true;
      downloadProgressPct.textContent = "";
    }
    if (downloadProgressLabel) {
      downloadProgressLabel.hidden = true;
      downloadProgressLabel.textContent = "";
    }
    if (downloadSummaryEl) {
      downloadSummaryEl.hidden = true;
      downloadSummaryEl.textContent = "";
    }
    if (downloadStalledEl) {
      downloadStalledEl.hidden = true;
      downloadStalledEl.textContent = "";
    }
    if (downloadWaitHintEl) {
      downloadWaitHintEl.hidden = true;
      downloadWaitHintEl.textContent = "";
    }
    if (downloadStatus) {
      downloadStatus.classList.remove("is-spinning");
      downloadStatus.hidden = true;
      downloadStatus.textContent = "";
    }
  }

  function applyDownloadUi(status, setup) {
    lastStatusPayload = status;
    lastSetupPayload = setup;
    const isLocal = currentSource() === "local";
    const cloudOnly = Boolean(setup?.cloud_only);
    const enginePackages = Boolean(setup?.engine_packages);
    const md = status?.model_download || {};
    const active = Boolean(md.active);
    const item = localItemById(localSelect.value);
    const needsDownload = Boolean(item && !item.ready && item.downloadable);
    const showReady = isLocal && Boolean(item?.ready);
    const showBtn =
      isLocal && !cloudOnly && needsDownload && Boolean(item?.downloadable) && !active && !md.error;
    const btnEnabled = showBtn && enginePackages;

    if (readyBadge) {
      readyBadge.hidden = !showReady || active || Boolean(md.error);
    }
    if (downloadBtn) {
      downloadBtn.hidden = !showBtn;
      downloadBtn.disabled = !btnEnabled;
      if (showBtn && !enginePackages) {
        downloadBtn.title = t("settings.enginePackagesFirst");
      } else {
        downloadBtn.removeAttribute("title");
      }
    }
    if (packagesHint) {
      packagesHint.hidden = !(
        isLocal &&
        !Boolean(setup?.engine_packages) &&
        !Boolean(setup?.cloud_only)
      );
    }
    if (gigaamVpnHint) {
      const gigaamSelected = localSelect.value === "gigaam";
      gigaamVpnHint.hidden = !(
        isLocal &&
        !cloudOnly &&
        gigaamSelected &&
        (needsDownload || (active && md.id === "gigaam"))
      );
    }
    if (!isLocal) {
      clearSettingsDownloadProgressUi();
      return;
    }
    if (active) {
      if (downloadProgressWrap) {
        downloadProgressWrap.hidden = false;
      }
      applyModelDownloadProgress(md, {
        progressEl: downloadProgressEl,
        progressFillEl: downloadProgressFill,
        progressPctEl: downloadProgressPct,
        progressLabelEl: downloadProgressLabel,
        summaryEl: downloadSummaryEl,
        statusEl: downloadStatus,
        stalledEl: downloadStalledEl,
        waitHintEl: downloadWaitHintEl,
      });
      return;
    }
    if (md.error) {
      if (downloadProgressWrap) {
        downloadProgressWrap.hidden = false;
      }
      if (downloadProgressEl) {
        downloadProgressEl.hidden = true;
      }
      if (downloadSummaryEl) {
        downloadSummaryEl.hidden = true;
        downloadSummaryEl.textContent = "";
      }
      if (downloadStatus) {
        downloadStatus.hidden = false;
        downloadStatus.textContent = md.error;
      }
      return;
    }
    clearSettingsDownloadProgressUi();
  }

  async function refreshDownloadState() {
    const [status, setup] = await Promise.all([api("/api/status"), api("/api/setup")]);
    const md = status.model_download || {};
    const wasActive = Boolean(lastStatusPayload?.model_download?.active);
    applyDownloadUi(status, setup);
    if (md.active) {
      return;
    }
    stopModelPoll();
    if (md.error) {
      return;
    }
    if (wasActive && downloadTargetId) {
      await loadModels();
      const item = localItemById(downloadTargetId);
      if (item?.ready) {
        await setModel(downloadTargetId);
      }
      downloadTargetId = null;
    }
  }

  async function downloadModel() {
    if (!downloadBtn) {
      return;
    }
    const modelId = localSelect.value;
    const item = localItemById(modelId);
    if (!item || item.ready || !item.downloadable) {
      return;
    }
    if (!lastSetupPayload?.engine_packages) {
      showToast("settings.enginePackagesRequired");
      return;
    }
    downloadTargetId = modelId;
    downloadBtn.disabled = true;
    try {
      await api("/api/model/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: modelId }),
      });
      if (!modelPollTimer) {
        modelPollTimer = setInterval(
          () => refreshDownloadState().catch((err) => reportError(t("settings.modelStatus"), err)),
          1000,
        );
      }
      await refreshDownloadState();
    } catch (err) {
      if (downloadProgressWrap) {
        downloadProgressWrap.hidden = false;
      }
      if (downloadStatus) {
        downloadStatus.hidden = false;
        downloadStatus.textContent = err.message || String(err);
      }
      downloadBtn.disabled = false;
      downloadTargetId = null;
    }
  }

  downloadBtn?.addEventListener("click", () => downloadModel());
  window.syncModelDownloadUi = applyDownloadUi;
  window.refreshDownloadStateHook = refreshDownloadState;
  window.refreshSetupAndDownloadUi = async () => {
    await Promise.all([
      refreshDownloadState(),
      typeof window.refreshEngineSetupUi === "function"
        ? window.refreshEngineSetupUi()
        : Promise.resolve(),
    ]);
  };

  function currentSource() {
    const checked = document.querySelector('input[name="asr-source"]:checked');
    return checked ? checked.value : "local";
  }

  function syncProviderSelectHint() {
    if (providerSelectHint) {
      providerSelectHint.textContent = t("settings.providerSelectBelow");
    }
  }

  function setLocalPickerOpen(open) {
    if (!localModelPicker.list || !localModelPicker.btn) {
      return;
    }
    if (localModelPicker.dropdown) {
      localModelPicker.dropdown.hidden = !open;
    } else {
      localModelPicker.list.hidden = !open;
    }
    localModelPicker.btn.setAttribute("aria-expanded", open ? "true" : "false");
    localModelPicker.btn.classList.toggle("is-open", open);
  }

  function syncAsrModeChip() {
    const chip = document.getElementById("settings-asr-mode-chip");
    if (!chip) {
      return;
    }
    const isLocal = currentSource() === "local";
    chip.hidden = false;
    chip.classList.toggle("settings-bento-chip-active", isLocal);
    chip.classList.toggle("settings-bento-chip-cloud", !isLocal);
    chip.textContent = isLocal ? t("settings.chipActive") : t("settings.chipCloud");
  }

  function setSourceRadio(source) {
    document.querySelectorAll('input[name="asr-source"]').forEach((el) => {
      el.checked = el.value === source;
    });
    const providerOn = source === "provider";
    const cloudOnly = Boolean(dataCloudOnly);
    if (localRadio) {
      localRadio.disabled = cloudOnly;
    }
    const localDisabled = cloudOnly || providerOn || localSelect.options.length === 0;
    localSelect.disabled = localDisabled;
    if (localModelPicker.btn) {
      localModelPicker.btn.disabled = localDisabled;
    }
    if (localModelPickerRoot) {
      localModelPickerRoot.classList.toggle("is-disabled", localDisabled);
    }
    setLocalPickerOpen(false);
    syncProviderSelectHint();
    syncAsrModeChip();
    if (computeWrap) {
      computeWrap.classList.toggle("compute-settings-disabled", providerOn || cloudOnly);
    }
  }

  let dataCloudOnly = false;

  function applyCloudOnlyUi(cloudOnly) {
    dataCloudOnly = cloudOnly;
    if (cloudBanner) {
      cloudBanner.hidden = !cloudOnly;
    }
    if (enableLocalBtn) {
      enableLocalBtn.hidden = !cloudOnly;
    }
  }

  function renderModels(data) {
    lastModelsData = data;
    const items = data.items || [];
    const localItems = filterLocalModelsForUi(items.filter((item) => item.kind === "local"));
    const cloudOnly = Boolean(data.cloud_only);
    applyCloudOnlyUi(cloudOnly);
    let source = data.source === "provider" ? "provider" : "local";
    if (cloudOnly) {
      source = "provider";
    }
    fillModelSelect(localSelect, localItems, data.selected_local || data.selected, localModelPicker);
    setSourceRadio(source);
    const selectedId = data.selected || "";
    const remoteId = pickRemoteModelId(data);
    const current = items.find((item) => item.id === selectedId);
    const remoteCurrent = items.find((item) => item.id === remoteId);
    syncProviderSelectHint();
    if (providerLabel && providerField) {
      const showActive =
        source === "provider" && remoteCurrent?.ready && Boolean(remoteCurrent.label);
      providerField.hidden = !showActive;
      if (showActive) {
        providerLabel.textContent = providerShortLabel(remoteCurrent.label);
      }
    }
    const folder = String(data.project_models || (data.roots && data.roots[0]) || "").trim();
    lastProjectModelsPath = folder;
    if (localFolderHint) {
      if (source === "local" && folder) {
        localFolderHint.textContent = t("settings.modelsFolder", { folder });
        localFolderHint.hidden = false;
      } else {
        localFolderHint.hidden = true;
        localFolderHint.textContent = "";
      }
    }
    if (lastStatusPayload && lastSetupPayload) {
      applyDownloadUi(lastStatusPayload, lastSetupPayload);
    } else {
      refreshDownloadState().catch((err) => reportError(t("settings.modelStatus"), err));
    }
    updateAsrContextBar(data);
  }

  async function loadModels() {
    renderModels(await api("/api/models"));
  }

  async function setModel(id) {
    if (!id) {
      return;
    }
    try {
      const data = await api("/api/models", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id }),
      });
      renderModels(data);
      if (data.engine_restarted) {
        showToast("shell.k9427388");
      } else {
        showToast("shell.k8396814");
      }
    } catch (err) {
      showToast(err.message || String(err));
      await loadModels();
    }
  }

  enableLocalBtn?.addEventListener("click", async () => {
    try {
      await api("/api/setup/enable-local", { method: "POST" });
      showToast("shell.k7132874");
      applyCloudOnlyUi(false);
      const settingsBlock = document.getElementById("engine-setup-settings");
      if (settingsBlock) {
        settingsBlock.hidden = false;
      }
      await loadModels();
    } catch (err) {
      reportError(t("nav.settings"), err);
    }
  });

  document.querySelectorAll('input[name="asr-source"]').forEach((el) => {
    el.addEventListener("change", () => {
      if (!el.checked) {
        return;
      }
      if (el.value === "local") {
        setSourceRadio("local");
        if (dataCloudOnly) {
          showToast("shell.k4423275");
          setSourceRadio("provider");
          return;
        }
        const localItem = localItemById(localSelect.value);
        if (localItem?.ready) {
          setModel(localSelect.value);
        } else if (lastStatusPayload && lastSetupPayload) {
          applyDownloadUi(lastStatusPayload, lastSetupPayload);
        }
        return;
      }
      setSourceRadio("provider");
      syncProviderSelectHint();
      const remoteId = pickRemoteModelId(lastModelsData || {});
      if (!remoteId) {
        showToast("shell.k7050516");
        return;
      }
      setModel(remoteId);
      if (lastStatusPayload && lastSetupPayload) {
        applyDownloadUi(lastStatusPayload, lastSetupPayload);
      }
      return;
    });
  });
  localModelPicker.btn?.addEventListener("click", () => {
    if (localModelPicker.btn.disabled) {
      return;
    }
    setLocalPickerOpen(Boolean(localModelPicker.dropdown?.hidden ?? localModelPicker.list?.hidden));
  });

  localModelPicker.list?.addEventListener("click", (event) => {
    const option = event.target.closest(".local-model-picker-option");
    if (!option || option.classList.contains("is-disabled")) {
      return;
    }
    const modelId = option.dataset.modelId;
    if (!modelId) {
      return;
    }
    localSelect.value = modelId;
    const localItems = (lastModelsData?.items || []).filter((item) => item.kind === "local");
    syncLocalModelPickerUi(localModelPicker, localItems, modelId);
    setLocalPickerOpen(false);
    localSelect.dispatchEvent(new Event("change", { bubbles: true }));
  });

  document.addEventListener("click", (event) => {
    if (!localModelPickerRoot?.contains(event.target)) {
      setLocalPickerOpen(false);
    }
  });

  localSelect.addEventListener("change", () => {
    const picked = localItemById(localSelect.value);
    const localItems = (lastModelsData?.items || []).filter((item) => item.kind === "local");
    syncLocalModelPickerUi(localModelPicker, localItems, localSelect.value);
    if (lastStatusPayload && lastSetupPayload) {
      applyDownloadUi(lastStatusPayload, lastSetupPayload);
    }
    if (currentSource() !== "local") {
      return;
    }
    const item = picked;
    if (item?.ready) {
      setModel(localSelect.value);
    }
  });
  function syncLocalModelLabels() {
    if (!lastModelsData || !localSelect) {
      return;
    }
    const localItems = filterLocalModelsForUi(
      (lastModelsData.items || []).filter((item) => item.kind === "local"),
    );
    const selected =
      localSelect.value || lastModelsData.selected_local || lastModelsData.selected || "";
    fillModelSelect(localSelect, localItems, selected, localModelPicker);
    if (localFolderHint && lastProjectModelsPath && currentSource() === "local") {
      localFolderHint.textContent = t("settings.modelsFolder", { folder: lastProjectModelsPath });
      localFolderHint.hidden = false;
    }
    if (lastStatusPayload && lastSetupPayload) {
      applyDownloadUi(lastStatusPayload, lastSetupPayload);
    }
  }

  onLocaleChange(() => {
    syncLocalModelLabels();
    syncProviderSelectHint();
  });

  loadModels().catch((err) => reportError(t("settings.providersList"), err));
  refreshDownloadState().catch((err) => reportError(t("settings.modelStatus"), err));
  window.refreshAsrModels = loadModels;
}

function initProxySettings() {
  const proxyEnabled = document.getElementById("proxy-enabled");
  const proxyHost = document.getElementById("proxy-host");
  const proxyPort = document.getElementById("proxy-port");
  const proxyUsername = document.getElementById("proxy-username");
  const proxyPassword = document.getElementById("proxy-password");
  const proxyPasswordHint = document.getElementById("proxy-password-hint");
  const proxySummary = document.getElementById("proxy-summary");
  const proxyStatus = document.getElementById("proxy-status");
  const proxyTargetInputs = () =>
    Array.from(document.querySelectorAll("[data-proxy-target]"));

  function hydrateProxy(proxy) {
    const cfg = proxy || {};
    if (proxyEnabled) {
      proxyEnabled.checked = Boolean(cfg.enabled);
    }
    if (proxyHost) {
      proxyHost.value = cfg.host || "";
    }
    if (proxyPort) {
      proxyPort.value = cfg.port != null ? String(cfg.port) : "8080";
    }
    if (proxyUsername) {
      proxyUsername.value = cfg.username || "";
    }
    if (proxyPassword) {
      proxyPassword.value = "";
    }
    if (proxyPasswordHint) {
      proxyPasswordHint.textContent = cfg.password_set
        ? t("shell.k2661382")
        : t("shell.k8910786");
    }
    const targets = cfg.targets || {};
    for (const input of proxyTargetInputs()) {
      const id = input.getAttribute("data-proxy-target");
      input.checked = targets[id] !== false;
    }
    if (proxySummary) {
      if (!cfg.enabled) {
        proxySummary.textContent = t("shell.k1823824");
      } else {
        const n = proxyTargetInputs().filter((el) => el.checked).length;
        proxySummary.textContent = t("settings.proxyOnServers", { n });
      }
    }
    const proxyChip = document.getElementById("proxy-status-chip");
    if (proxyChip) {
      if (!cfg.enabled) {
        proxyChip.textContent = t("settings.proxyChipOff");
        proxyChip.classList.remove("is-on");
      } else {
        const n = proxyTargetInputs().filter((el) => el.checked).length;
        proxyChip.textContent = t("settings.proxyChipOn", { n });
        proxyChip.classList.add("is-on");
      }
    }
    const proxyShortcutDesc = document.getElementById("settings-asr-shortcut-proxy-desc");
    if (proxyShortcutDesc) {
      const n = proxyTargetInputs().length;
      proxyShortcutDesc.textContent = cfg.enabled
        ? t("settings.shortcutProxyOn", {
            n: proxyTargetInputs().filter((el) => el.checked).length,
          })
        : t("settings.shortcutProxyDesc", { n });
    }
    if (proxyStatus) {
      proxyStatus.textContent = cfg.enabled
        ? t("shell.k2415647")
        : "";
    }
    updateProxyServiceBadges(cfg);
  }

  function collectProxyTargets() {
    const targets = {};
    for (const input of proxyTargetInputs()) {
      const id = input.getAttribute("data-proxy-target");
      if (id) {
        targets[id] = input.checked;
      }
    }
    return targets;
  }

  const PROXY_RESTART_HINT =
    t("apiErrors.restartPython");

  async function loadProxy() {
    let data;
    try {
      data = await api("/api/proxy");
    } catch (err) {
      if (err.status === 404) {
        try {
          data = await api("/api/providers/proxy");
        } catch (retryErr) {
          if (retryErr.status === 404) {
            if (proxyStatus) {
              proxyStatus.textContent = PROXY_RESTART_HINT;
            }
            showToast(PROXY_RESTART_HINT);
            return null;
          }
          throw retryErr;
        }
      } else {
        throw err;
      }
    }
    hydrateProxy(data);
    return data;
  }

  document.getElementById("btn-proxy-save")?.addEventListener("click", async () => {
    try {
      const body = {
        enabled: Boolean(proxyEnabled?.checked),
        host: proxyHost?.value?.trim() || "",
        port: proxyPort?.value ? Number(proxyPort.value) : 8080,
        username: proxyUsername?.value?.trim() || "",
        targets: collectProxyTargets(),
      };
      if (proxyPassword?.value) {
        body.password = proxyPassword.value;
      }
      await api("/api/proxy", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      await loadProxy();
      showToast("settings.proxySaved");
    } catch (err) {
      showToast(err.message || String(err));
    }
  });

  loadProxy().catch((err) => {
    if (err.status === 404) {
      if (proxyStatus) {
        proxyStatus.textContent = PROXY_RESTART_HINT;
      }
      showToast(PROXY_RESTART_HINT);
      return;
    }
    reportError(t("settings.proxy"), err);
  });
}

function initProvidersSettings() {
  const keyInput = document.getElementById("openrouter-key");
  const keyHint = document.getElementById("openrouter-key-hint");
  const statusEl = document.getElementById("openrouter-status");
  const apifyKeyInput = document.getElementById("apify-key");
  const apifyKeyHint = document.getElementById("apify-key-hint");
  const apifySummary = document.getElementById("apify-summary");
  const listEl = document.getElementById("custom-providers-list");
  const customStatus = document.getElementById("custom-status");
  const geminiEl = document.getElementById("gemini-cli-status");
  const orSummary = document.getElementById("openrouter-summary");
  const orModelSelect = document.getElementById("openrouter-model");
  const customSummary = document.getElementById("custom-summary");
  const geminiSummary = document.getElementById("gemini-summary");
  const protocolSelect = document.getElementById("custom-protocol");
  const customEndpoint = document.getElementById("custom-endpoint");
  const customModel = document.getElementById("custom-model");
  const customHint = document.getElementById("custom-protocol-hint");

  const protocolHints = {
    openai: {
      hint: t("shell.k6478130"),
      endpoint: "https://api.example.com/v1",
      model: "whisper-1",
    },
    gladia: {
      hint: t("shell.k1449041"),
      endpoint: "https://api.gladia.io",
      model: "solaria-1",
    },
    deepgram: {
      hint: t("shell.k4522264"),
      endpoint: "https://api.deepgram.com",
      model: "nova-3",
    },
  };

  function applyCustomProtocol() {
    const spec = protocolHints[protocolSelect?.value] || protocolHints.openai;
    if (customHint) {
      customHint.textContent = spec.hint;
    }
    if (customEndpoint && !customEndpoint.value) {
      customEndpoint.placeholder = spec.endpoint;
    }
    if (customModel && !customModel.value) {
      customModel.placeholder = spec.model;
    }
  }

  protocolSelect?.addEventListener("change", () => {
    const spec = protocolHints[protocolSelect.value] || protocolHints.openai;
    if (customEndpoint) {
      customEndpoint.placeholder = spec.endpoint;
      if (!customEndpoint.value || Object.values(protocolHints).some((item) => item.endpoint === customEndpoint.value)) {
        customEndpoint.value = spec.endpoint;
      }
    }
    if (customModel && (!customModel.value || Object.values(protocolHints).some((item) => item.model === customModel.value))) {
      customModel.value = spec.model;
    }
    applyCustomProtocol();
  });

  function httpPresetRoots() {
    return [...document.querySelectorAll("[data-http-preset]")];
  }

  function fillOpenRouterModels(openrouter) {
    if (!orModelSelect) {
      return;
    }
    const models = openrouter.models || [];
    const current = String(openrouter.model || "").trim();
    const keySet = Boolean(openrouter.api_key_set);
    orModelSelect.replaceChildren();
    if (!models.length) {
      const opt = document.createElement("option");
      opt.value = current;
      opt.textContent = current || t("shell.k8699689");
      orModelSelect.appendChild(opt);
      orModelSelect.disabled = !keySet;
      return;
    }
    for (const item of models) {
      const opt = document.createElement("option");
      opt.value = item.id;
      opt.textContent = item.label || item.id;
      orModelSelect.appendChild(opt);
    }
    if (current && [...orModelSelect.options].some((opt) => opt.value === current)) {
      orModelSelect.value = current;
    } else if (orModelSelect.options.length) {
      orModelSelect.selectedIndex = 0;
    }
    orModelSelect.disabled = !keySet;
  }

  function hydrateHttpPresets(items) {
    const byId = {};
    for (const item of items || []) {
      byId[item.id] = item;
    }
    for (const root of httpPresetRoots()) {
      const item = byId[root.dataset.httpPreset] || {};
      const summary = root.querySelector("[data-http-summary]");
      const hint = root.querySelector("[data-http-key-hint]");
      const modelField = root.querySelector("[data-http-model]");
      const keyField = root.querySelector("[data-http-key]");
      applyProviderSecretField(keyField, item);
      if (summary) {
        summary.textContent = item.api_key_set ? t("shell.k2661382") : t("shell.k7848969");
      }
      setProviderReady(root, Boolean(item.api_key_set));
      if (hint) {
        hint.textContent = item.api_key_set
          ? t("shell.k9673863")
          : t("shell.k1609208");
      }
      if (modelField && item.model) {
        const known = [...modelField.options].map((opt) => opt.value);
        if (item.model && !known.includes(item.model)) {
          const extra = document.createElement("option");
          extra.value = item.model;
          extra.textContent = item.model;
          modelField.appendChild(extra);
        }
        modelField.value = item.model;
      }
    }
  }

  function bindHttpPresets() {
    for (const root of httpPresetRoots()) {
      const save = root.querySelector("[data-http-save]");
      if (!save || save.dataset.bound === "1") {
        continue;
      }
      save.dataset.bound = "1";
      save.addEventListener("click", async () => {
        const id = root.dataset.httpPreset;
        const keyField = root.querySelector("[data-http-key]");
        const modelField = root.querySelector("[data-http-model]");
        try {
          const body = {
            model: modelField?.value || "",
            ...secretBodyPatch(keyField),
          };
          await api(`/api/providers/http/${encodeURIComponent(id)}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          });
          await loadProviders();
          if (window.refreshAsrModels) {
            await window.refreshAsrModels();
          }
          showToast("shell.k8687358");
        } catch (err) {
          const msg = err.message || String(err);
          if (/method not allowed/i.test(msg)) {
            showToast(
              t("shell.k2594618")
            );
          } else {
            showToast(msg);
          }
        }
      });
    }
  }

  function renderCustom(items) {
    if (!listEl) {
      return;
    }
    listEl.replaceChildren();
    for (const item of items || []) {
      const row = document.createElement("div");
      row.className = "custom-provider-row";
      const text = document.createElement("div");
      const title = document.createElement("p");
      title.textContent = `${item.name} · ${item.protocol || "openai"} · ${item.model}`;
      const meta = document.createElement("p");
      meta.className = "hint";
      const keyBit = item.api_key_set ? t("shell.k2661382") : t("shell.k6187846");
      meta.textContent = `${item.endpoint} (${keyBit})`;
      text.append(title, meta);
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "ghost";
      remove.textContent = t("common.delete");
      remove.addEventListener("click", async () => {
        try {
          await api(`/api/providers/custom/${encodeURIComponent(item.id)}`, { method: "DELETE" });
          await loadProviders();
          if (window.refreshAsrModels) {
            await window.refreshAsrModels();
          }
          showToast("shell.k2082334");
        } catch (err) {
          showToast(err.message || String(err));
        }
      });
      row.append(text, remove);
      listEl.appendChild(row);
    }
  }

  async function loadProviders() {
    const data = await api("/api/providers");
    const openrouter = data.openrouter || {};
    const apify = data.apify || {};
    applyProviderSecretField(keyInput, openrouter);
    if (keyHint) {
      keyHint.textContent = openrouter.api_key_set
        ? t("shell.k9673863")
        : t("shell.k3676583");
    }
    if (orSummary) {
      orSummary.textContent = openrouter.api_key_set ? t("shell.k2661382") : t("shell.k7848969");
    }
    setProviderReady(document.getElementById("spoiler-openrouter"), Boolean(openrouter.api_key_set));
    applyProviderSecretField(apifyKeyInput, apify);
    if (apifyKeyHint) {
      apifyKeyHint.textContent = apify.api_key_set
        ? t("shell.k9673863")
        : t("shell.k5545555");
    }
    if (apifySummary) {
      apifySummary.textContent = apify.api_key_set ? t("shell.k2661382") : t("shell.k7848969");
    }
    setProviderReady(document.getElementById("spoiler-apify"), Boolean(apify.api_key_set));
    fillOpenRouterModels(openrouter);
    if (statusEl) {
      const n = (openrouter.models || []).length;
      statusEl.textContent = n
        ? t("settings.modelsInCache", { n })
        : openrouter.api_key_set
          ? t("shell.k6579453")
          : t("shell.k3564599");
    }
    hydrateHttpPresets(data.http);
    renderCustom(data.custom);
    const customItems = data.custom || [];
    const nCustom = customItems.length;
    const customReady = customItems.some((item) => item.api_key_set);
    if (customSummary) {
      customSummary.textContent = nCustom ? t("settings.customCount", { n: nCustom }) : t("shell.k5730508");
    }
    setProviderReady(document.getElementById("spoiler-custom"), customReady);
    if (geminiEl) {
      const gemini = (data.cli && data.cli.gemini) || {};
      geminiEl.textContent = gemini.found
        ? t("settings.geminiFound", { path: gemini.path })
        : t("shell.k8033786");
      if (geminiSummary) {
        geminiSummary.textContent = gemini.found ? t("shell.k1744704") : t("shell.k4143816");
      }
      setProviderReady(document.getElementById("spoiler-gemini"), Boolean(gemini.found));
    }
    updateProxyServiceBadges(lastProxySettings);
    return data;
  }

  document.getElementById("btn-apify-save")?.addEventListener("click", async () => {
    try {
      await api("/api/providers/apify", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(secretBodyPatch(apifyKeyInput)),
      });
      await loadProviders();
      showToast("shell.k9432551");
    } catch (err) {
      showToast(err.message || String(err));
    }
  });

  orModelSelect?.addEventListener("change", async () => {
    const model = orModelSelect.value;
    if (!model) {
      return;
    }
    try {
      await api("/api/providers/openrouter", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model }),
      });
      await loadProviders();
      if (window.refreshAsrModels) {
        await window.refreshAsrModels();
      }
      showToast("shell.k1105160");
    } catch (err) {
      showToast(err.message || String(err));
      await loadProviders();
    }
  });

  document.getElementById("btn-openrouter-save")?.addEventListener("click", async () => {
    try {
      const body = {
        ...secretBodyPatch(keyInput),
      };
      if (orModelSelect?.value) {
        body.model = orModelSelect.value;
      }
      await api("/api/providers/openrouter", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      await loadProviders();
      if (window.refreshAsrModels) {
        await window.refreshAsrModels();
      }
      showToast("shell.k5843282");
    } catch (err) {
      showToast(err.message || String(err));
    }
  });

  document.getElementById("btn-openrouter-refresh")?.addEventListener("click", async () => {
    try {
      await api("/api/providers/openrouter/refresh", { method: "POST" });
      await loadProviders();
      if (window.refreshAsrModels) {
        await window.refreshAsrModels();
      }
      showToast("shell.k5971760");
    } catch (err) {
      showToast(err.message || String(err));
    }
  });

  document.getElementById("btn-custom-add")?.addEventListener("click", async () => {
    const name = document.getElementById("custom-name");
    const endpoint = document.getElementById("custom-endpoint");
    const model = document.getElementById("custom-model");
    const key = document.getElementById("custom-key");
    try {
      await api("/api/providers/custom", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name?.value || "",
          protocol: protocolSelect?.value || "openai",
          endpoint: endpoint?.value || "",
          model: model?.value || "",
          ...secretBodyPatch(key),
        }),
      });
      if (name) name.value = "";
      if (endpoint) endpoint.value = "";
      if (model) model.value = "";
      if (key) {
        bindSecretInput(key, { full: "", masked: "", isSet: false });
      }
      await loadProviders();
      if (window.refreshAsrModels) {
        await window.refreshAsrModels();
      }
      showToast("shell.k2665954");
    } catch (err) {
      showToast(err.message || String(err));
      if (customStatus) {
        customStatus.textContent = err.message || String(err);
      }
    }
  });

  bindHttpPresets();
  loadProviders().catch((err) => reportError(t("settings.providers"), err));
  applyCustomProtocol();
}

function initComputeSettings() {
  const computeHintEl = document.getElementById("compute-hint");
  const dashboardHintEl = document.getElementById("dashboard-compute-hint");
  const settingsHintEl = document.getElementById("compute-hint-settings");

  function renderCompute(data) {
    document.querySelectorAll("[data-compute]").forEach((el) => {
      el.classList.toggle("is-active", el.dataset.compute === data.preference);
    });
    document.querySelectorAll('input[name="compute"]').forEach((el) => {
      el.checked = el.value === data.preference;
    });
    const expl = (data.explanations || {})[data.preference] || "";
    const device = data.effective === "gpu" ? "GPU" : "CPU";
    const cuda = data.cuda_available ? t("shell.k2698833") : t("shell.k8303939");
    const parts = [];
    if (expl) {
      parts.push(expl);
    }
    parts.push(t("settings.computeLine", { device, cuda }));
    if (data.warning) {
      parts.push(data.warning);
    }
    const text = parts.join(" ");
    if (computeHintEl) {
      computeHintEl.textContent = text;
      computeHintEl.classList.remove("is-warn");
    }
    if (dashboardHintEl) {
      dashboardHintEl.textContent = text;
      dashboardHintEl.classList.remove("is-warn");
    }
    if (settingsHintEl) {
      settingsHintEl.textContent = text;
      settingsHintEl.classList.remove("is-warn");
    }
    const liveEl = document.getElementById("settings-bento-compute-live");
    if (liveEl) {
      const device = data.effective === "gpu" ? "GPU" : "CPU";
      if (data.cuda_available && data.effective === "gpu") {
        liveEl.textContent = `CUDA (${device})`;
      } else if (data.preference === "auto") {
        liveEl.textContent = device;
      } else {
        liveEl.textContent = data.preference === "gpu" ? "GPU" : "CPU";
      }
      liveEl.hidden = false;
    }
  }

  async function loadCompute() {
    renderCompute(await api("/api/compute"));
  }

  async function setCompute(preference) {
    try {
      const data = await api("/api/compute", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preference }),
      });
      renderCompute(data);
      if (data.engine_restarted) {
        showToast(
          t("shell.k6987353")
        );
      }
    } catch (err) {
      showToast(err.message || String(err));
      await loadCompute();
    }
  }

  document.querySelectorAll("[data-compute]").forEach((el) => {
    el.addEventListener("click", () => setCompute(el.dataset.compute));
  });
  document.querySelectorAll('input[name="compute"]').forEach((el) => {
    el.addEventListener("change", () => {
      if (el.checked) {
        setCompute(el.value);
      }
    });
  });

  setTimeout(() => loadCompute().catch((err) => reportError(t("settings.computeSettings"), err)), 0);

  initEngineSetup();
}

function engineSetupShouldShowModal(status) {
  if (!status) {
    return false;
  }
  if (status.show_engine_setup_modal) {
    return true;
  }
  return (
    !status.engine_packages && !status.dismissed && !status.cloud_only
  );
}

export function openEngineSetupModalIfNeeded(status) {
  const modal = document.getElementById("engine-setup-modal");
  if (!modal || !engineSetupShouldShowModal(status)) {
    return false;
  }
  modal.hidden = false;
  const focusTarget =
    document.getElementById("engine-setup-continue") ||
    document.getElementById("engine-setup-opt-local");
  if (focusTarget && typeof focusTarget.focus === "function") {
    focusTarget.focus();
  }
  return true;
}

function setEngineChoiceUi(choice, optLocal, optCloud) {
  if (!optLocal || !optCloud) {
    return;
  }
  const pickLocal = choice === "local";
  optLocal.classList.toggle("is-active", pickLocal);
  optCloud.classList.toggle("is-active", !pickLocal);
  if (pickLocal) {
    optLocal.classList.add("border-2", "border-blue-600", "bg-blue-50/40");
    optLocal.classList.remove("border", "border-slate-200", "bg-slate-50/60");
    optCloud.classList.remove("is-active", "border-2", "border-blue-600", "bg-blue-50/40");
    optCloud.classList.add("border", "border-slate-200", "bg-slate-50/60");
  } else {
    optCloud.classList.add("border-2", "border-blue-600", "bg-blue-50/40");
    optCloud.classList.remove("border", "border-slate-200", "bg-slate-50/60");
    optLocal.classList.remove("is-active", "border-2", "border-blue-600", "bg-blue-50/40");
    optLocal.classList.add("border", "border-slate-200", "bg-slate-50/60");
  }
  const localDot = optLocal.querySelector(".slysh-radio-dot");
  const cloudDot = optCloud.querySelector(".slysh-radio-dot");
  if (localDot) {
    localDot.classList.toggle("bg-blue-600", pickLocal);
    localDot.classList.toggle("bg-transparent", !pickLocal);
  }
  if (cloudDot) {
    cloudDot.classList.toggle("bg-blue-600", !pickLocal);
    cloudDot.classList.toggle("bg-transparent", pickLocal);
  }
}

function initEngineSetup() {
  const modal = document.getElementById("engine-setup-modal");
  const confirmModal = document.getElementById("engine-packages-confirm-modal");
  const stepChoose = document.getElementById("engine-setup-step-choose");
  const stepInstall = document.getElementById("engine-setup-step-install");
  const optLocal = document.getElementById("engine-setup-opt-local");
  const optCloud = document.getElementById("engine-setup-opt-cloud");
  const continueBtn = document.getElementById("engine-setup-continue");
  const dismissBtn = document.getElementById("engine-setup-dismiss");
  const laterBtn = document.getElementById("engine-setup-later");
  const confirmStartBtn = document.getElementById("engine-packages-confirm-start");
  const confirmBackBtn = document.getElementById("engine-packages-confirm-back");
  const confirmLaterBtn = document.getElementById("engine-packages-confirm-later");
  const logEl = document.getElementById("engine-setup-log");
  const statusEl = document.getElementById("engine-setup-status");
  const progressWrap = document.getElementById("engine-setup-progress-wrap");
  const progressEl = document.getElementById("engine-setup-progress");
  const progressFill = document.getElementById("engine-setup-progress-fill");
  const progressPct = document.getElementById("engine-setup-progress-pct");
  const progressSummary = document.getElementById("engine-setup-progress-summary");
  const progressLabel = document.getElementById("engine-setup-progress-label");
  const progressHint = document.getElementById("engine-setup-progress-hint");
  const progressStalled = document.getElementById("engine-setup-progress-stalled");
  const logToggle = document.getElementById("engine-setup-log-toggle");
  const logToggleLabel = document.getElementById("engine-setup-log-toggle-label");
  const logChevron = document.getElementById("engine-setup-log-chevron");
  const choicesEl = document.querySelector(".engine-setup-choices");
  let engineChoice = "local";
  let engineInstallActivityKey = "";
  const settingsBlock = document.getElementById("engine-setup-settings");
  const resyncBlock = document.getElementById("engine-resync-settings");
  const settingsBtn = document.getElementById("btn-install-engine");
  const repairBtn = document.getElementById("btn-engine-repair");
  const settingsLog = document.getElementById("engine-setup-settings-log");
  const settingsError = document.getElementById("engine-setup-settings-error");
  let pollTimer = null;
  let logExpanded = false;
  let firstRunInstall = false;
  let confirmFromFirstRun = false;
  let offerModelAfterPackages = false;
  let wasInstalling = false;
  let installSuccessTimer = null;
  let installFinishHandled = false;
  const POLL_MS = 1000;

  function clearInstallSuccessTimer() {
    if (installSuccessTimer) {
      clearTimeout(installSuccessTimer);
      installSuccessTimer = null;
    }
  }

  function showInstallSuccessUi() {
    setEngineSetupPhase("install");
    if (progressWrap) {
      progressWrap.hidden = false;
    }
    if (progressEl) {
      progressEl.indeterminate = false;
      progressEl.value = 100;
    }
    if (progressFill) {
      progressFill.style.width = "100%";
    }
    if (progressPct) {
      progressPct.textContent = "100%";
    }
    if (progressSummary) {
      progressSummary.hidden = false;
      progressSummary.textContent = t("firstRun.engineInstallFastCache");
    }
    if (progressHint) {
      progressHint.hidden = true;
    }
    if (progressStalled) {
      progressStalled.hidden = true;
    }
    if (progressLabel) {
      progressLabel.textContent = t("firstRun.engineInstallDone");
    }
    if (logToggle) {
      logToggle.hidden = true;
    }
    if (statusEl) {
      statusEl.hidden = false;
      statusEl.classList.add("is-success");
      statusEl.textContent = t("firstRun.engineInstallDone");
    }
  }

  async function finishInstallFlow(status) {
    if (installFinishHandled) {
      return;
    }
    installFinishHandled = true;
    clearInstallSuccessTimer();
    const offerModel =
      offerModelAfterPackages ||
      firstRunInstall ||
      Boolean(status.pending_model_setup);
    offerModelAfterPackages = false;
    if (modal) {
      modal.hidden = false;
    }
    showInstallSuccessUi();
    showToast(t("firstRun.engineInstallDoneToast"));
    const pauseMs = offerModel ? 6000 : 4000;
    installSuccessTimer = window.setTimeout(async () => {
      installSuccessTimer = null;
      if (offerModel && typeof window.openModelSetupModal === "function") {
        await window.openModelSetupModal();
      }
      if (modal) {
        modal.hidden = true;
      }
      if (statusEl) {
        statusEl.classList.remove("is-success");
      }
      setEngineSetupPhase("choose");
    }, pauseMs);
  }

  function stopPoll() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function setEngineSetupPhase(phase) {
    const installing = phase === "install";
    if (stepChoose) {
      stepChoose.hidden = installing;
    }
    if (stepInstall) {
      stepInstall.hidden = !installing;
    }
  }

  function formatProgressSummary(ip) {
    const parts = [];
    const total = Number(ip.packages_total) || 0;
    const done = Number(ip.packages_done) || 0;
    const bt = Number(ip.bytes_total) || 0;
    const bd = Number(ip.bytes_done) || 0;
    if (total > 0) {
      parts.push(t("firstRun.engineProgressSummaryPackages", { done, total }));
    }
    if (bt > 0) {
      parts.push(
        t("firstRun.engineProgressSummaryVolume", {
          done: formatGiBApprox(bd),
          total: formatGiBApprox(bt),
        }),
      );
    }
    return parts.join(" · ");
  }

  function openConfirmModal(fromFirstRun) {
    confirmFromFirstRun = Boolean(fromFirstRun);
    if (confirmModal) {
      confirmModal.hidden = false;
    }
    if (fromFirstRun && modal) {
      modal.hidden = true;
    }
    setEngineSetupPhase("choose");
  }

  function closeConfirmModal() {
    if (confirmModal) {
      confirmModal.hidden = true;
    }
  }

  function engineDisplayFraction(ip, installing) {
    if (!installing) {
      return null;
    }
    if (ip.fraction != null && ip.indeterminate === false) {
      return Math.min(1, Math.max(0, Number(ip.fraction)));
    }
    const total = Number(ip.packages_total) || 0;
    const done = Number(ip.packages_done) || 0;
    if (total > 0) {
      return Math.min(1, Math.max(0, done / total));
    }
    return null;
  }

  function installScreenActive() {
    return Boolean(stepInstall && !stepInstall.hidden);
  }

  function shouldShowEngineInstallProgress(status) {
    return (
      Boolean(status.installing) ||
      (installScreenActive() && !status.engine_packages)
    );
  }

  function applyInstallProgress(status) {
    const ip = status.install_progress || {};
    if (status.installing) {
      setEngineSetupPhase("install");
    }
    const showProgress = shouldShowEngineInstallProgress(status);
    if (progressWrap) {
      progressWrap.hidden = !showProgress;
    }
    if (choicesEl) {
      choicesEl.hidden = Boolean(status.installing);
    }
    const displayFraction = engineDisplayFraction(ip, status.installing);
    if (progressEl) {
      if (showProgress && status.installing && displayFraction != null) {
        progressEl.indeterminate = false;
        progressEl.value = Math.round(displayFraction * 100);
      } else if (showProgress && status.installing) {
        progressEl.removeAttribute("value");
        progressEl.indeterminate = true;
      } else {
        progressEl.indeterminate = false;
      }
    }
    if (progressFill && showProgress) {
      if (status.installing && displayFraction != null) {
        const pct = Math.round(displayFraction * 100);
        progressFill.style.width = `${pct}%`;
        progressFill.classList.remove("slysh-progress-animated");
        if (progressPct) {
          progressPct.textContent = `${pct}%`;
        }
      } else if (status.installing) {
        const activityKey = `${ip.current_package || ""}|${ip.message || ""}|${ip.packages_done || 0}`;
        if (activityKey !== engineInstallActivityKey) {
          engineInstallActivityKey = activityKey;
        }
        const pulse = 28 + (engineInstallActivityKey.length % 45);
        progressFill.style.width = `${pulse}%`;
        progressFill.classList.add("slysh-progress-animated");
        if (progressPct) {
          progressPct.textContent = "";
        }
      } else {
        progressFill.style.width = "0%";
        progressFill.classList.remove("slysh-progress-animated");
        if (progressPct) {
          progressPct.textContent = "";
        }
      }
    } else if (progressFill && !showProgress) {
      progressFill.style.width = "0%";
      if (progressPct) {
        progressPct.textContent = "";
      }
    }
    if (progressSummary) {
      const summary = formatProgressSummary(ip);
      progressSummary.hidden = !status.installing || !summary;
      progressSummary.textContent = summary;
    }
    if (progressLabel) {
      if (status.installing) {
        const pkg = String(ip.current_package || "").trim();
        progressLabel.textContent =
          pkg || ip.message || t("firstRun.engineProgressWorking");
      } else if (showProgress) {
        progressLabel.textContent = t("firstRun.engineProgressWorking");
      } else {
        progressLabel.textContent = "";
      }
    }
    if (progressHint) {
      progressHint.hidden = !status.installing;
      progressHint.textContent = status.installing
        ? t("firstRun.engineInstallWaitHint")
        : "";
    }
    if (progressStalled) {
      progressStalled.hidden = true;
      progressStalled.textContent = "";
    }
    if (logToggle) {
      logToggle.hidden = !status.installing;
      const logLabel = logExpanded ? t("firstRun.engineHideLog") : t("firstRun.engineShowLog");
      if (logToggleLabel) {
        logToggleLabel.textContent = logLabel;
      } else {
        logToggle.textContent = logLabel;
      }
      if (logChevron) {
        logChevron.classList.toggle("rotate-180", logExpanded);
      }
    }
  }

  function engineNeedsResync(status) {
    return Boolean(
      status &&
        !status.cloud_only &&
        status.engine_packages &&
        (status.engine_resync_recommended || status.engine_slot_needs_resync),
    );
  }

  function apply(status) {
    const missing = !status.engine_packages;
    if (settingsBlock) {
      settingsBlock.hidden = !missing;
    }
    if (resyncBlock) {
      resyncBlock.hidden = !engineNeedsResync(status) || Boolean(status.installing);
    }
    const logText = status.log_tail || "";
    if (logEl) {
      const showLog =
        logText && (!status.installing || logExpanded);
      logEl.hidden = !showLog;
      logEl.textContent = logText;
      if (showLog) {
        logEl.scrollTop = logEl.scrollHeight;
      }
    }
    if (settingsLog) {
      settingsLog.hidden = !logText;
      settingsLog.textContent = logText;
      if (logText) {
        settingsLog.scrollTop = settingsLog.scrollHeight;
      }
    }
    if (settingsError) {
      if (missing && status.error) {
        settingsError.hidden = false;
        settingsError.textContent = status.error;
      } else {
        settingsError.hidden = true;
        settingsError.textContent = "";
      }
    }
    applyInstallProgress(status);
    const justFinished =
      wasInstalling && !status.installing && Boolean(status.engine_packages);
    wasInstalling = Boolean(status.installing);
    if (statusEl && !justFinished) {
      if (status.engine_packages && !status.installing) {
        statusEl.hidden = false;
        statusEl.textContent = status.pending_model_setup
          ? t("firstRun.engineInstallDone")
          : t("settings.readyToTranscribe");
      } else if (status.error) {
        statusEl.hidden = false;
        statusEl.textContent = status.error;
      } else if (status.installing) {
        statusEl.hidden = true;
        statusEl.textContent = "";
      } else {
        statusEl.hidden = true;
        statusEl.textContent = "";
      }
    }
    const busy = Boolean(status.installing);
    if (continueBtn) {
      continueBtn.disabled = busy || Boolean(status.engine_packages);
    }
    if (optLocal) {
      optLocal.setAttribute("aria-disabled", busy ? "true" : "false");
    }
    if (optCloud) {
      optCloud.setAttribute("aria-disabled", busy ? "true" : "false");
    }
    if (settingsBtn) {
      settingsBtn.disabled = busy || Boolean(status.engine_packages);
    }
    if (repairBtn) {
      repairBtn.disabled = busy;
    }
    if (laterBtn) {
      laterBtn.disabled = busy;
    }
    if (status.engine_packages && !status.installing) {
      stopPoll();
      if (typeof window.refreshDownloadStateHook === "function") {
        window.refreshDownloadStateHook().catch((err) =>
          reportError(t("settings.modelStatus"), err),
        );
      }
      if (justFinished) {
        finishInstallFlow(status);
      }
    } else if (!status.installing) {
      if (status.engine_packages || status.error || !installScreenActive()) {
        stopPoll();
      } else {
        startPoll();
      }
    }
  }

  async function refresh() {
    const status = await api("/api/setup/engine");
    apply(status);
    return status;
  }

  function startPoll() {
    if (pollTimer) {
      return;
    }
    pollTimer = setInterval(() => {
      refresh().catch((err) => reportError(t("settings.engineSetup"), err));
    }, POLL_MS);
  }

  async function startInstall(fromFirstRun = false) {
    firstRunInstall = Boolean(fromFirstRun);
    offerModelAfterPackages = Boolean(fromFirstRun);
    installFinishHandled = false;
    clearInstallSuccessTimer();
    if (modal) {
      modal.hidden = false;
    }
    setEngineSetupPhase("install");
    try {
      const body = fromFirstRun ? { mark_pending_model: true } : {};
      const status = await api("/api/setup/engine", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      apply(status);
      if (!status.engine_packages) {
        startPoll();
      }
    } catch (err) {
      reportError(t("settings.engineSetup"), err);
    }
  }

  async function startEngineRepair() {
    installFinishHandled = false;
    clearInstallSuccessTimer();
    if (modal) {
      modal.hidden = false;
    }
    setEngineSetupPhase("install");
    try {
      const status = await api("/api/setup/engine-repair", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force: false }),
      });
      apply(status);
      if (status.installing) {
        startPoll();
      }
    } catch (err) {
      reportError(t("settings.engineSetup"), err);
    }
  }

  let dismissInFlight = false;

  function dismiss() {
    if (dismissInFlight) {
      return;
    }
    dismissInFlight = true;
    if (laterBtn) {
      laterBtn.disabled = true;
    }
    if (confirmLaterBtn) {
      confirmLaterBtn.disabled = true;
    }
    closeConfirmModal();
    if (modal) {
      modal.hidden = true;
    }
    setEngineSetupPhase("choose");
    api("/api/setup/later", { method: "POST" })
      .catch((err) => reportError(t("settings.engineSetup"), err))
      .finally(() => {
        dismissInFlight = false;
        if (laterBtn) {
          laterBtn.disabled = false;
        }
        if (confirmLaterBtn) {
          confirmLaterBtn.disabled = false;
        }
      });
  }

  async function chooseCloudOnly() {
    try {
      const status = await api("/api/setup/cloud-only", { method: "POST" });
      apply(status);
      if (modal) {
        modal.hidden = true;
      }
      if (status.needs_provider) {
        showToast("settings.needProviderKey");
        openSettingsModal("openrouter");
      } else {
        showToast("settings.cloudOnlyOn");
      }
      if (typeof window.refreshAsrModels === "function") {
        await window.refreshAsrModels();
      }
    } catch (err) {
      reportError(t("settings.cloudMode"), err);
    }
  }

  setEngineChoiceUi(engineChoice, optLocal, optCloud);

  function onEngineOptActivate(choice) {
    if (wasInstalling) {
      return;
    }
    engineChoice = choice;
    setEngineChoiceUi(engineChoice, optLocal, optCloud);
  }

  optLocal?.addEventListener("click", () => onEngineOptActivate("local"));
  optCloud?.addEventListener("click", () => onEngineOptActivate("cloud"));
  optLocal?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onEngineOptActivate("local");
    }
  });
  optCloud?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onEngineOptActivate("cloud");
    }
  });

  continueBtn?.addEventListener("click", () => {
    if (engineChoice === "cloud") {
      chooseCloudOnly();
    } else {
      openConfirmModal(true);
    }
  });
  dismissBtn?.addEventListener("click", () => {
    if (wasInstalling) {
      return;
    }
    dismiss();
  });
  settingsBtn?.addEventListener("click", () => openConfirmModal(false));
  repairBtn?.addEventListener("click", () => {
    startEngineRepair().catch((err) => reportError(t("settings.engineSetup"), err));
  });
  laterBtn?.addEventListener("click", () => dismiss());

  modal?.addEventListener("click", (event) => {
    if (event.target !== modal || modal.hidden) {
      return;
    }
    if (wasInstalling) {
      return;
    }
    dismiss();
  });

  confirmStartBtn?.addEventListener("click", () => {
    closeConfirmModal();
    startInstall(confirmFromFirstRun);
  });
  confirmBackBtn?.addEventListener("click", () => {
    closeConfirmModal();
    if (confirmFromFirstRun && modal) {
      modal.hidden = false;
      setEngineSetupPhase("choose");
    }
  });
  confirmLaterBtn?.addEventListener("click", () => dismiss());

  logToggle?.addEventListener("click", () => {
    logExpanded = !logExpanded;
    if (logChevron) {
      logChevron.classList.toggle("rotate-180", logExpanded);
    }
    refresh().catch((err) => reportError(t("settings.engineSetup"), err));
  });

  initModelSetup();

  refresh()
    .then((status) => {
      if (
        engineNeedsResync(status) &&
        !sessionStorage.getItem("slysh-engine-resync-hint")
      ) {
        sessionStorage.setItem("slysh-engine-resync-hint", "1");
        showToast("updates.engineResync");
        openSettingsModal();
      }
      openEngineSetupModalIfNeeded(status);
      if (status.installing) {
        if (modal) {
          modal.hidden = false;
        }
        setEngineSetupPhase("install");
        startPoll();
      }
    })
    .catch((err) => reportError(t("settings.engineSetup"), err));

  window.refreshEngineSetupUi = refresh;
  window.openEngineSetupModalIfNeeded = openEngineSetupModalIfNeeded;
  window.openEnginePackagesConfirm = openConfirmModal;
}

function initModelSetup() {
  const modal = document.getElementById("model-setup-modal");
  const select = document.getElementById("model-setup-select");
  const downloadBtn = document.getElementById("model-setup-download");
  const laterBtn = document.getElementById("model-setup-later");
  const statusEl = document.getElementById("model-setup-status");
  const progressWrap = document.getElementById("model-setup-download-progress-wrap");
  const progressEl = document.getElementById("model-setup-progress");
  const progressFill = document.getElementById("model-setup-download-progress-fill");
  const progressPct = document.getElementById("model-setup-download-progress-pct");
  const progressLabel = document.getElementById("model-setup-download-progress-label");
  const progressSummary = document.getElementById("model-setup-progress-summary");
  const progressStalled = document.getElementById("model-setup-progress-stalled");
  const downloadWaitHint = document.getElementById("model-setup-download-wait-hint");
  const gigaamVpnHint = document.getElementById("model-setup-gigaam-vpn-hint");
  let pollTimer = null;
  let downloadTargetId = null;
  let lastModelSetupStatus = null;

  if (!modal || !select) {
    return;
  }

  function stopPoll() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function downloadableOptions(items) {
    return filterLocalModelsForUi(
      (items || []).filter(
        (item) => item.kind === "local" && item.downloadable && !item.ready,
      ),
    );
  }

  async function populateSelect() {
    const data = await api("/api/models");
    const options = downloadableOptions(data.items);
    select.replaceChildren();
    for (const item of options) {
      const opt = document.createElement("option");
      opt.value = item.id;
      opt.textContent = item.label || item.id;
      select.appendChild(opt);
    }
    const preferred =
      getLocale() === "en"
        ? options.find((item) => String(item.id || "").startsWith("whisper:"))
        : options.find((item) => item.id === GIGAAM_MODEL_ID);
    if (preferred) {
      select.value = preferred.id;
    } else if (options[0]) {
      select.value = options[0].id;
    }
    return options.length;
  }

  function syncGigaamVpnHint(status) {
    if (!gigaamVpnHint || !select) {
      return;
    }
    const md = status?.model_download || {};
    const active = Boolean(md.active);
    const show =
      select.value === "gigaam" || (active && md.id === "gigaam");
    gigaamVpnHint.hidden = !show;
  }

  function applyDownloadUi(status) {
    lastModelSetupStatus = status;
    const md = status?.model_download || {};
    const active = Boolean(md.active);
    syncGigaamVpnHint(status);
    if (progressWrap) {
      progressWrap.hidden = !active;
    }
    applyModelDownloadProgress(md, {
      progressEl,
      progressFillEl: progressFill,
      progressPctEl: progressPct,
      progressLabelEl: progressLabel,
      summaryEl: progressSummary,
      statusEl,
      stalledEl: progressStalled,
      waitHintEl: downloadWaitHint,
    });
    if (!active) {
      if (progressWrap) {
        progressWrap.hidden = true;
      }
      if (progressSummary) {
        progressSummary.hidden = true;
        progressSummary.textContent = "";
      }
      if (progressStalled) {
        progressStalled.hidden = true;
        progressStalled.textContent = "";
      }
      if (downloadWaitHint) {
        downloadWaitHint.hidden = true;
      }
      if (statusEl && md.error) {
        statusEl.hidden = false;
        statusEl.textContent = md.error;
      } else if (statusEl && !md.error) {
        statusEl.hidden = true;
        statusEl.textContent = "";
      }
    }
    if (downloadBtn) {
      downloadBtn.disabled = active || !select.value;
    }
    if (laterBtn) {
      laterBtn.disabled = active;
    }
    if (select) {
      select.disabled = active;
    }
  }

  async function refreshStatus() {
    const [status, setup] = await Promise.all([
      api("/api/status"),
      api("/api/setup"),
    ]);
    applyDownloadUi(status);
    const md = status.model_download || {};
    if (md.active) {
      return;
    }
    stopPoll();
    if (md.error) {
      return;
    }
    if (downloadTargetId) {
      const models = await api("/api/models");
      const item = (models.items || []).find(
        (row) => row.id === downloadTargetId,
      );
      if (item?.ready) {
        modal.hidden = true;
        showToast("settings.modelReady");
        if (typeof window.refreshAsrModels === "function") {
          await window.refreshAsrModels();
        }
        downloadTargetId = null;
      }
    }
    if (
      setup.pending_model_setup &&
      setup.engine_packages &&
      !setup.cloud_only &&
      modal.hidden &&
      (await populateSelect()) > 0
    ) {
      modal.hidden = false;
    }
  }

  async function openModelSetupModal() {
    const count = await populateSelect();
    modal.hidden = false;
    if (downloadBtn) {
      downloadBtn.disabled = count === 0;
    }
    if (count === 0 && statusEl) {
      statusEl.hidden = false;
      statusEl.textContent = t("modelSetup.copy");
    }
    applyDownloadUi(await api("/api/status"));
  }

  async function downloadSelected() {
    const modelId = select.value;
    if (!modelId) {
      return;
    }
    downloadTargetId = modelId;
    downloadBtn.disabled = true;
    try {
      await api("/api/model/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: modelId }),
      });
      if (!pollTimer) {
        pollTimer = setInterval(() => {
          refreshStatus().catch((err) =>
            reportError(t("modelSetup.title"), err),
          );
        }, 1000);
      }
      await refreshStatus();
    } catch (err) {
      downloadTargetId = null;
      if (statusEl) {
        statusEl.hidden = false;
        statusEl.textContent = err.message || String(err);
      }
      downloadBtn.disabled = false;
    }
  }

  let modelDismissInFlight = false;

  function dismissModelStep() {
    if (modelDismissInFlight) {
      return;
    }
    modelDismissInFlight = true;
    if (laterBtn) {
      laterBtn.disabled = true;
    }
    modal.hidden = true;
    stopPoll();
    api("/api/setup/model-later", { method: "POST" })
      .catch((err) => reportError(t("modelSetup.title"), err))
      .finally(() => {
        modelDismissInFlight = false;
        if (laterBtn) {
          laterBtn.disabled = false;
        }
      });
  }

  downloadBtn?.addEventListener("click", () => downloadSelected());
  laterBtn?.addEventListener("click", () => dismissModelStep());
  select?.addEventListener("change", () => {
    syncGigaamVpnHint(lastModelSetupStatus || {});
  });

  window.openModelSetupModal = () => {
    openModelSetupModal().catch((err) =>
      reportError(t("modelSetup.title"), err),
    );
  };
}

const SIDEBAR_COLLAPSED_KEY = "sidebar-collapsed";
const SIDEBAR_WIDTH_KEY = "sidebar-user-width";
const SIDEBAR_WIDTH_MIN = 200;
const SIDEBAR_WIDTH_MAX = 480;
const SIDEBAR_WIDTH_DEFAULT = 270;

function clampSidebarWidth(px) {
  return Math.min(SIDEBAR_WIDTH_MAX, Math.max(SIDEBAR_WIDTH_MIN, px));
}

function readSidebarWidth() {
  const raw = localStorage.getItem(SIDEBAR_WIDTH_KEY);
  const parsed = raw != null ? Number.parseInt(raw, 10) : Number.NaN;
  if (Number.isFinite(parsed)) {
    return clampSidebarWidth(parsed);
  }
  return SIDEBAR_WIDTH_DEFAULT;
}

function applySidebarWidth(px, persist = true) {
  const shell = document.getElementById("app-shell");
  if (!shell) {
    return;
  }
  const width = clampSidebarWidth(px);
  shell.style.setProperty("--sidebar-user-width", `${width}px`);
  if (persist) {
    localStorage.setItem(SIDEBAR_WIDTH_KEY, String(width));
  }
}

function initSidebarResize() {
  const shell = document.getElementById("app-shell");
  const sidebar = document.getElementById("sidebar");
  const resizer = document.getElementById("sidebar-resizer");
  if (!shell || !sidebar || !resizer) {
    return;
  }

  applySidebarWidth(readSidebarWidth(), false);

  const syncResizerLabels = () => {
    const label = t("sidebar.resizeWidth");
    resizer.title = label;
    resizer.setAttribute("aria-label", label);
  };
  syncResizerLabels();
  onLocaleChange(syncResizerLabels);

  bindPanelResizer(resizer, (delta) => {
    if (shell.classList.contains("is-sidebar-collapsed")) {
      return;
    }
    const next = clampSidebarWidth(sidebar.offsetWidth + delta);
    applySidebarWidth(next);
  });

  resizer.addEventListener("dblclick", () => {
    shell.style.removeProperty("--sidebar-user-width");
    localStorage.removeItem(SIDEBAR_WIDTH_KEY);
  });
}

function initSidebarToggle() {
  const shell = document.getElementById("app-shell");
  const toggle = document.getElementById("btn-sidebar-toggle");
  const icon = document.getElementById("sidebar-toggle-icon");
  if (!shell || !toggle) {
    return;
  }

  const applyCollapsed = (collapsed) => {
    shell.classList.toggle("is-sidebar-collapsed", collapsed);
    toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    toggle.title = collapsed ? t("settings.expandMenu") : t("settings.collapseMenu");
    if (icon) {
      icon.textContent = collapsed ? "chevron_right" : "chevron_left";
    }
  };

  applyCollapsed(false);
  localStorage.setItem(SIDEBAR_COLLAPSED_KEY, "0");

  toggle.addEventListener("click", () => {
    const next = !shell.classList.contains("is-sidebar-collapsed");
    applyCollapsed(next);
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, next ? "1" : "0");
  });
}
