#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Stops any stale ADPA Tracker backend/frontend processes on Windows.

.DESCRIPTION
    Only touches ports 8000 and 5173. Mirrors stop.sh.
    NOTE: not tested on an actual Windows machine in this session.
#>

function Write-Info($msg) { Write-Host "[stop] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[stop] $msg" -ForegroundColor Green }

$foundAny = $false
foreach ($port in @(8000, 5173)) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $conns) {
        $foundAny = $true
        Write-Info "Stopping process on port $port (PID $($conn.OwningProcess))..."
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}

if (-not $foundAny) {
    Write-Ok "Nothing running on ports 8000 or 5173."
} else {
    Write-Ok "Done."
}
