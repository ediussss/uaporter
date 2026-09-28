@echo off
REM Self-bootstrapping launcher for UAPorter on Windows
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo [UAPorter] First run detected: Initializing environment and dependencies...
    python -m venv "%VENV_DIR%"
    "%VENV_DIR%\Scripts\pip.exe" install --quiet --upgrade pip
    "%VENV_DIR%\Scripts\pip.exe" install --quiet -e "%SCRIPT_DIR%"
    echo [UAPorter] Ready!
)

"%VENV_PYTHON%" -m uaporter.cli %*
