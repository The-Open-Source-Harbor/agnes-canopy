$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Baltimore Dashboard - Local Launcher" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] Python is not available in PATH." -ForegroundColor Red
    Write-Host "Install Python 3.10+ and try again." -ForegroundColor Red
    exit 1
}

Write-Host "[1/2] Installing dependencies..."
python -m pip install -r requirements.txt

Write-Host ""
Write-Host "[2/2] Starting Streamlit app..."
python -m streamlit run Baltimore_Dashboard_Updated.py
