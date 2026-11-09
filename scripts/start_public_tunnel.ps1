<#
.SYNOPSIS
    Starts the local Streamlit public dashboard and exposes it via a high-performance Cloudflare HTTPS tunnel.

.DESCRIPTION
    1. Launches Streamlit on port 8501 serving public_app.py (read-only, sanitized snapshots).
    2. Opens an encrypted HTTPS Cloudflare Quick Tunnel via bin/cloudflared.exe.
    3. Outputs the public HTTPS URL for external sharing (e.g. ChatGPT analysis).

.EXAMPLE
    .\scripts\start_public_tunnel.ps1
#>

[CmdletBinding()]
param()

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $ProjectRoot

$Streamlit = Join-Path $ProjectRoot ".venv\Scripts\streamlit.exe"
$Cloudflared = Join-Path $ProjectRoot "bin\cloudflared.exe"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  INDIGO QUANT - Free Public Cloudflare HTTPS Dashboard     " -ForegroundColor Cyan
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

# 2. Start Cloudflare Tunnel
Write-Host "[2/2] Connecting Cloudflare HTTPS public tunnel..." -ForegroundColor Yellow
Write-Host "Press Ctrl+C to terminate the tunnel when finished." -ForegroundColor Gray
Write-Host ""

& $Cloudflared tunnel --url http://127.0.0.1:8501
