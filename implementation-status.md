# Статус реализации (живой трекер)

Источники: [`implementation-order.md`](implementation-order.md), [`plan-fix.md`](plan-fix.md).

**Легенда:** ✅ готово · 🟡 частично · 🔵 в работе / не в git · ⬜ не начато · ⏭️ отложено

**Последнее обновление:** 2026-10-02 — `PRODUCT_OUT_OF_SCOPE.md`; F ✅; план без подписи/автообнов/legal/models-mandatory.

---

## Сводка волн

| Волна | Фокус | Статус | Комментарий |
|-------|--------|--------|-------------|
| **0** | Основа тестов | ✅ | `tests/` в git; `pytest` в CI; [`TEST_BASELINE.md`](TEST_BASELINE.md) |
| **A** | Корректность | ✅ | A1–A11 + smokes; Gemini prompt test (A10) |
| **B** | Надёжность UX | 🟡 | B1–B3,B5,B4.2–B4.3 ✅; B4.4 manual ⏭️ |
| **C** | Job runtime | ✅ | C.1–C.5 smokes + coordinator pytest (локально) |
| **D** | Безопасность | ✅ | D.1–D.6 закрыты |
| **E** | Установщик | 🟡 | [`INSTALLER-BUILD.md`](INSTALLER-BUILD.md); E.1–E.5 в коде |
| **F** | CI / доки | ✅ | CI + `ci_mandatory_checks`; справочник лицензий в payload (не legal roadmap) |

---

## Следующий крупный этап (план агента)

**Активно:** волна **G** plan-fix-2 — [`implementation-order-fix2.md`](implementation-order-fix2.md) · [`implementation-status-fix2.md`](implementation-status-fix2.md) (R01–R07, R12, R05; R08 вне scope; R09+ → волна H).

| Блок | ID | Содержание |
|------|-----|------------|
| **1** | G | Критический минимум plan-fix-2 (данные, хвост, coordinator, auth/secrets) |
| **2** | E / H | E.6 VM offline; R09–R14 после G |
| **3** | — | Опционально: B.4.4 (10+ мин live manual) |

D.1–D.6 закрыты (таблица D). Волна **F** закрыта по пунктам F.1–F.5.

## Вне плана (не делаем)

См. [`PRODUCT_OUT_OF_SCOPE.md`](PRODUCT_OUT_OF_SCOPE.md): подпись Setup / SmartScreen, автообновление в фоне, юридический due diligence, обязательное скачивание всех весов в `models/`.

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
| F.4 | Сторонние лицензии (справочник) | ✅ | `THIRD_PARTY_NOTICES.md` → `licenses\` |
| F.6 | Лицензия Slysh (вариант A) | ✅ | `LICENSE`, EULA RU/EN, `Slysh-Setup.exe` + `Slysh-Setup-en.exe`; публичный repo ≠ OSS |
| F.5 | Аудит секретов в git | ✅ | `audit_git_secrets.ps1` в CI + `ci_mandatory_checks` |

`powershell -File scripts\ci_mandatory_checks.ps1` — smokes + полный `pytest tests`.

## Волна E

| ID | Задача | Статус | Проверка |
|----|--------|--------|----------|
| E.1 | Воспроизводимый payload | ✅ | `build-installer-payload.ps1`, `payload.prev` |
| E.2 | Лёгкий venv + wheelhouse | ✅ | `smoke_installer_layout.py`, no torch |
| E.3 | WebView2 в Setup | ✅ | `fetch-installer-redist.ps1`, `Slysh.iss` |
| E.4 | SHA-256 обновлений | ✅ | `updates.py`, `smoke_updates_sha256.py` |
| E.5 | Upgrade ≠ first-run | ✅ | `IsAppUpgrade` / `.fresh-install` |
| E.6 | Чистые Win10/11 offline | 🟡 | [`installer/E6-OFFLINE-VM.md`](installer/E6-OFFLINE-VM.md); verify + `-ProbeOfflineUiSync`; VM журнал — вручную |
| E.7 | UI/engine split (§7.2) | ✅ | repair API + UI; probe/revert/prune; smokes/pytest |

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
| `smoke_engine_slot_resync.py` | E.7 |

---

## Уборка процессов после проверок

```powershell
powershell -File scripts\kill_slysh_orphans.ps1 -WhatIf   # только список
powershell -File scripts\kill_slysh_orphans.ps1 -Force    # завершить без вопроса
```

## Правило обновления

После каждой итерации: строки здесь + `wiki/log.md`.
