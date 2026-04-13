@echo off
chcp 65001 >nul 2>&1
title SimLife

echo.
echo  ==================================
echo         SimLife - Life Sim
echo  ==================================
echo.

cd /d "%~dp0\.."

where python >nul 2>&1 && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
    where python3 >nul 2>&1 && set "PYTHON_CMD=python3"
)
if not defined PYTHON_CMD (
    where py >nul 2>&1 && set "PYTHON_CMD=py"
)
if not defined PYTHON_CMD (
    echo [ERROR] Python not found
    pause
    exit /b 1
)

echo [SimLife] Starting on port 87659...
echo [SimLife] Browser will open http://127.0.0.1:87659
echo.
echo Press Ctrl+C to stop
echo.

%PYTHON_CMD% -m simlife.backend.main --port 8769
pause
