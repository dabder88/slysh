@echo off
setlocal
title Slysh

rem Broken NO_PROXY values like '::1/128' break huggingface_hub on Windows.
set "NO_PROXY="
set "no_proxy="

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "PYTHONPATH="
set "PYTHONHOME="
set "UV_PROJECT="
set "UV_WORKING_DIRECTORY="
set "PYWEBVIEW_GUI="
set "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS="
set "SLYSH_INSTALL_ROOT=%ROOT%"
set "GIGAAM_MODEL_ROOT=%ROOT%\models"
set "GIGAAM_PROJECT_MODELS=%ROOT%\models"
set "HF_HOME=%ROOT%\models\huggingface"
set "HUGGINGFACE_HUB_CACHE=%ROOT%\models\huggingface\hub"
set "GIGAAM_DIARIZATION_PATH="
set "UV_PYTHON_INSTALL_DIR=%ROOT%\runtime\python"
set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
set "PATH=%ROOT%\bin;%PATH%"

cd /d "%ROOT%" || (
    echo Не найдена папка %ROOT%
    pause
    exit /b 1
)

if not exist "%PYTHON%" goto :ensure_venv
"%PYTHON%" -c "import sys" >nul 2>&1
if errorlevel 1 goto :ensure_venv
goto :start

:ensure_venv
if exist "%ROOT%\bin\uv.exe" (
    "%ROOT%\bin\uv.exe" sync
) else (
    where uv >nul 2>&1
    if errorlevel 1 (
        echo Не найден uv. Установите: https://docs.astral.sh/uv/getting-started/installation/
        echo Также нужен ffmpeg в PATH.
        pause
        exit /b 1
    )
    echo Первый запуск: ставлю интерфейс. Пакеты расшифровки ^(torch, GigaAM^) — в окне после согласия.
    uv sync
)
if errorlevel 1 (
    echo Не удалось поставить окружение.
    pause
    exit /b 1
)
if not exist "%PYTHON%" (
    echo Не найден %PYTHON% после uv sync.
    pause
    exit /b 1
)

set "GIGAAM_UI_AUTH=1"
set "GIGAAM_LOOPBACK_STRICT=1"
set "SLYSH_DISABLE_OPENAPI=1"

:start
if exist "%ROOT%\Slysh.exe" (
    start "" "%ROOT%\Slysh.exe"
    exit /b 0
)
echo Запуск Slysh...
echo Кэш модели: %GIGAAM_MODEL_ROOT%
"%PYTHON%" -m slysh.app
if errorlevel 1 pause
endlocal
