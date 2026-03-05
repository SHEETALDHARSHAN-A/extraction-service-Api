# IDEP Local + Docker Dual Runtime Guide

This repository now supports both runtime modes:

- **Docker mode (default):** worker uses Triton backend.
- **Local mode (Windows-friendly):** worker can call GLM service directly (no Triton required).

## 1) Docker Mode (existing)

Use the existing compose flow:

```powershell
docker-compose -f docker\docker-compose.yml up --build -d
```

`temporal-worker` runs with:

- `INFERENCE_BACKEND=triton`
- `GLM_OCR_SERVICE_URL=http://glm-ocr-service:8002`

## 2) Local Mode (no Docker app services)

In local mode, run infra as local binaries/services, then run app services locally.

### Required infra running on host

- PostgreSQL (`localhost:5432`)
- Redis (`localhost:6379`)
- MinIO (`localhost:9000`)
- Temporal (`localhost:7233`)

### Start local services quickly

```powershell
.
\start_services_local.ps1
```

This script starts:

- preprocessing-service (Go)
- post-processing-service (Python gRPC)
- paddleocr-service (FastAPI)
- glm-ocr-service (FastAPI)
- temporal-worker (Go)
- api-gateway (Go)

and sets:

- `INFERENCE_BACKEND=glm_service`

### Optional Triton local mode

If you still want Triton in local mode:

```powershell
$env:INFERENCE_BACKEND="triton"
```

and ensure Triton is reachable via `TRITON_HOST`/`TRITON_HTTP_PORT`.

## 3) New worker config keys

- `INFERENCE_BACKEND`: `triton` or `glm_service`
- `GLM_OCR_SERVICE_URL`: URL of GLM OCR HTTP service (default `http://localhost:8002`)

## 4) Health checks

```powershell
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8002/health
```
