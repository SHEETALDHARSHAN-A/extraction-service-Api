$ErrorActionPreference = "Stop"

function Write-Step { param([string]$Message) Write-Host "[STEP] $Message" -ForegroundColor Cyan }
function Write-Ok { param([string]$Message) Write-Host "[OK]   $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "[WARN] $Message" -ForegroundColor Yellow }

function Test-Port {
    param([int]$Port)
    return [bool](Test-NetConnection -ComputerName "localhost" -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue)
}

function Wait-Port {
    param(
        [int]$Port,
        [string]$Name,
        [int]$MaxSeconds = 45
    )

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $MaxSeconds) {
        if (Test-Port -Port $Port) {
            Write-Ok "$Name is listening on :$Port"
            return
        }
        Start-Sleep -Seconds 2
    }
    throw "$Name did not become ready on port $Port within $MaxSeconds seconds"
}

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$localRoot = Join-Path $workspaceRoot ".local"
$binDir = Join-Path $localRoot "bin"
$redisDir = Join-Path $localRoot "redis"
$dataDir = Join-Path $localRoot "data"
$minioDataDir = Join-Path $dataDir "minio"

$redisServerExe = Join-Path $redisDir "redis-server.exe"
$minioExe = Join-Path $binDir "minio.exe"
$temporalExe = Join-Path $binDir "temporal.exe"

if (-not (Test-Path $redisServerExe) -or -not (Test-Path $minioExe) -or -not (Test-Path $temporalExe)) {
    throw "Infra binaries are missing. Run scripts\setup_local_infra.ps1 first."
}

New-Item -ItemType Directory -Force -Path $minioDataDir | Out-Null

Write-Step "Starting Redis"
if (-not (Test-Port -Port 6379)) {
    Start-Process -FilePath $redisServerExe -ArgumentList "--port", "6379" -WorkingDirectory $redisDir | Out-Null
    Wait-Port -Port 6379 -Name "Redis"
} else {
    Write-Warn "Redis already running on :6379"
}

Write-Step "Starting MinIO"
if (-not (Test-Port -Port 9000)) {
    $minioCommand = "`$env:MINIO_ROOT_USER='minioadmin'; `$env:MINIO_ROOT_PASSWORD='minioadmin'; & '$minioExe' server '$minioDataDir' --address :9000 --console-address :9001"
    Start-Process -FilePath "powershell" -ArgumentList "-NoProfile", "-Command", $minioCommand | Out-Null
    Wait-Port -Port 9000 -Name "MinIO API"
    Wait-Port -Port 9001 -Name "MinIO Console"
} else {
    Write-Warn "MinIO already running on :9000"
}

Write-Step "Starting Temporal dev server"
if (-not (Test-Port -Port 7233)) {
    $temporalCommand = "& '$temporalExe' server start-dev --ip 127.0.0.1 --port 7233 --ui-port 8233"
    Start-Process -FilePath "powershell" -ArgumentList "-NoProfile", "-Command", $temporalCommand | Out-Null
    Wait-Port -Port 7233 -Name "Temporal Frontend"
    Wait-Port -Port 8233 -Name "Temporal UI"
} else {
    Write-Warn "Temporal already running on :7233"
}

Write-Host ""
Write-Ok "Local infra is ready"
Write-Host "Redis:      localhost:6379"
Write-Host "MinIO API:  http://localhost:9000"
Write-Host "MinIO UI:   http://localhost:9001"
Write-Host "Temporal:   localhost:7233"
Write-Host "TemporalUI: http://localhost:8233"
