# IDEP Services Startup Guide

This guide covers how to start all local services for IDEP (no Docker) in the correct order.

## Quick Commands

Run from repo root:

```powershell
# Start infra only
powershell -ExecutionPolicy Bypass -File scripts\start_local_infra.ps1

# Start all application services in background
start_local_bg.bat

# Run end-to-end verification
test_local_e2e.bat

# Stop infra
powershell -ExecutionPolicy Bypass -File scripts\stop_local_infra.ps1
```

## 1. Services Overview

Infrastructure services:

- Redis (`localhost:6379`)
- MinIO API (`http://localhost:9000`)
- MinIO Console (`http://localhost:9001`)
- Temporal Frontend (`localhost:7233`)
- Temporal UI (`http://localhost:8233`)

Application services:

- Preprocessing service (gRPC `localhost:50051`)
- Post-processing service (gRPC `localhost:50052`)
- PaddleOCR service (HTTP `http://localhost:8001`, gRPC `localhost:50061`)
- GLM-OCR service (HTTP `http://localhost:8002`, gRPC `localhost:50062`)
- Temporal worker (`services/temporal-worker`)
- API Gateway (HTTP `http://localhost:8000`)

## 2. Quick Start (Recommended)

From repo root:

```bat
start_local_bg.bat
```

This starts all services in background/minimized windows.

For visible service windows, use:

```bat
start_local.bat
```

## 3. Infra Startup Only

If you only want infra first:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_local_infra.ps1
```

One-time setup for local binaries:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_local_infra.ps1
```

## 4. Manual Service Startup (Step by Step)

Use this section when you want full control or debugging.

### 4.1 Start infra

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_local_infra.ps1
```

### 4.2 Start preprocessing

```powershell
Set-Location services\preprocessing-service
..\..\run_with_env.bat python main.py
```

### 4.3 Start post-processing

```powershell
Set-Location services\post-processing-service
..\..\run_with_env.bat python main.py
```

### 4.4 Start PaddleOCR

```powershell
Set-Location services\paddleocr-service
..\..\run_with_env.bat python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

### 4.5 Start GLM-OCR

```powershell
Set-Location services\glm-ocr-service
..\..\run_with_env.bat python -m uvicorn app.main:app --host 0.0.0.0 --port 8002
```

### 4.6 Start Temporal worker

```powershell
Set-Location services\temporal-worker
..\..\run_with_env.bat go run worker/main.go
```

### 4.7 Start API Gateway

```powershell
Set-Location services\api-gateway
..\..\run_with_env.bat go run .
```

## 5. Verify All Services

### 5.1 HTTP checks

- API gateway health: `http://localhost:8000/health`
- GLM health: `http://localhost:8002/health`
- Paddle HTTP: `http://localhost:8001`

### 5.2 Port checks (PowerShell)

```powershell
Test-NetConnection localhost -Port 8000
Test-NetConnection localhost -Port 8001
Test-NetConnection localhost -Port 8002
Test-NetConnection localhost -Port 50051
Test-NetConnection localhost -Port 50052
Test-NetConnection localhost -Port 50061
Test-NetConnection localhost -Port 50062
Test-NetConnection localhost -Port 7233
Test-NetConnection localhost -Port 6379
```

### 5.3 End-to-end test

```bat
test_local_e2e.bat
```

## 6. Stop Services

Stop infra:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop_local_infra.ps1
```

Then close any remaining `IDEP-*` terminal windows for app services.

## 7. Common Issues

- `.env missing`: create or restore `.env` in repo root.
- Port already in use: stop previous process or change service port.
- API is up but extraction fails: verify GLM (`8002`, `50062`) and worker are running.
- Temporal not connected: verify `localhost:7233` and worker logs.
- Slow startup: first model warm-up can take extra time.

## 8. Default Local Mode Notes

Local scripts enforce these defaults:

- SQLite (`DATABASE_DRIVER=sqlite`)
- Local storage (`STORAGE_DRIVER=local`)
- Non-isolated GLM mode (`USE_ISOLATED_GPU_EXECUTOR=false`)

These defaults are intended for stable local development and testing.
