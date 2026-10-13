/**
 * ============================================================================
 * Slysh — Модуль «Избранные пути экспорта» (export-favorites.js)
 * Modern Pro Bento версия:
 * 1. Карточки в стиле Bento (только пути к папкам, без имён файлов).
 * 2. Поддержка кнопки-спойлера (в один ряд с «Добавить папку»).
 * 3. Динамический статус «В списке» для предотвращения дубликатов.
 * 4. Удаление из избранного в 1 клик прямо на карточке.
 * 5. 100% обратная совместимость со всеми существующими методами API.
 * ============================================================================
 */
import { api } from "./api.js";
import { t } from "./i18n.js";

let cachedDirs = null;
let exportFavoriteRemoveResolve = null;

const EXPORT_FILE_EXT_RE = /\.(srt|vtt|txt|md|json|ass|ssa)$/i;

export function normalizeFavoriteDirPath(path) {
  let value = String(path || "").trim();
  if (!value) {
    return "";
  }
  const base = value.split(/[/\\]/).pop() || "";
  if (EXPORT_FILE_EXT_RE.test(base)) {
    const slash = Math.max(value.lastIndexOf("/"), value.lastIndexOf("\\"));
    if (slash > 0) {
      value = value.slice(0, slash);
    }
  }
  return value.trim();
}

export function pathDirKey(path) {
  return String(path || "").trim().toLowerCase();
}

export function buildFavoriteKeySet(dirs) {
  const keys = new Set();
  for (const item of dirs || []) {
    const key = pathDirKey(item);
    if (key) {
      keys.add(key);
    }
  }
  return keys;
}

export async function fetchExportFavoriteDirs({ fresh = false } = {}) {
  if (!fresh && cachedDirs) {
    return [...cachedDirs];
  }
  const data = await api("/api/ui/export-favorites");
  cachedDirs = Array.isArray(data.dirs)
    ? data.dirs.map(normalizeFavoriteDirPath).filter(Boolean)
    : [];
  return [...cachedDirs];
}

export async function saveExportFavoriteDirs(dirs) {
  const normalized = (dirs || []).map(normalizeFavoriteDirPath).filter(Boolean);
  const data = await api("/api/ui/export-favorites", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dirs: normalized }),
  });
  cachedDirs = Array.isArray(data.dirs) ? data.dirs : [];
  return [...cachedDirs];
}

export async function mergeIntoFavorites(newDirs) {
  const current = await fetchExportFavoriteDirs({ fresh: true });
  const seen = new Set();
  const merged = [];
  for (const item of [...current, ...(newDirs || [])]) {
    const value = normalizeFavoriteDirPath(item);
    if (!value) {
      continue;
    }
    const key = value.toLowerCase();
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    merged.push(value);
  }
  return saveExportFavoriteDirs(merged);
}

export async function removeFavoriteDir(path) {
  const key = pathDirKey(path);
  if (!key) {
    return [];
  }
  const current = await fetchExportFavoriteDirs({ fresh: true });
  const next = current.filter((item) => pathDirKey(item) !== key);
  return saveExportFavoriteDirs(next);
}

export async function toggleFavoriteDir(path) {
  const trimmed = normalizeFavoriteDirPath(path);
  if (!trimmed) {
    return { dirs: await fetchExportFavoriteDirs({ fresh: true }), added: false, removed: false };
  }
  const current = await fetchExportFavoriteDirs({ fresh: true });
  const key = pathDirKey(trimmed);
  const exists = current.some((item) => pathDirKey(item) === key);
  if (exists) {
    const dirs = await removeFavoriteDir(trimmed);
    return { dirs, added: false, removed: true };
  }
  const dirs = await mergeIntoFavorites([trimmed]);
  return { dirs, added: true, removed: false };
}

export function invalidateExportFavoriteDirsCache() {
  cachedDirs = null;
}

export function collectDirsFromList(listEl) {
  if (!listEl) {
    return [];
  }
  const seen = new Set();
  const unique = [];
  for (const input of listEl.querySelectorAll(".export-dir-input")) {
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

export function collectExportTargetDirs(manualListEl) {
  return collectDirsFromList(manualListEl);
}

/**
 * Применяет выбранный путь к списку папок: заполняет пустую строку или добавляет новую.
 * @returns {"duplicate" | "filled" | "added" | "noop"}
 */
export function applyFavoritePathToExportList(listEl, path, rowOptions = {}) {
  if (!listEl) {
    return "noop";
  }
  const trimmed = normalizeFavoriteDirPath(path);
  if (!trimmed) {
    return "noop";
  }
  const targetKey = pathDirKey(trimmed);
  for (const input of listEl.querySelectorAll(".export-dir-input")) {
    if (pathDirKey(input.value) === targetKey) {
      input.focus();
      return "duplicate";
    }
  }
  const { favoriteKeys = null, onTargetDirsChanged = null } = rowOptions;
  for (const input of listEl.querySelectorAll(".export-dir-input")) {
    if (!(input.value || "").trim()) {
      input.value = trimmed;
      input.title = trimmed;
      const row = input.closest(".export-dir-row");
      if (row && favoriteKeys) {
        syncExportDirRowStar(row, favoriteKeys);
      }
      input.focus();
      onTargetDirsChanged?.();
      return "filled";
    }
  }
  addExportDirRowToList(listEl, trimmed, rowOptions);
  const lastInput = listEl.querySelector(".export-dir-row:last-child .export-dir-input");
  lastInput?.focus();
  onTargetDirsChanged?.();
  return "added";
}

export function syncExportDirRowStar(row, favoriteKeys) {
  if (!row || !favoriteKeys) {
    return;
  }
  const input = row.querySelector(".export-dir-input");
  const star = row.querySelector(".export-dir-favorite-star");
  if (!input || !star) {
    return;
  }
  const isFavorite = favoriteKeys.has(pathDirKey(input.value));
  star.classList.toggle("is-favorite", isFavorite);
  star.title = isFavorite
    ? t("exportUi.favoriteStarRemoveTooltip")
    : t("exportUi.favoriteStarSaveTooltip");
  star.setAttribute(
    "aria-label",
    isFavorite ? t("exportUi.favoriteStarRemoveTooltip") : t("exportUi.favoriteStarSaveTooltip")
  );
}

export function createExportDirRow(
  value = "",
  {
    onBrowse,
    favoriteKeys = null,
    onFavoriteToggled = null,
    showFavoriteStar = false,
    onTargetDirsChanged = null,
  } = {}
) {
  const row = document.createElement("div");
  row.className = "export-dir-row field-row";

  const input = document.createElement("input");
  input.type = "text";
  input.className = "export-dir-input";
  input.spellcheck = false;
  input.value = value;
  input.title = value;
  input.placeholder = t("exportUi.folderPathPlaceholder") || "Путь к папке…";
  input.addEventListener("input", () => {
    input.title = input.value;
  });

  const browseBtn = document.createElement("button");
  browseBtn.type = "button";
  browseBtn.className = "btn-outline btn-compact";
  browseBtn.dataset.act = "browse";
  browseBtn.title = t("common.browse");
  browseBtn.setAttribute("aria-label", t("common.browse"));
  browseBtn.innerHTML = `
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
    </svg>
  `;
  if (onBrowse) {
    browseBtn.addEventListener("click", () => {
      onBrowse(input).catch(() => {});
    });
  }

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "btn-outline btn-compact export-dir-remove";
  removeBtn.dataset.act = "remove";
  removeBtn.title = t("common.delete");
  removeBtn.setAttribute("aria-label", t("common.delete"));
  removeBtn.innerHTML = `
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
      <line x1="18" y1="6" x2="6" y2="18"></line>
      <line x1="6" y1="6" x2="18" y2="18"></line>
    </svg>
  `;
  removeBtn.addEventListener("click", () => {
    const list = row.parentElement;
    if (!list || list.querySelectorAll(".export-dir-row").length <= 1) {
      input.value = "";
      input.title = "";
      syncExportDirRemoveButtons(list);
      onTargetDirsChanged?.();
      return;
    }
    row.remove();
    syncExportDirRemoveButtons(list);
    onTargetDirsChanged?.();
  });

  const parts = [];
  if (showFavoriteStar && favoriteKeys) {
    const starBtn = document.createElement("button");
    starBtn.type = "button";
    starBtn.className = "export-dir-favorite-star";
    starBtn.innerHTML = `
      <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/>
      </svg>
    `;
    starBtn.addEventListener("click", () => {
      const path = (input.value || "").trim();
      if (!path) {
        return;
      }
      toggleFavoriteDir(path)
        .then((result) => onFavoriteToggled?.(result))
        .catch((err) => onFavoriteToggled?.({ error: err }));
    });
    input.addEventListener("input", () => syncExportDirRowStar(row, favoriteKeys));
    input.addEventListener("change", () => syncExportDirRowStar(row, favoriteKeys));
    parts.push(starBtn);
  }
  parts.push(input, browseBtn, removeBtn);
  row.append(...parts);
  if (showFavoriteStar && favoriteKeys) {
    syncExportDirRowStar(row, favoriteKeys);
  }
  return row;
}

export function syncExportDirRemoveButtons(listEl) {
  if (!listEl) {
    return;
  }
  const rows = listEl.querySelectorAll(".export-dir-row");
  const hideRemove = rows.length <= 1;
  rows.forEach((row) => {
    const removeBtn = row.querySelector('[data-act="remove"]');
    if (removeBtn) {
      removeBtn.hidden = hideRemove;
    }
  });
}

export function syncAllExportDirRowStars(listEl, favoriteKeys) {
  if (!listEl || !favoriteKeys) {
    return;
  }
  listEl.querySelectorAll(".export-dir-row").forEach((row) => {
    syncExportDirRowStar(row, favoriteKeys);
  });
}

export function fillExportDirsList(listEl, paths = [], rowOptions = {}) {
  if (!listEl) {
    return;
  }
  const items = Array.isArray(paths) ? paths : [paths];
  const normalized = items.length ? items : [""];
  listEl.replaceChildren();
  for (const path of normalized) {
    listEl.appendChild(createExportDirRow(path, rowOptions));
  }
  syncExportDirRemoveButtons(listEl);
}

export function addExportDirRowToList(listEl, value = "", rowOptions = {}) {
  if (!listEl) {
    return null;
  }
  const row = createExportDirRow(value, rowOptions);
  listEl.appendChild(row);
  syncExportDirRemoveButtons(listEl);
  return row;
}

/**
 * Инициализирует интерактивную кнопку-спойлер для раскрытия Bento-контейнера избранного.
 */
export function initExportFavoriteRemoveConfirm() {
  const modal = document.getElementById("export-favorite-remove-modal");
  const body = document.getElementById("export-favorite-remove-body");
  const confirmBtn = document.getElementById("export-favorite-remove-confirm");
  const cancelBtn = document.getElementById("export-favorite-remove-cancel");
  if (!modal || !confirmBtn || !cancelBtn) {
    return;
  }
  const finish = (value) => {
    modal.hidden = true;
    const resolve = exportFavoriteRemoveResolve;
    exportFavoriteRemoveResolve = null;
    resolve?.(value);
  };
  confirmBtn.addEventListener("click", () => finish(true));
  cancelBtn.addEventListener("click", () => finish(false));
  modal.addEventListener("click", (event) => {
    if (event.target === modal) {
      finish(false);
    }
  });
  modal._setExportFavoriteRemovePath = (path) => {
    if (body) {
      body.textContent = t("exportUi.favoriteRemoveBody", { path });
    }
  };
}

export function confirmExportFavoriteRemoval(path) {
  const modal = document.getElementById("export-favorite-remove-modal");
  if (!modal || typeof modal._setExportFavoriteRemovePath !== "function") {
    return Promise.resolve(window.confirm(t("exportUi.favoriteRemoveBody", { path })));
  }
  return new Promise((resolve) => {
    exportFavoriteRemoveResolve = resolve;
    modal._setExportFavoriteRemovePath(path);
    modal.hidden = false;
    document.getElementById("export-favorite-remove-cancel")?.focus();
  });
}

export function initExportFavoritesToggle({ toggleBtn, containerEl, countBadgeEl, count = 0 } = {}) {
  if (!toggleBtn || !containerEl) return;
  if (countBadgeEl) {
    countBadgeEl.textContent = String(count);
  }
  const startOpen = toggleBtn.classList.contains("is-open");
  containerEl.hidden = !startOpen;
  toggleBtn.setAttribute("aria-expanded", startOpen ? "true" : "false");

  toggleBtn.addEventListener("click", () => {
    const isOpen = toggleBtn.classList.contains("is-open");
    if (isOpen) {
      toggleBtn.classList.remove("is-open");
      toggleBtn.setAttribute("aria-expanded", "false");
      containerEl.hidden = true;
    } else {
      toggleBtn.classList.add("is-open");
      toggleBtn.setAttribute("aria-expanded", "true");
      containerEl.hidden = false;
    }
  });
}

/**
 * Рендерит список Bento-карточек избранных путей (ТОЛЬКО ПУТИ К ПАПКАМ, БЕЗ НАЗВАНИЙ ФАЙЛОВ).
 */
export function renderFavoritePickList(
  pickListEl,
  emptyHintEl,
  dirs,
  { onAdd = null, onRemove = null, targetListEl = null } = {}
) {
  if (!pickListEl) {
    return;
  }
  pickListEl.replaceChildren();
  const items = Array.isArray(dirs) ? dirs.filter((d) => String(d || "").trim()) : [];
  
  if (emptyHintEl) {
    emptyHintEl.hidden = items.length > 0;
  }

  // Обновляем бейдж счетчика в кнопке-спойлере, если он есть
  const badgeEl = document.getElementById("export-favorites-count-badge");
  if (badgeEl) {
    badgeEl.textContent = String(items.length);
  }

  // Собираем уже добавленные пути для проверки дублирования
  const currentKeys = new Set();
  if (targetListEl) {
    for (const input of targetListEl.querySelectorAll(".export-dir-input")) {
      const key = pathDirKey(normalizeFavoriteDirPath(input.value));
      if (key) currentKeys.add(key);
    }
  }

  for (const dir of items) {
    const folderPath = normalizeFavoriteDirPath(dir) || String(dir || "").trim();
    const card = document.createElement("div");
    card.className = "export-favorite-pick-row";
    const dirKey = pathDirKey(folderPath);
    const isAlreadyAdded = currentKeys.has(dirKey);

    if (isAlreadyAdded) {
      card.classList.add("is-selected");
    }

    // Левая часть: иконка папки + чистый путь к папке
    const left = document.createElement("div");
    left.className = "export-favorite-pick-row-left";

    const iconWrap = document.createElement("div");
    iconWrap.className = "export-favorite-folder-icon";
    iconWrap.innerHTML = isAlreadyAdded
      ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>`
      : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>`;

    const pathSpan = document.createElement("span");
    pathSpan.className = "export-favorite-pick-path";
    pathSpan.textContent = folderPath;
    pathSpan.title = folderPath;

    left.append(iconWrap, pathSpan);

    // Правая часть: кнопка добавления / статус "В списке" + кнопка удаления
    const right = document.createElement("div");
    right.className = "export-favorite-pick-row-actions";

    if (isAlreadyAdded) {
      const addedChip = document.createElement("span");
      addedChip.className = "export-favorite-chip-added";
      addedChip.innerHTML = `
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
        <span>${t("exportUi.inList") || "В списке"}</span>
      `;
      right.appendChild(addedChip);
    } else {
      const addBtn = document.createElement("button");
      addBtn.type = "button";
      addBtn.className = "export-favorite-add-btn";
      addBtn.innerHTML = `
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <line x1="12" y1="5" x2="12" y2="19"></line>
          <line x1="5" y1="12" x2="19" y2="12"></line>
        </svg>
        <span>${t("exportUi.add") || "Добавить"}</span>
      `;
      addBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        onAdd?.(folderPath);
      });
      right.appendChild(addBtn);
    }

    // Кнопка удаления из избранного (всплывает при hover)
    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "export-favorite-del-btn";
    delBtn.title = t("exportUi.favoriteStarRemoveTooltip") || "Убрать из избранного";
    delBtn.setAttribute("aria-label", delBtn.title);
    delBtn.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="18" y1="6" x2="6" y2="18"></line>
        <line x1="6" y1="6" x2="18" y2="18"></line>
      </svg>
    `;
    delBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      confirmExportFavoriteRemoval(folderPath).then((ok) => {
        if (!ok) {
          return;
        }
        removeFavoriteDir(folderPath).then((updatedDirs) => {
          if (onRemove) {
            onRemove(updatedDirs);
          } else {
            renderFavoritePickList(pickListEl, emptyHintEl, updatedDirs, { onAdd, onRemove, targetListEl });
          }
        });
      });
    });
    right.appendChild(delBtn);

    card.append(left, right);

    // Клик по всей карточке добавляет путь в список
    card.addEventListener("click", () => {
      if (!isAlreadyAdded && onAdd) {
        onAdd(folderPath);
      }
    });

    pickListEl.appendChild(card);
  }
}
