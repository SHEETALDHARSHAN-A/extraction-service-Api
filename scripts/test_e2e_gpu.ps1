# ============================================
# IDEP End-to-End Docker Test (API -> Temporal -> Triton -> MinIO)
# Supports mock mode (fast, deterministic) and full GPU mode.
# ============================================

param(
    [ValidateSet("mock", "gpu")]
    [string]$Mode = "mock",
    [switch]$KeepRunning
)

$ErrorActionPreference = "Stop"

function Write-Section { param([string]$Message) Write-Host "`n=== $Message ===" -ForegroundColor Cyan }
function Write-Info    { param([string]$Message) Write-Host "[INFO] $Message" -ForegroundColor Yellow }
function Write-Pass    { param([string]$Message) Write-Host "[PASS] $Message" -ForegroundColor Green }
function Write-Fail    { param([string]$Message) Write-Host "[FAIL] $Message" -ForegroundColor Red }

function Assert-True {
    param(
        [string]$Name,
        [bool]$Condition,
        [string]$Detail = ""
    )
    if ($Condition) {
        Write-Pass $Name
    } else {
        if ($Detail) {
            throw "Assertion failed: $Name ($Detail)"
        }
        throw "Assertion failed: $Name"
    }
}

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

function Find-PropertyValueRecursive {
    param(
        $Object,
        [string]$PropertyName
    )
    if ($null -eq $Object) { return $null }

    if ($Object -is [System.Collections.IDictionary]) {
        if ($Object.Contains($PropertyName)) {
            return $Object[$PropertyName]
        }
        foreach ($k in $Object.Keys) {
            $found = Find-PropertyValueRecursive -Object $Object[$k] -PropertyName $PropertyName
            if ($null -ne $found) { return $found }
        }
        return $null
    }

    if ($Object -is [System.Collections.IEnumerable] -and -not ($Object -is [string])) {
        foreach ($item in $Object) {
            $found = Find-PropertyValueRecursive -Object $item -PropertyName $PropertyName
            if ($null -ne $found) { return $found }
        }
        return $null
    }

    $props = $Object.PSObject.Properties.Name
    if ($props -contains $PropertyName) {
        return $Object.$PropertyName
    }
    foreach ($p in $Object.PSObject.Properties) {
        $found = Find-PropertyValueRecursive -Object $p.Value -PropertyName $PropertyName
        if ($null -ne $found) { return $found }
    }
    return $null
}

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$testfilesDir = Join-Path $workspaceRoot "testfiles"
$resultsDir = Join-Path $testfilesDir ".results"
$apiBase = "http://localhost:8000"
$candidateKeys = @("tp-proj-dev-key-123", "dev-key-123")

New-Item -ItemType Directory -Path $resultsDir -Force | Out-Null

$composeFiles = @("-f", "docker/docker-compose.yml")
if ($Mode -eq "mock") {
    $composeFiles += @("-f", "docker/docker-compose.test.yml")
}

$services = @(
    "db", "redis", "minio", "temporal",
    "preprocessing-service", "postprocessing-service",
    "triton", "temporal-worker", "api-gateway"
)

Push-Location $workspaceRoot
try {
    Write-Section "Docker stack startup ($Mode mode)"
    & docker compose @composeFiles up --build -d @services
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to start docker stack"
    }
    Write-Pass "Docker stack started"

    Write-Section "Wait for API health"
    $apiHealthy = $false
    for ($i = 1; $i -le 90; $i++) {
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
        }
    }
    if (-not $apiKey) {
        throw "No working API key found"
    }
    Write-Pass "Using API key: $apiKey"

    Write-Section "Select input file"
    $inputFile = Get-ChildItem $testfilesDir -Filter "*.pdf" | Select-Object -First 1
    if (-not $inputFile) {
        throw "No PDF found in testfiles"
    }
    Write-Pass "Using file: $($inputFile.Name)"

    Write-Section "Upload document with precision + extract_fields"
    $uploadResponse = Invoke-CurlJson -Context "upload document" -Args @(
        "-sS",
        "-f",
        "--max-time", "180",
        "-X", "POST",
        "-H", "Authorization: Bearer $apiKey",
        "-F", "document=@$($inputFile.FullName)",
        "-F", "output_formats=structured",
        "-F", "include_coordinates=true",
        "-F", "include_word_confidence=true",
        "-F", "precision_mode=high",
        "-F", "extract_fields=date,amount",
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
    for ($i = 1; $i -le 180; $i++) {
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

    Write-Section "Fetch and validate result envelope"
    $result = Invoke-CurlJson -Context "fetch result" -Args @(
        "-sS",
        "-f",
        "--max-time", "30",
        "-H", "Authorization: Bearer $apiKey",
        "$apiBase/jobs/$jobId/result"
    )
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $resultPath = Join-Path $resultsDir "result_$timestamp.json"
    $result | ConvertTo-Json -Depth 60 | Out-File -FilePath $resultPath -Encoding UTF8
    Write-Pass "Result saved: $resultPath"

    Assert-True "result has model name" ($result.model -eq "zai-org/GLM-OCR") "Expected model=zai-org/GLM-OCR"
    Assert-True "result has page_count" ([int]$result.page_count -ge 1)
    Assert-True "result has precision_mode=high" ($result.precision_mode -eq "high")

    $bbox = Find-PropertyValueRecursive -Object $result -PropertyName "bbox_2d"
    Assert-True "bbox_2d exists somewhere in result" ($null -ne $bbox)
    if ($bbox -is [System.Collections.IEnumerable] -and -not ($bbox -is [string])) {
        $arr = @($bbox)
        Assert-True "bbox_2d has 4 values" ($arr.Count -eq 4)
        if ($arr.Count -eq 4) {
            Assert-True "bbox_2d uses x1,y1,x2,y2 ordering" ([int]$arr[2] -gt [int]$arr[0])
        }
    }

    $extractFieldsEcho = Find-PropertyValueRecursive -Object $result -PropertyName "extract_fields"
    Assert-True "extract_fields echoed in nested result" ($null -ne $extractFieldsEcho)
    if ($null -ne $extractFieldsEcho) {
        $echoArray = @($extractFieldsEcho)
        Assert-True "extract_fields includes date" ($echoArray -contains "date")
        Assert-True "extract_fields includes amount" ($echoArray -contains "amount")
    }

    Write-Section "Done"
    Write-Pass "End-to-end Docker flow succeeded ($Mode mode)"
    Write-Info "Result file: $resultPath"
}
catch {
    Write-Fail $_.Exception.Message
    Write-Info "Showing recent service logs for debugging"
    & docker compose @composeFiles logs --tail 120 api-gateway temporal-worker triton
    throw
}
finally {
    if (-not $KeepRunning) {
        Write-Section "Docker stack teardown"
        & docker compose @composeFiles down --remove-orphans
        if ($LASTEXITCODE -eq 0) {
            Write-Pass "Docker stack stopped"
        } else {
            Write-Info "docker compose down returned exit code $LASTEXITCODE"
        }
    } else {
        Write-Info "KeepRunning enabled: stack left running"
    }
    Pop-Location
}
