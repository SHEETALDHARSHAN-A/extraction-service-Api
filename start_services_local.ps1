param(
    [switch]$UseGlmService = $true
)

$ErrorActionPreference = "Stop"

Write-Host "Starting IDEP services in local mode (no Docker app services)..." -ForegroundColor Cyan

$pythonExe = $null
if (Test-Path ".venv311\Scripts\python.exe") {
    $pythonExe = (Resolve-Path ".venv311\Scripts\python.exe").Path
} elseif (Test-Path ".venv\Scripts\python.exe") {
    $pythonExe = (Resolve-Path ".venv\Scripts\python.exe").Path
} else {
    throw "Virtual environment not found. Create .venv311 (recommended) or .venv first."
}

$goWorkPath = (Resolve-Path ".\go.work").Path
Write-Host "Using Python: $pythonExe" -ForegroundColor DarkCyan
Write-Host "Using GOWORK: $goWorkPath" -ForegroundColor DarkCyan

$env:TEMPORAL_HOST = $env:TEMPORAL_HOST -as [string]
if ([string]::IsNullOrWhiteSpace($env:TEMPORAL_HOST)) { $env:TEMPORAL_HOST = "localhost:7233" }
if ([string]::IsNullOrWhiteSpace($env:TEMPORAL_NAMESPACE)) { $env:TEMPORAL_NAMESPACE = "default" }
if ([string]::IsNullOrWhiteSpace($env:TEMPORAL_TASK_QUEUE)) { $env:TEMPORAL_TASK_QUEUE = "document-processing-task-queue" }
if ([string]::IsNullOrWhiteSpace($env:MINIO_ENDPOINT)) { $env:MINIO_ENDPOINT = "localhost:9000" }
if ([string]::IsNullOrWhiteSpace($env:MINIO_ACCESS_KEY)) { $env:MINIO_ACCESS_KEY = "minioadmin" }
if ([string]::IsNullOrWhiteSpace($env:MINIO_SECRET_KEY)) { $env:MINIO_SECRET_KEY = "minioadmin" }
if ([string]::IsNullOrWhiteSpace($env:MINIO_BUCKET)) { $env:MINIO_BUCKET = "idep-documents" }
if ([string]::IsNullOrWhiteSpace($env:REDIS_HOST)) { $env:REDIS_HOST = "localhost" }
if ([string]::IsNullOrWhiteSpace($env:REDIS_PORT)) { $env:REDIS_PORT = "6379" }
if ([string]::IsNullOrWhiteSpace($env:DATABASE_URL)) { $env:DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/idep" }
if ([string]::IsNullOrWhiteSpace($env:REDIS_URL)) { $env:REDIS_URL = "redis://localhost:6379/0" }
if ([string]::IsNullOrWhiteSpace($env:PADDLEOCR_SERVICE_URL)) { $env:PADDLEOCR_SERVICE_URL = "http://localhost:8001" }
if ([string]::IsNullOrWhiteSpace($env:GLM_OCR_SERVICE_URL)) { $env:GLM_OCR_SERVICE_URL = "http://localhost:8002" }
if ([string]::IsNullOrWhiteSpace($env:PREPROCESSING_HOST)) { $env:PREPROCESSING_HOST = "localhost:50051" }
if ([string]::IsNullOrWhiteSpace($env:POSTPROCESSING_HOST)) { $env:POSTPROCESSING_HOST = "localhost:50052" }
if ([string]::IsNullOrWhiteSpace($env:TRITON_HOST)) { $env:TRITON_HOST = "localhost" }
if ([string]::IsNullOrWhiteSpace($env:TRITON_HTTP_PORT)) { $env:TRITON_HTTP_PORT = "8000" }
if ([string]::IsNullOrWhiteSpace($env:TRITON_GRPC_PORT)) { $env:TRITON_GRPC_PORT = "8001" }

if ($UseGlmService) {
    $env:INFERENCE_BACKEND = "glm_service"
    Write-Host "Inference backend: glm_service (local)" -ForegroundColor Yellow
} elseif ([string]::IsNullOrWhiteSpace($env:INFERENCE_BACKEND)) {
    $env:INFERENCE_BACKEND = "triton"
}

Write-Host "Launching local services in new terminals..." -ForegroundColor Cyan

Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:GOWORK='$goWorkPath'; cd '$PWD/services/preprocessing-service'; go run main.go"
Start-Sleep -Seconds 1
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD/services/post-processing-service'; '$pythonExe' main.py"
Start-Sleep -Seconds 1
if ($UseGlmService) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD/services/paddleocr-service'; '$pythonExe' -m uvicorn app.main:app --host 0.0.0.0 --port 8001"
    Start-Sleep -Seconds 1
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD/services/glm-ocr-service'; '$pythonExe' -m uvicorn app.main:app --host 0.0.0.0 --port 8002"
    Start-Sleep -Seconds 1
}
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:GOWORK='$goWorkPath'; cd '$PWD/services/temporal-worker'; go run worker/main.go"
Start-Sleep -Seconds 1
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:GOWORK='$goWorkPath'; cd '$PWD/services/api-gateway'; go run main.go"

Write-Host "Done. Ensure infra is running locally: PostgreSQL, Redis, MinIO, Temporal." -ForegroundColor Green
Write-Host "API health: http://localhost:8000/health" -ForegroundColor Green
