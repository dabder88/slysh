# Режим «только облако»

Расшифровка файлов, диктофона и встречи через **HTTP-провайдеров** (Groq, OpenAI, Gladia, Deepgram, OpenRouter, кастомный API, Gemini CLI) **без** установки PyTorch и локального engine.

## Как включить

1. При первом запуске (модаль «Как расшифровывать») — **«Через облако (без нейросетей на ПК)»**.
2. Или в любой момент: Настройки → провайдер (режим снимается кнопкой «Включить локальную расшифровку»).

Настройка в `%LOCALAPPDATA%\Slysh\settings.json`: `engine_mode: "cloud_only"`.

API: `POST /api/setup/cloud-only`, сброс: `POST /api/setup/enable-local`.

## Поведение

- `auto_start_engine` выключен — subprocess с torch не поднимается.
- Выбор локальной модели GigaAM/Whisper в настройках заблокирован, пока режим активен.
- Расшифровка файлов идёт через `_run_remote_job` при выбранном remote id.

Подробно про провайдеров: [REMOTE-ASR.md](REMOTE-ASR.md).

## Ограничения

| Возможность | В cloud_only |
|-------------|----------------|
| Локальный GigaAM / Whisper | Нет |
| Диаризация спикеров (NeMo) | Нет — нужны extras engine |
| Кнопка «Скачать модель» GigaAM | Скрыта |
| YouTube по субтитрам | Да (без engine) |
| Приватность | Аудио уходит к выбранному провайдеру |

## Связанные документы

- [FIRST-RUN.md](FIRST-RUN.md)
- [ARCHITECTURE.md](../core/ARCHITECTURE.md)
- [ENDPOINTS.md](../api/ENDPOINTS.md)
