# Slysh — AI Instructions

## Обязательная документация

**ПЕРЕД ЛЮБОЙ РАБОТОЙ прочитай:**

1. **[AGENTS.md](../AGENTS.md)** — главная документация и стадия продукта
2. **[docs/core/WORKFLOW.md](../docs/core/WORKFLOW.md)** — запуск, тесты, UI
3. **[docs/core/ARCHITECTURE.md](../docs/core/ARCHITECTURE.md)** — процессы, БД, потоки
4. **[AI_GUIDE.md](../AI_GUIDE.md)** — короткий указатель

## Обязательное обновление документации

После значимых изменений обнови соответствующие файлы. Полная таблица — в [AGENTS.md](../AGENTS.md).

## Project Overview

**Slysh** — десктопное Windows-приложение для расшифровки файлов и микрофона (GigaAM / Whisper / OpenRouter / Groq / OpenAI / Gladia / Deepgram / кастомный HTTP / Gemini CLI). UI (FastAPI + pywebview) не импортирует PyTorch; локальное распознавание — отдельный процесс `engine_server`. Облако идёт в UI-процессе. Python-пакет по-прежнему называется `slysh`; данные лежат в `%LOCALAPPDATA%\Slysh`.

## Tech Stack

- Python 3.12, FastAPI, uvicorn, pywebview, SQLite
- Engine extras: torch 2.8 cu129, GigaAM, faster-whisper, openai-whisper
- Diarization extra: NeMo ASR
- UI: vanilla ES modules, Tailwind 3.4 (без бандлера JS)

## Architecture Rules

1. UI-процесс не импортирует `torch`, `gigaam`, `slysh.rnnt_backend`.
2. `api.py` не импортирует `speakers_msdd` статически — только `importlib` в рантайме.
3. Если `.venv` есть, **не** запускай `uv sync` при старте и «на всякий случай».
4. Установка движка из UI всегда с `--extra engine --extra diarization --extra youtube`.
5. Каталог весов — `models/` в корне проекта (`GIGAAM_PROJECT_MODELS` в тестах). `GIGAAM_MODEL_ROOT` / Buzz-пути `paths.py` не читает.
6. Тесты: `.\.venv\Scripts\python.exe -m pytest`, не `uv run pytest` на уже собранном venv.
7. Облачный ASR не поднимает engine и не импортирует torch (`providers.py`, `remote_asr.py`, `gemini_cli.py`).

## Commands

```bat
Slysh.bat
.\.venv\Scripts\python.exe -m pytest
npm run build:css
```

## Key Files

```
src/slysh/app.py          # окно + uvicorn
src/slysh/api.py          # UI HTTP API
src/slysh/engine_server.py
src/slysh/db.py
src/slysh/runtime_setup.py
src/slysh/providers.py
src/slysh/remote_asr.py
web/index.html
web/js/main.js
Slysh.bat
```
