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

## 8. Troubleshooting

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

## 9. Stopping & Cleanup

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
