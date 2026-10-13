import { basename, formatDuration, jobDisplayName, isYoutubeJob, showToast } from "./api.js";
import { msIcon } from "./icons.js";
import {
  formatBatchCountsSummary,
  speakersBadgeClass,
  speakersStatusLabel,
} from "./library-utils.js";
import { jobSourceBadgeClass, jobSourceLabel, jobSourceMeta } from "./job-source.js";
import { isYoutubeBatch, youtubeBatchSourceLabel } from "./batch-kind.js";
import { patchBatchName, jobStatusLabel } from "./library-store.js";
import { localeDateTag, t } from "./i18n.js";
import {
  applyLibraryFilters,
  createFiltersSpoiler,
  createPaginationBar,
  getPage,
  loadFilters,
  loadPageSize,
  paginateItems,
  resetPage,
  savePageSize,
  setPage,
} from "./library-table-filters.js";

const SORT_ICON_IDLE =
  '<svg class="library-sort-svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><path d="M8 9l4-4 4 4"/><path d="M8 15l4 4 4-4"/></svg>';
const SORT_ICON_ASC =
  '<svg class="library-sort-svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><path d="M8 15l4-4 4 4"/></svg>';
const SORT_ICON_DESC =
  '<svg class="library-sort-svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><path d="M8 9l4 4 4-4"/></svg>';

function appendSortIndicator(parent, colKey, sort) {
  const indicator = document.createElement("span");
  indicator.className = "library-sort-indicator";
  if (sort.key === colKey) {
    indicator.classList.add("is-active");
    indicator.innerHTML = sort.dir === "asc" ? SORT_ICON_ASC : SORT_ICON_DESC;
  } else {
    indicator.classList.add("is-muted");
    indicator.innerHTML = SORT_ICON_IDLE;
  }
  parent.appendChild(indicator);
}

function tableColumns() {
  return [
    { key: "name", label: t("common.name"), min: 120, default: 260 },
    { key: "source", label: t("libraryTable.source"), min: 96, default: 128 },
    { key: "date", label: t("libraryTable.date"), min: 80, default: 110 },
    { key: "duration", label: t("libraryTable.duration"), min: 80, default: 110 },
    { key: "status", label: t("libraryTable.status"), min: 160, default: 200 },
    { key: "speakers", label: t("libraryTable.identifySpeakers"), min: 120, default: 160 },
  ];
}

const lastRangeIndexByKey = new Map();
const tableOptionsByShell = new WeakMap();

function resolveTableOptions(dynamic, options) {
  const shell = dynamic.closest(".library-table-shell");
  if (!shell) {
    return options;
  }
  return tableOptionsByShell.get(shell) || options;
}

function loadWidths(storageKey) {
  try {
    const raw = localStorage.getItem(`library-table-widths-${storageKey}`);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    return Object.fromEntries(
      tableColumns().map((col) => {
        const value = Number(parsed?.[col.key]);
        if (!Number.isFinite(value)) {
          return [col.key, col.default];
        }
        return [col.key, Math.max(col.min, value)];
      })
    );
  } catch (_) {
    return null;
  }
}

function saveWidths(storageKey, widths) {
  localStorage.setItem(`library-table-widths-${storageKey}`, JSON.stringify(widths));
}

function loadSort(storageKey) {
  try {
    const raw = localStorage.getItem(`library-table-sort-${storageKey}`);
    if (!raw) {
      return { key: "date", dir: "desc" };
    }
    const parsed = JSON.parse(raw);
    if (!tableColumns().some((col) => col.key === parsed?.key)) {
      return { key: "date", dir: "desc" };
    }
    if (parsed.dir !== "asc" && parsed.dir !== "desc") {
      return { key: "date", dir: "desc" };
    }
    return { key: parsed.key, dir: parsed.dir };
  } catch (_) {
    return { key: "date", dir: "desc" };
  }
}

function saveSort(storageKey, sort) {
  localStorage.setItem(`library-table-sort-${storageKey}`, JSON.stringify(sort));
}

function formatDate(iso) {
  if (!iso) {
    return t("common.dash");
  }
  return new Date(iso).toLocaleDateString(localeDateTag(), {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function mediaIconName(jobOrPath) {
  if (typeof jobOrPath === "object" && jobOrPath?.kind === "youtube") {
    return "video_library";
  }
  const path = typeof jobOrPath === "object" ? jobOrPath?.source_path : jobOrPath;
  return /\.(mp4|mov|mkv|avi|webm)$/i.test(String(path || "")) ? "video_file" : "audio_file";
}

function bindColumnResize(table, storageKey, widths) {
  const headers = table.querySelectorAll("th[data-col-key]");
  headers.forEach((th, index) => {
    if (index >= headers.length - 1) {
      return;
    }
    const handle = document.createElement("span");
    handle.className = "library-col-resizer";
    handle.title = t("libraryTable.resizeColumn");
    th.appendChild(handle);
    let startX = 0;
    let startWidth = 0;
    const colKey = th.dataset.colKey;
    const onMove = (event) => {
      const col = tableColumns().find((c) => c.key === colKey);
      const min = col?.min || 60;
      const next = Math.max(min, startWidth + event.clientX - startX);
      widths[colKey] = next;
      table.style.setProperty(`--col-${colKey}`, `${next}px`);
      saveWidths(storageKey, widths);
    };
    const onUp = () => {
      handle.classList.remove("is-active");
      document.body.classList.remove("is-resizing-cols");
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    handle.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      event.stopPropagation();
      startX = event.clientX;
      startWidth = th.getBoundingClientRect().width;
      handle.classList.add("is-active");
      document.body.classList.add("is-resizing-cols");
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    });
  });
}

function applyWidths(table, widths) {
  for (const col of tableColumns()) {
    const w = widths[col.key] || col.default;
    table.style.setProperty(`--col-${col.key}`, `${w}px`);
  }
}

function statusBadgeClass(tone) {
  const map = {
    done: "archive-badge--done",
    err: "archive-badge--err",
    cancel: "archive-badge--cancel",
    run: "archive-badge--run",
    queue: "archive-badge--queue",
    idle: "archive-badge--idle",
  };
  return map[tone] || "archive-badge--done";
}

function jobName(job) {
  return jobDisplayName(job);
}

function batchName(batch) {
  return batch.name || t("legacy.batchNumber", { id: batch.id });
}

function sortValue(item, key, options) {
  if (item.kind === "batch") {
    const batch = item.batch;
    if (key === "name") {
      return batchName(batch).toLowerCase();
    }
    if (key === "source") {
      return "";
    }
    if (key === "date") {
      return String(batch.created_at || "");
    }
    if (key === "duration") {
      return -1;
    }
    if (key === "status") {
      return formatBatchCountsSummary(batch).toLowerCase();
    }
    return "";
  }
  const job = item.job;
  if (key === "name") {
    return jobName(job).toLowerCase();
  }
  if (key === "source") {
    return jobSourceLabel(job).toLowerCase();
  }
  if (key === "date") {
    return String(job.created_at || "");
  }
  if (key === "duration") {
    return job.duration_s == null ? -1 : Number(job.duration_s);
  }
  if (key === "status") {
    return String(options.jobStatusLabel(job) || "").toLowerCase();
  }
  return speakersStatusLabel(job).toLowerCase();
}

function compareItems(a, b, sort, options) {
  const av = sortValue(a, sort.key, options);
  const bv = sortValue(b, sort.key, options);
  let cmp = 0;
  if (typeof av === "number" && typeof bv === "number") {
    cmp = av - bv;
  } else {
    cmp = String(av).localeCompare(String(bv), "ru");
  }
  if (cmp === 0) {
    const aDate = a.kind === "batch" ? a.batch.created_at : a.job.created_at;
    const bDate = b.kind === "batch" ? b.batch.created_at : b.job.created_at;
    cmp = String(bDate || "").localeCompare(String(aDate || ""));
  }
  return sort.dir === "asc" ? cmp : -cmp;
}

function nextSort(current, key) {
  if (current.key === key) {
    return { key, dir: current.dir === "asc" ? "desc" : "asc" };
  }
  if (key === "name" || key === "status" || key === "speakers" || key === "source") {
    return { key, dir: "asc" };
  }
  return { key, dir: "desc" };
}

function jobKey(job) {
  return `job:${job.id}`;
}

function batchKey(batch) {
  return `batch:${batch.id}`;
}

function appendSelectCell(tr, { checked, onToggle, stopRow }) {
  const td = document.createElement("td");
  td.className = "library-table-check";
  const box = document.createElement("input");
  box.type = "checkbox";
  box.className = "library-check";
  box.checked = checked;
  box.addEventListener("click", (event) => {
    event.stopPropagation();
    onToggle(event);
  });
  td.appendChild(box);
  if (stopRow) {
    td.addEventListener("click", (event) => event.stopPropagation());
  }
  tr.appendChild(td);
}

function appendEmptySelectCell(tr) {
  const td = document.createElement("td");
  td.className = "library-table-check";
  tr.appendChild(td);
}

function renderJobRow(job, options, indent = false) {
  const tr = document.createElement("tr");
  const key = jobKey(job);
  const selected = Boolean(options.selectable && options.selectedKeys?.has(key));
  tr.className = `queue-table-row library-table-row${indent ? " library-table-row--child" : ""}${
    selected ? " is-selected" : ""
  }`;
  tr.dataset.rowKey = key;

  if (options.selectable) {
    if (indent) {
      appendEmptySelectCell(tr);
    } else {
      appendSelectCell(tr, {
        checked: selected,
        onToggle: (event) => options.onToggleKey(key, event),
        stopRow: true,
      });
    }
  }

  const nameCell = document.createElement("td");
  nameCell.className = "queue-table-name";
  const nameInner = document.createElement("div");
  nameInner.className = "queue-table-name-inner";
  if (indent) {
    nameInner.classList.add("library-table-name-inner--child");
  }
  nameInner.appendChild(msIcon(mediaIconName(job)));
  const nameText = document.createElement("span");
  nameText.className = "archive-table-filename";
  nameText.textContent = jobName(job);
  nameText.title = job.source_path || "";
  nameInner.appendChild(nameText);
  nameCell.appendChild(nameInner);

  const sourceCell = document.createElement("td");
  sourceCell.className = "library-table-source";
  const sourceBadge = document.createElement("span");
  const sourceMeta = jobSourceMeta(job);
  sourceBadge.className = jobSourceBadgeClass(job);
  sourceBadge.textContent = sourceMeta.label;
  sourceBadge.title = sourceMeta.title;
  sourceCell.appendChild(sourceBadge);

  const dateCell = document.createElement("td");
  dateCell.className = "hint";
  dateCell.textContent = formatDate(job.created_at);

  const durationCell = document.createElement("td");
  durationCell.className = "hint";
  durationCell.textContent = job.duration_s != null ? formatDuration(job.duration_s) : t("common.dash");

  const statusCell = document.createElement("td");
  statusCell.className = "library-table-status";
  const badge = document.createElement("span");
  const tone = options.jobStatusTone(job);
  badge.className = `archive-badge ${statusBadgeClass(tone)}`;
  badge.textContent = options.jobStatusLabel(job);
  badge.title = badge.textContent;
  statusCell.appendChild(badge);

  const speakersCell = document.createElement("td");
  speakersCell.className = "library-table-speakers";
  const speakersBadge = document.createElement("span");
  speakersBadge.className = `speakers-badge ${speakersBadgeClass(job)}`;
  speakersBadge.textContent = speakersStatusLabel(job);
  speakersBadge.title = speakersBadge.textContent;
  speakersCell.appendChild(speakersBadge);

  tr.appendChild(nameCell);
  tr.appendChild(sourceCell);
  tr.appendChild(dateCell);
  tr.appendChild(durationCell);
  tr.appendChild(statusCell);
  tr.appendChild(speakersCell);
  tr.addEventListener("click", (event) => {
    if (options.selectable && event.shiftKey) {
      options.onToggleKey(key, event);
      return;
    }
    options.onJobClick(job);
  });
  tr.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    options.onJobContextMenu(event, job, job.batch_id ?? null);
  });
  return tr;
}

function renderBatchRow(batch, options) {
  const expanded = options.expandedBatches.has(batch.id);
  const tr = document.createElement("tr");
  const key = batchKey(batch);
  const selected = Boolean(options.selectable && options.selectedKeys?.has(key));
  tr.className = `queue-table-row library-table-row library-table-row--batch${
    selected ? " is-selected" : ""
  }`;
  tr.dataset.rowKey = key;

  if (options.selectable) {
    appendSelectCell(tr, {
      checked: selected,
      onToggle: (event) => options.onToggleKey(key, event),
      stopRow: true,
    });
  }

  const nameCell = document.createElement("td");
  nameCell.className = "queue-table-name";
  const nameInner = document.createElement("div");
  nameInner.className = "queue-table-name-inner library-table-name-inner--batch";
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "library-batch-toggle icon-btn";
  toggle.title = expanded ? t("sidebar.collapse") : t("libraryTable.expand");
  toggle.appendChild(msIcon(expanded ? "expand_less" : "chevron_right"));
  toggle.addEventListener("click", (event) => {
    event.stopPropagation();
    if (expanded) {
      options.expandedBatches.delete(batch.id);
    } else {
      options.expandedBatches.add(batch.id);
    }
    options.onExpandChange();
  });
  nameInner.appendChild(toggle);
  nameInner.appendChild(msIcon(isYoutubeBatch(batch) ? "playlist_play" : "folder_zip"));
  const nameText = document.createElement("span");
  nameText.className = "archive-table-filename";
  nameText.textContent = batchName(batch);
  nameInner.appendChild(nameText);
  const renameBtn = document.createElement("button");
  renameBtn.type = "button";
  renameBtn.className = "library-batch-rename icon-btn";
  renameBtn.title = t("queue.renameBatch");
  renameBtn.appendChild(msIcon("edit"));
  renameBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    const current = batchName(batch);
    const next = window.prompt(t("queue.batchNamePrompt"), current);
    if (next == null) {
      return;
    }
    const trimmed = next.trim();
    if (!trimmed || trimmed === current) {
      return;
    }
    patchBatchName(batch.id, trimmed)
      .then(() => {
        showToast("queue.batchNameSaved");
        options.onExpandChange();
      })
      .catch((err) => showToast(err.message || String(err)));
  });
  nameInner.appendChild(renameBtn);
  nameCell.appendChild(nameInner);

  const sourceCell = document.createElement("td");
  sourceCell.className = "hint library-table-source";
  if (isYoutubeBatch(batch)) {
    const sourceBadge = document.createElement("span");
    sourceBadge.className = "job-source-badge job-source-badge--youtube";
    sourceBadge.textContent = t("libraryTable.youtubeBatch");
    sourceBadge.title = youtubeBatchSourceLabel(batch);
    sourceCell.appendChild(sourceBadge);
  } else {
    sourceCell.textContent = t("common.dash");
  }

  const dateCell = document.createElement("td");
  dateCell.className = "hint";
  dateCell.textContent = formatDate(batch.created_at);

  const durationCell = document.createElement("td");
  durationCell.className = "hint";
  durationCell.textContent = t("common.dash");

  const statusCell = document.createElement("td");
  statusCell.className = "library-table-status";
  const badge = document.createElement("span");
  badge.className = `archive-badge ${batch.running ? "archive-badge--run" : "archive-badge--done"}`;
  badge.textContent = formatBatchCountsSummary(batch);
  badge.title = badge.textContent;
  statusCell.appendChild(badge);

  const speakersCell = document.createElement("td");
  speakersCell.className = "hint library-table-speakers";
  speakersCell.textContent = t("common.dash");

  tr.appendChild(nameCell);
  tr.appendChild(sourceCell);
  tr.appendChild(dateCell);
  tr.appendChild(durationCell);
  tr.appendChild(statusCell);
  tr.appendChild(speakersCell);
  tr.addEventListener("click", (event) => {
    if (options.selectable && event.shiftKey) {
      options.onToggleKey(key, event);
      return;
    }
    options.onBatchClick(batch);
  });
  tr.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    event.stopPropagation();
    options.onBatchContextMenu(event, batch);
  });
  return { row: tr, expanded };
}

function resolveBulkActions(options) {
  if (options.bulkActions?.length) {
    return options.bulkActions;
  }
  if (options.bulkKind === "batches") {
    return [
      ["start", t("batch_panel.k2124285")],
      ["cancel", t("common.stop")],
      ["archive", t("transcripts.toArchive")],
      ["export", t("common.export")],
      ["delete", t("common.delete")],
    ];
  }
  return [
    ["start", t("common.transcribe")],
    ["cancel", t("common.stop")],
    ["archive", t("transcripts.toArchive")],
    ["export", t("common.export")],
    ["to-batch", t("libraryTable.toBatch")],
    ["delete", t("common.delete")],
  ];
}

function createBulkBar(options, selectedCount) {
  const bar = document.createElement("div");
  bar.className = "library-bulk-bar";
  if (!selectedCount) {
    bar.hidden = true;
    return bar;
  }
  const count = document.createElement("span");
  count.className = "library-bulk-count";
  count.textContent = t("libraryTable.selected", { count: selectedCount });
  bar.appendChild(count);
  const actions = resolveBulkActions(options);
  for (const [id, label] of actions) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = id === "delete" ? "btn-danger btn-compact" : "btn-outline btn-compact";
    btn.textContent = label;
    btn.addEventListener("click", () => options.onBulkAction(id));
    bar.appendChild(btn);
  }
  return bar;
}

function syncRowSelected(wrap, selectedKeys) {
  wrap.querySelectorAll("tr[data-row-key]").forEach((tr) => {
    const key = tr.dataset.rowKey;
    const on = selectedKeys.has(key);
    tr.classList.toggle("is-selected", on);
    const box = tr.querySelector("input.library-check");
    if (box) {
      box.checked = on;
    }
  });
}

function renderLibraryTableDynamic(dynamic, options) {
  const {
    storageKey,
    jobs,
    batches,
    emptyMessage,
    jobStatusLabel,
    jobStatusTone,
    onJobClick,
    onJobContextMenu,
    onBatchContextMenu,
    onBatchClick,
    expandedBatches,
    onExpandChange,
    selectable = false,
    selectedKeys = null,
    bulkKind = "files",
    bulkActions = null,
    onBulkAction = null,
  } = options;

  const refreshTable = () => {
    renderLibraryTableDynamic(dynamic, resolveTableOptions(dynamic, options));
  };
  const hasSourceData = jobs.length > 0 || batches.length > 0;
  const filters = loadFilters(storageKey);
  const pageSize = loadPageSize(storageKey);
  let page = getPage(storageKey);

  dynamic.replaceChildren();

  if (!hasSourceData) {
    const empty = document.createElement("p");
    empty.className = "hint archive-empty";
    empty.textContent = emptyMessage;
    dynamic.appendChild(empty);
    dynamic.appendChild(
      createPaginationBar({
        total: 0,
        page: 1,
        pageSize,
        onPageChange: (nextPage) => {
          setPage(storageKey, nextPage);
          refreshTable();
        },
        onPageSizeChange: (nextSize) => {
          savePageSize(storageKey, nextSize);
          resetPage(storageKey);
          refreshTable();
        },
      })
    );
    return;
  }

  const { jobs: filteredJobs, batches: filteredBatches } = applyLibraryFilters({
    jobs,
    batches,
    filters,
  });

  if (!filteredJobs.length && !filteredBatches.length) {
    const empty = document.createElement("p");
    empty.className = "hint archive-empty";
    empty.textContent = t("libraryTable.noFilterMatch");
    dynamic.appendChild(empty);
    dynamic.appendChild(
      createPaginationBar({
        total: 0,
        page: 1,
        pageSize,
        onPageChange: (nextPage) => {
          setPage(storageKey, nextPage);
          refreshTable();
        },
        onPageSizeChange: (nextSize) => {
          savePageSize(storageKey, nextSize);
          resetPage(storageKey);
          refreshTable();
        },
      })
    );
    return;
  }

  const widths = loadWidths(storageKey) || Object.fromEntries(tableColumns().map((c) => [c.key, c.default]));
  const sort = loadSort(storageKey);
  const wrap = document.createElement("div");
  wrap.className = "archive-table-wrap library-table-wrap";
  const table = document.createElement("table");
  table.className = "queue-table archive-table library-table";
  applyWidths(table, widths);

  const allTopItems = [
    ...filteredBatches.map((batch) => ({ kind: "batch", batch })),
    ...filteredJobs.map((job) => ({ kind: "job", job })),
  ].sort((a, b) => compareItems(a, b, sort, { jobStatusLabel }));

  const pagination = paginateItems(allTopItems, page, pageSize);
  page = pagination.page;
  setPage(storageKey, page);
  const topItems = pagination.items;
  const topKeys = topItems.map((item) =>
    item.kind === "batch" ? batchKey(item.batch) : jobKey(item.job)
  );

  const applySelection = () => {
    if (!selectable || !selectedKeys) {
      return;
    }
    syncRowSelected(wrap, selectedKeys);
    const nextBar = createBulkBar(
      { bulkKind, bulkActions, onBulkAction },
      selectedKeys.size
    );
    const prevBar = wrap.querySelector(".library-bulk-bar");
    if (prevBar) {
      prevBar.replaceWith(nextBar);
    }
    const selectAll = wrap.querySelector("thead input.library-check");
    if (selectAll) {
      const selectedTop = topKeys.filter((key) => selectedKeys.has(key)).length;
      selectAll.checked = topKeys.length > 0 && selectedTop === topKeys.length;
      selectAll.indeterminate = selectedTop > 0 && selectedTop < topKeys.length;
    }
  };

  const onToggleKey = (key, event) => {
    if (!selectable || !selectedKeys) {
      return;
    }
    const index = topKeys.indexOf(key);
    if (event.shiftKey && lastRangeIndexByKey.has(storageKey) && index >= 0) {
      const from = lastRangeIndexByKey.get(storageKey);
      const start = Math.min(from, index);
      const end = Math.max(from, index);
      for (let i = start; i <= end; i += 1) {
        selectedKeys.add(topKeys[i]);
      }
    } else if (selectedKeys.has(key)) {
      selectedKeys.delete(key);
    } else {
      selectedKeys.add(key);
    }
    if (index >= 0) {
      lastRangeIndexByKey.set(storageKey, index);
    }
    applySelection();
  };

  if (selectable && onBulkAction) {
    wrap.appendChild(
      createBulkBar({ bulkKind, bulkActions, onBulkAction }, selectedKeys?.size || 0)
    );
  }

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  if (selectable) {
    const th = document.createElement("th");
    th.className = "library-th-select";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.className = "library-check";
    box.title = t("libraryTable.selectAll");
    box.addEventListener("click", (event) => {
      event.stopPropagation();
      if (!selectedKeys) {
        return;
      }
      const allOn = topKeys.every((key) => selectedKeys.has(key));
      if (allOn) {
        for (const key of topKeys) {
          selectedKeys.delete(key);
        }
      } else {
        for (const key of topKeys) {
          selectedKeys.add(key);
        }
      }
      applySelection();
    });
    th.appendChild(box);
    headRow.appendChild(th);
  }
  for (const col of tableColumns()) {
    const th = document.createElement("th");
    th.dataset.colKey = col.key;
    th.className = "library-th-sort";
    if (sort.key === col.key) {
      th.classList.add("library-th-sorted");
      th.setAttribute("aria-sort", sort.dir === "asc" ? "ascending" : "descending");
    } else {
      th.setAttribute("aria-sort", "none");
    }
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "library-th-sort-btn";
    const label = document.createElement("span");
    label.className = "library-th-label";
    label.textContent = col.label;
    btn.appendChild(label);
    appendSortIndicator(btn, col.key, sort);
    btn.addEventListener("click", (event) => {
      event.stopPropagation();
      saveSort(storageKey, nextSort(sort, col.key));
      refreshTable();
    });
    th.appendChild(btn);
    headRow.appendChild(th);
  }
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  const rowOptions = {
    expandedBatches,
    onExpandChange,
    onBatchClick,
    onBatchContextMenu,
    onJobClick,
    onJobContextMenu,
    jobStatusLabel,
    jobStatusTone,
    selectable,
    selectedKeys,
    onToggleKey,
  };

  for (const item of topItems) {
    if (item.kind === "batch") {
      const { row, expanded } = renderBatchRow(item.batch, rowOptions);
      tbody.appendChild(row);
      if (expanded) {
        for (const job of item.batch.jobs || []) {
          tbody.appendChild(renderJobRow(job, rowOptions, true));
        }
      }
    } else {
      tbody.appendChild(renderJobRow(item.job, rowOptions));
    }
  }

  table.appendChild(tbody);
  bindColumnResize(table, storageKey, widths);
  wrap.appendChild(table);
  applySelection();
  dynamic.appendChild(wrap);
  dynamic.appendChild(
    createPaginationBar({
      total: pagination.total,
      page: pagination.page,
      pageSize,
      onPageChange: (nextPage) => {
        setPage(storageKey, nextPage);
        refreshTable();
      },
      onPageSizeChange: (nextSize) => {
        savePageSize(storageKey, nextSize);
        resetPage(storageKey);
        refreshTable();
      },
    })
  );
}

function setupLibraryTableShell(shell, options) {
  tableOptionsByShell.set(shell, options);
  let dynamic = shell.querySelector(".library-table-dynamic");
  if (!dynamic) {
    dynamic = document.createElement("div");
    dynamic.className = "library-table-dynamic";
    const filters = loadFilters(options.storageKey);
    shell.appendChild(
      createFiltersSpoiler({
        storageKey: options.storageKey,
        filters,
        onChange: () => {
          renderLibraryTableDynamic(dynamic, resolveTableOptions(dynamic, options));
        },
      })
    );
    shell.appendChild(dynamic);
  }
  renderLibraryTableDynamic(dynamic, options);
}

export function mountLibraryTable(container, options) {
  container.replaceChildren();
  const shell = document.createElement("div");
  shell.className = "library-table-shell";
  container.appendChild(shell);
  setupLibraryTableShell(shell, options);
}

export function createLibraryTable(options) {
  const shell = document.createElement("div");
  shell.className = "library-table-shell";
  setupLibraryTableShell(shell, options);
  return shell;
}
