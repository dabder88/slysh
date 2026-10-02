# Статус реализации (живой трекер)

Источники: [`implementation-order.md`](implementation-order.md), [`plan-fix.md`](plan-fix.md).

**Легенда:** ✅ готово · 🟡 частично · 🔵 в работе / не в git · ⬜ не начато · ⏭️ отложено

**Последнее обновление:** 2026-10-02 — E.7 probe new slot + revert; F.5 audit script.

---

## Сводка волн

| Волна | Фокус | Статус | Комментарий |
|-------|--------|--------|-------------|
| **0** | Основа тестов | ✅ | [`TEST_BASELINE.md`](TEST_BASELINE.md); `ci/check_import_path.py` |
| **A** | Корректность | ✅ | A1–A11 + smokes; Gemini prompt test (A10) |
| **B** | Надёжность UX | 🟡 | B1–B3,B5,B4.2–B4.3 ✅; B4.4 manual ⏭️ |
| **C** | Job runtime | 🟡 | C.4 ✅; C.1–C.3 ✅ smokes; C.5 smoke bat |
| **D** | Безопасность | ✅ | D.1–D.6 закрыты |
| **E** | Установщик | 🟡 | [`INSTALLER-BUILD.md`](INSTALLER-BUILD.md); E.1–E.5 в коде |
| **F** | CI / доки | 🟡 | GitHub workflow + `ci_mandatory_checks.ps1`; [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) |

---

## Следующий крупный этап (план агента)

| Блок | ID | Содержание |
|------|-----|------------|
| **1** | E | §7.2 dual venv (отдельно); E.6 manual matrix |
| **2** | F | лицензии/секреты в истории git (ручной аудит) |

D.1–D.6 закрыты (таблица D).

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
| A10 | Gemini без yolo | ✅ | temp cwd, cancel/timeout; `test_gemini_cli.py` |
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
| C.1 | Coordinator local/remote | ✅ | `smoke_asr_coordinator_*_queue.py` |
| C.2 | `run_id` | ✅ | `job_run_active`; idempotent start (локальные pytest) |
| C.3 | Cancel + engine | ✅ | QUEUED pump; `smoke_coordinator_cancel_running_pump.py` |
| C.4 | Idempotent start | ✅ | повторный `/start` в QUEUED не меняет `run_id` |
| C.5 | Single-instance | ✅ | `smoke_slysh_bat_single_instance.py`; lock в `app.main` |

---

## Волна D

| ID | Задача | Статус | Smoke / тест |
|----|--------|--------|----------------|
| D.1 | Loopback + engine token | ✅ | engine `127.0.0.1` + token; bat/launcher env |
| D.2 | UI session bootstrap/cookie | ✅ | pywebview bridge; per-instance cookie; `smoke_ui_auth_session.py` |
| D.3 | Host/Origin на mutating | ✅ | `test_loopback_security`; `smoke_loopback_host_origin.py` |
| D.4 | Path traversal media/open-path | ✅ | `test_media_access`; `smoke_job_media_traversal.py` |
| D.5 | DPAPI секреты | ✅ | providers+proxy migrate; `test_secrets_dpapi_migration.py`, smoke |
| D.6 | OpenAPI off в production | ✅ | `test_openapi_disabled_in_production` |

## Волна F

| ID | Задача | Статус |
|----|--------|--------|
| F.1 | Windows CI без torch | ✅ | `.github/workflows/pytest.yml` + smokes |
| F.2 | `test_ui_imports` в CI | ✅ | `ci/check_ui_imports.py` |
| F.3 | JS + CSS в CI | ✅ | `check-web-js.ps1`, `npm run build:css` |
| F.4 | Сторонние лицензии | 🟡 | `THIRD_PARTY_NOTICES.md` (черновик) |
| F.5 | Аудит секретов в git | 🟡 | `scripts/audit_git_secrets.ps1` (эвристика) |

Локально (с `tests/`): `powershell -File scripts\ci_mandatory_checks.ps1` — дополнительно полный pytest.

## Волна E

| ID | Задача | Статус | Проверка |
|----|--------|--------|----------|
| E.1 | Воспроизводимый payload | ✅ | `build-installer-payload.ps1`, `payload.prev` |
| E.2 | Лёгкий venv + wheelhouse | ✅ | `smoke_installer_layout.py`, no torch |
| E.3 | WebView2 в Setup | ✅ | `fetch-installer-redist.ps1`, `Slysh.iss` |
| E.4 | SHA-256 обновлений | ✅ | `updates.py`, `smoke_updates_sha256.py` |
| E.5 | Upgrade ≠ first-run | ✅ | `IsAppUpgrade` / `.fresh-install` |
| E.6 | Чистые Win10/11 offline | 🟡 | локальный прогон `dist\payload` OK; VM — `e6-offline-vm-verify.ps1 -RequireWheelhouse` |
| E.7 | UI/engine split (§7.2) | 🟡 | probe fresh slot; `revert_active_engine_venv`; smoke slots |

Сборка: [`INSTALLER-BUILD.md`](INSTALLER-BUILD.md).

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
| `smoke_secrets_dpapi_migration.py` | D.5 |
| `smoke_ui_auth_session.py` | D.2 |
| `smoke_coordinator_queued_cancel.py` | C.3 |
| `smoke_asr_coordinator_queue.py` | C.1 |
| `smoke_asr_coordinator_remote_queue.py` | C.1 |
| `smoke_coordinator_cancel_running_pump.py` | C.3 |
| `smoke_slysh_bat_single_instance.py` | C.5 |
| `kill_slysh_orphans.ps1` | уборка после проверок |
| `ci_mandatory_checks.ps1` | волна F (JS, CSS, ci/*, smokes, опц. pytest) |
| `check_payload_sanity.py` | E.3 (после payload) |
| `smoke_updates_sha256.py` | E.4 |
| `e6-offline-vm-verify.ps1` | E.6 |
| `smoke_runtime_env_slots.py` | E.7 |

---

## Уборка процессов после проверок

```powershell
powershell -File scripts\kill_slysh_orphans.ps1 -WhatIf   # только список
powershell -File scripts\kill_slysh_orphans.ps1 -Force    # завершить без вопроса
```

## Правило обновления

После каждой итерации: строки здесь + `wiki/log.md`.
