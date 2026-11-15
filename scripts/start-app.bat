@echo off
rem Double-click to start everything: the API, the worker and the website.
rem Three windows open. Keep them open. Close them to stop the app.
cd /d "%~dp0.."
if not exist "backend\.venv\Scripts\python.exe" (
  echo.
  echo The app is not set up on this computer yet.
  echo Set it up once first: right-click scripts\dev-backend.ps1 and choose "Run with PowerShell".
  echo.
  pause
  exit /b 1
)
if not exist "frontend\node_modules" (
  echo.
  echo The website is not set up on this computer yet.
  echo Set it up once first: right-click scripts\dev-frontend.ps1 and choose "Run with PowerShell".
  echo.
  pause
  exit /b 1
)
start "Appointment - API" /d "%cd%\backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"
start "Appointment - worker" /d "%cd%\backend" cmd /k ".venv\Scripts\python.exe -m app.workers.runner --interval 20"
start "Appointment - website" /d "%cd%\frontend" cmd /k "npm run dev"
echo.
echo  Starting... the app opens in your browser in a few seconds.
echo  Keep the three new windows open. Close them to stop the app.
timeout /t 12 /nobreak >nul
start "" http://localhost:3000
