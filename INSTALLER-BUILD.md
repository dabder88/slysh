# Сборка установщика Slysh (волна E)

Пользовательский артефакт: `dist\Slysh-Setup.exe` (не в git).

## Требования на машине сборки

- Windows x64
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`ISCC.exe`)
- `ffmpeg.exe` в `bin\ffmpeg.exe` (или в предыдущем `dist\payload\bin`)
- Собранный лаунчер: `installer\prebuilt\Slysh.exe` (`scripts\build-slysh-launcher.ps1`)
- Сеть для первой загрузки **uv** / **WebView2** bootstrapper (далее кэш в `installer\redist` и `dist\payload`)

## Цепочка

```powershell
powershell -File scripts\build-installer-payload.ps1
powershell -File scripts\build-slysh-setup.ps1
```

1. **Payload** (`dist\payload`): лёгкий `.venv` без torch, `wheelhouse` для offline repair UI, `runtime\python`, `bin\uv.exe`, `bin\ffmpeg.exe`, копии `src/`, `web/`, `Slysh.bat`, `Slysh.exe`.
2. Проверки: `smoke_installer_layout.py`, `check_payload_sanity.py`.
3. **Setup**: Inno `installer\Slysh.iss` + WebView2 из `installer\redist\` (скрипт `fetch-installer-redist.ps1`).

Предыдущий успешный payload сохраняется в `dist\payload.prev` до завершения сборки.

## Волна E — статус возможностей

| ID | Тема | Реализация |
|----|------|------------|
| E.1 | Воспроизводимый payload | staging `payload.build-*`, `payload.prev`, pin uv в `build-installer-payload.ps1` |
| E.2 | Без vendored torch / portable venv | `uv sync --no-editable`, wheelhouse, smoke layout |
| E.3 | WebView2 offline | `installer\redist\MicrosoftEdgeWebview2Setup.exe`, `[Run]` в `Slysh.iss` |
| E.4 | Обновления + SHA-256 | `updates.py`, `smoke_updates_sha256.py`; без digest — нет auto-install |
| E.5 | Upgrade vs first-run | `IsAppUpgrade` в `Slysh.iss` — `.fresh-install` только для новой установки |
| E.6 | Чистые Win10/11 | `scripts\e6-offline-vm-verify.ps1` на VM без сети после Setup |

## E.6 — чистая VM offline

На VM **без Python/uv/ffmpeg**, сеть отключена после копирования `Slysh-Setup.exe` (или payload):

```powershell
powershell -File scripts\e6-offline-vm-verify.ps1 -InstallRoot "$env:LOCALAPPDATA\Programs\Slysh" -RequireWheelhouse
```

Локальная проверка payload (не заменяет VM):

```powershell
powershell -File scripts\e6-offline-vm-verify.ps1 -InstallRoot dist\payload
```

## E.7 — UI / engine (fingerprint slots)

Установленная копия: лёгкий `.venv` (UI) + engine в `.venv-engine-<lock-sha256[:16]>`, активный слот в `runtime-env.json` (`active_engine_venv`, `previous_engine_venv`). Smoke: `scripts\smoke_runtime_env_slots.py`.

## Smokes после сборки

```powershell
.\.venv\Scripts\python.exe scripts\smoke_installer_layout.py
.\.venv\Scripts\python.exe scripts\check_payload_sanity.py
.\.venv\Scripts\python.exe scripts\smoke_updates_sha256.py
```

Подробный трекер: [`implementation-status.md`](implementation-status.md).
