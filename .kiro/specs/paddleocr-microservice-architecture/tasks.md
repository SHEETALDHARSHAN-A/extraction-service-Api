# Tasks: PaddleOCR Microservice Architecture

## Task 1: PaddleOCR Layout Detection Service Implementation

- [x] 1.1 Create service directory structure
  - [x] 1.1.1 Create `services/paddleocr-service/` directory
  - [x] 1.1.2 Create `services/paddleocr-service/app/` subdirectory
  - [x] 1.1.3 Create `services/paddleocr-service/app/models/` for model cache
  - [x] 1.1.4 Create `services/paddleocr-service/tests/` for test files

- [x] 1.2 Implement configuration management
  - [x] 1.2.1 Create `services/paddleocr-service/app/config.py`
  - [x] 1.2.2 Define environment variable configuration (PADDLEOCR_USE_GPU, PADDLEOCR_MODEL_DIR, etc.)
  - [x] 1.2.3 Implement configuration validation
  - [x] 1.2.4 Add logging configuration

- [x] 1.3 Implement PPStructureV3 model wrapper
  - [x] 1.3.1 Create `services/paddleocr-service/app/layout_detector.py`
  - [x] 1.3.2 Initialize PPStructureV3 with configurable options
  - [x] 1.3.3 Implement `detect_regions()` method
  - [x] 1.3.4 Add confidence filtering logic
  - [x] 1.3.5 Handle both CPU and GPU execution modes
  - [x] 1.3.6 Add model version tracking

- [x] 1.4 Implement Pydantic models
  - [x] 1.4.1 Create `services/paddleocr-service/app/models.py`
  - [x] 1.4.2 Define `Region` model with index, type, bbox, confidence
  - [x] 1.4.3 Define `PageDimensions` model
  - [x] 1.4.4 Define `DetectLayoutRequest` model
  - [x] 1.4.5 Define `DetectLayoutResponse` model
  - [x] 1.4.6 Define `HealthResponse` model

- [x] 1.5 Implement FastAPI application
  - [x] 1.5.1 Create `services/paddleocr-service/app/main.py`
  - [x] 1.5.2 Create FastAPI app instance with metadata
  - [x] 1.5.3 Implement `/detect-layout` POST endpoint
  - [x] 1.5.4 Implement `/health` GET endpoint
  - [x] 1.5.5 Add request validation middleware
  - [x] 1.5.6 Add error handling middleware
  - [x] 1.5.7 Add processing time tracking

- [x] 1.6 Implement image preprocessing
  - [x] 1.6.1 Add base64 image decoding
  - [x] 1.6.2 Implement image size validation
  - [x] 1.6.3 Add image format conversion (PIL to NumPy)
  - [x] 1.6.4 Implement image dimension extraction

- [x] 1.7 Add logging and monitoring
  - [x] 1.7.1 Implement structured JSON logging
  - [x] 1.7.2 Add request ID tracking
  - [x] 1.7.3 Log model initialization
  - [x] 1.7.4 Log processing time and resource usage

- [x] 1.8 Create Dockerfile
  - [x] 1.8.1 Use `python:3.11-slim` base image
  - [x] 1.8.2 Install PaddleOCR and dependencies
  - [x] 1.8.3 Copy application code
  - [x] 1.8.4 Set up non-root user
  - [x] 1.8.5 Expose port 8001
  - [x] 1.8.6 Add health check

- [x] 1.9 Create requirements.txt
  - [x] 1.9.1 Add paddlepaddle (CPU or GPU)
  - [x] 1.9.2 Add paddleocr 3.4.0+
  - [x] 1.9.3 Add fastapi 0.100+
  - [x] 1.9.4 Add uvicorn
  - [x] 1.9.5 Add pillow, numpy
  - [x] 1.9.6 Add pydantic, pydantic-settings

- [x] 1.10 Write unit tests
  - [x] 1.10.1 Create `services/paddleocr-service/tests/test_config.py`
  - [x] 1.10.2 Create `services/paddleocr-service/tests/test_layout_detector.py`
  - [x] 1.10.3 Create `services/paddleocr-service/tests/test_models.py`
  - [x] 1.10.4 Test configuration loading
  - [x] 1.10.5 Test layout detection with mock images
  - [x] 1.10.6 Test confidence filtering
  - [x] 1.10.7 Test error handling

- [x] 1.11 Write integration tests
  - [x] 1.11.1 Create `services/paddleocr-service/tests/test_api.py`
  - [x] 1.11.2 Test `/detect-layout` endpoint with real model
  - [x] 1.11.3 Test `/health` endpoint
  - [x] 1.11.4 Test error responses
  - [x] 1.11.5 Test image validation

## Task 2: GLM-OCR Service Modifications

- [x] 2.1 Review existing GLM-OCR service structure
  - [x] 2.1.1 Examine current `/jobs/upload` endpoint
  - [x] 2.1.2 Identify existing models and prompts
  - [x] 2.1.3 Document current request/response formats

- [x] 2.2 Implement /extract-region endpoint
  - [x] 2.2.1 Add `POST /extract-region` endpoint
  - [x] 2.2.2 Create request model for single region
  - [x] 2.2.3 Create response model with content and confidence
  - [x] 2.2.4 Implement region-type-specific prompts
  - [x] 2.2.5 Add processing time tracking
  - [x] 2.2.6 Add token usage tracking

- [x] 2.3 Implement /extract-regions-batch endpoint
  - [x] 2.3.1 Add `POST /extract-regions-batch` endpoint
  - [x] 2.3.2 Create batch request model
  - [x] 2.3.3 Create batch response model
  - [x] 2.3.4 Implement parallel region processing
  - [x] 2.3.5 Add per-region error handling
  - [x] 2.3.6 Track total processing time

- [x] 2.4 Implement region type prompt mapping
  - [x] 2.4.1 Create prompt configuration
  - [x] 2.4.2 Map region types to prompts:
    - [ ] text → "Text Recognition:"
    - [ ] table → "Table Recognition:"
    - [ ] formula → "Formula Recognition:"
    - [ ] title → "Title Recognition:"
    - [ ] figure → "Figure Recognition:"
  - [x] 2.4.3 Support custom prompts

- [x] 2.5 Add input validation
  - [x] 2.5.1 Validate base64 image format
  - [x] 2.5.2 Validate region type
  - [x] 2.5.3 Validate prompt length
  - [x] 2.5.4 Validate max_tokens parameter

- [x] 2.6 Update existing endpoints
  - [x] 2.6.1 Ensure `/jobs/upload` maintains backward compatibility
  - [x] 2.6.2 Add option to enable layout detection mode
  - [x] 2.6.3 Add response format option for per-field bboxes

- [x] 2.7 Add logging and monitoring
  - [x] 2.7.1 Implement structured JSON logging
  - [x] 2.7.2 Add request ID tracking
  - [x] 2.7.3 Log model inference time
  - [x] 2.7.4 Log token usage

- [x] 2.8 Update Docker configuration
  - [x] 2.8.1 Update existing Dockerfile
  - [x] 2.8.2 Add new endpoint handlers
  - [x] 2.8.3 Update health check endpoint
  - [x] 2.8.4 Update environment variables

- [x] 2.9 Write unit tests
  - [x] 2.9.1 Create tests for new endpoints
  - [x] 2.9.2 Test prompt mapping
  - [x] 2.9.3 Test input validation
  - [x] 2.9.4 Test batch processing

- [x] 2.10 Write integration tests
  - [x] 2.10.1 Test `/extract-region` with real model
  - [x] 2.10.2 Test `/extract-regions-batch` with multiple regions
  - [x] 2.10.3 Test backward compatibility with `/jobs/upload`

## Task 3: API Gateway Orchestration Enhancements

- [x] 3.1 Review existing API Gateway structure
  - [x] 3.1.1 Examine current job processing flow
  - [x] 3.1.2 Identify existing service URLs and endpoints
  - [x] 3.1.3 Document current response formats

- [x] 3.2 Implement layout detection orchestration
  - [x] 3.2.1 Add PaddleOCR service client
  - [x] 3.2.2 Implement layout detection request
  - [x] 3.2.3 Handle layout detection response
  - [x] 3.2.4 Add timeout handling (30s default)
  - [x] 3.2.5 Add retry logic (3 attempts, exponential backoff)

- [x] 3.3 Implement image cropping into regions
  - [x] 3.3.1 Create image cropping utility
  - [x] 3.3.2 Implement bbox-based cropping
  - [x] 3.3.3 Add padding option for regions
  - [x] 3.3.4 Handle edge cases (bbox outside image)
  - [x] 3.3.5 Convert cropped images to base64

- [x] 3.4 Implement region content extraction
  - [x] 3.4.1 Add GLM-OCR service client
  - [x] 3.4.2 Implement batch region processing
  - [x] 3.4.3 Map region types to prompts
  - [x] 3.4.4 Handle partial failures
  - [x] 3.4.5 Add parallel processing option

- [x] 3.5 Implement result assembly
  - [x] 3.5.1 Create unified result model
  - [x] 3.5.2 Assemble per-field bboxes
  - [x] 3.5.3 Generate markdown output
  - [x] 3.5.4 Calculate overall confidence
  - [x] 3.5.5 Track timing per stage

- [x] 3.6 Implement caching strategy
  - [x] 3.6.1 Add Redis client
  - [x] 3.6.2 Implement layout detection caching
  - [x] 3.6.3 Create cache key from image hash + options
  - [x] 3.6.4 Set configurable TTL (default 1 hour)
  - [x] 3.6.5 Implement cache invalidation

- [x] 3.7 Implement fallback behavior
  - [x] 3.7.1 Handle PaddleOCR service unavailable
    - [ ] Use full-page mode with single bbox
    - [ ] Log fallback decision
  - [x] 3.7.2 Handle GLM-OCR service unavailable
    - [ ] Return layout detection results only
    - [ ] Mark content extraction as failed
  - [x] 3.7.3 Handle both services unavailable
    - [ ] Return HTTP 503
    - [ ] Include error message
  - [x] 3.7.4 Handle partial region failures
    - [ ] Return successful regions
    - [ ] Include error list for failed regions

- [x] 3.8 Add circuit breaker pattern
  - [x] 3.8.1 Implement circuit breaker for PaddleOCR service
  - [x] 3.8.2 Implement circuit breaker for GLM-OCR service
  - [x] 3.8.3 Add failure threshold and recovery timeout
  - [x] 3.8.4 Log circuit breaker state changes

- [x] 3.9 Update job processing options
  - [x] 3.9.1 Add `enable_layout_detection` option
  - [x] 3.9.2 Add `layout_detection_options` object
  - [x] 3.9.3 Add `parallel_region_processing` option
  - [x] 3.9.4 Add `max_parallel_regions` option
  - [x] 3.9.5 Add `cache_layout_results` option

- [x] 3.10 Add logging and monitoring
  - [x] 3.10.1 Implement structured JSON logging
  - [x] 3.10.2 Add trace ID propagation
  - [x] 3.10.3 Log orchestration steps
  - [x] 3.10.4 Log fallback decisions
  - [x] 3.10.5 Add metrics for latency and error rates

- [x] 3.11 Write unit tests
  - [x] 3.11.1 Create tests for layout detection orchestration
  - [x] 3.11.2 Create tests for image cropping
  - [x] 3.11.3 Create tests for result assembly
  - [x] 3.11.4 Create tests for caching logic
  - [x] 3.11.5 Create tests for fallback behavior

- [x] 3.12 Write integration tests
  - [x] 3.12.1 Test full two-stage pipeline
  - [x] 3.12.2 Test fallback when PaddleOCR unavailable
  - [x] 3.12.3 Test fallback when GLM-OCR unavailable
  - [x] 3.12.4 Test caching functionality
  - [x] 3.12.5 Test batch region processing

## Task 4: Docker Compose Configuration

- [x] 4.1 Create docker-compose.yml
  - [x] 4.1.1 Define `paddleocr-service` container
    - [ ] Build from `services/paddleocr-service/Dockerfile`
    - [ ] Expose port 8001
    - [ ] Set environment variables
    - [ ] Add health check
  - [x] 4.1.2 Define `glm-ocr-service` container (modified)
    - [ ] Update existing container configuration
    - [ ] Expose port 8002
    - [ ] Add new endpoint health checks
  - [x] 4.1.3 Define `api-gateway` container (enhanced)
    - [ ] Update existing container configuration
    - [ ] Add service URL environment variables
    - [ ] Add Redis connection settings
  - [x] 4.1.4 Define supporting services
    - [ ] Redis for caching
    - [ ] MinIO for object storage
    - [ ] Temporal for workflow management

- [x] 4.2 Configure network settings
  - [x] 4.2.1 Create custom bridge network
  - [x] 4.2.2 Set service names for DNS resolution
  - [x] 4.2.3 Configure internal service communication

- [x] 4.3 Configure volumes
  - [x] 4.3.1 PaddleOCR model cache volume
  - [ ] GLM-OCR model cache volume
  - [ ] Redis data volume
  - [ ] MinIO data volume

- [x] 4.4 Configure resource limits
  - [x] 4.4.1 PaddleOCR service: 2 CPU, 4GB RAM (CPU mode) or 1 GPU, 6GB VRAM
  - [x] 4.4.2 GLM-OCR service: 1 GPU, 8GB VRAM, 16GB RAM
  - [x] 4.4.3 API Gateway: 1 CPU, 2GB RAM
  - [x] 4.4.4 Redis: 1 CPU, 2GB RAM
  - [x] 4.4.5 MinIO: 2 CPU, 4GB RAM

- [x] 4.5 Add health checks
  - [x] 4.5.1 Configure container health checks
  - [x] 4.5.2 Set restart policies
  - [x] 4.5.3 Add dependency ordering

- [x] 4.6 Create docker-compose.override.yml
  - [x] 4.6.1 Development environment overrides
  - [x] 4.6.2 GPU configuration for development
  - [x] 4.6.3 Volume mounts for development

- [x] 4.7 Create .env.example
  - [x] 4.7.1 Document all environment variables
  - [x] 4.7.2 Provide default values
  - [x] 4.7.3 Add comments for each variable

- [x] 4.8 Write deployment documentation
  - [x] 4.8.1 Docker Compose setup instructions
  - [x] 4.8.2 Environment variable reference
  - [x] 4.8.3 Troubleshooting common issues

## Task 5: Testing

- [-] 5.1 Unit tests
  - [x] 5.1.1 PaddleOCR service unit tests (>80% coverage)
    - [ ] Layout detector tests
    - [ ] Configuration tests
    - [ ] Model tests
  - [x] 5.1.2 GLM-OCR service unit tests (>80% coverage)
    - [ ] New endpoint tests
    - [ ] Prompt mapping tests
    - [ ] Validation tests
  - [ ] 5.1.3 API Gateway unit tests (>80% coverage)
    - [ ] Orchestration tests
    - [ ] Caching tests
    - [ ] Fallback tests

- [ ] 5.2 Integration tests
  - [ ] 5.2.1 End-to-end document processing
    - [ ] Test with layout detection enabled
    - [ ] Test with layout detection disabled
    - [ ] Test with multiple region types
  - [ ] 5.2.2 Service communication tests
    - [ ] Test PaddleOCR ↔ API Gateway
    - [ ] Test GLM-OCR ↔ API Gateway
    - [ ] Test service discovery
  - [ ] 5.2.3 Fallback behavior tests
    - [ ] Test PaddleOCR failure
    - [ ] Test GLM-OCR failure
    - [ ] Test both services failure
  - [ ] 5.2.4 Caching tests
    - [ ] Test cache hit/miss
    - [ ] Test cache invalidation
    - [ ] Test cache TTL

- [ ] 5.3 Performance tests
  - [ ] 5.3.1 Latency tests
    - [ ] Layout detection < 500ms
    - [ ] Content extraction per region < 3s
    - [ ] End-to-end < 10s for typical documents
  - [ ] 5.3.2 Throughput tests
    - [ ] PaddleOCR: 20 requests/second
    - [ ] GLM-OCR: 5 requests/second
    - [ ] API Gateway: 50 requests/second
  - [ ] 5.3.3 Concurrent request tests
    - [ ] Test 10 concurrent requests
    - [ ] Test 50 concurrent requests
    - [ ] Test 100 concurrent requests
  - [ ] 5.3.4 Memory leak tests
    - [ ] Long-running test (24 hours)
    - [ ] Monitor memory usage
    - [ ] Verify no memory growth

- [ ] 5.4 Acceptance tests
  - [ ] 5.4.1 Per-field bbox validation
    - [ ] Multiple regions detected (not just one full-page bbox)
    - [ ] Bbox coordinates accurate (within 5% of ground truth)
    - [ ] All detected regions have valid bboxes
  - [ ] 5.4.2 Backward compatibility tests
    - [ ] Existing `/jobs/upload` endpoint works
    - [ ] Response format matches existing schema
    - [ ] Full-page mode works when layout detection disabled
  - [ ] 5.4.3 Output format tests
    - [ ] Test text output format
    - [ ] Test JSON output format
    - [ ] Test markdown output format
    - [ ] Test table output format
    - [ ] Test key_value output format
    - [ ] Test structured output format
    - [ ] Test formula output format

- [ ] 5.5 Create test fixtures
  - [ ] 5.5.1 Sample images for testing
  - [ ] 5.5.2 Expected results for sample images
  - [ ] 5.5.3 Mock service responses

- [ ] 5.6 Create test documentation
  - [ ] 5.6.1 Test strategy document
  - [ ] 5.6.2 Test coverage report
  - [ ] 5.6.3 Performance test results

## Task 6: Documentation

- [ ] 6.1 API Documentation
  - [ ] 6.1.1 PaddleOCR Service OpenAPI Spec
    - [ ] Document `/detect-layout` endpoint
    - [ ] Document `/health` endpoint
    - [ ] Add request/response examples
    - [ ] Document error codes
  - [ ] 6.1.2 GLM-OCR Service OpenAPI Spec
    - [ ] Document `/extract-region` endpoint
    - [ ] Document `/extract-regions-batch` endpoint
    - [ ] Document `/jobs/upload` endpoint
    - [ ] Add request/response examples
  - [ ] 6.1.3 API Gateway OpenAPI Spec
    - [ ] Document enhanced endpoints
    - [ ] Document new job options
    - [ ] Add orchestration examples

- [ ] 6.2 Deployment Documentation
  - [ ] 6.2.1 Docker Compose Setup Guide
    - [ ] Prerequisites
    - [ ] Installation steps
    - [ ] Environment configuration
    - [ ] Starting services
    - [ ] Stopping services
  - [ ] 6.2.2 Environment Variable Reference
    - [ ] PaddleOCR service variables
    - [ ] GLM-OCR service variables
    - [ ] API Gateway variables
    - [ ] Supporting services variables
  - [ ] 6.2.3 Troubleshooting Guide
    - [ ] Common issues and solutions
    - [ ] Service logs location
    - [ ] Debugging tips

- [ ] 6.3 Architecture Documentation
  - [ ] 6.3.1 System Architecture Diagram
    - [ ] Service interaction diagram
    - [ ] Data flow diagram
    - [ ] Deployment architecture
  - [ ] 6.3.2 Sequence Diagrams
    - [ ] Document processing workflow
    - [ ] Layout detection workflow
    - [ ] Fallback workflow
  - [ ] 6.3.3 Component Diagram
    - [ ] Service components
    - [ ] Data models
    - [ ] Communication patterns

- [ ] 6.4 Developer Documentation
  - [ ] 6.4.1 Service Development Guide
    - [ ] PaddleOCR service development
    - [ ] GLM-OCR service development
    - [ ] API Gateway development
  - [ ] 6.4.2 Testing Guide
    - [ ] Running unit tests
    - [ ] Running integration tests
    - [ ] Running performance tests
  - [ ] 6.4.3 Contributing Guidelines
    - [ ] Code style
    - [ ] Commit message format
    - [ ] Pull request process

- [ ] 6.5 User Documentation
  - [ ] 6.5.1 API Usage Guide
    - [ ] Getting started
    - [ ] Authentication
    - [ ] Making requests
    - [ ] Handling responses
  - [ ] 6.5.2 Job Options Reference
    - [ ] Layout detection options
    - [ ] Region processing options
    - [ ] Caching options
  - [ ] 6.5.3 Error Codes Reference
    - [ ] HTTP status codes
    - [ ] Service-specific errors
    - [ ] Troubleshooting errors

- [ ] 6.6 Create README files
  - [ ] 6.6.1 Root README
    - [ ] Project overview
    - [ ] Quick start
    - [ ] Architecture overview
  - [ ] 6.6.2 PaddleOCR Service README
    - [ ] Service overview
    - [ ] API endpoints
    - [ ] Configuration
  - [ ] 6.6.3 GLM-OCR Service README
    - [ ] Service overview
    - [ ] API endpoints
    - [ ] Configuration
  - [ ] 6.6.4 API Gateway README
    - [ ] Service overview
    - [ ] Enhanced features
    - [ ] Configuration

- [ ] 6.7 Create changelog
  - [ ] 6.7.1 Document changes from monolithic to microservices
  - [ ] 6.7.2 Document new features
  - [ ] 6.7.3 Document breaking changes (if any)
