# Журнал

Сюда дописывать дату и что изменилось в продовой копии. Старые строки не переписывать.

## 2026-10-05

- API/UI: столбец «Длительность» — `duration_s` = длина записи (`media_duration_s` в SQLite, сегменты, range, probe); `processing_s` = время расшифровки; статус «Готово» без дубля времени в `library-store.js`.

## 2026-10-04

- R10: memmap для большого PCM (`SLYSH_DECODE_MEMMAP_BYTES`); отмена decode в engine file-job + диапазон через ffmpeg; очередь передаёт `cancelled` в `decode_pcm_16k_mono`.
- H1/H2/§5: engine watchdog, secrets lock, updates redirect validate, ASR snapshot на job (`job_asr_snapshot.py`).
- H4 / R09 (часть): `Slysh.exe` и `Slysh.bat` восстанавливают UI venv через `uv sync --no-editable --find-links wheelhouse --offline` при наличии wheelhouse; модуль `offline_bootstrap.py`, тесты `test_offline_bootstrap.py`; пересобран `installer/prebuilt/Slysh.exe`.
- Волна G plan-fix-2: диаризация не откатывает сохранённый текст (revision merge); save guard по job/draft generation; хвост &lt;1 с в chunking; speakers в ASR coordinator; mutex per data dir; auth без обхода `/api/*.json`; `.bak` синхронизируется после DPAPI; пакет — ошибка export/speakers не считается успехом; smoke cloud batch stub. Трекеры: `implementation-order-fix2.md`, `implementation-status-fix2.md`.

## 2026-10-03

- Редактор job: «Просмотр» с несохранённой «Правкой» показывает превью сегментов (`parseTranscript` в `web/js/transcript-format.js`, паритет с `transcript.py`); после «Сохранить» — GET job и обновление карточек.
- Topbar: индикатор «Локально/Облако · модель» (`#topbar-asr-strip`, `web/js/asr-context-bar.js`) на всех экранах кроме YouTube; клик открывает настройки ASR.
- Деинсталляция: в `{app}` удаляются все слоты `.venv-engine-*` и `venv-check.log` (`RemoveEngineVenvSlots` в `Slysh.iss`); `%LOCALAPPDATA%\Slysh` по-прежнему не трогается.
- Онбординг first-run: четыре модалки в стиле Modern Pro Bento (`docs/design/onboarding_modals_bento/`) — выбор локально/облако (радио + «Продолжить»), подтверждение пакетов, прогресс uv с терминальным логом, выбор первой модели; логика в `shell.js` без смены API `/api/setup/*`.
- Подтверждение выхода по крестику: in-app модалка, чекбокс «Больше не спрашивать» (`ui.skip_exit_confirm` в settings.json); `window.events.closing` + `JsApi.finish_app_exit`; показ модалки через отложенный `evaluate_js` (без deadlock WinForms); `_user_approved_exit` — повторный `closing` после «Выйти» не открывает модалку снова.
- UX intake файлов: после загрузки модалка «Расшифровать сейчас / Позже» (`intake-followup-modal`); для нескольких файлов вне пакета — сначала выбор отдельные/пакет (`upload-target-modal`), вкладка «Файлы» в legacy тоже через `resolveUploadTarget`. Автозапуск расшифровки нет.

## 2026-10-02

- E.6: `docs/features/E6-OFFLINE-VM.md` (матрица Win10/11 offline); `e6-offline-vm-verify.ps1` — pyvenv, runtime python, notices, `-ProbeOfflineUiSync`, `-ResultJson`.
- F.4: расширен `THIRD_PARTY_NOTICES.md` (лицензии по слоям, redist, облако).
- E.7: `prune_stale_engine_venv_slots` после успешного engine install; F.5 `audit_git_secrets` в `ci_mandatory_checks` и GitHub workflow; smoke slots расширен.
- C.3: отмена job в `QUEUED` вызывает `_pump_asr_queues`; smoke `smoke_coordinator_queued_cancel.py`; pytest `test_pump_local_skips_when_slot_busy`.
- D.1–D.2: UI auth в bat/launcher (`GIGAAM_UI_AUTH`, loopback strict); bootstrap только через pywebview bridge (`GIGAAM_UI_BOOTSTRAP_HTML=0`); cookie с уникальным именем; `smoke_ui_auth_session.py`; пересборка `installer/prebuilt/Slysh.exe`.
- D.5: ключи провайдеров и пароль прокси в `secrets.dpapi`, миграция при старте UI; proxy GET без plaintext; `smoke_secrets_dpapi_migration.py`.
- A10: Gemini CLI — temp cwd, копия аудио, без yolo, отмена/тайм-аут; `test_gemini_cli.py`.
- B4.2–B4.3: `capture_control_lock` на live/meeting resume и в `_live_worker`; drain ASR при meeting pause; pytest pause cycles + `smoke_capture_pause_resume.py`.
- D.3–D.4: строгий `Origin`/`Referer` на mutating `/api` при `GIGAAM_LOOPBACK_STRICT`; отказ `..` и относительных путей на `GET .../media` и `POST /api/open-path`; smokes `smoke_loopback_host_origin.py`, `smoke_job_media_traversal.py`; `docs/api/ENDPOINTS.md`.
- A6/B1: coerce спикеров на PATCH, sync revision в редакторе, smoke `smoke_segments_revision_409.py` (commit `90b0899`).
- A8: статус job `finalizing` во время фоновой ASR после live/meeting stop; smoke `smoke_capture_job_finalizing_status.py`; UI/locales; SCHEMA.
- C: ASR-слот coordinator на всё время live/meeting (не только finalize); освобождение при пустом finalize без PCM; pytest `test_live_start_acquires_local_coordinator_slot` + 5 coordinator; полный pytest 450; smokes finalize cancel/start-blocked; аудио 3/3 (`GIGAAM_FORCE_CPU=1`); `Slysh.bat` OK; Setup пересобран. YouTube smoke не гоняли (код YouTube не менялся).
- Smoke finalize (wave C / 3.1): `smoke_capture_finalize_cancel.py`, `smoke_capture_finalize_start_blocked.py` + pytest `test_capture_finalize_coordinator` (4), `test_live_stop_async_finalize`, `test_audio_ingest`, `test_live_buffer` — 25 passed; полный pytest 449; аудио 3/3, YouTube live Apify, `Slysh.bat` OK.

## 2026-10-01

- Локальные pytest (в gitignore): `test_capture_finalize_coordinator` — слот coordinator, блок start, `engine_cancel` при cancel, remote-слот; `test_live_stop_async_finalize` — быстрый stop и флаг `capture_finalizing`.
- C: блок `live/meeting/start` на время finalize; отмена job прерывает finalize в engine; remote-слот при облачной ASR.
- C: фоновая ASR после live/meeting stop держит слот `AsrCoordinator` (локальный engine); `run_id` и busy до конца finalize.
- 3.1: `meeting.js` — ожидание транскрипта и polling при `capture_finalizing` (как диктофон).
- 3.1: флаг `capture_finalizing` в job/status; диктофон ждёт текст при фоновой ASR; «Перерасшифровать» для failed (не YouTube).
- 3.1: `POST /api/live/stop` и `/api/meeting/stop` не ждут ASR до 600 с — аудио в worker, расшифровка в `capture_finalize_threads`.
- B4: при переполнении `AudioIngestQueue` — `on_overflow`, остановка live/meeting worker, ошибка в job; тесты `tests/test_audio_ingest.py`.
- Smoke YouTube live: ключ Apify и cookies из `%LOCALAPPDATA%\\Slysh` (`secrets.dpapi`), метод apify при `api_key_set`; temp БД для job (commit `6c0c4c9`).
- C: `run_youtube_job` учитывает `run_id` (`job_run_active`) — устаревший поток после повторного start не пишет сегменты.
- B5: контракт `POST /api/open-path` — только существующий путь (`resolve_existing`, 404); JsApi `open_path` по-прежнему через `resolve_open_target` (rename в папке). Smoke `scripts/smoke_open_path_api.py`.
- YouTube ingest: после «Получить транскрипт» редактор не показывает чужую готовую расшифровку (commit `7740f53`) — синхронный `applyRoute` при `#/editor/{id}`, сброс shell редактора, `selectedId`/`pollJobs` по hash, `attach_youtube_video(..., db=app.state.db)`.
- B2: метаданные YouTube job (`method`, `language`, `video_json`) в SQLite `job_youtube_meta`; миграция `youtube/job-meta.json` → `app.db`; smoke `scripts/smoke_youtube_ingest.py` (commit `0214502`).
- B2: атомарная запись `settings.json` / `compute.json` (`settings_store.py`, `.bak`); smoke `scripts/smoke_settings_atomic.py` (commit `ca31a95`).
- B3: корректное завершение UI (lifespan FastAPI, `shutdown_ui_runtime`, join engine); smoke `scripts/smoke_ui_lifespan_shutdown.py` (commit `56455c0`).
- B1: черновик редактора per job, dirty/stash при смене view, `beforeunload` (commit `7e68428`).
- Splash «Запуск Slysh…»: убран двойной export `uniqueSpeakers` в `web/js/legacy.js` (commit `1a4ef15`); smoke `scripts/smoke_web_legacy_exports.py` в `smoke_installer_layout` для payload.
- Модал «Модель для распознавания»: прогресс как в Настройках (%, bento-track), без дубля строки статуса при скачивании.
- Настройки «Движок обработки»: убрано упоминание Buzz в пояснении GPU; подсказки всегда нейтральным цветом (не `is-warn`).
- A11: диаризация спикеров через engine `POST /label_speakers` (`speakers_engine.py`); UI/batch без импорта `speakers_msdd`.
- Bootstrap UI: `initRouter` и экраны подключаются до долгого `/api/setup/engine`; при ошибке i18n/shell меню остаётся кликабельным; клик по фону first-run модалки — «Позже».
- `smoke_slysh_bat_startup.py`: переменная `SLYSH_SMOKE_ROOT` для проверки установки вне репозитория (например `F:\ProjectsAI\Slysh-test`).
- Прогресс «Определение спикеров»: убран ложный затык на 95% (оценка дольше для длинных записей, indeterminate и подсказка «дольше обычного»); логи `label_speakers` в engine; HTTP timeout диаризации `SLYSH_SPEAKER_HTTP_TIMEOUT` (по умолчанию 2 ч).
- «Имена спикеров»: подписи как в расшифровке («Спикер N» по `SPEAKER_XX`); в списке переименования нет ключей с суммарной речью &lt; 5 с.

## 2026-09-30

- Волна E (first-run / Setup): `UV_PROJECT_ENVIRONMENT` при engine `uv sync` → `.venv-engine`; проверка после sync; прогресс в модали при «зависшем» installing.
- Скачивание весов (GigaAM / Whisper): subprocess **engine** (`resolve_engine_subprocess_python`, `pythonw` без консоли).
- Старт установленной копии: `?skip_boot_splash=1` (нет дубля карточки лаунчера); mutex `Local\SlyshDesktopSingleInstance` + ранний lock в `main()`; Inno `InitializeSetup` без `{app}`.
- Payload: правка `.pth` / `pyvenv.cfg` после staging→payload; wheelhouse smoke после swap.
- Док: `docs/features/FIRST-RUN.md`, тесты в `tests/` (локально, в gitignore).

## 2026-09-29

Копия `Slysh-prod-GPT`: волны 0 и A (и часть B–F по инфраструктуре).

- Волна 0: `tests/conftest.py`, `scripts/run-pytest.ps1`, `.review/` в gitignore, 371 pytest (без сети).
- A: deadlock setup/updates, cancel engine chunk, cloud batch через `run_file_job`, `on_error=stop`, уникальный экспорт в пакете, ключи спикеров, маскировка секретов API, live/meeting failed при ошибке ASR, YAML MD, Gemini без yolo, убран CUDA warm-up из UI.
- B–C (база): dirty polling редактора, `run_id` в jobs, single-instance lock, shutdown uvicorn/engine в `main()`.
- D: `local_auth.py` (вкл. `GIGAAM_UI_AUTH=1`), F: `.github/workflows/pytest.yml`.
- E (offline Setup / wheelhouse): не выполнялась полная матрица чистой Windows — отдельная волна.
- Preflight ASR перед стартом job/live/meeting: понятная ошибка, если модель не скачана или нет пакетов; при падении engine — разбор stdout вместо голого «engine did not report PORT».
- Старт UI: ленивый импорт PortAudio (`sounddevice_lazy`), faulthandler в `%LOCALAPPDATA%\\Slysh\\logs\\faulthandler.log` — меньше нативных крашей при `Slysh.bat` до открытия окна.
- GigaAM на GPU: при cuBLAS/CUDA на чанке — автопереключение движка на CPU в том же процессе; подсказка в тексте ошибки job.
- Волна B: `segments_revision` + 409 при конфликте сохранения; черновики per job в редакторе; очередь аудио из callback (live/meeting); `taskkill /T` для engine при выходе.
- Волна C: `asr_coordinator.py` — один слот локального engine и один облачный worker; pump очереди `QUEUED` после завершения; guards `run_id` в progress/segments для engine и remote; повторный `POST …/start` при RUNNING/QUEUED → 200; `engine_cancel` только для job, занимающего локальный слот; тесты `test_asr_coordinator.py`.
- Поля API-ключей: маска 4+…+4 и полный ключ по глазику; `api_key_masked` + reveal `api_key` при UI-сессии; `secret-field.js` + правки shell/youtube.
- Fix: при `GIGAAM_UI_AUTH=1` публичны `/locales/*`, GET `/api/locale`, `*.json` статика; i18n fetch с credentials — убран баннер «locale ru» при старте.
- Волна D: loopback Host/Origin (`GIGAAM_LOOPBACK_STRICT`), UI-сессия (`GIGAAM_UI_AUTH`, bootstrap через `JsApi.ui_bootstrap_token`, `POST /api/ui/session`, cookie HttpOnly); токен engine (`GIGAAM_ENGINE_TOKEN`); DPAPI-хранилище ключей провайдеров; hardening `/api/jobs/{id}/media`; OpenAPI off (`SLYSH_DISABLE_OPENAPI`); `Slysh.bat` включает флаги; тесты `test_loopback_security.py`.
- Волна E (часть): обязательный `sha256:` в релизе для download/apply; staging `dist/payload.staging` → swap с `payload.prev`; UTF-8 без BOM в `version.json`; Inno Setup не пишет `.fresh-install` при апгрейде; UI `updates.missingSha256`.
- Волна E (продолжение): `wheelhouse/` в payload + offline `uv sync` в `Slysh.bat`; WebView2 bootstrapper в Setup (`fetch-installer-redist.ps1`); preflight ffmpeg/launcher до staging; smoke relocated payload + `smoke_slysh_bat_startup.py`.
- Волна E §7.2: `runtime_env.py` — `.venv` (UI) и `.venv-engine` (torch/GigaAM) в установленной копии; `resolve_engine_python()` для spawn engine; manifest `runtime-env.json`.
- Волна F: CI — env как в conftest, `check-web-js.ps1`; `installer/licenses/THIRD-PARTY-NOTICES.md`.

## 2026-09-23

Продовая копия доведена до неподписанного установщика Windows.

- Пакет переименован: код в `src/slysh`, команда `slysh`, лаунчер `Slysh.bat`.
- Каталог данных по умолчанию — `%LOCALAPPDATA%\Slysh`. Отдельный `GIGAAM_DESKTOP_HOME` лаунчер не задаёт.
- `Slysh.bat` задаёт `SLYSH_INSTALL_ROOT` на папку программы, модели и кэш Hugging Face — на `models` рядом с программой.
- Установщик Inno Setup: `installer/Slysh.iss`. Комплект сборки — `dist/payload`. Готовый файл — `dist/Slysh-Setup.exe`. Папка `dist` в git не входит.
- В установщике лёгкий Python без torch, свой `bin/ffmpeg.exe`, пустой `models`. База, ключи и веса этой машины в exe не входят.
- Установка в профиль пользователя, без прав администратора: `%LOCALAPPDATA%\Programs\Slysh`. Ярлык Slysh в меню Пуск. Удаление через «Приложения». Папку `models` деинсталлятор не стирает.
- Подписи exe нет. Кнопки «Обновить» нет. На GitHub Releases файл не выкладывался.

До этого в той же копии уже были: свой ffmpeg, окно первого запуска, локальные веса GigaAM, YouTube и диаризация внутри пакета. Подробности поведения — в [[first-run]], [[installer]], [[data-and-models]].

## 2026-09-26

Редизайн модала «Настройки» (Modern Pro Bento, ветка `prod-launch`).

- Пять вкладок: ASR, Сеть, Облако, YouTube, Система; класс `settings-bento` на `#settings-modal`.
- Перенос существующих секций без смены id полей и привязок `shell.js`.
- Visual parity: шапка, picker локальной модели, прогресс скачивания.
- Parity ASR / облако / прокси: плоская секция прокси, карточки облачных пресетов, deep-link на вкладку и спойлер провайдера.
- Документация: строка в `docs/core/ARCHITECTURE.md`, черновик `docs/design/settings_modal_bento/README.md`.

## 2026-09-27

Доработки UI и документации.

- Ширина модала настроек **640px**; микро-типографика в scope bento **+2px**.
- Legacy «Файлы и пакеты»: удалён дублирующий `#compute-hint`; отступы у `#files-chrome` и `#batches-chrome` под фильтры.
- Вики: [[settings-ui]], обновлён design README, правило «все значимые правки — в md» в [[rules]] и AGENTS.md.
- Legacy: flex `gap` подсказки и «Фильтров», `app.css?v=113`.
- Архив: убрана кнопка topbar «Загрузить» (была ярлыком на панель); загрузка — сайдбар / dashboard.

## 2026-09-28

- FFmpeg на Windows: `subprocess_no_console_kwargs` в decode и spawn engine, `-nostdin`; тест `test_decode_ffmpeg_subprocess_hides_console`.
- Прогресс расшифровки: сброс transform после indeterminate, полоска синхронна с `%`; фаза спикеров — indeterminate + секунды, не 100% от ASR.
- Toast: цепочка ключей i18n в `resolveToastMessage`; «Распознаю спикеров…» вместо `meeting.*`.
- Экспорт: модал не закрывается по клику на фон; крестик `#export-close`.

First-run / intake / toast (dev `Slysh.bat`):

- Resync пакетов только после маркера in-app update (`app-update-applied`), не из‑за расхождения `uv.lock` в клоне; при рабочих пакетах fingerprint сохраняется без модалки confirm.
- `prompt-engine-setup` снимается, если probe torch/GigaAM уже OK — choose-модалка не всплывает зря.
- Drop на панели в pywebview: без toast «нет пути», если native drop в `app.py` уже передал файлы.
- Toast спикеров: ключ `meeting.k2351323`, `resolveToastMessage` понимает кириллицу в ключах.
- Прогресс спикеров в редакторе: баннер job-progress не пересоздаётся каждые 500 ms — indeterminate-анимация видна; отдельный sweep в CSS для `.job-progress`.
- Прогресс спикеров: псевдо-% по elapsed и длительности файла (determinate, как ASR); подпись баннера в %.
- Редактор: колонка «Источник» по умолчанию 400px (`editor-player-width-v2`), ширина всегда применяется при открытии.
- Остановка спикеров: `/cancel` сразу снимает `speakers_running`; результат диаризации не пишется в БД после отмены.

- Ручная проверка обновлений: меню «Проверить обновления», GitHub Releases, API `/api/app/info`, `/api/updates/*`.
- Сборка: `version.json` в payload, `AppVersion` в Inno из `pyproject.toml`.
- Документация: [docs/features/APP-UPDATES.md](../docs/features/APP-UPDATES.md), [[installer]].

## 2026-09-27 (gitignore)

- Расширен `.gitignore`: `.test-home/`, `refs/`, `design/`, `web/dist/`, кэш локалей, legacy `web/app.js` / `web/styles.css`, логи лаунчера в корне.
- Сняты с отслеживания макеты `refs/`, исходники `design/`, дубликат CSS и кэш; в git остаются `web/branding/` и `slysh.ico`.

## 2026-09-28 (git: только продукт)

- В `.gitignore`: `tests/`, `docs/`, `wiki/`, `scripts/`, `.cursor/`, `.claude/`, `AGENTS.md`, `AI_GUIDE.md`, `package.json` / lock / tailwind.
- Сняты с отслеживания; в git — `src/`, `web/`, зависимости, `installer/`, `launcher/`, короткий `README.md`.

## 2026-09-28 (git: сборка для клона)

- В git возвращены: `package.json`, tailwind, скрипты сборки payload/Setup/CSS, `copy-local-models`, `sync-branding`, `smoke_installer_layout.py`.
- В ignore остаются одноразовые maintainer-скрипты (benchmark, probe_yt, verify_*, smoke_test_startup и т.д.).

## 2026-09-28 (редактор: открыть экспорт)

- Кнопки «Открыть файл» / «Открыть в папке» в редакторе: путь берётся из футера (`dataset.exportPath`) и синхронизируется с кэшем library после `GET /api/jobs` и экспорта в несколько папок; fallback `POST /api/open-path` при сбое pywebview; `upsertJobInStore` в `library-store.js`.
- Backend: ошибки `JsApi.open_path`, `explorer` без консоли в `open_paths.py`; тесты `tests/test_open_paths.py`.

## 2026-09-28 (экспорт: переименование и все папки)

- `open_paths.resolve_open_target`: при переименовании — один `.srt` в папке или открытие родительской папки; «Открыть» по всем путям из `last_export_paths` (SQLite JSON + `PUT /api/jobs/{id}/last-export-paths`).
- UI: `resolveExportOpenPaths`, цикл в `openSavedExport`; batch auto-export пишет все пути.

## 2026-09-28 (reveal: Explorer виден)

- «Открыть в папке»: запуск `explorer.exe` без `subprocess_no_console_kwargs` (скрытие окна ломало reveal); тест `test_reveal_in_folder_launches_explorer_without_no_console`.

## 2026-09-28 (YouTube: прогресс в редакторе)

- Одиночный ingest: после «Получить транскрипт» сразу `#/editor/{id}`, опрос job и баннер прогресса; `shouldPollEditorJob` для `kind=youtube`.

## 2026-09-29 (dashboard: пакет файлов при выбранном YouTube-пакете)

- Панель «Пакетная обработка»: `fileBatchTargetId()` — при выбранном YouTube-пакете локальные файлы/папки идут в новый file-пакет, а не в YouTube.
- Ранний guard в `addFilesToSelectedBatch` / `confirmFolderAdd` для drop на legacy «Пакеты».

## 2026-09-29 (i18n: системные надписи meeting/legacy/editor)

- В `ru.json` у 41 ключа `k*` значения-ссылки (`meeting.запись`, …) заменены на финальный русский текст.
- `t()` и `resolveMessageChain` в `i18n.js`; тест `test_no_indirection_values_in_locales`.

## 2026-09-29 (live/meeting: чанки ASR 20 с)

- Дефолт `GIGAAM_LIVE_CHUNK_SECONDS` / `LIVE_CHUNK_SECONDS` — **20** (как `CHUNK_SECONDS` для файлов); диктофон и запись встречи.

## 2026-09-29 (сайдбар: загрузка, о программе, версия)

- CTA «Загрузить файл»; пункт «О программе» (`about_url` в settings или `SLYSH_ABOUT_URL`); «Сказать спасибо» (`support_url` / `SLYSH_SUPPORT_URL`); версия `v*` внизу сайдбара из `/api/app/info`.
