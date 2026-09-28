@echo off
REM Universal installer for UAPorter (Windows)
echo [UAPorter] Setting up Python virtual environment...
python -m venv "%~dp0.venv"
call "%~dp0.venv\Scripts\pip.exe" install --quiet --upgrade pip
call "%~dp0.venv\Scripts\pip.exe" install --quiet -e "%~dp0"

echo [UAPorter] Installation complete!
echo [UAPorter] You can run: "%~dp0.venv\Scripts\uaporter.exe" --help
pause
