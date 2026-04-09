@echo off
chcp 65001 >nul 2>&1
title AGI Installer

echo.
echo ========================================
echo   AGI Cognitive Assistant Installer
echo ========================================
echo.

:: ---- 1. Check Python ----
echo [1/4] Checking Python...

set "PYTHON_CMD="

:: Try python, python3, py
where python >nul 2>&1 && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
    where python3 >nul 2>&1 && set "PYTHON_CMD=python3"
)
if not defined PYTHON_CMD (
    where py >nul 2>&1 && set "PYTHON_CMD=py"
)

if not defined PYTHON_CMD (
    echo.
    echo [ERROR] Python is NOT installed or not in PATH.
    echo.
    echo Please install Python 3.10+:
    echo   Download: https://www.python.org/downloads/
    echo.
    echo IMPORTANT: During installation, check the box:
    echo   [x] Add Python to PATH
    echo.
    echo After installing Python, run this script again.
    echo.
    pause
    exit /b 1
)

:: Check version
for /f "tokens=2 delims= " %%v in ('%PYTHON_CMD% --version 2^>^&1') do set PYVER=%%v
echo   Found Python %PYVER%

:: Check major version >= 3.10
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    if %%a LSS 3 (
        echo [ERROR] Python 3.10+ required, found %PYVER%
        pause
        exit /b 1
    )
    if %%a EQU 3 if %%b LSS 10 (
        echo [ERROR] Python 3.10+ required, found %PYVER%
        pause
        exit /b 1
    )
)

:: ---- 2. Upgrade pip ----
echo.
echo [2/4] Upgrading pip...
%PYTHON_CMD% -m pip install --upgrade pip -q 2>nul
if errorlevel 1 (
    echo [WARN] pip upgrade failed, will try to continue...
)

:: ---- 3. Install dependencies ----
echo.
echo [3/4] Installing dependencies from requirements.txt...
echo   (This may take a few minutes on first run)
echo.

%PYTHON_CMD% -m pip install -r "%~dp0requirements.txt" --quiet
if errorlevel 1 (
    echo.
    echo [WARN] Some core dependencies failed.
    echo         Retrying with verbose output...
    echo.
    %PYTHON_CMD% -m pip install -r "%~dp0requirements.txt"
    if errorlevel 1 (
        echo.
        echo [ERROR] Dependencies installation failed.
        echo         Try manually:
        echo           %PYTHON_CMD% -m pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
)

echo   [OK] Core dependencies installed.

:: ---- 3.5 Install optional packages (non-fatal) ----
echo.
echo   Checking optional packages...
echo.

set "OFFICE_OK=1"
set "TTS_OK=1"

:: edge-tts
%PYTHON_CMD% -c "import edge_tts" >nul 2>&1
if errorlevel 1 (
    echo   [..] edge-tts        - installing...
    %PYTHON_CMD% -m pip install edge-tts --quiet 2>nul
    %PYTHON_CMD% -c "import edge_tts" >nul 2>&1
    if errorlevel 1 (
        echo   [!!] edge-tts        - FAILED
        set "TTS_OK=0"
    ) else (
        echo   [OK] edge-tts        - installed
    )
) else (
    echo   [OK] edge-tts        - already installed
)

:: python-docx
%PYTHON_CMD% -c "import docx" >nul 2>&1
if errorlevel 1 (
    echo   [..] python-docx    - installing...
    %PYTHON_CMD% -m pip install python-docx --quiet 2>nul
    %PYTHON_CMD% -c "import docx" >nul 2>&1
    if errorlevel 1 (
        echo   [!!] python-docx    - FAILED
        set "OFFICE_OK=0"
    ) else (
        echo   [OK] python-docx    - installed
    )
) else (
    echo   [OK] python-docx    - already installed
)

:: openpyxl
%PYTHON_CMD% -c "import openpyxl" >nul 2>&1
if errorlevel 1 (
    echo   [..] openpyxl       - installing...
    %PYTHON_CMD% -m pip install openpyxl --quiet 2>nul
    %PYTHON_CMD% -c "import openpyxl" >nul 2>&1
    if errorlevel 1 (
        echo   [!!] openpyxl       - FAILED
        set "OFFICE_OK=0"
    ) else (
        echo   [OK] openpyxl       - installed
    )
) else (
    echo   [OK] openpyxl       - already installed
)

:: python-pptx
%PYTHON_CMD% -c "import pptx" >nul 2>&1
if errorlevel 1 (
    echo   [..] python-pptx    - installing...
    %PYTHON_CMD% -m pip install python-pptx --quiet 2>nul
    %PYTHON_CMD% -c "import pptx" >nul 2>&1
    if errorlevel 1 (
        echo   [!!] python-pptx    - FAILED
        set "OFFICE_OK=0"
    ) else (
        echo   [OK] python-pptx    - installed
    )
) else (
    echo   [OK] python-pptx    - already installed
)

:: reportlab
%PYTHON_CMD% -c "import reportlab" >nul 2>&1
if errorlevel 1 (
    echo   [..] reportlab      - installing...
    %PYTHON_CMD% -m pip install reportlab --quiet 2>nul
    %PYTHON_CMD% -c "import reportlab" >nul 2>&1
    if errorlevel 1 (
        echo   [!!] reportlab      - FAILED
        set "OFFICE_OK=0"
    ) else (
        echo   [OK] reportlab      - installed
    )
) else (
    echo   [OK] reportlab      - already installed
)

:: pdfplumber
%PYTHON_CMD% -c "import pdfplumber" >nul 2>&1
if errorlevel 1 (
    echo   [..] pdfplumber     - installing...
    %PYTHON_CMD% -m pip install pdfplumber --quiet 2>nul
    %PYTHON_CMD% -c "import pdfplumber" >nul 2>&1
    if errorlevel 1 (
        echo   [!!] pdfplumber     - FAILED
        set "OFFICE_OK=0"
    ) else (
        echo   [OK] pdfplumber     - installed
    )
) else (
    echo   [OK] pdfplumber     - already installed
)

:: yfinance
%PYTHON_CMD% -c "import yfinance" >nul 2>&1
if errorlevel 1 (
    echo   [..] yfinance       - installing...
    %PYTHON_CMD% -m pip install yfinance --quiet 2>nul
    %PYTHON_CMD% -c "import yfinance" >nul 2>&1
    if errorlevel 1 (
        echo   [!!] yfinance       - FAILED
    ) else (
        echo   [OK] yfinance       - installed
    )
) else (
    echo   [OK] yfinance       - already installed
)

:: newspaper3k
%PYTHON_CMD% -c "import newspaper" >nul 2>&1
if errorlevel 1 (
    echo   [..] newspaper3k   - installing...
    %PYTHON_CMD% -m pip install newspaper3k lxml_html_clean --quiet 2>nul
    %PYTHON_CMD% -c "import newspaper" >nul 2>&1
    if errorlevel 1 (
        echo   [!!] newspaper3k   - FAILED
    ) else (
        echo   [OK] newspaper3k   - installed
    )
) else (
    echo   [OK] newspaper3k   - already installed
)

:: lxml_html_clean
%PYTHON_CMD% -c "import lxml_html_clean" >nul 2>&1
if errorlevel 1 (
    echo   [..] lxml_html_clean - installing...
    %PYTHON_CMD% -m pip install lxml_html_clean --quiet 2>nul
    %PYTHON_CMD% -c "import lxml_html_clean" >nul 2>&1
    if errorlevel 1 (
        echo   [!!] lxml_html_clean - FAILED
    ) else (
        echo   [OK] lxml_html_clean - installed
    )
) else (
    echo   [OK] lxml_html_clean - already installed
)

:: fastapi / uvicorn / PyJWT
set "MOBILE_OK=1"

%PYTHON_CMD% -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo   [..] fastapi        - installing...
    %PYTHON_CMD% -m pip install fastapi uvicorn PyJWT --quiet 2>nul
    %PYTHON_CMD% -c "import fastapi" >nul 2>&1
    if errorlevel 1 (
        echo   [!!] fastapi/uvicorn/PyJWT - FAILED
        set "MOBILE_OK=0"
    ) else (
        echo   [OK] fastapi/uvicorn/PyJWT - installed
    )
) else (
    echo   [OK] fastapi/uvicorn/PyJWT - already installed
)

echo.
if "%OFFICE_OK%"=="1" (
    echo   [OK] All Office dependencies ready (.docx .xlsx .pptx .pdf).
) else (
    echo   [WARN] Some Office packages failed to install.
    echo         Run this script again or install manually:
    echo           pip install python-docx openpyxl python-pptx reportlab pdfplumber
)
if "%TTS_OK%"=="0" (
    echo   [WARN] edge-tts failed. Voice synthesis will be unavailable.
    echo         Fix: pip install edge-tts
)

:: ---- 4. Verify PyQt6 ----
echo.
echo [4/4] Verifying installation...
%PYTHON_CMD% -c "import PyQt6; print('  PyQt6 OK')" 2>nul
if errorlevel 1 (
    echo.
    echo [ERROR] PyQt6 verification failed. Please try:
    echo   %PYTHON_CMD% -m pip install PyQt6 --force-reinstall
    echo.
    pause
    exit /b 1
)

:: ---- Done ----
echo.
echo ========================================
echo   Installation Complete!
echo ========================================
echo.
echo   To start the app:
echo     - Double-click  launch.bat
echo     - Or run:       %PYTHON_CMD% main.py
echo.
echo   First launch: configure your API key in Settings.
echo ========================================
echo.
pause
