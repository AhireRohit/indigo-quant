<#
.SYNOPSIS
    Starts the local Streamlit public dashboard and exposes it via a free HTTPS public tunnel.

.DESCRIPTION
    1. Launches Streamlit on port 8501 serving public_app.py (read-only, sanitized snapshots).
    2. Opens an encrypted SSH reverse tunnel via Pinggy / localhost.run on port 443.
    3. Outputs the public HTTPS URL for external sharing (e.g. ChatGPT analysis).

.EXAMPLE
    .\scripts\start_public_tunnel.ps1
#>

[CmdletBinding()]
param()

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Streamlit = Join-Path $ProjectRoot ".venv\Scripts\streamlit.exe"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  INDIGO QUANT - Free Public HTTPS Dashboard Host          " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Check if Streamlit is already running on port 8501
$existingConn = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue
if (-not $existingConn) {
    Write-Host "[1/2] Starting Streamlit public dashboard on port 8501..." -ForegroundColor Yellow
    Start-Process -FilePath $Streamlit -ArgumentList "run public_app.py --server.port 8501 --server.headless true --server.address 127.0.0.1" -WindowStyle Hidden
    Start-Sleep -Seconds 3
} else {
    Write-Host "[1/2] Streamlit is already listening on port 8501." -ForegroundColor Green
}

# 2. Start SSH tunnel
Write-Host "[2/2] Connecting encrypted HTTPS public tunnel..." -ForegroundColor Yellow
Write-Host "Press Ctrl+C to terminate the tunnel when finished." -ForegroundColor Gray
Write-Host ""

& ssh -p 443 -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -R0:localhost:8501 a.pinggy.io
