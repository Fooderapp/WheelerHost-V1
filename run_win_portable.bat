@echo off
setlocal
REM Portable launcher for Wheeler Host on Windows (with optional audio helper)

set VENV=.venv
if not exist %VENV% (
  echo Creating venv...
  python -m venv %VENV% || goto err
)
call %VENV%\Scripts\activate.bat || goto err
python -m pip install --upgrade pip || goto err
if exist requirements-win.txt (
  python -m pip install -r requirements-win.txt || goto err
)
REM Optional audio libs (harmless if already installed)
python -m pip install numpy sounddevice || rem optional

set WHEELER_AUDIO_HELPER=1
python wheeler_main.py
exit /b 0

:err
echo Launch failed. Ensure Python is installed and try again.
exit /b 1

