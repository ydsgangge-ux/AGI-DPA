@echo off
chcp 65001 >nul 2>&1
title NewsAPI Installer

echo.
echo ========================================
echo   NewsAPI Python SDK Installer
echo ========================================
echo.
echo   NewsAPI - Global news data provider
echo   Free signup: https://newsapi.org/register
echo.

:: ---- Check Python ----
set "PYTHON_CMD="
where python >nul 2>&1 && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
    where python3 >nul 2>&1 && set "PYTHON_CMD=python3"
)
if not defined PYTHON_CMD (
    where py >nul 2>&1 && set "PYTHON_CMD=py"
)

if not defined PYTHON_CMD (
    echo [ERROR] Python not found. Please install Python 3.9+
    echo         https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [INFO] Using %PYTHON_CMD%
echo.

:: ---- Check if already installed ----
%PYTHON_CMD% -c "import newsapi" >nul 2>&1
if not errorlevel 1 (
    echo [OK] newsapi-python is already installed.
    echo.
    echo To configure API Key, fill in newsapi_key in App Settings.
    pause
    exit /b 0
)

:: ---- Install ----
echo [..] Installing newsapi-python...
echo.
%PYTHON_CMD% -m pip install newsapi-python

:: ---- Verify ----
%PYTHON_CMD% -c "import newsapi" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [FAILED] Installation failed. Check your network and retry:
    echo           %PYTHON_CMD% -m pip install newsapi-python
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Installation Complete!
echo ========================================
echo.
echo   Next step: Configure NewsAPI Key
echo   1. Visit https://newsapi.org/register (free signup)
echo   2. Fill in newsapi_key in AGI App Settings
echo   3. Or set env var: set NEWSAPI_KEY=your_key
echo.
echo   After configuration, news search will be available.
echo ========================================
echo.
pause
