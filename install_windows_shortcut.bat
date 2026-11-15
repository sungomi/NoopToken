@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: 먼저 가상환경 구성 확인
if not exist ".venv\Scripts\pythonw.exe" (
    call run_windows.bat --cli
)

set "TARGET_BAT=%~dp0run_windows.bat"
set "SHORTCUT_PATH=%USERPROFILE%\Desktop\AI 사용량 모니터.lnk"

powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath = '%TARGET_BAT%'; $s.WorkingDirectory = '%~dp0'; $s.WindowStyle = 7; $s.Description = 'AI 사용량 모니터 데스크톱 위젯'; $s.Save()"

echo ✅ 바탕화면에 'AI 사용량 모니터' 바로가기가 생성되었습니다!
pause
