import { jobDisplayName } from "./api.js";
import { batchDoneCount, batchFileCount } from "./library-utils.js";
import { jobSourceKinds, jobSourceKind } from "./job-source.js";
import { localeDateTag, t } from "./i18n.js";

export function jobStatusFilterOptions() {
  return [
    { id: "idle", label: t("jobStatus.idle") },
    { id: "queued", label: t("jobStatus.queued") },
    { id: "running", label: t("jobStatus.running") },
    { id: "completed", label: t("jobStatus.completed") },
    { id: "failed", label: t("jobStatus.failed") },
    { id: "cancelled", label: t("jobStatus.cancelled") },
  ];
}

export function speakersFilterOptions() {
  return [
    { id: "any", label: t("common.any") },
    { id: "yes", label: t("common.yes") },
    { id: "no", label: t("common.no") },
    { id: "running", label: t("libraryTable.running") },
    { id: "error", label: t("common.error") },
    { id: "empty", label: t("common.dash") },
  ];
}

export function pageSizeOptions() {
  return [
    { value: 10, label: "10" },
    { value: 30, label: "30" },
    { value: 50, label: "50" },
    { value: 0, label: t("common.all") },
  ];
}

export function defaultFilters() {
  return {
    name: "",
    sources: [],
    dateFrom: "",
    dateTo: "",
    durationMin: "",
    durationMax: "",
    statuses: [],
    speakers: "any",
  };
}

const pageByStorageKey = new Map();
const filtersOpenByStorageKey = new Map();

export function isFiltersOpen(storageKey) {
  return Boolean(filtersOpenByStorageKey.get(storageKey));
}

export function setFiltersOpen(storageKey, open) {
  filtersOpenByStorageKey.set(storageKey, Boolean(open));
}

function filtersStorageKey(storageKey) {
  return `library-table-filters-${storageKey}`;
}

function pageSizeStorageKey(storageKey) {
  return `library-table-page-size-${storageKey}`;
}

function normalizeFilters(raw) {
  const base = defaultFilters();
  if (!raw || typeof raw !== "object") {
    return base;
  }
  const sources = Array.isArray(raw.sources)
    ? raw.sources.filter((id) => id in jobSourceKinds())
    : [];
  const statuses = Array.isArray(raw.statuses)
    ? raw.statuses.filter((id) => jobStatusFilterOptions().some((opt) => opt.id === id))
    : [];
  const speakers = speakersFilterOptions().some((opt) => opt.id === raw.speakers)
    ? raw.speakers
    : "any";
  return {
    name: String(raw.name || "").trim().toLowerCase(),
    sources,
    dateFrom: String(raw.dateFrom || ""),
    dateTo: String(raw.dateTo || ""),
    durationMin: String(raw.durationMin || "").trim(),
    durationMax: String(raw.durationMax || "").trim(),
    statuses,
    speakers,
  };
}

export function loadFilters(storageKey) {
  try {
    const raw = localStorage.getItem(filtersStorageKey(storageKey));
    if (!raw) {
      return defaultFilters();
    }
    return normalizeFilters(JSON.parse(raw));
  } catch (_) {
    return defaultFilters();
  }
}

export function saveFilters(storageKey, filters) {
  localStorage.setItem(filtersStorageKey(storageKey), JSON.stringify(normalizeFilters(filters)));
}

export function loadPageSize(storageKey) {
  try {
    const raw = localStorage.getItem(pageSizeStorageKey(storageKey));
    const value = Number(raw);
    if (!Number.isFinite(value)) {
      return 30;
    }
    if (value === 0 || pageSizeOptions().some((opt) => opt.value === value)) {
      return value;
    }
    return 30;
  } catch (_) {
    return 30;
  }
}

export function savePageSize(storageKey, pageSize) {
  localStorage.setItem(pageSizeStorageKey(storageKey), String(pageSize));
}

export function getPage(storageKey) {
  return pageByStorageKey.get(storageKey) || 1;
}

export function setPage(storageKey, page) {
  pageByStorageKey.set(storageKey, Math.max(1, Number(page) || 1));
}

export function resetPage(storageKey) {
  pageByStorageKey.set(storageKey, 1);
}

export function countActiveFilters(filters) {
  const normalized = normalizeFilters(filters);
  let count = 0;
  if (normalized.name) {
    count += 1;
  }
  if (normalized.sources.length) {
    count += 1;
  }
  if (normalized.dateFrom || normalized.dateTo) {
    count += 1;
  }
  if (normalized.durationMin || normalized.durationMax) {
    count += 1;
  }
  if (normalized.statuses.length) {
    count += 1;
  }
  if (normalized.speakers !== "any") {
    count += 1;
  }
  return count;
}

function batchDisplayName(batch) {
  return String(batch?.name || t("legacy.batchNumber", { id: batch?.id || "" })).toLowerCase();
}

function parseMinutes(value) {
  if (value === "" || value == null) {
    return null;
  }
  const num = Number(value);
  return Number.isFinite(num) && num >= 0 ? num * 60 : null;
}

function dateOnly(iso) {
  if (!iso) {
    return "";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function matchesDateRange(iso, filters) {
  const value = dateOnly(iso);
  if (!value) {
    return !filters.dateFrom && !filters.dateTo;
  }
  if (filters.dateFrom && value < filters.dateFrom) {
    return false;
  }
  if (filters.dateTo && value > filters.dateTo) {
    return false;
  }
  return true;
}

function matchesDurationRange(durationS, filters) {
  const minS = parseMinutes(filters.durationMin);
  const maxS = parseMinutes(filters.durationMax);
  if (minS == null && maxS == null) {
    return true;
  }
  if (durationS == null || durationS < 0) {
    return false;
  }
  if (minS != null && durationS < minS) {
    return false;
  }
  if (maxS != null && durationS > maxS) {
    return false;
  }
  return true;
}

function jobEffectiveStatus(job) {
  if (job.speakers_running || job.engine_starting) {
    return "running";
  }
  return String(job.status || "idle");
}

function speakersCategory(job) {
  if (!job) {
    return "empty";
  }
  if (job.speakers_running) {
    return "running";
  }
  if (job.speakers_error) {
    return "error";
  }
  const count = Number(job.speaker_count || 0);
  if (count > 0 || job.has_speakers) {
    return "yes";
  }
  if (job.status === "completed") {
    return "no";
  }
  return "empty";
}

function matchesSpeakersFilter(job, speakersFilter) {
  if (speakersFilter === "any") {
    return true;
  }
  return speakersCategory(job) === speakersFilter;
}

function matchesName(text, query) {
  if (!query) {
    return true;
  }
  return String(text || "").toLowerCase().includes(query);
}

function batchMaxDuration(batch) {
  const jobs = batch?.jobs || [];
  let max = -1;
  for (const job of jobs) {
    if (job.duration_s != null) {
      max = Math.max(max, Number(job.duration_s));
    }
  }
  return max < 0 ? null : max;
}

function batchMatchesStatus(batch, statuses) {
  if (!statuses.length) {
    return true;
  }
  if (batch.running && statuses.includes("running")) {
    return true;
  }
  for (const job of batch.jobs || []) {
    if (statuses.includes(jobEffectiveStatus(job))) {
      return true;
    }
  }
  const total = batchFileCount(batch);
  const done = batchDoneCount(batch);
  if (!batch.running && done === 0 && statuses.includes("idle")) {
    return true;
  }
  if (!batch.running && total > 0 && done === total && statuses.includes("completed")) {
    return true;
  }
  return false;
}

export function jobMatchesFilters(job, filters) {
  const normalized = normalizeFilters(filters);
  if (!matchesName(jobDisplayName(job), normalized.name)) {
    return false;
  }
  if (normalized.sources.length && !normalized.sources.includes(jobSourceKind(job))) {
    return false;
  }
  if (!matchesDateRange(job.created_at, normalized)) {
    return false;
  }
  if (!matchesDurationRange(job.duration_s == null ? null : Number(job.duration_s), normalized)) {
    return false;
  }
  if (normalized.statuses.length && !normalized.statuses.includes(jobEffectiveStatus(job))) {
    return false;
  }
  if (!matchesSpeakersFilter(job, normalized.speakers)) {
    return false;
  }
  return true;
}

function batchMatchesFilters(batch, filters) {
  const normalized = normalizeFilters(filters);
  if (!matchesName(batchDisplayName(batch), normalized.name)) {
    return false;
  }
  if (!matchesDateRange(batch.created_at, normalized)) {
    return false;
  }
  if (!matchesDurationRange(batchMaxDuration(batch), normalized)) {
    return false;
  }
  if (!batchMatchesStatus(batch, normalized.statuses)) {
    return false;
  }
  const jobs = batch.jobs || [];
  const needsJobMatch =
    normalized.sources.length > 0 || normalized.speakers !== "any";
  if (needsJobMatch) {
    return jobs.some((job) => jobMatchesFilters(job, normalized));
  }
  return true;
}

export function applyLibraryFilters({ jobs, batches, filters }) {
  const normalized = normalizeFilters(filters);
  const filteredJobs = (jobs || []).filter((job) => jobMatchesFilters(job, normalized));
  const filteredBatches = (batches || [])
    .filter((batch) => batchMatchesFilters(batch, normalized))
    .map((batch) => ({
      ...batch,
      jobs: (batch.jobs || []).filter((job) => jobMatchesFilters(job, normalized)),
    }));
  return { jobs: filteredJobs, batches: filteredBatches };
}

export function paginateItems(items, page, pageSize) {
  const total = items.length;
  if (!total) {
    return { items: [], page: 1, totalPages: 1, total };
  }
  const size = pageSize > 0 ? pageSize : total;
  const totalPages = Math.max(1, Math.ceil(total / size));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const start = (safePage - 1) * size;
  return {
    items: items.slice(start, start + size),
    page: safePage,
    totalPages,
    total,
  };
}

function updateFiltersBadge(summary, filters) {
  const badge = summary.querySelector(".library-filters-badge");
  const active = countActiveFilters(filters);
  if (!badge) {
    return;
  }
  badge.textContent = active ? `· ${active}` : "";
  badge.hidden = !active;
}

export function createFiltersSpoiler({ storageKey, filters, onChange }) {
  const details = document.createElement("details");
  details.className = "library-filters-spoiler";
  details.open = isFiltersOpen(storageKey);
  details.addEventListener("toggle", () => {
    setFiltersOpen(storageKey, details.open);
  });

  const summary = document.createElement("summary");
  const summaryText = document.createElement("span");
  summaryText.textContent = t("filters.title");
  summary.appendChild(summaryText);
  const badge = document.createElement("span");
  badge.className = "library-filters-badge spoiler-meta";
  summary.appendChild(badge);
  details.appendChild(summary);
  updateFiltersBadge(summary, filters);

  const body = document.createElement("div");
  body.className = "library-filters-body";

  const emitChange = (resetPageOnChange = true) => {
    saveFilters(storageKey, filters);
    updateFiltersBadge(summary, filters);
    if (resetPageOnChange) {
      resetPage(storageKey);
    }
    onChange();
  };

  const nameField = document.createElement("label");
  nameField.className = "library-filter-field";
  nameField.textContent = t("common.name");
  const nameInput = document.createElement("input");
  nameInput.type = "search";
  nameInput.className = "library-filter-input";
  nameInput.placeholder = t("filters.namePlaceholder");
  nameInput.value = filters.name;
  nameInput.autocomplete = "off";
  let nameDebounceTimer = null;
  nameInput.addEventListener("input", () => {
    filters.name = nameInput.value.trim().toLowerCase();
    clearTimeout(nameDebounceTimer);
    nameDebounceTimer = setTimeout(() => emitChange(), 250);
  });
  nameField.appendChild(nameInput);
  body.appendChild(nameField);

  const sourceGroup = document.createElement("fieldset");
  sourceGroup.className = "library-filter-fieldset";
  const sourceLegend = document.createElement("legend");
  sourceLegend.textContent = t("libraryTable.source");
  sourceGroup.appendChild(sourceLegend);
  const sourceGrid = document.createElement("div");
  sourceGrid.className = "library-filter-checks";
  for (const [kind, meta] of Object.entries(jobSourceKinds())) {
    const label = document.createElement("label");
    label.className = "library-filter-check";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = kind;
    box.checked = filters.sources.includes(kind);
    box.addEventListener("change", () => {
      filters.sources = [...sourceGrid.querySelectorAll("input:checked")].map((el) => el.value);
      emitChange();
    });
    label.append(box, document.createTextNode(meta.label));
    sourceGrid.appendChild(label);
  }
  sourceGroup.appendChild(sourceGrid);
  body.appendChild(sourceGroup);

  const dateRow = document.createElement("div");
  dateRow.className = "library-filter-row";
  const dateFromField = document.createElement("label");
  dateFromField.className = "library-filter-field";
  dateFromField.textContent = t("filters.dateFrom");
  const dateFromInput = document.createElement("input");
  dateFromInput.type = "date";
  dateFromInput.lang = localeDateTag();
  dateFromInput.setAttribute("lang", localeDateTag());
  dateFromInput.className = "library-filter-input";
  dateFromInput.value = filters.dateFrom;
  dateFromInput.addEventListener("change", () => {
    filters.dateFrom = dateFromInput.value;
    emitChange();
  });
  dateFromField.appendChild(dateFromInput);
  const dateToField = document.createElement("label");
  dateToField.className = "library-filter-field";
  dateToField.textContent = t("filters.dateTo");
  const dateToInput = document.createElement("input");
  dateToInput.type = "date";
  dateToInput.lang = localeDateTag();
  dateToInput.setAttribute("lang", localeDateTag());
  dateToInput.className = "library-filter-input";
  dateToInput.value = filters.dateTo;
  dateToInput.addEventListener("change", () => {
    filters.dateTo = dateToInput.value;
    emitChange();
  });
  dateToField.appendChild(dateToInput);
  dateRow.append(dateFromField, dateToField);
  body.appendChild(dateRow);

  const durationRow = document.createElement("div");
  durationRow.className = "library-filter-row";
  const durationMinField = document.createElement("label");
  durationMinField.className = "library-filter-field";
  durationMinField.textContent = t("filters.durationMin");
  const durationMinInput = document.createElement("input");
  durationMinInput.type = "number";
  durationMinInput.min = "0";
  durationMinInput.step = "1";
  durationMinInput.className = "library-filter-input";
  durationMinInput.value = filters.durationMin;
  durationMinInput.addEventListener("change", () => {
    filters.durationMin = durationMinInput.value.trim();
    emitChange();
  });
  durationMinField.appendChild(durationMinInput);
  const durationMaxField = document.createElement("label");
  durationMaxField.className = "library-filter-field";
  durationMaxField.textContent = t("filters.durationMax");
  const durationMaxInput = document.createElement("input");
  durationMaxInput.type = "number";
  durationMaxInput.min = "0";
  durationMaxInput.step = "1";
  durationMaxInput.className = "library-filter-input";
  durationMaxInput.value = filters.durationMax;
  durationMaxInput.addEventListener("change", () => {
    filters.durationMax = durationMaxInput.value.trim();
    emitChange();
  });
  durationMaxField.appendChild(durationMaxInput);
  durationRow.append(durationMinField, durationMaxField);
  body.appendChild(durationRow);

  const statusGroup = document.createElement("fieldset");
  statusGroup.className = "library-filter-fieldset";
  const statusLegend = document.createElement("legend");
  statusLegend.textContent = t("libraryTable.status");
  statusGroup.appendChild(statusLegend);
  const statusGrid = document.createElement("div");
  statusGrid.className = "library-filter-checks";
  for (const opt of jobStatusFilterOptions()) {
    const label = document.createElement("label");
    label.className = "library-filter-check";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = opt.id;
    box.checked = filters.statuses.includes(opt.id);
    box.addEventListener("change", () => {
      filters.statuses = [...statusGrid.querySelectorAll("input:checked")].map((el) => el.value);
      emitChange();
    });
    label.append(box, document.createTextNode(opt.label));
    statusGrid.appendChild(label);
  }
  statusGroup.appendChild(statusGrid);
  body.appendChild(statusGroup);

  const speakersField = document.createElement("label");
  speakersField.className = "library-filter-field";
  speakersField.textContent = t("filters.speakers");
  const speakersSelect = document.createElement("select");
  speakersSelect.className = "library-filter-input";
  for (const opt of speakersFilterOptions()) {
    const option = document.createElement("option");
    option.value = opt.id;
    option.textContent = opt.label;
    speakersSelect.appendChild(option);
  }
  speakersSelect.value = filters.speakers;
  speakersSelect.addEventListener("change", () => {
    filters.speakers = speakersSelect.value;
    emitChange();
  });
  speakersField.appendChild(speakersSelect);
  body.appendChild(speakersField);

  const actions = document.createElement("div");
  actions.className = "library-filters-actions";
  const resetBtn = document.createElement("button");
  resetBtn.type = "button";
  resetBtn.className = "btn-outline btn-compact";
  resetBtn.textContent = t("filters.reset");
  resetBtn.addEventListener("click", () => {
    Object.assign(filters, defaultFilters());
    nameInput.value = "";
    dateFromInput.value = "";
    dateToInput.value = "";
    durationMinInput.value = "";
    durationMaxInput.value = "";
    speakersSelect.value = "any";
    sourceGrid.querySelectorAll("input").forEach((el) => {
      el.checked = false;
    });
    statusGrid.querySelectorAll("input").forEach((el) => {
      el.checked = false;
    });
    emitChange();
  });
  actions.appendChild(resetBtn);
  body.appendChild(actions);

  details.appendChild(body);
  return details;
}

export function createPaginationBar({
  total,
  page,
  pageSize,
  onPageChange,
  onPageSizeChange,
}) {
  const footer = document.createElement("div");
  footer.className = "library-table-footer";

  const size = pageSize > 0 ? pageSize : total;
  const totalPages = total ? Math.max(1, Math.ceil(total / size)) : 1;
  const safePage = Math.min(Math.max(1, page), totalPages);
  const start = total ? (safePage - 1) * size + 1 : 0;
  const end = total ? Math.min(total, safePage * size) : 0;

  const summary = document.createElement("span");
  summary.className = "library-table-footer-summary hint";
  summary.textContent = total
    ? t("library_table_filters.shownRange", { start, end, total })
    : t("libraryTable.noRecords");
  footer.appendChild(summary);

  const nav = document.createElement("div");
  nav.className = "library-table-footer-nav";

  const prevBtn = document.createElement("button");
  prevBtn.type = "button";
  prevBtn.className = "btn-outline btn-compact";
  prevBtn.textContent = t("common.back");
  prevBtn.disabled = safePage <= 1 || !total;
  prevBtn.addEventListener("click", () => onPageChange(safePage - 1));
  nav.appendChild(prevBtn);

  const pageInfo = document.createElement("span");
  pageInfo.className = "library-table-footer-page hint";
  pageInfo.textContent = total
    ? t("library_table_filters.pageOf", { page: safePage, pages: totalPages })
    : "";
  nav.appendChild(pageInfo);

  const nextBtn = document.createElement("button");
  nextBtn.type = "button";
  nextBtn.className = "btn-outline btn-compact";
  nextBtn.textContent = t("filters.next");
  nextBtn.disabled = safePage >= totalPages || !total;
  nextBtn.addEventListener("click", () => onPageChange(safePage + 1));
  nav.appendChild(nextBtn);

  footer.appendChild(nav);

  const sizeWrap = document.createElement("label");
  sizeWrap.className = "library-table-footer-size";
  const sizeLabel = document.createElement("span");
  sizeLabel.className = "hint";
  sizeLabel.textContent = t("filters.perPage");
  const sizeSelect = document.createElement("select");
  sizeSelect.className = "library-filter-input";
  for (const opt of pageSizeOptions()) {
    const option = document.createElement("option");
    option.value = String(opt.value);
    option.textContent = opt.label;
    sizeSelect.appendChild(option);
  }
  sizeSelect.value = String(pageSize);
  sizeSelect.addEventListener("change", () => {
    onPageSizeChange(Number(sizeSelect.value));
  });
  sizeWrap.append(sizeLabel, sizeSelect);
  footer.appendChild(sizeWrap);

  return footer;
}
