# E.6 — чистая Windows offline (матрица приёмки)

Проверка установщика на **чистой** Win10/Win11 x64 **без** заранее установленных Python, uv и ffmpeg. Сеть отключается **после** копирования `Slysh-Setup.exe` на VM (или после распаковки payload для разработчика).

Связано: [`INSTALLER-BUILD.md`](../INSTALLER-BUILD.md), [`plan-fix.md`](../plan-fix.md) §7.1 и «Приёмка установщика».

## Что автоматизировано

Скрипт `scripts\e6-offline-vm-verify.ps1` проверяет layout установленной копии или `dist\payload`:

- бинарники: `Slysh.exe`, `Slysh.bat`, `bin\uv.exe`, `bin\ffmpeg.exe`, UI `.venv\Scripts\python.exe` / `pythonw.exe`;
- `pyproject.toml`, `uv.lock`, `src\slysh`, bundled `runtime\python`;
- `pyvenv.cfg` → `home` внутри каталога установки (не кэш uv на машине сборки);
- импорт `slysh` через `python` и `pythonw`, **отсутствие** `torch` в UI venv;
- при `-RequireWheelhouse`: не менее 10 wheels в `wheelhouse\`;
- наличие `licenses\THIRD-PARTY-NOTICES.md` в установке;
- опционально `-ProbeOfflineUiSync`: `uv sync --find-links wheelhouse --offline` (repair UI без PyPI).

Локально (не заменяет VM):

```powershell
powershell -File scripts\build-installer-payload.ps1
powershell -File scripts\e6-offline-vm-verify.ps1 -InstallRoot dist\payload -RequireWheelhouse
```

## Подготовка VM

| Шаг | Действие |
|-----|----------|
| 1 | Снапшот «чистая» Win10 22H2 или Win11 23H2+, x64, обычный пользователь (не обязательно админ после Setup) |
| 2 | Убедиться: нет Python в PATH, нет `uv`, нет `ffmpeg` в PATH |
| 3 | На машине сборки: `powershell -File scripts\write_setup_acceptance_record.ps1` → JSON в `dist\acceptance\`; скопировать Setup, JSON и `scripts\e6-offline-vm-verify.ps1` на VM |
| 4 | Установить Slysh (путь по сценарию — см. матрицу) |
| 5 | **Отключить сеть** (адаптер VM или «Airplane mode») |
| 6 | Запустить проверку (см. ниже) |
| 7 | Ручные пункты матрицы — отметить в журнале |

Каталог по умолчанию после Setup: `%LOCALAPPDATA%\Programs\Slysh`.

```powershell
powershell -ExecutionPolicy Bypass -File .\e6-offline-vm-verify.ps1 `
  -InstallRoot "$env:LOCALAPPDATA\Programs\Slysh" `
  -RequireWheelhouse `
  -ProbeOfflineUiSync
```

Опционально сохранить отчёт:

```powershell
... -ResultJson "$env:USERPROFILE\Desktop\e6-result.json"
```

## Матрица сценариев

Отмечайте **OK / FAIL / N/A** и дату. Один прогон может закрыть несколько строк, если путь и ОС совпадают.

| ID | ОС | Путь установки | Сеть | Авто `e6-offline-vm-verify` | Ручные проверки |
|----|-----|----------------|------|-----------------------------|-----------------|
| E6-W10-DEF | Win10 x64 | `%LOCALAPPDATA%\Programs\Slysh` | off после Setup | `-RequireWheelhouse` | Запуск `Slysh.exe` → окно UI; облачный режим без engine |
| E6-W11-DEF | Win11 x64 | то же | off | то же | то же |
| E6-SPACE | Win10 или 11 | `C:\Program Files\Slysh Test\` (пробелы) | off | то же | Первый запуск, модал пакетов «Позже», настройки |
| E6-CYR | Win10 или 11 | `C:\Пользователи\Тест\Slysh\` или профиль с кириллицей | off | то же | `Slysh.bat` из ярлыка |
| E6-ENGINE | любая | дефолт | off → **кратко on** для engine | после verify | Установка engine из UI; обрыв сети → повтор; отмена |
| E6-UPGRADE | любая | дефолт | off после upgrade | verify на новой версии | Сохранены БД/ключи; нет `.fresh-install` |
| E6-UNINSTALL | любая | дефолт | — | — | Удаление; нет зависших `engine_server` / `pythonw` Slysh |

### Ручной минимум после авто-проверки

1. Двойной клик **Slysh** — UI открывается без ошибки WebView2 (redist в Setup).
2. **Настройки** → облачный провайдер или «только облако» — расшифровка без локального torch.
3. При сценарии E6-ENGINE: после успешной установки пакетов — короткая локальная расшифровка файла (по желанию).

## Журнал прогонов

Владелец продукта ведёт таблицу (пример):

| Дата | Сценарий | Сборка Setup (LastWriteTime / версия) | Авто verify | Ручное | Примечание |
|------|----------|----------------------------------------|-------------|--------|------------|
| | E6-W11-DEF | | | | |

Шаблон JSON пишет `-ResultJson` (поля: `ok`, `install_root`, `wheelhouse_count`, `checks`).

## Ограничения

- Авто-скрипт **не** поднимает VM и **не** запускает Inno Setup.
- SHA-256 релиза покрывается E.4 (ручное обновление в приложении). Подпись Setup — вне плана ([`PRODUCT_OUT_OF_SCOPE.md`](../PRODUCT_OUT_OF_SCOPE.md)).
- Engine wheels **не** входят в базовый offline payload; тяжёлая установка требует сети или заранее заполненного engine venv.
- **WebView2:** в Setup — bootstrapper (~2 МБ), не standalone (~200 МБ). Сценарий «чистая VM без WebView2 и без сети» для окна UI **не** в целевом приёмочном scope (решение владельца); E6 проверяет offline **UI venv / wheelhouse**, при наличии runtime — ручной запуск UI.
