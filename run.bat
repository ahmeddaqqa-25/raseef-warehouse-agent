@echo off
setlocal
cd /d "%~dp0"
title Raseef - Warehouse SQL Agent

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY (
  echo Python was not found. Install Python 3.10 - 3.13 from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" in the installer, then run this file again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating virtual environment...
  %PY% -m venv .venv || (echo Could not create the virtual environment. & pause & exit /b 1)
)
call ".venv\Scripts\activate.bat"

if not exist ".venv\.deps_ok" (
  echo [2/3] Installing packages, first run only, about 1-2 minutes...
  python -m pip install --quiet --upgrade pip
  python -m pip install --quiet -r requirements.txt || (echo Install failed. Check your internet connection. & pause & exit /b 1)
  echo ok> ".venv\.deps_ok"
)

if not exist ".env" copy ".env.example" ".env" >nul
if not exist "data\warehouse.db" (
  echo [3/3] Generating demo warehouse data...
  python data\generate_data.py
)

echo.
echo  Raseef is starting at http://127.0.0.1:8000  -  close this window to stop it.
echo.
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:8000"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
