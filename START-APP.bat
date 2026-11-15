@echo off
rem ============================================================================
rem  START-APP.bat  -  double-click to run the appointment app on this computer.
rem
rem  First time: installs everything (a few minutes, needs internet).
rem  Every time: updates the database, then opens 3 windows (API, worker, website)
rem  and the app in your browser at http://localhost:3000
rem  To stop the app: close the 3 windows.
rem ============================================================================
setlocal
title Appointment app - starting
cd /d "%~dp0"

echo.
echo  =============================================
echo    Appointment app is starting, please wait...
echo  =============================================
echo.

rem ---- 1. Python and Node.js must be installed --------------------------------
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto :no_python
where npm >nul 2>nul || goto :no_node

rem ---- 2. Backend: first time only --------------------------------------------
if exist "backend\.venv\Scripts\python.exe" goto :backend_ready
echo  [1/4] First start: installing the backend. This happens only once...
%PY% -m venv "backend\.venv" || goto :failed
"backend\.venv\Scripts\python.exe" -m pip install --upgrade pip
"backend\.venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt" || goto :failed
:backend_ready
if not exist "backend\.env" copy /y ".env.development.example" "backend\.env" >nul

rem ---- 3. Database: apply updates (safe to run every time) ---------------------
echo  [2/4] Updating the database...
pushd backend
".venv\Scripts\python.exe" -m alembic upgrade head || (popd & goto :failed)
".venv\Scripts\python.exe" ..\scripts\seed.py >nul || (popd & goto :failed)
popd

rem ---- 4. Website: first time only --------------------------------------------
if exist "frontend\node_modules" goto :frontend_ready
echo  [3/4] First start: installing the website. This happens only once...
pushd frontend
call npm install || (popd & goto :failed)
popd
:frontend_ready

rem ---- 5. Start the 3 parts, each in its own window ----------------------------
echo  [4/4] Starting the API, the worker and the website...
start "Appointment - API (keep open)" /d "%~dp0backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"
start "Appointment - worker (keep open)" /d "%~dp0backend" cmd /k ".venv\Scripts\python.exe -m app.workers.runner --interval 20"
start "Appointment - website (keep open)" /d "%~dp0frontend" cmd /k "npm run dev"

echo.
echo  Opening http://localhost:3000 in your browser in a few seconds...
timeout /t 15 /nobreak >nul
start "" "http://localhost:3000"
echo.
echo  The app is running. Keep the 3 new windows open. Close them to stop the app.
timeout /t 10 >nul
exit /b 0

:no_python
echo  Python is not installed.
echo  Install Python 3.11 or newer from https://www.python.org/downloads/windows/
echo  (tick "Add python.exe to PATH"), then double-click this file again.
pause
exit /b 1

:no_node
echo  Node.js is not installed.
echo  Install Node.js 22 LTS from https://nodejs.org/ then double-click this file again.
pause
exit /b 1

:failed
echo.
echo  Something went wrong above. Take a photo of this window and send it.
pause
exit /b 1
