# Design Document: GPU Extraction Production Ready

## Overview

This design addresses critical stability and feature gaps in the GPU-based document extraction system to make it production-ready. The system currently uses a microservice architecture with Triton Inference Server hosting the GLM-OCR model, a FastAPI-based GLM-OCR service, a Go-based API Gateway, and Temporal Workers for orchestration.

The key challenges being addressed are:

1. **Triton Stub Process Instability**: The Triton Python backend stub process becomes unhealthy when processing large documents (>5MB), causing request failures and requiring manual restarts.

2. **Missing Request Queue**: Concurrent requests directly hit the GPU without queueing, leading to GPU memory exhaustion and crashes.

3. **Limited Extraction Capabilities**: The system lacks word-level bounding boxes and key-value pair extraction with coordinates, which are essential for production use cases.

4. **Insufficient Observability**: Limited logging, metrics, and tracing make it difficult to diagnose issues and monitor system health.

5. **Poor Error Handling**: Errors are not gracefully handled, and there's no automatic retry mechanism for transient failures.

The solution involves:
- Configuring Triton with increased stub timeout (600s) and proper memory management
- Implementing a Redis-based request queue with priority handling and concurrency limits
- Enhancing the GLM-OCR service to support word-level and key-value extraction
- Adding comprehensive monitoring with Prometheus, Grafana, and Jaeger
- Implementing graceful error handling with exponential backoff retries
- Optimizing the Temporal Worker for parallel page processing

This design maintains backward compatibility while adding new capabilities through optional parameters.

## Architecture

### System Components


The architecture consists of the following components:

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ HTTP POST /jobs/upload
       ▼
┌─────────────────────────────────────────────────────────┐
│                    API Gateway (Go)                      │
│  - Request validation                                    │
│  - Job creation in PostgreSQL                            │
│  - Enqueue to Redis request queue                        │
│  - Start Temporal workflow                               │
└──────┬──────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│              Redis Request Queue                         │
│  - Priority queue (FIFO with priority levels)           │
│  - Job metadata storage                                  │
│  - Status tracking (queued, processing, completed)       │
│  - Concurrency control (max 1 GPU request)               │
└──────┬──────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│            Temporal Worker (Go)                          │
│  - Dequeue from Redis                                    │
│  - Parallel page processing (max 3 concurrent)           │
│  - Retry logic with exponential backoff                  │
│  - Result aggregation                                    │
└──────┬──────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│          GLM-OCR Service (FastAPI)                       │
│  - Word-level extraction                                 │
│  - Key-value pair extraction                             │
│  - Bounding box generation                               │
│  - GPU memory monitoring                                 │
└──────┬──────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│         Triton Inference Server                          │
│  - GLM-OCR model hosting                                 │
│  - Stub timeout: 600s                                    │
│  - GPU memory management                                 │
│  - Health monitoring                                     │
└─────────────────────────────────────────────────────────┘

Observability Stack:
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  Prometheus  │  │   Grafana    │  │    Jaeger    │
│   (Metrics)  │  │ (Dashboards) │  │   (Traces)   │
└──────────────┘  └──────────────┘  └──────────────┘
```

### Request Flow


1. **Client submits document** → API Gateway validates and creates job record
2. **API Gateway enqueues job** → Redis queue with priority and metadata
3. **API Gateway starts Temporal workflow** → Workflow polls queue for job
4. **Temporal Worker dequeues job** → Checks GPU availability via Redis lock
5. **Worker processes document** → Splits into pages, processes up to 3 pages in parallel
6. **Worker calls GLM-OCR service** → Service checks GPU memory before accepting
7. **GLM-OCR calls Triton** → Triton processes with 600s timeout
8. **Results aggregated** → Worker combines page results and stores in MinIO
9. **Job status updated** → PostgreSQL and Redis updated with completion status
10. **Client polls for results** → API Gateway returns result from MinIO

### Concurrency Control

The system implements multi-level concurrency control:

- **Redis Queue Level**: Only 1 job can hold the GPU lock at a time
- **Temporal Worker Level**: Up to 3 pages processed in parallel per job
- **GLM-OCR Service Level**: Checks available GPU memory before accepting requests
- **Triton Level**: Single model instance with 600s stub timeout

This ensures GPU memory is not exhausted while maximizing throughput for multi-page documents.

## Components and Interfaces

### 1. Triton Configuration Changes

**File**: `docker/docker-compose.yml` (triton service)

**Changes**:
```yaml
triton:
  command:
    - bash
    - -c
    - |
      export LD_LIBRARY_PATH=/usr/local/lib/python3.10/dist-packages/nvidia/cuda_runtime/lib:$LD_LIBRARY_PATH
      pip install --no-deps --force-reinstall safetensors==0.4.5 numpy==1.26.4 2>/dev/null
      exec tritonserver --model-repository=/models \
        --allow-gpu-metrics=true \
        --log-verbose=1 \
        --backend-config=python,shm-default-byte-size=8388608 \
        --backend-config=python,shm-growth-byte-size=8388608 \
        --backend-config=python,stub-timeout-seconds=600 \
        --backend-config=python,stub-health-check-interval-seconds=30
  shm_size: '4g'
  environment:
    - CUDA_LAUNCH_BLOCKING=1
    - PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512
```

**Key Parameters**:
- `stub-timeout-seconds=600`: Allows up to 10 minutes for large document processing
- `shm-default-byte-size=8388608`: 8MB shared memory (increased from 4MB)
- `stub-health-check-interval-seconds=30`: More frequent health checks
- `PYTORCH_CUDA_ALLOC_CONF`: Prevents memory fragmentation

### 2. Redis Request Queue

**New Component**: `services/api-gateway/queue/redis_queue.go`


**Interface**:
```go
type RequestQueue interface {
    // Enqueue adds a job to the queue with priority
    Enqueue(ctx context.Context, job *QueuedJob) error
    
    // Dequeue retrieves the next job from the queue
    Dequeue(ctx context.Context) (*QueuedJob, error)
    
    // UpdateStatus updates job status in the queue
    UpdateStatus(ctx context.Context, jobID string, status JobStatus) error
    
    // GetStatus retrieves current job status
    GetStatus(ctx context.Context, jobID string) (*JobStatus, error)
    
    // AcquireGPULock attempts to acquire exclusive GPU access
    AcquireGPULock(ctx context.Context, jobID string, ttl time.Duration) (bool, error)
    
    // ReleaseGPULock releases GPU lock
    ReleaseGPULock(ctx context.Context, jobID string) error
    
    // GetQueueLength returns current queue length
    GetQueueLength(ctx context.Context) (int64, error)
    
    // GetEstimatedWaitTime estimates wait time based on queue length
    GetEstimatedWaitTime(ctx context.Context) (time.Duration, error)
}

type QueuedJob struct {
    JobID        string
    Priority     int  // 0=normal, 1=high, 2=urgent
    EnqueuedAt   time.Time
    DocumentSize int64
    Options      map[string]interface{}
}

type JobStatus string

const (
    StatusQueued     JobStatus = "QUEUED"
    StatusProcessing JobStatus = "PROCESSING"
    StatusCompleted  JobStatus = "COMPLETED"
    StatusFailed     JobStatus = "FAILED"
)
```

**Redis Data Structures**:
- `queue:pending`: Sorted set (score = priority * 1000000 + timestamp)
- `queue:processing`: Hash map (jobID → processing metadata)
- `queue:status:{jobID}`: Hash (status, enqueued_at, started_at, etc.)
- `lock:gpu`: String key with TTL for GPU lock
- `metrics:queue_length`: Counter for monitoring

### 3. GLM-OCR Service Enhancements

**File**: `services/glm-ocr-service/app/models.py`

**New Models**:
```python
class WordBoundingBox(BaseModel):
    word: str
    bbox: List[int]  # [x, y, width, height]
    confidence: float

class KeyValuePair(BaseModel):
    key: str
    key_bbox: List[int]
    value: str
    value_bbox: List[int]
    confidence: float

class ExtractionOptions(BaseModel):
    granularity: str = "block"  # block, line, word
    include_coordinates: bool = True
    include_confidence: bool = True
    output_format: str = "text"  # text, json, markdown, table, key_value, structured
```

**File**: `services/glm-ocr-service/app/extractors.py` (new)


**Interface**:
```python
class WordLevelExtractor:
    """Extracts word-level bounding boxes from GLM-OCR output."""
    
    def extract_words(
        self, 
        content: str, 
        page_bbox: List[int],
        confidence: float
    ) -> List[WordBoundingBox]:
        """
        Extracts individual words with bounding boxes.
        Uses heuristics to approximate word positions based on content.
        """
        pass

class KeyValueExtractor:
    """Extracts key-value pairs with bounding boxes."""
    
    def extract_key_values(
        self,
        content: str,
        page_bbox: List[int]
    ) -> List[KeyValuePair]:
        """
        Identifies key-value patterns:
        - Colon-separated: "Invoice Number: 12345"
        - Table-based: Key in column 1, value in column 2
        - Form-field: Label above/beside input field
        """
        pass
```

### 4. API Gateway Queue Integration

**File**: `services/api-gateway/handlers/upload_handler.go` (modified)

**Changes**:
```go
func (h *UploadHandler) uploadDocument(c *gin.Context) {
    // ... existing validation ...
    
    // Enqueue job to Redis
    queuedJob := &queue.QueuedJob{
        JobID:        jobID,
        Priority:     determinePriority(c),
        EnqueuedAt:   time.Now(),
        DocumentSize: header.Size,
        Options:      extractOptions(c),
    }
    
    if err := h.Queue.Enqueue(c.Request.Context(), queuedJob); err != nil {
        return c.JSON(http.StatusServiceUnavailable, gin.H{
            "error": "Queue is full, please retry later",
            "retry_after": h.Queue.GetEstimatedWaitTime(c.Request.Context()),
        })
    }
    
    // Start Temporal workflow (will poll queue)
    // ... existing workflow start ...
}
```

**New Endpoint**: `GET /queue/status`
```go
func (h *UploadHandler) getQueueStatus(c *gin.Context) {
    length, _ := h.Queue.GetQueueLength(c.Request.Context())
    waitTime, _ := h.Queue.GetEstimatedWaitTime(c.Request.Context())
    
    c.JSON(http.StatusOK, gin.H{
        "queue_length": length,
        "estimated_wait_time_seconds": int(waitTime.Seconds()),
    })
}
```

### 5. Temporal Worker Modifications

**File**: `services/temporal-worker/workflows/document_processing.go` (modified)


**Changes**:
```go
func DocumentProcessingWorkflow(ctx workflow.Context, input map[string]interface{}) (map[string]interface{}, error) {
    // Wait for job to be dequeued from Redis
    jobID := input["job_id"].(string)
    
    // Poll queue until job is ready
    err := workflow.Await(ctx, func() bool {
        var status string
        err := workflow.ExecuteActivity(ctx, activities.CheckQueueStatus, jobID).Get(ctx, &status)
        return err == nil && status == "PROCESSING"
    })
    
    // Acquire GPU lock
    var lockAcquired bool
    err = workflow.ExecuteActivity(ctx, activities.AcquireGPULock, jobID).Get(ctx, &lockAcquired)
    if !lockAcquired {
        return nil, fmt.Errorf("failed to acquire GPU lock")
    }
    defer workflow.ExecuteActivity(ctx, activities.ReleaseGPULock, jobID)
    
    // Process pages in parallel (max 3 concurrent)
    pages := splitIntoPages(input)
    results := make([]PageResult, len(pages))
    
    // Use workflow.Go for parallel execution
    var wg sync.WaitGroup
    semaphore := make(chan struct{}, 3) // Max 3 concurrent
    
    for i, page := range pages {
        wg.Add(1)
        workflow.Go(ctx, func(ctx workflow.Context) {
            defer wg.Done()
            semaphore <- struct{}{}
            defer func() { <-semaphore }()
            
            var result PageResult
            err := workflow.ExecuteActivity(ctx, activities.ProcessPage, page).Get(ctx, &result)
            if err != nil {
                // Retry with exponential backoff
                retryPolicy := &temporal.RetryPolicy{
                    InitialInterval:    time.Second,
                    BackoffCoefficient: 2.0,
                    MaximumInterval:    time.Minute,
                    MaximumAttempts:    3,
                }
                // ... retry logic ...
            }
            results[i] = result
        })
    }
    
    wg.Wait()
    
    // Aggregate results
    finalResult := aggregateResults(results)
    return finalResult, nil
}
```

### 6. GPU Memory Monitoring

**File**: `services/glm-ocr-service/app/gpu_monitor.py` (new)

**Interface**:
```python
class GPUMonitor:
    """Monitors GPU memory usage and availability."""
    
    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    def get_memory_stats(self) -> Dict[str, float]:
        """Returns current GPU memory statistics."""
        if not torch.cuda.is_available():
            return {}
        
        return {
            "allocated_gb": torch.cuda.memory_allocated() / 1e9,
            "reserved_gb": torch.cuda.memory_reserved() / 1e9,
            "max_allocated_gb": torch.cuda.max_memory_allocated() / 1e9,
            "total_gb": torch.cuda.get_device_properties(0).total_memory / 1e9,
            "free_gb": (torch.cuda.get_device_properties(0).total_memory - 
                       torch.cuda.memory_allocated()) / 1e9,
        }
    
    def has_sufficient_memory(self, required_gb: float = 2.0) -> bool:
        """Checks if sufficient GPU memory is available."""
        stats = self.get_memory_stats()
        return stats.get("free_gb", 0) >= required_gb
    
    def clear_cache(self):
        """Clears GPU cache to free memory."""
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
```

## Data Models

### Queue Job Model


```go
type QueuedJob struct {
    JobID          string                 `json:"job_id"`
    Priority       int                    `json:"priority"`
    EnqueuedAt     time.Time              `json:"enqueued_at"`
    StartedAt      *time.Time             `json:"started_at,omitempty"`
    CompletedAt    *time.Time             `json:"completed_at,omitempty"`
    DocumentSize   int64                  `json:"document_size"`
    Status         JobStatus              `json:"status"`
    Options        map[string]interface{} `json:"options"`
    RetryCount     int                    `json:"retry_count"`
    ErrorMessage   string                 `json:"error_message,omitempty"`
}
```

### Extraction Result Model

```python
class ExtractionResult(BaseModel):
    content: str
    confidence: float
    processing_time_ms: int
    granularity: str
    bounding_boxes: Optional[List[BoundingBox]] = None
    word_boxes: Optional[List[WordBoundingBox]] = None
    key_value_pairs: Optional[List[KeyValuePair]] = None
    gpu_memory_used_gb: Optional[float] = None
    tokens_used: TokenUsage

class BoundingBox(BaseModel):
    x: int
    y: int
    width: int
    height: int
    confidence: float
    text: Optional[str] = None
```

### Monitoring Metrics Model

```go
type GPUMetrics struct {
    AllocatedGB    float64   `json:"allocated_gb"`
    ReservedGB     float64   `json:"reserved_gb"`
    FreeGB         float64   `json:"free_gb"`
    TotalGB        float64   `json:"total_gb"`
    Utilization    float64   `json:"utilization_percent"`
    Temperature    float64   `json:"temperature_celsius"`
    Timestamp      time.Time `json:"timestamp"`
}

type QueueMetrics struct {
    QueueLength        int64         `json:"queue_length"`
    ProcessingCount    int64         `json:"processing_count"`
    AvgWaitTimeSeconds float64       `json:"avg_wait_time_seconds"`
    AvgProcessingTime  float64       `json:"avg_processing_time_seconds"`
    ThroughputPerHour  float64       `json:"throughput_per_hour"`
    Timestamp          time.Time     `json:"timestamp"`
}
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

Before defining properties, let me analyze the acceptance criteria for testability:


### Property Reflection

After analyzing all acceptance criteria, I identified the following redundancies:

1. **Bounding Box Structure Properties**: Criteria 3.2 (bbox has x,y,width,height) and 3.4 (bbox has confidence) can be combined into a single property that validates complete bbox structure.

2. **Confidence Score Validation**: Criteria 9.3 (confidence 0.0-1.0) is validated by multiple other properties that check confidence scores, so it can be a general validation property.

3. **Logging Properties**: Criteria 10.1, 10.2, 10.5 all test logging completeness and can be combined into a general logging completeness property.

4. **Queue Behavior**: Criteria 2.1 (sequential processing) and 2.6 (limit to 1 concurrent) are testing the same concurrency control and can be combined.

5. **Format Support**: Criteria 5.1 and 5.2 are examples testing specific format/granularity support, not properties.

After reflection, I've consolidated 60 criteria into 35 unique properties and 15 examples/edge cases.

### Property 1: Document Size Handling

*For any* PDF document up to 10MB, processing the document should complete without the Triton stub process becoming unhealthy.

**Validates: Requirements 1.1**

### Property 2: GPU Memory Recovery

*For any* inference request that encounters GPU memory limitations, the system should retry with reduced batch size and eventually succeed or fail gracefully.

**Validates: Requirements 1.2**

### Property 3: Model Persistence

*For any* sequence of extraction requests, the GLM-OCR model should remain loaded in GPU memory between requests without reloading.

**Validates: Requirements 1.6**

### Property 4: Queue Sequential Processing

*For any* set of concurrent extraction requests, the request queue should accept all requests and ensure only 1 GPU inference executes at a time.

**Validates: Requirements 2.1, 2.6**

### Property 5: Queue Position Assignment

*For any* request enqueued, the system should assign it a queue position and estimated wait time based on current queue length.

**Validates: Requirements 2.2**

### Property 6: Queue Status Polling

*For any* queued job, the polling endpoint should return current queue position and status that matches the actual queue state.

**Validates: Requirements 2.4**

### Property 7: Queue Cancellation

*For any* queued request that is cancelled, the system should remove it from the queue and immediately process the next pending request.

**Validates: Requirements 2.7**

### Property 8: Word-Level Bounding Boxes

*For any* document extracted with granularity "word", each extracted word should have a bounding box with x, y, width, height, and confidence score.

**Validates: Requirements 3.1, 3.2, 3.4**

### Property 9: Word-Level JSON Structure

*For any* extraction with format "json" and granularity "word", the output should be an array of objects each containing text, bbox, and confidence fields.

**Validates: Requirements 3.5**

### Property 10: Word Order Preservation

*For any* document extraction, words should appear in the output in the same reading sequence as they appear on the page.

**Validates: Requirements 3.6**

### Property 11: Key-Value Detection

*For any* document extracted with format "key_value", all key-value pair structures should be identified and extracted.

**Validates: Requirements 4.1**

### Property 12: Key-Value Bounding Boxes

*For any* extracted key-value pair, both the key and value should have separate bounding box coordinates.

**Validates: Requirements 4.2**

### Property 13: Multi-Value Key Grouping

*For any* key with multiple associated values, all values should be grouped under the same key with individual bounding boxes.

**Validates: Requirements 4.3**

### Property 14: Key-Value Pattern Recognition

*For any* document containing colon-separated, table-based, or form-field key-value patterns, the system should recognize and extract them correctly.

**Validates: Requirements 4.4**

### Property 15: Multi-Line Key-Value Bounding Box

*For any* key-value pair spanning multiple lines, the bounding box should encompass all lines of both key and value.

**Validates: Requirements 4.5**

### Property 16: Key-Value Confidence Scores

*For any* extracted key-value pair, the system should include confidence scores for key detection, value detection, and key-value association.

**Validates: Requirements 4.6**

### Property 17: Conditional Coordinates Inclusion

*For any* extraction request with coordinates option enabled, the response should include bounding box data at the specified granularity level.

**Validates: Requirements 5.3**

### Property 18: Conditional Confidence Inclusion

*For any* extraction request with confidence option enabled, the response should include confidence scores for each extracted element.

**Validates: Requirements 5.4**

### Property 19: Table Structure Preservation

*For any* table extracted with format "table", the output should preserve row and column structure with cell-level bounding boxes.

**Validates: Requirements 5.6**

### Property 20: Structured Format Hierarchy

*For any* extraction with format "structured", the output should contain hierarchical document structure with section-level bounding boxes.

**Validates: Requirements 5.7**

### Property 21: GPU Memory Logging

*For any* inference request, the system should log GPU memory usage before and after the request.

**Validates: Requirements 6.2**

### Property 22: GPU Memory Pre-Flight Check

*For any* batch request, the GLM-OCR service should query available GPU memory before accepting the request.

**Validates: Requirements 6.4**

### Property 23: Exponential Backoff Retry

*For any* failed extraction request, the system should retry with exponential backoff up to a maximum of 3 attempts.

**Validates: Requirements 7.4**

### Property 24: Failure Detail Storage

*For any* extraction request that fails after all retries, the system should store complete failure details including error message, stack trace, and request parameters.

**Validates: Requirements 7.5**

### Property 25: Parallel Page Processing

*For any* PDF with more than 10 pages, the Temporal worker should process pages in parallel with a maximum of 3 concurrent page extractions.

**Validates: Requirements 8.1**

### Property 26: Preprocessing Cache

*For any* extraction request that is retried, the system should use cached preprocessed images instead of reprocessing.

**Validates: Requirements 8.2**

### Property 27: Document Chunking

*For any* document larger than 5MB, the Temporal worker should split it into chunks and process each chunk separately.

**Validates: Requirements 8.3**

### Property 28: Average Processing Time

*For any* set of documents under 1MB, the average processing time per page should be below 10 seconds.

**Validates: Requirements 8.6**

### Property 29: Bounding Box Boundary Validation

*For any* extracted bounding box, the coordinates should be within the page boundaries (0 ≤ x, y ≤ page dimensions).

**Validates: Requirements 9.1**

### Property 30: Word Box Non-Overlap

*For any* word-level extraction, word bounding boxes should not overlap incorrectly (allowing only valid overlaps like ligatures).

**Validates: Requirements 9.2**

### Property 31: Confidence Score Range

*For any* confidence score in the system, the value should be between 0.0 and 1.0 inclusive.

**Validates: Requirements 9.3**

### Property 32: Key-Value Structural Integrity

*For any* key-value extraction result, each value should have an associated key (no orphaned values).

**Validates: Requirements 9.4**

### Property 33: Structured Format Round-Trip

*For any* document, extracting with structured format and then reconstructing should preserve all content.

**Validates: Requirements 9.5**

### Property 34: Extraction Request Logging

*For any* extraction request, the logs should contain request_id, document_size, processing_time, and result status.

**Validates: Requirements 10.1, 10.5**

### Property 35: Health Check Logging

*For any* Triton stub process health check, the logs should contain timestamp and GPU memory usage.

**Validates: Requirements 10.2**

### Property 36: Queue Metrics Emission

*For any* time interval, the request queue should emit metrics for queue length, average wait time, and throughput.

**Validates: Requirements 10.3**

### Property 37: Structured JSON Logs

*For any* log entry, the log should be valid JSON that can be parsed by log aggregation tools.

**Validates: Requirements 10.6**

## Error Handling

The system implements comprehensive error handling at multiple levels to ensure graceful degradation and clear error communication.

### Error Categories

**1. GPU Memory Errors**
- **Cause**: Insufficient VRAM for model inference or batch processing
- **Detection**: PyTorch CUDA out-of-memory exceptions, GPU monitor pre-flight checks
- **Handling**: 
  - GLM-OCR service checks available memory before accepting requests
  - If memory < 2GB, return HTTP 503 with `Retry-After` header
  - If OOM during inference, Triton reduces batch size and retries
  - Log GPU memory stats with error for debugging
- **Client Response**: `{"error": "Insufficient GPU memory", "retry_after_seconds": 60, "available_memory_gb": 1.5}`

**2. Triton Stub Process Crashes**
- **Cause**: Segmentation faults, Python exceptions in model code, timeout exceeded
- **Detection**: Triton health check failures, stub process exit
- **Handling**:
  - Triton automatically restarts stub process
  - In-flight requests receive HTTP 503
  - Log restart event with GPU memory usage and document size
  - Queue holds pending requests until stub is healthy
- **Client Response**: `{"error": "Service temporarily unavailable", "retry_after_seconds": 30, "reason": "model_restart"}`

**3. Queue Full Errors**
- **Cause**: Too many concurrent requests exceeding queue capacity
- **Detection**: Redis queue length check before enqueue
- **Handling**:
  - API Gateway returns HTTP 429 before accepting request
  - Include estimated wait time based on current queue length
  - Client can retry after wait time
- **Client Response**: `{"error": "Queue is full", "retry_after_seconds": 120, "queue_length": 50}`

**4. Document Size Errors**
- **Cause**: Document exceeds maximum supported size (10MB)
- **Detection**: File size check in API Gateway
- **Handling**:
  - Reject request before enqueuing
  - Return HTTP 413 with maximum size limit
  - Log rejected request with document size
- **Client Response**: `{"error": "Document too large", "max_size_mb": 10, "provided_size_mb": 15.3}`

**5. Timeout Errors**
- **Cause**: Processing exceeds maximum allowed time
- **Detection**: Temporal workflow timeout, activity timeout
- **Handling**:
  - Temporal implements timeout at workflow (30 min) and activity (10 min) levels
  - On timeout, mark job as failed and release GPU lock
  - Store partial results if any pages completed
  - Log timeout with processing time and document metadata
- **Client Response**: `{"error": "Processing timeout", "timeout_seconds": 1800, "pages_completed": 5, "total_pages": 20}`

**6. Extraction Validation Errors**
- **Cause**: Invalid bounding boxes, malformed output, confidence scores out of range
- **Detection**: Post-processing validation in GLM-OCR service
- **Handling**:
  - Validate all bounding boxes are within page boundaries
  - Validate confidence scores are 0.0-1.0
  - Log validation warnings but return results
  - Include validation warnings in response metadata
- **Client Response**: `{"content": "...", "warnings": ["3 bounding boxes outside page boundaries", "12% of confidence scores below 0.5"]}`

### Retry Strategy

The system implements exponential backoff with jitter for automatic retries:

```go
type RetryPolicy struct {
    InitialInterval    time.Duration  // 1 second
    BackoffCoefficient float64        // 2.0
    MaximumInterval    time.Duration  // 60 seconds
    MaximumAttempts    int            // 3
    Jitter             float64        // 0.1 (10%)
}

func calculateBackoff(attempt int, policy RetryPolicy) time.Duration {
    interval := policy.InitialInterval * time.Duration(math.Pow(policy.BackoffCoefficient, float64(attempt)))
    if interval > policy.MaximumInterval {
        interval = policy.MaximumInterval
    }
    jitter := time.Duration(rand.Float64() * policy.Jitter * float64(interval))
    return interval + jitter
}
```

**Retryable Errors**:
- GPU memory errors (503)
- Triton stub process restarts (503)
- Temporary network failures
- Transient model inference errors

**Non-Retryable Errors**:
- Document too large (413)
- Invalid request format (400)
- Authentication failures (401)
- Unsupported extraction format (400)

### Error Logging

All errors are logged with structured context:

```json
{
  "timestamp": "2024-01-15T10:30:45Z",
  "level": "ERROR",
  "service": "glm-ocr-service",
  "request_id": "req_abc123",
  "error_type": "GPU_MEMORY_ERROR",
  "error_message": "CUDA out of memory",
  "stack_trace": "...",
  "context": {
    "document_size_mb": 8.5,
    "gpu_memory_allocated_gb": 3.2,
    "gpu_memory_free_gb": 0.3,
    "batch_size": 4,
    "retry_attempt": 1
  }
}
```

### Health Check Endpoint

The API Gateway provides a comprehensive health check endpoint:

**Endpoint**: `GET /health`

**Response**:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:45Z",
  "components": {
    "triton": {
      "status": "healthy",
      "gpu_memory_free_gb": 2.1,
      "model_loaded": true,
      "last_health_check": "2024-01-15T10:30:40Z"
    },
    "glm_ocr_service": {
      "status": "healthy",
      "response_time_ms": 45
    },
    "request_queue": {
      "status": "healthy",
      "queue_length": 3,
      "processing_count": 1,
      "estimated_wait_time_seconds": 45
    },
    "database": {
      "status": "healthy",
      "connection_pool_available": 18
    },
    "redis": {
      "status": "healthy",
      "memory_used_mb": 256
    }
  }
}
```

## Testing Strategy

The testing strategy employs a dual approach combining unit tests for specific scenarios and property-based tests for comprehensive coverage.

### Unit Testing

Unit tests focus on specific examples, edge cases, and integration points:

**API Gateway Tests** (`services/api-gateway/handlers/upload_handler_test.go`):
- Document upload validation (size limits, format validation)
- Queue integration (enqueue success, queue full handling)
- Health check endpoint responses
- Error response formatting

**Redis Queue Tests** (`services/api-gateway/queue/redis_queue_test.go`):
- Enqueue and dequeue operations
- Priority ordering
- GPU lock acquisition and release
- Queue status updates
- Cancellation handling

**GLM-OCR Service Tests** (`services/glm-ocr-service/tests/test_extractors.py`):
- Word-level extraction with hyphenated words (edge case)
- Key-value pattern recognition (colon-separated, table-based, form-field)
- Bounding box validation (within boundaries, no invalid overlaps)
- Confidence score inclusion
- JSON output structure

**Temporal Worker Tests** (`services/temporal-worker/workflows/document_processing_test.go`):
- Parallel page processing (3 concurrent pages)
- Document chunking for large files
- Retry logic with exponential backoff
- GPU lock management
- Result aggregation

**Triton Configuration Tests** (`docker/triton_test.sh`):
- Stub timeout configuration (600s)
- Shared memory configuration (8MB)
- GPU metrics exposure
- Model persistence between requests

### Property-Based Testing

Property-based tests validate universal properties across randomly generated inputs. Each test runs a minimum of 100 iterations.

**Testing Framework**: 
- Go: `gopter` library
- Python: `hypothesis` library

**Property Test Configuration**:
```go
// Example configuration
parameters := gopter.DefaultTestParameters()
parameters.MinSuccessfulTests = 100
parameters.MaxSize = 1000
```

**Property Tests**:

1. **Document Size Handling** (`test_triton_stability.py`)
   - Generate random PDFs from 1KB to 10MB
   - Verify processing completes without stub becoming unhealthy
   - **Tag**: Feature: gpu-extraction-production-ready, Property 1: For any PDF document up to 10MB, processing should complete without stub process becoming unhealthy

2. **Model Persistence** (`test_triton_stability.py`)
   - Generate sequence of random extraction requests
   - Verify model remains loaded in GPU memory (no reload logs)
   - **Tag**: Feature: gpu-extraction-production-ready, Property 3: For any sequence of extraction requests, GLM-OCR model should remain loaded in GPU memory

3. **Queue Sequential Processing** (`test_queue_concurrency.go`)
   - Generate random number of concurrent requests (5-20)
   - Verify only 1 GPU inference executes at a time
   - Verify all requests are accepted and processed
   - **Tag**: Feature: gpu-extraction-production-ready, Property 4: For any set of concurrent requests, queue should accept all and ensure only 1 GPU inference at a time

4. **Queue Position Assignment** (`test_queue_operations.go`)
   - Generate random requests with varying priorities
   - Verify each gets queue position and estimated wait time
   - **Tag**: Feature: gpu-extraction-production-ready, Property 5: For any enqueued request, system should assign queue position and estimated wait time

5. **Queue Cancellation** (`test_queue_operations.go`)
   - Generate random queue state with multiple pending requests
   - Cancel random request and verify removal and next request processing
   - **Tag**: Feature: gpu-extraction-production-ready, Property 7: For any queued request that is cancelled, system should remove it and process next request

6. **Word-Level Bounding Boxes** (`test_word_extraction.py`)
   - Generate random documents with varying text content
   - Request granularity "word"
   - Verify each word has bbox with x, y, width, height, confidence
   - **Tag**: Feature: gpu-extraction-production-ready, Property 8: For any document with granularity "word", each word should have complete bounding box

7. **Word Order Preservation** (`test_word_extraction.py`)
   - Generate random documents with known reading order
   - Verify extracted words match reading sequence
   - **Tag**: Feature: gpu-extraction-production-ready, Property 10: For any document extraction, words should appear in reading sequence

8. **Key-Value Detection** (`test_key_value_extraction.py`)
   - Generate random documents with key-value pairs
   - Request format "key_value"
   - Verify all key-value structures are identified
   - **Tag**: Feature: gpu-extraction-production-ready, Property 11: For any document with format "key_value", all key-value structures should be identified

9. **Key-Value Bounding Boxes** (`test_key_value_extraction.py`)
   - Generate random key-value pairs
   - Verify separate bboxes for key and value portions
   - **Tag**: Feature: gpu-extraction-production-ready, Property 12: For any extracted key-value pair, both key and value should have separate bboxes

10. **Multi-Value Key Grouping** (`test_key_value_extraction.py`)
    - Generate documents with keys having multiple values
    - Verify values are grouped under same key with individual bboxes
    - **Tag**: Feature: gpu-extraction-production-ready, Property 13: For any key with multiple values, all should be grouped with individual bboxes

11. **Key-Value Pattern Recognition** (`test_key_value_extraction.py`)
    - Generate documents with colon-separated, table-based, and form-field patterns
    - Verify all patterns are recognized correctly
    - **Tag**: Feature: gpu-extraction-production-ready, Property 14: For any document with key-value patterns, system should recognize all pattern types

12. **Conditional Coordinates Inclusion** (`test_extraction_options.py`)
    - Generate random extraction requests with coordinates option enabled/disabled
    - Verify bboxes included only when enabled
    - **Tag**: Feature: gpu-extraction-production-ready, Property 17: For any request with coordinates enabled, response should include bounding boxes

13. **Conditional Confidence Inclusion** (`test_extraction_options.py`)
    - Generate random extraction requests with confidence option enabled/disabled
    - Verify confidence scores included only when enabled
    - **Tag**: Feature: gpu-extraction-production-ready, Property 18: For any request with confidence enabled, response should include confidence scores

14. **Table Structure Preservation** (`test_table_extraction.py`)
    - Generate random tables with varying rows/columns
    - Request format "table"
    - Verify row/column structure preserved with cell-level bboxes
    - **Tag**: Feature: gpu-extraction-production-ready, Property 19: For any table extraction, output should preserve structure with cell-level bboxes

15. **Structured Format Hierarchy** (`test_structured_extraction.py`)
    - Generate random documents with hierarchical structure
    - Request format "structured"
    - Verify hierarchical structure with section-level bboxes
    - **Tag**: Feature: gpu-extraction-production-ready, Property 20: For any structured format request, output should contain hierarchy with section bboxes

16. **GPU Memory Logging** (`test_gpu_monitoring.py`)
    - Generate random inference requests
    - Verify logs contain GPU memory before and after each request
    - **Tag**: Feature: gpu-extraction-production-ready, Property 21: For any inference request, system should log GPU memory usage

17. **GPU Memory Pre-Flight Check** (`test_gpu_monitoring.py`)
    - Generate random batch requests
    - Verify GPU memory is queried before acceptance
    - **Tag**: Feature: gpu-extraction-production-ready, Property 22: For any batch request, service should query available GPU memory before accepting

18. **Exponential Backoff Retry** (`test_retry_logic.go`)
    - Generate random failures
    - Verify exponential backoff with max 3 attempts
    - **Tag**: Feature: gpu-extraction-production-ready, Property 23: For any failed request, system should retry with exponential backoff up to 3 attempts

19. **Failure Detail Storage** (`test_error_handling.go`)
    - Generate requests that fail after all retries
    - Verify complete failure details are stored
    - **Tag**: Feature: gpu-extraction-production-ready, Property 24: For any request failing after retries, system should store complete failure details

20. **Parallel Page Processing** (`test_parallel_processing.go`)
    - Generate random PDFs with 10-50 pages
    - Verify max 3 pages processed concurrently
    - **Tag**: Feature: gpu-extraction-production-ready, Property 25: For any PDF with >10 pages, worker should process max 3 pages in parallel

21. **Preprocessing Cache** (`test_caching.go`)
    - Generate random requests that are retried
    - Verify cached preprocessed images are used (no reprocessing)
    - **Tag**: Feature: gpu-extraction-production-ready, Property 26: For any retried request, system should use cached preprocessed images

22. **Document Chunking** (`test_chunking.go`)
    - Generate random documents from 5MB to 15MB
    - Verify documents >5MB are split into chunks
    - **Tag**: Feature: gpu-extraction-production-ready, Property 27: For any document >5MB, worker should split into chunks

23. **Average Processing Time** (`test_performance.py`)
    - Generate random documents under 1MB
    - Verify average processing time per page < 10 seconds
    - **Tag**: Feature: gpu-extraction-production-ready, Property 28: For any documents under 1MB, average processing time should be <10s per page

24. **Bounding Box Boundary Validation** (`test_bbox_validation.py`)
    - Generate random extraction results
    - Verify all bbox coordinates within page boundaries
    - **Tag**: Feature: gpu-extraction-production-ready, Property 29: For any extracted bbox, coordinates should be within page boundaries

25. **Word Box Non-Overlap** (`test_word_extraction.py`)
    - Generate random word-level extractions
    - Verify word bboxes don't overlap incorrectly
    - **Tag**: Feature: gpu-extraction-production-ready, Property 30: For any word-level extraction, word bboxes should not overlap incorrectly

26. **Confidence Score Range** (`test_validation.py`)
    - Generate random extraction results
    - Verify all confidence scores are 0.0-1.0
    - **Tag**: Feature: gpu-extraction-production-ready, Property 31: For any confidence score, value should be between 0.0 and 1.0

27. **Key-Value Structural Integrity** (`test_key_value_extraction.py`)
    - Generate random key-value extraction results
    - Verify each value has an associated key (no orphans)
    - **Tag**: Feature: gpu-extraction-production-ready, Property 32: For any key-value result, each value should have an associated key

28. **Structured Format Round-Trip** (`test_structured_extraction.py`)
    - Generate random documents
    - Extract with structured format, reconstruct, verify content preserved
    - **Tag**: Feature: gpu-extraction-production-ready, Property 33: For any document, structured format extraction and reconstruction should preserve all content

29. **Extraction Request Logging** (`test_logging.py`)
    - Generate random extraction requests
    - Verify logs contain request_id, document_size, processing_time, status
    - **Tag**: Feature: gpu-extraction-production-ready, Property 34: For any extraction request, logs should contain complete request metadata

30. **Health Check Logging** (`test_triton_monitoring.py`)
    - Generate random health check events
    - Verify logs contain timestamp and GPU memory usage
    - **Tag**: Feature: gpu-extraction-production-ready, Property 35: For any health check, logs should contain timestamp and GPU memory

31. **Queue Metrics Emission** (`test_queue_metrics.go`)
    - Generate random time intervals
    - Verify queue emits metrics for length, wait time, throughput
    - **Tag**: Feature: gpu-extraction-production-ready, Property 36: For any time interval, queue should emit complete metrics

32. **Structured JSON Logs** (`test_logging.py`)
    - Generate random log entries across all services
    - Verify all logs are valid JSON
    - **Tag**: Feature: gpu-extraction-production-ready, Property 37: For any log entry, log should be valid JSON

### Integration Testing

Integration tests validate end-to-end workflows:

**Test Scenarios**:
1. **Complete Extraction Flow**: Upload document → Queue → Process → Retrieve results
2. **Concurrent Request Handling**: Submit 10 concurrent requests, verify all complete successfully
3. **Large Document Processing**: Submit 20-page PDF, verify parallel processing and result aggregation
4. **Error Recovery**: Trigger GPU memory error, verify retry and eventual success
5. **Queue Full Scenario**: Fill queue to capacity, verify 429 responses and proper recovery
6. **Triton Restart Recovery**: Restart Triton during processing, verify automatic recovery

### Performance Testing

Performance tests validate system meets latency and throughput requirements:

**Metrics**:
- Average processing time per page (target: <10s for documents <1MB)
- Queue throughput (target: >100 documents/hour)
- GPU memory utilization (target: 70-90% during processing)
- API response time (target: <100ms for non-processing endpoints)

**Load Testing**:
- Sustained load: 50 concurrent users for 1 hour
- Spike test: 0 to 100 users in 1 minute
- Stress test: Gradually increase load until system degrades

### Test Coverage Goals

- Unit test coverage: >80% for all services
- Property test coverage: All 37 properties implemented
- Integration test coverage: All critical user flows
- Performance test coverage: All performance requirements validated

### Continuous Integration

All tests run automatically on:
- Pull request creation
- Merge to main branch
- Nightly builds (includes long-running property tests with 1000 iterations)

**CI Pipeline**:
1. Lint and format checks
2. Unit tests (parallel execution)
3. Property tests (100 iterations)
4. Integration tests (sequential)
5. Performance tests (on dedicated hardware)
6. Coverage report generation
