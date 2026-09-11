@echo off
setlocal enabledelayedexpansion
title Gayatri AI — Desktop Learning Assistant
cd /d "%~dp0"

echo ============================================================
echo   GAYATRI AI - One-Click Desktop Launcher
echo ============================================================
echo.

REM ── 1. Locate Python Executable ──────────────────────────────
set "PYTHON_EXE="
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    echo [OK] Using virtual environment (.venv)
) else (
    where python >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_EXE=python"
        echo [OK] Using system Python
    ) else (
        where py >nul 2>&1
        if not errorlevel 1 (
            set "PYTHON_EXE=py"
            echo [OK] Using Python launcher (py)
        )
    )
)

if "%PYTHON_EXE%"=="" (
    echo.
    echo [ERROR] Python not found on your system!
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo or run setup.bat to set up the environment.
    echo.
    pause
    exit /b 1
)

REM ── 2. Check Model Status ────────────────────────────────────
set "RUNTIME_MODEL=%LOCALAPPDATA%\GayatriAI\models\gayatri\gemma-2-2b-it-IQ3_M.gguf"
set "PROJECT_MODEL=%~dp0GayatriAI\models\gayatri\gemma-2-2b-it-IQ3_M.gguf"

if exist "%PROJECT_MODEL%" (
    echo [OK] Local AI Model detected in project folder.
) else if exist "%RUNTIME_MODEL%" (
    echo [OK] Local AI Model detected in AppData runtime folder.
) else (
    echo [INFO] Local AI Model not detected yet.
    echo        Gayatri AI will launch in setup/cloud mode.
    echo        You can download the local model with 1 click in:
    echo        Settings -^> Local AI Model -^> Download Model
    echo        or configure Cloud API keys (Gemini, Anthropic, OpenAI).
)

REM ── 3. Launch Application ────────────────────────────────────
echo.
echo Launching Gayatri AI desktop application...
echo (You can minimize this window while Gayatri AI is running)
echo.

"%PYTHON_EXE%" -m app.main

if errorlevel 1 (
    echo.
    echo ============================================================
    echo [ERROR] Gayatri AI exited with an error code.
    echo Check log file at: GayatriAI\logs\gayatri.log
    echo ============================================================
    echo.
    pause
)
