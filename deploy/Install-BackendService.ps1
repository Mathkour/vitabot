#requires -RunAsAdministrator
<#
.SYNOPSIS
    Keeps the FastAPI backend (Uvicorn) running on a fixed port as a startup task.
.DESCRIPTION
    Run elevated. Creates a wrapper script and a Scheduled Task (runs as SYSTEM, at startup,
    restarts on failure) that launches:
        .venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port <Port>
    Logs go to <BackendPath>\logs\backend.log. No third-party tools required.
.EXAMPLE
    .\Install-BackendService.ps1 -BackendPath C:\inetpub\cpbot\backend -Port 8000
#>
[CmdletBinding()]
param(
    [string]$BackendPath = 'C:\inetpub\cpbot\backend',
    [int]$Port = 8000,
    [string]$BindHost = '127.0.0.1',
    [string]$TaskName = 'CP_BOT_Backend'
)
$ErrorActionPreference = 'Stop'
$venvPy = Join-Path $BackendPath '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) { throw "venv python not found: $venvPy. Create the venv and install requirements first." }
New-Item -ItemType Directory -Force (Join-Path $BackendPath 'logs') | Out-Null

# Wrapper so we can redirect stdout/stderr to a log file
$cmd = Join-Path $BackendPath 'run-backend.cmd'
@"
@echo off
cd /d "$BackendPath"
"$venvPy" -m uvicorn main:app --host $BindHost --port $Port >> "$BackendPath\logs\backend.log" 2>&1
"@ | Set-Content $cmd -Encoding ASCII
Write-Host "[OK] wrote $cmd" -ForegroundColor Green

$action    = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$cmd`"" -WorkingDirectory $BackendPath
$trigger   = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
                -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
Start-ScheduledTask -TaskName $TaskName

Start-Sleep -Seconds 3
Write-Host ""
Write-Host "[OK] Task '$TaskName' started Uvicorn on ${BindHost}:$Port" -ForegroundColor Green
Write-Host "     Log: $BackendPath\logs\backend.log"
Write-Host "     Manage: Start-ScheduledTask / Stop-ScheduledTask -TaskName $TaskName"
