d# Requirements Document

## Introduction

This document specifies requirements for making the GPU extraction system production-ready. The system currently uses a microservice architecture with Triton Inference Server (GPU), GLM-OCR service, API Gateway, and Temporal Worker to extract text and structured data from documents (PDFs, images). While basic extraction works, the system has critical stability issues with larger documents, lacks proper request queueing, and is missing key features like word-level and key-value bounding box extraction.

The system must handle real-world production workloads reliably, process documents of varying sizes without crashes, queue concurrent requests efficiently, and provide detailed extraction results with bounding boxes at multiple granularity levels.

## Glossary

- **Triton_Server**: NVIDIA Triton Inference Server that hosts the GLM-OCR model and handles GPU inference requests
- **Stub_Process**: Python backend process in Triton that loads and executes the GLM-OCR model
- **GLM_OCR_Service**: FastAPI service that wraps the GLM-OCR vision-language model for region-based content extraction
- **API_Gateway**: Go-based service that receives client requests and orchestrates document processing
- **Temporal_Worker**: Go-based worker that executes document processing workflows via Temporal
- **Request_Queue**: System component that manages and prioritizes incoming extraction requests
- **Bounding_Box**: Rectangular coordinates (x, y, width, height) that define the location of extracted content on a page
- **Word_Level_Extraction**: Extraction that provides bounding boxes for individual words
- **Key_Value_Pair**: Structured data consisting of a label (key) and its associated value, such as "Invoice Number: 12345"
- **Extraction_Format**: Output format for extracted content (text, json, markdown, table, key_value, structured)
- **Granularity_Level**: Level of detail for extraction results (block, line, word)
- **GPU_Memory**: Video RAM (VRAM) available on the NVIDIA RTX 2050 GPU for model inference
- **Stub_Timeout**: Maximum time allowed for the Stub_Process to respond before being considered unhealthy

## Requirements

### Requirement 1: Triton Stub Process Stability

**User Story:** As a system operator, I want the Triton stub process to handle documents of all sizes without crashing, so that extraction requests complete reliably without delays or failures.

#### Acceptance Criteria

1. WHEN a PDF document up to 10MB is submitted for extraction, THE Triton_Server SHALL process it without the Stub_Process becoming unhealthy
2. WHEN the Stub_Process encounters a GPU memory limitation, THE Triton_Server SHALL reduce batch size and retry the inference
3. WHEN a document requires more than 60 seconds to process, THE Stub_Process SHALL continue processing without timing out
4. THE Triton_Server SHALL configure the Stub_Timeout to at least 600 seconds
5. WHEN the Stub_Process restarts, THE Triton_Server SHALL log the restart event with GPU memory usage and document size
6. THE Triton_Server SHALL keep the GLM-OCR model loaded in GPU_Memory between requests
7. WHEN GPU_Memory usage exceeds 90% of available VRAM, THE Triton_Server SHALL log a warning with current memory metrics

### Requirement 2: Request Queue Management

**User Story:** As a system administrator, I want concurrent extraction requests to be queued and processed efficiently, so that the system handles multiple users without overloadins via polling endpoint
5. WHEN a request has been queued for more than 5 minutes, THE Request_Queue SHALL send a notification to the requesting client
6. THE Request_Queue SHALL limit concurrent GPU inference requests to 1 to prevent GPU_Memory exhaustion
7. WHEN a queued request is cancelled by the client, THE Request_Queue SHALL remove it and process the next request

### Requirement 3: Word-Level Bounding Box Extraction

**User Story:** As a developer, I want to extract bounding boxes for individual words, so that I can build features like text highlighting, word search, and precise content location.

#### Acceptance Criteria

1. WHEN extraction is requested with granularity_level "word", THE GLM_OCR_Service SHALL return Bounding_Box coordinates for each extracted word
2. THE Bounding_Box SHALL include x, y, width, and height values in pixels relative to the page origin
3. WHEN a word spans multiple lines due to hyphenation, THE GLM_OCR_Service SHALL provide separate Bounding_Box entries for each part
4. THE GLM_OCR_Service SHALL include confidence scores for each word-level Bounding_Box
5. WHEN the extraction format is "json", THE GLM_OCR_Service SHALL structure word-level results as an array of objects with text, bbox, and confidence fields
6. THE GLM_OCR_Service SHALL maintain word order matching the reading sequence on the page

### Requirement 4: Key-Value Pair Extraction with Bounding Boxes

**User Story:** As a data extraction engineer, I want to extract key-value pairs with bounding boxes for both keys and values, so that I can accurately extract structured information like invoice fields and form data.

#### Acceptance Criteria

1. WHEN extraction format is "key_value", THE GLM_OCR_Service SHALL identify Key_Value_Pair structures in the document
2. THE GLM_OCR_Service SHALL provide separate Bounding_Box coordinates for the key portion and value portion of each Key_Value_Pair
3. WHEN a key has multiple associated values, THE GLM_OCR_Service SHALL group them under the same key with individual value Bounding_Box entries
4. THE GLM_OCR_Service SHALL recognize common key-value patterns including colon-separated, table-based, and form-field formats
5. WHEN a Key_Value_Pair spans multiple lines, THE GLM_OCR_Service SHALL provide a combined Bounding_Box encompassing all lines
6. THE GLM_OCR_Service SHALL include confidence scores for key detection, value detection, and key-value association

### Requirement 5: Comprehensive Extraction Format Testing

**User Story:** As a QA engineer, I want all extraction formats and options to be thoroughly tested, so that I can verify the system works correctly for all supported use cases.

#### Acceptance Criteria

1. THE System SHALL support extraction formats: text, json, markdown, table, key_value, and structured
2. THE System SHALL support Granularity_Level options: block, line, and word
3. WHEN coordinates option is enabled, THE System SHALL include Bounding_Box data in the response for the specified Granularity_Level
4. WHEN confidence option is enabled, THE System SHALL include confidence scores for each extracted element
5. THE System SHALL provide a test suite that validates each combination of Extraction_Format and Granularity_Level
6. THE System SHALL validate that table format extraction preserves row and column structure with cell-level Bounding_Box data
7. WHEN structured format is requested, THE System SHALL return hierarchical document structure with section-level Bounding_Box coordinates

### Requirement 6: GPU Memory Monitoring and Management

**User Story:** As a system operator, I want real-time GPU memory monitoring and automatic management, so that I can prevent out-of-memory errors and optimize resource utilization.

#### Acceptance Criteria

1. THE Triton_Server SHALL expose GPU_Memory usage metrics via Prometheus endpoint
2. THE Triton_Server SHALL log GPU_Memory usage before and after each inference request
3. WHEN GPU_Memory allocation fails, THE Triton_Server SHALL return a descriptive error message with current memory usage
4. THE GLM_OCR_Service SHALL query available GPU_Memory before accepting batch requests
5. WHEN available GPU_Memory is below 2GB, THE GLM_OCR_Service SHALL reject new requests with HTTP 503 and retry-after header
6. THE System SHALL provide a dashboard displaying real-time GPU_Memory usage, request queue length, and processing times

### Requirement 7: Graceful Error Handling and Recovery

**User Story:** As an API consumer, I want clear error messages and automatic recovery mechanisms, so that I understand failures and can retry requests successfully.

#### Acceptance Criteria

1. WHEN the Stub_Process crashes, THE Triton_Server SHALL automatically restart it and return HTTP 503 for in-flight requests
2. WHEN a document exceeds GPU_Memory capacity, THE API_Gateway SHALL return HTTP 413 with maximum supported document size
3. WHEN the Request_Queue is full, THE API_Gateway SHALL return HTTP 429 with retry-after header indicating estimated wait time
4. THE System SHALL implement exponential backoff for automatic retries with maximum 3 retry attempts
5. WHEN an extraction request fails after all retries, THE System SHALL store the failure details for debugging
6. THE API_Gateway SHALL provide a health check endpoint that reports the status of Triton_Server, GLM_OCR_Service, and Request_Queue

### Requirement 8: Performance Optimization for Large Documents

**User Story:** As a system architect, I want large documents to be processed efficiently, so that processing times remain acceptable even for complex multi-page PDFs.

#### Acceptance Criteria

1. WHEN a PDF has more than 10 pages, THE Temporal_Worker SHALL process pages in parallel with maximum 3 concurrent page extractions
2. THE System SHALL cache preprocessed images to avoid redundant preprocessing for retry attempts
3. WHEN a document is larger than 5MB, THE Temporal_Worker SHALL split it into chunks and process each chunk separately
4. THE GLM_OCR_Service SHALL implement model warmup on startup to reduce first-request latency
5. WHEN processing time exceeds 30 seconds for a single page, THE System SHALL log a performance warning with page size and complexity metrics
6. THE System SHALL maintain average processing time below 10 seconds per page for documents under 1MB

### Requirement 9: Extraction Result Validation

**User Story:** As a quality assurance engineer, I want extraction results to be validated for correctness and completeness, so that downstream systems receive reliable data.

#### Acceptance Criteria

1. THE GLM_OCR_Service SHALL validate that all Bounding_Box coordinates are within page boundaries
2. WHEN word-level extraction is requested, THE GLM_OCR_Service SHALL verify that word bounding boxes do not overlap incorrectly
3. THE System SHALL validate that confidence scores are between 0.0 and 1.0
4. WHEN key_value format is requested, THE System SHALL verify that each value has an associated key
5. THE System SHALL implement a round-trip property test for structured format: parse document, format to structured output, verify all content is preserved
6. THE System SHALL log validation warnings when confidence scores are below 0.5 for more than 20% of extracted content

### Requirement 10: Comprehensive Logging and Observability

**User Story:** As a DevOps engineer, I want detailed logs and metrics for all extraction operations, so that I can troubleshoot issues and monitor system health.

#### Acceptance Criteria

1. THE GLM_OCR_Service SHALL log each extraction request with request_id, document_size, processing_time, and result status
2. THE Triton_Server SHALL log Stub_Process health checks with timestamp and GPU_Memory usage
3. THE Request_Queue SHALL emit metrics for queue length, average wait time, and throughput
4. THE System SHALL integrate with Jaeger for distributed tracing across all microservices
5. WHEN an error occurs, THE System SHALL log the full error context including stack trace, request parameters, and system state
6. THE System SHALL provide structured JSON logs that can be parsed by log aggregation tools

