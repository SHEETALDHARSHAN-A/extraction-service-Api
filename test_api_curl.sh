#!/bin/bash

# GLM-OCR API Test Script with curl
# Tests the complete API workflow with GPU-accelerated document extraction

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
API_BASE="http://localhost:8000"
API_KEY="tp-proj-dev-key-123"
TEST_FILE="test_invoice_local.png"

# Check if test file exists
if [ ! -f "$TEST_FILE" ]; then
    echo -e "${RED}❌ Test file not found: $TEST_FILE${NC}"
    echo "Available test files:"
    ls -1 testfiles/*.pdf testfiles/*.png 2>/dev/null || echo "No test files found"
    exit 1
fi

echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}  GLM-OCR API Test - Full Workflow with GPU${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"
echo ""

# Step 1: Health Check
echo -e "${YELLOW}[1/6] Health Check${NC}"
HEALTH_RESPONSE=$(curl -s "$API_BASE/health")
if echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
    echo -e "${GREEN}✅ API Gateway is healthy${NC}"
    echo "$HEALTH_RESPONSE" | python3 -m json.tool
else
    echo -e "${RED}❌ API Gateway health check failed${NC}"
    echo "$HEALTH_RESPONSE"
    exit 1
fi
echo ""

# Step 2: Upload Document with JSON output format
echo -e "${YELLOW}[2/6] Uploading document for extraction (JSON format)${NC}"
echo "File: $TEST_FILE"
echo "Output format: json"
echo "Options: include_coordinates=true, precision_mode=high"
echo ""

UPLOAD_RESPONSE=$(curl -s -X POST "$API_BASE/jobs/upload" \
  -H "Authorization: Bearer $API_KEY" \
  -F "document=@$TEST_FILE" \
  -F "output_formats=json" \
  -F "include_coordinates=true" \
  -F "precision_mode=high")

echo "$UPLOAD_RESPONSE" | python3 -m json.tool

JOB_ID=$(echo "$UPLOAD_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('job_id', ''))")

if [ -z "$JOB_ID" ]; then
    echo -e "${RED}❌ Failed to get job_id from upload response${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Document uploaded successfully${NC}"
echo -e "Job ID: ${GREEN}$JOB_ID${NC}"
echo ""

# Step 3: Poll job status
echo -e "${YELLOW}[3/6] Polling job status${NC}"
MAX_ATTEMPTS=60
ATTEMPT=0
STATUS="PROCESSING"

while [ "$STATUS" = "PROCESSING" ] || [ "$STATUS" = "UPLOADED" ]; do
    ATTEMPT=$((ATTEMPT + 1))
    
    if [ $ATTEMPT -gt $MAX_ATTEMPTS ]; then
        echo -e "${RED}❌ Timeout waiting for job completion (${MAX_ATTEMPTS} attempts)${NC}"
        exit 1
    fi
    
    STATUS_RESPONSE=$(curl -s "$API_BASE/jobs/$JOB_ID" \
      -H "Authorization: Bearer $API_KEY")
    
    STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'UNKNOWN'))")
    
    echo -e "Attempt $ATTEMPT/$MAX_ATTEMPTS: Status = ${YELLOW}$STATUS${NC}"
    
    if [ "$STATUS" = "COMPLETED" ]; then
        echo -e "${GREEN}✅ Job completed successfully!${NC}"
        echo ""
        echo "Full status response:"
        echo "$STATUS_RESPONSE" | python3 -m json.tool
        break
    elif [ "$STATUS" = "FAILED" ]; then
        echo -e "${RED}❌ Job failed${NC}"
        echo "$STATUS_RESPONSE" | python3 -m json.tool
        exit 1
    fi
    
    sleep 2
done
echo ""

# Step 4: Get result
echo -e "${YELLOW}[4/6] Retrieving extraction result${NC}"
RESULT_FILE="result_${JOB_ID}.json"

curl -s "$API_BASE/jobs/$JOB_ID/result" \
  -H "Authorization: Bearer $API_KEY" \
  -o "$RESULT_FILE"

if [ -f "$RESULT_FILE" ]; then
    echo -e "${GREEN}✅ Result downloaded: $RESULT_FILE${NC}"
    echo ""
    echo "Result preview:"
    cat "$RESULT_FILE" | python3 -m json.tool | head -50
    echo ""
    echo -e "${YELLOW}... (truncated, see $RESULT_FILE for full output)${NC}"
else
    echo -e "${RED}❌ Failed to download result${NC}"
    exit 1
fi
echo ""

# Step 5: Test with custom prompt
echo -e "${YELLOW}[5/6] Testing with custom prompt${NC}"
CUSTOM_PROMPT="Extract all text from this document and identify any invoice numbers, dates, and amounts."

CUSTOM_RESPONSE=$(curl -s -X POST "$API_BASE/jobs/upload" \
  -H "Authorization: Bearer $API_KEY" \
  -F "document=@$TEST_FILE" \
  -F "prompt=$CUSTOM_PROMPT" \
  -F "include_coordinates=true")

echo "$CUSTOM_RESPONSE" | python3 -m json.tool

CUSTOM_JOB_ID=$(echo "$CUSTOM_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('job_id', ''))")

if [ -n "$CUSTOM_JOB_ID" ]; then
    echo -e "${GREEN}✅ Custom prompt job created: $CUSTOM_JOB_ID${NC}"
else
    echo -e "${RED}❌ Failed to create custom prompt job${NC}"
fi
echo ""

# Step 6: Test with structured output (all formats)
echo -e "${YELLOW}[6/6] Testing with structured output (all formats)${NC}"

STRUCTURED_RESPONSE=$(curl -s -X POST "$API_BASE/jobs/upload" \
  -H "Authorization: Bearer $API_KEY" \
  -F "document=@$TEST_FILE" \
  -F "output_formats=structured" \
  -F "include_coordinates=true" \
  -F "include_word_confidence=true" \
  -F "include_page_layout=true" \
  -F "granularity=word")

echo "$STRUCTURED_RESPONSE" | python3 -m json.tool

STRUCTURED_JOB_ID=$(echo "$STRUCTURED_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('job_id', ''))")

if [ -n "$STRUCTURED_JOB_ID" ]; then
    echo -e "${GREEN}✅ Structured output job created: $STRUCTURED_JOB_ID${NC}"
else
    echo -e "${RED}❌ Failed to create structured output job${NC}"
fi
echo ""

# Summary
echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ API Test Complete!${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"
echo ""
echo "Jobs created:"
echo "  1. JSON extraction: $JOB_ID (COMPLETED)"
echo "  2. Custom prompt: $CUSTOM_JOB_ID"
echo "  3. Structured output: $STRUCTURED_JOB_ID"
echo ""
echo "Result saved to: $RESULT_FILE"
echo ""
echo "To check other jobs:"
echo "  curl $API_BASE/jobs/$CUSTOM_JOB_ID -H \"Authorization: Bearer $API_KEY\""
echo "  curl $API_BASE/jobs/$STRUCTURED_JOB_ID -H \"Authorization: Bearer $API_KEY\""
echo ""
echo "To get their results (once completed):"
echo "  curl $API_BASE/jobs/$CUSTOM_JOB_ID/result -H \"Authorization: Bearer $API_KEY\" -o custom_result.json"
echo "  curl $API_BASE/jobs/$STRUCTURED_JOB_ID/result -H \"Authorization: Bearer $API_KEY\" -o structured_result.json"
echo ""
