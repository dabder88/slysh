import { api, showToast, isAbsolutePath } from "./api.js";
import { reportError } from "./errors.js";
import { navigate, getRoute, getEditorJobId } from "./router.js";
import { ensureIntakeAllowed } from "./intake-duplicate.js";
import { selectJob } from "./legacy.js";
import { refreshEditorJob } from "./editor.js";
import { localeDateTag, t } from "./i18n.js";
import { bindSecretInput, readSecretForSave } from "./secret-field.js";

function applyYoutubeApifyField(provider) {
  const input = document.getElementById("youtube-apify-key");
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

const METHOD_KEY = "youtube-method";
const BATCH_PREVIEW_KEY = "youtube-batch-preview-videos";

let youtubeInitialized = false;
let ingestPollTimer = null;
let youtubeBatchApiReady = false;

function selectedMethod() {
  const checked = document.querySelector('input[name="youtube-method"]:checked');
  return checked?.value || "apify";
}

function ingestMethod() {
  const method = selectedMethod();
  return method === "apify" ? "apify" : "ytdlp";
}

function saveMethodPreference() {
  localStorage.setItem(METHOD_KEY, selectedMethod());
  syncMethodPanels();
}

function loadMethodPreference() {
  const saved = localStorage.getItem(METHOD_KEY);
  const apify = document.getElementById("youtube-method-apify");
  const firefox = document.getElementById("youtube-method-firefox");
  const cookies = document.getElementById("youtube-method-cookies");
  if (!apify || !firefox || !cookies) {
    return;
  }
  if (saved === "firefox" || saved === "ytdlp") {
    firefox.checked = true;
  } else if (saved === "cookies") {
    cookies.checked = true;
  } else {
    apify.checked = true;
  }
  syncMethodPanels();
}

function syncMethodPanels() {
  document.querySelectorAll(".youtube-method-details").forEach((details) => {
    details.open = false;
  });
}

function renderStatusChip(el, ok, labelOk, labelBad) {
  if (!el) {
    return;
  }
  el.textContent = ok ? labelOk : labelBad;
  el.classList.toggle("youtube-status-chip--ok", ok);
  el.classList.toggle("youtube-status-chip--bad", !ok);
}

let youtubeBrowserCookie3 = false;

function setExtractCookiesEnabled(enabled) {
  const buttons = [
    document.getElementById("btn-youtube-extract-cookies"),
    document.getElementById("btn-youtube-extract-cookies-quick"),
  ];
  for (const btn of buttons) {
    if (!btn) {
      continue;
    }
    btn.disabled = !enabled;
    btn.title = enabled
      ? t("youtube.extractFirefox")
      : t("youtube.installCookie3");
  }
}

function updateCookiesMeta(status) {
  const firefoxMeta = document.getElementById("youtube-firefox-meta");
  const importMeta = document.getElementById("youtube-import-meta");
  const cookies = status.cookies || {};

  if (firefoxMeta) {
    if (cookies.present) {
      const when = cookies.updated_at
        ? new Date(cookies.updated_at).toLocaleString(localeDateTag())
        : "";
      firefoxMeta.textContent = when
        ? t("youtube.cookiesSavedWhen", { when })
        : t("youtube.k2719590");
    } else if (status.cookies_from_browser) {
      firefoxMeta.textContent =
        t("youtube.k6046160") +
        t("youtube.k673133");
    } else {
      const extra = status.browser_cookie3
        ? ""
        : t("youtube.k8575463");
      firefoxMeta.textContent = t("youtube.signInFirefox", { extra });
    }
  }

  if (importMeta) {
    if (cookies.present) {
      const when = cookies.updated_at
        ? new Date(cookies.updated_at).toLocaleString(localeDateTag())
        : "";
      importMeta.textContent = when
        ? t("youtube.cookiesFileLoadedWhen", { when })
        : t("youtube.k5982819");
    } else {
      importMeta.textContent = t("youtube.k7926877");
    }
  }
}

function updateApifyHint(status) {
  const hint = document.getElementById("youtube-apify-key-hint");
  if (!hint) {
    return;
  }
  const apify = status.apify || {};
  const keySet = Boolean(status.apify_key_set || apify.api_key_set);
  const tail = apify.api_key_masked || apify.api_key_tail || "";
  hint.textContent = keySet
    ? tail
      ? t("youtube.apifyKeyWithTail", { tail })
      : t("youtube.k6579778")
    : t("youtube.k1889791");
}

function syncYoutubeBatchStartButton() {
  const btn = document.getElementById("btn-youtube-batch-start");
  const hint = document.getElementById("youtube-batch-api-hint");
  if (btn) {
    btn.disabled = !youtubeBatchApiReady;
    btn.title = youtubeBatchApiReady
      ? ""
      : t("youtube.k2357567");
  }
  if (hint) {
    hint.hidden = youtubeBatchApiReady;
  }
}

async function refreshYoutubeStatus() {
  try {
    const status = await api("/api/youtube/status");
    youtubeBatchApiReady = Boolean(status.batch_api);
    syncYoutubeBatchStartButton();
    let apifyInfo = status.apify;
    if (status.apify_key_set && (!apifyInfo || !apifyInfo.api_key_tail)) {
      try {
        apifyInfo = await api("/api/providers/apify");
      } catch {
        apifyInfo = apifyInfo || {};
      }
    }
    youtubeBrowserCookie3 = Boolean(status.browser_cookie3);
    setExtractCookiesEnabled(youtubeBrowserCookie3);
    renderStatusChip(
      document.getElementById("youtube-status-apify"),
      status.apify_key_set,
      t("youtube.k8810962"),
      t("youtube.k7425484")
    );
    renderStatusChip(
      document.getElementById("youtube-status-firefox"),
      status.cookies_present || status.cookies_from_browser,
      status.cookies_from_browser && !status.cookies_present
        ? t("youtube.k138701")
        : t("youtube.k2719542"),
      t("youtube.k1382749")
    );
    renderStatusChip(
      document.getElementById("youtube-status-cookies-file"),
      status.cookies_present,
      t("youtube.k5747660"),
      t("youtube.k4769461")
    );
    renderStatusChip(
      document.getElementById("youtube-status-ytdlp"),
      status.ytdlp_found,
      t("youtube.k2998098"),
      t("youtube.k5362674")
    );
    renderStatusChip(
      document.getElementById("youtube-status-browser-cookie3"),
      status.browser_cookie3,
      t("youtube.k2514022"),
      t("youtube.k6508318")
    );
    updateCookiesMeta(status);
    const mergedApify = apifyInfo || status.apify || {};
    applyYoutubeApifyField(mergedApify);
    updateApifyHint({ ...status, apify: mergedApify });
  } catch (err) {
    reportError(t("youtube.k632702"), err);
  }
}

async function loadBrowserProfiles() {
  const select = document.getElementById("youtube-browser-profile");
  if (!select) {
    return;
  }
  select.innerHTML = "";
  try {
    const data = await api("/api/youtube/cookies/browsers");
    const profiles = (data.profiles || []).filter(
      (profile) => profile.browser === "firefox"
    );
    if (!profiles.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = data.hint || t("youtube.k324109");
      select.appendChild(option);
      return;
    }
    for (const profile of profiles) {
      const option = document.createElement("option");
      option.value = `${profile.browser}::${profile.profile}`;
      const suffix = profile.cookies_available === false ? t("youtube.k2517490") : "";
      const label = profile.label.replace(/^Firefox — /, "");
      option.textContent = `${label}${suffix}`;
      option.disabled = profile.cookies_available === false;
      if (profile.recommended && profile.cookies_available !== false) {
        option.dataset.recommended = "1";
      }
      select.appendChild(option);
    }
    const firstUsable = profiles.find((profile) => profile.cookies_available !== false);
    if (firstUsable) {
      select.value = `${firstUsable.browser}::${firstUsable.profile}`;
    }
  } catch (err) {
    reportError(t("youtube.k4573370"), err);
  }
}

async function pickCookiesFile() {
  if (window.pywebview?.api?.open_files) {
    const paths = await window.pywebview.api.open_files() || [];
    return paths[0] || "";
  }
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".txt,text/plain";
  await new Promise((resolve) => {
    input.addEventListener("change", () => resolve());
    input.click();
  });
  const file = input.files?.[0];
  const path = file?.pywebviewFullPath || file?.path || "";
  if (file && path && !isAbsolutePath(path)) {
    showToast("youtube.k2449802");
    return "";
  }
  return path;
}

function stopIngestPoll() {
  if (ingestPollTimer) {
    clearInterval(ingestPollTimer);
    ingestPollTimer = null;
  }
}

async function pollIngestJob(jobId) {
  const job = await api(`/api/jobs/${jobId}`);
  const statusEl = document.getElementById("youtube-ingest-status");
  const btn = document.getElementById("btn-youtube-ingest");
  const onEditor = getRoute() === "editor" && getEditorJobId() === jobId;

  if (job.status === "completed") {
    stopIngestPoll();
    if (btn) {
      btn.disabled = false;
    }
    if (onEditor) {
      if (statusEl) {
        statusEl.textContent = "";
      }
      const loaded = await selectJob(jobId);
      refreshEditorJob(loaded);
    } else {
      navigate("editor", { jobId });
      if (statusEl) {
        statusEl.textContent = "";
      }
    }
    return;
  }
  if (job.status === "failed") {
    stopIngestPoll();
    if (btn) {
      btn.disabled = false;
    }
    if (onEditor) {
      if (statusEl) {
        statusEl.textContent = "";
      }
      const loaded = await selectJob(jobId);
      refreshEditorJob(loaded);
    } else if (statusEl) {
      statusEl.textContent = job.error_text || t("youtube.k6715193");
    }
    showToast(job.error_text || t("youtube.k5630576"));
    return;
  }
  if (onEditor) {
    if (statusEl) {
      statusEl.textContent = "";
    }
    const loaded = await selectJob(jobId);
    refreshEditorJob(loaded);
    return;
  }
  if (statusEl) {
    statusEl.textContent = t("youtube.k4983190");
  }
}

async function ingestYoutube() {
  const urlInput = document.getElementById("youtube-url");
  const btn = document.getElementById("btn-youtube-ingest");
  const statusEl = document.getElementById("youtube-ingest-status");
  const url = (urlInput?.value || "").trim();
  if (!url) {
    showToast("youtube.k4404185");
    return;
  }
  const method = selectedMethod();
  const status = await api("/api/youtube/status");
  if (method === "apify") {
    const keySet = Boolean(status.apify_key_set || status.apify?.api_key_set);
    if (!keySet) {
      showToast("youtube.k1969104");
      syncMethodPanels();
      document.getElementById("youtube-apify-key")?.focus();
      return;
    }
  } else if (method === "firefox") {
    if (!status.cookies_present && !status.cookies_from_browser) {
      showToast("youtube.k2467724");
      syncMethodPanels();
      return;
    }
    if (!status.ytdlp_found) {
      showToast("youtube.k7094520");
      return;
    }
  } else if (method === "cookies") {
    if (!status.cookies_present) {
      showToast("youtube.k6063882");
      syncMethodPanels();
      return;
    }
    if (!status.ytdlp_found) {
      showToast("youtube.k7094520");
      return;
    }
  }
  if (btn) {
    btn.disabled = true;
  }
  if (statusEl) {
    statusEl.textContent = t("meeting.k9356652");
  }
  try {
    const allowed = await ensureIntakeAllowed({ youtubeUrls: [url] });
    if (!allowed) {
      if (btn) {
        btn.disabled = false;
      }
      if (statusEl) {
        statusEl.textContent = "";
      }
      return;
    }
    const job = await api("/api/youtube/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, method: ingestMethod(), language: "ru" }),
    });
    const jobId = Number(job?.id);
    if (!Number.isFinite(jobId)) {
      showToast(t("youtube.k5705747"));
      if (btn) {
        btn.disabled = false;
      }
      return;
    }
    if (statusEl) {
      statusEl.textContent = "";
    }
    navigate("editor", { jobId });
    stopIngestPoll();
    const runPoll = () =>
      pollIngestJob(jobId).catch((err) => {
        stopIngestPoll();
        if (btn) {
          btn.disabled = false;
        }
        reportError(t("youtube.k6357375"), err);
      });
    if (job.status === "completed" || job.status === "failed") {
      await runPoll();
      return;
    }
    runPoll();
    ingestPollTimer = setInterval(runPoll, 1000);
  } catch (err) {
    if (btn) {
      btn.disabled = false;
    }
    if (statusEl) {
      statusEl.textContent = "";
    }
    reportError(t("youtube.k5705747"), err);
  }
}

async function saveApifyKey() {
  const input = document.getElementById("youtube-apify-key");
  const key = readSecretForSave(input);
  if (key === undefined) {
    showToast("shell.k9432551");
    return;
  }
  if (!key) {
    showToast("youtube.k8956287");
    input?.focus();
    return;
  }
  try {
    await api("/api/providers/apify", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: key }),
    });
    showToast("shell.k9432551");
    await refreshYoutubeStatus();
  } catch (err) {
    reportError(t("youtube.k3925027"), err);
  }
}

async function extractCookiesQuick() {
  if (!youtubeBrowserCookie3) {
    showToast("youtube.installCookie3");
    return;
  }
  try {
    await api("/api/youtube/cookies/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ browser: "firefox", profile: "__default__" }),
    });
    showToast("youtube.k2038769");
    await refreshYoutubeStatus();
  } catch (err) {
    reportError(t("youtube.k979944"), err);
  }
}

async function extractCookies() {
  if (!youtubeBrowserCookie3) {
    showToast("youtube.installCookie3");
    return;
  }
  const select = document.getElementById("youtube-browser-profile");
  const value = select?.value || "";
  if (!value.includes("::")) {
    showToast("youtube.k4196813");
    return;
  }
  const [browser, profile] = value.split("::");
  if (browser !== "firefox") {
    showToast("youtube.k3044187");
    return;
  }
  try {
    await api("/api/youtube/cookies/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ browser, profile }),
    });
    showToast("youtube.k2719590");
    await refreshYoutubeStatus();
  } catch (err) {
    reportError(t("youtube.k4940459"), err);
  }
}

async function importCookies() {
  const path = await pickCookiesFile();
  if (!path) {
    return;
  }
  try {
    await api("/api/youtube/cookies/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    showToast("youtube.k7293933");
    await refreshYoutubeStatus();
  } catch (err) {
    reportError(t("youtube.k7811009"), err);
  }
}

function selectedBatchMode() {
  const checked = document.querySelector('input[name="youtube-batch-mode"]:checked');
  return checked?.value === "feed" ? "feed" : "lines";
}

function syncBatchSourcePanels() {
  const mode = selectedBatchMode();
  const linesWrap = document.getElementById("youtube-batch-lines-wrap");
  const feedWrap = document.getElementById("youtube-batch-feed-wrap");
  const filtersEl = document.querySelector(".youtube-batch-filters");
  if (linesWrap) {
    linesWrap.hidden = mode !== "lines";
  }
  if (feedWrap) {
    feedWrap.hidden = mode !== "feed";
  }
  if (filtersEl) {
    filtersEl.hidden = mode !== "feed";
  }
}

function isoDateToYyyymmdd(iso) {
  const s = (iso || "").trim();
  if (!s) {
    return null;
  }
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) {
    return null;
  }
  return `${m[1]}${m[2]}${m[3]}`;
}

function batchFiltersPayload() {
  const limitRaw = document.getElementById("youtube-batch-limit")?.value?.trim();
  const limit = limitRaw ? Number(limitRaw) : null;
  return {
    limit: Number.isFinite(limit) && limit > 0 ? limit : null,
    dateafter: isoDateToYyyymmdd(document.getElementById("youtube-batch-dateafter")?.value),
    datebefore: isoDateToYyyymmdd(document.getElementById("youtube-batch-datebefore")?.value),
    start_video: document.getElementById("youtube-batch-start-video")?.value?.trim() || null,
    direction: document.getElementById("youtube-batch-direction")?.value || "older",
  };
}

function batchResolveBody() {
  const mode = selectedBatchMode();
  return {
    mode,
    lines: document.getElementById("youtube-batch-lines")?.value || "",
    feed_url: document.getElementById("youtube-batch-feed-url")?.value?.trim() || "",
    filters: batchFiltersPayload(),
  };
}

function batchRulesPayload() {
  const exportEnabled = Boolean(document.getElementById("youtube-batch-export")?.checked);
  const dirs = collectYoutubeBatchExportDirs();
  return {
    batch_type: "youtube",
    skip_completed: Boolean(document.getElementById("youtube-batch-skip-completed")?.checked),
    export: exportEnabled,
    export_fmt: document.getElementById("youtube-batch-export-fmt")?.value || "md",
    export_dirs: dirs,
    export_dir_mode: dirs.length ? "fixed" : "beside_source",
    export_dir: dirs[0] || "",
    speakers: false,
  };
}

function syncYoutubeBatchExportOptions() {
  const enabled = Boolean(document.getElementById("youtube-batch-export")?.checked);
  document.getElementById("youtube-batch-export-options")?.toggleAttribute("hidden", !enabled);
}

async function pickYoutubeExportFolder(current = "") {
  if (window.pywebview?.api?.pick_folder) {
    const folder = await window.pywebview.api.pick_folder(current);
    return folder || "";
  }
  showToast("legacy.k379087");
  return "";
}

function createYoutubeExportDirRow(value = "") {
  const row = document.createElement("div");
  row.className = "export-dir-row field-row";

  const input = document.createElement("input");
  input.type = "text";
  input.className = "export-dir-input";
  input.spellcheck = false;
  input.value = value;

  const browseBtn = document.createElement("button");
  browseBtn.type = "button";
  browseBtn.className = "btn-outline btn-compact";
  browseBtn.title = t("common.browse");
  browseBtn.setAttribute("aria-label", t("common.browse"));
  browseBtn.innerHTML = '<span class="material-symbols-outlined" aria-hidden="true">folder_open</span>';
  browseBtn.addEventListener("click", async () => {
    const folder = await pickYoutubeExportFolder(input.value);
    if (folder) {
      input.value = folder;
    }
  });

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "btn-outline btn-compact export-dir-remove";
  removeBtn.title = t("common.delete");
  removeBtn.setAttribute("aria-label", t("common.delete"));
  removeBtn.innerHTML = '<span class="material-symbols-outlined" aria-hidden="true">close</span>';
  removeBtn.addEventListener("click", () => {
    const list = document.getElementById("youtube-batch-export-dirs");
    if (!list || list.querySelectorAll(".export-dir-row").length <= 1) {
      return;
    }
    row.remove();
    syncYoutubeExportDirRemoveButtons();
  });

  row.append(input, browseBtn, removeBtn);
  return row;
}

function syncYoutubeExportDirRemoveButtons() {
  const list = document.getElementById("youtube-batch-export-dirs");
  if (!list) {
    return;
  }
  const rows = list.querySelectorAll(".export-dir-row");
  const hideRemove = rows.length <= 1;
  rows.forEach((row) => {
    const btn = row.querySelector(".export-dir-remove");
    if (btn) {
      btn.hidden = hideRemove;
    }
  });
}

function addYoutubeExportDirRow(value = "") {
  const list = document.getElementById("youtube-batch-export-dirs");
  if (!list) {
    return;
  }
  list.appendChild(createYoutubeExportDirRow(value));
  syncYoutubeExportDirRemoveButtons();
}

function resetYoutubeBatchExportDirs() {
  const list = document.getElementById("youtube-batch-export-dirs");
  if (!list) {
    return;
  }
  list.replaceChildren();
  addYoutubeExportDirRow("");
}

function collectYoutubeBatchExportDirs() {
  const list = document.getElementById("youtube-batch-export-dirs");
  if (!list) {
    return [];
  }
  const seen = new Set();
  const unique = [];
  for (const input of list.querySelectorAll(".export-dir-input")) {
    const value = (input.value || "").trim();
    if (!value) {
      continue;
    }
    const key = value.toLowerCase();
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    unique.push(value);
  }
  return unique;
}

function setYoutubeScreenMode(mode) {
  const single = mode !== "batch";
  document.getElementById("youtube-single-panel")?.toggleAttribute("hidden", !single);
  document.getElementById("youtube-single-actions")?.toggleAttribute("hidden", !single);
  document.getElementById("youtube-ingest-status")?.toggleAttribute("hidden", !single);
  document.getElementById("youtube-batch-panel")?.toggleAttribute("hidden", single);
  document.getElementById("youtube-mode-single")?.classList.toggle("is-active", single);
  document.getElementById("youtube-mode-batch")?.classList.toggle("is-active", !single);
}

async function resolveYoutubeBatch() {
  const preview = document.getElementById("youtube-batch-preview");
  const statusEl = document.getElementById("youtube-batch-status");
  if (statusEl) {
    statusEl.textContent = t("youtube.k2338209");
  }
  try {
    const body = await api("/api/youtube/batch/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(batchResolveBody()),
    });
    sessionStorage.setItem(BATCH_PREVIEW_KEY, JSON.stringify(body.videos || []));
    const count = body.count ?? (body.videos || []).length;
    const existingCount = (body.videos || []).filter((v) => v.existing_job).length;
    if (preview) {
      const sample = (body.videos || [])
        .slice(0, 3)
        .map((v) => v.title || v.video_id)
        .join("; ");
      let text = sample
        ? t("youtube.videosFoundSample", {
            count,
            sample,
            suffix: count > 3 ? "…" : "",
          })
        : t("youtube.videosFound", { count });
      if (existingCount > 0) {
        text += t("youtube.videosAlreadyTranscribed", { count: existingCount });
      }
      preview.textContent = text;
    }
    if (statusEl) {
      statusEl.textContent = "";
    }
    showToast(t("youtube.videosInList", { count }));
  } catch (err) {
    if (statusEl) {
      statusEl.textContent = "";
    }
    reportError(t("youtube.k7159355"), err);
  }
}

async function postYoutubeBatchCreate(payload) {
  const opts = {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  };
  try {
    return await api("/api/youtube/batch", opts);
  } catch (err) {
    if (err?.status === 405) {
      return await api("/api/youtube/batch/create", opts);
    }
    throw err;
  }
}

async function startYoutubeBatch() {
  if (!youtubeBatchApiReady) {
    showToast(
      t("youtube.k9393218")
    );
    return;
  }
  const statusEl = document.getElementById("youtube-batch-status");
  const btn = document.getElementById("btn-youtube-batch-start");
  if (btn) {
    btn.disabled = true;
  }
  if (statusEl) {
    statusEl.textContent = t("youtube.k4356336");
  }
  try {
    const resolveBody = batchResolveBody();
    const resolved = await api("/api/youtube/batch/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(resolveBody),
    });
    const urls = (resolved.videos || []).map((v) => v.url).filter(Boolean);
    const allowed = await ensureIntakeAllowed({ youtubeUrls: urls });
    if (!allowed) {
      return;
    }
    const payload = {
      ...resolveBody,
      method: ingestMethod(),
      language: "ru",
      rules: batchRulesPayload(),
      autostart: true,
    };
    const batch = await postYoutubeBatchCreate(payload);
    showToast(
      t("youtube.batchStartedVideos", { name: batch.name, count: batch.total_count })
    );
    navigate("queue");
  } catch (err) {
    reportError(t("youtube.batchStartFailed"), err);
  } finally {
    if (btn) {
      btn.disabled = false;
    }
    syncYoutubeBatchStartButton();
    if (statusEl) {
      statusEl.textContent = "";
    }
  }
}

export function initYoutube() {
  if (youtubeInitialized) {
    return;
  }
  youtubeInitialized = true;
  loadMethodPreference();
  document.querySelectorAll('input[name="youtube-method"]').forEach((radio) => {
    radio.addEventListener("change", saveMethodPreference);
  });
  document.getElementById("btn-youtube-ingest")?.addEventListener("click", () => {
    ingestYoutube().catch((err) => showToast(err.message || String(err)));
  });
  document.getElementById("btn-youtube-apify-save")?.addEventListener("click", () => {
    saveApifyKey().catch((err) => showToast(err.message || String(err)));
  });
  document.getElementById("btn-youtube-extract-cookies-quick")?.addEventListener("click", () => {
    extractCookiesQuick().catch((err) => showToast(err.message || String(err)));
  });
  document.getElementById("btn-youtube-extract-cookies")?.addEventListener("click", () => {
    extractCookies().catch((err) => showToast(err.message || String(err)));
  });
  document.getElementById("btn-youtube-import-cookies")?.addEventListener("click", () => {
    importCookies().catch((err) => showToast(err.message || String(err)));
  });
  document.getElementById("youtube-mode-single")?.addEventListener("click", (event) => {
    event.stopPropagation();
    setYoutubeScreenMode("single");
  });
  document.getElementById("youtube-mode-batch")?.addEventListener("click", (event) => {
    event.stopPropagation();
    setYoutubeScreenMode("batch");
    syncBatchSourcePanels();
  });
  document.querySelectorAll('input[name="youtube-batch-mode"]').forEach((radio) => {
    radio.addEventListener("change", syncBatchSourcePanels);
  });
  document.getElementById("btn-youtube-batch-resolve")?.addEventListener("click", () => {
    resolveYoutubeBatch().catch((err) => showToast(err.message || String(err)));
  });
  document.getElementById("btn-youtube-batch-start")?.addEventListener("click", () => {
    startYoutubeBatch().catch((err) => showToast(err.message || String(err)));
  });
  document.getElementById("youtube-batch-export")?.addEventListener("change", syncYoutubeBatchExportOptions);
  document.getElementById("youtube-batch-export-dir-add")?.addEventListener("click", () => {
    addYoutubeExportDirRow("");
  });
  resetYoutubeBatchExportDirs();
  syncYoutubeBatchExportOptions();
  setYoutubeScreenMode("single");
  syncBatchSourcePanels();
}

export function onYoutubeShow() {
  loadMethodPreference();
  refreshYoutubeStatus();
  loadBrowserProfiles();
  syncYoutubeBatchExportOptions();
}
