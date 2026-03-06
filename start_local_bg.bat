@echo off
setlocal enabledelayedexpansion

echo.
echo =============================================
echo   IDEP Platform - Local Startup (Background)
echo =============================================
echo.

if not exist "%~dp0.env" (
    echo [FAIL] Missing %~dp0.env
    exit /b 1
)

for /f "usebackq tokens=1,* delims==" %%a in ("%~dp0.env") do (
    set "line=%%a"
    if not "!line!"=="" if not "!line:~0,1!"=="#" (
        set "%%a=%%b"
    )
)

REM Force local-safe defaults for non-docker runs.
set "DATABASE_DRIVER=sqlite"
set "DATABASE_URL=idep_local.db"
set "STORAGE_DRIVER=local"
set "LOCAL_STORAGE_ROOT=%~dp0.local\data\storage"
set "REDIS_URL=redis://localhost:6379/0"
set "TEMPORAL_HOST=localhost:7233"
set "MINIO_ENDPOINT=localhost:9000"
set "MINIO_USE_SSL=false"
set "PREPROCESSING_HOST=localhost:50051"
set "POSTPROCESSING_HOST=localhost:50052"
set "PADDLEOCR_SERVICE_URL=grpc://localhost:50061"
set "GLM_OCR_SERVICE_URL=grpc://localhost:50062"
set "INFERENCE_BACKEND=glm_service"
set "USE_ISOLATED_GPU_EXECUTOR=false"
set "API_PORT=8000"
set "SERVICE_HOST=0.0.0.0"

set "RUN_WITH_ENV=%~dp0run_with_env.bat"

REM Ensure local storage directories exist
if not exist "%~dp0.local\data\storage\idep-documents" (
    mkdir "%~dp0.local\data\storage\idep-documents" 2>nul
    echo [OK] Created local storage directory
)

REM ─── Step 1: Start Infrastructure ─────────────────────────────
echo.
echo [1/8] Starting infrastructure (Redis, Temporal)...
echo.

REM Check if Redis is running (ensure it's LISTENING)
netstat -ano 2>nul | find ":6379 " | findstr "LISTENING" >nul
if !errorlevel! neq 0 (
    if exist "%~dp0.local\redis\redis-server.exe" (
        echo   Starting Redis...
        start "IDEP-Redis" /min cmd /c """%~dp0.local\redis\redis-server.exe"" --port 6379"
        timeout /t 2 /nobreak >nul
        echo   [OK] Redis started on :6379
    ) else (
        echo   [WARN] Redis not installed. Queue features disabled.
    )
) else (
    echo   [OK] Redis already running on :6379
)

REM Check if Temporal is running (ensure it's LISTENING)
netstat -ano 2>nul | find ":7233 " | findstr "LISTENING" >nul
if !errorlevel! neq 0 (
    if exist "%~dp0.local\bin\temporal.exe" (
        echo   Starting Temporal dev server...
        start "IDEP-Temporal" /min cmd /c """%~dp0.local\bin\temporal.exe"" server start-dev --ip 127.0.0.1 --port 7233 --ui-port 8233"
        timeout /t 5 /nobreak >nul
        echo   [OK] Temporal started on :7233, UI on :8233
    ) else (
        echo   [WARN] Temporal not installed. Workflow processing disabled.
    )
) else (
    echo   [OK] Temporal already running on :7233
)

echo.

REM Propagate .env to services
copy /Y "%~dp0.env" "%~dp0services\api-gateway\.env" >nul
copy /Y "%~dp0.env" "%~dp0services\preprocessing-service\.env" >nul
copy /Y "%~dp0.env" "%~dp0services\temporal-worker\.env" >nul
copy /Y "%~dp0.env" "%~dp0services\glm-ocr-service\.env" >nul
copy /Y "%~dp0.env" "%~dp0services\paddleocr-service\.env" >nul
copy /Y "%~dp0.env" "%~dp0services\post-processing-service\.env" >nul

REM ─── Step 2: Start Preprocessing Service ──────────────────────
echo [2/8] Starting Preprocessing Service (gRPC :50051)...
netstat -ano 2>nul | find ":50051 " | findstr "LISTENING" >nul
if !errorlevel! neq 0 (
    pushd services\preprocessing-service
    start "IDEP-Preprocessing" /min cmd /c ""call "%RUN_WITH_ENV%" python main.py""
    popd
    timeout /t 3 /nobreak >nul
    echo   [OK] Preprocessing service starting on :50051
) else (
    echo   [OK] Preprocessing service already running on :50051
)

REM ─── Step 3: Start Post-Processing Service ────────────────────
echo [3/8] Starting Post-Processing Service (gRPC :50052)...
netstat -ano 2>nul | find ":50052 " | findstr "LISTENING" >nul
if !errorlevel! neq 0 (
    pushd services\post-processing-service
    start "IDEP-PostProcessing" /min cmd /c ""call "%RUN_WITH_ENV%" python main.py""
    popd
    timeout /t 2 /nobreak >nul
    echo   [OK] Post-processing service starting on :50052
) else (
    echo   [OK] Post-processing service already running on :50052
)

REM ─── Step 4: Start PaddleOCR Service ──────────────────────────
echo [4/8] Starting PaddleOCR Service (HTTP :8001, gRPC :50061)...
netstat -ano 2>nul | find ":8001 " | findstr "LISTENING" >nul
if !errorlevel! neq 0 (
    pushd services\paddleocr-service
    start "IDEP-PaddleOCR" /min cmd /c ""call "%RUN_WITH_ENV%" python -m uvicorn app.main:app --host 0.0.0.0 --port 8001""
    popd
    timeout /t 4 /nobreak >nul
    echo   [OK] PaddleOCR service starting on :8001 and :50061
) else (
    echo   [OK] PaddleOCR service already running on :8001
)

REM ─── Step 4: Start GLM-OCR Service ────────────────────────────
echo [5/8] Starting GLM-OCR Service (HTTP :8002, gRPC :50062)...
netstat -ano 2>nul | find ":8002 " | findstr "LISTENING" >nul
if !errorlevel! neq 0 (
    pushd services\glm-ocr-service
    start "IDEP-GLM-OCR" /min cmd /c ""call "%RUN_WITH_ENV%" python -m uvicorn app.main:app --host 0.0.0.0 --port 8002""
    popd
    timeout /t 3 /nobreak >nul
    echo   [OK] GLM-OCR service starting on :8002 and :50062
) else (
    echo   [OK] GLM-OCR service already running on :8002
)

REM ─── Step 5: Start Temporal Worker ────────────────────────────
echo [6/8] Starting Temporal Worker...
pushd services\temporal-worker
start "IDEP-Worker" /min cmd /c ""call "%RUN_WITH_ENV%" go run worker/main.go""
popd
timeout /t 3 /nobreak >nul
echo   [OK] Temporal worker starting

REM ─── Step 6: Start API Gateway ────────────────────────────────
echo [7/8] Starting API Gateway (HTTP :8000)...
netstat -ano 2>nul | find ":8000 " | findstr "LISTENING" >nul
if !errorlevel! neq 0 (
    pushd services\api-gateway
    start "IDEP-API-Gateway" /min cmd /c ""call "%RUN_WITH_ENV%" go run .""
    popd
    timeout /t 5 /nobreak >nul
    echo   [OK] API Gateway starting on :8000
) else (
    echo   [OK] API Gateway already running on :8000
)

REM ─── Step 7: Summary ──────────────────────────────────────────
echo.
echo [8/8] Waiting for services to initialize...
timeout /t 5 /nobreak >nul

echo.
echo =============================================
echo   IDEP Platform - All Services Started!
echo =============================================
echo.
echo   Service Endpoints:
echo   ------------------------------------------
echo   API Gateway:        http://localhost:8000
echo   API Health:         http://localhost:8000/health
echo   PaddleOCR Service:  http://localhost:8001 (gRPC :50061)
echo   GLM-OCR Service:    http://localhost:8002
echo   GLM-OCR Health:     http://localhost:8002/health (gRPC :50062)
echo   Preprocessing gRPC: localhost:50051
echo   Postprocess gRPC:   localhost:50052
echo   Temporal UI:        http://localhost:8233
echo.
echo   Storage: Local filesystem (.local/data/storage)
echo   Database: SQLite (idep_local.db)
echo.
echo   API Key: tp-proj-dev-key-123
echo.
echo   Quick Test:
echo     curl -X POST http://localhost:8000/jobs/upload -H "Authorization: Bearer tp-proj-dev-key-123" -F "document=@testfiles\sample.pdf"
echo.
echo   Run: test_local_e2e.bat for full end-to-end test
echo.
echo   Services are running in background windows.
echo   Use scripts\stop_local_infra.ps1 and close IDEP-* windows to stop everything.
echo =============================================
echo.
exit /b 0
