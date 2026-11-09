<#
.SYNOPSIS
    Installs INDIGO QUANT Autonomous Scheduler as a persistent Windows Scheduled Task.

.DESCRIPTION
    Registers a background Windows Scheduled Task named "IndigoQuantScheduler" that:
    1. Starts automatically on Windows user login and system startup.
    2. Runs completely in the background without popping up terminal or PowerShell windows.
    3. Executes the dedicated scheduler runner using the local Python virtual environment (.venv).
    4. Automatically restarts up to 3 times if the process terminates unexpectedly.
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
Write-Host "  INDIGO QUANT — Windows Task Scheduler Autostart Installer " -ForegroundColor Cyan
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

# 1. Prepare startup runner launcher script
$LauncherScript = Join-Path $ProjectRoot "deployment\launch_scheduler_daemon.vbs"
$VbsContent = @"
' INDIGO QUANT Silent Background Process Launcher
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "$ProjectRoot"
WshShell.Run """$VenvPython"" -m indigo_quant.scheduler.runner", 0, False
Set WshShell = Nothing
"@
Set-Content -Path $LauncherScript -Value $VbsContent -Encoding ASCII
Write-Host "[OK] Created silent background launcher: $LauncherScript" -ForegroundColor Green

# 2. Define Action
$Action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "`"$LauncherScript`"" `
    -WorkingDirectory $ProjectRoot

# 3. Define Triggers (At User Logon)
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# 4. Configure Robust Settings
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
    Write-Host "  • Name: $TaskName"
    Write-Host "  • Trigger: At Logon for user $env:USERNAME"
    Write-Host "  • Execution: Silent background daemon via $LauncherScript"
    Write-Host "  • Auto-Restart: 3 attempts every 1 minute on failure"
    Write-Host "  • Working Dir: $ProjectRoot"
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
