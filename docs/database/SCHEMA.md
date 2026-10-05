# Схема SQLite

Файл: `%LOCALAPPDATA%\Slysh\app.db` (или `$GIGAAM_DESKTOP_HOME/app.db`).

Код: `src/slysh/db.py`. Инициализация: `_SCHEMA` + `_migrate()` (колонки `archived`, диапазон ms и т.д.).

Foreign keys включены (`PRAGMA foreign_keys = ON`). Доступ с `_lock` (RLock).

## batches

| Колонка | Тип | Смысл |
|---------|-----|--------|
| `id` | INTEGER PK | |
| `name` | TEXT | Имя пакета |
| `rules_json` | TEXT | Правила, см. ниже |
| `status` | TEXT | `idle` / `running` / `paused` / `completed` |
| `created_at` | TEXT | ISO UTC |
| `archived` | INTEGER | 0/1 (миграция) |

### rules_json (ключи)

Из `batch_rules.DEFAULT_BATCH_RULES`:

| Ключ | Default | Смысл |
|------|---------|--------|
| `speakers` | `false` | Диаризация после расшифровки |
| `export` | `false` | Автоэкспорт |
| `export_fmt` | `srt` | `srt` / `vtt` / `txt` |
| `export_dir_mode` | `beside_source` | или `fixed` |
| `export_dir` | `""` | Папка при `fixed` |
| `skip_completed` | `true` | Пропуск уже готовых |
| `on_error` | `continue` | Поведение при ошибке job |

## jobs

| Колонка | Тип | Смысл |
|---------|-----|--------|
| `id` | INTEGER PK | |
| `kind` | TEXT | Источник: `file` / `live` / `meeting` / `youtube` |
| `source_path` | TEXT | Путь к медиафайлу или URL YouTube |
| `source_title` | TEXT | Название видео (YouTube, миграция) |
| `media_duration_s` | REAL | Кэш длительности записи (сек); заполняется при завершении job и при `refresh_media_duration` |

Для `kind=youtube` объект `youtube` в ответе API job (таблица `job_youtube_meta`, поле `video_json`): `title`, `channel`, `channel_url`, `upload_date`, `duration_s`, `chapters[]`, `thumbnail_url`, `video_id`, `url`. Старый `youtube/job-meta.json` при первом запуске мигрируется в SQLite и переименовывается в `job-meta.json.bak-migrated`.

## job_youtube_meta

| Колонка | Тип | Смысл |
|---------|-----|--------|
| `job_id` | INTEGER PK FK → jobs | CASCADE при удалении job |
| `method` | TEXT | `apify` / `ytdlp` |
| `language` | TEXT | Язык субтитров |
| `video_json` | TEXT | JSON метаданных и `audio_path` |
| `status` | TEXT | см. JobStatus |
| `progress` | REAL | 0…1 |
| `error_text` | TEXT | |
| `created_at` / `started_at` / `finished_at` | TEXT | |
| `last_export_path` | TEXT | Последний экспорт (последний элемент списка) |
| `last_export_paths` | TEXT | JSON-массив путей последнего мульти-экспорта |
| `device_used` | TEXT | cpu/gpu |
| `batch_id` | INTEGER FK | nullable, CASCADE при удалении пакета |
| `position` | INTEGER | Порядок в пакете |
| `range_start_ms` / `range_end_ms` | INTEGER | Фрагмент файла |
| `asr_model_id` / `asr_backend` | TEXT | Модель ASR на старте file-job; resume не переключает провайдер |
| `archived` | INTEGER | 0/1 |

**JobStatus:** `idle` → `queued` → `running` → `completed` \| `failed` \| `cancelled`; для live/meeting после stop до конца фоновой ASR — `finalizing`.

При старте приложения `recover_stale_state()` сбрасывает зависшие queued/running/finalizing jobs и running/paused batches.

## segments

| Колонка | Тип |
|---------|-----|
| `id` | INTEGER PK |
| `job_id` | INTEGER FK |
| `start_ms` / `end_ms` | INTEGER |
| `text` | TEXT |
| `speaker` | TEXT nullable |

Модель в коде: `models.Segment`.

## speakers

| Колонка | Тип |
|---------|-----|
| `job_id` + `speaker_key` | PK |
| `display_name` | TEXT |

`upsert_speaker`, `apply_speaker_names`.

## Связанные документы

- [ARCHITECTURE.md](../core/ARCHITECTURE.md)
- [ENDPOINTS.md](../api/ENDPOINTS.md)
- [AGENTS.md](../../AGENTS.md)
- [WORKFLOW.md](../core/WORKFLOW.md)
