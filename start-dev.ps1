# Starts the full dev stack: PostgreSQL (portable), FastAPI backend, Vite frontend.
# Usage: powershell -ExecutionPolicy Bypass -File .\start-dev.ps1

$root = $PSScriptRoot
$pgBin = "C:\Users\PC\tools\pg17b\pgsql\bin"
$pgData = "C:\Users\PC\tools\pg17b\data"

# 1. PostgreSQL — start if not already accepting connections
& "$pgBin\pg_isready.exe" -p 5432 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Starting PostgreSQL..."
    & "$pgBin\pg_ctl.exe" -D $pgData -l "C:\Users\PC\tools\pg17b\pg.log" -o "-p 5432" start
    Start-Sleep -Seconds 3
} else {
    Write-Host "PostgreSQL already running."
}

# 2. Backend (FastAPI on :8000)
$backendUp = $false
try { Invoke-RestMethod -Uri http://localhost:8000/healthz -TimeoutSec 3 | Out-Null; $backendUp = $true } catch {}
if (-not $backendUp) {
    Write-Host "Starting backend on http://localhost:8000 ..."
    Start-Process -FilePath "$root\backend\.venv\Scripts\python.exe" `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--port", "8000" `
        -WorkingDirectory "$root\backend" -WindowStyle Hidden
} else {
    Write-Host "Backend already running."
}

# 3. Frontend (Vite on :5173)
$frontendUp = $false
try { Invoke-WebRequest -Uri http://localhost:5173/ -UseBasicParsing -TimeoutSec 3 | Out-Null; $frontendUp = $true } catch {}
if (-not $frontendUp) {
    Write-Host "Starting frontend on http://localhost:5173 ..."
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "npm run dev" `
        -WorkingDirectory "$root\frontend" -WindowStyle Hidden
} else {
    Write-Host "Frontend already running."
}

Start-Sleep -Seconds 8
try {
    $h = Invoke-RestMethod -Uri http://localhost:8000/healthz -TimeoutSec 10
    Write-Host "Backend:  ok" -ForegroundColor Green
} catch { Write-Host "Backend:  not responding yet (give it a few more seconds)" -ForegroundColor Yellow }
try {
    Invoke-WebRequest -Uri http://localhost:5173/ -UseBasicParsing -TimeoutSec 10 | Out-Null
    Write-Host "Frontend: ok -> http://localhost:5173" -ForegroundColor Green
} catch { Write-Host "Frontend: not responding yet (give it a few more seconds)" -ForegroundColor Yellow }
