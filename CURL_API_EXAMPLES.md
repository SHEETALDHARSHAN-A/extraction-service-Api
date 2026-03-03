# GLM-OCR API - curl Examples

Quick reference for testing the GLM-OCR document extraction API with curl commands.

## Prerequisites

1. Start the services:
   ```bash
   docker-compose -f docker/docker-compose.yml up -d
   ```

2. Wait for services to be ready (~30-60 seconds)

3. Verify health:
   ```bash
   curl http://localhost:8000/health
   ```

## API Key

All requests require authentication with Bearer token:
```
Authorization: Bearer tp-proj-dev-key-123
```

## Basic Examples

### 1. Simple Text Extraction

```bash
curl -X POST http://localhost:8000/jobs/upload \
  -H "Authorization: Bearer tp-proj-dev-key-123" \
  -F "document=@testfiles/test_invoice_local.png"
```

**Response:**
```json
{
  "job_id": "abc-123-...",
  "filename": "test_invoice_local.png",
  "status": "PROCESSING",
  "workflow_id": "doc-processing-abc-123-...",
  "output_formats": "text",
  "result_url": "/jobs/abc-123-.../result",
  "status_url": "/jobs/abc-123-..."
}
```

### 2. JSON Format with Coordinates

```bash
curl -X POST http://localhost:8000/jobs/upload \
  -H "Authorization: Bearer tp-proj-dev-key-123" \
  -F "document=@testfiles/test_invoice_local.png" \
  -F "output_formats=json" \
  -F "include_coordinates=true"
```

### 3. Multiple Output Formats

```bash
curl -X POST http://localhost:8000/jobs/upload \
  -H "Authorization: Bearer tp-proj-dev-key-123" \
  -F "document=@testfiles/test_invoice_local.png" \
  -F "output_formats=json,markdown,table"
```

### 4. Custom Prompt

```bash
curl -X POST http://localhost:8000/jobs/upload \
  -H "Authorization: Bearer tp-proj-dev-key-123" \
  -F "document=@testfiles/test_invoice_local.png" \
  -F "prompt=Extract all invoice details including invoice number, date, vendor, and line items. Return as JSON."
```

### 5. Structured Output (All Formats)

```bash
curl -X POST http://localhost:8000/jobs/upload \
  -H "Authorization: Bearer tp-proj-dev-key-123" \
  -F "document=@testfiles/test_invoice_local.png" \
  -F "output_formats=structured" \
  -F "include_coordinates=true" \
  -F "include_word_confidence=true" \
  -F "include_page_layout=true" \
  -F "granularity=word"
```

### 6. High Precision Mode

```bash
curl -X POST http://localhost:8000/jobs/upload \
  -H "Authorization: Bearer tp-proj-dev-key-123" \
  -F "document=@testfiles/test_invoice_local.png" \
  -F "output_formats=json" \
  -F "precision_mode=high" \
  -F "include_coordinates=true"
```

### 7. With Field Extraction

```bash
curl -X POST http://localhost:8000/jobs/upload \
  -H "Authorization: Bearer tp-proj-dev-key-123" \
  -F "document=@testfiles/test_invoice_local.png" \
  -F "output_formats=json" \
  -F "extract_fields=invoice_number,date,total_amount,vendor"
```

## Checking Job Status

### Get Job Status

```bash
curl http://localhost:8000/jobs/<JOB_ID> \
  -H "Authorization: Bearer tp-proj-dev-key-123"
```

**Response:**
```json
{
  "id": "abc-123-...",
  "filename": "test_invoice_local.png",
  "status": "COMPLETED",
  "confidence": 0.95,
  "page_count": 1,
  "result_path": "results/abc-123-.../result.json",
  "created_at": "2026-03-03T...",
  "updated_at": "2026-03-03T..."
}
```

### Get Result

```bash
curl http://localhost:8000/jobs/<JOB_ID>/result \
  -H "Authorization: Bearer tp-proj-dev-key-123" \
  -o result.json
```

### List All Jobs

```bash
curl http://localhost:8000/jobs \
  -H "Authorization: Bearer tp-proj-dev-key-123"
```

## Batch Upload

### Upload Multiple Documents

```bash
curl -X POST http://localhost:8000/jobs/batch \
  -H "Authorization: Bearer tp-proj-dev-key-123" \
  -F "documents=@testfiles/invoice1.pdf" \
  -F "documents=@testfiles/invoice2.pdf" \
  -F "documents=@testfiles/receipt.png" \
  -F "output_formats=json" \
  -F "include_coordinates=true"
```

**Response:**
```json
{
  "batch_id": "b5c6d7e8-...",
  "total": 3,
  "succeeded": 3,
  "failed": 0,
  "output_formats": "json",
  "status_url": "/jobs/batch/b5c6d7e8-...",
  "jobs": [
    {"job_id": "aaa...", "filename": "invoice1.pdf", "status": "PROCESSING"},
    {"job_id": "bbb...", "filename": "invoice2.pdf", "status": "PROCESSING"},
    {"job_id": "ccc...", "filename": "receipt.png", "status": "PROCESSING"}
  ]
}
```

### Check Batch Status

```bash
curl http://localhost:8000/jobs/batch/<BATCH_ID> \
  -H "Authorization: Bearer tp-proj-dev-key-123"
```

### Filter Batch by Status

```bash
# Only completed files
curl "http://localhost:8000/jobs/batch/<BATCH_ID>?status=COMPLETED" \
  -H "Authorization: Bearer tp-proj-dev-key-123"

# Only failed files
curl "http://localhost:8000/jobs/batch/<BATCH_ID>?status=FAILED" \
  -H "Authorization: Bearer tp-proj-dev-key-123"
```

## Advanced Options

### All Available Parameters

```bash
curl -X POST http://localhost:8000/jobs/upload \
  -H "Authorization: Bearer tp-proj-dev-key-123" \
  -F "document=@testfiles/test_invoice_local.png" \
  -F "output_formats=structured" \
  -F "prompt=" \
  -F "include_coordinates=true" \
  -F "include_word_confidence=true" \
  -F "include_line_confidence=true" \
  -F "include_page_layout=true" \
  -F "language=auto" \
  -F "granularity=word" \
  -F "redact_pii=false" \
  -F "deskew=true" \
  -F "enhance=true" \
  -F "max_pages=0" \
  -F "temperature=0.0" \
  -F "max_tokens=4096" \
  -F "precision_mode=high" \
  -F "extract_fields=invoice_number,date,amount"
```

## Monitoring & Admin

### System Stats

```bash
curl http://localhost:8000/admin/stats \
  -H "Authorization: Bearer tp-proj-dev-key-123"
```

### Cache Stats

```bash
curl http://localhost:8000/admin/cache \
  -H "Authorization: Bearer tp-proj-dev-key-123"
```

### Prometheus Metrics

```bash
curl http://localhost:8000/metrics
```

## PowerShell Examples (Windows)

### Simple Upload

```powershell
curl.exe -X POST http://localhost:8000/jobs/upload `
  -H "Authorization: Bearer tp-proj-dev-key-123" `
  -F "document=@testfiles\test_invoice_local.png" `
  -F "output_formats=json"
```

### Get Result

```powershell
curl.exe http://localhost:8000/jobs/<JOB_ID>/result `
  -H "Authorization: Bearer tp-proj-dev-key-123" `
  -o result.json
```

## Complete Workflow Example

```bash
# 1. Upload document
RESPONSE=$(curl -s -X POST http://localhost:8000/jobs/upload \
  -H "Authorization: Bearer tp-proj-dev-key-123" \
  -F "document=@testfiles/test_invoice_local.png" \
  -F "output_formats=json" \
  -F "include_coordinates=true")

# 2. Extract job ID
JOB_ID=$(echo $RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['job_id'])")
echo "Job ID: $JOB_ID"

# 3. Poll status (wait for completion)
while true; do
  STATUS=$(curl -s http://localhost:8000/jobs/$JOB_ID \
    -H "Authorization: Bearer tp-proj-dev-key-123" \
    | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])")
  
  echo "Status: $STATUS"
  
  if [ "$STATUS" = "COMPLETED" ]; then
    break
  elif [ "$STATUS" = "FAILED" ]; then
    echo "Job failed!"
    exit 1
  fi
  
  sleep 2
done

# 4. Download result
curl -s http://localhost:8000/jobs/$JOB_ID/result \
  -H "Authorization: Bearer tp-proj-dev-key-123" \
  -o result.json

echo "Result saved to result.json"
cat result.json | python3 -m json.tool
```

## Automated Test Scripts

We've provided automated test scripts:

### Bash (Linux/Mac/WSL)
```bash
chmod +x test_api_curl.sh
./test_api_curl.sh
```

### PowerShell (Windows)
```powershell
.\test_api_curl.ps1
```

These scripts will:
1. Check API health
2. Upload a test document
3. Poll for completion
4. Download the result
5. Test custom prompts
6. Test structured output

## Troubleshooting

### "unauthorized" error
- Make sure you include the Authorization header
- Use the correct API key: `tp-proj-dev-key-123`

### "Job not found" error
- Check if the job ID is correct
- List all jobs: `curl http://localhost:8000/jobs -H "Authorization: Bearer tp-proj-dev-key-123"`

### Job stuck in PROCESSING
- Check Triton logs: `docker-compose -f docker/docker-compose.yml logs triton`
- Check worker logs: `docker-compose -f docker/docker-compose.yml logs temporal-worker`
- Verify GPU is available: `docker exec -it extraction-service-triton-1 nvidia-smi`

### Connection refused
- Make sure services are running: `docker-compose -f docker/docker-compose.yml ps`
- Check API gateway logs: `docker-compose -f docker/docker-compose.yml logs api-gateway`

## Expected Result Format

### JSON Output Example

```json
{
  "job_id": "abc-123-...",
  "model": "glm-ocr",
  "created_at": "2026-03-03T...",
  "processing_time_ms": 3200,
  "document_confidence": 0.93,
  "page_count": 1,
  "usage": {
    "prompt_tokens": 45,
    "completion_tokens": 512
  },
  "result": {
    "document_type": "invoice",
    "fields": {
      "invoice_number": "INV-2026-0042",
      "date": "2026-02-25",
      "vendor": "Acme Corp",
      "total_amount": "$1,358.02"
    },
    "line_items": [
      {
        "description": "Widget A",
        "quantity": 10,
        "unit_price": "$100.00",
        "total": "$1,000.00"
      }
    ]
  }
}
```

### With Coordinates

```json
{
  "result": {
    "document_type": "invoice",
    "fields": {
      "invoice_number": {
        "value": "INV-2026-0042",
        "bbox": [280, 100, 180, 25],
        "confidence": 0.97
      }
    }
  }
}
```

## GPU Verification

Check if GPU is being used:

```bash
# Inside Triton container
docker exec -it extraction-service-triton-1 nvidia-smi

# Check GPU metrics
curl http://localhost:8002/metrics | grep gpu
```

Expected: You should see GPU memory usage (2-3 GB) and the Triton process using the GPU.
