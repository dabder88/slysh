# Статус plan-fix-2 (волна G / H)

Источники: [`plan-fix-2.md`](plan-fix-2.md), порядок — [`implementation-order-fix2.md`](implementation-order-fix2.md).

**Легенда:** ✅ готово · 🟡 частично · 🔵 в работе · ⬜ не начато · ⏭️ отложено / вне scope

**Baseline аудита:** `2f19be8`. **Последнее обновление:** 2026-10-04 (H3 `b4d6bda`, H4 R09 🟡).

---

## Сводка

| Блок | Статус | Комментарий |
|------|--------|-------------|
| **G** Критический минимум | ✅ | коммит `32ba4e8` |
| **H** Offline / масштаб / приёмка | 🔵 | H4 R09: launcher offline sync 🟡 |

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
| H1 | R11 | ✅ (watchdog/join — 🟡) |
| H4 | R09 | 🟡 (offline UI sync ✅; WebView2 standalone в Setup при `fetch` + url) |
| H2 | R13–R14 | ✅ `a418af3` |
| H3 | R10 | ✅ |
| H5 | R15 (полная) | ⬜ |

---

## Не путать с волнами 0–F

| Тема | Статус в 0–F | plan-fix-2 |
|------|----------------|------------|
| Ревизия сегментов, 409 | B1 ✅ | G2 — async save guard |
| Превью Правка/Просмотр | 2f19be8 ✅ | дополняет G2 |
| Coordinator file ASR | C ✅ | G4 — диаризация в слот |
| R08 reveal ключей | — | ⏭️ отказ владельца |

---

## Smokes (G)

| Скрипт | Gx |
|--------|-----|
| `smoke_cloud_batch_route.py` | G9 ✅ |

---

## Правило обновления

После каждого Gx/Hx: строки здесь + [`wiki/log.md`](wiki/log.md); при UI/backend — Setup.
