@echo off
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "RUN_WITH_ENV=%ROOT%run_with_env.bat"

echo =============================================
echo   IDEPPlatform - Definitive Local Startup
echo =============================================

echo [1/3] Starting Infrastructure...
start /B "IDEP-Redis" "%ROOT%.local\redis\redis-server.exe" --port 6379 
timeout /t 2 /nobreak >nul
start /B "IDEP-Temporal" "%ROOT%.local\bin\temporal.exe" server start-dev --ip 127.0.0.1 --port 7233 --ui-port 8233
timeout /t 10 /nobreak >nul

echo [2/3] Starting Services...
pushd services\preprocessing-service
start /B "IDEP-Pre" cmd /c """%RUN_WITH_ENV%"" go run main.go"
popd
pushd services\post-processing-service
start /B "IDEP-Post" cmd /c """%RUN_WITH_ENV%"" python main.py"
popd
pushd services\glm-ocr-service
start /B "IDEP-OCR" cmd /c """%RUN_WITH_ENV%"" python -m uvicorn app.main:app --host 0.0.0.0 --port 8002"
popd
pushd services\temporal-worker
start /B "IDEP-Worker" cmd /c """%RUN_WITH_ENV%"" go run worker/main.go"
popd
pushd services\api-gateway
start /B "IDEP-Gateway" cmd /c """%RUN_WITH_ENV%"" go run main.go"
popd

echo [3/3] Waiting for API Gateway (30s)...
timeout /t 30 /nobreak >nul

echo.
echo =============================================
echo   Triggering Final Test Upload
echo =============================================
curl.exe -v -X POST http://localhost:8000/jobs/upload ^
  -H "Authorization: Bearer tp-proj-dev-key-123" ^
  -F "document=@testfiles\test_simple.png"

echo.
echo =============================================
echo   Startup Sequence Complete
echo =============================================
pause
