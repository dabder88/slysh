# Slysh

Windows-приложение для расшифровки аудио и видео (GigaAM, Whisper, облачные API). Интерфейс — FastAPI + pywebview; распознавание в отдельном процессе.

## Установка

Готовый установщик: [Releases](https://github.com/dabder88/slysh/releases/latest) → **Slysh-Setup.exe**. Данные приложения: `%LOCALAPPDATA%\Slysh`.

## Запуск из исходников (Windows)

Нужны **uv**, **ffmpeg** в PATH и Python **3.12** (см. `.python-version`).

```bat
Slysh.bat
```

При первом клоне без `.venv` bat один раз выполнит `uv sync` (лёгкий UI). Пакеты torch/GigaAM — из окна согласия в приложении или:

```bat
uv sync --extra engine --extra diarization --extra youtube
```

Веса моделей — в папку `models/` (в git не входят). Разово скопировать уже скачанные веса:

```bat
powershell -File scripts\copy-local-models.ps1
```

## Сборка CSS (после правок `web/styles/`)

```bat
npm install
npm run build:css
```

Поднимите `?v=` у `/app.css` и изменённых модулей в `web/index.html`.

## Сборка установщика

1. Положите **ffmpeg** в `bin\ffmpeg.exe` (в git не входит; LGPL-сборка).
2. Установите [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`ISCC.exe`).
3. Соберите payload и Setup:

```powershell
powershell -File scripts\build-installer-payload.ps1
powershell -File scripts\build-slysh-setup.ps1
```

Результат: `dist\Slysh-Setup.exe` (папка `dist/` в git не входит).

Пересборка лаунчера `Slysh.exe` (опционально, нужен MSVC `cl.exe`): `scripts\build-slysh-launcher.ps1` — см. `launcher/README.md`.

Логотип в UI: `web/branding/`. Исходники макета — локально `design/logo/final`, обновление: `scripts\sync-branding.ps1`.

## Что не в репозитории

Тесты, внутренняя вики/документация для разработки, настройки Cursor/Claude, артефакты (`dist/`, `design/`, `models/`, `.venv/`, секреты в `.env`) — см. `.gitignore`.
