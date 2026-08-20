#!/usr/bin/env pwsh
<#
.SYNOPSIS
    One-command local startup for AD Security Remediation Tracker (ADPA Tracker) on Windows.

.DESCRIPTION
    LOCAL-ONLY by design: backend binds 127.0.0.1 only, frontend binds
    localhost only (no --host flag), no telemetry/external services are
    started. See docs/LOCAL_DATA_SECURITY.md.

    NOTE: this script has not been tested on an actual Windows machine in
    this session (development happened on macOS/Linux) -- it mirrors
    start.sh's logic and steps exactly, but treat it as unverified until
    you've run it once yourself. Please report anything that doesn't work.

.EXAMPLE
    .\start.ps1
#>

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $ScriptDir "backend"
$FrontendDir = Join-Path $ScriptDir "frontend"
$VenvDir = Join-Path $BackendDir "venv"

$BackendProcess = $null
$FrontendProcess = $null

function Write-Info($msg)  { Write-Host "[start] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "[start] $msg" -ForegroundColor Green }
function Write-Err($msg)   { Write-Host "[start] $msg" -ForegroundColor Red }

function Get-FileHashHex($path) {
    (Get-FileHash -Path $path -Algorithm SHA256).Hash.ToLower()
}

function Stop-App {
    Write-Host ""
    Write-Info "Stopping ADPA Tracker..."
    if ($FrontendProcess -and -not $FrontendProcess.HasExited) {
        Write-Info "Stopping frontend (PID $($FrontendProcess.Id))..."
        Stop-Process -Id $FrontendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($BackendProcess -and -not $BackendProcess.HasExited) {
        Write-Info "Stopping backend (PID $($BackendProcess.Id))..."
        Stop-Process -Id $BackendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Ok "Stopped."
}

# Ctrl+C cleanup: PowerShell's default behavior on Ctrl+C is to stop the
# current pipeline, which unwinds through try/finally -- the main wait loop
# below is wrapped in try/finally calling Stop-App for exactly this reason.
# This is the standard, reliable pattern (avoids brittle event-registration
# scoping issues). If Ctrl+C ever doesn't clean up in your PowerShell host,
# run .\stop.ps1 as a fallback.

# ---------------------------------------------------------------------------
# 1. Verify required tools
# ---------------------------------------------------------------------------

Write-Info "Checking required tools..."
$missing = @()
foreach ($tool in @("python", "node", "npm")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        # also try python3, common on some Windows setups
        if ($tool -eq "python" -and (Get-Command "python3" -ErrorAction SilentlyContinue)) {
            continue
        }
        $missing += $tool
    }
}
if ($missing.Count -gt 0) {
    Write-Err "Missing required tool(s): $($missing -join ', ')"
    Write-Err "Install them, then re-run .\start.ps1."
    exit 1
}
$PythonCmd = if (Get-Command "python" -ErrorAction SilentlyContinue) { "python" } else { "python3" }
Write-Ok "$PythonCmd, node, npm found."

# ---------------------------------------------------------------------------
# 2-3. Create + activate backend venv
# ---------------------------------------------------------------------------

if (-not (Test-Path $VenvDir)) {
    Write-Info "Creating backend/venv (first run)..."
    & $PythonCmd -m venv $VenvDir
} else {
    Write-Info "backend/venv already exists, reusing it."
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip = Join-Path $VenvDir "Scripts\pip.exe"
$VenvAlembic = Join-Path $VenvDir "Scripts\alembic.exe"
$VenvUvicorn = Join-Path $VenvDir "Scripts\uvicorn.exe"

# ---------------------------------------------------------------------------
# 4. Install backend requirements only when needed
# ---------------------------------------------------------------------------

$ReqFile = Join-Path $BackendDir "requirements.txt"
$ReqStamp = Join-Path $VenvDir ".requirements.sha256"
$CurrentReqHash = Get-FileHashHex $ReqFile
$NeedsBackendInstall = $true
if (Test-Path $ReqStamp) {
    $StampedHash = Get-Content $ReqStamp -Raw
    if ($StampedHash.Trim() -eq $CurrentReqHash) { $NeedsBackendInstall = $false }
}
if ($NeedsBackendInstall) {
    Write-Info "Installing backend dependencies (requirements.txt changed or first run)..."
    & $VenvPip install -q --upgrade pip
    & $VenvPip install -q -r $ReqFile
    Set-Content -Path $ReqStamp -Value $CurrentReqHash -NoNewline
    Write-Ok "Backend dependencies installed."
} else {
    Write-Info "Backend dependencies already up to date, skipping install."
}

# ---------------------------------------------------------------------------
# 5. Install frontend dependencies only when needed
# ---------------------------------------------------------------------------

$LockFile = Join-Path $FrontendDir "package-lock.json"
$NodeModules = Join-Path $FrontendDir "node_modules"
$LockStamp = Join-Path $NodeModules ".package-lock.sha256"
$CurrentLockHash = if (Test-Path $LockFile) { Get-FileHashHex $LockFile } else { "no-lockfile" }
$NeedsFrontendInstall = $true
if ((Test-Path $NodeModules) -and (Test-Path $LockStamp)) {
    $StampedLockHash = Get-Content $LockStamp -Raw
    if ($StampedLockHash.Trim() -eq $CurrentLockHash) { $NeedsFrontendInstall = $false }
}
if ($NeedsFrontendInstall) {
    Write-Info "Installing frontend dependencies (package-lock.json changed or first run)..."
    Push-Location $FrontendDir
    npm install --no-fund --no-audit --loglevel=error
    Pop-Location
    Set-Content -Path $LockStamp -Value $CurrentLockHash -NoNewline
    Write-Ok "Frontend dependencies installed."
} else {
    Write-Info "Frontend dependencies already up to date, skipping install."
}

# ---------------------------------------------------------------------------
# 6. Ensure DATABASE_URL (SQLite, local-only dev database)
# ---------------------------------------------------------------------------

if (-not $env:DATABASE_URL) { $env:DATABASE_URL = "sqlite:///./app.db" }
if (-not $env:LOCAL_ONLY) { $env:LOCAL_ONLY = "true" }
Write-Info "DATABASE_URL=$($env:DATABASE_URL)"

# ---------------------------------------------------------------------------
# 7. Run migrations
# ---------------------------------------------------------------------------

Write-Info "Running database migrations..."
Push-Location $BackendDir
& $VenvAlembic upgrade head
Pop-Location

# ---------------------------------------------------------------------------
# 8-9. Security preflight -- stop immediately on failure
# ---------------------------------------------------------------------------

Write-Info "Running local security preflight..."
& $VenvPython (Join-Path $ScriptDir "scripts\local_security_preflight.py")
if ($LASTEXITCODE -ne 0) {
    Write-Err "Security preflight FAILED -- see output above."
    Write-Err "The application will NOT start until this passes. Fix the issue and re-run .\start.ps1."
    exit 1
}

# ---------------------------------------------------------------------------
# Port-conflict check
# ---------------------------------------------------------------------------

function Test-PortBusy($port) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $conn
}
if ((Test-PortBusy 8000) -or (Test-PortBusy 5173)) {
    Write-Err "Port 8000 or 5173 is already in use -- a previous run may still be active."
    Write-Err "Run .\stop.ps1 (or stop.sh) to clean it up, then re-run .\start.ps1."
    exit 1
}

# ---------------------------------------------------------------------------
# 10. Start backend on 127.0.0.1:8000 (never 0.0.0.0)
# ---------------------------------------------------------------------------

Write-Info "Starting backend on http://127.0.0.1:8000 ..."
$BackendProcess = Start-Process -FilePath $VenvUvicorn `
    -ArgumentList "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
    -WorkingDirectory $BackendDir `
    -RedirectStandardOutput (Join-Path $ScriptDir ".backend.log") `
    -RedirectStandardError (Join-Path $ScriptDir ".backend.err.log") `
    -PassThru -WindowStyle Hidden

$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 1
        if ($resp.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
    Start-Sleep -Milliseconds 500
}
if (-not $ready) {
    Write-Err "Backend did not become ready. Check .backend.log / .backend.err.log for details."
    Stop-App
    exit 1
}
Write-Ok "Backend is up."

# ---------------------------------------------------------------------------
# 11. Start frontend on localhost only (no --host flag => Vite default)
# ---------------------------------------------------------------------------

Write-Info "Starting frontend on http://localhost:5173 ..."
$VitePath = Join-Path $FrontendDir "node_modules\.bin\vite.cmd"
$FrontendProcess = Start-Process -FilePath $VitePath `
    -ArgumentList "--port", "5173" `
    -WorkingDirectory $FrontendDir `
    -RedirectStandardOutput (Join-Path $ScriptDir ".frontend.log") `
    -RedirectStandardError (Join-Path $ScriptDir ".frontend.err.log") `
    -PassThru -WindowStyle Hidden

$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -TimeoutSec 1
        if ($resp.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
    Start-Sleep -Milliseconds 500
}
if (-not $ready) {
    Write-Err "Frontend did not become ready. Check .frontend.log / .frontend.err.log for details."
    Stop-App
    exit 1
}

# ---------------------------------------------------------------------------
# 12. Success message
# ---------------------------------------------------------------------------

Write-Host ""
Write-Ok "ADPA Tracker is running at http://localhost:5173"
Write-Info "Backend API + docs: http://127.0.0.1:8000/docs"
Write-Info "Press Ctrl+C to stop."
Write-Host ""

# ---------------------------------------------------------------------------
# 13-14. Keep both processes managed; clean shutdown on Ctrl+C
# ---------------------------------------------------------------------------

try {
    while (-not $BackendProcess.HasExited -and -not $FrontendProcess.HasExited) {
        Start-Sleep -Seconds 1
    }
} finally {
    Stop-App
}
