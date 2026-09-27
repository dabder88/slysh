# Первый запуск пакетов расшифровки

Цель: чужой клон с GitHub открывает окно без 3 ГБ torch; на машине разработки с готовым `.venv` ничего не ломается.

## Поток

```
bat
  ├─ есть .venv\Scripts\python.exe → сразу Slysh (без uv sync)
  └─ нет venv
        ├─ нет uv → сообщение + pause + выход
        └─ есть uv → uv sync (без extras) → окно
              GET /api/setup
                ├─ engine_packages true → обычная работа (модали нет)
                ├─ engine_mode cloud_only → модали нет (см. [CLOUD-ONLY.md](CLOUD-ONLY.md))
                ├─ флаг «Позже» (`setup-engine-later`) и **нет** `prompt-engine-setup` → модали нет
                └─ иначе при отсутствии torch и не `cloud_only` → модаль «Как расшифровывать» (как в первой версии wizard; API `show_engine_setup_modal`)
                      Сохранённый ключ и Gemini CLI в PATH окно не закрывают и cloud_only не включают.
                      ├─ «Локально на этом компьютере» → модаль подтверждения `#engine-packages-confirm-modal` (объём ~3–5 ГБ, не веса модели, VPN, «позже в Настройках») → «Начать загрузку» → `uv sync --extra engine …` (без окна cmd, прогресс в `#engine-setup-modal`) → модаль выбора модели
                      ├─ «Через облако» → POST /api/setup/cloud-only; без API-ключа открываются Настройки
                      └─ «Напомнить позже» → setup-engine-later
```

Веса моделей **не** входят в `uv sync`. После локальных пакетов first-run предлагает скачать модель (по умолчанию GigaAM) или «Позже» (`POST /api/setup/model-later`). В **Настройках** те же действия доступны всегда.

Облако: Настройки → ключ OpenRouter, пресет Groq/OpenAI/Gladia/Deepgram, кастомный HTTP (тип API OpenAI/Gladia/Deepgram), либо Gemini CLI в PATH. Claude/Codex/ChatGPT CLI не подключаются — они не принимают аудиофайл в headless. Как подключать и чем Gladia solaria-1 отличается от solaria-3: [REMOTE-ASR.md](REMOTE-ASR.md).

## Почему нельзя uv sync «на всякий случай»

`uv sync` без extras на полном окружении **удаляет** torch, пакет GigaAM и NeMo. Поэтому:

- bat при существующем python extras не ставит;
- UI ставит пакеты только после кнопки и **всегда** с обоими extras.

## Bat

Файл: `Slysh.bat` — для **разработки из git** (консоль, `pause` при ошибках). У **установленной** копии пользователь запускает `Slysh.exe` из меню Пуск (без окна терминала).

- Сброс `NO_PROXY` / `no_proxy`.
- `SLYSH_INSTALL_ROOT` — папка программы, от неё берутся `web/`, иконка и `bin\ffmpeg.exe`.
- `GIGAAM_MODEL_ROOT`, **`GIGAAM_PROJECT_MODELS`** (каталог весов в UI) и `HF_HOME` — `%ROOT%\models`. **`Slysh.exe`** выставляет эти переменные заново, чтобы профильные dev-значения (например другой клон) не подменяли путь после установки.
- **`UV_PYTHON_INSTALL_DIR=%ROOT%\runtime\python`** — bundled Python для установщика; не `%AppData%\Roaming\uv`.
- Отдельный каталог данных не задаётся: база и настройки идут в `%LOCALAPPDATA%\Slysh`.

## Проба и API

`src/slysh/runtime_setup.py`:

- `engine_packages_ok()` — subprocess того же интерпретатора, `import torch, gigaam`
- `start_engine_install(mark_pending_model=…)` — фон, лог `%LOCALAPPDATA%\Slysh\logs\engine-setup.log`; при `installing` — `install_progress` (пакеты/объём по логу uv, `stalled` если лог не менялся ~90 с). **`uv sync` из UI** — [`subprocess_no_console_kwargs()`](../../src/slysh/subprocess_win.py) на Windows.
- «Позже»: файл `setup-engine-later` в app dir (не в git). Файл **`prompt-engine-setup`** — цикл после Setup; пока он есть, модаль показывается даже если старый «Позже» ещё не снят (снимается при `apply_fresh_install_marker` или кнопке «Позже»).
- Шаг модели: `setup-pending-model-download` в app dir; сброс через `POST /api/setup/model-later` или старт `POST /api/model/download`. В `#model-setup-modal` и в Настройках при скачивании — determinate-прогресс и текст **~X из ~Y** (оценка объёма отдельно для GigaAM и каждого `whisper:<size>`); опрос `/api/status` раз в **1 с**; при `stalled` — подсказка про VPN (как у engine). Для **GigaAM** в модалке показывается напоминание отключить VPN на время загрузки.

`GET /api/setup` **не** запускает uv. Тесты: `tests/test_runtime_setup.py`.

## UI

`web/js/shell.js` — `initEngineSetup()`, `openEngineSetupModalIfNeeded()` (после boot-splash в `main.js`). Модаль `#engine-setup-modal` по `show_engine_setup_modal` из API. **Локально:** сначала `#engine-packages-confirm-modal`, затем экран установки (`engine-setup-step-install`) с прогрессом «N/M пакетов · ~X/Y ГБ» из `install_progress`; при `stalled` — подсказка про VPN. `uv sync` из UI без окна cmd ([`subprocess_win.py`](../../src/slysh/subprocess_win.py)). После успеха — `#model-setup-modal`. Настройки: та же confirm-модал по «Скачать пакеты расшифровки».

При сбое старта из **`Slysh.exe`** — MessageBox при раннем выходе `pythonw` (≈3 с), логи в `%LOCALAPPDATA%\Slysh\logs`, `{install}\launch-last-error.txt`. Splash лаунчера — карточка **Windows 11 Fluent** (скругление DWM, бейдж «ДЕСКТОП», эквалайзер, marquee-прогресс): фразы **«Подготовка окружения…»** на `uv sync` и **«Запуск Slysh…»** до старта `pythonw`; окно закрывается после отпуска процесса. В WebView — boot-карточка в том же стиле до `/api/setup`; модаль — после boot (`scheduleEngineSetupModal`). API: `show_engine_setup_modal`, `engine_setup_blockers`. «Позже» без prompt — модали нет (удалить `setup-engine-later` или переустановить Setup).

## Установщик

Сборка комплекта: `powershell -File scripts\build-installer-payload.ps1`, затем `scripts\smoke_installer_layout.py`, затем `ISCC.exe installer\Slysh.iss` → `dist\Slysh-Setup.exe`.

`installer\Slysh.iss` собирает неподписанный `dist\Slysh-Setup.exe`. В меню Пуск — папка **Slysh** (между **Skype** и **Steam** в «Все приложения»): ярлык **Slysh** и удаление. Путь: `%AppData%\Microsoft\Windows\Start Menu\Programs\Slysh\`. Setup снимает старый одиночный `Programs\Slysh.lnk` и обновляет кэш меню. На последнем шаге мастера — «Запустить Slysh» и задача «Создать значок на рабочем столе» (стандарт Inno `[Run]` / `[Tasks]`). Исходный комплект — `dist\payload`: `Slysh.exe`, лёгкое окружение без torch, **`runtime\python`** (интерпретатор 3.12 для uv, не `%AppData%\Roaming\uv`), `bin\ffmpeg.exe`, `bin\uv.exe` (для установки пакетов расшифровки без системного uv), пустой `models`. **`Slysh.exe`** выставляет `UV_PYTHON_INSTALL_DIR={app}\runtime\python` и при битом `.venv` (другой путь установки, удалённый uv-python) сам вызывает `uv sync` до старта окна. База, ключи и веса в установщик не входят. Ставится в профиль пользователя; удаление — ярлык в той же папке меню Пуск, «Приложения» Windows или `unins000.exe` в `{app}`.

**Удаление:** снимается весь `{app}`, включая `.venv` после `uv sync` (torch и т.д.). Папка **`models/`** по умолчанию **тоже удаляется**; в начале деинсталляции вопрос «оставить models» — **«Нет»** оставляет только скачанные веса. **`%LOCALAPPDATA%\Slysh`** (база, настройки, логи) деинсталлятор **не** трогает. Перед удалением закройте Slysh — иначе DLL в `.venv` могут остаться.

Приёмка exe — на чистом профиле Windows без uv/torch: выбор языка RU/EN в Setup → «Локально» → прогресс пакетов → модаль модели → «Скачать» GigaAM. Подробнее: [wiki/installer.md](../../wiki/installer.md).

## QA: полное скачивание пакетов (не из кэша uv)

Повторная установка **без** удаления кэша uv часто занимает **~20 с** — пакеты берутся с диска (`%LOCALAPPDATA%\uv`), не из интернета.

**Полный путь «как первый раз»:**

1. Закрыть Slysh.
2. Скрипт: `powershell -ExecutionPolicy Bypass -File scripts\reset-engine-first-run-qa.ps1`  
   Удаляет `{InstallRoot}\.venv`, флаги в `%LOCALAPPDATA%\Slysh\`, лог `engine-setup.log`, **весь** `%LOCALAPPDATA%\uv\`.
3. По желанию перед «Начать загрузку» в системе или в ярлыке: **`SLYSH_ENGINE_INSTALL_NO_CACHE=1`** — тогда UI вызывает `uv sync --no-cache` (см. `uv_sync_engine_argv()` в `runtime_setup.py`).
4. Запустить Slysh → «Локально» → confirm → ждать **10–30 мин** (torch ~3+ ГБ с PyPI).

Веса **модели** (GigaAM) — отдельно; для их повторного скачивания очистите `{install}\models\gigaam\` (не только кэш uv).

## Связанные документы

- [WORKFLOW.md](../core/WORKFLOW.md)
- [ARCHITECTURE.md](../core/ARCHITECTURE.md)
- [ENDPOINTS.md](../api/ENDPOINTS.md)
- [README.md](../../README.md)
- [AGENTS.md](../../AGENTS.md)
