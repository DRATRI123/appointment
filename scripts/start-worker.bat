@echo off
rem Double-click to start the background worker (messages, reminders, clean-up).
rem Keep the window open while the clinic uses the app. Close the window to stop it.
title Appointment - worker
cd /d "%~dp0..\backend"
if not exist ".venv\Scripts\python.exe" (
  echo.
  echo The app is not set up on this computer yet.
  echo Set it up once first: right-click scripts\dev-backend.ps1 and choose "Run with PowerShell".
  echo.
  pause
  exit /b 1
)
echo.
echo  Worker is running. It sends messages and reminders every 20 seconds.
echo  Keep this window open. Close it to stop.
echo.
".venv\Scripts\python.exe" -m app.workers.runner --interval 20
echo.
echo The worker stopped.
pause
