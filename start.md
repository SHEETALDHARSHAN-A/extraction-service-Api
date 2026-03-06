# Local Service Startup Commands

These are the exact PowerShell commands used to start all services for local end-to-end testing.

## 1. Post-processing Service

```powershell
Set-Location "c:\Users\MONISH RAJ T\OneDrive\Desktop\IDLE\services\post-processing-service"; cmd /c "..\..\run_with_env.bat python main.py"
```

## 2. Preprocessing Service

```powershell
Set-Location "c:\Users\MONISH RAJ T\OneDrive\Desktop\IDLE\services\preprocessing-service"; cmd /c "..\..\run_with_env.bat python main.py"
```

## 3. GLM OCR Service

```powershell
Set-Location "c:\Users\MONISH RAJ T\OneDrive\Desktop\IDLE\services\glm-ocr-service"; cmd /c "..\..\run_with_env.bat python -m uvicorn app.main:app --host 0.0.0.0 --port 8002"
```

## 4. Temporal Worker (local backend routing)

```powershell
Set-Location "c:\Users\MONISH RAJ T\OneDrive\Desktop\IDLE\services\temporal-worker"; $env:INFERENCE_BACKEND="glm_service"; $env:TEMPORAL_HOST="localhost:7233"; $env:TEMPORAL_NAMESPACE="default"; $env:TEMPORAL_TASK_QUEUE="document-processing-task-queue"; $env:PREPROCESSING_HOST="localhost:50051"; $env:POSTPROCESSING_HOST="localhost:50052"; $env:GLM_OCR_SERVICE_URL="grpc://localhost:50062"; $env:STORAGE_DRIVER="local"; $env:LOCAL_STORAGE_ROOT="c:\Users\MONISH RAJ T\OneDrive\Desktop\IDLE\.local\data\storage"; cmd /c "..\..\run_with_env.bat go run worker/main.go"
```

## 5. API Gateway (local mode)

```powershell
Set-Location "c:\Users\MONISH RAJ T\OneDrive\Desktop\IDLE\services\api-gateway"; $env:DATABASE_DRIVER="sqlite"; $env:DATABASE_URL="idep_local.db"; $env:STORAGE_DRIVER="local"; $env:LOCAL_STORAGE_ROOT="c:\Users\MONISH RAJ T\OneDrive\Desktop\IDLE\.local\data\storage"; $env:REDIS_URL="redis://localhost:6379/0"; $env:TEMPORAL_HOST="localhost:7233"; $env:TEMPORAL_NAMESPACE="default"; $env:TEMPORAL_TASK_QUEUE="document-processing-task-queue"; $env:MINIO_ENDPOINT="localhost:9000"; $env:MINIO_BUCKET="idep-documents"; $env:MINIO_ACCESS_KEY="minioadmin"; $env:MINIO_SECRET_KEY="minioadmin"; $env:MINIO_USE_SSL="false"; $env:PADDLEOCR_SERVICE_URL="grpc://localhost:50061"; $env:GLM_OCR_SERVICE_URL="grpc://localhost:50062"; $env:IDEP_API_KEYS="tp-proj-dev-key-123:admin,tp-test-sandbox-456:viewer"; $env:API_PORT="8000"; cmd /c "..\..\run_with_env.bat go run ."
```

