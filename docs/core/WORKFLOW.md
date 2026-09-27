# Рабочий процесс Slysh

## Перед началом

1. Прочитай [AGENTS.md](../../AGENTS.md) (стадия продукта и запреты).
2. Прочитай [ARCHITECTURE.md](ARCHITECTURE.md), если трогаешь процессы, БД или роуты.
3. Работай в репозитории **Slysh**, не в Buzz, если задача про это приложение.

## Запуск

Ежедневно:

```bat
Slysh.bat
```

Если есть `.venv\Scripts\python.exe` — сразу `python -m slysh.app`. **Не** добавляй `uv sync` в этот путь.

Консоль (когда extras уже стоят):

```bat
.\.venv\Scripts\python.exe -m slysh.app
```

Измерение HTTP-старта без engine: `scripts/measure_startup.py` (uvicorn + `/api/status`, `/api/setup`). Для установленной копии цель — окно или splash лаунчера в первые секунды при рабочем `.venv`; долгий `uv sync` только при починке venv (splash «подготовка…»).

## Тесты

На машине с готовым venv:

```bat
cd /d к корню репозитория
.\.venv\Scripts\python.exe -m pytest
```

Не используй `uv run pytest`, если не готов к sync: uv может заново тянуть torch (~3 ГБ) или снять extras.

Точечно: `.\.venv\Scripts\python.exe -m pytest tests/test_runtime_setup.py tests/test_ui_imports.py tests/test_remote_asr.py`.

UI-импорты: `tests/test_ui_imports.py` — не ломай список forbidden-модулей без обновления ARCHITECTURE и AGENTS.md.

Для тестов БД/API задавай `GIGAAM_DESKTOP_HOME` на временную папку (так делают фикстуры).

## Зависимости

- Базовый UI: зависимости `[project]` в `pyproject.toml` (без torch).
- Расшифровка: `--extra engine` (torch cu129, GigaAM, whisper).
- Спикеры: `--extra diarization` (NeMo). Код диаризации в пакете, внешний каталог не нужен.
- YouTube: `--extra youtube` (`yt-dlp`, cookies, transcript API).

Установка из приложения: `uv sync --extra engine --extra diarization --extra youtube` в корне репо (`runtime_setup.py`). Никогда не делай на полном venv `uv sync` **без** этих extras.

Индекс torch: `pytorch-cu129` в `pyproject.toml`.

## UI: CSS и кэш JS

1. Стили — `web/styles/input.css` (+ `tokens.css`).
2. Сборка: `npm run build:css` → `web/app.css`.
3. Подними `?v=` у `/app.css` и у изменённых модулей в importmap `web/index.html`.

Без бампа WebView может показать старый JS/CSS.

## Установщик (`Slysh-Setup.exe`)

`dist\Slysh-Setup.exe` **не в git**; внутри — снимок `dist\payload` (`src/`, `web/`, лёгкий `.venv`, `Slysh.exe`). Разработка через `Slysh.bat` не обновляет exe автоматически.

**После правок first-run, модалей, `web/`, UI-backend (`src/slysh/`), launcher/installer** — пересобрать и дать пользователю свежий Setup:

```powershell
powershell -File scripts\build-installer-payload.ps1
powershell -File scripts\build-slysh-setup.ps1
```

Результат: `dist\Slysh-Setup.exe`. В отчёте указать полный путь и дату изменения файла.

Только `Slysh.bat` / pytest без этих шагов — достаточно для dev-клона; **переустановка старым Setup** покажет старый интерфейс.

## Код

- Пользовательские строки — русский.
- Новые импорты в UI-процессе: убедись, что нет torch.
- Диаризация и GigaAM backend — только engine или `importlib` в обработчике.
- Не коммить `models/*` (кроме `.gitkeep`), `.venv`, колёса torch.

## Документация

После значимых изменений обнови таблицу в [AGENTS.md](../../AGENTS.md). **Все правки фиксируй в markdown**, не только в коде:

- `docs/` — спецификация (ARCHITECTURE, API, features, design).
- `wiki/log.md` — дата и суть для prod-копии `Slysh-prod`; новые темы — отдельный `wiki/*.md` и строка в `wiki/index.md`.
- Правило подробнее: [wiki/rules.md](../../wiki/rules.md).

Не оставляй пустых `.md`.

## Частые ловушки

| Симптом | Причина |
|---------|---------|
| Окно не открывается, в консоли качается torch | Случайный `uv sync` / `uv run` |
| Пропали GigaAM/NeMo из venv | `uv sync` без extras |
| Старый интерфейс после правки JS | Не поднят `?v=` |
| После переустановки старый first-run / модали | Не пересобран `dist\Slysh-Setup.exe` после правок `web/` или `src/slysh/` |
| Стили «есть в input.css, нет на экране» | Не собран `app.css` или класс съеден `@layer` |
| huggingface_hub странно падает | Битый `NO_PROXY`; bat его сбрасывает |
| Тест UI imports красный | Статический import torch/gigaam/speakers_msdd |

## Связанные документы

- [AGENTS.md](../../AGENTS.md) — главная документация
- [ARCHITECTURE.md](ARCHITECTURE.md) — устройство
- [../api/ENDPOINTS.md](../api/ENDPOINTS.md)
- [../database/SCHEMA.md](../database/SCHEMA.md)
- [../features/FIRST-RUN.md](../features/FIRST-RUN.md)
- [../features/REMOTE-ASR.md](../features/REMOTE-ASR.md)
- [README.md](../../README.md)
