const workspacePanel = document.getElementById("workspace");
const livePanel = document.getElementById("live");
const filesChrome = document.getElementById("files-chrome");
const batchesChrome = document.getElementById("batches-chrome");
const jobListEl = document.getElementById("job-list");
const batchListEl = document.getElementById("batch-list");
const transcriptEl = document.getElementById("transcript-edit");
const transcriptHintEl = document.getElementById("transcript-hint");
const playerEl = document.getElementById("player");
const saveBtn = document.getElementById("btn-save");
const speakersBtn = document.getElementById("btn-speakers");
const transcribeBtn = document.getElementById("btn-transcribe");
const speakerRenameEl = document.getElementById("speaker-rename");
const toastEl = document.getElementById("toast");
const exportModal = document.getElementById("export-modal");
const exportNameEl = document.getElementById("export-name");
const exportDirEl = document.getElementById("export-dir");
const exportFmtEl = document.getElementById("export-fmt");
const exportActionsEl = document.getElementById("export-actions");
const exportActionsPathEl = document.getElementById("export-actions-path");
const ctxMenu = document.getElementById("ctx-menu");
const jobBannerEl = document.getElementById("job-banner");
const computeHintEl = document.getElementById("compute-hint");
const batchTargetSelectEl = document.getElementById("batch-target-select");
const folderAddModal = document.getElementById("folder-add-modal");
const folderAddCountEl = document.getElementById("folder-add-count");
const folderAddNameEl = document.getElementById("folder-add-name");
const folderAddNameWrap = document.getElementById("folder-add-name-wrap");
const folderAddRecursiveEl = document.getElementById("folder-add-recursive");
const folderAddTitleEl = document.getElementById("folder-add-title");
const batchRulesModal = document.getElementById("batch-rules-modal");

const BATCH_TARGET_NEW = "__new__";
const SELECTED_BATCH_KEY = "selected_batch_id";

let activeMainTab = "files";

const STATUS_LABELS = {
  idle: "не расшифрован",
  queued: "в очереди",
  running: "в процессе",
  completed: "готово",
  failed: "ошибка",
  cancelled: "отменено",
};

let selectedId = null;
let pollTimer = null;
let jobs = [];
let batches = [];
let orphans = [];
let speakerKeys = [];
let toastTimer = null;
let ctxJobId = null;
let ctxBatchId = null;
let rulesBatchId = null;
let dragJobId = null;
let lastSpeakersError = null;
let selectedBatchId = null;
let pendingFolderPaths = [];
let pendingFolderBatchId = null;

function showToast(message) {
  toastEl.textContent = message;
  toastEl.hidden = false;
  if (toastTimer) {
    clearTimeout(toastTimer);
  }
  toastTimer = setTimeout(() => {
    toastEl.hidden = true;
  }, 5000);
}

function api(path, options) {
  return fetch(path, options).then(async (r) => {
    if (!r.ok) {
      const raw = await r.text();
      let message = raw;
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
      throw new Error(message);
    }
    const type = r.headers.get("content-type") || "";
    if (type.includes("application/json")) {
      return r.json();
    }
    return r;
  });
}

function switchTab(name) {
  activeMainTab = name;
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.tab === name);
  });
  const inWorkspace = name === "files" || name === "batches";
  workspacePanel.classList.toggle("is-visible", inWorkspace);
  workspacePanel.hidden = !inWorkspace;
  livePanel.classList.toggle("is-visible", name === "live");
  livePanel.hidden = name !== "live";
  if (filesChrome) {
    filesChrome.hidden = name !== "files";
  }
  if (batchesChrome) {
    batchesChrome.hidden = name !== "batches";
  }
  if (jobListEl) {
    jobListEl.hidden = name !== "files";
  }
  if (batchListEl) {
    batchListEl.hidden = name !== "batches";
  }
  renderLibrary();
}

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

function hasActiveJobs(list) {
  const all = list || jobs;
  if (batches.some((b) => b.running)) {
    return true;
  }
  if (all.some((j) => j.speakers_running || j.engine_starting)) {
    return true;
  }
  return all.some(
    (j) => j.status === "queued" || j.status === "running"
  );
}

function collapsedBatchSet() {
  try {
    return new Set(JSON.parse(localStorage.getItem("collapsed_batches") || "[]"));
  } catch (_) {
    return new Set();
  }
}

function toggleBatchCollapsed(batchId) {
  const set = collapsedBatchSet();
  const key = String(batchId);
  if (set.has(key)) {
    set.delete(key);
  } else {
    set.add(key);
  }
  localStorage.setItem("collapsed_batches", JSON.stringify([...set]));
}

function loadSelectedBatchId() {
  try {
    const raw = localStorage.getItem(SELECTED_BATCH_KEY);
    if (!raw) {
      return batches.length ? batches[0].id : null;
    }
    const id = Number(raw);
    if (Number.isFinite(id) && batches.some((b) => b.id === id)) {
      return id;
    }
  } catch (_) {
    /* ignore */
  }
  return batches.length ? batches[0].id : null;
}

function saveSelectedBatchId(batchId) {
  selectedBatchId = batchId;
  if (batchId == null) {
    localStorage.removeItem(SELECTED_BATCH_KEY);
  } else {
    localStorage.setItem(SELECTED_BATCH_KEY, String(batchId));
  }
  syncBatchTargetSelect();
}

function selectedBatchLabel(batchId = selectedBatchId) {
  const batch = batchById(batchId);
  return batch ? batch.name : "Пакет";
}

function isSelectedBatch(batchId) {
  return selectedBatchId != null && selectedBatchId === batchId;
}

function syncBatchTargetSelect() {
  if (!batchTargetSelectEl) {
    return;
  }
  const current = selectedBatchId == null ? "" : String(selectedBatchId);
  batchTargetSelectEl.innerHTML = "";
  if (!batches.length) {
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = "Сначала создайте пакет";
    batchTargetSelectEl.appendChild(empty);
    batchTargetSelectEl.value = "";
    return;
  }
  for (const batch of batches) {
    const opt = document.createElement("option");
    opt.value = String(batch.id);
    opt.textContent = batch.name;
    batchTargetSelectEl.appendChild(opt);
  }
  const newOpt = document.createElement("option");
  newOpt.value = BATCH_TARGET_NEW;
  newOpt.textContent = "Создать новый пакет…";
  batchTargetSelectEl.appendChild(newOpt);
  if ([...batchTargetSelectEl.options].some((opt) => opt.value === current)) {
    batchTargetSelectEl.value = current;
  } else if (batches.length) {
    selectedBatchId = batches[0].id;
    localStorage.setItem(SELECTED_BATCH_KEY, String(selectedBatchId));
    batchTargetSelectEl.value = String(selectedBatchId);
  }
}

function setSelectedBatch(batchId) {
  saveSelectedBatchId(batchId);
  renderLibrary();
}

function defaultBatchName(paths) {
  for (const path of paths || []) {
    const base = String(path).split(/[/\\]/).pop() || "";
    if (!base.includes(".")) {
      return base || "Пакет";
    }
  }
  const first = (paths && paths[0]) || "";
  const stem = first.split(/[/\\]/).pop() || "Пакет";
  return stem.replace(/\.[^.]+$/, "") || "Пакет";
}

function pathLooksLikeFolder(path) {
  const base = String(path).split(/[/\\]/).pop() || "";
  return !/\.(wav|mp3|m4a|flac|ogg|opus|webm|mp4|mkv|avi)$/i.test(base);
}

async function refreshLibrary() {
  const data = await api("/api/library");
  batches = data.batches || [];
  orphans = data.orphans || [];
  jobs = [...orphans, ...batches.flatMap((b) => b.jobs || [])];
  selectedBatchId = loadSelectedBatchId();
  syncBatchTargetSelect();
  renderLibrary();
  syncPoll();
}

async function refreshJobs() {
  await refreshLibrary();
}

function jobById(id) {
  return jobs.find((j) => j.id === id);
}

function batchById(id) {
  return batches.find((b) => b.id === id);
}

function formatDuration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours) {
    return `${hours} ч ${minutes} мин`;
  }
  if (minutes) {
    return `${minutes} мин ${secs} с`;
  }
  return `${secs} с`;
}

function jobStatusTone(job) {
  if (job.speakers_running || job.engine_starting || job.status === "running") {
    return "run";
  }
  if (job.status === "queued") {
    return "queue";
  }
  if (job.status === "completed") {
    return "done";
  }
  if (job.status === "failed") {
    return "err";
  }
  if (job.status === "cancelled") {
    return "cancel";
  }
  return "idle";
}

function jobStatusLabel(job) {
  if (job.speakers_running) {
    const wait =
      job.speakers_elapsed_s != null ? ` · ${formatDuration(job.speakers_elapsed_s)}` : "";
    return `в процессе · спикеры${wait}`;
  }
  if ((job.status === "queued" || job.status === "running") && job.engine_starting) {
    const wait = job.duration_s != null ? ` · ${formatDuration(job.duration_s)}` : "";
    return `в процессе · загрузка модели${wait}`;
  }
  if (job.status === "running") {
    const pct = Math.round(Number(job.progress || 0) * 100);
    const wait = job.duration_s != null ? ` · ${formatDuration(job.duration_s)}` : "";
    return `в процессе · ${pct}%${wait}`;
  }
  const base = STATUS_LABELS[job.status] || job.status;
  if (job.status === "completed" && job.duration_s != null) {
    return `${base} · ${formatDuration(job.duration_s)}`;
  }
  return base;
}

function syncJobBanner(job) {
  if (!jobBannerEl) {
    return;
  }
  if (!job) {
    jobBannerEl.hidden = true;
    jobBannerEl.textContent = "";
    return;
  }
  const tone = jobStatusTone(job);
  jobBannerEl.hidden = false;
  jobBannerEl.className = `job-banner job-badge--${tone}`;
  let text = jobStatusLabel(job);
  if (job.status === "failed" && job.error_text) {
    text = `${text}: ${job.error_text}`;
  } else if (job.speakers_error) {
    text = `${text} · ${job.speakers_error}`;
  }
  jobBannerEl.textContent = text;
}

function syncPoll() {
  if (hasActiveJobs(jobs)) {
    if (!pollTimer) {
      pollTimer = setInterval(() => pollJobs(), 500);
    }
  } else {
    stopPoll();
  }
}

function renderJobItem(job, batchId) {
  const li = document.createElement("li");
  li.className = "job-item";
  li.dataset.id = String(job.id);
  if (batchId != null) {
    li.dataset.batchId = String(batchId);
    li.draggable = true;
    li.addEventListener("dragstart", (event) => {
      dragJobId = job.id;
      event.dataTransfer.effectAllowed = "move";
    });
    li.addEventListener("dragover", (event) => event.preventDefault());
    li.addEventListener("drop", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (dragJobId != null && dragJobId !== job.id) {
        reorderBatchJob(batchId, dragJobId, job.id).catch((err) =>
          showToast(err.message || String(err))
        );
      }
      dragJobId = null;
    });
  }
  if (job.id === selectedId) {
    li.classList.add("is-selected");
  }
  const title = document.createElement("div");
  title.className = "job-name";
  title.textContent = job.source_path.split(/[/\\]/).pop();
  const status = document.createElement("div");
  status.className = `job-status job-badge job-badge--${jobStatusTone(job)}`;
  status.textContent = jobStatusLabel(job);
  li.appendChild(title);
  li.appendChild(status);
  const errText = job.error_text || job.speakers_error;
  if (errText) {
    const err = document.createElement("div");
    err.className = "job-error";
    err.textContent = errText;
    li.appendChild(err);
  }
  li.addEventListener("click", () => selectJob(job.id));
  li.addEventListener("contextmenu", (event) => openContextMenu(event, job, batchId));
  return li;
}

function batchStatusTone(batch) {
  if (batch.running || batch.active_count > 0) {
    return "run";
  }
  if (batch.status === "completed") {
    return "done";
  }
  if (batch.status === "paused") {
    return "queue";
  }
  if (batch.failed_count > 0) {
    return "err";
  }
  return "idle";
}

function batchStatusLabel(batch) {
  const done = batch.done_count || 0;
  const total = batch.total_count || 0;
  const failed = batch.failed_count || 0;
  let text = `${done}/${total} готово`;
  if (failed) {
    text += ` · ${failed} ошибок`;
  }
  if (batch.running) {
    text = `в процессе · ${text}`;
  } else if (batch.status === "paused") {
    text = `пауза · ${text}`;
  }
  return text;
}

function renderBatchBlock(batch) {
  const collapsed = collapsedBatchSet().has(String(batch.id));
  const block = document.createElement("li");
  block.className = "batch-block";
  if (isSelectedBatch(batch.id)) {
    block.classList.add("is-add-target");
  }
  const header = document.createElement("div");
  header.className = "batch-header";
  const title = document.createElement("div");
  title.className = "batch-title";
  title.textContent = batch.name;
  const badge = document.createElement("div");
  badge.className = `job-badge job-badge--${batchStatusTone(batch)}`;
  badge.textContent = batchStatusLabel(batch);
  const actions = document.createElement("div");
  actions.className = "batch-actions";
  const startBtn = document.createElement("button");
  startBtn.type = "button";
  startBtn.textContent = "▶";
  startBtn.title = "Запустить пакет";
  startBtn.disabled = Boolean(batch.running) || !(batch.total_count > 0);
  startBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    startBatch(batch.id).catch((err) => showToast(err.message || String(err)));
  });
  const rulesBtn = document.createElement("button");
  rulesBtn.type = "button";
  rulesBtn.textContent = "⚙";
  rulesBtn.title = "Правила";
  rulesBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    openBatchRulesModal(batch.id);
  });
  const toggleBtn = document.createElement("button");
  toggleBtn.type = "button";
  toggleBtn.textContent = collapsed ? "▸" : "▾";
  toggleBtn.title = collapsed ? "Развернуть" : "Свернуть";
  toggleBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleBatchCollapsed(batch.id);
    renderLibrary();
  });
  if (batch.running) {
    const pauseBtn = document.createElement("button");
    pauseBtn.type = "button";
    pauseBtn.textContent = "⏸";
    pauseBtn.title = "Пауза после текущего";
    pauseBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      pauseBatch(batch.id).catch((err) => showToast(err.message || String(err)));
    });
    actions.appendChild(pauseBtn);
    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.textContent = "⏹";
    cancelBtn.title = "Остановить пакет";
    cancelBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      cancelBatch(batch.id).catch((err) => showToast(err.message || String(err)));
    });
    actions.appendChild(cancelBtn);
  }
  actions.appendChild(startBtn);
  actions.appendChild(rulesBtn);
  actions.appendChild(toggleBtn);
  header.appendChild(title);
  header.appendChild(badge);
  header.appendChild(actions);
  header.addEventListener("click", (event) => {
    if (event.target.closest(".batch-actions")) {
      return;
    }
    setSelectedBatch(batch.id);
  });
  header.addEventListener("contextmenu", (event) => openBatchContextMenu(event, batch));
  block.appendChild(header);
  if (!collapsed) {
    const list = document.createElement("ul");
    list.className = "batch-jobs";
    for (const job of batch.jobs || []) {
      list.appendChild(renderJobItem(job, batch.id));
    }
    block.appendChild(list);
  }
  return block;
}

function renderFilesList() {
  if (!jobListEl) {
    return;
  }
  jobListEl.innerHTML = "";
  if (!orphans.length) {
    const empty = document.createElement("li");
    empty.className = "orphan-empty";
    empty.textContent = "Пока пусто — нажмите «+ Файлы»";
    jobListEl.appendChild(empty);
    return;
  }
  for (const job of orphans) {
    jobListEl.appendChild(renderJobItem(job, null));
  }
}

function renderBatchesList() {
  if (!batchListEl) {
    return;
  }
  batchListEl.innerHTML = "";
  if (!batches.length) {
    const empty = document.createElement("li");
    empty.className = "orphan-empty";
    empty.textContent = "Нет пакетов — нажмите «+ Пакет»";
    batchListEl.appendChild(empty);
    return;
  }
  for (const batch of batches) {
    batchListEl.appendChild(renderBatchBlock(batch));
  }
}

function renderLibrary() {
  renderFilesList();
  renderBatchesList();
}

function renderJobs() {
  renderLibrary();
}

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function isEditingTranscript() {
  return document.activeElement === transcriptEl;
}

async function selectJob(id) {
  if (id !== selectedId) {
    speakerKeys = [];
  }
  selectedId = id;
  renderLibrary();
  const job = await api(`/api/jobs/${id}`);
  playerEl.src = `/api/jobs/${id}/media`;
  renderTranscript(job.transcript || "");
  saveBtn.hidden = !((job.transcript && job.transcript.length) || (job.segments && job.segments.length));
  syncSpeakersUi(job);
  syncExportActions(job);
  syncTranscribeUi(job);
  syncJobBanner(job);
  if (job.speakers_error && job.speakers_error !== lastSpeakersError) {
    lastSpeakersError = job.speakers_error;
    showToast(job.speakers_error);
  }
  syncPoll();
}

async function pollJobs() {
  await refreshLibrary();
  if (selectedId != null) {
    const job = await api(`/api/jobs/${selectedId}`);
    if (!isEditingTranscript()) {
      renderTranscript(job.transcript || "");
    }
    saveBtn.hidden = !((job.transcript && job.transcript.length) || (job.segments && job.segments.length));
    syncSpeakersUi(job);
    syncExportActions(job);
    syncTranscribeUi(job);
    syncJobBanner(job);
    if (job.speakers_error && job.speakers_error !== lastSpeakersError) {
      lastSpeakersError = job.speakers_error;
      showToast(job.speakers_error);
    }
    jobs = jobs.map((j) => (j.id === job.id ? { ...j, ...job } : j));
    renderLibrary();
  }
  syncPoll();
}

function syncTranscribeUi(job) {
  const canStart = Boolean(
    job && ["idle", "failed", "cancelled"].includes(job.status)
  );
  transcribeBtn.hidden = !job;
  transcribeBtn.disabled = !canStart;
}

function syncExportActions(job) {
  const path = job && job.last_export_path;
  if (!path) {
    exportActionsEl.hidden = true;
    exportActionsPathEl.textContent = "";
    return;
  }
  exportActionsEl.hidden = false;
  exportActionsPathEl.textContent = path;
}

function uniqueSpeakers(segments) {
  const keys = [];
  const seen = new Set();
  for (const seg of segments || []) {
    if (seg.speaker && !seen.has(seg.speaker)) {
      seen.add(seg.speaker);
      keys.push(seg.speaker);
    }
  }
  return keys;
}

function syncSpeakersUi(job) {
  const completed = job && job.status === "completed";
  speakersBtn.hidden = !completed;
  speakersBtn.disabled = Boolean(job && job.speakers_running);
  const keys = speakerKeys.length ? speakerKeys : uniqueSpeakers(job.segments || []);
  renderSpeakerRename(completed ? keys : []);
}

function renderSpeakerRename(keys) {
  const current = Array.from(speakerRenameEl.querySelectorAll("input")).map(
    (input) => input.dataset.speakerKey
  );
  const same =
    current.length === keys.length && current.every((key, index) => key === keys[index]);
  if (same) {
    speakerRenameEl.hidden = keys.length === 0;
    return;
  }
  speakerRenameEl.innerHTML = "";
  if (!keys.length) {
    speakerRenameEl.hidden = true;
    return;
  }
  speakerRenameEl.hidden = false;
  for (const key of keys) {
    const label = document.createElement("label");
    label.textContent = key;
    const input = document.createElement("input");
    input.dataset.speakerKey = key;
    input.placeholder = "Имя";
    input.addEventListener("change", () => saveSpeakerNames().catch((err) => showToast(err.message)));
    label.appendChild(input);
    speakerRenameEl.appendChild(label);
  }
}

async function saveSpeakerNames() {
  if (selectedId == null) {
    return;
  }
  const body = {};
  for (const input of speakerRenameEl.querySelectorAll("input")) {
    const name = input.value.trim();
    if (name) {
      body[input.dataset.speakerKey] = name;
    }
  }
  if (!Object.keys(body).length) {
    return;
  }
  await api(`/api/jobs/${selectedId}/speakers`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await selectJob(selectedId);
}

async function runSpeakers() {
  if (selectedId == null) {
    return;
  }
    try {
    await api(`/api/jobs/${selectedId}/speakers`, { method: "POST" });
    lastSpeakersError = null;
    showToast("Распознаю спикеров…");
    await refreshJobs();
    await selectJob(selectedId);
  } catch (err) {
    showToast(err.message || String(err));
  }
}

function renderTranscript(text) {
  const value = text || "";
  const hasText = Boolean(value);
  transcriptEl.hidden = !hasText;
  transcriptHintEl.hidden = !hasText;
  if (transcriptEl.value !== value) {
    transcriptEl.value = value;
  }
}

function seekTo(ms) {
  try {
    playerEl.currentTime = Math.max(0, Number(ms) / 1000);
    playerEl.play().catch(() => {});
  } catch (_) {
    /* ignore */
  }
}

function seekFromTranscriptClick() {
  const pos = transcriptEl.selectionStart;
  const before = transcriptEl.value.slice(0, pos);
  const lineStart = before.lastIndexOf("\n") + 1;
  const rest = transcriptEl.value.slice(lineStart);
  const line = rest.split("\n", 1)[0] || "";
  const match = line.match(/^\[(\d{2}):(\d{2}):(\d{2})\]/);
  if (!match) {
    return;
  }
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  const seconds = Number(match[3]);
  seekTo(((hours * 3600) + (minutes * 60) + seconds) * 1000);
}

function isAbsolutePath(path) {
  return /^(?:[A-Za-z]:[\\/]|\\\\|\/|file:)/i.test(String(path || "").trim());
}

function pathsFromDrop(event) {
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

async function addOrphanFiles(paths) {
  const unique = [...new Set((paths || []).filter(Boolean))];
  if (!unique.length) {
    return;
  }
  const scan = await api("/api/batches/scan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paths: unique, recursive: false }),
  });
  for (const path of scan.paths || []) {
    await api("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
  }
  await refreshLibrary();
  showToast(`Добавлено файлов: ${(scan.paths || []).length}`);
}

async function addFilesToSelectedBatch(paths) {
  const batchId = selectedBatchId;
  if (batchId == null) {
    showToast("Сначала создайте или выберите пакет.");
    switchTab("batches");
    return;
  }
  const unique = [...new Set((paths || []).filter(Boolean))];
  if (!unique.length) {
    return;
  }
  if (unique.some(pathLooksLikeFolder)) {
    showToast("Для папки используйте «+ Папка».");
    return;
  }
  try {
    await addToBatch(batchId, unique, false);
    await refreshLibrary();
    showToast(`Добавлено в «${selectedBatchLabel(batchId)}»`);
  } catch (err) {
    showToast(err.message || String(err));
    await refreshLibrary();
  }
}

async function addToBatch(batchId, paths, recursive) {
  await api(`/api/batches/${batchId}/items`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paths, recursive }),
  });
}

async function addPathsForCurrentTab(paths) {
  const unique = [...new Set((paths || []).filter(Boolean))];
  if (!unique.length) {
    return;
  }
  const onlyFolders = unique.every(pathLooksLikeFolder);
  if (onlyFolders) {
    if (activeMainTab === "files") {
      showToast("Папки добавляйте во вкладке «Пакеты».");
      switchTab("batches");
      return;
    }
    if (selectedBatchId == null) {
      await openFolderAddModal(unique, null);
      return;
    }
    await openFolderAddModal(unique, selectedBatchId);
    return;
  }
  if (unique.some(pathLooksLikeFolder)) {
    showToast("Смешивайте файлы и папки отдельно.");
    return;
  }
  if (activeMainTab === "batches") {
    await addFilesToSelectedBatch(unique);
  } else {
    try {
      await addOrphanFiles(unique);
    } catch (err) {
      showToast(err.message || String(err));
      await refreshLibrary();
    }
  }
}

async function enqueueDropped(paths) {
  await addPathsForCurrentTab(paths);
}

function closeFolderAddModal() {
  if (folderAddModal) {
    folderAddModal.hidden = true;
  }
  pendingFolderPaths = [];
  pendingFolderBatchId = null;
}

async function openFolderAddModal(paths, batchId) {
  if (!folderAddModal) {
    showToast("Обновите окно приложения (перезапуск).");
    return;
  }
  pendingFolderPaths = [...new Set((paths || []).filter(Boolean))];
  pendingFolderBatchId = batchId;
  if (!pendingFolderPaths.length) {
    return;
  }
  const creating = batchId == null;
  if (folderAddTitleEl) {
    folderAddTitleEl.textContent = creating ? "Пакет из папки" : "Добавить папку в пакет";
  }
  if (folderAddNameWrap) {
    folderAddNameWrap.hidden = !creating;
  }
  if (folderAddNameEl) {
    folderAddNameEl.value = defaultBatchName(pendingFolderPaths);
  }
  if (folderAddRecursiveEl) {
    folderAddRecursiveEl.checked = false;
  }
  try {
    const scan = await api("/api/batches/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paths: pendingFolderPaths, recursive: false }),
    });
    const label = creating
      ? `Будет создан пакет, файлов: ${scan.count}`
      : `В пакет «${selectedBatchLabel(batchId)}», файлов: ${scan.count}`;
    if (folderAddCountEl) {
      folderAddCountEl.textContent = label;
    }
  } catch (err) {
    if (folderAddCountEl) {
      folderAddCountEl.textContent = err.message || String(err);
    }
  }
  folderAddModal.hidden = false;
}

async function confirmFolderAdd() {
  const paths = pendingFolderPaths;
  const batchId = pendingFolderBatchId;
  const recursive = Boolean(folderAddRecursiveEl && folderAddRecursiveEl.checked);
  closeFolderAddModal();
  if (!paths.length) {
    return;
  }
  try {
    if (batchId == null) {
      const name =
        (folderAddNameEl && folderAddNameEl.value.trim()) || defaultBatchName(paths);
      const batch = await api("/api/batches", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      await addToBatch(batch.id, paths, recursive);
      setSelectedBatch(batch.id);
      switchTab("batches");
      await refreshLibrary();
      showToast(`Пакет «${name}» создан`);
    } else {
      await addToBatch(batchId, paths, recursive);
      await refreshLibrary();
      showToast(`Папка добавлена в «${selectedBatchLabel(batchId)}»`);
    }
  } catch (err) {
    showToast(err.message || String(err));
    await refreshLibrary();
  }
}

async function pickFilePaths() {
  if (window.pywebview && window.pywebview.api && window.pywebview.api.open_files) {
    return window.pywebview.api.open_files() || [];
  }
  const input = document.createElement("input");
  input.type = "file";
  input.multiple = true;
  input.accept = "audio/*,video/*";
  await new Promise((resolve) => {
    input.addEventListener("change", () => resolve());
    input.click();
  });
  const paths = Array.from(input.files || [])
    .map((f) => f.pywebviewFullPath || f.path)
    .filter((path) => path && isAbsolutePath(path));
  if (!paths.length && (input.files || []).length) {
    showToast("Нет полного пути к файлу. Используйте кнопку «+ Файлы» в приложении.");
  }
  return paths;
}

async function pickFolderPath() {
  if (window.pywebview && window.pywebview.api && window.pywebview.api.pick_folder) {
    const folder = await window.pywebview.api.pick_folder();
    return folder || "";
  }
  showToast("Выбор папки доступен в десктопном приложении.");
  return "";
}

async function addFiles() {
  const paths = await pickFilePaths();
  if (!paths.length) {
    return;
  }
  await addPathsForCurrentTab(paths);
}

async function addFolder() {
  const folder = await pickFolderPath();
  if (!folder) {
    return;
  }
  if (selectedBatchId == null) {
    await openFolderAddModal([folder], null);
    return;
  }
  await openFolderAddModal([folder], selectedBatchId);
}

async function createEmptyBatch() {
  const stamp = new Date();
  const name = `Пакет ${stamp.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" })}`;
  try {
    const batch = await api("/api/batches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    setSelectedBatch(batch.id);
    switchTab("batches");
    await refreshLibrary();
    showToast(`Пакет «${name}» создан — добавьте файлы`);
  } catch (err) {
    showToast(err.message || String(err));
  }
}

function handleBatchTargetSelectChange() {
  if (!batchTargetSelectEl) {
    return;
  }
  const value = batchTargetSelectEl.value;
  if (value === BATCH_TARGET_NEW) {
    createEmptyBatch().catch((err) => showToast(err.message || String(err)));
    return;
  }
  const id = Number(value);
  if (Number.isFinite(id)) {
    setSelectedBatch(id);
  }
}

async function reorderBatchJob(batchId, fromId, toId) {
  const batch = batchById(batchId);
  if (!batch) {
    return;
  }
  const ids = (batch.jobs || []).map((j) => j.id);
  const fromIdx = ids.indexOf(fromId);
  const toIdx = ids.indexOf(toId);
  if (fromIdx < 0 || toIdx < 0) {
    return;
  }
  ids.splice(fromIdx, 1);
  ids.splice(toIdx, 0, fromId);
  await api(`/api/batches/${batchId}/reorder`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_ids: ids }),
  });
  await refreshLibrary();
}

async function startBatch(batchId) {
  await api(`/api/batches/${batchId}/start`, { method: "POST" });
  await refreshLibrary();
  showToast("Пакет запущен");
}

async function pauseBatch(batchId) {
  await api(`/api/batches/${batchId}/pause`, { method: "POST" });
  await refreshLibrary();
  showToast("Пауза после текущего файла");
}

async function cancelBatch(batchId) {
  await api(`/api/batches/${batchId}/cancel`, { method: "POST" });
  await refreshLibrary();
  showToast("Пакет остановлен");
}

async function deleteBatch(batchId) {
  const batch = batchById(batchId);
  const name = batch ? batch.name : String(batchId);
  if (!window.confirm(`Удалить пакет «${name}» и все его файлы?`)) {
    return;
  }
  await api(`/api/batches/${batchId}`, { method: "DELETE" });
  if (selectedId != null) {
    const job = jobById(selectedId);
    if (!job) {
      selectedId = null;
      transcriptEl.value = "";
      transcriptEl.hidden = true;
      transcriptHintEl.hidden = true;
      saveBtn.hidden = true;
      speakersBtn.hidden = true;
      exportActionsEl.hidden = true;
      speakerRenameEl.hidden = true;
      playerEl.removeAttribute("src");
      syncJobBanner(null);
    }
  }
  await refreshLibrary();
}

function openBatchRulesModal(batchId) {
  const batch = batchById(batchId);
  if (!batch) {
    return;
  }
  rulesBatchId = batchId;
  const rules = batch.rules || {};
  document.getElementById("rule-speakers").checked = Boolean(rules.speakers);
  document.getElementById("rule-export").checked = Boolean(rules.export);
  document.getElementById("rule-export-fmt").value = rules.export_fmt || "srt";
  document.getElementById("rule-export-dir-mode").value = rules.export_dir_mode || "beside_source";
  document.getElementById("rule-export-dir").value = rules.export_dir || "";
  document.getElementById("rule-skip-completed").checked = rules.skip_completed !== false;
  syncRuleExportDirUi();
  batchRulesModal.hidden = false;
}

function closeBatchRulesModal() {
  batchRulesModal.hidden = true;
  rulesBatchId = null;
}

function syncRuleExportDirUi() {
  const mode = document.getElementById("rule-export-dir-mode").value;
  document.getElementById("rule-export-dir-wrap").hidden = mode !== "fixed";
}

async function saveBatchRules() {
  if (rulesBatchId == null) {
    return;
  }
  const rules = {
    speakers: document.getElementById("rule-speakers").checked,
    export: document.getElementById("rule-export").checked,
    export_fmt: document.getElementById("rule-export-fmt").value,
    export_dir_mode: document.getElementById("rule-export-dir-mode").value,
    export_dir: document.getElementById("rule-export-dir").value.trim(),
    skip_completed: document.getElementById("rule-skip-completed").checked,
    on_error: "continue",
  };
  await api(`/api/batches/${rulesBatchId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rules }),
  });
  closeBatchRulesModal();
  await refreshLibrary();
  showToast("Правила сохранены");
}

async function saveSegments() {
  if (selectedId == null) {
    return;
  }
  await api(`/api/jobs/${selectedId}/segments`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript: transcriptEl.value }),
  });
  showToast("Сохранено");
}

function sourceStem(sourcePath) {
  const base = (sourcePath || "").split(/[/\\]/).pop() || "transcript";
  return base.replace(/\.[^.]+$/, "") || "transcript";
}

function sourceDir(sourcePath) {
  return (sourcePath || "").replace(/[/\\][^/\\]+$/, "");
}

function closeExportModal() {
  exportModal.hidden = true;
}

function currentExportFmt() {
  return (exportFmtEl.value || "srt").toLowerCase();
}

function syncExportNameExtension() {
  const fmt = currentExportFmt();
  const raw = (exportNameEl.value || "").trim() || "transcript";
  const stem = raw.replace(/\.[^.\\/]+$/, "") || "transcript";
  exportNameEl.value = `${stem}.${fmt}`;
}

function openExportModal() {
  if (selectedId == null) {
    showToast("Сначала выберите запись.");
    return;
  }
  const job = jobById(selectedId);
  exportFmtEl.value = "srt";
  exportNameEl.value = `${sourceStem(job && job.source_path)}.srt`;
  exportDirEl.value = sourceDir(job && job.source_path);
  exportModal.hidden = false;
  exportNameEl.focus();
  exportNameEl.select();
}

async function browseExportFolder() {
  const current = exportDirEl.value;
  if (window.pywebview && window.pywebview.api && window.pywebview.api.pick_folder) {
    const folder = await window.pywebview.api.pick_folder(current);
    if (folder) {
      exportDirEl.value = folder;
    }
    return;
  }
  showToast("Выберите папку в поле «Папка» или вставьте путь.");
}

function joinExportPath(directory, filename) {
  const name = String(filename || "").split(/[/\\]/).pop();
  const dir = String(directory || "").replace(/[/\\]+$/, "");
  if (!dir) {
    return name;
  }
  return `${dir}\\${name}`;
}

async function confirmExport() {
  if (selectedId == null) {
    return;
  }
  syncExportNameExtension();
  const fmt = currentExportFmt();
  const filename = (exportNameEl.value || "").trim();
  const directory = (exportDirEl.value || "").trim();
  if (!filename || !directory) {
    showToast("Укажите имя файла и папку.");
    return;
  }
  const path = joinExportPath(directory, filename);
  closeExportModal();
  const result = await api(`/api/jobs/${selectedId}/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fmt, path }),
  });
  showToast(`Сохранено: ${result.path || path}`);
  await refreshJobs();
  await selectJob(selectedId);
}

async function exportSelected() {
  openExportModal();
}

async function openSavedExport(reveal) {
  const job = selectedId == null ? null : jobById(selectedId);
  const path = job && job.last_export_path;
  if (!path) {
    showToast("Сначала экспортируйте файл.");
    return;
  }
  if (window.pywebview && window.pywebview.api && window.pywebview.api.open_path) {
    await window.pywebview.api.open_path(path, reveal);
    return;
  }
  await api("/api/open-path", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, reveal }),
  });
}

async function startSelected() {
  if (selectedId == null) {
    showToast("Сначала выберите запись.");
    return;
  }
  await api(`/api/jobs/${selectedId}/start`, { method: "POST" });
  await selectJob(selectedId);
  await refreshJobs();
}

async function retranscribeSelected() {
  if (selectedId == null) {
    return;
  }
  await api(`/api/jobs/${selectedId}/retranscribe`, { method: "POST" });
  await selectJob(selectedId);
  await refreshJobs();
}

async function cancelSelected() {
  if (selectedId == null) {
    return;
  }
  await api(`/api/jobs/${selectedId}/cancel`, { method: "POST" });
  await refreshJobs();
}

async function deleteSelected(id) {
  const jobId = id == null ? selectedId : id;
  if (jobId == null) {
    return;
  }
  const job = jobById(jobId);
  const name = job ? job.source_path.split(/[/\\]/).pop() : String(jobId);
  if (!window.confirm(`Удалить запись «${name}» из истории?`)) {
    return;
  }
  await api(`/api/jobs/${jobId}`, { method: "DELETE" });
  if (selectedId === jobId) {
    selectedId = null;
    transcriptEl.value = "";
    transcriptEl.hidden = true;
    transcriptHintEl.hidden = true;
    saveBtn.hidden = true;
    speakersBtn.hidden = true;
    exportActionsEl.hidden = true;
    speakerRenameEl.hidden = true;
    playerEl.removeAttribute("src");
    syncJobBanner(null);
  }
  await refreshJobs();
}

function hideContextMenu() {
  ctxMenu.hidden = true;
  ctxJobId = null;
  ctxBatchId = null;
}

function openBatchContextMenu(event, batch) {
  event.preventDefault();
  ctxBatchId = batch.id;
  ctxJobId = null;
  const running = Boolean(batch.running);
  ctxMenu.querySelector('[data-act="batch-start"]').hidden = running || !(batch.total_count > 0);
  ctxMenu.querySelector('[data-act="batch-pause"]').hidden = !running;
  ctxMenu.querySelector('[data-act="batch-cancel"]').hidden = !running;
  ctxMenu.querySelector('[data-act="batch-rules"]').hidden = false;
  ctxMenu.querySelector('[data-act="batch-add"]').hidden = false;
  ctxMenu.querySelector('[data-act="batch-add-folder"]').hidden = false;
  ctxMenu.querySelector('[data-act="batch-delete"]').hidden = running;
  ctxMenu.querySelector('[data-act="remove-from-batch"]').hidden = true;
  ctxMenu.querySelector('[data-act="transcribe"]').hidden = true;
  ctxMenu.querySelector('[data-act="export"]').hidden = true;
  ctxMenu.querySelector('[data-act="speakers"]').hidden = true;
  ctxMenu.querySelector('[data-act="retranscribe"]').hidden = true;
  ctxMenu.querySelector('[data-act="cancel"]').hidden = true;
  ctxMenu.querySelector('[data-act="delete"]').hidden = true;
  ctxMenu.hidden = false;
  ctxMenu.style.left = `${event.clientX}px`;
  ctxMenu.style.top = `${event.clientY}px`;
}

function openContextMenu(event, job, batchId) {
  event.preventDefault();
  ctxJobId = job.id;
  ctxBatchId = batchId;
  selectedId = job.id;
  renderLibrary();
  const completed = job.status === "completed";
  const active = job.status === "queued" || job.status === "running";
  const canStart = ["idle", "failed", "cancelled"].includes(job.status);
  ctxMenu.querySelector('[data-act="batch-start"]').hidden = true;
  ctxMenu.querySelector('[data-act="batch-pause"]').hidden = true;
  ctxMenu.querySelector('[data-act="batch-cancel"]').hidden = true;
  ctxMenu.querySelector('[data-act="batch-rules"]').hidden = true;
  ctxMenu.querySelector('[data-act="batch-add"]').hidden = true;
  ctxMenu.querySelector('[data-act="batch-add-folder"]').hidden = true;
  ctxMenu.querySelector('[data-act="batch-delete"]').hidden = true;
  ctxMenu.querySelector('[data-act="remove-from-batch"]').hidden = batchId == null;
  ctxMenu.querySelector('[data-act="transcribe"]').hidden = !canStart;
  ctxMenu.querySelector('[data-act="export"]').hidden = !completed;
  ctxMenu.querySelector('[data-act="speakers"]').hidden = !completed;
  ctxMenu.querySelector('[data-act="retranscribe"]').hidden = active;
  ctxMenu.querySelector('[data-act="cancel"]').hidden = !active;
  ctxMenu.querySelector('[data-act="delete"]').hidden = false;
  ctxMenu.hidden = false;
  ctxMenu.style.left = `${event.clientX}px`;
  ctxMenu.style.top = `${event.clientY}px`;
}

function bindClick(id, handler) {
  const el = document.getElementById(id);
  if (el) {
    el.addEventListener("click", handler);
  }
}

bindClick("btn-add-files", () =>
  addFiles().catch((err) => showToast(err.message || String(err)))
);
bindClick("btn-batch-add-files", () =>
  addFiles().catch((err) => showToast(err.message || String(err)))
);
bindClick("btn-batch-add-folder", () =>
  addFolder().catch((err) => showToast(err.message || String(err)))
);
bindClick("btn-batch-new", () =>
  createEmptyBatch().catch((err) => showToast(err.message || String(err)))
);
if (batchTargetSelectEl) {
  batchTargetSelectEl.addEventListener("change", handleBatchTargetSelectChange);
}
document.getElementById("btn-transcribe").addEventListener("click", () =>
  startSelected().catch((err) => showToast(err.message || String(err)))
);
document.getElementById("btn-export").addEventListener("click", () =>
  exportSelected().catch((err) => showToast(err.message || String(err)))
);
document.getElementById("btn-retranscribe").addEventListener("click", () =>
  retranscribeSelected().catch((err) => showToast(err.message || String(err)))
);
document.getElementById("btn-cancel").addEventListener("click", () =>
  cancelSelected().catch((err) => showToast(err.message || String(err)))
);
speakersBtn.addEventListener("click", () => runSpeakers());
saveBtn.addEventListener("click", () => saveSegments().catch((err) => showToast(err.message || String(err))));
transcriptEl.addEventListener("click", () => seekFromTranscriptClick());

exportModal.addEventListener("click", (event) => {
  if (event.target === exportModal) {
    closeExportModal();
  }
});
document.getElementById("export-cancel").addEventListener("click", () => closeExportModal());
document.getElementById("export-confirm").addEventListener("click", () =>
  confirmExport().catch((err) => showToast(err.message || String(err)))
);
document.getElementById("export-browse").addEventListener("click", () =>
  browseExportFolder().catch((err) => showToast(err.message || String(err)))
);
exportFmtEl.addEventListener("change", () => syncExportNameExtension());
document.getElementById("btn-open-export").addEventListener("click", () =>
  openSavedExport(false).catch((err) => showToast(err.message || String(err)))
);
document.getElementById("btn-open-export-folder").addEventListener("click", () =>
  openSavedExport(true).catch((err) => showToast(err.message || String(err)))
);

ctxMenu.addEventListener("click", (event) => {
  const btn = event.target.closest("[data-act]");
  if (!btn) {
    return;
  }
  const act = btn.dataset.act;
  const jobId = ctxJobId;
  const batchId = ctxBatchId;
  hideContextMenu();
  if (jobId != null) {
    selectedId = jobId;
  }
  const run = {
    transcribe: startSelected,
    export: exportSelected,
    speakers: runSpeakers,
    retranscribe: retranscribeSelected,
    cancel: cancelSelected,
    delete: () => deleteSelected(jobId),
    "batch-start": () => startBatch(batchId),
    "batch-pause": () => pauseBatch(batchId),
    "batch-cancel": () => cancelBatch(batchId),
    "batch-rules": () => openBatchRulesModal(batchId),
    "batch-add": () => {
      setSelectedBatch(batchId);
      switchTab("batches");
      return addFiles();
    },
    "batch-add-folder": () => {
      setSelectedBatch(batchId);
      switchTab("batches");
      return addFolder();
    },
    "batch-delete": () => deleteBatch(batchId),
    "remove-from-batch": async () => {
      await api(`/api/jobs/${jobId}/remove-from-batch`, { method: "POST" });
      await refreshLibrary();
    },
  }[act];
  if (run) {
    Promise.resolve(run()).catch((err) => showToast(err.message || String(err)));
  }
});

document.addEventListener("click", (event) => {
  if (!ctxMenu.hidden && !ctxMenu.contains(event.target)) {
    hideContextMenu();
  }
});

window.addEventListener("dragover", (e) => {
  e.preventDefault();
  document.body.classList.add("is-drop");
});
window.addEventListener("dragleave", () => document.body.classList.remove("is-drop"));
window.addEventListener("drop", (e) => {
  e.preventDefault();
  document.body.classList.remove("is-drop");
  if (window.pywebview) {
    return;
  }
  const paths = pathsFromDrop(e);
  if (!paths.length) {
    showToast("Перетаскивание не дало полный путь. Нажмите «+ Файлы».");
    return;
  }
  enqueueDropped(paths).catch((err) => showToast(err.message || String(err)));
});

refreshLibrary().catch(console.error);
syncBatchTargetSelect();
switchTab("files");

if (folderAddModal) {
  const folderAddCancel = document.getElementById("folder-add-cancel");
  const folderAddConfirm = document.getElementById("folder-add-confirm");
  if (folderAddCancel) {
    folderAddCancel.addEventListener("click", closeFolderAddModal);
  }
  if (folderAddConfirm) {
    folderAddConfirm.addEventListener("click", () =>
      confirmFolderAdd().catch((err) => showToast(err.message || String(err)))
    );
  }
  folderAddModal.addEventListener("click", (event) => {
    if (event.target === folderAddModal) {
      closeFolderAddModal();
    }
  });
}
if (batchRulesModal) {
  const batchRulesCancel = document.getElementById("batch-rules-cancel");
  const batchRulesSave = document.getElementById("batch-rules-save");
  if (batchRulesCancel) {
    batchRulesCancel.addEventListener("click", closeBatchRulesModal);
  }
  if (batchRulesSave) {
    batchRulesSave.addEventListener("click", () =>
      saveBatchRules().catch((err) => showToast(err.message || String(err)))
    );
  }
  const ruleExportDirMode = document.getElementById("rule-export-dir-mode");
  if (ruleExportDirMode) {
    ruleExportDirMode.addEventListener("change", syncRuleExportDirUi);
  }
  const ruleExportBrowse = document.getElementById("rule-export-browse");
  if (ruleExportBrowse) {
    ruleExportBrowse.addEventListener("click", async () => {
      if (window.pywebview && window.pywebview.api && window.pywebview.api.pick_folder) {
        const folder = await window.pywebview.api.pick_folder(
          document.getElementById("rule-export-dir").value
        );
        if (folder) {
          document.getElementById("rule-export-dir").value = folder;
        }
      }
    });
  }
  batchRulesModal.addEventListener("click", (event) => {
    if (event.target === batchRulesModal) {
      closeBatchRulesModal();
    }
  });
}

function renderCompute(data) {
  document.querySelectorAll('input[name="compute"]').forEach((el) => {
    el.checked = el.value === data.preference;
  });
  if (!computeHintEl) {
    return;
  }
  const expl = (data.explanations || {})[data.preference] || "";
  const device = data.effective === "gpu" ? "GPU" : "CPU";
  const cuda = data.cuda_available ? "CUDA доступна" : "CUDA недоступна";
  const parts = [];
  if (expl) {
    parts.push(expl);
  }
  parts.push(`Сейчас расшифровка и спикеры пойдут на ${device} (${cuda}).`);
  if (data.warning) {
    parts.push(data.warning);
  }
  computeHintEl.textContent = parts.join(" ");
  computeHintEl.classList.toggle("is-warn", Boolean(data.warning));
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
      showToast("Движок остановится и при следующей расшифровке запустится уже на выбранном устройстве.");
    }
  } catch (err) {
    showToast(err.message || String(err));
    await loadCompute();
  }
}

document.querySelectorAll('input[name="compute"]').forEach((el) => {
  el.addEventListener("change", () => {
    if (el.checked) {
      setCompute(el.value).catch((err) => showToast(err.message || String(err)));
    }
  });
});
setTimeout(() => loadCompute().catch(console.error), 0);

const downloadBtn = document.getElementById("btn-download-model");
const downloadStatus = document.getElementById("model-download-status");
let modelPollTimer = null;

async function refreshModelStatus() {
  const status = await api("/api/status");
  const missing = status.model === "missing";
  downloadBtn.hidden = !missing;
  if (!missing) {
    downloadStatus.hidden = true;
    downloadStatus.classList.remove("is-spinning");
    downloadBtn.disabled = false;
    if (modelPollTimer) {
      clearInterval(modelPollTimer);
      modelPollTimer = null;
    }
  }
}

async function downloadModel() {
  downloadBtn.disabled = true;
  downloadStatus.hidden = false;
  downloadStatus.classList.add("is-spinning");
  downloadStatus.textContent = "Скачивание модели…";
  try {
    await api("/api/model/download", { method: "POST" });
    if (!modelPollTimer) {
      modelPollTimer = setInterval(() => refreshModelStatus().catch(console.error), 2000);
    }
    await refreshModelStatus();
  } catch (err) {
    downloadStatus.classList.remove("is-spinning");
    downloadStatus.textContent = err.message || String(err);
    downloadBtn.disabled = false;
  }
}

downloadBtn.addEventListener("click", () => downloadModel());
refreshModelStatus().catch(console.error);

const micSelect = document.getElementById("mic-select");
const recBtn = document.getElementById("btn-rec");
const stopBtn = document.getElementById("btn-stop");
const liveHint = document.getElementById("live-hint");
const liveCountdown = document.getElementById("live-countdown");
const liveMeter = document.getElementById("live-meter");
const liveTranscript = document.getElementById("live-transcript");
const NO_MIC_HINT = "Микрофон не найден. Проверьте устройства записи Windows.";

let livePollTimer = null;
let liveJobId = null;

async function loadMics() {
  let mics = [];
  try {
    mics = await api("/api/mics");
  } catch (err) {
    mics = [];
  }
  micSelect.innerHTML = "";
  for (const mic of mics) {
    const opt = document.createElement("option");
    opt.value = String(mic.id);
    opt.textContent = mic.name;
    micSelect.appendChild(opt);
  }
  const empty = mics.length === 0;
  recBtn.disabled = empty;
  micSelect.disabled = empty;
  liveHint.textContent = empty ? NO_MIC_HINT : "";
}

function renderLiveSegments(segments) {
  liveTranscript.innerHTML = "";
  for (const seg of segments || []) {
    const p = document.createElement("p");
    p.textContent = seg.speaker ? `${seg.speaker}: ${seg.text}` : seg.text;
    liveTranscript.appendChild(p);
  }
}

async function pollLive() {
  const status = await api("/api/live/status");
  const listening = Boolean(status.listening);
  const hasMics = micSelect.options.length > 0;
  recBtn.disabled = !hasMics || listening;
  stopBtn.disabled = !listening;
  if (listening) {
    const n = Math.max(0, Math.ceil(Number(status.remaining_s) || 0));
    liveCountdown.textContent = `Слушаю… следующий кусок через ${n}s`;
  } else {
    liveCountdown.textContent = "";
  }
  const rms = Number(status.rms) || 0;
  liveMeter.style.width = `${Math.min(100, Math.round(rms * 400))}%`;
  if (status.error) {
    liveHint.textContent = status.error;
  }
  const jobId = status.job_id || liveJobId;
  if (jobId) {
    liveJobId = jobId;
    const job = await api(`/api/jobs/${jobId}`);
    renderLiveSegments(job.segments || []);
  }
  if (!listening && livePollTimer) {
    clearInterval(livePollTimer);
    livePollTimer = null;
  }
}

function startLivePoll() {
  if (!livePollTimer) {
    livePollTimer = setInterval(() => pollLive().catch(console.error), 400);
  }
  pollLive().catch(console.error);
}

async function startLive() {
  liveHint.textContent = "";
  const deviceId = micSelect.value === "" ? undefined : Number(micSelect.value);
  const body = {};
  if (Number.isFinite(deviceId)) {
    body.device_id = deviceId;
  }
  const job = await api("/api/live/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  liveJobId = job.id;
  startLivePoll();
}

async function stopLive() {
  await api("/api/live/stop", { method: "POST" });
  await pollLive();
  await refreshJobs();
}

recBtn.addEventListener("click", () => startLive().catch((err) => {
  liveHint.textContent = err.message || NO_MIC_HINT;
}));
stopBtn.addEventListener("click", () => stopLive().catch(console.error));
loadMics().catch(console.error);
