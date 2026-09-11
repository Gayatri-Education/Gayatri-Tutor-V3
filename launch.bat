@echo off
setlocal enabledelayedexpansion
title Gayatri AI — Desktop Learning Assistant
cd /d "%~dp0"

echo ============================================================
echo   GAYATRI AI - Desktop Learning Platform
echo ============================================================
echo.

REM ── 1. Locate Python Executable ──────────────────────────────
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    echo [OK] Virtual environment found: .venv
    goto :check_model
)

where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHON_EXE=python"
    echo [OK] System Python found
    goto :check_model
)

where py >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHON_EXE=py"
    echo [OK] Python launcher found
    goto :check_model
)

echo.
echo [ERROR] Python not found on your system!
echo Please install Python 3.10+ from https://www.python.org/downloads/
echo or run setup.bat to configure the environment.
echo.
pause
exit /b 1

:check_model
REM ── 2. Check Model Status ────────────────────────────────────
set "RUNTIME_MODEL=%LOCALAPPDATA%\GayatriAI\models\gayatri\gemma-2-2b-it-IQ3_M.gguf"
set "PROJECT_MODEL=%~dp0GayatriAI\models\gayatri\gemma-2-2b-it-IQ3_M.gguf"

if exist "%PROJECT_MODEL%" (
    echo [OK] Local AI Model detected: GayatriAI\models\gayatri
    goto :launch_app
)

if exist "%RUNTIME_MODEL%" (
    echo [OK] Local AI Model detected in AppData
    goto :launch_app
)

echo [INFO] Local AI Model not downloaded yet.
echo        Gayatri AI will launch in setup and cloud mode.
echo        You can download the local model with 1 click in:
echo        Settings -^> Local AI Model -^> Download Model
echo        or configure Cloud API keys in Settings.

:launch_app
REM ── 3. Launch Application ────────────────────────────────────
echo.
echo Starting Gayatri AI desktop application...
echo (Keep this window open or minimize it while using Gayatri AI)
echo.

"%PYTHON_EXE%" -m app.main
set "EXIT_CODE=%ERRORLEVEL%"

if %EXIT_CODE% neq 0 (
    echo.
    echo ============================================================
    echo [ERROR] Gayatri AI exited with code %EXIT_CODE%.
    echo Check log file at: GayatriAI\logs\gayatri.log
    echo ============================================================
    echo.
    pause
)
