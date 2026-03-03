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

- [ ] 1.5 Implement FastAPI application
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

- [ ] 1.8 Create Dockerfile
  - [ ] 1.8.1 Use `python:3.11-slim` base image
  - [ ] 1.8.2 Install PaddleOCR and dependencies
  - [ ] 1.8.3 Copy application code
  - [ ] 1.8.4 Set up non-root user
  - [ ] 1.8.5 Expose port 8001
  - [ ] 1.8.6 Add health check

- [ ] 1.9 Create requirements.txt
  - [x] 1.9.1 Add paddlepaddle (CPU or GPU)
  - [x] 1.9.2 Add paddleocr 3.4.0+
  - [x] 1.9.3 Add fastapi 0.100+
  - [x] 1.9.4 Add uvicorn
  - [x] 1.9.5 Add pillow, numpy
  - [x] 1.9.6 Add pydantic, pydantic-settings

- [ ] 1.10 Write unit tests
  - [ ] 1.10.1 Create `services/paddleocr-service/tests/test_config.py`
  - [ ] 1.10.2 Create `services/paddleocr-service/tests/test_layout_detector.py`
  - [ ] 1.10.3 Create `services/paddleocr-service/tests/test_models.py`
  - [ ] 1.10.4 Test configuration loading
  - [ ] 1.10.5 Test layout detection with mock images
  - [ ] 1.10.6 Test confidence filtering
  - [ ] 1.10.7 Test error handling

- [ ] 1.11 Write integration tests
  - [ ] 1.11.1 Create `services/paddleocr-service/tests/test_api.py`
  - [ ] 1.11.2 Test `/detect-layout` endpoint with real model
  - [ ] 1.11.3 Test `/health` endpoint
  - [ ] 1.11.4 Test error responses
  - [ ] 1.11.5 Test image validation

## Task 2: GLM-OCR Service Modifications

- [ ] 2.1 Review existing GLM-OCR service structure
  - [ ] 2.1.1 Examine current `/jobs/upload` endpoint
  - [ ] 2.1.2 Identify existing models and prompts
  - [ ] 2.1.3 Document current request/response formats

- [ ] 2.2 Implement /extract-region endpoint
  - [ ] 2.2.1 Add `POST /extract-region` endpoint
  - [ ] 2.2.2 Create request model for single region
  - [ ] 2.2.3 Create response model with content and confidence
  - [ ] 2.2.4 Implement region-type-specific prompts
  - [ ] 2.2.5 Add processing time tracking
  - [ ] 2.2.6 Add token usage tracking

- [ ] 2.3 Implement /extract-regions-batch endpoint
  - [ ] 2.3.1 Add `POST /extract-regions-batch` endpoint
  - [ ] 2.3.2 Create batch request model
  - [ ] 2.3.3 Create batch response model
  - [ ] 2.3.4 Implement parallel region processing
  - [ ] 2.3.5 Add per-region error handling
  - [ ] 2.3.6 Track total processing time

- [ ] 2.4 Implement region type prompt mapping
  - [ ] 2.4.1 Create prompt configuration
  - [ ] 2.4.2 Map region types to prompts:
    - [ ] text → "Text Recognition:"
    - [ ] table → "Table Recognition:"
    - [ ] formula → "Formula Recognition:"
    - [ ] title → "Title Recognition:"
    - [ ] figure → "Figure Recognition:"
  - [ ] 2.4.3 Support custom prompts

- [ ] 2.5 Add input validation
  - [ ] 2.5.1 Validate base64 image format
  - [ ] 2.5.2 Validate region type
  - [ ] 2.5.3 Validate prompt length
  - [ ] 2.5.4 Validate max_tokens parameter

- [ ] 2.6 Update existing endpoints
  - [ ] 2.6.1 Ensure `/jobs/upload` maintains backward compatibility
  - [ ] 2.6.2 Add option to enable layout detection mode
  - [ ] 2.6.3 Add response format option for per-field bboxes

- [ ] 2.7 Add logging and monitoring
  - [ ] 2.7.1 Implement structured JSON logging
  - [ ] 2.7.2 Add request ID tracking
  - [ ] 2.7.3 Log model inference time
  - [ ] 2.7.4 Log token usage

- [ ] 2.8 Update Docker configuration
  - [ ] 2.8.1 Update existing Dockerfile
  - [ ] 2.8.2 Add new endpoint handlers
  - [ ] 2.8.3 Update health check endpoint
  - [ ] 2.8.4 Update environment variables

- [ ] 2.9 Write unit tests
  - [ ] 2.9.1 Create tests for new endpoints
  - [ ] 2.9.2 Test prompt mapping
  - [ ] 2.9.3 Test input validation
  - [ ] 2.9.4 Test batch processing

- [ ] 2.10 Write integration tests
  - [ ] 2.10.1 Test `/extract-region` with real model
  - [ ] 2.10.2 Test `/extract-regions-batch` with multiple regions
  - [ ] 2.10.3 Test backward compatibility with `/jobs/upload`

## Task 3: API Gateway Orchestration Enhancements

- [ ] 3.1 Review existing API Gateway structure
  - [ ] 3.1.1 Examine current job processing flow
  - [ ] 3.1.2 Identify existing service URLs and endpoints
  - [ ] 3.1.3 Document current response formats

- [ ] 3.2 Implement layout detection orchestration
  - [ ] 3.2.1 Add PaddleOCR service client
  - [ ] 3.2.2 Implement layout detection request
  - [ ] 3.2.3 Handle layout detection response
  - [ ] 3.2.4 Add timeout handling (30s default)
  - [ ] 3.2.5 Add retry logic (3 attempts, exponential backoff)

- [ ] 3.3 Implement image cropping into regions
  - [ ] 3.3.1 Create image cropping utility
  - [ ] 3.3.2 Implement bbox-based cropping
  - [ ] 3.3.3 Add padding option for regions
  - [ ] 3.3.4 Handle edge cases (bbox outside image)
  - [ ] 3.3.5 Convert cropped images to base64

- [ ] 3.4 Implement region content extraction
  - [ ] 3.4.1 Add GLM-OCR service client
  - [ ] 3.4.2 Implement batch region processing
  - [ ] 3.4.3 Map region types to prompts
  - [ ] 3.4.4 Handle partial failures
  - [ ] 3.4.5 Add parallel processing option

- [ ] 3.5 Implement result assembly
  - [ ] 3.5.1 Create unified result model
  - [ ] 3.5.2 Assemble per-field bboxes
  - [ ] 3.5.3 Generate markdown output
  - [ ] 3.5.4 Calculate overall confidence
  - [ ] 3.5.5 Track timing per stage

- [ ] 3.6 Implement caching strategy
  - [ ] 3.6.1 Add Redis client
  - [ ] 3.6.2 Implement layout detection caching
  - [ ] 3.6.3 Create cache key from image hash + options
  - [ ] 3.6.4 Set configurable TTL (default 1 hour)
  - [ ] 3.6.5 Implement cache invalidation

- [ ] 3.7 Implement fallback behavior
  - [ ] 3.7.1 Handle PaddleOCR service unavailable
    - [ ] Use full-page mode with single bbox
    - [ ] Log fallback decision
  - [ ] 3.7.2 Handle GLM-OCR service unavailable
    - [ ] Return layout detection results only
    - [ ] Mark content extraction as failed
  - [ ] 3.7.3 Handle both services unavailable
    - [ ] Return HTTP 503
    - [ ] Include error message
  - [ ] 3.7.4 Handle partial region failures
    - [ ] Return successful regions
    - [ ] Include error list for failed regions

- [ ] 3.8 Add circuit breaker pattern
  - [ ] 3.8.1 Implement circuit breaker for PaddleOCR service
  - [ ] 3.8.2 Implement circuit breaker for GLM-OCR service
  - [ ] 3.8.3 Add failure threshold and recovery timeout
  - [ ] 3.8.4 Log circuit breaker state changes

- [ ] 3.9 Update job processing options
  - [ ] 3.9.1 Add `enable_layout_detection` option
  - [ ] 3.9.2 Add `layout_detection_options` object
  - [ ] 3.9.3 Add `parallel_region_processing` option
  - [ ] 3.9.4 Add `max_parallel_regions` option
  - [ ] 3.9.5 Add `cache_layout_results` option

- [ ] 3.10 Add logging and monitoring
  - [ ] 3.10.1 Implement structured JSON logging
  - [ ] 3.10.2 Add trace ID propagation
  - [ ] 3.10.3 Log orchestration steps
  - [ ] 3.10.4 Log fallback decisions
  - [ ] 3.10.5 Add metrics for latency and error rates

- [ ] 3.11 Write unit tests
  - [ ] 3.11.1 Create tests for layout detection orchestration
  - [ ] 3.11.2 Create tests for image cropping
  - [ ] 3.11.3 Create tests for result assembly
  - [ ] 3.11.4 Create tests for caching logic
  - [ ] 3.11.5 Create tests for fallback behavior

- [ ] 3.12 Write integration tests
  - [ ] 3.12.1 Test full two-stage pipeline
  - [ ] 3.12.2 Test fallback when PaddleOCR unavailable
  - [ ] 3.12.3 Test fallback when GLM-OCR unavailable
  - [ ] 3.12.4 Test caching functionality
  - [ ] 3.12.5 Test batch region processing

## Task 4: Docker Compose Configuration

- [ ] 4.1 Create docker-compose.yml
  - [ ] 4.1.1 Define `paddleocr-service` container
    - [ ] Build from `services/paddleocr-service/Dockerfile`
    - [ ] Expose port 8001
    - [ ] Set environment variables
    - [ ] Add health check
  - [ ] 4.1.2 Define `glm-ocr-service` container (modified)
    - [ ] Update existing container configuration
    - [ ] Expose port 8002
    - [ ] Add new endpoint health checks
  - [ ] 4.1.3 Define `api-gateway` container (enhanced)
    - [ ] Update existing container configuration
    - [ ] Add service URL environment variables
    - [ ] Add Redis connection settings
  - [ ] 4.1.4 Define supporting services
    - [ ] Redis for caching
    - [ ] MinIO for object storage
    - [ ] Temporal for workflow management

- [ ] 4.2 Configure network settings
  - [ ] 4.2.1 Create custom bridge network
  - [ ] 4.2.2 Set service names for DNS resolution
  - [ ] 4.2.3 Configure internal service communication

- [ ] 4.3 Configure volumes
  - [ ] 4.3.1 PaddleOCR model cache volume
  - [ ] GLM-OCR model cache volume
  - [ ] Redis data volume
  - [ ] MinIO data volume

- [ ] 4.4 Configure resource limits
  - [ ] 4.4.1 PaddleOCR service: 2 CPU, 4GB RAM (CPU mode) or 1 GPU, 6GB VRAM
  - [ ] 4.4.2 GLM-OCR service: 1 GPU, 8GB VRAM, 16GB RAM
  - [ ] 4.4.3 API Gateway: 1 CPU, 2GB RAM
  - [ ] 4.4.4 Redis: 1 CPU, 2GB RAM
  - [ ] 4.4.5 MinIO: 2 CPU, 4GB RAM

- [ ] 4.5 Add health checks
  - [ ] 4.5.1 Configure container health checks
  - [ ] 4.5.2 Set restart policies
  - [ ] 4.5.3 Add dependency ordering

- [ ] 4.6 Create docker-compose.override.yml
  - [ ] 4.6.1 Development environment overrides
  - [ ] 4.6.2 GPU configuration for development
  - [ ] 4.6.3 Volume mounts for development

- [ ] 4.7 Create .env.example
  - [ ] 4.7.1 Document all environment variables
  - [ ] 4.7.2 Provide default values
  - [ ] 4.7.3 Add comments for each variable

- [ ] 4.8 Write deployment documentation
  - [ ] 4.8.1 Docker Compose setup instructions
  - [ ] 4.8.2 Environment variable reference
  - [ ] 4.8.3 Troubleshooting common issues

## Task 5: Testing

- [ ] 5.1 Unit tests
  - [ ] 5.1.1 PaddleOCR service unit tests (>80% coverage)
    - [ ] Layout detector tests
    - [ ] Configuration tests
    - [ ] Model tests
  - [ ] 5.1.2 GLM-OCR service unit tests (>80% coverage)
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

- [-] 5.3 Performance tests
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
