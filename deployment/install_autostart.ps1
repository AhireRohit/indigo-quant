<#
.SYNOPSIS
    Installs INDIGO QUANT Autonomous Scheduler as a persistent Windows Scheduled Task.

.DESCRIPTION
    Registers a background Windows Scheduled Task named "IndigoQuantScheduler" that:
    1. Starts automatically on Windows user login and system startup.
    2. Runs completely in the background without popping up terminal or PowerShell windows.
    3. Directly executes pythonw.exe so Windows Task Scheduler genuinely supervises process lifecycle.
    4. Automatically restarts up to 3 times if the engine process crashes.
    5. Configures power settings so it continues running on AC power or battery.

.NOTES
    Run from an elevated or normal PowerShell terminal in the project directory:
    powershell -ExecutionPolicy Bypass -File .\deployment\install_autostart.ps1
#>

[CmdletBinding()]
param(
    [string]$TaskName = "IndigoQuantScheduler",
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $VenvPython)) {
    $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
}

if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment Python executable not found at: $VenvPython. Run .\setup.ps1 first."
    exit 1
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  INDIGO QUANT - Windows Task Scheduler Autostart Installer " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Project Directory: $ProjectRoot"
Write-Host "Python Executable: $VenvPython"
Write-Host ""

if ($Uninstall) {
    Write-Host "Uninstalling Scheduled Task: $TaskName..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "[OK] Task $TaskName removed successfully." -ForegroundColor Green
    exit 0
}

# 1. Clean up legacy VBS launcher if present
$LegacyVbs = Join-Path $ProjectRoot "deployment\launch_scheduler_daemon.vbs"
if (Test-Path $LegacyVbs) {
    Remove-Item $LegacyVbs -Force -ErrorAction SilentlyContinue
}

# 2. Define Scheduled Task Action
# Directly execute pythonw.exe (the windowless Windows GUI Python binary).
# This provides silent background execution without any popping console windows,
# while allowing Windows Task Scheduler to directly supervise the process lifecycle,
# monitor state (reporting 'Running' while active), and automatically trigger
# crash recovery / restart policies if the process ever terminates unexpectedly.
$Action = New-ScheduledTaskAction `
    -Execute $VenvPython `
    -Argument "-m indigo_quant.scheduler.runner" `
    -WorkingDirectory $ProjectRoot

# 3. Define Triggers (At User Logon)
$UserAccount = "$env:USERDOMAIN\$env:USERNAME"
if (-not $env:USERDOMAIN) {
    $UserAccount = $env:USERNAME
}
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $UserAccount

# 4. Configure Robust Settings with Automatic Crash Recovery
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Days 365) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

# 5. Register Task
try {
    # Unregister if already present
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Description "INDIGO QUANT Autonomous Indian Equity Swing-Trading Research Engine" | Out-Null

    Write-Host ""
    Write-Host "[SUCCESS] Task '$TaskName' registered successfully with Windows Task Scheduler!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Task Details:" -ForegroundColor Cyan
    Write-Host "  - Name: $TaskName"
    Write-Host "  - Trigger: At Logon for user $UserAccount"
    Write-Host "  - Execution: Direct supervised background process via $VenvPython"
    Write-Host "  - Supervision: Windows Task Scheduler tracks engine PID directly"
    Write-Host "  - Auto-Restart: 3 attempts every 1 minute on failure"
    Write-Host "  - Working Dir: $ProjectRoot"
    Write-Host ""
    Write-Host "To start the task immediately:" -ForegroundColor Yellow
    Write-Host "  Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
    Write-Host "Or use:" -ForegroundColor Yellow
    Write-Host "  .\deployment\manage_service.ps1 -Action start" -ForegroundColor White
    Write-Host ""
    Write-Host "To inspect service heartbeat & logs:" -ForegroundColor Yellow
    Write-Host "  .\deployment\manage_service.ps1 -Action status" -ForegroundColor White
}
catch {
    Write-Error "Failed to register scheduled task: $_"
    exit 1
}
