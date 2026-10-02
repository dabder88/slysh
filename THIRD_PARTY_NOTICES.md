# Сторонние компоненты (справка для владельца)

Краткий перечень основных зависимостей Slysh. **Лицензию всего продукта выбирает владельец**; этот файл не заменяет юридическую due diligence.

## Python (базовый UI, `pyproject.toml`)

| Компонент | Назначение |
|-----------|------------|
| FastAPI, Uvicorn | HTTP API и статика UI |
| pywebview | Окно WebView2 |
| sounddevice, soundfile, numpy | Запись/буфер аудио в UI-процессе |

## Опциональные extras

| Extra | Компоненты | Назначение |
|-------|------------|------------|
| `engine` | PyTorch, torchaudio, faster-whisper, openai-whisper, GigaAM (git) | Локальная расшифровка |
| `diarization` | NeMo ASR toolkit | Спикеры |
| `youtube` | yt-dlp, browser-cookie3, youtube-transcript-api, requests | YouTube ingest |

## Сборка и установщик (репозиторий)

| Компонент | Назначение |
|-----------|------------|
| Tailwind CSS, npm | Сборка `web/app.css` |
| uv (в payload Setup) | Виртуальное окружение установленной копии |
| ffmpeg (бинарник в payload, LGPL) | Декодирование медиа |
| WebView2 Runtime | Отображение UI (Microsoft) |

## Облачные API (по выбору пользователя)

OpenRouter, Groq, OpenAI, Gladia, Deepgram, кастомный HTTP, Gemini CLI — сторонние сервисы; ключи хранятся локально (DPAPI на Windows).

---

Обновляйте этот список при смене `pyproject.toml`, payload установщика или документированных интеграций (волна F).
