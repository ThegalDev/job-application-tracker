@echo off
echo ==========================================
echo      JOB APPLICATION MANAGER SETUP
echo ==========================================

cd /d "%~dp0"

echo 1. Checking Python...
python --version
if %errorlevel% neq 0 (
    echo Python not found! Please install Python.
    pause
    exit /b
)

echo.
echo 2. Installing dependencies...
python -m pip install fastapi uvicorn requests beautifulsoup4
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b
)

echo.
echo 3. Starting Server...
start "Job Tracker Server" cmd /k "cd dashboard && python -m uvicorn server:app --reload --port 8000"

echo.
echo 4. Starting Email Monitor...
start "Email Monitor" cmd /k "cd dashboard && python email_monitor.py"

echo.
echo 5. Starting Job Sourcer...
start "Job Sourcer" cmd /k "cd dashboard && python job_sourcer.py"

echo.
echo 5. Opening Dashboard...
timeout /t 4 >nul
start http://localhost:8000

echo.
echo ==========================================
echo      DONE! You can minimize this window.
echo ==========================================
pause
