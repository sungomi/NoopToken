@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [TokenChecker] Setting up Python virtual environment...
    where uv >nul 2>nul
    if %errorlevel% equ 0 (
        uv venv .venv
        uv pip install -r requirements.txt
    ) else (
        python -m venv .venv
        ".venv\Scripts\python.exe" -m pip install --upgrade pip -q
        ".venv\Scripts\pip.exe" install -r requirements.txt -q
    )
)

if "%~1"=="--cli" (
    ".venv\Scripts\python.exe" widget.py --cli
    pause
    exit /b 0
)

start "" ".venv\Scripts\pythonw.exe" widget.py %*
