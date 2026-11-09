# INDIGO QUANT — Windows 11 PowerShell Setup and Validation Script
# Automated environment setup, dependency installation, database initialization, and diagnostics.

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   INDIGO QUANT — AUTOMATED ENVIRONMENT SETUP" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Check Python Version (>= 3.11)
Write-Host "`n[1/7] Checking Python version..." -ForegroundColor Yellow
$pythonExe = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if (-not $pythonExe) {
    Write-Error "Python is not installed or not in system PATH. Python 3.11+ is required."
}

$pyVersion = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
Write-Host "Found Python version: $pyVersion at $pythonExe" -ForegroundColor Green

$versionCheck = & python -c "import sys; print(1 if sys.version_info >= (3, 11) else 0)"
if ($versionCheck -ne "1") {
    Write-Error "Python 3.11 or newer is required. Found Python $pyVersion"
}

# 2. Setup Virtual Environment
Write-Host "`n[2/7] Checking / Creating virtual environment (.venv)..." -ForegroundColor Yellow
if (-not (Test-Path ".venv")) {
    & python -m venv .venv
    Write-Host "Virtual environment .venv created." -ForegroundColor Green
} else {
    Write-Host "Virtual environment .venv already exists." -ForegroundColor Green
}

$venvPython = ".\.venv\Scripts\python.exe"

# 3. Upgrade pip and Install Dependencies
Write-Host "`n[3/7] Installing pinned dependencies from requirements.txt..." -ForegroundColor Yellow
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt
& $venvPython -m pip install -e . --no-deps
Write-Host "Dependencies installed successfully." -ForegroundColor Green

# 4. Initialize Database and Seed Universe & Accounts
Write-Host "`n[4/7] Initializing SQLite database and seeding 5 virtual portfolios..." -ForegroundColor Yellow
& $venvPython -c "from indigo_quant.db.session import SessionLocal; from indigo_quant.db.repository import init_db, seed_universe_and_accounts; init_db(); db = SessionLocal(); seed_universe_and_accounts(db); db.close()"
Write-Host "Database initialized with ₹1,00,000 virtual capital per strategy." -ForegroundColor Green

# 5. Validate Market Data Connectivity
Write-Host "`n[5/7] Validating free market-data providers (TejHQ & Yahoo Finance)..." -ForegroundColor Yellow
& $venvPython -c "from indigo_quant.db.session import SessionLocal; from indigo_quant.data.ingestion import DataIngestionEngine; db = SessionLocal(); eng = DataIngestionEngine(db); print('Provider Health:', eng.get_provider_health()); db.close()"
Write-Host "Market data connectivity probe complete." -ForegroundColor Green

# 6. Run Automated Test Suite
Write-Host "`n[6/7] Running automated pytest test suite..." -ForegroundColor Yellow
& $venvPython -m pytest tests -v --tb=short

# 7. Print Success and Launch Instructions
Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "   INDIGO QUANT SETUP COMPLETED SUCCESSFULLY!" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "`nTo launch the interactive Streamlit dashboard:" -ForegroundColor Cyan
Write-Host "  .\.venv\Scripts\python.exe -m streamlit run src/indigo_quant/dashboard/app.py" -ForegroundColor White
Write-Host "`nTo run the CLI doctor diagnostics:" -ForegroundColor Cyan
Write-Host "  .\.venv\Scripts\python.exe -m indigo_quant.cli doctor" -ForegroundColor White
Write-Host "`nTo run a market scan:" -ForegroundColor Cyan
Write-Host "  .\.venv\Scripts\python.exe -m indigo_quant.cli scan" -ForegroundColor White
