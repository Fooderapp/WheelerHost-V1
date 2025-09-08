@echo off
setlocal
cd /d "%~dp0"

if not exist .venv (
  py -3 -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements-win.txt

rem Ensure ViGEmBridge.exe exists next to this script or in ViGEmBridge\bin\Release\net8.0\
rem Alternatively install vJoy + pyvjoy for fallback.

python wheeler_main.py

endlocal

