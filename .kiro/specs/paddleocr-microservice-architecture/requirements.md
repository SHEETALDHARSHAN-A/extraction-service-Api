# Requirements: PaddleOCR Microservice Architecture

## 1. Overview

### 1.1 Purpose
Implement a production-ready microservices architecture that separates PaddleOCR layout detection and GLM-OCR content extraction into independent services, enabling per-field bounding boxes for document processing while resolving the PyTorch + PaddlePaddle CUDA conflict.

### 1.2 Background
The current system attempts to use both PaddleOCR (for layout detection) and PyTorch-based GLM-OCR (for content extraction) in the same Python process. This causes a CUDA device property registration conflict, resulting in:
- PaddleOCR initialization failure
- Fallback to full-page bounding box: `[0, 0, page_width, page_height]`
- No per-field bounding boxes for extracted data

### 1.3 Goals
- Enable per-field bounding boxes for all extracted document fields
- Resolve PyTorch + PaddlePaddle CUDA conflict through service separation
- Maintain backward compatibility with existing API
- Support production-scale throughput and reliability
- Enable independent scaling of layout detection and content extraction

### 1.4 Non-Goals
- Replacing the existing GLM-OCR model
- Changing the external API contract (maintain existing endpoints)
- Supporting real-time streaming of results
- Implementing custom layout detection models beyond PaddleOCR

## 2. Functional Requirements

### 2.1 PaddleOCR Layout Detection Service

#### FR-1: Service Initialization
- **Requirement**: The service SHALL initialize PaddleOCR PPStructureV3 on startup
- **Details**:
  - Load layout detection models from configurable path or auto-download
  - Support CPU and GPU execution modes
  - Validate model availability before accepting requests
  - Log initialization status and model versions

#### FR-2: Layout Detection API
- **Requirement**: The service SHALL provide an HTTP REST API endpoint for layout detection
- **Endpoint**: `POST /detect-layout`
- **Request Format**:
  ```json
  {
    "image": "base64_encoded_image_data",
    "options": {
      "detect_tables": true,
      "detect_formulas": true,
      "min_confidence": 0.5
    }
  }
  ```
- **Response Format**:
  ```json
  {
    "regions": [
      {
        "index": 0,
        "type": "text",
        "bbox": [x1, y1, x2, y2],
        "confidence": 0.95
      },
      {
        "index": 1,
        "type": "table",
        "bbox": [x1, y1, x2, y2],
        "confidence": 0.92
      }
    ],
    "page_dimensions": {
      "width": 800,
      "height": 600
    },
    "processing_time_ms": 150
  }
  ```

#### FR-3: Region Type Detection
- **Requirement**: The service SHALL detect and classify document regions into types
- **Supported Types**:
  - `text` - Plain text blocks, paragraphs, headings
  - `table` - Tabular data structures
  - `formula` - Mathematical formulas
  - `title` - Document titles and section headers
  - `figure` - Images, charts, diagrams
  - `caption` - Figure and table captions
  - `header` / `footer` - Page headers and footers
  - `list_item` - Bulleted or numbered lists

#### FR-4: Confidence Filtering
- **Requirement**: The service SHALL filter regions based on minimum confidence threshold
- **Details**:
  - Default threshold: 0.5
  - Configurable per request via `min_confidence` option
  - Return confidence score for each detected region

#### FR-5: Error Handling
- **Requirement**: The service SHALL handle errors gracefully
- **Error Scenarios**:
  - Invalid image format → HTTP 400 with error message
  - Image too large → HTTP 413 with size limit
  - Model initialization failure → HTTP 503 with retry-after header
  - Processing timeout → HTTP 504 with partial results if available

### 2.2 GLM-OCR Content Extraction Service (Modified)

#### FR-6: Region-Based Processing
- **Requirement**: The service SHALL accept cropped image regions for content extraction
- **New Endpoint**: `POST /extract-region`
- **Request Format**:
  ```json
  {
    "image": "base64_encoded_cropped_region",
    "region_type": "text",
    "prompt": "Text Recognition:",
    "options": {
      "output_format": "json",
      "max_tokens": 2048,
      "precision": "normal"
    }
  }
  ```
- **Response Format**:
  ```json
  {
    "content": "extracted text or structured data",
    "confidence": 0.93,
    "processing_time_ms": 2500,
    "tokens_used": {
      "prompt": 150,
      "completion": 320
    }
  }
  ```

#### FR-7: Batch Region Processing
- **Requirement**: The service SHALL support batch processing of multiple regions
- **Endpoint**: `POST /extract-regions-batch`
- **Request Format**:
  ```json
  {
    "regions": [
      {
        "region_id": "region_0",
        "image": "base64_encoded_data",
        "region_type": "text",
        "prompt": "Text Recognition:"
      },
      {
        "region_id": "region_1",
        "image": "base64_encoded_data",
        "region_type": "table",
        "prompt": "Table Recognition:"
      }
    ],
    "options": {
      "output_format": "json",
      "max_tokens": 2048
    }
  }
  ```
- **Response Format**:
  ```json
  {
    "results": [
      {
        "region_id": "region_0",
        "content": "...",
        "confidence": 0.95
      },
      {
        "region_id": "region_1",
        "content": "...",
        "confidence": 0.92
      }
    ],
    "total_processing_time_ms": 5200
  }
  ```

#### FR-8: Task-Specific Prompts
- **Requirement**: The service SHALL use region-type-specific prompts for optimal extraction
- **Prompt Mapping**:
  - `text` → "Text Recognition:"
  - `table` → "Table Recognition:"
  - `formula` → "Formula Recognition:"
  - Custom prompts allowed via request parameter

#### FR-9: Backward Compatibility
- **Requirement**: The service SHALL maintain existing `/jobs/upload` endpoint for full-page processing
- **Details**:
  - Existing clients continue to work without changes
  - Full-page mode returns single bbox when layout detection not used
  - New clients can opt-in to multi-region mode via options

### 2.3 API Gateway Orchestration

#### FR-10: Two-Stage Pipeline Orchestration
- **Requirement**: The API Gateway SHALL orchestrate the two-stage pipeline for document processing
- **Workflow**:
  1. Receive document upload request
  2. Call PaddleOCR service for layout detection
  3. Crop original image into regions based on bboxes
  4. Call GLM-OCR service for each region (parallel or sequential)
  5. Assemble final result with per-field bboxes
  6. Return unified response to client

#### FR-11: Enhanced Job Processing
- **Requirement**: The API Gateway SHALL enhance the existing job processing workflow
- **New Job Options**:
  ```json
  {
    "enable_layout_detection": true,
    "layout_detection_options": {
      "min_confidence": 0.5,
      "detect_tables": true,
      "detect_formulas": true
    },
    "parallel_region_processing": true,
    "max_parallel_regions": 5
  }
  ```

#### FR-12: Result Assembly
- **Requirement**: The API Gateway SHALL assemble results from both services into unified output
- **Output Format**:
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
    "markdown": "## Invoice Number: INV-12345\n\n...",
    "model": "zai-org/GLM-OCR",
    "mode": "two-stage",
    "confidence": 0.93,
    "usage": {
      "layout_detection_ms": 150,
      "content_extraction_ms": 5200,
      "total_ms": 5350
    }
  }
  ```

#### FR-13: Fallback Behavior
- **Requirement**: The API Gateway SHALL implement fallback strategies when services fail
- **Fallback Scenarios**:
  - PaddleOCR service unavailable → Use full-page mode with single bbox
  - GLM-OCR service unavailable → Return layout detection results only
  - Both services unavailable → Return HTTP 503 with error message
  - Partial region failures → Return successful regions + error list

#### FR-14: Caching Strategy
- **Requirement**: The API Gateway SHALL cache layout detection results
- **Details**:
  - Cache key: SHA-256 hash of image + layout options
  - Cache storage: Redis
  - TTL: Configurable (default 1 hour)
  - Cache invalidation: Manual or TTL-based

### 2.4 Service Communication

#### FR-15: HTTP REST Communication
- **Requirement**: Services SHALL communicate via HTTP REST APIs
- **Details**:
  - JSON request/response format
  - Standard HTTP status codes
  - Request timeout: 30 seconds (configurable)
  - Retry logic: 3 attempts with exponential backoff

#### FR-16: Service Discovery
- **Requirement**: Services SHALL register with service discovery mechanism
- **Details**:
  - Docker Compose: Use service names (e.g., `paddleocr-service`, `glm-ocr-service`)
  - Kubernetes: Use service DNS names
  - Health check endpoint: `GET /health`

#### FR-17: Health Checks
- **Requirement**: All services SHALL provide health check endpoints
- **Endpoint**: `GET /health`
- **Response Format**:
  ```json
  {
    "status": "healthy",
    "service": "paddleocr-layout-detection",
    "version": "1.0.0",
    "uptime_seconds": 3600,
    "models_loaded": true,
    "gpu_available": true
  }
  ```

## 3. Non-Functional Requirements

### 3.1 Performance

#### NFR-1: Latency
- **Requirement**: End-to-end processing latency SHALL be < 10 seconds for typical documents
- **Breakdown**:
  - Layout detection: < 500ms
  - Content extraction per region: < 3 seconds
  - Orchestration overhead: < 200ms

#### NFR-2: Throughput
- **Requirement**: The system SHALL support at least 10 concurrent document processing requests
- **Details**:
  - PaddleOCR service: 20 requests/second
  - GLM-OCR service: 5 requests/second (GPU-bound)
  - API Gateway: 50 requests/second

#### NFR-3: Resource Utilization
- **Requirement**: Services SHALL operate within defined resource limits
- **Limits**:
  - PaddleOCR service: 2 CPU cores, 4GB RAM (CPU mode) or 1 GPU, 6GB VRAM (GPU mode)
  - GLM-OCR service: 1 GPU, 8GB VRAM, 16GB RAM
  - API Gateway: 1 CPU core, 2GB RAM

### 3.2 Reliability

#### NFR-4: Availability
- **Requirement**: The system SHALL achieve 99.9% uptime
- **Details**:
  - Graceful degradation when services fail
  - Automatic service restart on crash
  - Health monitoring and alerting

#### NFR-5: Error Recovery
- **Requirement**: Services SHALL recover from transient failures automatically
- **Details**:
  - Retry failed requests with exponential backoff
  - Circuit breaker pattern for service calls
  - Fallback to degraded mode when necessary

### 3.3 Scalability

#### NFR-6: Horizontal Scaling
- **Requirement**: Services SHALL support horizontal scaling
- **Details**:
  - Stateless service design
  - Load balancing across multiple instances
  - Independent scaling of each service

#### NFR-7: Resource Scaling
- **Requirement**: Services SHALL scale resources based on load
- **Details**:
  - Auto-scaling based on CPU/GPU utilization
  - Queue-based load management
  - Graceful handling of resource exhaustion

### 3.4 Maintainability

#### NFR-8: Logging
- **Requirement**: Services SHALL provide structured logging
- **Log Levels**: DEBUG, INFO, WARN, ERROR
- **Log Format**: JSON with timestamp, service name, request ID, message
- **Log Destinations**: stdout (Docker logs), centralized logging system

#### NFR-9: Monitoring
- **Requirement**: Services SHALL expose metrics for monitoring
- **Metrics**:
  - Request count, latency (p50, p95, p99)
  - Error rate, success rate
  - GPU utilization, memory usage
  - Queue depth, processing time per stage

#### NFR-10: Observability
- **Requirement**: The system SHALL support distributed tracing
- **Details**:
  - Trace ID propagation across services
  - Span creation for each processing stage
  - Integration with tracing systems (Jaeger, Zipkin)

### 3.5 Security

#### NFR-11: Authentication
- **Requirement**: Internal service communication SHALL be authenticated
- **Details**:
  - API key or JWT token for service-to-service calls
  - Separate authentication for external API Gateway access

#### NFR-12: Input Validation
- **Requirement**: Services SHALL validate all inputs
- **Validations**:
  - Image format and size limits
  - Parameter range checks
  - Sanitization of user-provided prompts

## 4. Deployment Requirements

### 4.1 Docker Configuration

#### DR-1: PaddleOCR Service Container
- **Requirement**: The PaddleOCR service SHALL be containerized
- **Base Image**: `python:3.11-slim` or `paddlepaddle/paddle:latest-gpu`
- **Dependencies**: PaddleOCR, PaddlePaddle, FastAPI, Pillow
- **Ports**: 8001 (HTTP API)
- **Volumes**: Model cache directory

#### DR-2: GLM-OCR Service Container
- **Requirement**: The GLM-OCR service SHALL be containerized (existing, modified)
- **Base Image**: NVIDIA Triton or custom PyTorch image
- **Dependencies**: PyTorch, Transformers, FastAPI
- **Ports**: 8002 (HTTP API)
- **GPU**: Required (NVIDIA GPU with CUDA support)

#### DR-3: Docker Compose Configuration
- **Requirement**: Services SHALL be defined in docker-compose.yml
- **Services**:
  - `paddleocr-service`
  - `glm-ocr-service` (modified existing)
  - `api-gateway` (enhanced existing)
  - Supporting services (Redis, MinIO, Temporal, etc.)

### 4.2 Environment Configuration

#### DR-4: Configuration Management
- **Requirement**: Services SHALL use environment variables for configuration
- **PaddleOCR Service Variables**:
  - `PADDLEOCR_MODEL_DIR`: Model cache directory
  - `PADDLEOCR_USE_GPU`: Enable GPU mode (true/false)
  - `PADDLEOCR_GPU_MEM`: GPU memory limit (MB)
  - `LOG_LEVEL`: Logging level
- **GLM-OCR Service Variables**:
  - `GLM_MODEL_PATH`: Model path or HuggingFace ID
  - `GLM_PRECISION_MODE`: Inference precision (normal/high/precision)
  - `CUDA_VISIBLE_DEVICES`: GPU device ID
- **API Gateway Variables**:
  - `PADDLEOCR_SERVICE_URL`: PaddleOCR service endpoint
  - `GLM_OCR_SERVICE_URL`: GLM-OCR service endpoint
  - `ENABLE_LAYOUT_DETECTION`: Enable two-stage pipeline (true/false)
  - `CACHE_LAYOUT_RESULTS`: Enable layout caching (true/false)

## 5. Testing Requirements

### 5.1 Unit Testing

#### TR-1: Service Unit Tests
- **Requirement**: Each service SHALL have unit tests with >80% code coverage
- **Test Scope**:
  - API endpoint handlers
  - Input validation logic
  - Error handling paths
  - Model inference mocking

### 5.2 Integration Testing

#### TR-2: Service Integration Tests
- **Requirement**: The system SHALL have integration tests for the full pipeline
- **Test Scenarios**:
  - End-to-end document processing with layout detection
  - Fallback behavior when services fail
  - Batch region processing
  - Caching functionality

#### TR-3: Performance Testing
- **Requirement**: The system SHALL be performance tested under load
- **Test Scenarios**:
  - Concurrent request handling (10, 50, 100 requests)
  - Large document processing (multi-page PDFs)
  - Memory leak detection (long-running tests)

### 5.3 Acceptance Testing

#### TR-4: Per-Field Bbox Validation
- **Requirement**: Tests SHALL verify per-field bounding boxes are returned
- **Validation**:
  - Multiple regions detected (not just one full-page bbox)
  - Bbox coordinates are accurate (within 5% of ground truth)
  - All detected regions have valid bboxes

#### TR-5: Backward Compatibility Testing
- **Requirement**: Tests SHALL verify existing API clients continue to work
- **Validation**:
  - Existing `/jobs/upload` endpoint works without changes
  - Response format matches existing schema
  - Full-page mode works when layout detection disabled

## 6. Documentation Requirements

### 6.1 API Documentation

#### DOC-1: OpenAPI Specification
- **Requirement**: All service APIs SHALL be documented with OpenAPI 3.0 spec
- **Content**:
  - Endpoint descriptions
  - Request/response schemas
  - Error codes and messages
  - Example requests and responses

### 6.2 Deployment Documentation

#### DOC-2: Deployment Guide
- **Requirement**: A deployment guide SHALL be provided
- **Content**:
  - Docker Compose setup instructions
  - Environment variable reference
  - Service configuration options
  - Troubleshooting common issues

### 6.3 Architecture Documentation

#### DOC-3: Architecture Diagram
- **Requirement**: System architecture SHALL be documented with diagrams
- **Content**:
  - Service interaction diagram
  - Data flow diagram
  - Deployment architecture
  - Sequence diagrams for key workflows

## 7. Success Criteria

### 7.1 Functional Success
- ✅ Per-field bounding boxes are returned for all document types
- ✅ PyTorch + PaddlePaddle conflict is resolved (services run independently)
- ✅ Existing API clients continue to work without changes
- ✅ All output formats (text, json, markdown, table, key_value, structured, formula) work with per-field bboxes

### 7.2 Performance Success
- ✅ End-to-end latency < 10 seconds for typical documents
- ✅ System handles 10+ concurrent requests
- ✅ Layout detection completes in < 500ms
- ✅ Content extraction per region < 3 seconds

### 7.3 Reliability Success
- ✅ System achieves 99.9% uptime
- ✅ Graceful degradation when services fail
- ✅ Automatic recovery from transient failures
- ✅ No data loss during service restarts

### 7.4 Quality Success
- ✅ Unit test coverage > 80%
- ✅ All integration tests pass
- ✅ Performance tests meet latency/throughput targets
- ✅ Documentation is complete and accurate

## 8. Constraints and Assumptions

### 8.1 Constraints
- Must use existing Docker infrastructure
- Must maintain backward compatibility with existing API
- Must use PaddleOCR for layout detection (no custom models)
- Must use GLM-OCR for content extraction (no model replacement)
- GPU resources are limited (single GPU for GLM-OCR)

### 8.2 Assumptions
- Docker and Docker Compose are available in production
- NVIDIA GPU with CUDA support is available for GLM-OCR
- Redis is available for caching
- MinIO is available for object storage
- Network latency between services is < 10ms (same host or local network)

## 9. Dependencies

### 9.1 External Dependencies
- PaddleOCR 3.4.0+
- PaddlePaddle 2.5.0+ (CPU or GPU)
- PyTorch 2.0+ with CUDA support
- Transformers 5.0+
- FastAPI 0.100+
- Redis 7.0+
- MinIO (latest)

### 9.2 Internal Dependencies
- Existing API Gateway (Go)
- Existing Temporal Worker (Go)
- Existing preprocessing service (Go + Python)
- Existing post-processing service (Python)

## 10. Risks and Mitigation

### 10.1 Technical Risks

#### Risk 1: PaddleOCR Accuracy
- **Risk**: Layout detection may not be accurate for all document types
- **Impact**: Incorrect bboxes, missing regions
- **Mitigation**: 
  - Implement confidence thresholding
  - Provide fallback to full-page mode
  - Allow manual bbox adjustment via API

#### Risk 2: Service Communication Latency
- **Risk**: Network latency between services may impact performance
- **Impact**: Increased end-to-end latency
- **Mitigation**:
  - Deploy services on same host or low-latency network
  - Implement request batching
  - Use connection pooling

#### Risk 3: GPU Resource Contention
- **Risk**: Single GPU shared between multiple requests may cause queuing
- **Impact**: Increased latency, reduced throughput
- **Mitigation**:
  - Implement request queue with priority
  - Add GPU monitoring and alerting
  - Plan for horizontal scaling with multiple GPUs

### 10.2 Operational Risks

#### Risk 4: Service Dependency Failures
- **Risk**: Failure of one service impacts entire pipeline
- **Impact**: System unavailability
- **Mitigation**:
  - Implement circuit breaker pattern
  - Provide fallback modes
  - Add comprehensive health checks

#### Risk 5: Model Download Failures
- **Risk**: PaddleOCR models may fail to download on first run
- **Impact**: Service initialization failure
- **Mitigation**:
  - Pre-download models during Docker build
  - Implement retry logic with exponential backoff
  - Provide manual model installation option

## 11. Future Enhancements

### 11.1 Potential Improvements
- Support for multi-page PDF processing
- Custom layout detection model training
- Real-time streaming of results
- Support for additional document types (handwritten, forms)
- Advanced caching strategies (distributed cache, CDN)
- GraphQL API for flexible querying
- WebSocket support for real-time updates

### 11.2 Scalability Enhancements
- Kubernetes deployment with auto-scaling
- Multi-GPU support for GLM-OCR service
- Distributed processing with message queues (RabbitMQ, Kafka)
- Edge deployment for low-latency processing
