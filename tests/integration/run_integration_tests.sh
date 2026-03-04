#!/bin/bash

# Integration Test Runner Script
# This script runs the complete extraction flow integration tests

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
API_KEY="${API_KEY:-tp-proj-dev-key-123}"
MAX_WAIT_TIME=300  # 5 minutes

echo "============================================================"
echo "Integration Test Runner"
echo "============================================================"
echo ""
echo "API Base URL: $API_BASE_URL"
echo "API Key: ${API_KEY:0:20}..."
echo ""

# Function to check if services are healthy
check_services() {
    echo "Checking service health..."
    
    response=$(curl -s -o /dev/null -w "%{http_code}" "$API_BASE_URL/health" || echo "000")
    
    if [ "$response" = "200" ]; then
        echo -e "${GREEN}✅ Services are healthy${NC}"
        return 0
    else
        echo -e "${RED}❌ Services are not healthy (HTTP $response)${NC}"
        return 1
    fi
}

# Function to wait for services to be ready
wait_for_services() {
    echo "Waiting for services to be ready..."
    
    elapsed=0
    while [ $elapsed -lt $MAX_WAIT_TIME ]; do
        if check_services; then
            return 0
        fi
        
        echo "  Waiting... ($elapsed/$MAX_WAIT_TIME seconds)"
        sleep 5
        elapsed=$((elapsed + 5))
    done
    
    echo -e "${RED}❌ Services did not become healthy within $MAX_WAIT_TIME seconds${NC}"
    return 1
}

# Function to run tests with pytest
run_pytest() {
    echo ""
    echo "============================================================"
    echo "Running Integration Tests with pytest"
    echo "============================================================"
    echo ""
    
    export API_BASE_URL
    export API_KEY
    
    if command -v pytest &> /dev/null; then
        pytest tests/integration/test_complete_extraction_flow.py -v -s
        return $?
    else
        echo -e "${YELLOW}⚠️  pytest not found, falling back to direct execution${NC}"
        return 1
    fi
}

# Function to run tests directly
run_direct() {
    echo ""
    echo "============================================================"
    echo "Running Integration Tests (Direct Execution)"
    echo "============================================================"
    echo ""
    
    export API_BASE_URL
    export API_KEY
    
    python tests/integration/test_complete_extraction_flow.py
    return $?
}

# Main execution
main() {
    # Check if services are already healthy
    if ! check_services; then
        echo ""
        echo -e "${YELLOW}Services not healthy. Attempting to wait...${NC}"
        
        if ! wait_for_services; then
            echo ""
            echo -e "${RED}❌ Cannot run tests: Services are not available${NC}"
            echo ""
            echo "To start services:"
            echo "  cd docker"
            echo "  docker-compose up -d"
            echo ""
            echo "Then wait for services to initialize (1-2 minutes)"
            exit 1
        fi
    fi
    
    echo ""
    
    # Try pytest first, fall back to direct execution
    if run_pytest; then
        echo ""
        echo "============================================================"
        echo -e "${GREEN}✅ ALL INTEGRATION TESTS PASSED${NC}"
        echo "============================================================"
        exit 0
    elif run_direct; then
        echo ""
        echo "============================================================"
        echo -e "${GREEN}✅ ALL INTEGRATION TESTS PASSED${NC}"
        echo "============================================================"
        exit 0
    else
        echo ""
        echo "============================================================"
        echo -e "${RED}❌ INTEGRATION TESTS FAILED${NC}"
        echo "============================================================"
        exit 1
    fi
}

# Run main function
main
