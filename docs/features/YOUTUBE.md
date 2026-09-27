# YouTube-транскрибация

Экран **YouTube** (`#/youtube`) получает готовый транскрипт из субтитров видео — без скачивания аудио и без локального ASR.

## Для пользователя

1. Сайдбар → **YouTube**.
2. Вставьте ссылку (`watch?v=`, `youtu.be/`, `/shorts/`).
3. Выберите способ:
   - **Облачный сервис** — через Apify. Ключ можно указать прямо на экране YouTube (раскройте «Настройка способа») или в Настройках.
   - **Через ваш Firefox** — локально, бесплатно; извлечение cookies только из Firefox.
   - **Через другой браузер** — загрузите `cookies.txt`, экспортированный из Chrome/Edge (см. инструкцию на экране).
4. **Получить транскрипт** → job `kind=youtube` появится в расшифровках, откроется редактор.

### Пакет

На том же экране вкладка **Пакет**:

1. **Список URL** — по одной ссылке на строку, или **канал / плейлист** — одна ссылка и фильтры (лимит, даты YYYYMMDD, старт с video ID, направление older/newer; Shorts исключаются).
2. **Проверить список** → preview без записи в БД; в preview видно, сколько видео **уже в расшифровках** (`existing_job` в ответе resolve).
3. **Запустить пакет** → перед созданием пакета интерфейс спрашивает, загрузить заново, если часть URL уже есть среди готовых расшифровок (как и одиночная ссылка **Получить транскрипт**).
4. Между видео пауза **5 с** (настраивается в правилах пакета).
5. Опционально **автоэкспорт** SRT/VTT/TXT или **Markdown** (тот же Obsidian-шаблон, что у файлов: `title`, `source` = URL, `kind: youtube`, секция Transcript с таймкодами) в одну или несколько папок; если папки не заданы — `%LOCALAPPDATA%\Slysh\youtube\exports\`.

Файловые пакеты и YouTube-пакеты **не смешиваются** (нельзя добавить файлы в YouTube-пакет через «+ Файлы»).

После обновления **Python-кода** (новые API) нужен **полный перезапуск** Slysh (`Slysh.bat`). Кнопка «Сбросить кэш интерфейса» в настройках обновляет только HTML/JS, не backend.

Если субтитров нет — ошибка. Fallback на ASR не выполняется.

## Apify

Основной актор: `scrapesage/youtube-transcript-scraper`. При ошибке — резервный `h7sDV53CddomktSi5`.

Для видео, где yt-dlp не может скачать субтитры из‑за **PO Token** (типично с авто-субтитрами в 2025–2026), **Apify обычно работает надёжнее**.

## yt-dlp: цепочка fallback

При методе **yt-dlp + cookies** Slysh пробует по порядку:

1. Несколько `player_client` (android_vr без cookies, затем с cookies)
2. `youtube-transcript-api` (если установлен)
3. **Apify** — автоматически, если задан API-ключ

## Cookies (для yt-dlp)

Файл: `%LOCALAPPDATA%\Slysh\youtube\cookies.txt` (Netscape).

- **Firefox (только он):** на экране YouTube → «Вход в YouTube (для способа «Через ваш Firefox»)».
  - В списке профилей показываются **только профили Firefox** (Chrome и Edge не поддерживаются).
  - **Без файла:** если `cookies.txt` отсутствует, yt-dlp читает cookies напрямую из Firefox (`--cookies-from-browser firefox`).
  - **Быстро из Firefox:** кнопка извлекает cookies из профиля по умолчанию через `browser-cookie3`.
  - **По профилю:** выберите `default-release` (не пустой `default`) → **Извлечь**.
  - Пакет `browser-cookie3` ставится вместе с локальными пакетами (`uv sync --extra engine --extra diarization --extra youtube`). Отдельный `uv sync --extra youtube` на уже собранном окружении не запускать: без остальных extras он снимет torch.
  Выбирайте профиль с пометкой **default-release** (или другой, где есть `cookies.sqlite`). Профиль **default** без файла cookies в списке помечен «(нет cookies)» и недоступен.
- **Chrome 127+ на Windows:** App-Bound Encryption блокирует чтение cookies Python-скриптами. Используйте Firefox, Apify или ручной импорт cookies.txt (расширение Get cookies.txt LOCALLY) → **Загрузить cookies.txt**.

## Ограничения v1

- Нет локального медиаплеера в редакторе — ссылка «Открыть на YouTube»; таймкоды глав прокручивают расшифровку к соответствующему сегменту.
- Метаданные (дата, таймкоды глав): oEmbed + yt-dlp + разбор страницы watch (`youtube_metadata.py`); при открытии job в редакторе недостающие поля догружаются автоматически.
- **Спикеры:** для YouTube **не поддерживаются** — только текст субтитров без диаризации.
- Список канала для пакета — через **yt-dlp**; Apify вызывается **на каждое видео**, если выбран метод Apify.
- Последовательная обработка (не параллельно); **перед добавлением** одиночного URL или пакета UI предупреждает о совпадении с готовой расшифровкой. Правило **«пропускать готовые»** (`skip_completed`) действует только при **повторном запуске** уже созданного пакета в `batch_runner`.

## Устройство

```
#/youtube
  POST /api/youtube/ingest { url, method, language }
  POST /api/youtube/batch/resolve — preview URL (+ `existing_job` для уже готовых)
  POST /api/library/check-existing — проверка файлов и YouTube URL перед intake
  POST /api/youtube/batch — пакет + jobs + autostart
       ├─ apify → youtube_apify.py → Apify run-sync
       └─ ytdlp → youtube_ytdlp.py → yt-dlp --cookies … --write-sub
            └─ vtt.py → Segment[]
  batch rules.batch_type=youtube → batch_runner (без engine)
  job kind=youtube, source_path=canonical URL, source_title=название видео
```

| Что | Где |
|-----|-----|
| Экран | `web/js/youtube.js`, `view-youtube` в `web/index.html` |
| Список канала | `src/slysh/youtube_channel.py` |
| Оркестратор | `src/slysh/youtube_ingest.py` |
| Apify | `src/slysh/youtube_apify.py` |
| yt-dlp | `src/slysh/youtube_ytdlp.py` |
| Cookies | `src/slysh/youtube_cookies.py` |
| Метаданные | `src/slysh/youtube_metadata.py` |
| VTT | `src/slysh/vtt.py` |

UI-процесс не импортирует torch.

## Зависимости

`yt-dlp`, `browser-cookie3` и `youtube-transcript-api` входят в extra `youtube`. Кнопка «Локально» ставит их вместе с engine и diarization. Для Apify достаточно HTTP-клиента из stdlib.

## Связанные документы

- [ENDPOINTS.md](../api/ENDPOINTS.md)
- [SCHEMA.md](../database/SCHEMA.md)
- [ARCHITECTURE.md](../core/ARCHITECTURE.md)
