@echo off
title AI Writing Tools Launcher
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        echo Make sure Python 3.10+ is installed and in PATH.
        pause
        exit /b 1
    )
    echo Installing dependencies...
    venv\Scripts\pip.exe install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install dependencies.
        pause
        exit /b 1
    )
    echo.
)

start "" venv\Scripts\pythonw.exe main.py
