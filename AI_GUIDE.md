# AI Quick Reference — Slysh

## ПЕРЕД НАЧАЛОМ РАБОТЫ (ОБЯЗАТЕЛЬНО!)

1. **[AGENTS.md](AGENTS.md)** — стадия продукта, правила, навигация
2. **[docs/core/WORKFLOW.md](docs/core/WORKFLOW.md)** — запуск и стиль работы
3. **[docs/core/ARCHITECTURE.md](docs/core/ARCHITECTURE.md)** — как устроено
4. При API — [docs/api/ENDPOINTS.md](docs/api/ENDPOINTS.md)
5. При БД — [docs/database/SCHEMA.md](docs/database/SCHEMA.md)
6. При первом запуске — [docs/features/FIRST-RUN.md](docs/features/FIRST-RUN.md)
7. При облачных провайдерах — [docs/features/REMOTE-ASR.md](docs/features/REMOTE-ASR.md)
8. При записи созвона — [docs/features/MEETING-CAPTURE.md](docs/features/MEETING-CAPTURE.md)
9. При YouTube — [docs/features/YOUTUBE.md](docs/features/YOUTUBE.md)
10. Продукт vs Vibe — [docs/guides/COMPETITOR-VIBE.md](docs/guides/COMPETITOR-VIBE.md)
11. Поток сегментов в редактор — [docs/features/STREAMING-TRANSCRIPT.md](docs/features/STREAMING-TRANSCRIPT.md)
12. Только облако без torch — [docs/features/CLOUD-ONLY.md](docs/features/CLOUD-ONLY.md)
13. Модал «Настройки» (bento) — [docs/design/settings_modal_bento/README.md](docs/design/settings_modal_bento/README.md), вики prod-копии — [wiki/settings-ui.md](wiki/settings-ui.md)
14. Обновления Setup — [docs/features/APP-UPDATES.md](docs/features/APP-UPDATES.md)

## Ключевые принципы

- Видимое имя: **Slysh**. Пакет и команда: `slysh` / `slysh`.
- Два процесса: UI без PyTorch, engine с torch.
- Готовый `.venv` не трогать `uv sync`.
- Веса в `models/` рядом с репо, не в `%LOCALAPPDATA%`.
- App data: `%LOCALAPPDATA%\Slysh` (`app.db`, логи, записи диктофона и встреч).

## Ключевые файлы

| Файл | Зачем |
|------|--------|
| `Slysh.bat` | Ежедневный запуск |
| `src/slysh/app.py` | Окно pywebview |
| `src/slysh/api.py` | Все UI-роуты |
| `src/slysh/providers.py` | Облачные/CLI провайдеры |
| `src/slysh/engine_server.py` | ASR HTTP |
| `src/slysh/db.py` | SQLite |
| `web/js/router.js` | Экраны |
| `web/styles/input.css` | Исходник стилей |

## ОБЯЗАТЕЛЬНО: обновляй документацию

После смены маршрутов, схемы БД, процесса запуска, запретов на импорт — правь `AGENTS.md` и `docs/core/ARCHITECTURE.md`. **Любую значимую правку сохраняй в md:** `docs/` по таблице в AGENTS.md и для prod-копии — дописывай [wiki/log.md](wiki/log.md) (см. [wiki/rules.md](wiki/rules.md)). Подробности в таблице в AGENTS.md.

## Частые ошибки

- `uv run pytest` / `uv sync` на полном venv → качает torch заново или **снимает** extras.
- Импорт `torch` в `api.py` / `app.py` — упадёт `tests/test_ui_imports.py` и замедлит старт окна.
- Правка CSS только в `input.css` без `npm run build:css` и без бампа `app.css?v=`.
- Правка JS без бампа `?v=` в importmap `web/index.html`.
- Путать `GIGAAM_MODEL_ROOT` (env для engine) с каталогом сканера (`paths.project_models_dir()`).

## Чек-лист перед работой

- [ ] Прочитал AGENTS.md и WORKFLOW
- [ ] Не планирую `uv sync` без нужды
- [ ] UI-изменения не тянут torch
- [ ] Знаю, какой экран/API трогаю
- [ ] Запланировал обновление md (docs + wiki/log при значимых правках)
