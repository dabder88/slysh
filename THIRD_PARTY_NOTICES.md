# Сторонние компоненты (справка для владельца)

Краткий перечень основных зависимостей **Slysh**. **Лицензию всего продукта выбирает владелец**; этот файл не заменяет юридическую due diligence. Точные версии пакетов — в `uv.lock` установленной копии или репозитория.

Копия для пользователя Setup: `licenses\THIRD-PARTY-NOTICES.md` в каталоге программы (копируется при сборке payload из этого файла).

## Как обновлять

1. При изменении `pyproject.toml` / `uv.lock` — проверить строки ниже и при необходимости дописать новые пакеты.
2. Для полного списка wheels после `uv sync` (на машине разработки):  
   `uv pip list` в UI `.venv` и в engine venv после установки extras.
3. Сборка payload: `scripts\build-installer-payload.ps1` кладёт этот файл в `dist\payload\licenses\`.

---

## Python — базовый UI (`[project]` dependencies)

| Компонент | Типичная лицензия | Назначение в Slysh |
|-----------|-------------------|---------------------|
| [FastAPI](https://github.com/tiangolo/fastapi) | MIT | HTTP API UI |
| [Uvicorn](https://github.com/encode/uvicorn) | BSD-3-Clause | ASGI-сервер |
| [pywebview](https://github.com/r0x0r/pywebview) | BSD-3-Clause | Окно WebView2 |
| [sounddevice](https://github.com/spatialaudio/python-sounddevice) | MIT | Захват аудио (PortAudio) |
| [soundfile](https://github.com/bastibe/python-soundfile) | BSD-3-Clause | Чтение/запись WAV (libsndfile) |
| [NumPy](https://numpy.org/) | BSD-3-Clause | Буферы аудио в UI |

Транзитивные зависимости (Pydantic, Starlette, httptools и др.) наследуют свои лицензии из lock-файла.

---

## Python — extra `engine` (локальная расшифровка)

Устанавливается в отдельное engine-окружение (`.venv-engine-*`), не в лёгкий UI venv.

| Компонент | Типичная лицензия | Назначение |
|-----------|-------------------|------------|
| [PyTorch](https://pytorch.org/) | BSD-style (см. NOTICE) | Инференс моделей |
| [torchaudio](https://github.com/pytorch/audio) | BSD-style | Аудио для torch |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | MIT | Whisper CTranslate2 |
| [openai-whisper](https://github.com/openai/whisper) | MIT | Whisper (референс) |
| [GigaAM](https://github.com/salute-developers/GigaAM) | См. репозиторий (Salute) | Основной RNNT ASR |

PyTorch wheels для установщика подтягиваются с индекса `pytorch-cu129` (см. `pyproject.toml`); при поставке пользователю учитывайте условия NVIDIA/CUDA для GPU-сборок.

---

## Python — extra `diarization`

| Компонент | Типичная лицензия | Назначение |
|-----------|-------------------|------------|
| [NeMo toolkit ASR](https://github.com/NVIDIA/NeMo) | Apache-2.0 | Диаризация спикеров |
| [OmegaConf](https://github.com/omry/omegaconf) | BSD-3-Clause | Конфиги NeMo |

Тяжёлые зависимости NeMo — см. `uv.lock`; для релиза может потребоваться отдельный перечень NOTICE от NVIDIA.

---

## Python — extra `youtube`

| Компонент | Типичная лицензия | Назначение |
|-----------|-------------------|------------|
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Unlicense | Скачивание с YouTube |
| [browser-cookie3](https://github.com/borisbabic/browser_cookie3) | LGPL-3.0 | Cookies для yt-dlp |
| [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api) | MIT | Субтитры YouTube |
| [Requests](https://requests.readthedocs.io/) | Apache-2.0 | HTTP-клиент |

---

## Сборка репозитория (не в runtime пользователя, кроме артефактов Setup)

| Компонент | Лицензия | Назначение |
|-----------|----------|------------|
| [Tailwind CSS](https://tailwindcss.com/) | MIT | Сборка `web/app.css` |
| [Node.js / npm](https://nodejs.org/) | Разные (см. npm пакеты) | `npm run build:css` |
| [Hatchling](https://github.com/pypa/hatch) | MIT | Сборка wheel пакета `slysh` |
| [pytest](https://pytest.org/), httpx | MIT | Тесты (dev group) |

---

## Бинарники и runtime в Setup (payload)

| Компонент | Лицензия / условия | Назначение |
|-----------|-------------------|------------|
| **ffmpeg** / **ffprobe** (`bin\`, текст `licenses\ffmpeg-LGPL.txt`) | LGPL-2.1+ (сборка зависит от конфигурации ffmpeg) | Декодирование медиа |
| **uv** (`bin\uv.exe`) | Apache-2.0 / MIT (Astral) | Создание и sync venv |
| **CPython** (`runtime\python\…`) | PSF License | Интерпретатор для uv/UI venv |
| **Slysh.exe** (лаунчер) | Проприетарный код продукта | Старт без консоли |
| **Microsoft Edge WebView2 Runtime** (bootstrapper в Setup) | [Условия Microsoft](https://developer.microsoft.com/microsoft-edge/webview2/) | Отображение UI |

---

## Облачные сервисы (по выбору пользователя)

Данные отправляются на сторонние API только при настройке ключей пользователем:

| Провайдер | Документация |
|-----------|--------------|
| OpenRouter | https://openrouter.ai/ |
| Groq, OpenAI | Соответствующие ToS/API |
| Gladia, Deepgram | Пресеты HTTP ASR |
| Кастомный HTTP endpoint | URL пользователя |
| Gemini CLI | Google — отдельный CLI и ToS |
| Apify (YouTube) | https://apify.com/ |

Секреты на Windows хранятся локально (DPAPI), не в репозитории.

---

## Обязательства при распространении (кратко)

- **LGPL (ffmpeg):** при изменении линковки/поставке object code — соблюдать требования LGPL; в payload кладётся `ffmpeg-LGPL.txt`.
- **MIT / BSD / Apache:** обычно требуют сохранения текста лицензии и отказа от гарантий; для релиза часто объединяют NOTICE-файл из `uv pip licenses` или аналога.
- **NeMo / PyTorch / CUDA:** проверить совместимость коммерческого использования и redist GPU-библиотек.
- **Git-зависимость GigaAM:** фиксируется коммитом в `uv.lock`; при форке — соблюдать лицензию upstream.

---

*Волна F (F.4). Последнее содержательное обновление: 2026-10-02.*
