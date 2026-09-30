import { t } from "./i18n.js";

const store = new WeakMap();

const API_SECRET_SELECTOR =
  '#openrouter-key, #apify-key, #custom-key, #youtube-apify-key, [data-http-key]';

function ensureWrap(input) {
  if (input.closest(".secret-field-wrap")) {
    return input.closest(".secret-field-wrap");
  }
  const parent = input.parentNode;
  if (!parent) {
    return null;
  }
  const wrap = document.createElement("div");
  wrap.className = "secret-field-wrap";
  parent.insertBefore(wrap, input);
  wrap.appendChild(input);
  return wrap;
}

function ensureToggle(wrap, input) {
  let btn = wrap.querySelector(".secret-field-toggle");
  if (btn) {
    return btn;
  }
  btn = document.createElement("button");
  btn.type = "button";
  btn.className = "secret-field-toggle";
  btn.setAttribute("aria-label", t("secretField.show"));
  btn.setAttribute("aria-pressed", "false");
  const icon = document.createElement("span");
  icon.className = "material-symbols-outlined";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = "visibility";
  btn.appendChild(icon);
  wrap.appendChild(btn);
  btn.addEventListener("click", () => {
    const state = store.get(input);
    if (!state || !state.isSet) {
      return;
    }
    state.revealed = !state.revealed;
    applyDisplay(input, state);
    const show = state.revealed;
    icon.textContent = show ? "visibility_off" : "visibility";
    btn.setAttribute("aria-label", show ? t("secretField.hide") : t("secretField.show"));
    btn.setAttribute("aria-pressed", show ? "true" : "false");
  });
  return btn;
}

function applyDisplay(input, state) {
  input.type = "text";
  if (!state.isSet) {
    input.value = state.draft || "";
    return;
  }
  if (state.dirty) {
    input.value = state.draft;
    return;
  }
  input.value = state.revealed ? state.full : state.masked;
}

/**
 * @param {HTMLInputElement} input
 * @param {{ full?: string, masked?: string, isSet?: boolean }} opts
 */
export function bindSecretInput(input, opts = {}) {
  if (!input) {
    return;
  }
  const full = String(opts.full || "");
  const masked = String(opts.masked || "");
  const isSet = Boolean(opts.isSet) && Boolean(full || masked);
  const state = {
    full,
    masked: masked || full,
    isSet,
    revealed: false,
    dirty: false,
    draft: "",
  };
  store.set(input, state);
  input.type = "text";
  input.autocomplete = "off";
  applyDisplay(input, state);
  if (!input.dataset.secretBound) {
    input.dataset.secretBound = "1";
    input.addEventListener("input", () => {
      const cur = store.get(input);
      if (!cur) {
        return;
      }
      cur.dirty = true;
      cur.draft = input.value;
      store.set(input, cur);
    });
  }
  const wrap = ensureWrap(input);
  if (wrap) {
    ensureToggle(wrap, input);
  }
}

/** @returns {string|undefined} undefined = do not send api_key (unchanged) */
export function readSecretForSave(input) {
  if (!input) {
    return undefined;
  }
  const state = store.get(input);
  if (!state) {
    const raw = (input.value || "").trim();
    return raw || undefined;
  }
  if (!state.isSet && !state.dirty) {
    const raw = (input.value || "").trim();
    return raw || undefined;
  }
  if (!state.dirty) {
    return undefined;
  }
  const value = (state.draft || input.value || "").trim();
  return value;
}

/** Wrap non-API password inputs (e.g. proxy) with classic show/hide. */
export function initSecretFields(root = document) {
  const scope = root && root.querySelectorAll ? root : document;
  for (const input of scope.querySelectorAll('input[type="password"]')) {
    if (input.matches(API_SECRET_SELECTOR)) {
      continue;
    }
    if (input.closest(".secret-field-wrap")) {
      continue;
    }
    const wrap = ensureWrap(input);
    if (!wrap) {
      continue;
    }
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "secret-field-toggle";
    btn.setAttribute("aria-label", t("secretField.show"));
    btn.setAttribute("aria-pressed", "false");
    const icon = document.createElement("span");
    icon.className = "material-symbols-outlined";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = "visibility";
    btn.appendChild(icon);
    wrap.appendChild(btn);
    btn.addEventListener("click", () => {
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      icon.textContent = show ? "visibility_off" : "visibility";
      btn.setAttribute("aria-label", show ? t("secretField.hide") : t("secretField.show"));
      btn.setAttribute("aria-pressed", show ? "true" : "false");
    });
  }
}
