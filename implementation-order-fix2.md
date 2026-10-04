# Порядок реализации plan-fix-2 (волны G и H)

**Статусы:** [`implementation-status-fix2.md`](implementation-status-fix2.md) (обновлять после каждой итерации).

**Источники:** [`plan-fix-2.md`](plan-fix-2.md), [`implementation-order.md`](implementation-order.md), [`implementation-status.md`](implementation-status.md), [`PRODUCT_OUT_OF_SCOPE.md`](PRODUCT_OUT_OF_SCOPE.md).

**Базовый коммит аудита:** `2f19be8`. Редактор: превью Правка/Просмотр и GET после save — **не** закрывают R02 (гонка A→B).

### Правила

- Рабочая копия: `F:\ProjectsAI\Slysh-prod-GPT`. Для подтверждённого дефекта — сначала падающий тест.
- Тесты: `PYTHONPATH=src`, изолированный `GIGAAM_DESKTOP_HOME`, без пользовательских данных и платных API.
- Не запускать `uv sync` в полном окружении с extras.
- После `web/` или `src/slysh/` — пересборка Setup (AGENTS.md). Запись в [`wiki/log.md`](wiki/log.md).

### Вне scope

| ID | Решение |
|----|---------|
| **R08** | Отказ владельца: оставляем reveal ключей в GET для авторизованной UI-сессии (`provider_reveal.py`). |
| **R09–R14, полная R15** | Волна **H** — после закрытия G. |

---

## Сводка волн

| Волна | Фокус | Ориентир | Блокирует |
|-------|--------|----------|-----------|
| **G** | Потеря данных, хвост аудио, coordinator диаризации, auth/secrets, пакеты | 1–2 нед. | Стабильный prod для редактор/ASR/пакетов |
| **H** | Offline Setup, RAM/timeouts, updates, VM/E2E | 2–4+ нед. | Публичный offline-релиз |

---

## Волна G — порядок G1 → G9

### G1 — R01: диаризация не откатывает сохранённый текст

- **Файлы:** [`src/slysh/speakers.py`](src/slysh/speakers.py), [`src/slysh/api.py`](src/slysh/api.py), [`tests/test_speakers_cancel.py`](tests/test_speakers_cancel.py).
- **Суть:** `base_revision` при старте; успех — merge speaker labels в **текущие** сегменты с `expected_revision`; при ошибке/отмене **не** `replace_segments(snapshot)`, если revision изменилась.
- **Тесты:** конкурентное сохранение во время диаризации; отмена без потери USER EDIT.
- **Зависимости:** нет.

### G2 — R02: ответ save только для своего job/черновика

- **Файлы:** [`web/js/legacy.js`](web/js/legacy.js), [`web/js/editor.js`](web/js/editor.js), bump `?v=` в [`web/index.html`](web/index.html).
- **Суть:** `saveToken` (jobId, draftGeneration, revision); UI apply только при совпадении; store upsert всегда.
- **Тесты:** pytest/ручной сценарий; при возможности — unit guard.
- **Зависимости:** нет (параллельно с G5).

### G3 — R04: короткий речевой хвост

- **Файлы:** [`src/slysh/chunking.py`](src/slysh/chunking.py), [`tests/test_chunking.py`](tests/test_chunking.py).
- **Суть:** не отбрасывать непустой остаток &lt; 1 с; pad только на вход модели при необходимости.
- **Зависимости:** нет.

### G4 — R03: диаризация в ASR coordinator

- **Файлы:** [`src/slysh/api.py`](src/slysh/api.py), [`src/slysh/batch_runner.py`](src/slysh/batch_runner.py), [`src/slysh/asr_coordinator.py`](src/slysh/asr_coordinator.py).
- **Суть:** `begin_local_wait` / `end_local` вокруг `assign_speakers`; `engine_cancel` при отмене спикеров только если job держит local slot.
- **Тесты:** pytest coordinator + smoke при необходимости.
- **Зависимости:** G1.

### G5 — R12: single-instance per data dir

- **Файлы:** [`src/slysh/single_instance.py`](src/slysh/single_instance.py), [`tests/test_single_instance.py`](tests/test_single_instance.py).
- **Суть:** имя mutex из хеша нормализованного `app_dir`.
- **Зависимости:** нет.

### G6 — R06: auth без обхода по `.json`

- **Файлы:** [`src/slysh/local_auth.py`](src/slysh/local_auth.py), тест в `tests/`.
- **Суть:** статические расширения только GET/HEAD и не для `/api/*`.
- **Зависимости:** нет.

### G7 — R07: секреты не в `.bak`

- **Файлы:** [`src/slysh/providers.py`](src/slysh/providers.py), [`src/slysh/settings_store.py`](src/slysh/settings_store.py), [`tests/test_secrets_dpapi_migration.py`](tests/test_secrets_dpapi_migration.py).
- **Суть:** после миграции DPAPI перезаписать `.bak` очищенным `settings.json`.
- **Зависимости:** нет.

### G8 — R05: обязательные стадии пакета

- **Файлы:** [`src/slysh/batch_runner.py`](src/slysh/batch_runner.py).
- **Суть:** ошибка speakers/export → `failed`, `on_error=stop`; не увеличивать `done` без успеха стадий.
- **Тесты:** расширить/добавить batch smoke.
- **Зависимости:** G4 для speakers в пакете (желательно).

### G9 — R15 (subset): регрессии проверок

- **Файлы:** [`scripts/smoke_cloud_batch_route.py`](scripts/smoke_cloud_batch_route.py), [`scripts/ci_mandatory_checks.ps1`](scripts/ci_mandatory_checks.ps1).
- **Суть:** заглушка `complete(**kwargs)`; новые smokes в mandatory по мере появления.
- **Зависимости:** G1–G8.

---

## Волна H (чеклист, детали в plan-fix-2 §4–8)

Порядок: **H1 (R11)** → **H2 (R13–R14)** → **H3 (R10)** → **H4 (R09)** → **H5 (R15)**.

### H1 — R11: таймауты UI/engine (коммит `3bede01`)

- **Файлы:** `app.py` (ожидание uvicorn ≤30 с), `engine_client.py` (connect 5 с, control 10 с, transcribe отдельно).
- **Тесты:** `test_engine_client_timeout.py`.
- **Дальше:** watchdog прогресса ASR (env), join engine при выходе — отдельная итерация.

| Rxx | Кратко |
|-----|--------|
| R09 | Offline bootstrap, wheelhouse, WebView2 full runtime (E.6) |
| R10 | Streaming decode, bounded RAM live |
| R11 | Engine/UI timeouts — см. H1 |
| R13 | Updates: operation id, re-hash перед apply — `updates.py`, `test_updates_operation.py` |
| R14 | Payload staging smoke до promote, без fallback venv — `build-installer-payload.ps1` |
| R15 | VM matrix, 10+ min devices, WebView E2E |

---

## Связь plan-fix-2 → волна

| Rxx | Волна | Примечание |
|-----|-------|------------|
| R01–R07, R12, R05 | G | |
| R08 | — | Отказ |
| R09–R14, R15 | H | |
| B1 revision, A6 speakers key, C coordinator ASR, D auth base | 0–F | Не переделывать |

---

*Дата: 2026-10-04.*
