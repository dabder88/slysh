# Порядок реализации plan-fix-3 (волна I)

**Статусы:** [`implementation-status-fix3.md`](implementation-status-fix3.md) — **обновляет агент** после каждой итерации Ix (не владелец).

**Источники:** [`plan-fix-3.md`](plan-fix-3.md), [`plan-fix-2.md`](plan-fix-2.md) §10, [`implementation-status-fix2.md`](implementation-status-fix2.md), [`PRODUCT_OUT_OF_SCOPE.md`](PRODUCT_OUT_OF_SCOPE.md).

**Базовый коммит аудита:** `6f8690d` (+ незакоммиченное дерево на момент проверки — см. plan-fix-3 §1). Волны G/H считаются закрытыми по коду в объёме fix2; fix3 — **дочистка** оставшихся дефектов.

### Правила

- Рабочая копия: `F:\ProjectsAI\Slysh-prod-GPT`. Для подтверждённого дефекта — сначала падающий тест.
- Тесты: `PYTHONPATH=src`, изолированный `GIGAAM_DESKTOP_HOME`, без пользовательских данных и платных API.
- Не запускать `uv sync` в полном окружении с extras.
- После `web/`, `src/slysh/`, `launcher/` или payload — пересборка Setup (AGENTS.md). Агент сам обновляет [`implementation-status-fix3.md`](implementation-status-fix3.md) и [`wiki/log.md`](wiki/log.md).
- Не расширять scope косметикой. Пункт не закрыт без наблюдаемого поведения (plan-fix-3 §2).

### Сохраняемые решения владельца (не возвращать в scope)

| Тема | Решение |
|------|---------|
| **R08** | Reveal ключей авторизованной UI-сессии — оставляем. |
| **R09** | Полный автономный WebView2 в Setup — **не** требуется. **Требуется** offline создание Python/UI-окружения из wheelhouse (F3-04). |
| **R10** | Memmap, temp PCM, cancel decode, bounded live — достаточно; полный pipe и многочасовой RAM — **не** gate (F3-07 в scope). |
| **R15** | Gate — subset pytest/smokes; VM / hardware / WebView E2E — вручную. |
| **Roadmap** | Подпись Setup, фоновое автообновление, все модели в `models/`, legal due diligence — [`PRODUCT_OUT_OF_SCOPE.md`](PRODUCT_OUT_OF_SCOPE.md). |

---

## Сводка волны I

| Волна | Фокус | Ориентир | Зависит от |
|-------|--------|----------|------------|
| **I** | 7 дефектов F3-01…F3-07 | 1–2 нед. | G/H (fix2); не ломать закрытые регрессии |

**Рекомендуемый порядок:** I1 → I2 → I3 → I4 → I5 → I6 → I7 → **I8** (CI + Setup). Одна причина — одна логически завершённая сдача с тестом.

---

## I1 — F3-01: атомарный снимок сегментов и ревизии (R01)

- **Файлы:** [`src/slysh/db.py`](src/slysh/db.py), [`src/slysh/speakers.py`](src/slysh/speakers.py), тесты диаризации.
- **Суть:** сегменты + revision под одной блокировкой/транзакцией; apply меток с проверкой структуры (ID, порядок, границы); text-only правки пользователя — merge меток в текущий текст; при конфликте — отказ без отката на OLD.
- **Тесты:** race-before-apply; text-only-during-model; structure-change; user-speaker-change; отмена/ошибка backend (см. plan-fix-3 §3).
- **Зависимости:** нет.

## I2 — F3-06: ревизия редактора per job / черновик (R02)

- **Файлы:** [`web/js/legacy.js`](web/js/legacy.js), [`web/js/editor.js`](web/js/editor.js), bump `?v=` в [`web/index.html`](web/index.html).
- **Суть:** `segmentsRevision` не глобальный для всех job; обновление revision **после** проверки `saveResponseAppliesToEditor`; 409 без тихого rebase чужого черновика.
- **Тесты:** отложенный save A при открытом B (revision 9 vs 2); out-of-order saves; правки во время запроса остаются dirty.
- **Зависимости:** нет (параллельно с I1 допустимо; приёмку A→B+speakers — после I1+I2).

## I3 — F3-02: короткий хвост live / meeting (R04)

- **Файлы:** [`src/slysh/live_buffer.py`](src/slysh/live_buffer.py), ветки pause/stop/finalize в API/live/meeting.
- **Суть:** `take_pending_tail` / `flush` отдают любой непустой остаток; второй `flush` — `None`; pad только на вход backend; таймкоды по фактической длине.
- **Тесты:** параметризация отсчётов; 20,5 / 40,5 с; finalize с заглушкой ASR на последнем коротком блоке.
- **Зависимости:** не ломать [`tests/test_chunking.py`](tests/test_chunking.py) (файловая ветка).

## I4 — F3-03: meeting overflow явно (R10)

- **Файлы:** [`src/slysh/meeting_capture.py`](src/slysh/meeting_capture.py), [`src/slysh/api.py`](src/slysh/api.py), [`src/slysh/audio_ingest.py`](src/slysh/audio_ingest.py).
- **Суть:** `LiveBufferOverflowError` из `session.push` → callback остановки; один раз; не completed; WAV и текст сохранены; повтор ASR из файла.
- **Тесты:** малый cap + медленная ASR-заглушка; сравнение WAV; регрессия пути диктофона.
- **Зависимости:** I3 желательно (общий live_buffer).

## I5 — F3-05: proxy password не в plaintext `.bak` (R07)

- **Файлы:** [`src/slysh/http_proxy.py`](src/slysh/http_proxy.py), [`src/slysh/settings_store.py`](src/slysh/settings_store.py), [`src/slysh/api.py`](src/slysh/api.py).
- **Суть:** согласованная миграция с провайдерами; DPAPI → очищенный primary + safe `.bak`; restore не возвращает plaintext.
- **Тесты:** расширить/добавить к [`tests/test_secrets_dpapi_migration.py`](tests/test_secrets_dpapi_migration.py) + proxy-only сценарии.
- **Зависимости:** нет.

## I6 — F3-07: жизненный цикл temp PCM (R10)

- **Файлы:** [`src/slysh/decode.py`](src/slysh/decode.py), потребители memmap/chunks.
- **Суть:** `pcm_path` удаляется при ошибке/отмене; memmap close перед unlink; явный контракт владения.
- **Тесты:** cancel ffmpeg; bad exit; memmap на Windows; цикл из десятков ошибок — ноль оставшихся `.f32le`.
- **Зависимости:** нет.

## I7 — F3-04: согласовать offline bootstrap и wheelhouse (R09)

- **Файлы:** [`src/slysh/offline_bootstrap.py`](src/slysh/offline_bootstrap.py), [`launcher/Slysh.c`](launcher/Slysh.c), [`Slysh.bat`](Slysh.bat), [`scripts/build-installer-payload.ps1`](scripts/build-installer-payload.ps1), тест bootstrap **с реальной установкой wheels**.
- **Суть:** pinned UI/runtime requirements без dev/engine; полный wheelhouse Win x64 / Py 3.12 (в т.ч. wheels для sdist вроде proxy_tools); `uv pip sync --no-index --find-links`; единый контракт launcher/bat/helper; нет тихого fallback в сеть.
- **Проверка:** временный каталог, пустой UV cache, запрет сети, путь с пробелами/кириллицей; отсутствующий wheel → явная ошибка (plan-fix-3 §6).
- **Зависимости:** последним среди фич — пересборка payload + Setup обязательна.

## I8 — Общая проверка и сдача (R15 subset)

- **Файлы:** [`scripts/run_plan_fix2_targeted_tests.ps1`](scripts/run_plan_fix2_targeted_tests.ps1) (расширить или `run_plan_fix3_targeted_tests.ps1`), [`scripts/ci_mandatory_checks.ps1`](scripts/ci_mandatory_checks.ps1).
- **Суть:** новые регрессии F3 в mandatory subset; полный pytest в изолированном home; JS syntax + поведенческие тесты редактора при наличии; `$LASTEXITCODE` в PowerShell.
- **Сборка:** `Slysh-Setup-ru.exe` / `Slysh-Setup-en.exe` — путь, LastWriteTime, SHA-256; соответствие src/web и payload.
- **Зависимости:** I1–I7.

---

## Связь plan-fix-3 → волна I

| F3-xx | Rxx | Ix | Приоритет |
|-------|-----|-----|-----------|
| F3-01 | R01 | I1 | P1 |
| F3-02 | R04 | I3 | P1 |
| F3-03 | R10 | I4 | P1 |
| F3-04 | R09 | I7 | P1 |
| F3-05 | R07 | I5 | P2 |
| F3-06 | R02 | I2 | P2 |
| F3-07 | R10 | I6 | P2 |

Детали формулировок и критерии приёмки — только в [`plan-fix-3.md`](plan-fix-3.md) §3–10.

---

*Дата: 2026-10-06.*
