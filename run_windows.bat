@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: 1. 최초 실행 시 가상환경(.venv) 자동 생성 및 패키지 설치
if not exist ".venv\Scripts\python.exe" (
    echo [AI 사용량 모니터] 최초 실행 환경을 구성하고 있습니다...
    where uv >nul 2>nul
    if %errorlevel%==0 (
        uv venv .venv
        uv pip install -r requirements.txt
    ) else (
        python -m venv .venv
        ".venv\Scripts\python.exe" -m pip install --upgrade pip
        ".venv\Scripts\pip.exe" install -r requirements.txt
    )
)

:: 2. --cli 인자가 있으면 콘솔 출력, 없으면 백그라운드 GUI 위젯(pythonw)으로 즉시 실행
if "%~1"=="--cli" (
    ".venv\Scripts\python.exe" widget.py %*
    pause
) else (
    start "" ".venv\Scripts\pythonw.exe" widget.py %*
)
