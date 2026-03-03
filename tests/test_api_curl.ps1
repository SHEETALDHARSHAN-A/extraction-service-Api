# GLM-OCR API Test Script with curl (PowerShell)
# Tests the complete API workflow with GPU-accelerated document extraction

$ErrorActionPreference = "Stop"

# Configuration
$API_BASE = "http://localhost:8000"
$API_KEY = "tp-proj-dev-key-123"
$TEST_FILE = "test_invoice_local.png"

# Check if test file exists
if (-not (Test-Path $TEST_FILE)) {
    Write-Host "❌ Test file not found: $TEST_FILE" -ForegroundColor Red
    Write-Host "Available test files:"
    Get-ChildItem testfiles\*.pdf, testfiles\*.png -ErrorAction SilentlyContinue
    exit 1
}

Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Yellow
Write-Host "  GLM-OCR API Test - Full Workflow with GPU" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Yellow
Write-Host ""

# Step 1: Health Check
Write-Host "[1/6] Health Check" -ForegroundColor Yellow
$healthResponse = curl.exe -s "$API_BASE/health"
$healthJson = $healthResponse | ConvertFrom-Json

if ($healthJson.status -eq "healthy") {
    Write-Host "✅ API Gateway is healthy" -ForegroundColor Green
    $healthResponse | ConvertFrom-Json | ConvertTo-Json -Depth 10
} else {
    Write-Host "❌ API Gateway health check failed" -ForegroundColor Red
    Write-Host $healthResponse
    exit 1
}
Write-Host ""

# Step 2: Upload Document with JSON output format
Write-Host "[2/6] Uploading document for extraction (JSON format)" -ForegroundColor Yellow
Write-Host "File: $TEST_FILE"
Write-Host "Output format: json"
Write-Host "Options: include_coordinates=true, precision_mode=high"
Write-Host ""

$uploadResponse = curl.exe -s -X POST "$API_BASE/jobs/upload" `
  -H "Authorization: Bearer $API_KEY" `
  -F "document=@$TEST_FILE" `
  -F "output_formats=json" `
  -F "include_coordinates=true" `
  -F "precision_mode=high"

$uploadJson = $uploadResponse | ConvertFrom-Json
$uploadJson | ConvertTo-Json -Depth 10

$JOB_ID = $uploadJson.job_id

if (-not $JOB_ID) {
    Write-Host "❌ Failed to get job_id from upload response" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Document uploaded successfully" -ForegroundColor Green
Write-Host "Job ID: $JOB_ID" -ForegroundColor Green
Write-Host ""

# Step 3: Poll job status
Write-Host "[3/6] Polling job status" -ForegroundColor Yellow
$MAX_ATTEMPTS = 60
$ATTEMPT = 0
$STATUS = "PROCESSING"

while ($STATUS -eq "PROCESSING" -or $STATUS -eq "UPLOADED") {
    $ATTEMPT++
    
    if ($ATTEMPT -gt $MAX_ATTEMPTS) {
        Write-Host "❌ Timeout waiting for job completion ($MAX_ATTEMPTS attempts)" -ForegroundColor Red
        exit 1
    }
    
    $statusResponse = curl.exe -s "$API_BASE/jobs/$JOB_ID" `
      -H "Authorization: Bearer $API_KEY"
    
    $statusJson = $statusResponse | ConvertFrom-Json
    $STATUS = $statusJson.status
    
    Write-Host "Attempt $ATTEMPT/$MAX_ATTEMPTS`: Status = $STATUS" -ForegroundColor Yellow
    
    if ($STATUS -eq "COMPLETED") {
        Write-Host "✅ Job completed successfully!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Full status response:"
        $statusJson | ConvertTo-Json -Depth 10
        break
    } elseif ($STATUS -eq "FAILED") {
        Write-Host "❌ Job failed" -ForegroundColor Red
        $statusJson | ConvertTo-Json -Depth 10
        exit 1
    }
    
    Start-Sleep -Seconds 2
}
Write-Host ""

# Step 4: Get result
Write-Host "[4/6] Retrieving extraction result" -ForegroundColor Yellow
$RESULT_FILE = "result_$JOB_ID.json"

curl.exe -s "$API_BASE/jobs/$JOB_ID/result" `
  -H "Authorization: Bearer $API_KEY" `
  -o $RESULT_FILE

if (Test-Path $RESULT_FILE) {
    Write-Host "✅ Result downloaded: $RESULT_FILE" -ForegroundColor Green
    Write-Host ""
    Write-Host "Result preview:"
    $resultContent = Get-Content $RESULT_FILE -Raw | ConvertFrom-Json
    $resultContent | ConvertTo-Json -Depth 10 | Select-Object -First 50
    Write-Host ""
    Write-Host "... (truncated, see $RESULT_FILE for full output)" -ForegroundColor Yellow
} else {
    Write-Host "❌ Failed to download result" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Step 5: Test with custom prompt
Write-Host "[5/6] Testing with custom prompt" -ForegroundColor Yellow
$CUSTOM_PROMPT = "Extract all text from this document and identify any invoice numbers, dates, and amounts."

$customResponse = curl.exe -s -X POST "$API_BASE/jobs/upload" `
  -H "Authorization: Bearer $API_KEY" `
  -F "document=@$TEST_FILE" `
  -F "prompt=$CUSTOM_PROMPT" `
  -F "include_coordinates=true"

$customJson = $customResponse | ConvertFrom-Json
$customJson | ConvertTo-Json -Depth 10

$CUSTOM_JOB_ID = $customJson.job_id

if ($CUSTOM_JOB_ID) {
    Write-Host "✅ Custom prompt job created: $CUSTOM_JOB_ID" -ForegroundColor Green
} else {
    Write-Host "❌ Failed to create custom prompt job" -ForegroundColor Red
}
Write-Host ""

# Step 6: Test with structured output (all formats)
Write-Host "[6/6] Testing with structured output (all formats)" -ForegroundColor Yellow

$structuredResponse = curl.exe -s -X POST "$API_BASE/jobs/upload" `
  -H "Authorization: Bearer $API_KEY" `
  -F "document=@$TEST_FILE" `
  -F "output_formats=structured" `
  -F "include_coordinates=true" `
  -F "include_word_confidence=true" `
  -F "include_page_layout=true" `
  -F "granularity=word"

$structuredJson = $structuredResponse | ConvertFrom-Json
$structuredJson | ConvertTo-Json -Depth 10

$STRUCTURED_JOB_ID = $structuredJson.job_id

if ($STRUCTURED_JOB_ID) {
    Write-Host "✅ Structured output job created: $STRUCTURED_JOB_ID" -ForegroundColor Green
} else {
    Write-Host "❌ Failed to create structured output job" -ForegroundColor Red
}
Write-Host ""

# Summary
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Yellow
Write-Host "✅ API Test Complete!" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Yellow
Write-Host ""
Write-Host "Jobs created:"
Write-Host "  1. JSON extraction: $JOB_ID (COMPLETED)"
Write-Host "  2. Custom prompt: $CUSTOM_JOB_ID"
Write-Host "  3. Structured output: $STRUCTURED_JOB_ID"
Write-Host ""
Write-Host "Result saved to: $RESULT_FILE"
Write-Host ""
Write-Host "To check other jobs:"
Write-Host "  curl.exe $API_BASE/jobs/$CUSTOM_JOB_ID -H `"Authorization: Bearer $API_KEY`""
Write-Host "  curl.exe $API_BASE/jobs/$STRUCTURED_JOB_ID -H `"Authorization: Bearer $API_KEY`""
Write-Host ""
Write-Host "To get their results (once completed):"
Write-Host "  curl.exe $API_BASE/jobs/$CUSTOM_JOB_ID/result -H `"Authorization: Bearer $API_KEY`" -o custom_result.json"
Write-Host "  curl.exe $API_BASE/jobs/$STRUCTURED_JOB_ID/result -H `"Authorization: Bearer $API_KEY`" -o structured_result.json"
Write-Host ""
