# Статус plan-fix-3 (волна I)

Источники: [`plan-fix-3.md`](plan-fix-3.md), порядок — [`implementation-order-fix3.md`](implementation-order-fix3.md). Предыдущий цикл: [`implementation-status-fix2.md`](implementation-status-fix2.md).

**Легенда:** ✅ готово · 🟡 частично · 🔵 в работе · ⬜ не начато · ⏭️ отложено / вне scope

**Baseline аудита:** `6f8690d`. **Последнее обновление:** 2026-10-06 — **I1** ✅ (F3-01 атомарный snapshot диаризации).

---

## Сводка

| Блок | Статус | Комментарий |
|------|--------|-------------|
| **I** F3-01…F3-07 | 🔵 | I1 ✅; I2–I7 ⬜ |
| **I8** CI / Setup / отчёт | ⬜ | После закрытия I1–I7 |

Полный pytest на baseline аудита **не** выполнялся (plan-fix-3 §1). Статус «готово» здесь — только после тестов и поведенческой проверки по plan-fix-3 §10.

---

## Волна I

| Ix | F3 | Rxx | Задача | P | Статус | Тест / примечание |
|----|-----|-----|--------|---|--------|-------------------|
| I1 | F3-01 | R01 | Атомарный snapshot сегментов + apply диаризации | P1 | ✅ | `get_segments_snapshot`, `test_speakers_cancel.py` (+3 race/structure) |
| I2 | F3-06 | R02 | `segmentsRevision` per job, save A не трогает B | P2 | ⬜ | `legacy.js` / `editor.js` |
| I3 | F3-02 | R04 | Хвост &lt; 1 с в live/meeting | P1 | ⬜ | `live_buffer.py`; файловая ветка уже ✅ |
| I4 | F3-03 | R10 | Meeting overflow → stop + ошибка | P1 | ⬜ | vs диктофон `LiveBufferOverflowError` |
| I5 | F3-05 | R07 | Proxy password не в `.bak` | P2 | ⬜ | дополнение G7 |
| I6 | F3-07 | R10 | Очистка temp PCM при ошибке/отмене | P2 | ⬜ | `decode.py` finally |
| I7 | F3-04 | R09 | Offline wheelhouse + единый bootstrap | P1 | ⬜ | payload + реальный no-network test |
| I8 | — | R15 | Subset CI, full pytest, Setup SHA-256 | — | ⬜ | расширить `run_plan_fix2_targeted_tests` или преемник |

---

## Вне scope fix3 (не считать незакрытыми F3)

| Тема | Решение |
|------|---------|
| R08 reveal в API | ⏭️ владелец |
| WebView2 standalone ~200 МБ | ⏭️ plan-fix-2 §10; F3-04 не требует окно без WebView2 |
| VM E6 журнал, ≥10 min mic/loopback, WebView E2E, 1–3 h RAM | ⏭️ ручная приёмка, не gate I8 |
| Подпись Setup, автообновление в фоне, все модели, legal audit | ⏭️ [`PRODUCT_OUT_OF_SCOPE.md`](PRODUCT_OUT_OF_SCOPE.md) |

---

## Связь с plan-fix-2 (не переделывать без причины)

| fix2 | fix3 |
|------|------|
| G1 R01 cancel/snapshot | I1 углубляет TOCTOU read/apply |
| G2 R02 draft generation + apply guard | I2 глобальная `segmentsRevision` |
| G3 R04 `chunking.py` | I3 `live_buffer` / meeting-live |
| H4 R09 wheelhouse флаги | I7 содержимое wheelhouse + sync контракт |
| H3 R10 memmap/cancel | I6 утечка PCM; I4 overflow meeting |

---

## Ручная приёмка (как в fix2, не блокирует I8)

| Сценарий | Статус |
|----------|--------|
| VM E6 offline UI venv (без требования WebView2 без сети) | ⬜ |
| Микрофон / loopback / meeting ≥10 min | ⬜ |
| WebView E2E | ⬜ |
| Нагрузка 1–3 h / RAM | ⬜ |

---

## Правило обновления (обязанность агента)

**Владельцу не поручать ручное ведение этого файла.** После каждой завершённой итерации по plan-fix-3 (закрыт Ix или существенный прогресс) **агент Cursor** обязан:

1. Обновить таблицу «Волна I», сводку и дату в шапке (`implementation-status-fix3.md`).
2. Дописать факт в [`wiki/log.md`](wiki/log.md).
3. При изменениях `web/`, `src/slysh/`, `launcher/` или payload — пересобрать Setup и указать в логе/статусе I8 пути, LastWriteTime и SHA-256 (`Slysh-Setup-ru.exe`, `Slysh-Setup-en.exe`).

Статус ✅ — только с указанием теста/smoke и результата прогона. Не закрывать пункты по одному только добавлению кода без проверки.
