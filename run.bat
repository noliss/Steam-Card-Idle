@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m steam_card_idle %*
) else (
  python -m steam_card_idle %*
)
if errorlevel 1 pause
