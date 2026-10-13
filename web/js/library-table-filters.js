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

const SOURCE_ICONS = {
  file: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>`,
  live: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="23"></line><line x1="8" y1="23" x2="16" y2="23"></line></svg>`,
  meeting: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path></svg>`,
  youtube: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="23 7 16 12 23 17 23 7"></polygon><rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect></svg>`,
};

function updateFiltersBadge(summary, filters) {
  const badge = summary.querySelector(".library-filters-badge");
  const count = countActiveFilters(filters);
  if (!badge) {
    return;
  }
  const textEl = badge.querySelector(".library-filters-badge-text");
  if (count > 0) {
    badge.hidden = false;
    if (textEl) {
      textEl.textContent = t("filters.activeCount", { count });
    }
  } else {
    badge.hidden = true;
    if (textEl) {
      textEl.textContent = "";
    }
  }
}

export function createFiltersSpoiler({ storageKey, filters, onChange }) {
  const details = document.createElement("details");
  details.className = "library-filters-spoiler";
  details.open = isFiltersOpen(storageKey);
  details.addEventListener("toggle", () => {
    setFiltersOpen(storageKey, details.open);
  });

  const summary = document.createElement("summary");
  summary.className = "library-filters-summary";

  const summaryLeft = document.createElement("div");
  summaryLeft.className = "library-filters-summary-left";

  const chevron = document.createElement("span");
  chevron.className = "library-filters-chevron";
  chevron.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"></polyline></svg>`;

  const summaryIcon = document.createElement("div");
  summaryIcon.className = "library-filters-summary-icon";
  summaryIcon.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"></polygon></svg>`;

  const summaryTitle = document.createElement("span");
  summaryTitle.className = "library-filters-summary-title";
  summaryTitle.textContent = t("filters.title");

  const badge = document.createElement("span");
  badge.className = "library-filters-badge";
  badge.hidden = true;
  const badgeDot = document.createElement("span");
  badgeDot.className = "library-filters-badge-dot";
  badgeDot.setAttribute("aria-hidden", "true");
  const badgeText = document.createElement("span");
  badgeText.className = "library-filters-badge-text";
  badge.append(badgeDot, badgeText);

  summaryLeft.append(chevron, summaryIcon, summaryTitle, badge);

  const summaryRight = document.createElement("div");
  summaryRight.className = "library-filters-summary-right";

  const quickResetBtn = document.createElement("button");
  quickResetBtn.type = "button";
  quickResetBtn.className = "library-filters-quick-reset";
  quickResetBtn.title = t("filters.reset");
  quickResetBtn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg><span>${t("filters.reset")}</span>`;

  summaryRight.appendChild(quickResetBtn);
  summary.append(summaryLeft, summaryRight);
  details.appendChild(summary);

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

  const topRow = document.createElement("div");
  topRow.className = "library-filters-top-row";

  const searchField = document.createElement("div");
  searchField.className = "library-filter-field library-filter-field--search";

  const searchLabel = document.createElement("div");
  searchLabel.className = "library-filter-label";
  searchLabel.textContent = t("common.name");

  const searchBox = document.createElement("div");
  searchBox.className = "library-filter-search-box";

  const searchIcon = document.createElement("span");
  searchIcon.className = "library-filter-search-icon";
  searchIcon.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>`;

  const searchInput = document.createElement("input");
  searchInput.type = "search";
  searchInput.className = "library-filter-search-input";
  searchInput.placeholder = t("filters.namePlaceholder");
  searchInput.value = filters.name || "";
  searchInput.autocomplete = "off";

  let searchDebounceTimer = null;
  searchInput.addEventListener("input", () => {
    filters.name = searchInput.value.trim().toLowerCase();
    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => emitChange(), 250);
  });

  const searchClearBtn = document.createElement("button");
  searchClearBtn.type = "button";
  searchClearBtn.className = "library-filter-search-clear";
  searchClearBtn.textContent = "✕";
  searchClearBtn.title = t("filters.clearSearch");
  searchClearBtn.addEventListener("click", () => {
    searchInput.value = "";
    filters.name = "";
    emitChange();
    searchInput.focus();
  });

  searchBox.append(searchIcon, searchInput, searchClearBtn);
  searchField.append(searchLabel, searchBox);

  const speakersField = document.createElement("div");
  speakersField.className = "library-filter-field library-filter-field--speakers";

  const speakersLabel = document.createElement("div");
  speakersLabel.className = "library-filter-label";
  speakersLabel.textContent = t("filters.speakers");

  const speakersSelect = document.createElement("select");
  speakersSelect.className = "library-filter-select";
  for (const opt of speakersFilterOptions()) {
    const optEl = document.createElement("option");
    optEl.value = opt.id;
    optEl.textContent = opt.label;
    speakersSelect.appendChild(optEl);
  }
  speakersSelect.value = filters.speakers || "any";
  speakersSelect.addEventListener("change", () => {
    filters.speakers = speakersSelect.value;
    emitChange();
  });
  speakersField.append(speakersLabel, speakersSelect);

  const resetBtnWrap = document.createElement("div");
  resetBtnWrap.className = "library-filter-field library-filter-field--reset";

  const resetBtnLabel = document.createElement("div");
  resetBtnLabel.className = "library-filter-label";
  resetBtnLabel.style.visibility = "hidden";
  resetBtnLabel.textContent = "—";

  const fullResetBtn = document.createElement("button");
  fullResetBtn.type = "button";
  fullResetBtn.className = "library-filter-btn-reset";
  fullResetBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path></svg><span>${t("filters.reset")}</span>`;

  resetBtnWrap.append(resetBtnLabel, fullResetBtn);
  topRow.append(searchField, speakersField, resetBtnWrap);
  body.appendChild(topRow);

  const bentoGrid = document.createElement("div");
  bentoGrid.className = "library-filters-bento-grid";

  const colSources = document.createElement("div");
  colSources.className = "library-filter-col-sources";

  const sourcesLabel = document.createElement("div");
  sourcesLabel.className = "library-filter-label";
  sourcesLabel.textContent = t("libraryTable.source");

  const sourcesGrid = document.createElement("div");
  sourcesGrid.className = "library-filter-grid-2x2";

  const sourceButtons = new Map();
  for (const [kind, meta] of Object.entries(jobSourceKinds())) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "library-filter-chip";
    chip.dataset.source = kind;
    chip.innerHTML = `${SOURCE_ICONS[kind] || ""}<span>${meta.label}</span>`;
    if (filters.sources.includes(kind)) {
      chip.classList.add("is-active");
    }
    chip.addEventListener("click", () => {
      chip.classList.toggle("is-active");
      const activeSources = [];
      sourceButtons.forEach((btn, k) => {
        if (btn.classList.contains("is-active")) {
          activeSources.push(k);
        }
      });
      filters.sources = activeSources;
      emitChange();
    });
    sourceButtons.set(kind, chip);
    sourcesGrid.appendChild(chip);
  }
  colSources.append(sourcesLabel, sourcesGrid);

  const divider1 = document.createElement("div");
  divider1.className = "library-filter-v-divider";

  const colStatuses = document.createElement("div");
  colStatuses.className = "library-filter-col-statuses";

  const statusesLabel = document.createElement("div");
  statusesLabel.className = "library-filter-label";
  statusesLabel.textContent = t("libraryTable.status");

  const statusesGrid = document.createElement("div");
  statusesGrid.className = "library-filter-grid-3x2";

  const statusButtons = new Map();
  for (const opt of jobStatusFilterOptions()) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "library-filter-chip";
    chip.dataset.status = opt.id;
    chip.innerHTML = `<span class="library-filter-status-dot"></span><span>${opt.label}</span>`;
    if (filters.statuses.includes(opt.id)) {
      chip.classList.add("is-active");
    }
    chip.addEventListener("click", () => {
      chip.classList.toggle("is-active");
      const activeStatuses = [];
      statusButtons.forEach((btn, id) => {
        if (btn.classList.contains("is-active")) {
          activeStatuses.push(id);
        }
      });
      filters.statuses = activeStatuses;
      emitChange();
    });
    statusButtons.set(opt.id, chip);
    statusesGrid.appendChild(chip);
  }
  colStatuses.append(statusesLabel, statusesGrid);

  const divider2 = document.createElement("div");
  divider2.className = "library-filter-v-divider";

  const colRanges = document.createElement("div");
  colRanges.className = "library-filter-col-ranges";

  const rangesLabel = document.createElement("div");
  rangesLabel.className = "library-filter-label";
  rangesLabel.textContent = t("filters.periodAndDuration");

  const rangesStack = document.createElement("div");
  rangesStack.className = "library-filter-ranges-stack";

  const dateRow = document.createElement("div");
  dateRow.className = "library-filter-range-compact-row";

  const dateTag = document.createElement("span");
  dateTag.className = "library-filter-range-tag";
  dateTag.textContent = t("filters.rangeDateTag");

  const dateFromInput = document.createElement("input");
  dateFromInput.type = "date";
  dateFromInput.lang = localeDateTag();
  dateFromInput.setAttribute("lang", localeDateTag());
  dateFromInput.className = "library-filter-range-input";
  dateFromInput.value = filters.dateFrom || "";
  dateFromInput.title = t("filters.dateFrom");
  dateFromInput.addEventListener("change", () => {
    filters.dateFrom = dateFromInput.value;
    emitChange();
  });

  const dateDivider = document.createElement("span");
  dateDivider.className = "library-filter-range-divider";
  dateDivider.textContent = "—";

  const dateToInput = document.createElement("input");
  dateToInput.type = "date";
  dateToInput.lang = localeDateTag();
  dateToInput.setAttribute("lang", localeDateTag());
  dateToInput.className = "library-filter-range-input";
  dateToInput.value = filters.dateTo || "";
  dateToInput.title = t("filters.dateTo");
  dateToInput.addEventListener("change", () => {
    filters.dateTo = dateToInput.value;
    emitChange();
  });

  dateRow.append(dateTag, dateFromInput, dateDivider, dateToInput);

  const durRow = document.createElement("div");
  durRow.className = "library-filter-range-compact-row";

  const durTag = document.createElement("span");
  durTag.className = "library-filter-range-tag";
  durTag.textContent = t("filters.rangeMinTag");

  const durMinInput = document.createElement("input");
  durMinInput.type = "number";
  durMinInput.min = "0";
  durMinInput.step = "1";
  durMinInput.placeholder = t("filters.durationFromPlaceholder");
  durMinInput.className = "library-filter-range-input";
  durMinInput.value = filters.durationMin || "";
  durMinInput.title = t("filters.durationMin");
  durMinInput.addEventListener("change", () => {
    filters.durationMin = durMinInput.value.trim();
    emitChange();
  });

  const durDivider = document.createElement("span");
  durDivider.className = "library-filter-range-divider";
  durDivider.textContent = "—";

  const durMaxInput = document.createElement("input");
  durMaxInput.type = "number";
  durMaxInput.min = "0";
  durMaxInput.step = "1";
  durMaxInput.placeholder = t("filters.durationToPlaceholder");
  durMaxInput.className = "library-filter-range-input";
  durMaxInput.value = filters.durationMax || "";
  durMaxInput.title = t("filters.durationMax");
  durMaxInput.addEventListener("change", () => {
    filters.durationMax = durMaxInput.value.trim();
    emitChange();
  });

  durRow.append(durTag, durMinInput, durDivider, durMaxInput);

  rangesStack.append(dateRow, durRow);
  colRanges.append(rangesLabel, rangesStack);

  bentoGrid.append(colSources, divider1, colStatuses, divider2, colRanges);
  body.appendChild(bentoGrid);

  details.appendChild(body);

  function resetAllFilters() {
    Object.assign(filters, defaultFilters());
    searchInput.value = "";
    speakersSelect.value = "any";
    dateFromInput.value = "";
    dateToInput.value = "";
    durMinInput.value = "";
    durMaxInput.value = "";
    sourceButtons.forEach((btn) => btn.classList.remove("is-active"));
    statusButtons.forEach((btn) => btn.classList.remove("is-active"));
    emitChange();
  }

  quickResetBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    event.preventDefault();
    resetAllFilters();
  });
  fullResetBtn.addEventListener("click", () => resetAllFilters());

  updateFiltersBadge(summary, filters);
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
