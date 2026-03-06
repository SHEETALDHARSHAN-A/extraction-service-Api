@echo off
REM ============================================
REM IDEP Platform - Local End-to-End Test
REM Tests the full pipeline: upload → process → retrieve result
REM ============================================
setlocal enabledelayedexpansion

echo.
echo =============================================
echo   IDEP - Local End-to-End Test
echo =============================================
echo.

set API_URL=http://localhost:8000
set API_KEY=tp-proj-dev-key-123

REM ─── Step 1: Health Check ─────────────────────────────────────
echo [1/8] Checking API Gateway health...
curl -s -o nul -w "%%{http_code}" %API_URL%/health > "%TEMP%\idep_health.txt" 2>nul
set /p HEALTH_CODE=<"%TEMP%\idep_health.txt"
if "%HEALTH_CODE%"=="200" (
    echo   [OK] API Gateway is healthy
) else (
    echo   [FAIL] API Gateway is not responding on %API_URL%
    echo          Make sure to run start_local.bat first!
    exit /b 1
)

REM ─── Step 2: Check GLM-OCR Service ───────────────────────────
echo [2/8] Checking GLM-OCR service health...
set GLM_READY=0
set GLM_TRIES=0
set GLM_MAX_TRIES=24

:glm_wait_loop
set /a GLM_TRIES+=1
curl -s http://localhost:8002/health -o "%TEMP%\idep_glm_health.json" 2>nul

for /f "tokens=*" %%a in ('python -c "import json; d=json.load(open(r'%TEMP%\idep_glm_health.json')); s=str(d.get('health_status', d.get('status',''))).lower(); m=d.get('model_loaded', None); ok=(s=='healthy') or (m is True); print('1' if ok else '0')" 2^>nul') do set GLM_READY=%%a

if "%GLM_READY%"=="1" (
    echo   [OK] GLM-OCR model is ready
) else (
    echo   [INFO] GLM-OCR not ready yet ^(attempt %GLM_TRIES%/%GLM_MAX_TRIES%^) - waiting...
    if %GLM_TRIES% geq %GLM_MAX_TRIES% (
        echo   [WARN] GLM-OCR model did not become ready in time.
        echo          Continuing anyway, extraction may fail with 503 while model restarts.
    ) else (
        timeout /t 5 /nobreak >nul
        goto :glm_wait_loop
    )
)

REM ─── Step 3: Check PaddleOCR Service ─────────────────────────
echo [3/8] Checking PaddleOCR service health...
curl -s -o nul -w "%%{http_code}" http://localhost:8001/health > "%TEMP%\idep_paddle.txt" 2>nul
set /p PADDLE_CODE=<"%TEMP%\idep_paddle.txt"
if "%PADDLE_CODE%"=="200" (
    echo   [OK] PaddleOCR service is healthy
) else (
    echo   [WARN] PaddleOCR service not healthy (code=%PADDLE_CODE%)
)

REM ─── Step 4: Check gRPC Ports ────────────────────────────────
echo [4/8] Checking gRPC service ports...
set PORT_FAIL=0
for %%P in (50051 50052 50061 50062) do (
    powershell -NoProfile -Command "$ok=Test-NetConnection -ComputerName localhost -Port %%P -InformationLevel Quiet -WarningAction SilentlyContinue; if($ok){exit 0}else{exit 1}" >nul 2>nul
    if errorlevel 1 (
        echo   [WARN] Port %%P is not listening
        set PORT_FAIL=1
    ) else (
        echo   [OK] Port %%P is listening
    )
)
if "%PORT_FAIL%"=="1" (
    echo          One or more gRPC services are unavailable.
)

REM ─── Step 5: Find a test file ─────────────────────────────────
echo [5/8] Looking for test files...

set TEST_FILE=
if exist "testfiles\sample.pdf" (
    set TEST_FILE=testfiles\sample.pdf
) else if exist "test_simple.png" (
    set TEST_FILE=test_simple.png
) else (
    REM Find any file in testfiles
    for %%F in (testfiles\*.*) do (
        set TEST_FILE=%%F
        goto :found_file
    )
)
:found_file

if "%TEST_FILE%"=="" (
    echo   [WARN] No test files found. Creating a test image...
    REM Create a simple test PNG
    python -c "from PIL import Image, ImageDraw, ImageFont; img=Image.new('RGB',(400,200),'white'); d=ImageDraw.Draw(img); d.text((20,20),'INVOICE\nDate: 2026-03-05\nTotal: $1,234.56',fill='black'); img.save('test_simple.png')" 2>nul
    if exist "test_simple.png" (
        set TEST_FILE=test_simple.png
        echo   [OK] Created test image: test_simple.png
    ) else (
        echo   [FAIL] Cannot create test file. Please place a PDF or image in testfiles\
        exit /b 1
    )
) else (
    echo   [OK] Using test file: %TEST_FILE%
)

REM ─── Step 6: Upload Document ──────────────────────────────────
echo [6/8] Uploading document...
echo.

curl -s -X POST %API_URL%/jobs/upload ^
    -H "Authorization: Bearer %API_KEY%" ^
    -F "document=@%TEST_FILE%" ^
    -F "output_formats=text,json,structured" ^
    -F "fast_mode=true" ^
    -F "max_tokens=512" ^
    -F "precision_mode=high" ^
    -F "include_coordinates=true" ^
    -F "include_word_confidence=true" ^
    -F "include_line_confidence=true" ^
    -F "include_page_layout=true" ^
    -F "enable_layout_detection=true" ^
    -F "detect_tables=true" ^
    -F "detect_formulas=true" ^
    -F "parallel_region_processing=true" ^
    -F "max_parallel_regions=5" ^
    -F "min_confidence=0.5" ^
    -F "granularity=word" ^
    -F "language=auto" ^
    -F "max_pages=0" ^
    -F "temperature=0.0" ^
    -F "redact_pii=false" ^
    -F "enhance=false" ^
    -F "deskew=false" ^
    -o "%TEMP%\idep_upload.json"

type "%TEMP%\idep_upload.json"
echo.

REM Extract job_id from response
for /f "tokens=*" %%a in ('python -c "import json; d=json.load(open(r'%TEMP%\idep_upload.json')); print(d.get('job_id',''))" 2^>nul') do set JOB_ID=%%a

if "%JOB_ID%"=="" (
    echo   [FAIL] Upload failed - no job_id in response
    exit /b 1
)

echo.
echo   [OK] Document uploaded! Job ID: %JOB_ID%
echo.

REM ─── Step 7: Poll for Completion ──────────────────────────────
echo [7/8] Polling for completion...

set ATTEMPTS=0
set MAX_ATTEMPTS=60
set STATUS=PROCESSING

:poll_loop
if %ATTEMPTS% geq %MAX_ATTEMPTS% goto :timeout

set /a ATTEMPTS+=1

curl -s %API_URL%/jobs/%JOB_ID% ^
    -H "Authorization: Bearer %API_KEY%" ^
    -o "%TEMP%\idep_status.json" 2>nul

for /f "tokens=*" %%a in ('python -c "import json; d=json.load(open(r'%TEMP%\idep_status.json')); print(d.get('status','UNKNOWN'))" 2^>nul') do set STATUS=%%a

echo   Attempt %ATTEMPTS%/%MAX_ATTEMPTS% - Status: %STATUS%

if "%STATUS%"=="COMPLETED" goto :completed
if "%STATUS%"=="FAILED" goto :failed

timeout /t 5 /nobreak >nul
goto :poll_loop

:completed
echo.
echo [8/8] Retrieving final result...
echo.
echo   =============================================
echo   [OK] Job COMPLETED!
echo   =============================================
echo.

REM Retrieve result
if not exist "demo_results" mkdir demo_results

curl -s %API_URL%/jobs/%JOB_ID%/result ^
    -H "Authorization: Bearer %API_KEY%" ^
    -o "demo_results\%JOB_ID%_result.json"

echo.
echo   Result saved to: demo_results\%JOB_ID%_result.json
echo.
echo   Result preview:
type "demo_results\%JOB_ID%_result.json"
echo.
echo.
echo   =============================================
echo   END-TO-END TEST PASSED!
echo   =============================================
goto :done

:failed
echo.
echo   [FAIL] Job failed!
echo   Status details:
type "%TEMP%\idep_status.json"
echo.
goto :done

:timeout
echo.
echo   [TIMEOUT] Job did not complete within %MAX_ATTEMPTS% attempts
echo   Last status: %STATUS%
echo   This may be normal if the GLM model is still loading.
goto :done

:done
echo.
REM Cleanup temp files
del "%TEMP%\idep_health.txt" 2>nul
del "%TEMP%\idep_glm.txt" 2>nul
del "%TEMP%\idep_paddle.txt" 2>nul
del "%TEMP%\idep_upload.json" 2>nul
del "%TEMP%\idep_status.json" 2>nul
