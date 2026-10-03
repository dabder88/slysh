import { t, onLocaleChange } from "./i18n.js";

let stripEl = null;
let btnEl = null;
let modeEl = null;
let modelEl = null;
let lastData = null;
let routeVisible = true;
let onOpenSettings = null;

function splitModelCatalogLabel(label) {
  const text = String(label || "").trim();
  const sep = text.indexOf(" · ");
  if (sep > 0) {
    return { title: text.slice(0, sep), meta: text.slice(sep + 3) };
  }
  return { title: text, meta: "" };
}

function providerShortLabel(label) {
  const text = String(label || "").trim();
  if (!text) {
    return "";
  }
  const sep = text.indexOf(" · ");
  return sep > 0 ? text.slice(0, sep) : text;
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

function resolveDisplay(data) {
  const items = data.items || [];
  const cloudOnly = Boolean(data.cloud_only);
  let source = data.source === "provider" ? "provider" : "local";
  if (cloudOnly) {
    source = "provider";
  }
  const isCloud = source === "provider";

  let modelItem = null;
  if (isCloud) {
    const remoteId = pickRemoteModelId(data);
    modelItem = items.find((item) => item.id === remoteId) || null;
    if (!modelItem && data.selected) {
      const sel = items.find((item) => item.id === data.selected);
      if (sel && sel.kind !== "local") {
        modelItem = sel;
      }
    }
  } else {
    const selectedId = data.selected || data.selected_local || "";
    modelItem =
      items.find((item) => item.id === selectedId && item.kind === "local") ||
      items.find((item) => item.id === data.selected_local) ||
      items.find((item) => item.kind === "local" && item.ready) ||
      items.find((item) => item.kind === "local") ||
      null;
  }

  let modelLabel = "";
  let notReady = false;
  if (modelItem) {
    const raw = isCloud
      ? providerShortLabel(modelItem.label)
      : splitModelCatalogLabel(modelItem.label).title;
    modelLabel = raw || modelItem.label || "";
    notReady = modelItem.ready === false;
  } else {
    modelLabel = t("topbar.asrNotConfigured");
    notReady = true;
  }

  if (!modelLabel.trim()) {
    modelLabel = t("topbar.asrNotConfigured");
    notReady = true;
  } else if (notReady) {
    modelLabel = `${modelLabel} · ${t("topbar.asrNotReady")}`;
  }

  return {
    isCloud,
    modeLabel: isCloud ? t("topbar.asrCloud") : t("topbar.asrLocal"),
    modelLabel,
    notReady,
  };
}

function paint() {
  if (!stripEl || !btnEl || !modeEl || !modelEl) {
    return;
  }
  if (!lastData || !routeVisible) {
    stripEl.hidden = true;
    return;
  }
  const display = resolveDisplay(lastData);
  stripEl.hidden = false;
  btnEl.classList.toggle("is-local", !display.isCloud);
  btnEl.classList.toggle("is-cloud", display.isCloud);
  btnEl.classList.toggle("is-not-ready", display.notReady);
  modeEl.textContent = display.modeLabel;
  modelEl.textContent = display.modelLabel;
}

export function updateAsrContextBar(data) {
  if (data && typeof data === "object") {
    lastData = data;
  }
  paint();
}

export function setAsrContextBarRouteVisible(routeName) {
  routeVisible = routeName !== "youtube";
  paint();
}

export function initAsrContextBar(options = {}) {
  onOpenSettings = options.onOpenSettings || null;
  stripEl = document.getElementById("topbar-asr-strip");
  btnEl = document.getElementById("topbar-asr-strip-btn");
  modeEl = document.getElementById("topbar-asr-mode");
  modelEl = document.getElementById("topbar-asr-model");
  if (!stripEl || !btnEl) {
    return;
  }
  btnEl.addEventListener("click", () => {
    if (typeof onOpenSettings === "function") {
      onOpenSettings();
    }
  });
  onLocaleChange(() => {
    paint();
  });
  paint();
}
