# Large Document Processing Performance Analysis

## Problem Statement

The 20-page PDF test takes **7+ minutes** to complete, even though:
- GPU has 96% free memory (3.9GB available)
- System is configured for parallel processing (max 3 concurrent pages)
- Single-page documents complete in < 1 second

## Performance Breakdown

### Actual Timing (from logs)
```
Start: 16:53:51
Preprocessing: 16:53:51 → 16:54:12 (21 seconds)
AI Extraction: 16:54:12 → 17:01:17 (7 minutes 5 seconds = 425 seconds)
Post-processing: 17:01:17 → 17:01:17 (< 1 second)
Total: ~7.5 minutes
```

### Per-Page Performance
- **20 pages in 425 seconds = 21.25 seconds per page**
- **Expected with 3x parallelization**: ~7 seconds per page (3 pages at once)
- **Actual speedup**: 1x (sequential processing)

## Root Cause Analysis

### Evidence of Sequential Processing

From Triton logs, requests are processed one at a time:
```
17:00:56 - Request starts
17:01:17 - Request completes (21 seconds)
[Next request starts after previous completes]
```

### Why Parallel Processing Isn't Working

1. **Workflow Code Has Parallel Logic** ✅
   - `processPagesConcurrently()` function exists
   - `maxConcurrent := 3` is set
   - Uses `workflow.Go` for concurrent execution

2. **But Triton Receives Sequential Requests** ❌
   - Triton logs show only 1 request at a time
   - No concurrent inference requests observed
   - Each page waits for previous to complete

### Possible Causes

#### 1. Activity Execution Limitation
The Temporal worker may be configured to execute activities sequentially:
```go
// In worker configuration
MaxConcurrentActivityExecutionSize: 1  // ← This would cause sequential execution
```

#### 2. GPU Lock Preventing Parallelism
The Redis GPU lock (Requirement 2.6) may be preventing concurrent page processing:
```go
// If GPU lock is acquired per-page instead of per-job
AcquireGPULock()  // Blocks other pages
ProcessPage()
ReleaseGPULock()
```

#### 3. Triton Model Configuration
Triton may be configured to process only 1 request at a time:
```
# In model config
instance_group [
  {
    count: 1  # Only 1 model instance
    kind: KIND_GPU
  }
]
```

#### 4. GLM-OCR Service Bottleneck
The GLM-OCR service may have a global lock or single-threaded request handling.

## GPU Utilization

### Current State
- **Total Memory**: 4096 MiB
- **Used**: 155 MiB (3.8%)
- **Free**: 3941 MiB (96.2%)

### Observation
GPU is severely **underutilized**. With 96% free memory, it could easily handle 3 concurrent page processing requests.

## Performance Impact

### Current Performance
- **20 pages**: 7.5 minutes
- **100 pages**: ~37 minutes
- **1000 pages**: ~6 hours

### Expected with 3x Parallelization
- **20 pages**: 2.5 minutes (3x faster)
- **100 pages**: 12 minutes (3x faster)
- **1000 pages**: 2 hours (3x faster)

### Potential with Full GPU Utilization
With 4GB GPU and ~150MB per page, could theoretically process:
- **~25 pages concurrently** (4000MB / 150MB)
- **20 pages**: < 30 seconds
- **100 pages**: < 2 minutes
- **1000 pages**: < 20 minutes

## Recommendations

### Immediate Actions (High Priority)

1. **Check Temporal Worker Configuration**
   ```go
   // In services/temporal-worker/main.go
   workerOptions := worker.Options{
       MaxConcurrentActivityExecutionSize: 10,  // Allow concurrent activities
       MaxConcurrentWorkflowTaskExecutionSize: 10,
   }
   ```

2. **Verify GPU Lock Scope**
   - GPU lock should be per-job, not per-page
   - Pages within same job should process concurrently
   - Only different jobs should wait for GPU lock

3. **Check Triton Model Instances**
   ```
   # In triton model config
   instance_group [
     {
       count: 3  # Allow 3 concurrent instances
       kind: KIND_GPU
     }
   ]
   ```

4. **Add Logging to Verify Parallelism**
   ```go
   logger.Info("Starting page processing", 
       "page", pageNum, 
       "concurrent_pages", activePagesCount)
   ```

### Medium Priority

5. **Optimize Page Processing**
   - Reduce per-page overhead
   - Implement page batching (process multiple pages in single Triton call)
   - Cache preprocessing results

6. **Add Performance Monitoring**
   - Track concurrent page processing count
   - Monitor GPU utilization during processing
   - Log page processing start/end times

7. **Implement Adaptive Concurrency**
   - Start with 3 concurrent pages
   - Increase if GPU memory allows
   - Decrease if GPU memory pressure detected

### Low Priority

8. **Consider Alternative Architectures**
   - Batch processing: Send multiple pages to Triton in single request
   - Pipeline processing: Overlap preprocessing, inference, and postprocessing
   - Multi-GPU support: Distribute pages across multiple GPUs

## Testing Recommendations

### Verify Parallel Processing

1. **Add Debug Logging**
   ```go
   logger.Info("🔄 Processing pages concurrently", 
       "total_pages", pageCount,
       "max_concurrent", maxConcurrent,
       "batch_size", batchSize)
   ```

2. **Monitor Triton Requests**
   ```bash
   # Should see 3 concurrent requests
   docker logs docker-triton-1 -f | grep "executing"
   ```

3. **Check GPU Utilization**
   ```bash
   # Should see higher GPU utilization
   nvidia-smi -l 1
   ```

### Performance Benchmarks

Create tests for:
- 5 pages (should complete in ~35 seconds with 3x parallelism)
- 10 pages (should complete in ~70 seconds)
- 20 pages (should complete in ~140 seconds = 2.3 minutes)

## Expected vs Actual

| Pages | Sequential | 3x Parallel | Actual | Status |
|-------|-----------|-------------|--------|--------|
| 1     | 21s       | 21s         | <1s    | ✅ Fast |
| 5     | 105s      | 35s         | ?      | ❓ Unknown |
| 10    | 210s      | 70s         | ?      | ❓ Unknown |
| 20    | 420s      | 140s        | 425s   | ❌ Sequential |

## Conclusion

The large document processing is slow because **pages are being processed sequentially instead of in parallel**, despite having:
- Parallel processing code in the workflow
- Abundant GPU memory (96% free)
- Configuration for 3 concurrent pages

The root cause is likely one of:
1. Temporal worker limiting concurrent activity execution
2. GPU lock preventing page-level parallelism
3. Triton configured for single instance
4. GLM-OCR service bottleneck

**Immediate fix**: Check and update Temporal worker configuration to allow concurrent activity execution.

**Expected improvement**: 3x faster processing (7.5 minutes → 2.5 minutes for 20 pages)

**Potential improvement**: Up to 25x faster with full GPU utilization optimization
