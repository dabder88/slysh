# Статус реализации (живой трекер)

Источники: [`implementation-order.md`](implementation-order.md), [`plan-fix.md`](plan-fix.md).

**Легенда:** ✅ готово · 🟡 частично · 🔵 в работе / не в git · ⬜ не начато · ⏭️ отложено

**Последнее обновление:** 2026-10-02 — B4.2–B4.3 pause/stop lock + тесты.

---

## Сводка волн

| Волна | Фокус | Статус | Комментарий |
|-------|--------|--------|-------------|
| **0** | Основа тестов | 🟡 | pytest ~450; таблица «8 fail» не оформлена |
| **A** | Корректность | 🟡 | A1–A5,A8,A9,A11 ✅ smokes; **A6** 🟡; **A7,A10** остаются |
| **B** | Надёжность UX | 🟡 | B1–B3,B5,B4.2–B4.3 ✅; B4.4 manual ⏭️ |
| **C** | Job runtime | 🟡 | C.4 ✅; C.1–C.3 🟡 (не весь §1.1) |
| **D** | Безопасность | 🟡 | D.3–D.4 ✅; D.1–D.2/D.5–D.6 частично |
| **E** | Установщик | 🟡 | |
| **F** | CI / доки | 🟡 | |

---

## Следующий крупный этап (план агента)

| Блок | ID | Содержание |
|------|-----|------------|
| **1** | D.5 / A10 | DPAPI; Gemini yolo |
| **2** | D.5 | DPAPI для локальных секретов |
| **3** | D.1–D.2 | Loopback-only, UI session в WebView |

D.3–D.4 закрыты (см. таблицу D ниже).

---

## Волна A

| ID | Задача | Статус | Smoke / тест |
|----|--------|--------|----------------|
| A1 | Deadlock setup/updates | ✅ | `smoke_setup_updates_deadlock.py` |
| A2 | Cancel engine, следующий chunk | ✅ | `test_engine_cancel`, `smoke_engine_cancel_sequence.py` |
| A3 | Пакет `cloud_only` | ✅ | `smoke_cloud_batch_route.py` + guard в `_run_file_asr_job` |
| A4 | `on_error=stop`, итог пакета | ✅ | `smoke_batch_on_error_stop.py` |
| A5 | Коллизии экспорта пакета | ✅ | `smoke_batch_export_collision.py` |
| A6 | Спикер = ключ | ✅ | coerce на PATCH; export display; `test_speaker_patch_export.py` |
| A7 | Секреты в API | ✅ | masked + session; PUT omit/``; `smoke_providers_secret_contract.py` |
| A8 | Live/meeting finalize | ✅ | `finalizing` в БД, smokes finalize/double_stop, pytest live |
| A9 | YAML экспорт | ✅ | `json.dumps` в front matter; `smoke_export_yaml_windows_path.py` |
| A10 | Gemini без yolo | 🟡 | `yolo` в коде нет |
| A11 | Диаризация в engine | ✅ | |

---

## Волна B

| ID | Задача | Статус |
|----|--------|--------|
| B1 | Редактор dirty/stash | ✅ | `expected_revision` + 409; poll `syncSegmentsRevision`; smoke `smoke_segments_revision_409.py` |
| B2 | Атомарные settings, YT meta | ✅ |
| B3 | UI shutdown | ✅ |
| B4.1 | Audio ingest queue | ✅ |
| B4.2 | Сериализация pause/stop | ✅ | lock на pause/resume/stop + worker; meeting pause drain |
| B4.3 | Тесты pause/resume | ✅ | `test_live_buffer` cycles; `smoke_capture_pause_resume.py` |
| B4.4 | 10+ мин manual | ⏭️ |
| B5 | open_path 404 | ✅ |

---

## Волна C

| ID | Задача | Статус |
|----|--------|--------|
| C.1 | Coordinator local/remote | 🟡 |
| C.2 | `run_id` | 🟡 |
| C.3 | Cancel + engine | 🟡 |
| C.4 | Idempotent start | ✅ |
| C.5 | Single-instance | 🟡 |

---

## Волна D

| ID | Задача | Статус | Smoke / тест |
|----|--------|--------|----------------|
| D.1 | Loopback + engine token | 🟡 | `test_engine_requires_token`; bind 127.0.0.1 |
| D.2 | UI session bootstrap/cookie | 🟡 | `test_ui_session_cookie` |
| D.3 | Host/Origin на mutating | ✅ | `test_loopback_security`; `smoke_loopback_host_origin.py` |
| D.4 | Path traversal media/open-path | ✅ | `test_media_access`; `smoke_job_media_traversal.py` |
| D.5 | DPAPI секреты | ⬜ | |
| D.6 | OpenAPI off в production | ✅ | `test_openapi_disabled_in_production` |

## Волны E–F

См. `implementation-order.md`; E установщик 🟡.

---

## Smokes в git (регрессия волны A)

| Скрипт | Волна |
|--------|--------|
| `smoke_setup_updates_deadlock.py` | A1 |
| `smoke_cloud_batch_route.py` | A3 |
| `smoke_batch_on_error_stop.py` | A4 |
| `smoke_batch_export_collision.py` | A5 |
| `smoke_live_capture_finalize.py` | A8 |
| `smoke_capture_job_finalizing_status.py` | A8 |
| `smoke_capture_double_stop.py` | A8 |
| `smoke_capture_finalize_cancel.py` | C.3 |
| `smoke_capture_finalize_start_blocked.py` | C.3 |
| `smoke_export_yaml_windows_path.py` | A9 |
| `smoke_engine_cancel_sequence.py` | A2 |
| `smoke_speaker_rename_twice.py` | A6 |
| `smoke_segments_revision_409.py` | B1 |
| `smoke_loopback_host_origin.py` | D.3 |
| `smoke_job_media_traversal.py` | D.4 |
| `smoke_capture_pause_resume.py` | B4.3 |
| `kill_slysh_orphans.ps1` | уборка после проверок |

---

## Уборка процессов после проверок

```powershell
powershell -File scripts\kill_slysh_orphans.ps1 -WhatIf   # только список
powershell -File scripts\kill_slysh_orphans.ps1 -Force    # завершить без вопроса
```

## Правило обновления

После каждой итерации: строки здесь + `wiki/log.md`.
