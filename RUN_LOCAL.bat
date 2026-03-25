@echo off
setlocal

cd /d "%~dp0"
echo ==========================================
echo Baltimore Dashboard - Local Launcher
echo ==========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python is not available in PATH.
  echo Install Python 3.10+ and try again.
  pause
  exit /b 1
)

echo [1/2] Installing dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Dependency installation failed.
  pause
  exit /b 1
)

echo.
echo [2/2] Starting Streamlit app...
python -m streamlit run Baltimore_Dashboard_Updated.py

endlocal
