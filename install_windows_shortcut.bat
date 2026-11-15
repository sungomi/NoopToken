@echo off
setlocal
cd /d "%~dp0"

echo [AI Monitor v1.0] Creating Desktop Shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop') + '\AI Monitor v1.0.lnk'); $s.TargetPath='%~dp0run_windows.bat'; $s.WorkingDirectory='%~dp0'; $s.WindowStyle=7; if (Test-Path '%~dp0assets\icon.ico') { $s.IconLocation='%~dp0assets\icon.ico' }; $s.Save()"
echo [OK] Desktop shortcut 'AI Monitor v1.0' has been created!
pause
