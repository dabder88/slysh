# Статус plan-fix-2 (волна G / H)

Источники: [`plan-fix-2.md`](plan-fix-2.md), порядок — [`implementation-order-fix2.md`](implementation-order-fix2.md).

**Легенда:** ✅ готово · 🟡 частично · 🔵 в работе · ⬜ не начато · ⏭️ отложено / вне scope

**Baseline аудита:** `2f19be8`. **Последнее обновление:** 2026-10-05 (R15 fingerprint script + UI engine shutdown test).

---

## Сводка

| Блок | Статус | Комментарий |
|------|--------|-------------|
| **G** Критический минимум | ✅ | коммит `32ba4e8` |
| **H** Offline / масштаб / приёмка | 🟡 | Код + subset CI ✅; ручная матрица R15 — ниже |

---

## Волна G

| ID | Rxx | Задача | Статус | Smoke / тест |
|----|-----|--------|--------|----------------|
| G1 | R01 | Диаризация + revision | ✅ | `test_speakers_cancel.py` |
| G2 | R02 | Save race guard | ✅ | `editor.js` draft generation + `legacy.js` |
| G3 | R04 | Хвост &lt; 1 с | ✅ | `test_chunking.py` |
| G4 | R03 | Speakers в coordinator | ✅ | `api.py`, `batch_runner.py` |
| G5 | R12 | Mutex per app dir | ✅ | `test_single_instance.py` |
| G6 | R06 | Auth `.json` bypass | ✅ | `test_api_json_suffix_requires_ui_auth` |
| G7 | R07 | `.bak` без секретов | ✅ | `test_secrets_dpapi_migration.py` |
| G8 | R05 | Пакет: стадии ≠ успех | ✅ | `batch_runner.py` |
| G9 | R15 | Smokes / CI | ✅ | `smoke_cloud_batch_route.py` stub |

---

## Волна H

| ID | Rxx | Статус |
|----|-----|--------|
| H1 | R11 | ✅ `engine_watchdog`, `SLYSH_ENGINE_PROGRESS_STALL_S` (default 600s); chunk HTTP timeout = transcribe |
| H2 | R13–R14 | ✅ + redirect allowlist, download без Bearer |
| H3 | R10 | 🟡 memmap, cancel, `iter_pcm_chunk_windows`; ffmpeg pipe / 1h load — вручную |
| H4 | R09 | 🟡 UI venv/wheelhouse ✅; WebView2 standalone в Setup ⏭️ владелец |
| H5 | R15 | 🟡 `run_plan_fix2_targeted_tests` в `ci_mandatory_checks`; Setup `dist\Slysh-Setup.exe` 2026-10-05 10:56 |
| §5.1 | Gemini CLI | ✅ cwd + blocklist + pytest + `check_gemini_cli_prompt` |
| §5.2 | secrets_dpapi | ✅ lock + concurrent pytest; corrupt read → `SecretsStoreReadError` |
| §5.3 | ASR snapshot | ✅ start/resume/retranscribe API + batch `begin_file_transcription` |
| §5.4 | COM pytest | ✅ sessionfinish + `test_com_pytest_teardown` |

---

## Ручная приёмка (R15, не блокирует merge кода)

| Сценарий | Статус |
|----------|--------|
| VM E6 offline, журнал с SHA-256 Setup | ⬜ (`scripts\write_setup_acceptance_record.ps1`) |
| Микрофон / loopback / meeting ≥10 min | ⬜ |
| WebView E2E (настройки, медиа, экспорт) | ⬜ |
| Нагрузка R10 (1–3 h файл, замер RAM) | ⬜ |

---

## Не путать с волнами 0–F

| Тема | Статус в 0–F | plan-fix-2 |
|------|----------------|------------|
| Ревизия сегментов, 409 | B1 ✅ | G2 — async save guard |
| Превью Правка/Просмотр | 2f19be8 ✅ | дополняет G2 |
| Coordinator file ASR | C ✅ | G4 — диаризация в слот |
| R08 reveal ключей | — | ⏭️ отказ владельца |
| R09 WebView2 standalone (~200 МБ) | bootstrapper в Setup | ⏭️ не увеличиваем Setup; E6 offline WebView2 — N/A |

---

## Smokes (G / H5)

| Скрипт | Gx / H5 |
|--------|---------|
| `smoke_cloud_batch_route.py` | G9 ✅, CI mandatory |
| `run_plan_fix2_targeted_tests.ps1` | H5 subset G–H |

---

## Правило обновления

После каждого Gx/Hx: строки здесь + [`wiki/log.md`](wiki/log.md); при UI/backend — Setup.
