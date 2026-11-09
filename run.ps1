# INDIGO QUANT — Windows Execution Helper
param (
    [string]$Mode = "dashboard" # "dashboard", "api", "scheduler", "scan", "doctor"
)

$venvPython = ".\.venv\Scripts\python.exe"

switch ($Mode.ToLower()) {
    "dashboard" {
        Write-Host "Starting INDIGO QUANT Streamlit Dashboard on http://localhost:8501..." -ForegroundColor Green
        & $venvPython -m streamlit run src/indigo_quant/dashboard/app.py --server.port 8501
    }
    "api" {
        Write-Host "Starting INDIGO QUANT FastAPI Server on http://127.0.0.1:8000..." -ForegroundColor Green
        & $venvPython -m uvicorn indigo_quant.api.main:app --host 127.0.0.1 --port 8000 --reload
    }
    "scan" {
        Write-Host "Executing daily deterministic swing scan..." -ForegroundColor Cyan
        & $venvPython -m indigo_quant.cli scan
    }
    "doctor" {
        & $venvPython -m indigo_quant.cli doctor
    }
    "test" {
        & $venvPython -m pytest tests -v
    }
    default {
        Write-Host "Unknown mode '$Mode'. Supported: dashboard, api, scan, doctor, test" -ForegroundColor Red
    }
}
