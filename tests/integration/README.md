# Integration Tests

This directory contains integration tests for the GPU extraction system that validate end-to-end workflows across all microservices.

## Overview

Integration tests verify that all components work together correctly:
- API Gateway (Go)
- Redis Request Queue
- Temporal Worker (Go)
- GLM-OCR Service (FastAPI)
- Triton Inference Server
- PostgreSQL
- MinIO
- Redis

## Test Coverage

### test_complete_extraction_flow.py

Validates the complete extraction flow from document upload to result retrieval:

**Test Cases:**
1. **Basic Complete Flow** - Upload → Queue → Process → Retrieve
2. **Word-Level Granularity** - Word-level bounding box extraction
3. **Key-Value Format** - Key-value pair extraction with separate bboxes
4. **Queue Status Polling** - Queue metrics and status monitoring
5. **Concurrent Request Handling** - 10 simultaneous requests with proper queueing
6. **Large Document Processing** - 20-page PDF with parallel page processing
7. **Error Recovery with Retry** - Exponential backoff retry mechanism validation
8. **Error Handling** - Invalid document handling

**Requirements Validated:**
- Requirement 2.1: Queue sequential processing
- Requirement 2.2: Queue position assignment
- Requirement 2.4: Queue status polling
- Requirement 2.6: Queue limits concurrent GPU inference to 1
- Requirement 3.1, 3.2, 3.4: Word-level bounding boxes
- Requirement 3.6: Word order preservation
- Requirement 4.1, 4.2: Key-value extraction with bboxes
- Requirement 4.6: Key-value confidence scores
- Requirement 7.2, 7.3: Error handling
- Requirement 7.4: Exponential backoff retry (max 3 attempts)
- Requirement 7.5: Failure details stored after max retries
- Requirement 7.6: Health check endpoint
- Requirement 8.1: Parallel page processing (max 3 concurrent)
- Requirement 10.1: Extraction request logging

## Prerequisites

### 1. Start All Services

```bash
# From project root
cd docker
docker-compose up -d
```

### 2. Wait for Services to be Healthy

```bash
# Check health status
curl http://localhost:8000/health

# Or use the verify script
./verify-monitoring.sh
```

All services should report "healthy" status:
- triton
- glm_ocr_service
- request_queue
- database
- redis

### 3. Install Test Dependencies

```bash
# From project root
pip install -r tests/integration/requirements.txt

# This includes:
# - pytest (testing framework)
# - requests (HTTP client)
# - Pillow (image processing)
# - reportlab (PDF generation for large document tests)
```

## Running Tests

### Run All Integration Tests

```bash
# Using pytest (recommended)
pytest tests/integration/test_complete_extraction_flow.py -v

# Run with detailed output
pytest tests/integration/test_complete_extraction_flow.py -v -s

# Run specific test
pytest tests/integration/test_complete_extraction_flow.py::test_complete_extraction_flow_basic -v
```

### Run Tests Directly (Without pytest)

```bash
# From project root
python tests/integration/test_complete_extraction_flow.py
```

### Run with Custom Configuration

```bash
# Set custom API URL and key
export API_BASE_URL=http://localhost:8000
export API_KEY=tp-proj-dev-key-123

pytest tests/integration/test_complete_extraction_flow.py -v
```

## Test Output

### Successful Test Run

```
============================================================
TEST: Complete Extraction Flow - Basic
============================================================

1. Creating and uploading test document...
   ✅ Document uploaded: job_id=abc-123-...
   Status: QUEUED
   Output formats: text,json

2. Checking queue status...
   Queue length: 1
   Estimated wait time: 15s

3. Polling for job completion...
   Attempt 1/60: QUEUED (position: 1, wait: 15s)
   Attempt 2/60: PROCESSING (Processing page 1 of 1)
   ✅ Job completed: COMPLETED

4. Retrieving results...
   ✅ Results retrieved
   Model: glm-ocr
   Processing time: 3200ms
   Document confidence: 0.93

5. Validating result structure...
   ✅ Result structure valid

============================================================
✅ TEST PASSED: Complete Extraction Flow - Basic
============================================================
```

### Failed Test Run

If services are not available:
```
❌ Services not available: Critical services unhealthy: triton: unhealthy

To run integration tests:
1. Start all services: docker-compose up -d
2. Wait for services to be healthy
3. Run tests: python test_complete_extraction_flow.py
```

## Troubleshooting

### Services Not Healthy

**Problem:** Health check fails with unhealthy services

**Solution:**
```bash
# Check service logs
docker-compose logs triton
docker-compose logs glm-ocr-service
docker-compose logs api-gateway

# Restart unhealthy services
docker-compose restart triton
docker-compose restart glm-ocr-service

# Wait for services to initialize (may take 1-2 minutes)
```

### Test Timeout

**Problem:** Test times out waiting for job completion

**Solution:**
- Check Temporal Worker logs: `docker-compose logs temporal-worker`
- Check GLM-OCR Service logs: `docker-compose logs glm-ocr-service`
- Verify GPU is available: `nvidia-smi`
- Increase timeout: Set `MAX_POLL_ATTEMPTS` environment variable

### Connection Refused

**Problem:** Cannot connect to API Gateway

**Solution:**
```bash
# Verify API Gateway is running
docker-compose ps api-gateway

# Check API Gateway logs
docker-compose logs api-gateway

# Verify port is accessible
curl http://localhost:8000/health
```

### Queue Full Error (HTTP 429)

**Problem:** Queue is full, cannot enqueue new jobs

**Solution:**
```bash
# Check queue status
curl http://localhost:8000/queue/status

# Wait for queue to drain or clear Redis queue
docker-compose exec redis redis-cli FLUSHDB
```

## Test Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_BASE_URL` | `http://localhost:8000` | API Gateway base URL |
| `API_KEY` | `tp-proj-dev-key-123` | API authentication key |
| `MAX_POLL_ATTEMPTS` | `60` | Maximum status poll attempts |
| `POLL_INTERVAL` | `2` | Seconds between status polls |

### Timeouts

- **Job Completion Timeout**: 120 seconds (60 attempts × 2 seconds)
- **Health Check Timeout**: 5 seconds
- **HTTP Request Timeout**: 30 seconds (default)

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  integration-tests:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v2
      
      - name: Start services
        run: |
          cd docker
          docker-compose up -d
      
      - name: Wait for services
        run: |
          timeout 300 bash -c 'until curl -f http://localhost:8000/health; do sleep 5; done'
      
      - name: Run integration tests
        run: |
          pip install -r tests/requirements.txt
          pytest tests/integration/test_complete_extraction_flow.py -v
      
      - name: Cleanup
        if: always()
        run: |
          cd docker
          docker-compose down -v
```

## Performance Benchmarks

Expected performance for integration tests:

| Test Case | Expected Duration | Notes |
|-----------|------------------|-------|
| Basic Complete Flow | 10-30 seconds | Depends on queue length |
| Word Granularity | 15-40 seconds | More processing required |
| Key-Value Format | 15-40 seconds | Pattern recognition overhead |
| Queue Status Polling | 10-30 seconds | Minimal overhead |
| Concurrent Requests (10) | 60-180 seconds | Sequential GPU processing |
| Large Document (20 pages) | 120-600 seconds | Parallel page processing (max 3 concurrent) |
| Error Recovery with Retry | 10-30 seconds | Validates retry configuration |
| Error Handling | 1-5 seconds | Fast failure |

**Total Suite Duration**: 5-15 minutes (with healthy services)

**Note on Large Document Test:**
- The 20-page PDF test validates parallel page processing (Requirement 8.1)
- With max 3 concurrent pages, processing should be faster than sequential
- Expected: ~7 batches of 3 pages each (20 pages / 3 = ~7 batches)
- Actual time depends on GPU performance and page complexity

## Adding New Integration Tests

### Test Template

```python
def test_new_integration_feature(ensure_services_healthy):
    """
    Test Case: Description
    
    Steps:
    1. Step 1
    2. Step 2
    3. Step 3
    
    Validates:
    - Requirement X.Y: Description
    """
    print("\n" + "=" * 80)
    print("TEST: New Integration Feature")
    print("=" * 80)
    
    # Test implementation
    
    print("\n" + "=" * 80)
    print("✅ TEST PASSED: New Integration Feature")
    print("=" * 80)
```

### Best Practices

1. **Use the `ensure_services_healthy` fixture** - Ensures services are available
2. **Print clear progress messages** - Helps with debugging
3. **Validate response structure** - Check all expected fields
4. **Handle timeouts gracefully** - Use `wait_for_job_completion()`
5. **Clean up resources** - Cancel jobs if test fails
6. **Document requirements** - Link to specific requirements being validated

## Related Documentation

- [API Documentation](../../docs/API.md) - Complete API reference
- [Design Document](../../.kiro/specs/gpu-extraction-production-ready/design.md) - System architecture
- [Requirements](../../.kiro/specs/gpu-extraction-production-ready/requirements.md) - Feature requirements
- [Monitoring Setup](../../docker/MONITORING.md) - Observability configuration

## Support

For issues or questions:
1. Check service logs: `docker-compose logs <service-name>`
2. Verify health status: `curl http://localhost:8000/health`
3. Check queue status: `curl http://localhost:8000/queue/status`
4. Review test output for specific error messages
