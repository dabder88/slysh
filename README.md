# Slysh

Personal Windows app for GigaAM transcription of files and microphone audio. The UI process (FastAPI + pywebview) never imports PyTorch; recognition runs in a separate engine process.

Python package and launch command are still `slysh` (`uv run slysh`). The visible product name is **Slysh**.

## Документация для ИИ и разработчиков

Устройство проекта, стадия и правила работы:

- [AGENTS.md](AGENTS.md) — главная документация
- [AI_GUIDE.md](AI_GUIDE.md) — короткий указатель
- [docs/core/ARCHITECTURE.md](docs/core/ARCHITECTURE.md) — процессы UI/engine
- [docs/core/WORKFLOW.md](docs/core/WORKFLOW.md) — запуск и тесты
- [docs/features/FIRST-RUN.md](docs/features/FIRST-RUN.md) — клон и пакеты расшифровки

## Запуск на Windows

Двойной клик по `Slysh.bat` в папке проекта. Нужны **ffmpeg в PATH** и **uv**.

Чужой Windows ставится из `Slysh-Setup.exe` (скрипт `installer/Slysh.iss`): ярлык в меню Пуск, удаление через «Приложения», данные в `%LOCALAPPDATA%\Slysh`. В комплект уже входит `bin\ffmpeg.exe`. Сам exe в git не коммитится.

Иконка окна на панели задач берётся из `slysh.ico` в корне репозитория (при запуске через Python/pywebview). Чтобы ярлык на рабочем столе выглядел так же: создайте ярлык на `Slysh.bat` → «Изменить значок» → укажите `slysh.ico` в папке проекта. Прямой запуск bat из проводника может показывать значок Python, пока не открыто окно приложения.

Логотип в интерфейсе: `web/branding/` и `slysh.ico` (в git). Папка `design/` в репозиторий не входит; для смены макета держите локально `design/logo/final`, затем `powershell -File scripts\sync-branding.ps1`.

Если `.venv` уже есть (повторный запуск на вашей машине) — bat сразу открывает окно, **без** `uv sync`.

Клон с GitHub без окружения:

1. Поставьте [uv](https://docs.astral.sh/uv/getting-started/installation/) и ffmpeg.
2. Запустите bat: один раз ставится лёгкий UI (`uv sync` без extras).
3. В окне, если пакетов расшифровки нет, появится согласие. «Скачать пакеты» ставит torch/GigaAM. Можно закрыть «Позже» и в Настройках указать OpenRouter, Groq, OpenAI, Gladia, Deepgram, свой HTTP endpoint или Gemini CLI — локальный движок тогда не обязателен. Как подключать сервисы: [docs/features/REMOTE-ASR.md](docs/features/REMOTE-ASR.md).
4. Веса модели этим шагом не качаются — кнопка **Скачать модель**, как раньше.

Веса лежат в `models` рядом с проектом. Разово скопируйте уже скачанные файлы (Buzz cache и локальный Hugging Face hub — только копирование, в рантайме эти папки не читаются):

```bat
powershell -File scripts\copy-local-models.ps1
```

Из консоли:

```bat
cd /d путь\к\Slysh
uv sync --extra engine --extra diarization --extra youtube
uv run slysh
```

## Model cache

Единственный каталог: `models` в корне проекта (в тестах — `GIGAAM_PROJECT_MODELS`).

Сканер смотрит туда на:

- `gigaam/*.ckpt`
- Hugging Face `models--*--faster-whisper-*`
- плоские `faster-whisper-<size>/`
- OpenAI Whisper `whisper/*.pt` (и `*.pt` в корне `models/`)

После того как вы положили файлы, откройте **Настройки** или вызовите `GET /api/models` — список обновится. Новые модели не нужно прописывать в коде.

В **Настройках** можно скачать **GigaAM** (в `models/gigaam/`) или **Faster-Whisper** выбранного размера (в `models/faster-whisper-<size>/`).

Force CPU inference with `GIGAAM_FORCE_CPU=1`.

## Live microphone and meeting capture

Live dictation (`#/live`) uses sequential ~20 s windows, not overlapping partials. Expect about 20 seconds of latency before text appears.

Meeting capture (`#/meeting`) records Windows system audio (WASAPI loopback) plus an optional microphone, mixed to one mono track — no Zoom/Meet bot. Dictation and meeting recording cannot run at the same time. Details: [docs/features/MEETING-CAPTURE.md](docs/features/MEETING-CAPTURE.md).

## Startup time

Measure window/API start without loading the engine:

```bat
uv run python scripts/measure_startup.py
```
