@echo off
chcp 65001 >nul 2>&1
title AGI Cognitive Assistant
cd /d "%~dp0"

:: Find Python command
set "PYTHON_CMD="
where python >nul 2>&1 && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
    where python3 >nul 2>&1 && set "PYTHON_CMD=python3"
)
if not defined PYTHON_CMD (
    where py >nul 2>&1 && set "PYTHON_CMD=py"
)

if not defined PYTHON_CMD (
    echo.
    echo [ERROR] Python is not installed or not in PATH.
    echo.
    echo Please run install.bat first, or install Python from:
    echo   https://www.python.org/downloads/
    echo.
    echo IMPORTANT: Check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: Check if PyQt6 is available
%PYTHON_CMD% -c "import PyQt6" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] PyQt6 is not installed.
    echo.
    echo Please run install.bat first to install dependencies.
    echo.
    pause
    exit /b 1
)

:: Launch the app
%PYTHON_CMD% main.py %*
if errorlevel 1 (
    echo.
    echo [ERROR] Application exited with errors.
    echo Check the console output above for details.
    echo.
    pause
)
