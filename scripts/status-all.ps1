<#
.SYNOPSIS
    Show status of all ZeroManual services.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File W:\ZeroManual\scripts\status-all.ps1
#>
[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot 'stack-lib.ps1')

$StackRoot = Split-Path -Parent $PSScriptRoot
$LogDir    = Join-Path $StackRoot 'logs'
$PidFile   = Join-Path $LogDir 'pids.json'
$NginxDir  = 'C:\nginx'

$pids = Load-Pids

Write-Step "ZeroManual Stack Status" 'Green'
Write-Step "=========================" 'Green'

# --- nginx -------------------------------------------------------------------
$nginxRunning = Get-Process -Name 'nginx' -ErrorAction SilentlyContinue
$nginxPortOpen = Test-PortOpen -Port 80
$nginxStatus = if ($nginxRunning -and $nginxPortOpen) { 'RUNNING' } elseif ($nginxRunning -and -not $nginxPortOpen) { 'RUNNING (no listener)' } else { 'STOPPED' }
Write-Step "nginx (port 80):           $nginxStatus" $(if ($nginxStatus -like 'RUNNING*') { 'Green' } else { 'Red' })

# --- Browser Agent -----------------------------------------------------------
$baPortOpen = Test-PortOpen -Port 8001
$baStatus = if ($baPortOpen) { 'RUNNING' } else { 'STOPPED' }
Write-Step "Browser Agent (port 8001):  $baStatus" $(if ($baStatus -eq 'RUNNING') { 'Green' } else { 'Red' })

# --- Eye ---------------------------------------------------------------------
$eyePortOpen = Test-PortOpen -Port 8000
$eyeStatus = if ($eyePortOpen) { 'RUNNING' } else { 'STOPPED' }
Write-Step "Eye API (port 8000):        $eyeStatus" $(if ($eyeStatus -eq 'RUNNING') { 'Green' } else { 'Red' })

# --- Workers -----------------------------------------------------------------
$celeryRunning = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -match "celery.*worker" -and $_.CommandLine -match "workers"
}
$workersStatus = if ($celeryRunning) { 'RUNNING' } else { 'STOPPED' }
Write-Step "Workers (Celery):           $workersStatus" $(if ($workersStatus -eq 'RUNNING') { 'Green' } else { 'Red' })

# --- Dashboard ---------------------------------------------------------------
$dashPortOpen = Test-PortOpen -Port 3000
$dashStatus = if ($dashPortOpen) { 'RUNNING' } else { 'STOPPED' }
Write-Step "Dashboard (port 3000):      $dashStatus" $(if ($dashStatus -eq 'RUNNING') { 'Green' } else { 'Red' })

Write-Step "`nLogs directory: $LogDir" 'Cyan'
if (Test-Path -LiteralPath $LogDir) {
    $logs = Get-ChildItem -LiteralPath $LogDir -File | Sort-Object LastWriteTime -Descending | Select-Object -First 10
    if ($logs) {
        Write-Step "Recent logs:" 'Cyan'
        foreach ($log in $logs) {
            Write-Host "  $($log.Name)  ($($log.Length) bytes, $($log.LastWriteTime))"
        }
    }
}