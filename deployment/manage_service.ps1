<#
.SYNOPSIS
    Service Management Tool for INDIGO QUANT on Windows 11.

.DESCRIPTION
    Provides commands to check status, start, stop, restart, and view logs for
    the autonomous background trading engine daemon.

.EXAMPLE
    .\manage_service.ps1 -Action status
    .\manage_service.ps1 -Action start
    .\manage_service.ps1 -Action stop
    .\manage_service.ps1 -Action restart
    .\manage_service.ps1 -Action logs
#>

[CmdletBinding()]
param(
    [ValidateSet("status", "start", "stop", "restart", "logs")]
    [string]$Action = "status",
    [string]$TaskName = "IndigoQuantScheduler"
)

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$PidFile = Join-Path $ProjectRoot "data\indigo_scheduler.pid"
$HeartbeatFile = Join-Path $ProjectRoot "data\heartbeat.json"
$LogFile = Join-Path $ProjectRoot "logs\indigo_scheduler.log"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

function Get-DaemonStatus {
    $isRunning = $false
    $pidNum = $null

    if (Test-Path $PidFile) {
        $pidContent = (Get-Content $PidFile -Raw).Trim()
        if ($pidContent -match '^\d+$') {
            $pidNum = [int]$pidContent
            $proc = Get-Process -Id $pidNum -ErrorAction SilentlyContinue
            if ($proc) {
                $isRunning = $true
            }
        }
    }

    return [PSCustomObject]@{
        IsRunning = $isRunning
        PID       = $pidNum
    }
}

switch ($Action) {
    "status" {
        Write-Host "============================================================" -ForegroundColor Cyan
        Write-Host "  INDIGO QUANT - Autonomous Engine Status Probe             " -ForegroundColor Cyan
        Write-Host "============================================================" -ForegroundColor Cyan

        $st = Get-DaemonStatus
        if ($st.IsRunning) {
            Write-Host "Service State:   [RUNNING (AUTONOMOUS)]" -ForegroundColor Green
            Write-Host "Process PID:     $($st.PID)" -ForegroundColor White
        } else {
            Write-Host "Service State:   [STOPPED / IDLE]" -ForegroundColor Yellow
            Write-Host "Process PID:     None" -ForegroundColor Gray
        }

        # Check Windows Task Scheduler registration
        $schedTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($schedTask) {
            Write-Host "Windows Task:    Registered (State: $($schedTask.State))" -ForegroundColor Cyan
        } else {
            Write-Host "Windows Task:    Not Registered (Run .\deployment\install_autostart.ps1)" -ForegroundColor DarkGray
        }

        # Read Heartbeat JSON
        if (Test-Path $HeartbeatFile) {
            try {
                $hb = Get-Content $HeartbeatFile -Raw | ConvertFrom-Json
                Write-Host ""
                Write-Host "Heartbeat Health:" -ForegroundColor Cyan
                $healthColor = "Yellow"
                if ($hb.status -eq "HEALTHY") {
                    $healthColor = "Green"
                }
                Write-Host "  - Engine Health:    $($hb.status)" -ForegroundColor $healthColor
                Write-Host "  - Started At:       $($hb.started_at)"
                Write-Host "  - Last Heartbeat:   $($hb.last_heartbeat)"
                Write-Host "  - Engine Uptime:    $($hb.uptime_seconds) seconds"
                if ($hb.active_jobs) {
                    Write-Host "  - Registered Jobs:  $($hb.active_jobs -join ', ')"
                }
            } catch {
                Write-Host "  - Could not parse heartbeat: $_" -ForegroundColor DarkGray
            }
        } else {
            Write-Host "Heartbeat File:  Not found (Engine has not started yet)" -ForegroundColor DarkGray
        }

        # Recent log snippet
        if (Test-Path $LogFile) {
            Write-Host ""
            Write-Host "Recent Log Entries (Last 5 lines):" -ForegroundColor Cyan
            Get-Content $LogFile -Tail 5 | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
        }
    }

    "start" {
        $st = Get-DaemonStatus
        if ($st.IsRunning) {
            Write-Host "[INFO] Indigo Quant scheduler is already running with PID $($st.PID)." -ForegroundColor Yellow
            return
        }

        Write-Host "Starting INDIGO QUANT scheduler daemon..." -ForegroundColor Cyan

        $schedTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($schedTask) {
            Start-ScheduledTask -TaskName $TaskName
            Start-Sleep -Seconds 2
        } else {
            # Start via background process directly
            $psi = New-Object System.Diagnostics.ProcessStartInfo
            $psi.FileName = $VenvPython
            $psi.Arguments = "-m indigo_quant.scheduler.runner"
            $psi.WorkingDirectory = $ProjectRoot
            $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
            $psi.CreateNoWindow = $true
            $psi.UseShellExecute = $false
            [System.Diagnostics.Process]::Start($psi) | Out-Null
            Start-Sleep -Seconds 2
        }

        $newSt = Get-DaemonStatus
        if ($newSt.IsRunning) {
            Write-Host "[SUCCESS] Indigo Quant daemon started with PID $($newSt.PID)." -ForegroundColor Green
        } else {
            Write-Host "[WARNING] Daemon started. Checking status in a moment..." -ForegroundColor Yellow
        }
    }

    "stop" {
        Write-Host "Stopping INDIGO QUANT scheduler..." -ForegroundColor Yellow
        $st = Get-DaemonStatus
        if ($st.PID) {
            Stop-Process -Id $st.PID -Force -ErrorAction SilentlyContinue
            Write-Host "[OK] Terminated PID $($st.PID)." -ForegroundColor Green
        }

        $schedTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($schedTask -and $schedTask.State -eq "Running") {
            Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        }

        if (Test-Path $PidFile) {
            Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        }
        Write-Host "[OK] Service stopped successfully." -ForegroundColor Green
    }

    "restart" {
        & $PSCommandPath -Action stop
        Start-Sleep -Seconds 2
        & $PSCommandPath -Action start
    }

    "logs" {
        if (-not (Test-Path $LogFile)) {
            Write-Host "Log file not found at: $LogFile" -ForegroundColor Yellow
            return
        }
        Write-Host "Following $LogFile (Press Ctrl+C to exit)..." -ForegroundColor Cyan
        Get-Content $LogFile -Wait -Tail 30
    }
}
