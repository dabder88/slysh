@echo off
cd /d "%~dp0.."
if not exist "web\app.css" (
  echo [build-ui] web\app.css not found, building...
)
call npm run build:css
