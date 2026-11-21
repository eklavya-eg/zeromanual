<#
.SYNOPSIS
    Start all ZeroManual services: nginx, browseragent, eye, workers, dashboard.

.DESCRIPTION
    Idempotent - services already running are left alone.
    All output goes to W:\ZeroManual\logs\.

.PARAMETER SkipBuild
    Reuse the existing dashboard build instead of running `npm run build`.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File W:\ZeroManual\scripts\start-all.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipBuild
)

. (Join-Path $PSScriptRoot 'stack-lib.ps1')
$ErrorActionPreference = 'Stop'

# --- Paths -------------------------------------------------------------------
$StackRoot   = Split-Path -Parent $PSScriptRoot
$LogDir      = Join-Path $StackRoot 'logs'
$NginxDir    = 'C:\nginx'  # Adjust if nginx is elsewhere
$BrowserAgentDir = Join-Path $StackRoot 'browseragent'
$EyeDir      = Join-Path $StackRoot 'eye'
$WorkersDir  = Join-Path $StackRoot 'workers'
$DashboardDir = Join-Path $StackRoot 'dashboard'

# Ports
$NginxPort      = 80
$BrowserAgentPort = 8001
$EyePort        = 8000
$DashboardPort  = 3000

if (-not (Test-Path -LiteralPath $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$pids = Load-Pids

Write-Step "Starting ZeroManual stack" 'Green'

# --- 1. nginx ----------------------------------------------------------------
$nginxExe = Join-Path $NginxDir 'nginx.exe'
if (-not (Test-Path -LiteralPath $nginxExe)) {
    Write-Warning "nginx not found at $nginxExe - skipping"
} else {
    if (Get-Process -Name 'nginx' -ErrorAction SilentlyContinue) {
        Write-Step "nginx already running - reloading config"
        Start-Process -FilePath $nginxExe -ArgumentList '-s', 'reload', '-p', $NginxDir `
                      -WorkingDirectory $NginxDir -WindowStyle Hidden -Wait
    } else {
        Write-Step "Starting nginx"
        cd $NginxDir
        Start-Process -FilePath $nginxExe -ArgumentList '-p', $NginxDir `
                      -WorkingDirectory $NginxDir -WindowStyle Hidden
        Start-Sleep -Seconds 2
        if (-not (Get-Process -Name 'nginx' -ErrorAction SilentlyContinue)) {
            Write-Warning "nginx did not stay up - see $NginxDir\logs\error.log"
        }
    }
}

# --- 2. Browser Agent --------------------------------------------------------
if (Test-PortOpen -Port $BrowserAgentPort) {
    Write-Step "Browser Agent already listening on $BrowserAgentPort"
} else {
    $python = Get-VenvPython -ProjectDir $BrowserAgentDir
    if (-not $python) { throw "Python not found for Browser Agent" }
    Write-Step "Starting Browser Agent (python main.py)"
    $pids['browseragent'] = Start-Background -Name 'browseragent' -FilePath $python `
                              -Arguments @('main.py') -WorkingDirectory $BrowserAgentDir
    Wait-Port -Port $BrowserAgentPort -TimeoutSec 60 -Label 'Browser Agent' | Out-Null
}

# --- 3. Eye ------------------------------------------------------------------
if (Test-PortOpen -Port $EyePort) {
    Write-Step "Eye already listening on $EyePort"
} else {
    $python = Get-VenvPython -ProjectDir $EyeDir
    if (-not $python) { throw "Python not found for Eye" }
    Write-Step "Starting Eye (python main.py)"
    $pids['eye'] = Start-Background -Name 'eye' -FilePath $python `
                       -Arguments @('main.py') -WorkingDirectory $EyeDir
    Wait-Port -Port $EyePort -TimeoutSec 60 -Label 'Eye' | Out-Null
}

# --- 4. Workers (Celery) -----------------------------------------------------
$celeryRunning = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -match "celery.*worker" -and $_.CommandLine -match "workers"
}
if ($celeryRunning) {
    Write-Step "Workers (Celery) already running"
} else {
    $uv = Resolve-Exe -Name 'uv' -Fallbacks @("$env:USERPROFILE\.local\bin\uv.exe")
    if (-not $uv) { throw "uv not found on PATH" }
    Write-Step "Starting Workers (uv run celery worker)"
    $pids['workers'] = Start-Background -Name 'workers' -FilePath $uv `
                           -Arguments @('run', 'celery', '-A', 'workers.celery_app:celery_app', 'worker', '--loglevel=INFO', '--pool=solo', '-Q', 'job-applications') `
                           -WorkingDirectory $WorkersDir
    Start-Sleep -Seconds 3
}

# --- 5. Dashboard ------------------------------------------------------------
$npm = Resolve-Exe -Name 'npm.cmd' -Fallbacks @('C:\Program Files\nodejs\npm.cmd')
if (-not $npm) { throw "npm not found on PATH" }

if (-not $SkipBuild) {
    Write-Step "Building dashboard (npm run build)"
    $buildLog = Join-Path $LogDir 'dashboard-build.log'
    $build = Start-Process -FilePath $npm -ArgumentList 'run', 'build' `
                 -WorkingDirectory $DashboardDir -WindowStyle Hidden -Wait -PassThru `
                 -RedirectStandardOutput $buildLog `
                 -RedirectStandardError (Join-Path $LogDir 'dashboard-build.err.log')
    if ($build.ExitCode -ne 0) {
        Write-Warning "npm run build exited $($build.ExitCode) - serving previous dist. See $buildLog"
    }
}

if (Test-PortOpen -Port $DashboardPort) {
    Write-Step "Dashboard already listening on $DashboardPort"
} else {
    Write-Step "Starting Dashboard (npm start)"
    $pids['dashboard'] = Start-Background -Name 'dashboard' -FilePath $npm `
                               -Arguments @('start') -WorkingDirectory $DashboardDir
    Wait-Port -Port $DashboardPort -TimeoutSec 90 -Label 'Dashboard' | Out-Null
}

Save-Pids -Pids $pids

Write-Step "Stack started. Logs: $LogDir" 'Green'
Write-Step "Service URLs:" 'Cyan'
Write-Step "  nginx:          http://localhost:$NginxPort" 'Cyan'
Write-Step "  Browser Agent:  http://localhost:$BrowserAgentPort" 'Cyan'
Write-Step "  Eye API:        http://localhost:$EyePort" 'Cyan'
Write-Step "  Dashboard:      http://localhost:$DashboardPort" 'Cyan'