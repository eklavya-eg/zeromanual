<#
.SYNOPSIS
    Shared library for ZeroManual service stack management.
#>

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$StackRoot  = Split-Path -Parent $ScriptRoot
$LogDir     = Join-Path $StackRoot 'logs'
$PidFile    = Join-Path $LogDir 'pids.json'

# --- Pretty step output ------------------------------------------------------
function Write-Step {
    param([string]$Message, [string]$Color = 'Cyan')
    $prefix = "[$(Get-Date -Format 'HH:mm:ss')]"
    Write-Host "$prefix $Message" -ForegroundColor $Color
}

# --- PID persistence ---------------------------------------------------------
function Load-Pids {
    if (Test-Path -LiteralPath $PidFile) {
        try { return (Get-Content -Raw -LiteralPath $PidFile | ConvertFrom-Json) }
        catch { return @{} }
    }
    return @{}
}

function Save-Pids {
    param([hashtable]$Pids)
    if (-not (Test-Path -LiteralPath $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
    $Pids | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $PidFile -Encoding utf8
}

# --- Port check --------------------------------------------------------------
function Test-PortOpen {
    param([int]$Port, [string]$TargetHost = '127.0.0.1')
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $result = $tcp.BeginConnect($TargetHost, $Port, $null, $null)
        $success = $result.AsyncWaitHandle.WaitOne(500)
        $tcp.Close()
        return $success
    } catch { return $false }
}

function Wait-Port {
    param([int]$Port, [int]$TimeoutSec = 60, [string]$Label = 'service')
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while (-not (Test-PortOpen -Port $Port)) {
        if ((Get-Date) -ge $deadline) { throw "Timed out waiting for $Label on port $Port" }
        Start-Sleep -Seconds 2
    }
}

# --- Resolve executable ------------------------------------------------------
function Resolve-Exe {
    param([string]$Name, [string[]]$Fallbacks = @())
    $found = (Get-Command $Name -ErrorAction SilentlyContinue).Source
    if ($found) { return $found }
    foreach ($fb in $Fallbacks) {
        if (Test-Path -LiteralPath $fb) { return $fb }
    }
    return $null
}

# --- Start a background process with logging ---------------------------------
function Start-Background {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory
    )
    $stdoutLog = Join-Path $LogDir "$Name.out.log"
    $stderrLog = Join-Path $LogDir "$Name.err.log"

    # Build the argument string
    $argStr = $Arguments -join ' '

    # Use Start-Process with redirected output (PowerShell-native approach)
    $proc = Start-Process -FilePath $FilePath -ArgumentList $argStr `
               -WorkingDirectory $WorkingDirectory `
               -RedirectStandardOutput $stdoutLog `
               -RedirectStandardError $stderrLog `
               -WindowStyle Hidden `
               -PassThru

    return $proc.Id
}

# --- Stop a tracked process --------------------------------------------------
function Stop-Tracked {
    param([string]$Name, [int]$ProcId)
    try {
        $proc = Get-Process -Id $ProcId -ErrorAction SilentlyContinue
        if ($proc -and -not $proc.HasExited) {
            Write-Step "Stopping $Name (PID $ProcId)..."
            $proc.Kill()
            $proc.WaitForExit(5000)
        }
    } catch {
        Write-Warning "Failed to stop $Name (PID $ProcId): $_"
    }
}

# --- Get venv python path ----------------------------------------------------
function Get-VenvPython {
    param([string]$ProjectDir)
    $venvPython = Join-Path $ProjectDir '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $venvPython) {
        return $venvPython
    }
    # Fallback to system python
    return (Resolve-Exe -Name 'python')
}