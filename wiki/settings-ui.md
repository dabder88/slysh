# Настройки (модал)

Окно «Настройки» открывается из сайдбара, hash-роута нет. Контейнер: `#settings-modal`, класс карточки `settings-bento`.

## Вкладки

Пять вкладок (Modern Pro Bento, ширина модалки **640px**):

| Вкладка | Ключ | Содержимое |
|---------|------|------------|
| ASR | `asr` | Локальная модель или облачный провайдер, picker каталога, прогресс скачивания, режим CPU/GPU |
| Сеть | `proxy` | Прокси HTTP(S), без вложенного `<details>` — секция плоская |
| Облако | `cloud` | Пресеты Groq/OpenAI/Gladia/Deepgram, OpenRouter, Gemini CLI, кастомный HTTP; спойлеры провайдеров |
| YouTube | `youtube` | Apify и связанные поля |
| Система | `system` | Перезагрузка UI, логи |

Последняя открытая вкладка запоминается в `sessionStorage` (`settings-bento-tab`). Вызов `openSettingsModal("openrouter")` (и другие id из `SETTINGS_SPOILER_TAB`) переключает вкладку и прокручивает к нужному блоку.

Логика: `web/js/shell.js` (`initSettingsBentoTabs`, `openSettingsModal`). Стили: `.settings-modal-card.settings-bento` в `web/styles/input.css`.

## Документация для разработки

Подробный mapping id и parity с макетом: [docs/design/settings_modal_bento/README.md](../docs/design/settings_modal_bento/README.md). Архитектура роутов: [docs/core/ARCHITECTURE.md](../docs/core/ARCHITECTURE.md).

## Связанные правки экрана «Файлы и пакеты»

На legacy-экране убран дублирующий `#compute-hint` (подсказка GPU уже в настройках ASR). Отступы фильтров: `#files-chrome`, `#batches-chrome`.

См. [[log]], [[product]].
