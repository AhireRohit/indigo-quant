# ==============================================================================
# INDIGO QUANT — GitHub & Streamlit Community Cloud Deployment Helper
# ==============================================================================
# Verifies repository hygiene, checks for secret leaks, validates public assets,
# and assists in pushing to GitHub for instant deployment to Streamlit Cloud.
# ==============================================================================

[CmdletBinding()]
param(
    [string]$RemoteUrl = "",
    [switch]$Force
)

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "🎯 INDIGO QUANT - GitHub & Streamlit Cloud Deployment Verification" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# 1. Security & Secret Audit
Write-Host "`n[1/5] Auditing for Secret Leaks..." -ForegroundColor Yellow
$sensitivePatterns = @(".env", "data/*.db", "data/*.lock", "data/heartbeat.json", "logs/*.log")
$leakDetected = $false

foreach ($pattern in $sensitivePatterns) {
    $trackedFiles = git ls-files $pattern 2>$null
    if ($trackedFiles) {
        Write-Host "  [FAIL] Sensitive files tracked by Git matching ${pattern}:" -ForegroundColor Red
        $trackedFiles | ForEach-Object { Write-Host "    - $_" -ForegroundColor Red }
        $leakDetected = $true
    }
}

if (Test-Path ".env") {
    $envTracked = git ls-files .env 2>$null
    if ($envTracked) {
        Write-Host "  [FAIL] .env file is tracked in Git! Untrack it immediately." -ForegroundColor Red
        $leakDetected = $true
    } else {
        Write-Host "  [OK] .env is properly ignored and NOT tracked." -ForegroundColor Green
    }
}

if ($leakDetected -and -not $Force) {
    Write-Host "`n[FATAL] Secret audit failed. Untrack sensitive files before pushing to GitHub." -ForegroundColor Red
    exit 1
} else {
    Write-Host "  [OK] Zero secrets detected in Git staging index." -ForegroundColor Green
}

# 2. Verify Streamlit Community Cloud Artifacts
Write-Host "`n[2/5] Verifying Streamlit Cloud Assets..." -ForegroundColor Yellow
$requiredFiles = @("public_app.py", "requirements.txt", ".streamlit/config.toml")
foreach ($file in $requiredFiles) {
    if (Test-Path $file) {
        Write-Host "  [OK] Found $file" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] Missing required deployment file: $file" -ForegroundColor Red
        exit 1
    }
}

if (Test-Path "public_data") {
    $jsonCount = (Get-ChildItem -Path "public_data" -Filter "*.json" -Recurse | Measure-Object).Count
    $parquetCount = (Get-ChildItem -Path "public_data" -Filter "*.parquet" -Recurse | Measure-Object).Count
    Write-Host "  [OK] public_data/ contains $jsonCount JSON snapshots and $parquetCount curated Parquet datasets." -ForegroundColor Green
} else {
    Write-Host "  [WARNING] public_data/ directory not found. Export public data first using 'indigo export-public'." -ForegroundColor Yellow
}

# 3. Check Git Remote
Write-Host "`n[3/5] Checking Git Remote..." -ForegroundColor Yellow
$existingRemotes = git remote -v 2>$null

if ($RemoteUrl) {
    if ($existingRemotes -match "origin") {
        Write-Host "  Updating remote 'origin' to $RemoteUrl..." -ForegroundColor Cyan
        git remote set-url origin $RemoteUrl
    } else {
        Write-Host "  Adding remote 'origin' ($RemoteUrl)..." -ForegroundColor Cyan
        git remote add origin $RemoteUrl
    }
}

$currentRemote = git remote get-url origin 2>$null
if ($currentRemote) {
    Write-Host "  [OK] Git remote origin configured: $currentRemote" -ForegroundColor Green
} else {
    Write-Host "  [NOTICE] No Git remote 'origin' is currently set." -ForegroundColor Yellow
    Write-Host "  To configure: .\scripts\deploy_github.ps1 -RemoteUrl 'https://github.com/<username>/<repo>.git'" -ForegroundColor Gray
}

# 4. Check Local Git Status
Write-Host "`n[4/5] Checking Git Working Tree Status..." -ForegroundColor Yellow
$status = git status --short
if (-not $status) {
    Write-Host "  [OK] Working tree clean. Everything committed." -ForegroundColor Green
} else {
    Write-Host "  [NOTICE] Uncommitted changes detected:" -ForegroundColor Yellow
    $status | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
}

# 5. Streamlit Cloud Linking Guide
Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host "🚀 STREAMLIT COMMUNITY CLOUD DEPLOYMENT INSTRUCTIONS" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "1. Push your latest code to GitHub:" -ForegroundColor White
Write-Host "   git push -u origin master" -ForegroundColor Gray
Write-Host "`n2. Open Streamlit Community Cloud:" -ForegroundColor White
Write-Host "   https://share.streamlit.io/" -ForegroundColor Gray
Write-Host "`n3. Click 'Create app' -> 'Yup, I have an app' and set:" -ForegroundColor White
Write-Host "   - Repository:   <your-github-username>/<your-repo-name>" -ForegroundColor Gray
Write-Host "   - Branch:       master" -ForegroundColor Gray
Write-Host "   - Main file path: public_app.py" -ForegroundColor Green
Write-Host "   - App URL:      (choose a custom subdomain, e.g. indigo-quant.streamlit.app)" -ForegroundColor Gray
Write-Host "`n4. Click 'Deploy!'" -ForegroundColor Green
Write-Host "   Streamlit Cloud will read requirements.txt and launch the read-only dashboard." -ForegroundColor White
Write-Host "=================================================================" -ForegroundColor Cyan
