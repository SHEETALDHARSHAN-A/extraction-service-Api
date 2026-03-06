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

### 5. Stop local infra
```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop_local_infra.ps1
```
Then close remaining `IDEP-*` service windows if they are still open.

## Service Features

*   **Dual-Stage Pipeline**: Uses fast layout detection, followed by parallel region extraction.
*   **Durability**: Backed by Temporal, Jobs are resilient to worker crashes.
*   **Circuit Breakers**: Protection against transient ML service failures.
*   **Rate Limiting**: Distributed Redis-based API rate limits.
*   **Observability Full Stack**: Jaeger distributed tracing and Prometheus metrics are built-in.
