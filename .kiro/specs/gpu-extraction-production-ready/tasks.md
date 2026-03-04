# Implementation Plan: GPU Extraction Production Ready

## Overview

This implementation plan transforms the GPU extraction system into a production-ready service by addressing critical stability issues, adding request queueing, implementing word-level and key-value extraction, and establishing comprehensive monitoring and error handling. The implementation follows a phased approach: infrastructure setup, core feature implementation, testing, and integration.

## Tasks

- [x] 1. Configure Triton Inference Server for stability
  - [x] 1.1 Update Triton configuration in docker-compose.yml
    - Increase stub timeout to 600 seconds
    - Configure shared memory to 8MB
    - Enable GPU metrics and verbose logging
    - Set backend configuration for Python stub
    - Add CUDA environment variables for memory management
    - _Requirements: 1.4, 1.5, 1.6, 1.7_
  
  - [ ]* 1.2 Write property test for document size handling
    - **Property 1: Document Size Handling**
    - **Validates: Requirements 1.1**
  
  - [ ]* 1.3 Write property test for model persistence
    - **Property 3: Model Persistence**
    - **Validates: Requirements 1.6**

- [x] 2. Implement Redis request queue system
  - [x] 2.1 Create Redis queue interface and data structures
    - Define RequestQueue interface in Go
    - Implement QueuedJob and JobStatus types
    - Set up Redis client configuration
    - _Requirements: 2.1, 2.2, 2.6_
  
  - [x] 2.2 Implement queue operations (enqueue, dequeue, status)
    - Implement Enqueue with priority-based sorted set
    - Implement Dequeue with atomic operations
    - Implement UpdateStatus and GetStatus methods
    - Implement GetQueueLength and GetEstimatedWaitTime
    - _Requirements: 2.1, 2.2, 2.3, 2.4_
  
  - [x] 2.3 Implement GPU lock mechanism
    - Implement AcquireGPULock with Redis distributed lock
    - Implement ReleaseGPULock with proper cleanup
    - Add lock TTL and automatic expiration
    - _Requirements: 2.6_
  
  - [x] 2.4 Implement queue cancellation
    - Add CancelJob method to remove from queue
    - Trigger next job processing on cancellation
    - _Requirements: 2.7_
  
  - [ ]* 2.5 Write property tests for queue operations
    - **Property 4: Queue Sequential Processing**
    - **Property 5: Queue Position Assignment**
    - **Property 6: Queue Status Polling**
    - **Property 7: Queue Cancellation**
    - **Validates: Requirements 2.1, 2.2, 2.4, 2.6, 2.7**

- [x] 3. Integrate queue with API Gateway
  - [x] 3.1 Modify upload handler to enqueue jobs
    - Update uploadDocument to create QueuedJob
    - Enqueue job to Redis before starting workflow
    - Handle queue full errors with HTTP 429
    - Return estimated wait time in response
    - _Requirements: 2.1, 2.2, 2.3_
  
  - [x] 3.2 Create queue status endpoint
    - Implement GET /queue/status endpoint
    - Return queue length and estimated wait time
    - _Requirements: 2.4_
  
  - [x] 3.3 Update health check endpoint
    - Add queue status to health check response
    - Include Triton, GLM-OCR, Redis, and database status
    - _Requirements: 7.6_

- [x] 4. Modify Temporal Worker for queue integration
  - [x] 4.1 Update workflow to poll queue
    - Add queue polling logic at workflow start
    - Wait for job status to become PROCESSING
    - Implement CheckQueueStatus activity
    - _Requirements: 2.1, 2.4_
  
  - [x] 4.2 Implement GPU lock acquisition in workflow
    - Add AcquireGPULock activity
    - Add ReleaseGPULock activity with defer
    - Handle lock acquisition failures
    - _Requirements: 2.6_
  
  - [x] 4.3 Implement parallel page processing
    - Use workflow.Go for concurrent page processing
    - Implement semaphore for max 3 concurrent pages
    - Add sync.WaitGroup for coordination
    - _Requirements: 8.1_
  
  - [x] 4.4 Implement document chunking for large files
    - Split documents >5MB into chunks
    - Process each chunk separately
    - Aggregate chunk results
    - _Requirements: 8.3_
  
  - [x] 4.5 Implement retry logic with exponential backoff
    - Configure RetryPolicy with exponential backoff
    - Add jitter to prevent thundering herd
    - Limit to maximum 3 retry attempts
    - Store failure details after final retry
    - _Requirements: 7.4, 7.5_
  
  - [ ]* 4.6 Write property tests for parallel processing and retry
    - **Property 23: Exponential Backoff Retry**
    - **Property 24: Failure Detail Storage**
    - **Property 25: Parallel Page Processing**
    - **Property 26: Preprocessing Cache**
    - **Property 27: Document Chunking**
    - **Validates: Requirements 7.4, 7.5, 8.1, 8.2, 8.3**

- [x] 5. Checkpoint - Ensure queue and workflow integration tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement GPU memory monitoring
  - [x] 6.1 Create GPU monitor module
    - Create GPUMonitor class in Python
    - Implement get_memory_stats method using torch.cuda
    - Implement has_sufficient_memory check
    - Implement clear_cache method
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
  
  - [x] 6.2 Integrate GPU monitor with GLM-OCR service
    - Add GPU memory check before accepting requests
    - Return HTTP 503 when memory < 2GB
    - Log GPU memory before and after each inference
    - Include GPU memory in extraction results
    - _Requirements: 6.2, 6.3, 6.4, 6.5_
  
  - [x] 6.3 Expose GPU metrics via Prometheus
    - Add Prometheus metrics endpoint to Triton
    - Export GPU memory usage metrics
    - Export request processing metrics
    - _Requirements: 6.1_
  
  - [ ]* 6.4 Write property tests for GPU monitoring
    - **Property 21: GPU Memory Logging**
    - **Property 22: GPU Memory Pre-Flight Check**
    - **Validates: Requirements 6.2, 6.4**

- [x] 7. Implement word-level bounding box extraction
  - [x] 7.1 Create WordLevelExtractor class
    - Implement extract_words method
    - Parse GLM-OCR output to identify word boundaries
    - Generate bounding boxes for each word
    - Calculate confidence scores for word-level boxes
    - _Requirements: 3.1, 3.2, 3.4_
  
  - [x] 7.2 Handle hyphenated words across lines
    - Detect hyphenation patterns
    - Create separate bounding boxes for each part
    - _Requirements: 3.3_
  
  - [x] 7.3 Implement word order preservation
    - Sort words by reading sequence (top-to-bottom, left-to-right)
    - Maintain original document flow
    - _Requirements: 3.6_
  
  - [x] 7.4 Add word-level JSON output format
    - Structure output as array of {text, bbox, confidence}
    - Validate JSON schema
    - _Requirements: 3.5_
  
  - [ ]* 7.5 Write property tests for word-level extraction
    - **Property 8: Word-Level Bounding Boxes**
    - **Property 9: Word-Level JSON Structure**
    - **Property 10: Word Order Preservation**
    - **Validates: Requirements 3.1, 3.2, 3.4, 3.5, 3.6**

- [x] 8. Implement key-value pair extraction
  - [x] 8.1 Create KeyValueExtractor class
    - Implement extract_key_values method
    - Define KeyValuePair model with separate bboxes
    - _Requirements: 4.1, 4.2_
  
  - [x] 8.2 Implement pattern recognition for key-value pairs
    - Detect colon-separated patterns ("Key: Value")
    - Detect table-based patterns (key column, value column)
    - Detect form-field patterns (label above/beside field)
    - _Requirements: 4.4_
  
  - [x] 8.3 Handle multi-value keys
    - Group multiple values under same key
    - Provide individual bounding boxes for each value
    - _Requirements: 4.3_
  
  - [x] 8.4 Handle multi-line key-value pairs
    - Create combined bounding box encompassing all lines
    - _Requirements: 4.5_
  
  - [x] 8.5 Add confidence scores for key-value extraction
    - Calculate key detection confidence
    - Calculate value detection confidence
    - Calculate key-value association confidence
    - _Requirements: 4.6_
  
  - [ ]* 8.6 Write property tests for key-value extraction
    - **Property 11: Key-Value Detection**
    - **Property 12: Key-Value Bounding Boxes**
    - **Property 13: Multi-Value Key Grouping**
    - **Property 14: Key-Value Pattern Recognition**
    - **Property 15: Multi-Line Key-Value Bounding Box**
    - **Property 16: Key-Value Confidence Scores**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6**

- [x] 9. Implement extraction format and granularity options
  - [x] 9.1 Create ExtractionOptions model
    - Define granularity options (block, line, word)
    - Define output_format options (text, json, markdown, table, key_value, structured)
    - Add include_coordinates and include_confidence flags
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  
  - [x] 9.2 Implement conditional coordinates inclusion
    - Include bounding boxes only when include_coordinates=true
    - Apply to specified granularity level
    - _Requirements: 5.3_
  
  - [x] 9.3 Implement conditional confidence inclusion
    - Include confidence scores only when include_confidence=true
    - Apply to all extracted elements
    - _Requirements: 5.4_
  
  - [x] 9.4 Implement table format extraction
    - Preserve row and column structure
    - Provide cell-level bounding boxes
    - _Requirements: 5.6_
  
  - [x] 9.5 Implement structured format extraction
    - Create hierarchical document structure
    - Provide section-level bounding boxes
    - _Requirements: 5.7_
  
  - [ ]* 9.6 Write property tests for extraction options
    - **Property 17: Conditional Coordinates Inclusion**
    - **Property 18: Conditional Confidence Inclusion**
    - **Property 19: Table Structure Preservation**
    - **Property 20: Structured Format Hierarchy**
    - **Validates: Requirements 5.3, 5.4, 5.6, 5.7**

- [x] 10. Checkpoint - Ensure extraction feature tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Implement extraction result validation
  - [x] 11.1 Create validation module
    - Validate bounding boxes within page boundaries
    - Validate confidence scores in range 0.0-1.0
    - Validate word boxes don't overlap incorrectly
    - Validate key-value structural integrity (no orphaned values)
    - _Requirements: 9.1, 9.2, 9.3, 9.4_
  
  - [x] 11.2 Add validation warnings to response
    - Log validation warnings for low confidence scores
    - Include warnings in response metadata
    - _Requirements: 9.6_
  
  - [x] 11.3 Implement round-trip validation for structured format
    - Extract with structured format
    - Reconstruct document
    - Verify content preservation
    - _Requirements: 9.5_
  
  - [ ]* 11.4 Write property tests for validation
    - **Property 29: Bounding Box Boundary Validation**
    - **Property 30: Word Box Non-Overlap**
    - **Property 31: Confidence Score Range**
    - **Property 32: Key-Value Structural Integrity**
    - **Property 33: Structured Format Round-Trip**
    - **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5**

- [x] 12. Implement comprehensive error handling
  - [x] 12.1 Implement GPU memory error handling
    - Detect CUDA out-of-memory exceptions
    - Return HTTP 503 with retry-after header
    - Log GPU memory stats with error
    - _Requirements: 7.3, 6.3_
  
  - [x] 12.2 Implement Triton stub crash handling
    - Detect stub process failures
    - Return HTTP 503 for in-flight requests
    - Log restart events with context
    - _Requirements: 7.1, 1.5_
  
  - [x] 12.3 Implement document size validation
    - Check document size before processing
    - Return HTTP 413 for documents >10MB
    - Include max size in error response
    - _Requirements: 7.2_
  
  - [x] 12.4 Implement queue full error handling
    - Check queue capacity before enqueue
    - Return HTTP 429 with retry-after header
    - _Requirements: 7.3_
  
  - [x] 12.5 Implement timeout error handling
    - Configure workflow and activity timeouts
    - Store partial results on timeout
    - Log timeout with processing metadata
    - _Requirements: 1.3_
  
  - [x] 12.6 Implement structured error logging
    - Log all errors with structured JSON format
    - Include error context (stack trace, request params, system state)
    - _Requirements: 10.5_

- [x] 13. Implement comprehensive logging and observability
  - [x] 13.1 Implement structured JSON logging
    - Configure all services to output JSON logs
    - Include standard fields (timestamp, level, service, request_id)
    - _Requirements: 10.6_
  
  - [x] 13.2 Implement extraction request logging
    - Log request_id, document_size, processing_time, status
    - Log at start and completion of each request
    - _Requirements: 10.1_
  
  - [x] 13.3 Implement Triton health check logging
    - Log timestamp and GPU memory usage
    - Log stub process health check results
    - _Requirements: 10.2_
  
  - [x] 13.4 Implement queue metrics emission
    - Emit queue length, average wait time, throughput
    - Export metrics to Prometheus
    - _Requirements: 10.3_
  
  - [x] 13.5 Integrate distributed tracing with Jaeger
    - Add Jaeger client to all services
    - Trace requests across microservices
    - Include trace_id in all logs
    - _Requirements: 10.4_
  
  - [ ]* 13.6 Write property tests for logging and metrics
    - **Property 34: Extraction Request Logging**
    - **Property 35: Health Check Logging**
    - **Property 36: Queue Metrics Emission**
    - **Property 37: Structured JSON Logs**
    - **Validates: Requirements 10.1, 10.2, 10.3, 10.6**

- [x] 14. Implement performance optimizations
  - [x] 14.1 Implement preprocessing cache
    - Cache preprocessed images with TTL
    - Use cached images for retry attempts
    - _Requirements: 8.2_
  
  - [x] 14.2 Implement model warmup on startup
    - Run dummy inference on GLM-OCR service startup
    - Reduce first-request latency
    - _Requirements: 8.4_
  
  - [x] 14.3 Add performance monitoring and warnings
    - Log warning when page processing exceeds 30 seconds
    - Include page size and complexity metrics
    - Monitor average processing time per page
    - _Requirements: 8.5, 8.6_
  
  - [ ]* 14.4 Write property test for average processing time
    - **Property 28: Average Processing Time**
    - **Validates: Requirements 8.6**

- [x] 15. Create monitoring dashboard
  - [x] 15.1 Set up Prometheus and Grafana
    - Configure Prometheus to scrape all service metrics
    - Create Grafana datasource for Prometheus
    - _Requirements: 6.6_
  
  - [x] 15.2 Create GPU monitoring dashboard
    - Display real-time GPU memory usage
    - Display GPU utilization and temperature
    - Add alerts for high memory usage (>90%)
    - _Requirements: 6.6_
  
  - [x] 15.3 Create queue monitoring dashboard
    - Display queue length over time
    - Display average wait time and processing time
    - Display throughput metrics
    - _Requirements: 6.6_
  
  - [x] 15.4 Create request processing dashboard
    - Display request success/failure rates
    - Display processing time percentiles (p50, p95, p99)
    - Display error breakdown by type
    - _Requirements: 6.6_

- [ ] 16. Integration and end-to-end testing
  - [ ]* 16.1 Write integration test for complete extraction flow
    - Test upload → queue → process → retrieve results
    - Verify all components work together
  
  - [ ]* 16.2 Write integration test for concurrent request handling
    - Submit 10 concurrent requests
    - Verify all complete successfully with proper queueing
  
  - [ ]* 16.3 Write integration test for large document processing
    - Submit 20-page PDF
    - Verify parallel processing and result aggregation
  
  - [ ]* 16.4 Write integration test for error recovery
    - Trigger GPU memory error
    - Verify retry and eventual success
  
  - [ ]* 16.5 Write integration test for queue full scenario
    - Fill queue to capacity
    - Verify HTTP 429 responses and recovery

- [ ] 17. Performance testing and optimization
  - [ ]* 17.1 Run load testing with 50 concurrent users
    - Sustained load for 1 hour
    - Verify system stability and throughput
  
  - [ ]* 17.2 Run spike testing
    - Ramp from 0 to 100 users in 1 minute
    - Verify queue handles spike gracefully
  
  - [ ]* 17.3 Run stress testing
    - Gradually increase load until degradation
    - Identify bottlenecks and capacity limits

- [-] 18. Documentation and deployment preparation
  - [ ] 18.1 Update API documentation
    - Document new queue endpoints
    - Document extraction options (granularity, formats)
    - Document error responses and retry behavior
  
  - [ ] 18.2 Create deployment guide
    - Document Triton configuration changes
    - Document Redis setup and configuration
    - Document monitoring setup (Prometheus, Grafana, Jaeger)
  
  - [ ] 18.3 Create operational runbook
    - Document common issues and resolutions
    - Document monitoring and alerting procedures
    - Document scaling and capacity planning

- [ ] 19. Final checkpoint - Ensure all tests pass and system is production-ready
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties across all inputs
- Integration and performance tests validate end-to-end system behavior
- The implementation uses Go for API Gateway and Temporal Worker, Python for GLM-OCR service
- Checkpoints ensure incremental validation at key milestones
- All 37 properties from the design document are covered in property test tasks
