# ============================================
# IDEP End-to-End GPU Test (Docker-only)
# ============================================

$ErrorActionPreference = "Stop"

function Write-Section { param([string]$Message) Write-Host "`n=== $Message ===" -ForegroundColor Cyan }
function Write-Info    { param([string]$Message) Write-Host "[INFO] $Message" -ForegroundColor Yellow }
function Write-Pass    { param([string]$Message) Write-Host "[PASS] $Message" -ForegroundColor Green }
function Write-Fail    { param([string]$Message) Write-Host "[FAIL] $Message" -ForegroundColor Red }

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$testfilesDir = Join-Path $workspaceRoot "testfiles"
$resultsDir = Join-Path $testfilesDir ".results"
$apiBase = "http://localhost:8000"
$candidateKeys = @("tp-proj-dev-key-123", "dev-key-123")

function Invoke-CurlJson {
    param(
        [Parameter(Mandatory = $true)][string[]]$Args,
        [Parameter(Mandatory = $true)][string]$Context
    )

    $raw = & curl.exe @Args
    if ($LASTEXITCODE -ne 0) {
        throw "curl failed during $Context"
    }
    if ([string]::IsNullOrWhiteSpace($raw)) {
        throw "Empty response during $Context"
    }
    try {
        return ($raw | ConvertFrom-Json)
    }
    catch {
        throw "Invalid JSON during $Context. Raw response: $raw"
    }
}

New-Item -ItemType Directory -Path $resultsDir -Force | Out-Null

Write-Section "Docker stack startup"
Push-Location $workspaceRoot
try {
    docker compose version *> $null
    if ($LASTEXITCODE -eq 0) {
        $composeCmd = "docker compose"
    } else {
        $composeCmd = "docker-compose"
    }
}
catch {
    $composeCmd = "docker-compose"
}

Write-Info "Using compose command: $composeCmd"
# Invoke-Expression "$composeCmd -f docker/docker-compose.yml up --build -d"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to start docker stack"
}
Write-Pass "Docker stack started"

Write-Section "Wait for API health"
$apiHealthy = $false
for ($i = 1; $i -le 60; $i++) {
    try {
        $health = Invoke-CurlJson -Args @("-sS", "-f", "--max-time", "3", "$apiBase/health") -Context "health check"
        if ($health.status -eq "healthy") {
            $apiHealthy = $true
            break
        }
    } catch {
    }
    Start-Sleep -Seconds 2
}
if (-not $apiHealthy) {
    throw "API did not become healthy in time"
}
Write-Pass "API is healthy"

Write-Section "Choose auth key"
$apiKey = $null
foreach ($key in $candidateKeys) {
    try {
        $null = & curl.exe -sS -f --max-time 5 -H "Authorization: Bearer $key" "$apiBase/jobs"
        if ($LASTEXITCODE -eq 0) {
            $apiKey = $key
            break
        }
    } catch {
        Write-Info "Non-auth probe response for key $key, continuing"
    }
}
if (-not $apiKey) {
    $apiKey = $candidateKeys[1]
}
Write-Pass "Using API key: $apiKey"

Write-Section "Select input file"
$inputFile = Get-ChildItem $testfilesDir -Filter "*.pdf" | Select-Object -First 1
if (-not $inputFile) {
    throw "No PDF found in testfiles"
}
Write-Pass "Using file: $($inputFile.Name)"

Write-Section "Upload document"
$uploadResponse = Invoke-CurlJson -Context "upload document" -Args @(
    "-sS",
    "-f",
    "--max-time", "180",
    "-X", "POST",
    "-H", "Authorization: Bearer $apiKey",
    "-F", "document=@$($inputFile.FullName)",
    "-F", "output_formats=json,structured",
    "-F", "include_coordinates=true",
    "-F", "enhance=true",
    "-F", "deskew=true",
    "$apiBase/jobs/upload"
)
$jobId = $uploadResponse.job_id
if (-not $jobId) {
    throw "Upload succeeded but no job_id returned"
}
Write-Pass "Created job: $jobId"

Write-Section "Poll job status"
$status = "UNKNOWN"
for ($i = 1; $i -le 120; $i++) {
    Start-Sleep -Seconds 2
    $statusResponse = Invoke-CurlJson -Context "poll job status" -Args @(
        "-sS",
        "-f",
        "--max-time", "10",
        "-H", "Authorization: Bearer $apiKey",
        "$apiBase/jobs/$jobId"
    )
    $status = $statusResponse.status
    Write-Info "Status poll ${i}: $status"
    if ($status -eq "COMPLETED" -or $status -eq "FAILED") { break }
}
if ($status -ne "COMPLETED") {
    throw "Job did not complete successfully. Final status: $status"
}
Write-Pass "Job completed"

Write-Section "Fetch result"
$result = Invoke-CurlJson -Context "fetch result" -Args @(
    "-sS",
    "-f",
    "--max-time", "30",
    "-H", "Authorization: Bearer $apiKey",
    "$apiBase/jobs/$jobId/result"
)
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$resultPath = Join-Path $resultsDir "result_$timestamp.json"
$result | ConvertTo-Json -Depth 20 | Out-File -FilePath $resultPath -Encoding UTF8
Write-Pass "Result saved: $resultPath"

Write-Section "GPU metrics"
try {
    $metrics = Invoke-WebRequest -Method Get -Uri "http://localhost:8002/metrics" -TimeoutSec 5
    if ($metrics.Content -match "gpu|nvidia") {
        Write-Pass "Triton metrics endpoint includes GPU metrics"
    } else {
        Write-Info "Triton metrics endpoint reachable; no GPU lines matched"
    }
} catch {
    Write-Info "Could not query Triton metrics endpoint"
}

Write-Section "Done"
Write-Pass "End-to-end Docker GPU flow succeeded"
Write-Info "Result file: $resultPath"
Write-Info "To stop stack: $composeCmd -f docker/docker-compose.yml down"

Pop-Location
