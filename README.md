# Slysh

Windows-приложение для расшифровки аудио и видео (GigaAM, Whisper, облачные API). Интерфейс — FastAPI + pywebview; распознавание в отдельном процессе.

## Установка

Готовый установщик: [Releases](https://github.com/dabder88/slysh/releases/latest) → **Slysh-Setup.exe**. Данные приложения: `%LOCALAPPDATA%\Slysh`.

## Запуск из исходников (Windows)

Нужны **uv**, **ffmpeg** в PATH и Python **3.12** (см. `.python-version`).

```bat
Slysh.bat
```

При первом клоне без `.venv` bat один раз выполнит `uv sync` (лёгкий UI). Пакеты torch/GigaAM — из окна согласия в приложении или `uv sync --extra engine --extra diarization --extra youtube`.

Веса моделей — в папку `models/` рядом с проектом (в git не входят).

## Состав репозитория

В git только код приложения (`src/slysh`, `web/`), зависимости (`pyproject.toml`, `uv.lock`), лаунчер и скрипт установщика (`launcher/`, `installer/`). Тесты, внутренняя документация, скрипты сборки и настройки Cursor/Claude хранятся локально и в `.gitignore`.
