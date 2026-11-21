<#
.SYNOPSIS
    Stop all ZeroManual services: nginx, browseragent, eye, workers, dashboard.
    Uses saved PIDs from logs/pids.json and falls back to port/process detection.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File W:\ZeroManual\scripts\stop-all.ps1
#>
[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot 'stack-lib.ps1')
$ErrorActionPreference = 'Continue'

$StackRoot = Split-Path -Parent $PSScriptRoot
$LogDir    = Join-Path $StackRoot 'logs'
$PidFile   = Join-Path $LogDir 'pids.json'
$NginxDir  = 'C:\nginx'

$pids = Load-Pids

Write-Step "Stopping ZeroManual stack" 'Green'

# --- Stop tracked PIDs first -------------------------------------------------
foreach ($name in $pids.Keys) {
    $procId = $pids[$name]
    Stop-Tracked -Name $name -ProcId $procId
}

# --- Fallback: stop by port/process pattern ----------------------------------
# nginx
if (Get-Process -Name 'nginx' -ErrorAction SilentlyContinue) {
    Write-Step "Stopping nginx..."
    $nginxExe = Join-Path $NginxDir 'nginx.exe'
    if (Test-Path -LiteralPath $nginxExe) {
        cd $NginxDir
        Start-Process -FilePath $nginxExe -ArgumentList '-s', 'quit', '-p', $NginxDir `
                      -WorkingDirectory $NginxDir -WindowStyle Hidden -Wait
    } else {
        Get-Process -Name 'nginx' -ErrorAction SilentlyContinue | Stop-Process -Force
    }
}

# Browser Agent (port 8001)
$portProc = Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue
if ($portProc) {
    Stop-Tracked -Name 'browseragent' -ProcId $portProc.OwningProcess
}

# Eye (port 8000)
$portProc = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($portProc) {
    Stop-Tracked -Name 'eye' -ProcId $portProc.OwningProcess
}

# Dashboard (port 3000)
$portProc = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
if ($portProc) {
    Stop-Tracked -Name 'dashboard' -ProcId $portProc.OwningProcess
}

# Celery workers
$celeryProcesses = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -match "celery.*worker" -and $_.CommandLine -match "workers"
}
foreach ($proc in $celeryProcesses) {
    Stop-Tracked -Name 'workers' -ProcId $proc.ProcessId
}

# Clean up any remaining node processes for dashboard
$nodeProcesses = Get-CimInstance Win32_Process | Where-Object {
    ($_.CommandLine -match "next") -or ($_.CommandLine -match "npm.*start")
}
foreach ($proc in $nodeProcesses) {
    Stop-Tracked -Name 'dashboard' -ProcId $proc.ProcessId
}

# Clean up any remaining python processes from our folders
$pythonProcesses = Get-CimInstance Win32_Process | Where-Object {
    ($_.CommandLine -match "python main.py") -and (
        $_.CommandLine -match "browseragent" -or
        $_.CommandLine -match "eye"
    )
}
foreach ($proc in $pythonProcesses) {
    Stop-Tracked -Name 'python' -ProcId $proc.ProcessId
}

# Clear PID file
if (Test-Path -LiteralPath $PidFile) {
    Remove-Item -LiteralPath $PidFile -Force
}

Write-Step "All services stopped" 'Green'