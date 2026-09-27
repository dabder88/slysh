# Settings modal — Modern Pro Bento

Визуальный редизайн `#settings-modal`: карточка **640px**, пять вкладок, bento-плитки (светлая палитра slate/blue). Микро-типографика в scope bento увеличена на **+2px** относительно первой итерации макета.

## Вкладки

| Tab | `data-settings-tab` | DOM |
|-----|---------------------|-----|
| ASR | `asr` | `#settings-pane-asr` — локаль/провайдер, сегменты радио, picker каталога, gradient progress, `#compute-settings-wrap`, горячие клавиши tab-jump |
| Сеть | `proxy` | `#settings-pane-proxy` — `#proxy-settings` (плоская секция, без `<details>`) |
| Облако | `cloud` | `#settings-pane-cloud` — `#providers-settings` (карточки пресетов, спойлеры OpenRouter / Gemini / custom HTTP) |
| YouTube | `youtube` | `#settings-pane-youtube` — Apify |
| Система | `system` | `#settings-pane-system` — reload UI, logs |

Навигация: `initSettingsBentoTabs()` / `setSettingsBentoTab()` в [`web/js/shell.js`](../../../web/js/shell.js). Последняя вкладка — `sessionStorage` ключ `settings-bento-tab`.

Deep-link: `openSettingsModal("openrouter")` (и id из `SETTINGS_SPOILER_TAB`) переключает вкладку, открывает спойлер при необходимости и прокручивает к секции.

UI parity (относительно HTML-prototype):

- Заголовок модалки, tab-bar, tile grid
- Локальный picker: чип выбранной модели, список из каталога (`syncLocalModelPickerUi`)
- Прогресс скачивания: обёртка `#settings-model-download-progress-wrap`, заливка через `applyModelDownloadProgress`
- Прокси: chip статуса, поля без collapsible wrapper
- Облако: карточки пресетов + collapsible блоки провайдеров

## Invariant id (не менять без правки JS)

`#local-model-picker*`, `#btn-download-model`, `#settings-model-download-progress-wrap`, `#asr-source-field`, `#compute-settings-wrap`, `#proxy-*`, `#openrouter-*`, `#spoiler-*`, `#apify-*`, `#settings-close`, `#btn-reload-ui`, `#providers-settings`, `#proxy-settings`, …

Имена полей формы и API `/api/settings` не менялись — только разметка и CSS.

## Локализация

Ключи вкладок и подписей: `web/locales/ru.json`, `en.json` (префиксы `settings.tab.*`, связанные hint-строки).

## Сборка

После правок `web/styles/input.css`: `npm run build:css`, бамп `app.css?v=` и при необходимости `shell.js?v=` в `web/index.html`.

## Референс-макет

Исходный HTML-prototype: `modern_pro_bento_showcase.html` (Antigravity brain). В репозитории дублировать необязательно; каноническое описание поведения — этот файл и [wiki/settings-ui.md](../../../wiki/settings-ui.md).

## История (prod-launch)

- Bento-каркас и 5 panes — коммиты на ветке `prod-launch` (сентябрь 2026).
- Visual parity: header, picker, progress.
- ASR / cloud / proxy parity: flat proxy, cloud cards, shortcuts.
- 640px + типографика; legacy `#compute-hint` удалён; отступы `#files-chrome` / `#batches-chrome`.

Хронология для вики: [wiki/log.md](../../../wiki/log.md).
