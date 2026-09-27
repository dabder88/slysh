# HTTP API Slysh

Два сервера: **UI** (uvicorn в процессе окна) и **engine** (отдельный процесс). UI отдаёт статику `web/` с `/`.

## UI — jobs

| Метод | Путь | Назначение |
|-------|------|------------|
| GET | `/api/jobs` | Список jobs |
| POST | `/api/jobs` | Создать (`path`, опционально `batch_id`) |
| GET | `/api/jobs/{job_id}` | Job + сегменты (при `running` file-job сегменты накапливаются — локальный engine и облако, см. [STREAMING-TRANSCRIPT.md](../features/STREAMING-TRANSCRIPT.md)) |
| PATCH | `/api/jobs/{job_id}` | Архивация и поля |
| PATCH | `/api/jobs/{job_id}/segments` | Правка текста сегментов |
| POST | `/api/jobs/{job_id}/start` | Старт расшифровки |
| POST | `/api/jobs/{job_id}/retranscribe` | Повтор |
| POST | `/api/jobs/{job_id}/cancel` | Отмена расшифровки, ingest YouTube, облачного ASR и **диаризации спикеров** |
| DELETE | `/api/jobs/{job_id}` | Удаление |
| GET | `/api/jobs/{job_id}/media` | Файл источника |
| POST | `/api/jobs/{job_id}/export` | Экспорт SRT/VTT/TXT/MD |
| POST | `/api/jobs/{job_id}/speakers` | Диаризация (`kind=meeting` после стопа; файлы — по `source_path`). Для `kind=youtube` — **не поддерживается** (400) |
| PUT | `/api/jobs/{job_id}/speakers` | Имена спикеров |
| POST | `/api/jobs/{job_id}/remove-from-batch` | Убрать из пакета |

## UI — library / batches

| Метод | Путь | Назначение |
|-------|------|------------|
| GET | `/api/library` | Jobs, сгруппированные по пакетам |
| POST | `/api/library/check-existing` | Совпадения с готовыми расшифровками (`files[]`, `youtube_urls[]`) — `completed`, не в архиве |
| GET | `/api/batches` | Список пакетов |
| POST | `/api/batches` | Создать |
| GET | `/api/batches/{batch_id}` | Пакет + jobs |
| PATCH | `/api/batches/{batch_id}` | Имя (можно при выполняющемся пакете), правила (только когда пакет не активен), архив |
| DELETE | `/api/batches/{batch_id}` | Удалить |
| POST | `/api/batches/scan` | Сканировать папки |
| POST | `/api/batches/{batch_id}/items` | Добавить файлы |
| PUT | `/api/batches/{batch_id}/reorder` | Порядок |
| POST | `/api/batches/{batch_id}/start` | Запуск пакета |
| POST | `/api/batches/{batch_id}/pause` | Пауза |
| POST | `/api/batches/{batch_id}/cancel` | Отмена пакета |
| POST | `/api/batches/{batch_id}/export` | Экспорт всех completed в пакете |

## UI — экспорт пачкой

| Метод | Путь |
|-------|------|
| POST | `/api/export-jobs` |

## UI — модели, устройство, движок, setup

| Метод | Путь | Назначение |
|-------|------|------------|
| GET | `/api/status` | engine / model / asr / `can_download_local` / `model_download` (с `progress`: байты, `fraction`, `stalled`) |
| GET | `/api/models` | Локальный каталог + OpenRouter + Groq/OpenAI/Gladia/Deepgram + кастомные HTTP + Gemini CLI |
| PUT | `/api/models` | Выбрать модель |
| GET | `/api/providers` | OpenRouter/Apify/пресеты HTTP/кастом/CLI (включая сохранённые ключи) |
| GET | `/api/proxy` | Настройки HTTP-прокси; дубль `GET /api/providers/proxy` |
| PUT | `/api/proxy` | Прокси: `enabled`, `host`, `port`, `username`, `password` (опустить — не менять), `targets`; дубль `PUT /api/providers/proxy` |
| GET | `/api/providers/apify` | Статус ключа Apify |
| PUT | `/api/providers/apify` | Сохранить ключ Apify |
| PUT | `/api/providers/openrouter` | Ключ и модель OpenRouter |
| POST | `/api/providers/openrouter/refresh` | Каталог STT OpenRouter |
| PUT/POST | `/api/providers/http/{id}` | Ключ и модель встроенного сервиса (`groq`, `openai`, `gladia`, `deepgram`) |
| POST | `/api/providers/custom` | Добавить HTTP-провайдера (protocol, endpoint, модель, ключ) |
| PUT | `/api/providers/custom/{id}` | Обновить кастомного |
| DELETE | `/api/providers/custom/{id}` | Удалить кастомного |
| GET | `/api/providers/cli` | Статус Gemini CLI |
| GET | `/api/model/download` | Статус скачивания: `{ active, id, error, progress }`; `progress`: `bytes_done`, `bytes_total`, `fraction`, `indeterminate`, `message`, `stalled` |
| POST | `/api/model/download` | Скачать веса в `models/`; body `{ "id": "gigaam" \| "whisper:<size>" }` (без body — GigaAM) |
| GET | `/api/locale` | `{ "ui_locale": "ru" \| "en" }`; query `hint` — при отсутствии `ui_locale` в settings сохраняет `en`/`ru` по hint |
| PUT | `/api/locale` | body `{ "ui_locale": "ru" \| "en" }` |
| GET/PUT | `/api/compute` | auto / gpu / cpu; поля `explanations` / `warning` по `ui_locale` из settings |
| GET | `/api/setup` | `{ engine_packages, installing, dismissed, pending_model_setup, install_progress, remote_ready, log_tail, … }` — **не** стартует `uv`. При `installing`, `install_progress` включает `packages_done`, `packages_total`, `bytes_done`, `bytes_total`, `fraction`, `stalled` (нет изменений лога ~90 с) |
| GET | `/api/setup/engine` | Тот же статус + хвост лога |
| POST | `/api/setup/engine` | Старт `uv sync --extra engine --extra diarization --extra youtube`; body `{ "mark_pending_model": true }` — шаг выбора модели после пакетов (first-run «Локально») |
| POST | `/api/setup/later` | Флаг «Позже» |
| POST | `/api/setup/model-later` | Сброс флага `setup-pending-model-download` (шаг модели в first-run) |
| POST | `/api/setup/cloud-only` | Режим «только облако» (`engine_mode`), без autostart engine |
| POST | `/api/setup/enable-local` | Сброс `engine_mode` → `auto`, разрешить локальный engine |
| POST | `/api/engine/start` | Принудительно поднять engine |

Реализация setup: `src/slysh/runtime_setup.py`. См. [FIRST-RUN.md](../features/FIRST-RUN.md).

## UI — приложение и обновления

| Метод | Путь | Назначение |
|-------|------|------------|
| GET | `/api/app/info` | `version`, `install_kind`, `updates_enabled`, `github_repo`, `releases_url`, `last_check_at` |
| POST | `/api/updates/check` | GitHub `releases/latest` → `has_update`, `latest_version`, `release_notes`, `html_url` (только установленная копия) |
| GET | `/api/updates/status` | `phase` (`idle` / `downloading` / `ready` / `error`), прогресс байтов, `error` |
| POST | `/api/updates/download` | Скачать `Slysh-Setup.exe` во временную папку |
| POST | `/api/updates/apply` | Запуск установщика, выход процесса UI |

См. [APP-UPDATES.md](../features/APP-UPDATES.md). В `/api/setup` добавлено поле `engine_resync_recommended` после обновления приложения при смене `uv.lock`.


## UI — диктофон, запись встречи и файлы

| Метод | Путь |
|-------|------|
| GET | `/api/mics` | `?refresh=1` пересканирует микрофоны |
| GET | `/api/live/status` | `listening`, `paused`, `session_active`, `segments`, `remaining_s` |
| POST | `/api/live/start` |
| POST | `/api/live/pause` |
| POST | `/api/live/resume` |
| POST | `/api/live/stop` |
| POST | `/api/live/clear` | Сброс `job_id` на экране диктофона (без удаления job из БД) |
| GET | `/api/meeting/devices` | `?refresh=1` пересканирует выходы и микрофоны |
| GET | `/api/meeting/status` | `listening`, `paused`, `session_active`, `segments`, `elapsed_s` |
| POST | `/api/meeting/start` |
| POST | `/api/meeting/pause` |
| POST | `/api/meeting/resume` |
| POST | `/api/meeting/stop` |
| POST | `/api/meeting/clear` | Сброс `job_id` на экране встречи (без удаления job из БД) |
| GET | `/api/youtube/status` | Apify key, cookies, `cookies_auth_mode` (`file`/`browser`), yt-dlp, `batch_api`, `batch_resolve_api` |
| GET | `/api/youtube/cookies/browsers` | Профили Firefox/Chrome/Edge |
| POST | `/api/youtube/cookies/extract` | `{ browser, profile }` → cookies.txt; `profile: "__default__"` — быстрое извлечение |
| POST | `/api/youtube/cookies/import` | `{ path }` — импорт cookies.txt |
| POST | `/api/youtube/ingest` | `{ url, method: apify\|ytdlp, language? }` → job `kind=youtube` |
| POST | `/api/youtube/batch/resolve` | `{ mode: lines\|feed, lines?, feed_url?, filters? }` → `{ count, videos[] }` preview |
| POST | `/api/youtube/batch` | Создать YouTube-пакет: те же поля + `method`, `language`, `rules?`, `autostart?` → batch с `rules.batch_type=youtube` |
| POST | `/api/youtube/batch/create` | То же, что `/api/youtube/batch` (алиас для обхода редких 405 на static) |
| POST | `/api/open-path` |

## Engine (отдельный процесс)

База: `http://127.0.0.1:<port>` из stdout `PORT=`. Клиент: `engine_client.py`.

| Метод | Путь |
|-------|------|
| GET | `/health` |
| GET | `/progress` |
| POST | `/transcribe_file` |
| POST | `/transcribe_chunk` |
| POST | `/cancel` |

## Связанные документы

- [ARCHITECTURE.md](../core/ARCHITECTURE.md)
- [AGENTS.md](../../AGENTS.md)
- [WORKFLOW.md](../core/WORKFLOW.md)
- [REMOTE-ASR.md](../features/REMOTE-ASR.md)
- [MEETING-CAPTURE.md](../features/MEETING-CAPTURE.md)
- [YOUTUBE.md](../features/YOUTUBE.md)
