#!/bin/bash
# ============================================
# IDEP E2E GPU Test (Bash/Linux/WSL)
# Run on Linux/WSL instead of PowerShell
# ============================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TESTFILES_DIR="$WORKSPACE_ROOT/testfiles"
API_KEY="tp-proj-dev-key-123"
API_BASE="http://localhost:8000"
MAX_WAIT=120

# Helper functions
log_section() {
    echo -e "\n${BLUE}===================================================${NC}"
    echo -e "${BLUE}${1}${NC}"
    echo -e "${BLUE}===================================================${NC}\n"
}

log_success() {
    echo -e "${GREEN}✅ ${1}${NC}"
}

log_error() {
    echo -e "${RED}❌ ${1}${NC}"
}

log_info() {
    echo -e "${YELLOW}ℹ️  ${1}${NC}"
}

log_section "1. VERIFYING PREREQUISITES"

# Check Docker
log_info "Checking Docker..."
if ! command -v docker &> /dev/null; then
    log_error "Docker not found"
    exit 1
fi
DOCKER_VERSION=$(docker --version)
log_success "Docker installed: $DOCKER_VERSION"

# Check Docker Compose
if ! command -v docker-compose &> /dev/null; then
    log_error "Docker Compose not found"
    exit 1
fi
log_success "Docker Compose installed"

# Check GPU
log_info "Checking GPU support..."
if docker run --rm --gpus all nvidia/cuda:12.2.2-base-ubuntu22.04 nvidia-smi &> /dev/null; then
    log_success "GPU is accessible in Docker"
else
    log_error "GPU not accessible in Docker"
    exit 1
fi

# Check testfiles
if [ ! -d "$TESTFILES_DIR" ]; then
    log_error "testfiles directory not found at: $TESTFILES_DIR"
    exit 1
fi

TEST_FILE_COUNT=$(find "$TESTFILES_DIR" -name "*.pdf" | wc -l)
log_success "Found $TEST_FILE_COUNT PDF files in testfiles"

log_section "2. STARTING DOCKER SERVICES"

cd "$WORKSPACE_ROOT"

log_info "Stopping any existing containers..."
docker-compose -f docker/docker-compose.yml down 2>/dev/null || true

log_info "Starting containers with existing images (no rebuild)..."
if ! docker-compose -f docker/docker-compose.yml up -d; then
    log_error "Failed to start docker-compose"
    exit 1
fi

log_success "Services started"

log_section "3. WAITING FOR SERVICES TO BE HEALTHY"

wait_for_service() {
    local service=$1
    local endpoint=$2
    local max_wait=${3:-$MAX_WAIT}
    
    local start=$(date +%s)
    local healthy=0
    
    while [ $healthy -eq 0 ]; do
        local now=$(date +%s)
        local elapsed=$((now - start))
        
        if [ $elapsed -gt $max_wait ]; then
            log_error "$service did not become healthy within $max_wait seconds"
            return 1
        fi
        
        if curl -s "$endpoint" > /dev/null 2>&1; then
            log_success "$service is healthy"
            return 0
        fi
        
        log_info "$service not ready yet... waiting"
        sleep 5
    done
}

wait_for_service "API Gateway" "$API_BASE/health" || exit 1
wait_for_service "Temporal UI" "http://localhost:8080" || true

log_section "4. TESTING SINGLE DOCUMENT UPLOAD"

# Find first PDF
TEST_FILE=$(find "$TESTFILES_DIR" -name "*.pdf" | head -1)

if [ -z "$TEST_FILE" ]; then
    log_error "No PDF files found"
    exit 1
fi

FILE_NAME=$(basename "$TEST_FILE")
FILE_SIZE=$(du -h "$TEST_FILE" | cut -f1)

log_info "Uploading: $FILE_NAME ($FILE_SIZE)"

UPLOAD_RESPONSE=$(curl -s -X POST "$API_BASE/jobs/upload" \
    -H "Authorization: Bearer $API_KEY" \
    -F "document=@$TEST_FILE" \
    -F "output_formats=json,structured" \
    -F "include_coordinates=true" \
    -F "deskew=true" \
    -F "enhance=true")

JOB_ID=$(echo "$UPLOAD_RESPONSE" | grep -o '"job_id":"[^"]*' | cut -d '"' -f 4)

if [ -z "$JOB_ID" ]; then
    log_error "Upload failed"
    echo "$UPLOAD_RESPONSE" | head -20
    exit 1
fi

log_success "Document uploaded"
log_info "Job ID: $JOB_ID"

log_section "5. MONITORING JOB PROGRESS"

log_info "Monitoring job: $JOB_ID"

POLL_COUNT=0
MAX_POLLS=60

while [ $POLL_COUNT -lt $MAX_POLLS ]; do
    sleep 5
    ((POLL_COUNT++))
    
    STATUS_RESPONSE=$(curl -s "$API_BASE/jobs/$JOB_ID" \
        -H "Authorization: Bearer $API_KEY")
    
    STATUS=$(echo "$STATUS_RESPONSE" | grep -o '"status":"[^"]*' | cut -d '"' -f 4)
    
    log_info "[$POLL_COUNT/$MAX_POLLS] Job status: $STATUS"
    
    if [ "$STATUS" = "COMPLETED" ]; then
        log_success "Job completed!"
        break
    elif [ "$STATUS" = "FAILED" ]; then
        log_error "Job failed"
        break
    fi
done

log_section "6. RETRIEVING RESULTS"

if [ "$STATUS" = "COMPLETED" ]; then
    RESULT=$(curl -s "$API_BASE/jobs/$JOB_ID/result" \
        -H "Authorization: Bearer $API_KEY")
    
    # Create results directory
    RESULTS_DIR="$TESTFILES_DIR/.results"
    mkdir -p "$RESULTS_DIR"
    
    # Save result
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    RESULT_FILE="$RESULTS_DIR/result_$TIMESTAMP.json"
    echo "$RESULT" | jq . > "$RESULT_FILE"
    
    log_success "Results saved to: $RESULT_FILE"
    
    # Show summary
    log_info "Result Summary:"
    echo "$RESULT" | jq '{
        document_type,
        pages,
        confidence,
        text_length: (.text_content | length),
        tables: (.tables | length)
    }' 2>/dev/null || true
else
    log_error "Job did not complete successfully"
fi

log_section "7. SERVICE STATUS"

log_info "Container Status:"
docker-compose -f docker/docker-compose.yml ps

log_info "Resource Usage:"
docker stats --no-stream | head -10

log_section "TESTING COMPLETE"

log_success "Testing finished!"
log_info "To view dashboards:"
echo "  - Temporal UI: http://localhost:8080"
echo "  - Grafana: http://localhost:3000 (admin/idep-admin)"
echo "  - Prometheus: http://localhost:9090"
echo "  - Jaeger: http://localhost:16686"

log_info "To view logs:"
echo "  docker-compose -f docker/docker-compose.yml logs -f api-gateway"
echo "  docker-compose -f docker/docker-compose.yml logs -f triton"

log_info "To stop services:"
echo "  docker-compose -f docker/docker-compose.yml down"

cd - > /dev/null
