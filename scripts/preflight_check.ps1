# ============================================
# IDEP Docker-only preflight checks
# ============================================

$ErrorActionPreference = "Stop"

function Write-Check { param([string]$Message) Write-Host "[CHECK] $Message" -ForegroundColor Cyan }
function Write-Pass  { param([string]$Message) Write-Host "[PASS]  $Message" -ForegroundColor Green }
function Write-Fail  { param([string]$Message) Write-Host "[FAIL]  $Message" -ForegroundColor Red }
function Write-Warn  { param([string]$Message) Write-Host "[WARN]  $Message" -ForegroundColor Yellow }

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$allPass = $true

Write-Host ""
Write-Host "IDEP preflight checks (Docker + GPU)" -ForegroundColor Cyan
Write-Host "Workspace: $workspaceRoot" -ForegroundColor DarkGray
Write-Host ""

Write-Check "Docker CLI"
try {
    $dockerVersion = docker --version
    if ($LASTEXITCODE -ne 0) { throw "docker command failed" }
    Write-Pass $dockerVersion
}
catch {
    Write-Fail "Docker CLI not available"
    $allPass = $false
}

Write-Check "Docker daemon"
try {
    docker ps *> $null
    if ($LASTEXITCODE -ne 0) { throw "docker daemon not reachable" }
    Write-Pass "Docker daemon is running"
}
catch {
    Write-Fail "Docker daemon is not reachable"
    $allPass = $false
}

Write-Check "Docker Compose"
try {
    $composeVersion = docker compose version
    if ($LASTEXITCODE -eq 0) {
        Write-Pass $composeVersion
    }
    else {
        $composeVersion = docker-compose --version
        if ($LASTEXITCODE -ne 0) { throw "Compose not found" }
        Write-Pass $composeVersion
    }
}
catch {
    Write-Fail "Docker Compose not found"
    $allPass = $false
}

Write-Check "GPU from Docker"
try {
    docker run --rm --gpus all nvidia/cuda:12.2.2-base-ubuntu22.04 nvidia-smi *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Pass "GPU is accessible in containers"
    }
    else {
        Write-Fail "GPU is not accessible in containers"
        Write-Warn "Enable GPU support in Docker Desktop and NVIDIA Container Toolkit"
        $allPass = $false
    }
}
catch {
    Write-Fail "GPU check command failed"
    $allPass = $false
}

Write-Check "Required project paths"
$requiredPaths = @(
    "docker\docker-compose.yml",
    "services\api-gateway\main.go",
    "services\triton-models\glm_ocr\1\model.py",
    "testfiles"
)
$missingPaths = @()
foreach ($relativePath in $requiredPaths) {
    $absolutePath = Join-Path $workspaceRoot $relativePath
    if (-not (Test-Path $absolutePath)) {
        $missingPaths += $relativePath
    }
}
if ($missingPaths.Count -eq 0) {
    Write-Pass "All required paths are present"
}
else {
    Write-Fail ("Missing paths: " + ($missingPaths -join ", "))
    $allPass = $false
}

Write-Check "Test files"
$testfilesDir = Join-Path $workspaceRoot "testfiles"
$pdfCount = (Get-ChildItem $testfilesDir -Filter "*.pdf" -ErrorAction SilentlyContinue | Measure-Object).Count
if ($pdfCount -gt 0) {
    Write-Pass "Found $pdfCount PDF files in testfiles"
}
else {
    Write-Warn "No PDF files found in testfiles"
}

Write-Host ""
if ($allPass) {
    Write-Host "Preflight PASSED" -ForegroundColor Green
    Write-Host "Run next: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\test_e2e_gpu.ps1" -ForegroundColor Green
    exit 0
}
else {
    Write-Host "Preflight FAILED" -ForegroundColor Red
    exit 1
}
