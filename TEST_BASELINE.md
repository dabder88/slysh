# Волна 0: baseline pytest (историческая сводка)

Исходный аудит (`plan-fix.md`): **364 passed, 8 failed**. Текущий локальный прогон (копия GPT, venv с dev): **469+ passed** при `GIGAAM_SKIP_ENGINE=1` и изолированном `GIGAAM_DESKTOP_HOME` в фикстурах.

`tests/` в этой ветке **не в git** (см. `.gitignore`); CI использует `scripts/ci_mandatory_checks.ps1` и каталог `ci/`.

## Было 8 fail → причина → что сделано

| # | Область | Причина | Исправление |
|---|---------|---------|-------------|
| 1 | Диаризация (3 теста) | Контракт `label(..., cancelled=None)` | Заглушки и engine path обновлены; pytest diarization |
| 2 | `JsApi` / `open_url` | Ограничения URL vs тест | Согласованы разрешённые схемы/хосты |
| 3 | `open_path` | 404 vs открытие родителя | B5: API 404 для отсутствующего файла; `smoke_open_path_api.py` |
| 4 | Installer layout | Жёсткий путь машины сборки | `smoke_installer_layout.py` / payload smoke |
| 5 | Секреты в API | Полный ключ в GET | A7: masked + session; `smoke_providers_secret_contract.py` |
| 6 | Streaming transcript | Сегмент до завершения + тайм-аут | Тесты streaming/job progress |
| 7–8 | Прочие (см. `.review/pytest.log`) | Смешанные контракты batch/UI | Волны A/B: batch, export, cloud route smokes |

## Изоляция (0.1)

- `PYTHONPATH` → `src/`; проверка: `ci/check_import_path.py`
- Данные: `GIGAAM_DESKTOP_HOME` во временный каталог (conftest / CI)
- Сеть: обязательный pytest без внешних API; интеграции — отдельные smokes

## Обязательные проверки без полного `tests/`

```powershell
powershell -File scripts\ci_mandatory_checks.ps1
```

См. также [`implementation-status.md`](implementation-status.md).
