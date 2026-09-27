# AGENTS.md — Главная документация Slysh

Десктопное Windows-приложение для расшифровки аудио/видео и микрофона. Основной движок — **GigaAM** (e2e RNNT), дополнительно Whisper / faster-whisper. Интерфейс — pywebview + FastAPI; распознавание в отдельном процессе, чтобы окно не грузило PyTorch.

Python-пакет и команда по-прежнему `slysh` (`uv run slysh`, модуль `slysh`). Видимое имя продукта — **Slysh**. База и логи: `%LOCALAPPDATA%\Slysh`.

Запуск из исходников: `Slysh.bat`. Установщик — `dist\Slysh-Setup.exe`, в git не кладётся. Сборка: `scripts\build-installer-payload.ps1` (внутри — `smoke_installer_layout.py`) → `scripts\build-slysh-setup.ps1` → `dist\Slysh-Setup.exe`; комплект `dist\payload` (в т.ч. `bin\uv.exe`, `bin\ffmpeg.exe`, копии `src/` и `web/`).

### После правок, которые видит пользователь Setup

Если менялись **first-run**, модали установки пакетов, **`web/`**, **`src/slysh/`** (runtime_setup, launcher-поведение через payload), **`installer/`** или **`launcher/`** (пересборка `Slysh.exe` в payload) — **агент по завершении задачи пересобирает установщик** (не ждать отдельной просьбы «собери Setup»):

```powershell
powershell -File scripts\build-installer-payload.ps1
powershell -File scripts\build-slysh-setup.ps1
```

В ответе пользователю указать полный путь к **`dist\Slysh-Setup.exe`** и **LastWriteTime** файла (чтобы отличить от старой копии). Проверка «удалил → поставил заново» без этой сборки **не** подтягивает новый UI/backend.

Исключение: правки только docs/тестов без UI/backend — Setup не обязателен.

---

## Стадия продукта (сентябрь 2026)

Сделано и работает на машине разработки:

- Окно Slysh: очередь, редактор расшифровки, архив, диктофон, запись встречи (системный звук, спикеры после стопа), YouTube-транскрипт (один URL и **пакет канала/списка**), пакеты файлов
- Отдельный engine-процесс, каталог моделей в `models/`
- Облачный ASR: OpenRouter, Groq/OpenAI/Gladia/Deepgram (пресеты), кастомный HTTP, Gemini CLI
- Пакетная обработка, экспорт SRT/VTT/TXT/MD, идентификация спикеров (NeMo, если extra установлен)
- Поток сегментов в редактор во время файловой расшифровки (локальный engine)
- Режим «только облако» без torch (`engine_mode` в settings)
- Первый запуск для чужого клона: лёгкий `uv sync` только если нет `.venv`; модаль согласия на torch/GigaAM/NeMo (можно пропустить и указать API)
- Модал «Настройки»: bento UI, 640px, вкладки ASR / Сеть / Облако / YouTube / Система ([design doc](docs/design/settings_modal_bento/README.md), [wiki/settings-ui.md](wiki/settings-ui.md))
- Ручная проверка обновлений установленной копии (GitHub Releases, [APP-UPDATES.md](docs/features/APP-UPDATES.md))

Сознательно не сделано:

- Скачивание всех весов в `models/` как обязательный шаг клона (в Настройках — GigaAM и Faster-Whisper в `models/`)
- Подпись установщика, SmartScreen; автообновление в фоне (есть ручная проверка — [APP-UPDATES.md](docs/features/APP-UPDATES.md))

Связанный репозиторий Buzz — **другой продукт**. Код диаризации лежит в пакете `slysh.diarization`. Не править Buzz, если задача про Slysh.

---

## КРИТИЧЕСКИ ВАЖНО: обновление документации

**После любых значимых изменений обновляй документацию сразу.** Правки не считаются завершёнными, пока факты не записаны в **markdown** (репозиторий `docs/`, вики `wiki/` — см. ниже), а не только в коде или в чате Cursor.

| Изменение | Какие файлы обновить |
|-----------|----------------------|
| Экраны / hash-роуты фронтенда | [docs/core/ARCHITECTURE.md](docs/core/ARCHITECTURE.md), этот файл |
| Модал «Настройки», bento UI, id полей настроек | [docs/design/settings_modal_bento/README.md](docs/design/settings_modal_bento/README.md), [wiki/settings-ui.md](wiki/settings-ui.md), ARCHITECTURE, [wiki/log.md](wiki/log.md) |
| Любая значимая правка в prod-копии (ветка `prod-launch`, дерево `Slysh-prod`) | [wiki/log.md](wiki/log.md) (дата + суть); при новой теме — новый `wiki/*.md` + строка в [wiki/index.md](wiki/index.md) |
| HTTP API UI или engine | [docs/api/ENDPOINTS.md](docs/api/ENDPOINTS.md), ARCHITECTURE, этот файл |
| Схема SQLite / статусы job/batch | [docs/database/SCHEMA.md](docs/database/SCHEMA.md), ARCHITECTURE, этот файл |
| Запрет импорта torch в UI | ARCHITECTURE, WORKFLOW, этот файл, `tests/test_ui_imports.py` |
| Bat / первый запуск / extras | [docs/features/FIRST-RUN.md](docs/features/FIRST-RUN.md), README.md, этот файл |
| First-run / installer UI / payload (`web/`, `src/slysh/` в Setup) | [docs/core/WORKFLOW.md](docs/core/WORKFLOW.md) (пересборка Setup), FIRST-RUN, этот файл |
| Каталог моделей / env путей | ARCHITECTURE, README.md |
| Стек зависимостей | этот файл, README.md, `pyproject.toml` |
| Новая пользовательская фича | `docs/features/…`, этот файл (навигация) |

**Правила:** правь конкретные секции, не переписывай всё; проверяй ссылки между файлами. Для человека и другой нейросети в prod-копии дублируй суть изменений в [wiki/log.md](wiki/log.md) (хронология) и при необходимости в тематических страницах вики — см. [wiki/rules.md](wiki/rules.md).

### Создание новой документации

1. Файл в `docs/` (`core/`, `guides/`, `features/`, `api/`, `database/`)
2. Ссылка в навигации этого файла
3. При пользовательском сценарии — коротко в [README.md](README.md)

Не создавай пустые заглушки.

---

## Навигация по документации

### Основные документы

| Документ | Описание | Когда использовать |
|----------|----------|-------------------|
| [wiki/index.md](wiki/index.md) | Вики продовой копии: что это, как запускается, как собран установщик | Первая страница для человека и для другой нейросети |
| [docs/core/ARCHITECTURE.md](docs/core/ARCHITECTURE.md) | Процессы, фронт, модели, env | Перед правкой структуры |
| [docs/core/WORKFLOW.md](docs/core/WORKFLOW.md) | Запуск, тесты, CSS/JS, запреты | Перед началом работы |
| [AI_GUIDE.md](AI_GUIDE.md) | Короткий указатель для ИИ | Первая минута сессии |
| [AGENTS.md](AGENTS.md) | Точка входа Cursor | Автоправила репозитория |
| [README.md](README.md) | Запуск для человека | Клон и ежедневный старт |

### Дополнительные

| Документ | Описание |
|----------|----------|
| [docs/api/ENDPOINTS.md](docs/api/ENDPOINTS.md) | Список HTTP-роутов |
| [docs/database/SCHEMA.md](docs/database/SCHEMA.md) | Таблицы SQLite |
| [docs/features/FIRST-RUN.md](docs/features/FIRST-RUN.md) | Клон Git, venv, модаль пакетов |
| [docs/features/REMOTE-ASR.md](docs/features/REMOTE-ASR.md) | OpenRouter, Groq, OpenAI, Gladia, Deepgram, кастомный HTTP |
| [docs/features/MEETING-CAPTURE.md](docs/features/MEETING-CAPTURE.md) | Запись созвона: WASAPI loopback + микрофон |
| [docs/features/YOUTUBE.md](docs/features/YOUTUBE.md) | Транскрипт YouTube: Apify или yt-dlp + cookies |
| [docs/features/APP-UPDATES.md](docs/features/APP-UPDATES.md) | Ручная проверка обновлений через GitHub Releases |
| [docs/guides/COMPETITOR-VIBE.md](docs/guides/COMPETITOR-VIBE.md) | Конкурентный разбор vs Vibe, приоритеты roadmap |
| [docs/guides/LANDING-BRIEF.md](docs/guides/LANDING-BRIEF.md) | Смыслы и УТП для лендинга Slysh |
| [docs/features/STREAMING-TRANSCRIPT.md](docs/features/STREAMING-TRANSCRIPT.md) | Сегменты в редакторе во время file-job (engine и облако) |
| [docs/features/CLOUD-ONLY.md](docs/features/CLOUD-ONLY.md) | Расшифровка через API без локального torch |
| [docs/features/UI-LOCALE.md](docs/features/UI-LOCALE.md) | Язык интерфейса RU/EN, `ui_locale`, `web/locales/` |
| [docs/design/settings_modal_bento/README.md](docs/design/settings_modal_bento/README.md) | Модал «Настройки»: вкладки bento, invariant id, сборка CSS |
| [wiki/settings-ui.md](wiki/settings-ui.md) | Вики prod-копии: настройки для человека и агента |

Существующий пользовательский README — [README.md](README.md).

---

## Быстрый старт

Нужны **Windows**, **ffmpeg в PATH**, **uv**, Python **3.12** (см. `.python-version`).

Ежедневный запуск (если `.venv` уже есть):

```bat
Slysh.bat
```

Bat **не** вызывает `uv sync`, если существует `.venv\Scripts\python.exe`.

Клон без venv: bat один раз делает `uv sync` без extras → окно → согласие на тяжёлые пакеты. Подробно: [docs/features/FIRST-RUN.md](docs/features/FIRST-RUN.md).

Тесты (на уже собранном venv):

```bat
.\.venv\Scripts\python.exe -m pytest
```

Сборка CSS:

```bat
npm run build:css
```

Переменные: каталог данных — `GIGAAM_DESKTOP_HOME` (иначе `%LOCALAPPDATA%\Slysh`). Веса — `models/` или `GIGAAM_PROJECT_MODELS`. CPU: `GIGAAM_FORCE_CPU=1`. Полный список — в ARCHITECTURE.

---

## Стек технологий

| Слой | Технологии |
|------|------------|
| Язык | Python 3.12 (`requires-python >=3.12,<3.13`) |
| UI HTTP | FastAPI, uvicorn, pywebview 5 |
| Аудио UI | sounddevice, soundfile, numpy |
| Engine | torch 2.8.0+cu129, torchaudio, GigaAM (git), faster-whisper, openai-whisper |
| Спикеры | nemo-toolkit-asr (extra `diarization`) |
| БД | SQLite (`app.db`) |
| UI | HTML + ES modules, без бандлера JS |
| CSS | Tailwind 3.4, Material Symbols |
| Пакетный менеджер | uv (`pyproject.toml`, `uv.lock`) |

---

## Архитектура и потоки данных

Два процесса. Подробности и диаграммы — [ARCHITECTURE.md](docs/core/ARCHITECTURE.md).

```
bat → python -m slysh.app
        ├── uvicorn 127.0.0.1:ephemeral  (FastAPI UI, статика web/)
        ├── pywebview окно → http://127.0.0.1:<port>/
        └── по требованию: subprocess engine_server (torch)
                └── HTTP /transcribe_file, /progress, …
```

### Маршрутизация UI (hash)

| Hash | Экран |
|------|--------|
| `#/dashboard` | Панель |
| `#/queue` | Очередь |
| `#/transcripts` | Список расшифровок |
| `#/editor/{id}` | Редактор job |
| `#/archive` | Архив |
| `#/live` | Диктофон |
| `#/meeting` | Запись встречи |
| `#/youtube` | YouTube-транскрипт |
| `#/legacy/...` | Файлы и пакеты |

Настройки — модал, не hash-роут.

### Поток расшифровки файла

`POST /api/jobs/{id}/start` → локальная модель: spawn engine → decode ffmpeg → GigaAM/Whisper. Облако/CLI: UI-поток `transcribe_media` (без torch). Сегменты в SQLite → UI редактор.

Пакет: `batch_runner` в фоне, один активный пакет.

---

## Важные файлы и директории

### Backend

| Путь | Роль |
|------|------|
| `src/slysh/app.py` | `main()`, окно, JsApi |
| `src/slysh/api.py` | `create_ui_app`, все `/api/*` |
| `src/slysh/engine_server.py` | ASR-процесс |
| `src/slysh/engine_client.py` | HTTP к engine |
| `src/slysh/db.py` | SQLite |
| `src/slysh/runtime_setup.py` | Проба torch/gigaam, `uv sync` extras |
| `src/slysh/providers.py` | OpenRouter, пресеты Groq/OpenAI/Gladia/Deepgram, кастомный HTTP, Gemini CLI, ключи |
| `src/slysh/remote_asr.py` | STT по HTTP: OpenAI-совместимый, Gladia, Deepgram |
| `src/slysh/gemini_cli.py` | Headless `gemini -p @file` |
| `src/slysh/live_buffer.py` | Буфер диктофона и записи встречи |
| `src/slysh/meeting_capture.py` | Запись встречи: микшер, список устройств |
| `src/slysh/youtube_ingest.py` | YouTube: Apify / yt-dlp, сегменты в SQLite |
| `src/slysh/youtube_channel.py` | Список видео канала/плейлиста (yt-dlp) для пакета |
| `src/slysh/wasapi_loopback.py` | Системный звук Windows (COM WASAPI loopback) |
| `src/slysh/catalog.py` | Сканер `models/` + облачные id |
| `src/slysh/compute.py` | auto/gpu/cpu |
| `src/slysh/batch_runner.py` | Пакетная очередь |
| `src/slysh/rnnt_backend.py` | GigaAM (только engine) |
| `src/slysh/whisper_backend.py` | Whisper (только engine) |
| `src/slysh/speakers_msdd.py` | Диаризация (ленивый импорт) |

### Frontend

| Путь | Роль |
|------|------|
| `web/index.html` | Оболочка, importmap `?v=` |
| `web/js/main.js` | Инициализация экранов |
| `web/js/router.js` | Hash-роутер |
| `web/js/meeting.js` | Экран записи встречи |
| `web/js/youtube.js` | Экран YouTube |
| `web/js/shell.js` | Настройки, модаль пакетов |
| `web/styles/input.css` | Исходник Tailwind |
| `web/app.css` | Сборка |
| `web/branding/` | Логотип и favicon для UI (из `design/logo/final`, `scripts/sync-branding.ps1`) |

### Прочее

| Путь | Роль |
|------|------|
| `Slysh.bat` | Лаунчер |
| `slysh.ico` | Иконка окна (pywebview) и ярлыка Windows |
| `design/logo/final/` | Исходники логотипа; после правок — `build_exact_assets.py` + `sync-branding.ps1` |
| `pyproject.toml` | Пакет, extras `engine` / `diarization` / `youtube` |
| `models/` | Веса (в git только `.gitkeep`) |
| `tests/` | pytest |
| `scripts/` | smoke, copy-local-models, measure_startup |

---

## База данных

SQLite: `app.db` в app dir. Таблицы: `batches`, `jobs`, `segments`, `speakers`. Схема и статусы — [docs/database/SCHEMA.md](docs/database/SCHEMA.md).

---

## Структура проекта

```
Slysh/
├── AGENTS.md
├── AI_GUIDE.md
├── AGENTS.md
├── README.md
├── pyproject.toml
├── uv.lock
├── package.json
├── Slysh.bat
├── .claude/instructions.md
├── docs/
│   ├── core/ARCHITECTURE.md
│   ├── core/WORKFLOW.md
│   ├── api/ENDPOINTS.md
│   ├── database/SCHEMA.md
│   ├── features/FIRST-RUN.md
│   ├── features/REMOTE-ASR.md
│   └── features/MEETING-CAPTURE.md
│   └── features/YOUTUBE.md
├── src/slysh/
├── web/
├── tests/
├── scripts/
└── models/          # локальные веса, не в git
```

---

## Быстрая справка для частых задач

### Новый экран UI

1. Секция в `web/index.html`, пункт сайдбара
2. Роут в `web/js/router.js`
3. `init*` в `web/js/main.js`
4. Бамп `?v=` у изменённых модулей и `main.js` при необходимости
5. Обновить ARCHITECTURE (таблица маршрутов) и этот файл

### Новый API endpoint

1. Обработчик в `create_ui_app` (`api.py`)
2. Тест в `tests/`
3. Обновить [docs/api/ENDPOINTS.md](docs/api/ENDPOINTS.md)

### Изменение схемы БД

1. `_SCHEMA` и `_migrate()` в `db.py`
2. Тесты `tests/test_db.py` / `test_batch_db.py`
3. [docs/database/SCHEMA.md](docs/database/SCHEMA.md)

### Стили

1. Правь `web/styles/input.css` (не собранный `app.css` вручную)
2. `npm run build:css`
3. Бамп `app.css?v=` в `index.html`

---

## Ключевые технические паттерны

### Architecture Constraints (MUST FOLLOW)

1. UI-процесс не импортирует `torch` / `gigaam` / `rnnt_backend`. Проверка: `tests/test_ui_imports.py`.
2. Проба движка — subprocess `python -c "import torch, gigaam"`, не импорт в UI.
3. Не вызывать `uv sync` при существующем `.venv` (bat и агент).
4. `uv sync` без extras на полном окружении снимает torch/GigaAM/NeMo. Установка из UI — оба extras.
5. `paths.py` игнорирует `BUZZ_MODEL_ROOT` / `GIGAAM_MODEL_ROOT` для сканера; каталог — `models/` или `GIGAAM_PROJECT_MODELS`.
6. Не коммить веса в `models/` и секреты.

### Coding Conventions

- Python 3.12, типы в новых модулях
- Фронт — ES modules, без сборщика JS
- Пользовательские строки UI — на русском
- Тесты через pytest, фикстуры с `GIGAAM_DESKTOP_HOME` = tmp

---

## Связанные документы

1. [AGENTS.md](AGENTS.md)
2. [AI_GUIDE.md](AI_GUIDE.md)
3. [docs/core/ARCHITECTURE.md](docs/core/ARCHITECTURE.md)
4. [docs/core/WORKFLOW.md](docs/core/WORKFLOW.md)
5. [docs/api/ENDPOINTS.md](docs/api/ENDPOINTS.md)
6. [docs/database/SCHEMA.md](docs/database/SCHEMA.md)
7. [docs/features/FIRST-RUN.md](docs/features/FIRST-RUN.md)
8. [docs/features/REMOTE-ASR.md](docs/features/REMOTE-ASR.md)
9. [docs/features/MEETING-CAPTURE.md](docs/features/MEETING-CAPTURE.md)
10. [docs/features/YOUTUBE.md](docs/features/YOUTUBE.md)
11. [docs/features/UI-LOCALE.md](docs/features/UI-LOCALE.md)
12. [docs/design/settings_modal_bento/README.md](docs/design/settings_modal_bento/README.md)
13. [wiki/index.md](wiki/index.md) и [wiki/log.md](wiki/log.md)
14. [README.md](README.md)
15. [pyproject.toml](pyproject.toml)

---

## Помни главное правило

**Документация — это часть кода. Устаревшая документация хуже, чем её отсутствие.**
