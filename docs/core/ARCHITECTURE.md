# Архитектура Slysh

Десктопное приложение: окно WebView2 (pywebview) ходит на локальный FastAPI. Распознавание речи вынесено в отдельный Python-процесс с PyTorch.

## Процессы

```
Установленная копия: Slysh.exe (без консоли) → pythonw -m slysh.app. Перед стартом exe задаёт `SLYSH_INSTALL_ROOT`, `GIGAAM_MODEL_ROOT`, **`GIGAAM_PROJECT_MODELS`** и кэши Hugging Face в `{install}\models`, чтобы UI и engine не брали каталог моделей из пользовательского env разработки.
Разработка из git:    Slysh.bat → python -m slysh.app
  └─ UI-процесс (slysh.app)
        ├─ uvicorn 127.0.0.1:<случайный порт>
        │     FastAPI create_ui_app() + StaticFiles(web/)
        ├─ webview.create_window("Slysh", http://127.0.0.1:<port>/)
        └─ по первой локальной расшифровке:
              subprocess: python -m slysh.engine_server
                FastAPI: /health /progress /transcribe_file /transcribe_chunk /cancel
           облако/CLI: без engine, `remote_asr.transcribe_media` в UI-потоке
```

Точка входа UI: `slysh.app:main` (`pyproject.toml` script `slysh`).

Engine поднимается из `api._spawn_engine()`: `Popen` того же `sys.executable`, читает stdout до `PORT=<n>`, кладёт URL в `app.state.engine_url`. Автостарт можно отключить `GIGAAM_SKIP_ENGINE=1` или режимом `engine_mode: cloud_only` в `settings.json` ([CLOUD-ONLY.md](../features/CLOUD-ONLY.md)): тогда `create_ui_app` ставит `auto_start_engine=false`.

`JobQueue` (`queue.py`) покрыт тестами, в проде `app.state.queue = None`: одиночные jobs идут через `_start_asr_job` (локально — `_start_engine_job`, иначе HTTP/Gemini).

## Запрет PyTorch в UI

Модули `app.py`, `api.py`, `db.py`, `queue.py`, `runtime_setup.py`, `providers.py`, `remote_asr.py`, `gemini_cli.py`, `meeting_capture.py`, `wasapi_loopback.py`, `youtube_ingest.py`, `youtube_apify.py`, `youtube_ytdlp.py`, `youtube_cookies.py`, `vtt.py` не должны импортировать `torch`, `gigaam`, `slysh.rnnt_backend`. `api.py` не импортирует `speakers_msdd` статически.

Проба пакетов: subprocess `import torch, gigaam` (`runtime_setup.PROBE_IMPORTS`).

Torch-модули: `rnnt_backend.py`, `whisper_backend.py`, `engine_server.py`, `speakers_msdd.py`, `speakers_cluster.py`.

## Старт окна (`app.py`)

1. `setup_logging()`
2. Ключ Evergreen WebView2 Runtime в реестре. Если его нет, диалог с кнопкой «Скачать и установить» качает официальный bootstrapper Microsoft (`LinkId=2124703`), запускает его и выходит. Сервер и окно при этом не стартуют. После установки пользователь открывает Slysh снова.
3. `Database(db_path())`, `recover_stale_state()` (зависшие queued/running)
4. `create_ui_app(db, engine=None, auto_start_engine=True)`
5. Uvicorn в daemon-thread, порт 0
6. pywebview: минимум ширины 1100px (сайдбар 256px), высота по умолчанию 720
7. `JsApi`: нативные диалоги файлов/папки, открытие путей и логов

## Поток расшифровки файла

```
POST /api/jobs/{id}/start
  db.begin_transcription()          # queued
  thread _start_asr_job
    локально: _start_engine_job
      _spawn_engine() при необходимости
      decode_pcm_16k_mono (ffmpeg)
      slice_chunks (~20 с)
      loop: transcribe_chunk → db.append_segments
    облако/CLI: _run_remote_job
      prepare_stt_chunks (MP3, ~3 мин при потоке в редактор)
      loop: transcribe_http_file / CLI → db.append_segments
    completed | failed | cancelled
```

Редактор (`#/editor/{id}`): при `running` file-job опрашивает GET `/api/jobs/{id}` и дописывает сегменты. Подробно: [STREAMING-TRANSCRIPT.md](../features/STREAMING-TRANSCRIPT.md).

Чанки live/pipeline: `chunking.CHUNK_SECONDS = 20`, `SAMPLE_RATE = 16000`. Диктофон и запись встречи — последовательные окна ~20 с, не overlapping; задержка текста около 20 с. Захват микрофона открывается на native/48/44.1 kHz при необходимости и ресемплится в 16 kHz (`open_mic_input_stream` в `meeting_capture.py`). Запись встречи: WASAPI loopback через Core Audio (`wasapi_loopback.py`) + опционально микрофон, микс в моно (`meeting_capture.py`). Диктофон и встреча взаимно исключаются.

YouTube (`#/youtube`): готовые субтитры без engine — Apify или `yt-dlp` + cookies; один URL или **пакет** (`rules.batch_type=youtube`, `POST /api/youtube/batch`, разбор канала в `youtube_channel.py`). Подробно: [YOUTUBE.md](../features/YOUTUBE.md).

## Пакеты

`POST /api/batches/{id}/start` → `batch_runner.start_batch()`. Один активный пакет (`is_batch_active`). Правила (`batch_rules.DEFAULT_BATCH_RULES`): `batch_type` (`file`|`youtube`), для YouTube — `youtube_method`, `youtube_language`, `delay_seconds`; спикеры, автоэкспорт (в т.ч. `md`), папка, `skip_completed`, `on_error`. YouTube-пакет не поднимает engine.

Смена модели или CPU/GPU запрещена, пока пайплайн занят (`_pipeline_busy`).

## Спикеры

`POST /api/jobs/{id}/speakers` → `importlib` `speakers_msdd` → `assign_speakers`. Код диаризации лежит в `slysh.diarization` (Sortformer по умолчанию, MSDD по `GIGAAM_DIARIZER=msdd`). Нужен extra `diarization` (NeMo). Имена: `PUT /api/jobs/{id}/speakers`.

## Фронтенд

Vanilla ES modules, без webpack/vite. Роутер — hash в `web/js/router.js`.

| Route | View id | Nav | Назначение |
|-------|---------|-----|------------|
| `dashboard` | `view-dashboard` | `nav-dashboard` | Панель |
| `queue` | `view-queue` | `nav-queue` | Очередь |
| `transcripts` | `view-transcripts` | `nav-editor` | Список расшифровок; вкладки `#/transcripts/files` и `#/transcripts/batches` |
| `editor` | `view-editor` | `nav-editor` | Редактор `#/editor/{id}` |
| `archive` | `view-archive` | `nav-archive` | Архив; вкладки `#/archive/files` и `#/archive/batches` |
| `live` | `view-live` | `nav-live` | Диктофон |
| `meeting` | `view-meeting` | `nav-meeting` | Запись встречи |
| `youtube` | `view-youtube` | `nav-youtube` | YouTube-транскрипт |
| `legacy` | `view-legacy` | `nav-legacy` | Файлы и пакеты |

`#/package/{id}` редиректится в legacy. Настройки: модал `#settings-modal` (не hash-роут) — вкладки ASR / Сеть / Облако / YouTube / Система (bento UI, ширина 640px), радио «локальная модель / провайдер», спойлеры провайдеров; см. [`docs/design/settings_modal_bento/README.md`](../design/settings_modal_bento/README.md) и [wiki/settings-ui.md](../../wiki/settings-ui.md). Первый запуск пакетов: `#engine-setup-modal` (`shell.js` `initEngineSetup`).

Инициализация: `web/js/main.js` — `await initI18n()` ( `GET /api/locale?hint=…`, словари `web/locales/{ru,en}.json` ) → `initShell` → `initRouter` → экраны. Смена языка: `PUT /api/locale`, `applyI18n`, событие `onLocaleChange` → `notifyCurrentRoute()`. Подробно: [UI-LOCALE.md](../features/UI-LOCALE.md).

CSS: `web/styles/input.css` → `npm run build:css` → `web/app.css`. Кэш: `?v=` в `web/index.html` (CSS и importmap). Middleware UI: `Cache-Control: no-store` для html/js/css.

Таблицы библиотеки (`web/js/library-table.js`, `library-table-filters.js`): Расшифровки, Архив, Файлы и Пакеты — на экранах «Расшифровки» и «Архив» отдельные вкладки «Файлы» / «Пакеты» (как в legacy), у каждой вкладки своя таблица и `storageKey` (`transcripts-files`, `transcripts-batches`, `archive-files`, `archive-batches`). Фильтры по столбцам — client-side, под спойлером; значения в `localStorage` (`library-table-filters-{storageKey}`). Пагинация верхнего уровня: 10 / 30 / 50 / все (`library-table-page-size-{storageKey}`).

## Модели

Сканер: `catalog.py`, корень `paths.project_models_dir()` (`install_root()/models` или `GIGAAM_PROJECT_MODELS`).

`install_root()` — папка с `pyproject.toml` (поиск вверх от модуля) или `SLYSH_INSTALL_ROOT`, если это существующий каталог. От него берутся `web/`, `slysh.ico`, `models/` и `bin/ffmpeg.exe` (если файла нет, затем ищется `ffmpeg` в PATH).

Продовая копия запуска живёт отдельно от ежедневного клона и не пишет в его базу:

- ежедневный клон хранит данные в своём каталоге профиля и этой веткой не меняется
- продовая копия не задаёт отдельный каталог данных: база и логи идут в `%LOCALAPPDATA%\Slysh`

Ищет:

- `gigaam/*.ckpt` или `*.pt`
- Hugging Face `models--*--faster-whisper-*`
- плоские `faster-whisper-<size>/`
- `whisper/*.pt` и `*.pt` в корне `models/`

GigaAM id: `gigaam`. Whisper: `whisper:<size>`. OpenRouter: `openrouter:{slug}`. Встроенные HTTP: `http:groq`, `http:openai`, `http:gladia`, `http:deepgram`. Кастомный HTTP: `custom:{id}`. Gemini CLI: `cli:gemini` (только если `gemini` есть в PATH). Скачивание весов в `models/`: `POST /api/model/download` с `id` (`gigaam` — subprocess `rnnt_backend --download-only` → `models/gigaam/`; `whisper:<size>` — `whisper_download` + Hugging Face `Systran/faster-whisper-<size>` → `models/faster-whisper-<size>/`). В настройках список локальных моделей включает неустановленные размеры (`downloadable: true` в `GET /api/models`).

Облачный STT идёт в UI-процессе: ffmpeg → mp3 (куски ≤ 20 МБ) → протокол сервиса. Исходящие запросы к выбранным сервисам могут идти через HTTP-прокси из `settings.json` → `proxy` (`http_proxy`: STT, YouTube, Gemini CLI). API: `GET`/`PUT /api/proxy`. OpenAI-совместимые (OpenRouter, Groq, OpenAI, кастом с `protocol=openai`): `POST …/audio/transcriptions`, `Authorization: Bearer`. Gladia: `x-gladia-key`, `POST /v2/upload` + `POST /v2/pre-recorded` + опрос; для русского — **solaria-1** (`solaria-3` без языка Gladia отклоняет, Slysh модель не шлёт). Deepgram: `Authorization: Token`, `POST /v1/listen`. Либо `gemini -p "@file"`. Torch-engine не стартует. Диктофон и запись встречи: локальная модель или HTTP STT, не Gemini CLI. Claude / Codex / ChatGPT CLI не поддерживаются (нет file STT). Подробно: [REMOTE-ASR.md](../features/REMOTE-ASR.md), [MEETING-CAPTURE.md](../features/MEETING-CAPTURE.md).

Ключи: `settings.json` → `providers`, плюс env `OPENROUTER_API_KEY`, … GET `/api/providers` и `/api/proxy` возвращают сохранённые значения для локального UI.

`GIGAAM_MODEL_ROOT` bat выставляет в `models/` и прокидывает в env engine; **сканер `paths.py` эту переменную не читает** (и игнорирует `BUZZ_MODEL_ROOT`).

## Данные на диске

| Путь | Содержимое |
|------|------------|
| `%LOCALAPPDATA%\Slysh\app.db` | SQLite |
| `...\settings.json` | Модель ASR, compute, `ui_locale` (`ru`/`en`), ключи провайдеров |
| `...\logs\` | `app.log`, `engine-setup.log` |
| `...\recordings\` | WAV диктофона и записи встречи |
| `...\youtube\cookies.txt` | Cookies для yt-dlp |
| `...\youtube\job-meta.json` | method/language для re-ingest YouTube jobs |
| `...\setup-engine-later` | Флаг «Позже» для модали пакетов |
| `<repo>/models/` | Веса ASR (не в git) |

Override домашнего каталога: `GIGAAM_DESKTOP_HOME`.

## Переменные окружения

| Переменная | Назначение |
|------------|------------|
| `GIGAAM_DESKTOP_HOME` | Корень app data |
| `SLYSH_INSTALL_ROOT` | Корень установки (`web/`, `models/`, иконка), если задан |
| `GIGAAM_PROJECT_MODELS` | Корень весов (тесты) |
| `GIGAAM_MODEL_ROOT` | Env для engine / bat |
| `GIGAAM_FORCE_CPU` | Принудительно CPU |
| `GIGAAM_DEVICE` | `auto` / `gpu` / `cpu` |
| `GIGAAM_ASR_ID` | Выбранная модель |
| `GIGAAM_ASR_BACKEND` | `gigaam` / `whisper` / `remote` |
| `OPENROUTER_API_KEY` | Ключ OpenRouter (перекрывает settings.json) |
| `GROQ_API_KEY` | Ключ Groq |
| `OPENAI_API_KEY` | Ключ OpenAI |
| `GLADIA_API_KEY` | Ключ Gladia |
| `DEEPGRAM_API_KEY` | Ключ Deepgram |
| `GIGAAM_SKIP_ENGINE` | Не стартовать engine |
| `GIGAAM_ENGINE_FAKE` | Фейковый backend |
| `HF_HOME` | Кэш Hugging Face для весов спикеров; bat ставит `models\huggingface` |
| `APIFY_API_TOKEN` / `APIFY_TOKEN` | Ключ Apify для YouTube |
| `YTDLP_BINARY` / `YT_DLP_BINARY` | Путь к yt-dlp |
| `GIGAAM_DIARIZER` | `sortformer` (default) / `msdd` |
| `FFMPEG_BINARY` / `FFMPEG_PATH` | ffmpeg |
| `NO_PROXY` | Bat обнуляет (ломает huggingface_hub) |

## Экспорт

Форматы: `txt`, `srt`, `vtt`, `md` (единый Obsidian-шаблон для всех источников, `export.py`). Одиночный job: `POST /api/jobs/{id}/export`. Пакет: `POST /api/batches/{id}/export`. Несколько completed: `POST /api/export-jobs`. В UI-модалке экспорта можно указать **несколько целевых папок** (кнопка «Добавить папку»); фронтенд вызывает тот же endpoint для каждой пары (папка × job).

## Связанные документы

- [AGENTS.md](../../AGENTS.md) — главная документация
- [WORKFLOW.md](WORKFLOW.md) — рабочий процесс
- [../api/ENDPOINTS.md](../api/ENDPOINTS.md) — HTTP
- [../database/SCHEMA.md](../database/SCHEMA.md) — SQLite
- [../features/FIRST-RUN.md](../features/FIRST-RUN.md) — первый запуск
- [../features/REMOTE-ASR.md](../features/REMOTE-ASR.md) — облачные провайдеры
- [../features/MEETING-CAPTURE.md](../features/MEETING-CAPTURE.md) — запись созвона без бота
- [README.md](../../README.md) — запуск для человека
