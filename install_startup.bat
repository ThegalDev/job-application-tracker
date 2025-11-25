@echo off
set "SCRIPT_PATH=%~dp0run_tracker.bat"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\JobTracker.lnk"

echo Creating shortcut in Startup folder...
echo Target: %SCRIPT_PATH%
echo Destination: %SHORTCUT_PATH%

powershell "$s=(New-Object -COM WScript.Shell).CreateShortcut('%SHORTCUT_PATH%');$s.TargetPath='%SCRIPT_PATH%';$s.Save()"

echo.
echo Done! The Job Tracker will now start automatically when you log in.
pause
