# IDEP - Intelligent Document Extraction Platform

An enterprise-scale document extraction service utilizing a dual orchestration pipeline: PaddleOCR for layout detection and GLM-OCR for high-fidelity region extraction. This system is designed for high resilience and durability.

## Architecture Overview

IDEP comprises an asynchronous microservices architecture orchestrated by [Temporal.io](https://temporal.io):

*   **API Gateway (Go)**: The primary entry point. Handles authentication, rate limiting, document caching, scheduling, and returns job statuses.
*   **Temporal Worker (Go)**: Orchestrates the core pipeline (preprocessing, layout detection, ML inference, and postprocessing).
*   **Fallback Gateway (Python)**: A secondary proxy for standard text processing bypassing ML models.
*   **PaddleOCR Service**: Used for fast layout and table detection.
*   **GLM-OCR Service / Triton Inference Server**: Specialized LLM-based text, formula, and table extraction on cropped regions.
*   **Infrastructure**: PostgreSQL (job state), Redis (caching, queueing & rate limiting), MinIO (document storage), Prometheus/Grafana/Jaeger (observability).

## Quick Start

### 1. Configure the Environment
Copy the configuration template and modify as needed:
```bash
cp .env.example .env
```
Ensure all secrets (`JWT_SECRET`, `MINIO_SECRET_KEY`, `POSTGRES_PASSWORD`, etc.) are securely set.

### 2. Launch the Platform
```bash
docker compose -f docker/docker-compose.yml up -d
```
*Note: Due to the complexity of the services (including Triton), startup may take several minutes.*

## Local Run (No Docker, Windows)

Use this path when you want to run and test services directly on your machine.

For full startup instructions (quick + manual per service), see `docs/SERVICES_STARTUP.md`.

### 1. One-time infra setup
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_local_infra.ps1
```

### 2. Start local infra (Redis, MinIO, Temporal)
```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_local_infra.ps1
```

### 3. Start all app services locally
```bat
start_local_bg.bat
```
This starts:
- API Gateway on `http://localhost:8000`
- PaddleOCR on `http://localhost:8001` and gRPC `:50061`
- GLM-OCR on `http://localhost:8002` and gRPC `:50062`
- Preprocessing gRPC on `:50051`
- Post-processing gRPC on `:50052`
- Temporal worker

### 4. Run end-to-end local test
```bat
test_local_e2e.bat
```

### 4a. Single API Call (Upload + Wait + Final Result)

Use this when you want one request to return the final extraction output directly.

```bash
curl -X POST http://localhost:8000/jobs/extract \
	-H "Authorization: Bearer tp-proj-dev-key-123" \
	-F "document=@testfiles/test_simple.png" \
	-F "output_formats=structured" \
	-F "include_coordinates=true" \
	-F "include_word_confidence=true" \
	-F "include_page_layout=true" \
	-F "wait_timeout_seconds=1200" \
	-F "poll_interval_ms=1000"
```

Timeout controls for long-running documents:
- `wait_timeout_seconds` default is `1200` (20 min), allowed range `10..7200`.
- `poll_interval_ms` default is `1000`, allowed range `200..5000`.

If processing exceeds your wait timeout, the endpoint returns `202` with `status_url` and `result_url`.

### 5. Stop local infra
```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop_local_infra.ps1
```
Then close remaining `IDEP-*` service windows if they are still open.

### Troubleshooting Quick Fixes

1. Ports already in use

```powershell
Get-NetTCPConnection -LocalPort 8000,8001,8002,50051,50052,50061,50062,7233,6379 -ErrorAction SilentlyContinue
```

2. Infra/service state looks stale

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop_local_infra.ps1
powershell -ExecutionPolicy Bypass -File scripts\start_local_infra.ps1
start_local_bg.bat
```

3. API up but extraction fails
- Verify `http://localhost:8002/health` (GLM service).
- Verify worker is running (`services/temporal-worker`).
- Re-run `test_local_e2e.bat` after both are healthy.

## Service Features

*   **Dual-Stage Pipeline**: Uses fast layout detection, followed by parallel region extraction.
*   **Durability**: Backed by Temporal, Jobs are resilient to worker crashes.
*   **Circuit Breakers**: Protection against transient ML service failures.
*   **Rate Limiting**: Distributed Redis-based API rate limits.
*   **Observability Full Stack**: Jaeger distributed tracing and Prometheus metrics are built-in.
