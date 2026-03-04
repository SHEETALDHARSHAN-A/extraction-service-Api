# IDEP Platform — Complete Run & Test Guide

> **Hardware**: NVIDIA RTX 2050 GPU | **OS**: Windows  
> **Stack**: Go (Gin, Temporal SDK) + Python (Triton, Presidio) + Docker

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [First-Time Setup](#2-first-time-setup)
3. [Starting the Platform](#3-starting-the-platform)
4. [Verifying All Services](#4-verifying-all-services)
5. [Testing the API](#5-testing-the-api)
6. [GPU Verification](#6-gpu-verification)
7. [Monitoring & Observability](#7-monitoring--observability)
8. [Troubleshooting](#8-troubleshooting)
9. [Stopping & Cleanup](#9-stopping--cleanup)

---

## 1. Prerequisites

### Install These First

| Tool | Version | Install Command / Link |
|------|---------|----------------------|
| **Docker Desktop** | 4.x+ | https://docker.com/products/docker-desktop |
| **NVIDIA Container Toolkit** | latest | [Install Guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) |
| **NVIDIA Driver** | 535+ | https://www.nvidia.com/drivers |
| **Go** | 1.22+ | https://go.dev/dl |
| **Git** | latest | https://git-scm.com |
| **curl** | (builtin) | Comes with Windows 10+ |

### Enable GPU in Docker Desktop

1. Open **Docker Desktop** → **Settings** → **General**
2. Ensure **"Use WSL 2 based engine"** is checked
3. Go to **Settings** → **Resources** → **WSL Integration**
4. Enable integration with your WSL distro
5. Restart Docker Desktop

### Verify GPU access from Docker

```powershell
docker run --rm --gpus all nvidia/cuda:12.2.2-base-ubuntu22.04 nvidia-smi
```

Use a full tag (for example `12.2.2-base-ubuntu22.04`); generic tags like `latest` or `12.0-base` are not published for this repo.

You should see your **RTX 2050** listed with driver version and CUDA version.

> [!IMPORTANT]
> If `nvidia-smi` fails inside Docker, install the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html#docker) first.

---

## 2. First-Time Setup

### Step 1: Clone/Navigate to the project

```powershell
cd C:\Users\sreya\OneDrive\Desktop\Extraction-service
```

### Step 2: Initialize Go dependencies

```powershell
# API Gateway
cd services\api-gateway
go mod tidy

# Temporal Worker
cd ..\temporal-worker
go mod tidy

# Preprocessing Service
cd ..\preprocessing-service
go mod tidy

# Shared module
cd ..\..\shared
go mod tidy

# Back to root
cd ..
```

### Step 3: Verify all Go services compile

```powershell
cd services\api-gateway && go build -o NUL . && echo "API Gateway OK"
cd ..\temporal-worker && go build -o NUL .\worker\... && echo "Worker OK"
cd ..\preprocessing-service && go build -o NUL . && echo "Preprocessing OK"
cd ..\..
```

All three should print "OK" with no errors.

---

## 3. Starting the Platform

### Option A: Full Stack with GPU (Recommended)

```powershell
cd C:\Users\sreya\OneDrive\Desktop\Extraction-service
docker-compose -f docker\docker-compose.yml up --build -d
```

This starts **12 containers**:

| # | Container | Port | Purpose |
|---|-----------|------|---------|
| 1 | `api-gateway` | 8000 | REST API (Go/Gin) |
| 2 | `temporal-worker` | — | Workflow execution (Go) |
| 3 | `preprocessing-service` | 50051 | PDF/Image processing (Go/gRPC) |
| 4 | `postprocessing-service` | 50052 | PII redaction (Python/gRPC) |
| 5 | `triton` | 8001, 8002 | GLM-OCR inference (GPU) |
| 6 | `temporal` | 7233, 8080 | Workflow orchestrator |
| 7 | `db` | 5432 | PostgreSQL |
| 8 | `redis` | 6379 | Cache |
| 9 | `minio` | 9000, 9001 | Object storage |
| 10 | `prometheus` | 9090 | Metrics collection |
| 11 | `grafana` | 3000 | Dashboards |
| 12 | `jaeger` | 16686 | Distributed tracing |

### GPU Requirement

Production deployment requires NVIDIA GPU support for Triton inference.
Run with the standard production compose file:

```powershell
docker-compose -f docker\docker-compose.yml up --build -d
```

### Watch the Logs

```powershell
# All services
docker-compose -f docker\docker-compose.yml logs -f

# Specific service
docker-compose -f docker\docker-compose.yml logs -f api-gateway
docker-compose -f docker\docker-compose.yml logs -f triton
```

### Wait for Ready

All services take about 30-60 seconds to fully initialize. Wait until you see:

```
api-gateway    | ✅ PostgreSQL connected and migrated
api-gateway    | ✅ MinIO connected
api-gateway    | ✅ Temporal connected
api-gateway    | 🚀 API Gateway starting on :8000
temporal-worker| 🚀 Temporal Worker starting on queue: document-processing-task-queue
```

---

## 4. Verifying All Services

### 4.1 API Gateway Health

```powershell
curl http://localhost:8000/health
```

**Expected**:
```json
{"service":"idep-api-gateway","status":"healthy","time":"2026-02-26T..."}
```

### 4.2 Temporal UI

Open in browser: **http://localhost:8080**

You should see the Temporal Web UI with the `default` namespace.

### 4.3 MinIO Console

Open in browser: **http://localhost:9001**

Login: `minioadmin` / `minioadmin`

You should see the `idep-documents` bucket auto-created.

### 4.4 Prometheus

Open in browser: **http://localhost:9090**

Go to **Status → Targets** — you should see:
- `idep-api-gateway` — UP
- `triton-inference` — UP

### 4.5 Grafana

Open in browser: **http://localhost:3000**

Login: `admin` / `idep-admin`

Add Prometheus as a data source: URL = `http://prometheus:9090`

### 4.6 Jaeger

Open in browser: **http://localhost:16686**

### 4.7 Triton GPU Metrics

```powershell
curl http://localhost:8002/metrics | findstr "gpu"
```

---

## 5. Testing the API

### 5.1 Authentication (API Keys)

We use **OpenAI-style API Keys**. JWT and Role-based access have been removed for simplicity.

| Key Type | Prefix | Example Key |
|----------|--------|-------------|
| **Production** | `tp-proj-` | `tp-proj-dev-key-123` |
| **Test** | `tp-test-` | `tp-test-sandbox-456` |

**Usage**:
Pass the key in the `Authorization` header as a Bearer token:
```powershell
# -H "Authorization: Bearer tp-proj-dev-key-123"
```

### 5.2 Single Document Upload

Propagate options like `redact_pii`, `deskew`, or `enhance` (default: true).

```powershell
curl -X POST http://localhost:8000/jobs/upload ^
  -H "Authorization: Bearer tp-proj-dev-key-123" ^
  -F "document=@C:\path\to\your\document.pdf" ^
  -F "output_formats=json,structured" ^
  -F "redact_pii=true" ^
  -F "include_coordinates=true"
```

**Expected** (HTTP 202):
```json
{
  "job_id": "abc-123-...",
  "status": "PROCESSING",
  "result_url": "/jobs/abc-123-.../result",
  "status_url": "/jobs/abc-123-..."
}
```

### 5.3 Check Job Status

```powershell
curl http://localhost:8000/jobs/<JOB_ID> ^
  -H "Authorization: Bearer tp-proj-dev-key-123"
```

### 5.4 Batch Upload (Up to 10,000 files)

```powershell
curl -X POST http://localhost:8000/jobs/batch ^
  -H "Authorization: Bearer tp-proj-dev-key-123" ^
  -F "documents=@invoice1.pdf" ^
  -F "documents=@receipt.png" ^
  -F "output_formats=text"
```

### 5.5 Check Batch Progress

The batch status is highly detailed, showing overall percentage and per-file confidence.

```powershell
curl http://localhost:8000/jobs/batch/<BATCH_ID> ^
  -H "Authorization: Bearer tp-proj-dev-key-123"
```

**Features**:
- **Filter**: `?status=FAILED` to see only errors.
- **Progress**: Returns `"progress": "85.5%"` based on completed files.

### 5.6 Download Result

```powershell
curl http://localhost:8000/jobs/<JOB_ID>/result ^
  -H "Authorization: Bearer tp-proj-dev-key-123" ^
  -o result.json
```

### 5.7 List All Jobs

```powershell
curl http://localhost:8000/jobs ^
  -H "Authorization: Bearer tp-proj-dev-key-123"
```

### 5.8 Admin Stats

```powershell
curl http://localhost:8000/admin/stats ^
  -H "Authorization: Bearer tp-proj-dev-key-123"
```

### 5.9 Prometheus Metrics

```powershell
curl http://localhost:8000/metrics | findstr "idep_"
```

**Expected outputs**:
```
idep_http_requests_total{method="GET",path="/health",status="200"} 5
idep_http_request_duration_seconds_bucket{...}
idep_active_jobs 2
idep_jobs_total{status="created"} 4
```

### 5.10 Run All Tests

```powershell
.\scripts\test_all.bat
```

This runs all the above tests automatically.

---

## 6. GPU Verification

### 6.1 Check GPU is Allocated to Triton

```powershell
docker exec -it extraction-service-triton-1 nvidia-smi
```

**Expected**: Your RTX 2050 with Triton process visible:
```
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 535.xx       Driver Version: 535.xx       CUDA Version: 12.x    |
|-------------------------------+----------------------+----------------------+
| GPU  Name ...                 | Bus-Id        Disp.  | Memory-Usage         |
|   0  NVIDIA GeForce RTX 2050  | 0000:01:00.0  On     |  xxxMiB / 4096MiB    |
+-------------------------------+----------------------+----------------------+
|  Processes:                                                                 |
|    PID   Type   Process name                             GPU Memory Usage   |
|  xxxxx    C    /opt/tritonserver/bin/tritonserver              xxxMiB       |
+-----------------------------------------------------------------------------+
```

### 6.2 Check Triton Model Status

```powershell
curl http://localhost:8001/v2/models/glm_ocr
```

### 6.3 GPU Metrics via Prometheus

```powershell
curl http://localhost:8002/metrics | findstr "gpu_utilization"
```

### 6.4 Monitor GPU in Real-Time

```powershell
docker exec -it extraction-service-triton-1 watch -n 1 nvidia-smi
```

---

## 7. Monitoring & Observability

### 7.1 Workflow Monitoring (Temporal UI)

1. Open **http://localhost:8080**
2. Navigate to **Workflows** in the `default` namespace
3. You should see `doc-processing-<JOB_ID>` workflows
4. Click any workflow to see the step-by-step execution:
   - `Preprocess` → `CallTriton` → `PostProcess`
5. Check **Retry history** for any failed activities

### 7.2 Grafana Dashboard Setup

1. Open **http://localhost:3000** → Login (`admin`/`idep-admin`)
2. **Add Data Source** → Prometheus → URL: `http://prometheus:9090` → Save
3. **Create Dashboard** → Add panels with these queries:

| Panel | Prometheus Query |
|-------|-----------------|
| Request Rate | `rate(idep_http_requests_total[5m])` |
| P95 Latency | `histogram_quantile(0.95, rate(idep_http_request_duration_seconds_bucket[5m]))` |
| Active Jobs | `idep_active_jobs` |
| Jobs Created | `rate(idep_jobs_total{status="created"}[5m])` |
| GPU Utilization | `nv_gpu_utilization` (from Triton) |
| GPU Memory | `nv_gpu_memory_used_bytes / nv_gpu_memory_total_bytes` |

### 7.3 Jaeger Tracing

1. Open **http://localhost:16686**
2. Select service `idep-api-gateway` from dropdown
3. Click **Find Traces**
4. Click any trace to see the full request path

---

## 8. Troubleshooting and Common Issues

### Common Issues and Resolutions

#### Issue 1: Triton Stub Process Becomes Unhealthy

**Symptoms:**
- Triton health check fails
- Logs show "Stub process timeout" or "Stub process unhealthy"
- Requests fail with 503 errors
- GPU inference stops working

**Root Causes:**
- Large document processing exceeds stub timeout
- GPU memory exhaustion
- Model inference crash

**Resolution Steps:**

1. **Check Triton logs**:
```powershell
docker-compose -f docker\docker-compose.yml logs triton | findstr "stub"
```

2. **Verify stub timeout configuration**:
```powershell
docker-compose -f docker\docker-compose.yml exec triton ps aux | findstr "tritonserver"
# Should show: --backend-config=python,stub-timeout-seconds=600
```

3. **Check GPU memory**:
```powershell
docker exec -it extraction-service-triton-1 nvidia-smi
```

4. **If GPU memory is exhausted**:
```powershell
# Restart Triton to clear GPU memory
docker-compose -f docker\docker-compose.yml restart triton

# Wait for model to reload (2-3 minutes)
# Monitor logs
docker-compose -f docker\docker-compose.yml logs -f triton
```

5. **If stub timeout is too low**:
```powershell
# Update docker-compose.yml to increase timeout
# --backend-config=python,stub-timeout-seconds=600

# Rebuild and restart
docker-compose -f docker\docker-compose.yml up -d --build triton
```

6. **Verify health after restart**:
```powershell
curl http://localhost:18000/v2/health/ready
```

**Prevention:**
- Ensure stub timeout is set to 600 seconds
- Monitor GPU memory usage via Grafana
- Set up alerts for high GPU memory usage (>90%)

---

#### Issue 2: Queue Full - Requests Rejected with HTTP 429

**Symptoms:**
- API returns HTTP 429 "Queue is full"
- `retry_after_seconds` in error response
- Queue length at maximum (50)

**Root Causes:**
- High request volume exceeding processing capacity
- Slow processing due to large documents
- GPU bottleneck (only 1 concurrent inference)

**Resolution Steps:**

1. **Check queue status**:
```powershell
curl http://localhost:8000/queue/status
```

2. **Check Redis queue**:
```powershell
docker-compose -f docker\docker-compose.yml exec redis redis-cli ZCARD queue:pending
docker-compose -f docker\docker-compose.yml exec redis redis-cli HLEN queue:processing
```

3. **Identify stuck jobs**:
```powershell
# Check processing jobs
docker-compose -f docker\docker-compose.yml exec redis redis-cli HGETALL queue:processing

# Check Temporal workflows
# Open http://localhost:8080 and look for stuck workflows
```

4. **Clear stuck jobs** (if identified):
```powershell
# Cancel stuck workflow in Temporal UI
# Or manually remove from Redis (use with caution)
docker-compose -f docker\docker-compose.yml exec redis redis-cli HDEL queue:processing <job_id>
```

5. **Increase queue capacity** (temporary):
```powershell
# Update .env
QUEUE_MAX_LENGTH=100

# Restart API Gateway
docker-compose -f docker\docker-compose.yml restart api-gateway
```

6. **Monitor queue metrics**:
```powershell
# Open Grafana dashboard
# http://localhost:3000/d/queue-monitoring
```

**Prevention:**
- Set up queue length alerts (>40 jobs)
- Monitor average processing time
- Consider scaling horizontally (multiple GPU nodes)
- Implement request prioritization for critical jobs

---

#### Issue 3: GPU Out of Memory Errors

**Symptoms:**
- Requests fail with "CUDA out of memory"
- GPU memory usage at 100%
- Triton logs show memory allocation failures

**Root Causes:**
- Large document with many pages
- Memory leak in model code
- Insufficient GPU memory for model + inference

**Resolution Steps:**

1. **Check GPU memory usage**:
```powershell
docker exec -it extraction-service-triton-1 nvidia-smi
```

2. **Check GLM-OCR service metrics**:
```powershell
curl http://localhost:8002/metrics | findstr "gpu_memory"
```

3. **Clear GPU cache**:
```powershell
# Restart GLM-OCR service
docker-compose -f docker\docker-compose.yml restart glm-ocr-service

# Or restart Triton (more aggressive)
docker-compose -f docker\docker-compose.yml restart triton
```

4. **Check for memory leaks**:
```powershell
# Monitor GPU memory over time
docker exec -it extraction-service-triton-1 watch -n 1 nvidia-smi

# Process several documents and watch for memory growth
```

5. **Reduce batch size** (if applicable):
```powershell
# Update GLM-OCR service configuration
# Reduce MAX_PARALLEL_REGIONS in .env
MAX_PARALLEL_REGIONS=2

# Restart services
docker-compose -f docker\docker-compose.yml restart api-gateway temporal-worker
```

6. **Verify memory management settings**:
```powershell
# Check Triton environment variables
docker-compose -f docker\docker-compose.yml exec triton env | findstr "CUDA"
# Should show: PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512
```

**Prevention:**
- Monitor GPU memory usage continuously
- Set up alerts for GPU memory >90%
- Implement pre-flight memory checks (already in place)
- Document maximum supported document size

---

#### Issue 4: Slow Processing Times

**Symptoms:**
- Processing takes longer than expected
- P95 latency >30 seconds
- Queue wait times increasing

**Root Causes:**
- Large documents (many pages)
- Complex document layout
- GPU underutilization
- Network bottlenecks

**Resolution Steps:**

1. **Check processing time metrics**:
```powershell
# Open Grafana dashboard
# http://localhost:3000/d/request-processing
# Check P50, P95, P99 latencies
```

2. **Identify slow jobs**:
```powershell
# Check Temporal workflows
# Open http://localhost:8080
# Sort by duration, identify outliers
```

3. **Check GPU utilization**:
```powershell
docker exec -it extraction-service-triton-1 nvidia-smi
# Look for GPU utilization % - should be 70-90% during processing
```

4. **Check parallel processing**:
```powershell
# Verify MAX_PARALLEL_REGIONS setting
docker-compose -f docker\docker-compose.yml exec api-gateway env | findstr "MAX_PARALLEL"

# Increase if GPU is underutilized
MAX_PARALLEL_REGIONS=5
```

5. **Check preprocessing cache**:
```powershell
# Verify cache is enabled
docker-compose -f docker\docker-compose.yml exec api-gateway env | findstr "CACHE"

# Check Redis cache hit rate
docker-compose -f docker\docker-compose.yml exec redis redis-cli INFO stats | findstr "keyspace"
```

6. **Profile slow documents**:
```powershell
# Enable detailed logging
LOG_LEVEL=DEBUG

# Process document and check logs
docker-compose -f docker\docker-compose.yml logs -f glm-ocr-service
```

**Prevention:**
- Set up alerts for P95 latency >30s
- Monitor GPU utilization
- Optimize parallel processing settings
- Implement document size limits

---

#### Issue 5: High Error Rate

**Symptoms:**
- Error rate >10%
- Many failed jobs in Temporal
- Grafana shows high error rate

**Root Causes:**
- Invalid documents (corrupted PDFs)
- Service instability
- Configuration errors
- Resource exhaustion

**Resolution Steps:**

1. **Check error metrics**:
```powershell
# Open Grafana dashboard
# http://localhost:3000/d/request-processing
# Check error rate and error types
```

2. **Analyze error logs**:
```powershell
# Check API Gateway errors
docker-compose -f docker\docker-compose.yml logs api-gateway | findstr "ERROR"

# Check GLM-OCR errors
docker-compose -f docker\docker-compose.yml logs glm-ocr-service | findstr "ERROR"

# Check Temporal Worker errors
docker-compose -f docker\docker-compose.yml logs temporal-worker | findstr "ERROR"
```

3. **Identify error patterns**:
```powershell
# Group errors by type
docker-compose -f docker\docker-compose.yml logs api-gateway | findstr "ERROR" | findstr "error_type"
```

4. **Check service health**:
```powershell
curl http://localhost:8000/health
curl http://localhost:8002/health
curl http://localhost:18000/v2/health/ready
```

5. **Restart unhealthy services**:
```powershell
docker-compose -f docker\docker-compose.yml restart <service-name>
```

6. **Check for resource exhaustion**:
```powershell
# Check memory usage
docker stats

# Check disk space
docker system df
```

**Prevention:**
- Set up error rate alerts (>10%)
- Implement input validation
- Monitor service health continuously
- Set up automated service recovery

---

#### Issue 6: Database Connection Failures

**Symptoms:**
- "Failed to connect to database" errors
- API Gateway fails to start
- Job status queries fail

**Root Causes:**
- PostgreSQL not running
- Network connectivity issues
- Database credentials incorrect
- Connection pool exhausted

**Resolution Steps:**

1. **Check PostgreSQL status**:
```powershell
docker-compose -f docker\docker-compose.yml ps db
```

2. **Check PostgreSQL logs**:
```powershell
docker-compose -f docker\docker-compose.yml logs db
```

3. **Restart PostgreSQL**:
```powershell
docker-compose -f docker\docker-compose.yml restart db
# Wait 5 seconds
docker-compose -f docker\docker-compose.yml restart api-gateway
```

4. **Test database connection**:
```powershell
docker-compose -f docker\docker-compose.yml exec db psql -U postgres -d idep -c "SELECT 1;"
```

5. **Check connection pool**:
```powershell
# Check active connections
docker-compose -f docker\docker-compose.yml exec db psql -U postgres -d idep -c "SELECT count(*) FROM pg_stat_activity;"
```

6. **Verify credentials**:
```powershell
# Check .env file
type .env | findstr "DB_"
```

**Prevention:**
- Monitor database health
- Set up connection pool monitoring
- Configure connection pool limits appropriately
- Set up database backups

---

### Problem: "Failed to connect to database"
```powershell
# Check if PostgreSQL is running
docker-compose -f docker\docker-compose.yml ps db
# Restart the db
docker-compose -f docker\docker-compose.yml restart db
# Wait 5 seconds, then restart api-gateway
docker-compose -f docker\docker-compose.yml restart api-gateway
```

### Problem: "Failed to connect to Temporal"
```powershell
# Temporal needs PostgreSQL first. Restart in order:
docker-compose -f docker\docker-compose.yml restart db temporal temporal-worker
```

### Problem: Triton fails with GPU error
```powershell
# Verify NVIDIA runtime is available
docker info | findstr "nvidia"
# If not listed, install nvidia-container-toolkit and restart Docker Desktop
# Fallback: switch to mock mode (see Option B above)
```

### Problem: "unauthorized" on API calls
```powershell
# Make sure you include:
# -H "Authorization: Bearer tp-proj-dev-key-123"
```

### Problem: Build errors in Go services
```powershell
cd C:\Users\sreya\OneDrive\Desktop\Extraction-service
cd services\api-gateway && go mod tidy
cd ..\temporal-worker && go mod tidy
cd ..\preprocessing-service && go mod tidy
cd ..\..\shared && go mod tidy
```

### View Logs of Any Service
```powershell
docker-compose -f docker\docker-compose.yml logs -f <service-name>
# Examples: api-gateway, temporal-worker, triton, temporal, db
```

---

## 9. Monitoring and Alerting Procedures

### Daily Monitoring Checklist

Perform these checks daily to ensure system health:

1. **Check Service Health**:
```powershell
# All services should be "Up (healthy)"
docker-compose -f docker\docker-compose.yml ps
```

2. **Check Queue Status**:
```powershell
curl http://localhost:8000/queue/status
# Queue length should be <20
# Average wait time should be <30s
```

3. **Check GPU Health**:
```powershell
docker exec -it extraction-service-triton-1 nvidia-smi
# GPU utilization should be 0-90%
# Memory usage should be <90%
# Temperature should be <85°C
```

4. **Check Error Rate**:
```powershell
# Open Grafana: http://localhost:3000/d/request-processing
# Error rate should be <5%
```

5. **Check Processing Times**:
```powershell
# Open Grafana: http://localhost:3000/d/request-processing
# P95 latency should be <20s
```

6. **Check Disk Space**:
```powershell
docker system df
# Should have >20GB free
```

7. **Check Database Size**:
```powershell
docker-compose -f docker\docker-compose.yml exec db psql -U postgres -d idep -c "SELECT pg_size_pretty(pg_database_size('idep'));"
```

### Alert Response Procedures

#### High GPU Memory Usage Alert (>90%)

**Severity**: Warning  
**Response Time**: 15 minutes

**Actions**:
1. Check current GPU memory usage
2. Identify jobs using excessive memory
3. Consider restarting Triton if memory leak suspected
4. Review recent large documents
5. Update documentation if new maximum document size identified

#### Critical GPU Memory Usage Alert (>95%)

**Severity**: Critical  
**Response Time**: 5 minutes

**Actions**:
1. Immediately check GPU status
2. Restart Triton to free memory
3. Investigate root cause
4. Update capacity planning if needed

#### High Queue Length Alert (>40 jobs)

**Severity**: Warning  
**Response Time**: 30 minutes

**Actions**:
1. Check queue status and processing rate
2. Identify any stuck jobs
3. Check GPU utilization
4. Consider temporarily increasing queue capacity
5. Review capacity planning

#### Queue Near Capacity Alert (>45 jobs)

**Severity**: Critical  
**Response Time**: 10 minutes

**Actions**:
1. Immediately check for stuck jobs
2. Clear any stuck jobs
3. Increase queue capacity temporarily
4. Notify stakeholders of potential service degradation
5. Escalate if issue persists

#### High Error Rate Alert (>10%)

**Severity**: Warning  
**Response Time**: 15 minutes

**Actions**:
1. Check error logs for patterns
2. Identify error types
3. Check service health
4. Restart unhealthy services
5. Investigate root cause

#### Critical Error Rate Alert (>25%)

**Severity**: Critical  
**Response Time**: 5 minutes

**Actions**:
1. Immediately check all service health
2. Restart unhealthy services
3. Check for infrastructure issues
4. Notify stakeholders
5. Escalate to engineering team

#### Slow Processing Alert (P95 >30s)

**Severity**: Warning  
**Response Time**: 30 minutes

**Actions**:
1. Check GPU utilization
2. Review recent documents for complexity
3. Check parallel processing settings
4. Review cache hit rate
5. Optimize if needed

### Monitoring Dashboard URLs

| Dashboard | URL | Purpose |
|-----------|-----|---------|
| Grafana - GPU Monitoring | http://localhost:3000/d/gpu-monitoring | GPU memory, utilization |
| Grafana - Queue Monitoring | http://localhost:3000/d/queue-monitoring | Queue length, wait times |
| Grafana - Request Processing | http://localhost:3000/d/request-processing | Latency, error rates |
| Prometheus | http://localhost:9090 | Raw metrics, alerts |
| Jaeger | http://localhost:16686 | Distributed tracing |
| Temporal UI | http://localhost:8080 | Workflow execution |

### Metrics to Monitor

#### GPU Metrics
- `gpu_memory_allocated_gb`: Current GPU memory in use
- `gpu_memory_free_gb`: Available GPU memory
- `nv_gpu_utilization`: GPU utilization percentage
- `nv_gpu_memory_used_bytes`: GPU memory used (from Triton)

#### Queue Metrics
- `queue_length`: Current queue length
- `queue_processing_count`: Jobs being processed
- `queue_avg_wait_time_seconds`: Average wait time
- `queue_avg_processing_time_seconds`: Average processing time
- `queue_throughput_per_hour`: Jobs per hour

#### Request Metrics
- `extraction_requests_total`: Total requests (by status)
- `extraction_duration_seconds`: Processing time histogram
- `idep_http_requests_total`: HTTP requests (by endpoint, status)
- `idep_http_request_duration_seconds`: HTTP latency histogram

#### System Metrics
- `process_resident_memory_bytes`: Service memory usage
- `process_cpu_seconds_total`: Service CPU usage
- `go_goroutines`: Active goroutines (Go services)

---

## 10. Scaling and Capacity Planning

### Current Capacity

**Single GPU Node (RTX 2050)**:
- **Throughput**: ~100-150 documents/hour (depends on document size)
- **Concurrent Processing**: 1 GPU inference + 3 parallel pages
- **Queue Capacity**: 50 pending jobs
- **GPU Memory**: 4GB VRAM
- **Processing Time**: 
  - Small documents (<1MB, 1-5 pages): 5-10 seconds
  - Medium documents (1-5MB, 5-10 pages): 15-30 seconds
  - Large documents (5-10MB, 10-20 pages): 30-60 seconds

### Scaling Strategies

#### Vertical Scaling (Upgrade GPU)

**Option 1: Upgrade to RTX 3060 (12GB VRAM)**
- **Benefits**: 
  - 3x more GPU memory
  - Can process larger documents
  - Can increase batch size
- **Throughput Increase**: ~50% (150-225 docs/hour)
- **Cost**: ~$400-500

**Option 2: Upgrade to RTX 4070 (12GB VRAM)**
- **Benefits**:
  - 3x more GPU memory
  - Faster inference (newer architecture)
  - Better power efficiency
- **Throughput Increase**: ~100% (200-300 docs/hour)
- **Cost**: ~$600-700

#### Horizontal Scaling (Multiple GPU Nodes)

**Option 1: Add Second GPU Node**
- **Setup**: Deploy second instance with same configuration
- **Load Balancing**: Use nginx or HAProxy
- **Throughput**: 2x (200-300 docs/hour)
- **Complexity**: Medium (need load balancer, shared Redis/DB)

**Option 2: Kubernetes Cluster**
- **Setup**: Deploy on Kubernetes with multiple GPU nodes
- **Auto-scaling**: Scale based on queue length
- **Throughput**: 3-5x (300-750 docs/hour)
- **Complexity**: High (need K8s expertise, GPU operator)

### Capacity Planning Guidelines

#### When to Scale

**Scale Up (Vertical) When**:
- GPU memory usage consistently >80%
- Processing large documents frequently
- Single node is sufficient for throughput needs

**Scale Out (Horizontal) When**:
- Queue length consistently >30
- Throughput needs exceed single GPU capacity
- Need high availability / redundancy

#### Capacity Calculation

**Formula**:
```
Required Capacity = (Peak Requests/Hour) / (Throughput/Hour) * Safety Factor

Safety Factor = 1.5 (50% headroom)
```

**Example**:
- Peak: 200 requests/hour
- Current throughput: 100 docs/hour
- Required capacity: 200 / 100 * 1.5 = 3 nodes

#### Cost-Benefit Analysis

| Option | Cost | Throughput | Complexity | Recommendation |
|--------|------|------------|------------|----------------|
| Current (RTX 2050) | $0 | 100-150/hr | Low | <150 docs/hr |
| Upgrade to RTX 3060 | $400 | 150-225/hr | Low | 150-200 docs/hr |
| Upgrade to RTX 4070 | $600 | 200-300/hr | Low | 200-250 docs/hr |
| Add 2nd Node | $1000 | 200-300/hr | Medium | 250-400 docs/hr |
| K8s Cluster (3 nodes) | $2000+ | 300-750/hr | High | >400 docs/hr |

### Performance Optimization

Before scaling, consider these optimizations:

1. **Enable Preprocessing Cache**:
```bash
CACHE_LAYOUT_RESULTS=true
LAYOUT_CACHE_TTL_SECONDS=3600
```
- **Impact**: 20-30% throughput increase for repeated documents

2. **Optimize Parallel Processing**:
```bash
MAX_PARALLEL_REGIONS=5  # Increase if GPU underutilized
```
- **Impact**: 10-20% throughput increase

3. **Implement Request Prioritization**:
- Process small documents first
- **Impact**: Reduced average wait time

4. **Optimize Model Inference**:
- Use FP16 precision (if accuracy acceptable)
- **Impact**: 30-40% faster inference

5. **Implement Document Size Limits**:
```bash
MAX_DOCUMENT_SIZE_MB=10
MAX_PAGES=20
```
- **Impact**: Prevents resource exhaustion

### Monitoring for Capacity Planning

Track these metrics over time:

1. **Peak Request Rate**: Requests per hour during peak times
2. **Average Processing Time**: By document size
3. **Queue Length**: Maximum and average
4. **GPU Utilization**: Percentage during processing
5. **Error Rate**: Percentage of failed requests

**Review Frequency**: Monthly or when traffic increases >20%

---

## 11. Stopping & Cleanup

### Stop All Services
```powershell
docker-compose -f docker\docker-compose.yml down
```

### Stop and Remove All Data (Fresh Start)
```powershell
docker-compose -f docker\docker-compose.yml down -v
```

### Rebuild a Single Service
```powershell
docker-compose -f docker\docker-compose.yml build api-gateway
docker-compose -f docker\docker-compose.yml up -d api-gateway
```

---

## Quick Reference: All Service URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| API Gateway | http://localhost:8000 | Key: `tp-proj-dev-key-123` |
| Temporal UI | http://localhost:8080 | — |
| MinIO Console | http://localhost:9001 | `minioadmin` / `minioadmin` |
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3000 | `admin` / `idep-admin` |
| Jaeger | http://localhost:16686 | — |
| PostgreSQL | localhost:5432 | `postgres` / `postgres` |
| Redis | localhost:6379 | — |
| Triton gRPC | localhost:8001 | — |
| Triton Metrics | http://localhost:8002 | — |
