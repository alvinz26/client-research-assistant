@echo off
rem Double-click to start Client Research Assistant in your browser (Windows).
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo First run: setting things up. This takes a minute or two...
    where py >nul 2>nul && (py -3 -m venv .venv) || (python -m venv .venv)
)
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo Python 3.11 or newer is needed. Download it from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" during installation, then double-click this file again.
    pause
    exit /b 1
)

echo Checking dependencies...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
    echo Installing dependencies failed. Check your internet connection and try again.
    pause
    exit /b 1
)

echo.
echo Starting... your browser will open at http://localhost:8501
echo Keep this window open while you use the app. Close it to stop.
start "" cmd /c "timeout /t 4 >nul & start http://localhost:8501"
".venv\Scripts\python.exe" -m streamlit run app.py
pause
