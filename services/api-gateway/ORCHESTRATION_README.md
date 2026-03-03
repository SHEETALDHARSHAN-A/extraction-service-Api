# API Gateway Orchestration Enhancements

## Overview

This document describes the two-stage pipeline orchestration implemented in the API Gateway for the PaddleOCR microservice architecture.

## Architecture

The orchestration layer coordinates between two services:
1. **PaddleOCR Service** - Layout detection (http://paddleocr-service:8001)
2. **GLM-OCR Service** - Content extraction (http://glm-ocr-service:8002)

## Components

### 1. Service Clients (`clients/`)

#### PaddleOCR Client (`clients/paddleocr.go`)
- Communicates with PaddleOCR service for layout detection
- Implements retry logic with exponential backoff (3 attempts)
- Includes circuit breaker pattern for fault tolerance
- Timeout: 30 seconds (configurable)

#### GLM-OCR Client (`clients/glmocr.go`)
- Communicates with GLM-OCR service for content extraction
- Supports batch and parallel region processing
- Implements retry logic and circuit breaker
- Maps region types to appropriate prompts

#### Circuit Breaker (`clients/circuit_breaker.go`)
- Prevents cascading failures
- States: Closed, Open, Half-Open
- Configurable failure threshold (default: 5)
- Configurable timeout (default: 60 seconds)

### 2. Orchestrator (`orchestrator/`)

#### Pipeline Orchestrator (`orchestrator/pipeline.go`)
Coordinates the two-stage document processing pipeline:

**Stage 1: Layout Detection**
- Calls PaddleOCR service to detect document regions
- Caches results in Redis (optional, 1-hour TTL)
- Returns regions with bounding boxes and confidence scores

**Stage 2: Image Cropping**
- Crops original image into regions based on bboxes
- Handles edge cases (bbox outside image bounds)
- Converts cropped images to base64

**Stage 3: Content Extraction**
- Calls GLM-OCR service for each region
- Supports parallel processing (configurable max parallel regions)
- Maps region types to appropriate prompts

**Stage 4: Result Assembly**
- Combines layout detection and content extraction results
- Generates unified response with per-field bboxes
- Calculates overall confidence and timing metrics

### 3. Configuration (`config/config.go`)

New environment variables:
- `PADDLEOCR_SERVICE_URL` - PaddleOCR service endpoint (default: http://paddleocr-service:8001)
- `GLM_OCR_SERVICE_URL` - GLM-OCR service endpoint (default: http://glm-ocr-service:8002)
- `ENABLE_LAYOUT_DETECTION` - Enable two-stage pipeline (default: false)
- `CACHE_LAYOUT_RESULTS` - Cache layout detection results (default: true)
- `MAX_PARALLEL_REGIONS` - Max parallel region processing (default: 5)
- `SERVICE_REQUEST_TIMEOUT` - Service request timeout in seconds (default: 30)
- `SERVICE_RETRY_ATTEMPTS` - Number of retry attempts (default: 3)
- `CIRCUIT_BREAKER_THRESHOLD` - Circuit breaker failure threshold (default: 5)
- `CIRCUIT_BREAKER_TIMEOUT` - Circuit breaker timeout in seconds (default: 60)

## API Usage

### Upload Document with Layout Detection

```bash
curl -X POST http://localhost:8000/jobs/upload \
  -F "document=@invoice.pdf" \
  -F "enable_layout_detection=true" \
  -F "min_confidence=0.5" \
  -F "detect_tables=true" \
  -F "detect_formulas=true" \
  -F "parallel_region_processing=true" \
  -F "max_parallel_regions=5" \
  -F "cache_layout_results=true"
```

### Response Format

```json
{
  "job_id": "uuid",
  "filename": "invoice.pdf",
  "status": "PROCESSING",
  "workflow_id": "doc-processing-uuid",
  "output_formats": "text",
  "options": {
    "enable_layout_detection": true,
    "parallel_region_processing": true,
    "layout_detection_options": {
      "min_confidence": "0.5",
      "detect_tables": true,
      "detect_formulas": true,
      "max_parallel_regions": "5",
      "cache_layout_results": true
    }
  },
  "result_url": "/jobs/uuid/result",
  "status_url": "/jobs/uuid"
}
```

### Result Format (Two-Stage Mode)

```json
{
  "pages": [
    {
      "page": 1,
      "width": 800,
      "height": 600,
      "elements": [
        {
          "index": 0,
          "label": "text",
          "content": "Invoice Number: INV-12345",
          "bbox_2d": [100, 50, 400, 80],
          "confidence": 0.95
        },
        {
          "index": 1,
          "label": "table",
          "content": "{...}",
          "bbox_2d": [100, 100, 700, 400],
          "confidence": 0.92
        }
      ]
    }
  ],
  "markdown": "Invoice Number: INV-12345\n\n...",
  "model": "zai-org/GLM-OCR",
  "mode": "two-stage",
  "confidence": 0.93,
  "usage": {
    "layout_detection_ms": 150,
    "content_extraction_ms": 5200,
    "total_ms": 5350,
    "regions_processed": 2
  }
}
```

## Fallback Behavior

The orchestrator implements multiple fallback strategies:

### 1. Layout Detection Disabled
- Processes document in full-page mode
- Single bbox: [0, 0, page_width, page_height]
- Mode: "full-page"

### 2. PaddleOCR Service Unavailable
- Falls back to full-page mode
- Logs fallback decision
- Mode: "full-page"

### 3. GLM-OCR Service Unavailable
- Returns layout detection results only
- No content extraction
- Mode: "layout-only"

### 4. Both Services Unavailable
- Returns HTTP 503 error
- Includes error message

### 5. Partial Region Failures
- Returns successful regions
- Includes error list for failed regions

## Caching Strategy

Layout detection results are cached in Redis:
- **Cache Key**: SHA-256 hash of (image + layout options)
- **TTL**: 1 hour (3600 seconds)
- **Storage**: Redis with prefix "idep:layout:"
- **Invalidation**: TTL-based or manual

## Circuit Breaker Pattern

Prevents cascading failures when services are down:

### States
- **Closed**: Normal operation, requests pass through
- **Open**: Service is failing, requests are blocked
- **Half-Open**: Testing if service has recovered

### Behavior
1. After N failures (threshold), circuit opens
2. Requests are blocked for timeout period
3. After timeout, circuit enters half-open state
4. If 3 consecutive requests succeed, circuit closes
5. If any request fails in half-open, circuit reopens

## Testing

### Unit Tests
- `orchestrator/pipeline_test.go` - Orchestrator tests
- `clients/circuit_breaker_test.go` - Circuit breaker tests

Run unit tests:
```bash
cd services/api-gateway
go test ./orchestrator/... -v
go test ./clients/... -v
```

### Integration Tests
- `tests/integration_test.go` - End-to-end pipeline tests

Run integration tests:
```bash
cd services/api-gateway
go test ./tests/... -v
```

## Performance Considerations

### Latency Targets
- Layout detection: < 500ms
- Content extraction per region: < 3 seconds
- End-to-end: < 10 seconds for typical documents

### Throughput
- PaddleOCR service: 20 requests/second
- GLM-OCR service: 5 requests/second (GPU-bound)
- API Gateway: 50 requests/second

### Optimization Strategies
1. **Parallel Region Processing**: Process multiple regions concurrently
2. **Layout Caching**: Cache layout detection results to avoid reprocessing
3. **Circuit Breaker**: Fail fast when services are down
4. **Connection Pooling**: Reuse HTTP connections

## Monitoring and Logging

### Structured Logging
All orchestration steps are logged with:
- Request ID
- Processing time
- Service calls
- Fallback decisions
- Error details

### Metrics
- Request count and latency (p50, p95, p99)
- Error rate and success rate
- Circuit breaker state changes
- Cache hit/miss ratio

## Future Enhancements

1. **Multi-page PDF Support**: Process multiple pages in parallel
2. **Advanced Caching**: Distributed cache with CDN
3. **GraphQL API**: Flexible querying of results
4. **WebSocket Support**: Real-time progress updates
5. **Custom Layout Models**: Support for custom PaddleOCR models
6. **Region Prioritization**: Process important regions first
7. **Adaptive Timeout**: Adjust timeouts based on document complexity

## Troubleshooting

### Common Issues

**Issue**: Circuit breaker keeps opening
- **Cause**: Service is down or slow
- **Solution**: Check service health, increase timeout or threshold

**Issue**: Layout detection returns no regions
- **Cause**: Low confidence threshold or poor image quality
- **Solution**: Lower min_confidence or improve image quality

**Issue**: Content extraction is slow
- **Cause**: Too many regions or large images
- **Solution**: Enable parallel processing, reduce max_parallel_regions

**Issue**: Cache not working
- **Cause**: Redis unavailable or cache disabled
- **Solution**: Check Redis connection, enable CACHE_LAYOUT_RESULTS

### Debug Mode

Enable debug logging:
```bash
export LOG_LEVEL=DEBUG
```

Check service health:
```bash
curl http://paddleocr-service:8001/health
curl http://glm-ocr-service:8002/health
```

## References

- [PaddleOCR Documentation](https://github.com/PaddlePaddle/PaddleOCR)
- [GLM-OCR Model](https://huggingface.co/zai-org/GLM-OCR)
- [Circuit Breaker Pattern](https://martinfowler.com/bliki/CircuitBreaker.html)
- [Microservices Architecture](https://microservices.io/)
