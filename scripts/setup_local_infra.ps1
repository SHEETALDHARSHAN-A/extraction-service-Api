$ErrorActionPreference = "Stop"

function Write-Step { param([string]$Message) Write-Host "[STEP] $Message" -ForegroundColor Cyan }
function Write-Info { param([string]$Message) Write-Host "[INFO] $Message" -ForegroundColor DarkCyan }
function Write-Ok { param([string]$Message) Write-Host "[OK]   $Message" -ForegroundColor Green }

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$localRoot = Join-Path $workspaceRoot ".local"
$binDir = Join-Path $localRoot "bin"
$downloadsDir = Join-Path $localRoot "downloads"
$redisDir = Join-Path $localRoot "redis"
$dataDir = Join-Path $localRoot "data"
$minioDataDir = Join-Path $dataDir "minio"

New-Item -ItemType Directory -Force -Path $binDir, $downloadsDir, $redisDir, $minioDataDir | Out-Null

Write-Step "Installing Temporal CLI"
$temporalExe = Join-Path $binDir "temporal.exe"
if (-not (Test-Path $temporalExe)) {
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/temporalio/cli/releases/latest" -Headers @{ "User-Agent" = "PowerShell" }
    $asset = $release.assets | Where-Object { $_.name -like "*windows_amd64.zip" } | Select-Object -First 1
    if (-not $asset) {
        throw "Unable to find Temporal CLI windows_amd64.zip release asset"
    }
    $temporalZip = Join-Path $downloadsDir "temporal_cli.zip"
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $temporalZip -UseBasicParsing
    Expand-Archive -Path $temporalZip -DestinationPath $binDir -Force
    Remove-Item $temporalZip -Force
    Write-Ok "Temporal CLI installed: $temporalExe"
} else {
    Write-Info "Temporal CLI already present"
}

Write-Step "Installing MinIO server"
$minioExe = Join-Path $binDir "minio.exe"
if (-not (Test-Path $minioExe)) {
    Invoke-WebRequest -Uri "https://dl.min.io/server/minio/release/windows-amd64/minio.exe" -OutFile $minioExe -UseBasicParsing
    Write-Ok "MinIO installed: $minioExe"
} else {
    Write-Info "MinIO already present"
}

Write-Step "Installing Redis for Windows"
$redisServerExe = Join-Path $redisDir "redis-server.exe"
if (-not (Test-Path $redisServerExe)) {
    $redisZip = Join-Path $downloadsDir "redis.zip"
    $redisUrl = "https://github.com/tporadowski/redis/releases/download/v5.0.14.1/Redis-x64-5.0.14.1.zip"
    Invoke-WebRequest -Uri $redisUrl -OutFile $redisZip -UseBasicParsing
    Expand-Archive -Path $redisZip -DestinationPath $redisDir -Force
    Remove-Item $redisZip -Force
    Write-Ok "Redis installed: $redisServerExe"
} else {
    Write-Info "Redis already present"
}

Write-Step "Verifying local infra binaries"
if (-not (Test-Path $temporalExe)) { throw "Temporal CLI installation failed" }
if (-not (Test-Path $minioExe)) { throw "MinIO installation failed" }
if (-not (Test-Path $redisServerExe)) { throw "Redis installation failed" }

Write-Host ""
Write-Ok "Local infra setup complete"
Write-Info "Binaries:"
Write-Info "  Temporal: $temporalExe"
Write-Info "  MinIO:    $minioExe"
Write-Info "  Redis:    $redisServerExe"
