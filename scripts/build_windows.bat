@echo off
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Create venv and install deps first.
  exit /b 1
)
call .venv\Scripts\activate
pip install -r requirements.txt -r requirements-build.txt
python -m PyInstaller --noconfirm --clean steam_card_idle.spec
if errorlevel 1 exit /b 1

rem Intermediate EXE in build\ has no _internal — remove so it is not launched by mistake
if exist "build\steam_card_idle\SteamCardIdle.exe" del /f /q "build\steam_card_idle\SteamCardIdle.exe"

echo.
echo OK. Run this file:
echo   dist\SteamCardIdle\SteamCardIdle.exe
echo.
echo Zip the whole folder dist\SteamCardIdle\ for Releases.
explorer "dist\SteamCardIdle"
