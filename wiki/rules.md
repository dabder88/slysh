# Правила для правок

- Не править `F:\ProjectsAI\Slysh` и `F:\ProjectsAI\buzz-gigaam`, если задача про эту продовую копию.
- Не запускать `uv sync` без extras в `.venv` этой папки и в ежедневном `.venv`. Такая команда снимает torch.
- Лёгкое окружение установщика — только `dist/payload/.venv`. Сборка: `scripts\build-installer-payload.ps1` (`uv sync --no-editable` без extras). В payload обязательны `bin\uv.exe` и `bin\ffmpeg.exe`.
- Процесс окна не импортирует torch, пакет модели `gigaam` и `slysh.rnnt_backend`. Проверка: `tests/test_ui_imports.py`.
- В именах файлов поставки нет строки `gigaam`. Исключение — каталог и файлы самой модели `models/gigaam`, и чужой пакет `gigaam`, который ставит кнопка «Локально».
- В git не класть `dist`, веса `models`, базу, `settings.json` и ключи.
- Установщик не подписывать и не выкладывать, пока это не попросят отдельно.

## Документация (обязательно)

Любая **значимая** правка в этой копии должна быть отражена в **markdown**, не только в коде и чате.

1. **Техническая спецификация** — файлы в `docs/` по таблице в [AGENTS.md](../AGENTS.md) (ARCHITECTURE, ENDPOINTS, features, design и т.д.).
2. **Вики продовой копии** — дописать дату и суть в [[log]]; при новой теме — отдельная страница в `wiki/` и одна строка в [[index]].
3. **UI/дизайн настроек** — при изменении модала обновлять [docs/design/settings_modal_bento/README.md](../docs/design/settings_modal_bento/README.md) и при необходимости [[settings-ui]].

Пустые заглушки не создавать. Старые записи в [[log]] не переписывать — только дописывать.

См. [[product]], [[installer]], [[first-run]], [[settings-ui]].
