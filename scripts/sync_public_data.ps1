<#
.SYNOPSIS
    Exports sanitized public data and pushes snapshots to GitHub for Streamlit Cloud.

.DESCRIPTION
    1. Generates updated JSON snapshots in public_data/.
    2. Builds standalone static HTML dashboard at public_data/index.html.
    3. Commits and pushes changes to the GitHub repository so Streamlit Cloud auto-refreshes.

.EXAMPLE
    .\scripts\sync_public_data.ps1
#>

[CmdletBinding()]
param(
    [string]$CommitMessage = "Update Indigo Quant public data snapshots [automated sync]"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  INDIGO QUANT — Public Data Sync & Cloud Export Engine    " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Export fresh snapshots
Write-Host "Generating sanitized JSON snapshots and static HTML..." -ForegroundColor Cyan
& $Python -m indigo_quant.cli export-public

if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to export public snapshots."
    exit 1
}

# 2. Check if git repository exists
$isGit = Test-Path (Join-Path $ProjectRoot ".git")
if (-not $isGit) {
    Write-Host ""
    Write-Host "[INFO] Project is not yet a Git repository." -ForegroundColor Yellow
    Write-Host "Snapshots are ready in 'public_data/'." -ForegroundColor Green
    Write-Host "To link to GitHub for Streamlit Community Cloud:" -ForegroundColor Cyan
    Write-Host "  git init" -ForegroundColor White
    Write-Host "  git add ." -ForegroundColor White
    Write-Host "  git commit -m `"Initial commit`"" -ForegroundColor White
    Write-Host "  git remote add origin https://github.com/<your-username>/indigo-quant-public.git" -ForegroundColor White
    Write-Host "  git push -u origin main" -ForegroundColor White
    exit 0
}

# 3. Commit and push public_data
Write-Host "Staging public snapshots for Git commit..." -ForegroundColor Cyan
git add public_data/ public_app.py requirements_public.txt .streamlit/

$status = git status --porcelain public_data/ public_app.py
if ([string]::IsNullOrWhiteSpace($status)) {
    Write-Host "[OK] No changes detected in public snapshots. Cloud is already up to date." -ForegroundColor Green
    exit 0
}

Write-Host "Committing changes..." -ForegroundColor Cyan
git commit -m $CommitMessage

# Check if remote exists
$remotes = git remote
if ($remotes) {
    Write-Host "Pushing to remote repository..." -ForegroundColor Cyan
    git push
    Write-Host "[SUCCESS] Pushed snapshots to GitHub. Streamlit Community Cloud will auto-deploy!" -ForegroundColor Green
} else {
    Write-Host "[INFO] Changes committed locally. No remote repository configured yet." -ForegroundColor Yellow
}
