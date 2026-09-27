# Slysh.exe launcher

GUI launcher without a console window. Sets the same environment as `Slysh.bat` and runs:

`.venv\Scripts\pythonw.exe -m slysh.app`

## Rebuild prebuilt (maintainer)

Requires **Visual Studio Build Tools** (Desktop development with C++).

From **x64 Native Tools Command Prompt**:

```bat
cd /d F:\ProjectsAI\Slysh-prod\launcher
cl /nologo /utf-8 /O2 /W4 Slysh.c /Fe:..\installer\prebuilt\Slysh.exe /link /SUBSYSTEM:WINDOWS shlwapi.lib user32.lib shell32.lib gdi32.lib dwmapi.lib comctl32.lib
```

Copy result to `installer/prebuilt/Slysh.exe` (path above). Commit the binary when launcher logic changes.

Payload build copies `installer/prebuilt/Slysh.exe` → `dist/payload/Slysh.exe`.

## Environment

Before starting Python, the launcher sets (same as `Slysh.bat`, plus UI catalog path):

- `SLYSH_INSTALL_ROOT` — folder containing `Slysh.exe`
- `GIGAAM_MODEL_ROOT` and **`GIGAAM_PROJECT_MODELS`** — `{install}\models` (overrides dev `GIGAAM_PROJECT_MODELS` from the user profile)
- **`UV_PYTHON_INSTALL_DIR`** — `{install}\runtime\python` (bundled CPython for uv; not `%AppData%\Roaming\uv`)
- `HF_HOME`, `HUGGINGFACE_HUB_CACHE`, `PATH` (`bin\`)

If `.venv` is missing, broken (wrong `pyvenv.cfg` `home`), or `pythonw` fails a probe, the launcher runs **`bin\uv.exe sync`** once; on failure it removes `.venv` and retries. Repair details go to `{install}\launch-last-error.txt` (`venv repair: uv sync …`).

Source must be compiled with **`/utf-8`** so Russian `MessageBoxW` strings are correct.

On non-zero exit from `pythonw`, the launcher writes `{install}\launch-last-error.txt` and shows the exit code plus `%LOCALAPPDATA%\Slysh\logs` (including **`startup-crash.log`** from Python). Dev env vars (`PYTHONPATH`, `PYWEBVIEW_GUI`, `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS`, …) are cleared before spawn.
