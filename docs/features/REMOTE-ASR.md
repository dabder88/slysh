# Облачные и HTTP-провайдеры ASR

Настройки → спойлеры (порядок в UI): **Gladia**, **Groq**, **Deepgram**, **OpenAI**, **OpenRouter**, **Gemini CLI**, **Кастомный HTTP**. Ключ вставляется в поле спойлера сервиса, не в общий текст подсказки.

### Бесплатные лимиты (проверяйте на сайте провайдера — условия меняются)

| Провайдер | Что дают | Тип |
|-----------|----------|-----|
| Gladia | €50 кредитов при регистрации (ориентир ~80+ ч async / ~60+ ч live) | разово, без ежемесячного reset |
| Groq | $0-тариф Whisper в квотах RPM/RPD и ~8 ч аудио/сутки, файл до 25 MB | постоянный free tier |
| Deepgram | $200 промо-кредитов без карты (часто срок 12 месяцев) | стартовый trial, не «free forever» |

Официально: [Gladia pricing](https://www.gladia.io/pricing), [Groq rate limits](https://console.groq.com/docs/rate-limits), [Deepgram pricing](https://deepgram.com/pricing).

После смены Python-кода провайдеров нужно **закрыть окно и запустить `Slysh.bat`**. Кнопка «Обновить интерфейс» подтягивает HTML/JS; старый uvicorn на `PUT`/`POST /api/providers/http/…` отвечает **Method Not Allowed** (запрос падает в StaticFiles).

## Встроенные сервисы

| Настройки | id в каталоге | Протокол | Куда идёт запрос |
|-----------|---------------|----------|------------------|
| Groq | `http:groq` | OpenAI Whisper | `POST https://api.groq.com/openai/v1/audio/transcriptions`, Bearer |
| OpenAI | `http:openai` | OpenAI Whisper | `POST https://api.openai.com/v1/audio/transcriptions`, Bearer |
| Gladia | `http:gladia` | Gladia v2 | `x-gladia-key`, `POST /v2/upload`, затем `POST /v2/pre-recorded`, опрос |
| Deepgram | `http:deepgram` | Deepgram | `Authorization: Token`, `POST /v1/listen` |
| OpenRouter | `openrouter:{slug}` | OpenRouter STT | `POST …/audio/transcriptions` (JSON + base64) |
| Кастом | `custom:{id}` | `openai` / `gladia` / `deepgram` | endpoint из настроек |
| Gemini CLI | `cli:gemini` | CLI | `gemini -p "@file"`; не для диктофона и записи встречи |

Ключи в `%LOCALAPPDATA%\Slysh\settings.json` → `providers`. Env перекрывает файл: `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY`, `GLADIA_API_KEY`, `DEEPGRAM_API_KEY`. GET `/api/providers` и GET `/api/proxy` отдают сохранённые секреты целиком (локальное приложение).

## Прокси (HTTP/HTTPS)

Настройки → отдельный блок **Прокси** (выше «Сервисы и ключи»): хост, порт, логин и пароль (необязательны), вкл., чекбоксы по сервисам. API: `GET`/`PUT /api/proxy`. В `settings.json` → `proxy`:

| Поле | Смысл |
|------|--------|
| `enabled` | Включить прокси |
| `host`, `port`, `username`, `password` | HTTP-прокси (логин/пароль опциональны) |
| `targets` | `openrouter`, `groq`, `openai`, `gladia`, `deepgram`, `custom`, `gemini`, `youtube` |

Реализация: `src/slysh/http_proxy.py` — `remote_asr.py` (HTTP STT), `gemini_cli.py` и `youtube_*.py` (env / opener). Только HTTP/HTTPS-прокси (stdlib), не SOCKS. Локальный engine не проксируется. При `enabled` без хоста сохранение отклоняется (400).

Сохранение пресета: `POST` или `PUT` `/api/providers/http/{groq|openai|gladia|deepgram}`. UI шлёт **POST**.

Расшифровка без torch-engine (UI-процесс). Диктофон и запись встречи: локальная модель или HTTP; Gemini CLI нельзя.

## Gladia

Для русского и автоязыка выбирайте **solaria-1**.

**solaria-3** — только en/fr/de/es/it и **обязателен** один язык в `language_config`. Без языка Gladia отвечает `Invalid parameter(s). See validation_errors…`. В Slysh нет выбора языка: `solaria-3` в запрос не отправляется, Gladia берёт default solaria-1 (`gladia_init_payload` в `remote_asr.py`). **solaria-2** в API нет.

Кастомный Gladia: тип API «Gladia», endpoint `https://api.gladia.io`, ключ, модель solaria-1.

## Кастомный HTTP

Тип API в форме «Добавить»:

- **OpenAI Whisper API** — Bearer, `…/audio/transcriptions` (полный URL или base).
- **Gladia** / **Deepgram** — те же адаптеры, свой base URL (прокси).

Не подставлять Gladia в форму как «OpenAI» с `https://api.gladia.io` — это другой контракт.

## Код

| Файл | Роль |
|------|------|
| `src/slysh/providers.py` | Пресеты, ключи, `protocol` у custom |
| `src/slysh/http_proxy.py` | Настройки и opener для HTTP-прокси |
| `src/slysh/remote_asr.py` | Адаптеры, `gladia_init_payload` |
| `src/slysh/catalog.py` | id `http:…` в списке моделей |
| `web/index.html`, `web/js/shell.js` | Спойлеры и поля ключа (статическая вёрстка, не пустой JS-список) |

Тесты: `tests/test_remote_asr.py`, `tests/test_http_proxy.py`.
