# GPU Extraction Test Report
**Date:** March 4, 2026  
**Test Duration:** ~35 minutes  
**Status:** ⚠️ ISSUES FOUND

## Test Summary

Tested GPU extraction with real-time service log monitoring using two documents:
1. ✅ Simple test invoice (PNG, 7.6 KB) - **PASSED**
2. ❌ Real PDF invoice (PDF, 150 KB) - **FAILED**

## Test Results

### Test 1: Simple Invoice (test_invoice_local.png)
- **Status:** ✅ SUCCESS
- **Processing Time:** 7.73 seconds
- **Model:** zai-org/GLM-OCR
- **Confidence:** 92%
- **Extracted Data:** Invoice #INV-2026-0042, Date: March 3, 2026, Amount: $1,234.56
- **Issues:** None

### Test 2: Real PDF Invoice (Prompt Consultancy Invoice no.PC_120_24-25.pdf)
- **Status:** ❌ FAILURE
- **File Size:** 150.52 KB (PDF)
- **Error:** Triton stub process crash
- **Processing Time:** >3 minutes (still processing after crash recovery)

## Critical Bugs Found

### Bug #1: Triton Stub Process Crashes on Larger PDFs

**Severity:** 🔴 CRITICAL

**Description:**  
The Triton Python backend stub process becomes unhealthy and crashes when processing larger or more complex PDF documents. This causes:
1. Initial inference request fails with HTTP 500 error
2. Stub process automatically restarts
3. Model must be reloaded from scratch (~50 seconds)
4. Request is retried but may timeout
5. Significant processing delays (3+ minutes vs 7 seconds)

**Error Message:**
```
E0304 11:43:53.361058 1 python_be.cc:2415] Stub process is unhealthy and it will be restarted.
```

**Triton Logs:**
```
I0304 11:43:47.985271 1 http_server.cc:4509] HTTP request: 2 /v2/models/glm_ocr/infer
I0304 11:43:48.016204 1 python_be.cc:1362] model glm_ocr, instance glm_ocr_0_0, executing 1 requests
E0304 11:43:53.361058 1 python_be.cc:2415] Stub process is unhealthy and it will be restarted.
I0304 11:43:54.136735 1 stub_launcher.cc:253] Starting Python backend stub...
```

**Temporal Worker Logs:**
```
2026/03/04 11:43:54 ERROR Activity error. 
Error triton inference failed for page 1: triton http 500: 
{"error":"Failed to process the request(s) for model instance 'glm_ocr_0_0', 
message: Stub process 'glm_ocr_0_0' is not healthy."}
```

**Root Cause Analysis:**
1. **GPU Memory Issues:** Larger PDFs may exceed available GPU memory (RTX 2050 has limited VRAM)
2. **Timeout Issues:** Processing takes longer than stub timeout threshold
3. **Model Loading:** GLM-OCR model is large and takes ~50s to reload after crash
4. **No Graceful Degradation:** System doesn't fall back to smaller batch sizes or alternative processing

**Impact:**
- ❌ Production-blocking: Cannot reliably process real-world documents
- ❌ Poor user experience: 3+ minute delays vs 7 seconds for simple docs
- ❌ Resource waste: Model reloading consumes significant GPU/CPU resources
- ❌ Reliability: Unpredictable failures based on document complexity

### Bug #2: API Key Format Mismatch (FIXED)

**Severity:** 🟡 MEDIUM (Already Fixed)

**Description:**  
The test script initially used API key `dev-key-123` but the API gateway expects keys with prefix `tp-proj-` or `tp-test-`.

**Fix Applied:**  
Updated test script to use `tp-proj-dev-key-123`

**Status:** ✅ RESOLVED

### Bug #3: Missing Service Logs

**Severity:** 🟢 LOW

**Description:**  
GLM-OCR and PaddleOCR services don't output logs during processing, making debugging difficult.

**Observed:**
```
Service: docker-glm-ocr-service-1
No logs captured

Service: docker-paddleocr-service-1  
No logs captured
```

**Impact:**  
- Harder to debug GPU/model issues
- Cannot monitor GPU utilization
- Missing inference timing details

## Recommendations

### Immediate Actions (Critical)

1. **Fix Triton Stub Crashes**
   - Increase stub timeout from default to 600s
   - Add GPU memory monitoring and limits
   - Implement graceful degradation (reduce batch size on OOM)
   - Add retry logic with exponential backoff

2. **Optimize Model Loading**
   - Keep model in GPU memory between requests
   - Implement model warmup on startup
   - Consider model quantization to reduce memory footprint

3. **Add Monitoring**
   - GPU memory usage metrics
   - Inference timing per document size
   - Stub health checks
   - Alert on stub restarts

### Short-term Improvements

4. **Enhance Logging**
   - Add detailed logs to GLM-OCR service
   - Log GPU memory usage before/after inference
   - Add request/response timing logs

5. **Add Fallback Strategy**
   - Implement PaddleOCR fallback when Triton fails
   - Add document size limits with clear error messages
   - Queue large documents for batch processing

6. **Testing**
   - Add automated tests for various document sizes
   - Test with documents up to 10MB
   - Load testing with concurrent requests

### Long-term Enhancements

7. **Architecture Improvements**
   - Consider splitting large PDFs into smaller chunks
   - Implement progressive processing (page-by-page)
   - Add caching for preprocessed images

8. **Resource Management**
   - Dynamic GPU memory allocation
   - Request queuing based on available resources
   - Auto-scaling based on load

## Test Artifacts

- **Test Script:** `test_gpu_extraction_with_logs.py`
- **Results:** `test_results/extraction_result_20260304_171122.json`
- **Service Logs:** `test_results/service_logs_20260304_171122.txt`

## Conclusion

While GPU extraction works for simple documents, **the system is not production-ready** due to critical stability issues with larger PDFs. The Triton stub crash is a blocking issue that must be resolved before deployment.

**Next Steps:**
1. Create bugfix spec for Triton stub crash issue
2. Implement fixes and retry testing
3. Add comprehensive test suite for various document types/sizes
4. Performance optimization for large documents
