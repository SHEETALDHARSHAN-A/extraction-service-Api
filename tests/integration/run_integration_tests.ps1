# Integration Test Runner Script (PowerShell)
# This script runs the complete extraction flow integration tests

param(
    [string]$ApiBaseUrl = "http://localhost:8000",
    [string]$ApiKey = "tp-proj-dev-key-123",
    [int]$MaxWaitTime = 300
)

# Configuration
$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Integration Test Runner" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "API Base URL: $ApiBaseUrl"
Write-Host "API Key: $($ApiKey.Substring(0, [Math]::Min(20, $ApiKey.Length)))..."
Write-Host ""

# Function to check if services are healthy
function Test-ServicesHealthy {
    Write-Host "Checking service health..."
    
    try {
        $response = Invoke-WebRequest -Uri "$ApiBaseUrl/health" -Method Get -TimeoutSec 5 -UseBasicParsing
        
        if ($response.StatusCode -eq 200) {
            Write-Host "✅ Services are healthy" -ForegroundColor Green
            return $true
        }
    }
    catch {
        Write-Host "❌ Services are not healthy: $_" -ForegroundColor Red
        return $false
    }
    
    return $false
}

# Function to wait for services to be ready
function Wait-ForServices {
    Write-Host "Waiting for services to be ready..."
    
    $elapsed = 0
    while ($elapsed -lt $MaxWaitTime) {
        if (Test-ServicesHealthy) {
            return $true
        }
        
        Write-Host "  Waiting... ($elapsed/$MaxWaitTime seconds)"
        Start-Sleep -Seconds 5
        $elapsed += 5
    }
    
    Write-Host "❌ Services did not become healthy within $MaxWaitTime seconds" -ForegroundColor Red
    return $false
}

# Function to run tests with pytest
function Invoke-PytestTests {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "Running Integration Tests with pytest" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""
    
    $env:API_BASE_URL = $ApiBaseUrl
    $env:API_KEY = $ApiKey
    
    # Check if pytest is available
    $pytestCmd = Get-Command pytest -ErrorAction SilentlyContinue
    
    if ($pytestCmd) {
        try {
            & pytest tests/integration/test_complete_extraction_flow.py -v -s
            return $LASTEXITCODE -eq 0
        }
        catch {
            Write-Host "⚠️  pytest execution failed: $_" -ForegroundColor Yellow
            return $false
        }
    }
    else {
        Write-Host "⚠️  pytest not found, falling back to direct execution" -ForegroundColor Yellow
        return $false
    }
}

# Function to run tests directly
function Invoke-DirectTests {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "Running Integration Tests (Direct Execution)" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""
    
    $env:API_BASE_URL = $ApiBaseUrl
    $env:API_KEY = $ApiKey
    
    try {
        & python tests/integration/test_complete_extraction_flow.py
        return $LASTEXITCODE -eq 0
    }
    catch {
        Write-Host "❌ Direct execution failed: $_" -ForegroundColor Red
        return $false
    }
}

# Main execution
try {
    # Check if services are already healthy
    if (-not (Test-ServicesHealthy)) {
        Write-Host ""
        Write-Host "Services not healthy. Attempting to wait..." -ForegroundColor Yellow
        
        if (-not (Wait-ForServices)) {
            Write-Host ""
            Write-Host "❌ Cannot run tests: Services are not available" -ForegroundColor Red
            Write-Host ""
            Write-Host "To start services:"
            Write-Host "  cd docker"
            Write-Host "  docker-compose up -d"
            Write-Host ""
            Write-Host "Then wait for services to initialize (1-2 minutes)"
            exit 1
        }
    }
    
    Write-Host ""
    
    # Try pytest first, fall back to direct execution
    $success = $false
    
    if (Invoke-PytestTests) {
        $success = $true
    }
    elseif (Invoke-DirectTests) {
        $success = $true
    }
    
    if ($success) {
        Write-Host ""
        Write-Host "============================================================" -ForegroundColor Green
        Write-Host "✅ ALL INTEGRATION TESTS PASSED" -ForegroundColor Green
        Write-Host "============================================================" -ForegroundColor Green
        exit 0
    }
    else {
        Write-Host ""
        Write-Host "============================================================" -ForegroundColor Red
        Write-Host "❌ INTEGRATION TESTS FAILED" -ForegroundColor Red
        Write-Host "============================================================" -ForegroundColor Red
        exit 1
    }
}
catch {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Red
    Write-Host "❌ ERROR: $_" -ForegroundColor Red
    Write-Host "============================================================" -ForegroundColor Red
    exit 1
}
