@echo off
REM ============================================
REM IDEP Platform - Local Non-Docker Startup
REM Starts all services for local development
REM ============================================
setlocal enabledelayedexpansion

echo.
echo =============================================
echo   IDEP Platform - Local Startup (No Docker)
echo =============================================
echo.

REM Load .env file
for /f "usebackq tokens=1,* delims==" %%a in ("%~dp0.env") do (
    set "line=%%a"
    if not "!line:~0,1!"=="#" (
        if not "!line!"=="" (
            set "%%a=%%b"
        )
    )
)

set "RUN_WITH_ENV=%~dp0run_with_env.bat"

REM Ensure local storage directories exist
if not exist "%~dp0.local\data\storage\idep-documents" (
    mkdir "%~dp0.local\data\storage\idep-documents" 2>nul
    echo [OK] Created local storage directory
)

REM ─── Step 1: Start Infrastructure ─────────────────────────────
echo.
echo [1/7] Starting infrastructure (Redis, Temporal)...
echo.

REM Check if Redis is running (ensure it's LISTENING)
netstat -ano 2>nul | find ":6379 " | findstr "LISTENING" >nul"
if !errorlevel! neq 0 (
    if exist "%~dp0.local\redis\redis-server.exe" (
        echo   Starting Redis...
        start "IDEP-Redis" cmd /k """%~dp0.local\redis\redis-server.exe"" --port 6379"
        timeout /t 2 /nobreak >nul
        echo   [OK] Redis started on :6379
    ) else (
        echo   [WARN] Redis not installed. Queue features disabled.
    )
) else (
    echo   [OK] Redis already running on :6379
)

REM Check if Temporal is running (ensure it's LISTENING)
netstat -ano 2>nul | find ":7233 " | findstr "LISTENING" >nul"
if !errorlevel! neq 0 (
    if exist "%~dp0.local\bin\temporal.exe" (
        echo   Starting Temporal dev server...
        start "IDEP-Temporal" cmd /k """%~dp0.local\bin\temporal.exe"" server start-dev --ip 127.0.0.1 --port 7233 --ui-port 8233"
        timeout /t 5 /nobreak >nul
        echo   [OK] Temporal started on :7233 (UI: :8233)
    ) else (
        echo   [WARN] Temporal not installed. Workflow processing disabled.
    )
) else (
    echo   [OK] Temporal already running on :7233
)

echo.

REM Propagate .env to services
copy /Y "%~dp0.env" "%~dp0services\api-gateway\.env" >nul"
copy /Y "%~dp0.env" "%~dp0services\preprocessing-service\.env" >nul"
copy /Y "%~dp0.env" "%~dp0services\temporal-worker\.env" >nul"
copy /Y "%~dp0.env" "%~dp0services\glm-ocr-service\.env" >nul"
copy /Y "%~dp0.env" "%~dp0services\post-processing-service\.env" >nul"

REM ─── Step 2: Start Preprocessing Service ──────────────────────
echo [2/7] Starting Preprocessing Service (gRPC :50051)...
netstat -ano 2>nul | find ":50051 " | findstr "LISTENING" >nul"
if !errorlevel! neq 0 (
    pushd services\preprocessing-service
    start "IDEP-Preprocessing" cmd /k call "%~dp0run_with_env.bat" go run main.go
    popd
    timeout /t 3 /nobreak >nul
    echo   [OK] Preprocessing service starting on :50051
) else (
    echo   [OK] Preprocessing service already running on :50051
)

REM ─── Step 3: Start Post-Processing Service ────────────────────
echo [3/7] Starting Post-Processing Service (gRPC :50052)...
netstat -ano 2>nul | find ":50052 " | findstr "LISTENING" >nul"
if !errorlevel! neq 0 (
    pushd services\post-processing-service
    start "IDEP-PostProcessing" cmd /k call "%~dp0run_with_env.bat" python main.py
    popd
    timeout /t 2 /nobreak >nul
    echo   [OK] Post-processing service starting on :50052
) else (
    echo   [OK] Post-processing service already running on :50052
)

REM ─── Step 4: Start GLM-OCR Service ────────────────────────────
echo [4/7] Starting GLM-OCR Service (HTTP :8002)...
netstat -ano 2>nul | find ":8002 " | findstr "LISTENING" >nul"
if !errorlevel! neq 0 (
    pushd services\glm-ocr-service
    start "IDEP-GLM-OCR" cmd /k call "%~dp0run_with_env.bat" python -m uvicorn app.main:app --host 0.0.0.0 --port 8002
    popd
    timeout /t 3 /nobreak >nul
    echo   [OK] GLM-OCR service starting on :8002
) else (
    echo   [OK] GLM-OCR service already running on :8002
)

REM ─── Step 5: Start Temporal Worker ────────────────────────────
echo [5/7] Starting Temporal Worker...
pushd services\temporal-worker
start "IDEP-Worker" cmd /k call "%~dp0run_with_env.bat" go run worker/main.go
popd
timeout /t 3 /nobreak >nul
echo   [OK] Temporal worker starting

REM ─── Step 6: Start API Gateway ────────────────────────────────
echo [6/7] Starting API Gateway (HTTP :8000)...
netstat -ano 2>nul | find ":8000 " | findstr "LISTENING" >nul"
if !errorlevel! neq 0 (
    pushd services\api-gateway
    start "IDEP-API-Gateway" cmd /k call "%~dp0run_with_env.bat" go run main.go
    popd
    timeout /t 5 /nobreak >nul
    echo   [OK] API Gateway starting on :8000
) else (
    echo   [OK] API Gateway already running on :8000
)

REM ─── Step 7: Summary ──────────────────────────────────────────
echo.
echo [7/7] Waiting for services to initialize...
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
echo   GLM-OCR Service:    http://localhost:8002
echo   GLM-OCR Health:     http://localhost:8002/health
echo   Temporal UI:        http://localhost:8233
echo.
echo   Storage: Local filesystem (.local/data/storage)
echo   Database: SQLite (idep_local.db)
echo.
echo   API Key: tp-proj-dev-key-123
echo.
echo   Quick Test:
echo     curl -X POST http://localhost:8000/jobs/upload ^
echo       -H "Authorization: Bearer tp-proj-dev-key-123" ^
echo       -F "document=@testfiles\sample.pdf"
echo.
echo   Run: test_local_e2e.bat for full end-to-end test
echo.
echo   Press Ctrl+C to stop all services
echo =============================================
echo.

REM Keep the script running to show it's active
pause
