@echo off
setlocal
cd /d "%~dp0"

echo [NoopToken] Creating Desktop Shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop') + '\NoopToken.lnk'); $s.TargetPath='%~dp0run_windows.bat'; $s.WorkingDirectory='%~dp0'; $s.WindowStyle=7; if (Test-Path '%~dp0assets\icon.ico') { $s.IconLocation='%~dp0assets\icon.ico' }; $s.Save()"
echo [OK] Desktop shortcut 'NoopToken' has been created!
pause
