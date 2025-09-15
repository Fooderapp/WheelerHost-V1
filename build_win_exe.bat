@echo off
setlocal
REM Build WindowsAudioHelper (NAudio WASAPI loopback) and WheelerHost.exe via PyInstaller

REM 1) Build the audio helper (requires .NET 8 SDK)
if exist WindowsAudioHelper\AudioHelper.csproj (
  echo Building WindowsAudioHelper...
  dotnet publish WindowsAudioHelper\AudioHelper.csproj -c Release -r win-x64 --self-contained true || goto err
) else (
  echo Skipping audio helper build (project not found)
)

REM 2) Ensure Python deps
python -m pip install --upgrade pip || goto err
if exist requirements-win.txt (
  python -m pip install -r requirements-win.txt || goto err
)
python -m pip install pyinstaller || goto err

REM 3) Bundle helper into the app folder
set HELPER=WindowsAudioHelper\bin\Release\net8.0\win-x64\publish\AudioHelper.exe
set ADDDATA=
if exist %HELPER% (
  set ADDDATA=--add-binary "%HELPER%;."
)

REM 4) Build WheelerHost.exe
echo Building WheelerHost.exe...
pyinstaller --noconfirm --noconsole %ADDDATA% --name WheelerHost wheeler_main.py || goto err

echo.
echo Build complete. See dist\WheelerHost\WheelerHost.exe
exit /b 0

:err
echo Build failed. See messages above.
exit /b 1

