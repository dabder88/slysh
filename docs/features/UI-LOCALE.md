# Язык интерфейса (RU / EN)

Переключатель в **Настройки → Язык интерфейса**. Выбор сохраняется в `settings.json` как `ui_locale` (`ru` или `en`). Окно перезапускать не нужно: после смены языка вызываются `applyI18n()` и перерисовка активного экрана.

## Первый запуск

Если `ui_locale` ещё не задан, фронтенд шлёт `GET /api/locale?hint=…`, где `hint` — `en`, если в `navigator.languages` есть английский, иначе `ru`. Сервер записывает значение в settings и возвращает его.

Установщик `Slysh-Setup.exe` перед первым запуском пишет `{install_root}/.install-ui-locale` (`ru` или `en`). При старте `app.py` вызывает `consume_install_ui_locale_seed()` **до** `configure_webview_browser_language()`, чтобы WebView2 сразу получил `--lang=ru-RU` или `--lang=en-US`. Файл seed одноразовый; язык потом меняется в Настройках.

## Файлы

| Путь | Назначение |
|------|------------|
| `web/js/i18n.js` | `initI18n`, `t`, `setLocale`, `applyI18n`, `onLocaleChange` |
| `web/locales/ru.json`, `en.json` | Словари (ключи должны совпадать 1:1) |
| `src/slysh/ui_locale.py` | Чтение/запись `ui_locale` |
| `web/index.html` | Статический текст: `data-i18n`, `data-i18n-placeholder`, … |

## Добавление строк

1. Добавьте ключ в **оба** `ru.json` и `en.json` (вложенность через точку в `t("section.key")`).
2. В разметке: `data-i18n="section.key"` на узел с текстом (не на иконки Material Symbols). Для кнопок с иконкой — `data-i18n` на внутренний `<span>`, не на `<button>`. HTML из словаря — `data-i18n-html` (только доверенные строки из `locales/`).
3. В JS: `import { t, localeDateTag } from "./i18n.js"` (без `?v=` в пути импорта) и `t("section.key", { var: value })` для подстановок `{var}`. Даты: `toLocaleDateString(localeDateTag(), …)`.
4. Динамические списки: подпишитесь на `onLocaleChange` или полагайтесь на `notifyCurrentRoute()` в `main.js`.
5. Кэш-бастинг: только importmap в `index.html` (`"/js/i18n.js": "/js/i18n.js?v=…"`) и `?v=` у `/locales/*.json` в `loadMessages`. **Нельзя** писать `./i18n.js?v=NN` в импортах других модулей — иначе `initI18n()` загрузит словарь в другой экземпляр модуля, и в UI останутся сырые ключи (`common.done`, `libraryTable.source`, …).

Паритет ключей и отсутствие кириллицы в `en.json` (значения): `tests/test_i18n_locales.py`.

Скрипты сопровождения (при массовом добавлении `page.*` или slug-ключей):

- `scripts/gen_page_en_patch.py` → `web/locales/page.en.patch.json`
- `scripts/sync_en_locale_text.py` — подстановка `page.en.patch` и `ru→en` по совпадающим фразам
- `scripts/fix_batch_panel_locale_keys.py`, `scripts/translate_en_locales.py` — дочистка `en.json` (перевод оставшихся RU-строк)

## API

- `GET /api/locale?hint=en` — текущая локаль (и первичная инициализация).
- `PUT /api/locale` — body `{ "ui_locale": "ru" | "en" }`.

Подсказки GPU/CPU в настройках (`GET /api/compute`) локализуются по сохранённому `ui_locale`.

## Календари (`input type="date"`)

Нативный вид даты в WebView2 (Chromium) задаётся флагом `--lang=en-US` / `--lang=ru-RU` при старте приложения (`configure_webview_browser_language()` в `app.py`, по `ui_locale` из settings). В JS при смене языка: `lang` на `<html>`, `<body>` и полях, пересоздание контролов в `applyI18n()`.

Если после переключения EN/RU в настройках подпись даты осталась на старом языке — **перезапустите Slysh** (или «Перезагрузить окно» в настройках): флаг Chromium читается только при новом запуске WebView2.

## Не переводится в v1

- Язык контента ASR / YouTube (`language: ru` в запросах).
- Произвольные `detail` ошибок с бэкенда (частично — `translateKnownApiError` в `api.js`).
- Имя продукта **Slysh**.
