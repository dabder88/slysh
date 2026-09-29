let currentLocale = "ru";
let messages = {};
let i18nReady = false;
const listeners = new Set();

function browserLocaleHint() {
  const langs = navigator.languages?.length ? navigator.languages : [navigator.language];
  for (const raw of langs) {
    if (!raw) {
      continue;
    }
    const token = String(raw).toLowerCase().split("-")[0];
    if (token === "en") {
      return "en";
    }
    if (token === "ru") {
      return "ru";
    }
  }
  return "ru";
}

function resolvePath(obj, path) {
  return path.split(".").reduce((acc, part) => (acc && acc[part] != null ? acc[part] : undefined), obj);
}

const MESSAGE_KEY_LIKE = /^[a-z][\w\u0400-\u04FF]*(?:\.[\w\u0400-\u04FF]+)+$/i;

/** Follow locale values that point at other keys (max depth 4). */
export function resolveMessageChain(text) {
  if (typeof text !== "string") {
    return text;
  }
  let value = text;
  for (let depth = 0; depth < 4; depth += 1) {
    if (!MESSAGE_KEY_LIKE.test(value)) {
      break;
    }
    const next = resolvePath(messages, value);
    if (next == null || typeof next !== "string" || next === value) {
      break;
    }
    value = next;
  }
  return value;
}

export function getLocale() {
  return currentLocale;
}

/** BCP 47 tag for `toLocaleDateString` / `input[type=date].lang`. */
export function localeDateTag() {
  return currentLocale === "en" ? "en-US" : "ru-RU";
}

export function onLocaleChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function notifyLocaleChange() {
  for (const fn of listeners) {
    try {
      fn(currentLocale);
    } catch (err) {
      console.error(err);
    }
  }
}

async function loadMessages(locale) {
  const res = await fetch(`/locales/${locale}.json?v=13`);
  if (!res.ok) {
    throw new Error(`locale ${locale}`);
  }
  messages = await res.json();
}

async function localeApiGet(path) {
  const res = await fetch(path);
  if (!res.ok) {
    throw new Error(`locale api ${res.status}`);
  }
  return res.json();
}

async function localeApiPut(path, body) {
  const res = await fetch(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`locale api ${res.status}`);
  }
  const text = await res.text();
  return text ? JSON.parse(text) : {};
}

export function t(key, vars) {
  let value = resolvePath(messages, key);
  if (value == null) {
    if (!i18nReady && !Object.keys(messages).length) {
      console.error(`i18n: t("${key}") before initI18n()`);
    }
    return key;
  }
  if (typeof value !== "string") {
    return key;
  }
  value = resolveMessageChain(value);
  if (!vars) {
    return value;
  }
  return value.replace(/\{(\w+)\}/g, (_, name) => (vars[name] != null ? String(vars[name]) : ""));
}

function syncDateInputLocales(scope) {
  const tag = localeDateTag();
  document.documentElement.setAttribute("lang", tag);
  if (document.body) {
    document.body.setAttribute("lang", tag);
  }
  scope.querySelectorAll('input[type="date"]').forEach((el) => {
    if (el.dataset.dateLocaleSynced === tag) {
      return;
    }
    const parent = el.parentNode;
    if (!parent) {
      return;
    }
    const clone = document.createElement("input");
    clone.type = "date";
    clone.lang = tag;
    clone.setAttribute("lang", tag);
    if (el.id) {
      clone.id = el.id;
    }
    if (el.className) {
      clone.className = el.className;
    }
    if (el.name) {
      clone.name = el.name;
    }
    if (el.min) {
      clone.min = el.min;
    }
    if (el.max) {
      clone.max = el.max;
    }
    if (el.disabled) {
      clone.disabled = true;
    }
    clone.value = el.value;
    clone.dataset.dateLocaleSynced = tag;
    parent.replaceChild(clone, el);
  });
}

export function applyI18n(root) {
  const scope = root || document;
  scope.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (key) {
      el.textContent = t(key);
    }
  });
  scope.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.getAttribute("data-i18n-placeholder");
    if (key) {
      el.placeholder = t(key);
    }
  });
  scope.querySelectorAll("[data-i18n-title]").forEach((el) => {
    const key = el.getAttribute("data-i18n-title");
    if (key) {
      el.title = t(key);
    }
  });
  scope.querySelectorAll("[data-i18n-aria-label]").forEach((el) => {
    const key = el.getAttribute("data-i18n-aria-label");
    if (key) {
      el.setAttribute("aria-label", t(key));
    }
  });
  scope.querySelectorAll("[data-i18n-html]").forEach((el) => {
    const key = el.getAttribute("data-i18n-html");
    if (key) {
      el.innerHTML = t(key);
    }
  });
  syncDateInputLocales(scope);
}

export async function setLocale(locale, options = {}) {
  const next = locale === "en" ? "en" : "ru";
  if (next === currentLocale && !options.force) {
    applyI18n();
    return currentLocale;
  }
  await loadMessages(next);
  currentLocale = next;
  i18nReady = true;
  applyI18n();
  notifyLocaleChange();
  if (!options.skipSave) {
    await localeApiPut("/api/locale", { ui_locale: next });
  }
  return currentLocale;
}

export async function initI18n() {
  const hint = browserLocaleHint();
  let data;
  try {
    data = await localeApiGet(`/api/locale?hint=${encodeURIComponent(hint)}`);
  } catch (_) {
    data = { ui_locale: hint };
  }
  const locale = data.ui_locale === "en" ? "en" : "ru";
  await loadMessages(locale);
  currentLocale = locale;
  i18nReady = true;
  applyI18n();
  return currentLocale;
}

export function jobStatusLabel(status) {
  const key = `jobStatus.${status}`;
  const label = t(key);
  return label === key ? status : label;
}
