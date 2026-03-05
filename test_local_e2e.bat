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
echo [1/5] Checking API Gateway health...
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
echo [2/5] Checking GLM-OCR service health...
curl -s -o nul -w "%%{http_code}" http://localhost:8002/health > "%TEMP%\idep_glm.txt" 2>nul
set /p GLM_CODE=<"%TEMP%\idep_glm.txt"
if "%GLM_CODE%"=="200" (
    echo   [OK] GLM-OCR service is healthy
) else (
    echo   [WARN] GLM-OCR service not healthy (code=%GLM_CODE%)
    echo          Model may still be loading...
)

REM ─── Step 3: Find a test file ─────────────────────────────────
echo [3/5] Looking for test files...

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

REM ─── Step 4: Upload Document ──────────────────────────────────
echo [4/5] Uploading document...
echo.

curl -s -X POST %API_URL%/jobs/upload ^
    -H "Authorization: Bearer %API_KEY%" ^
    -F "document=@%TEST_FILE%" ^
    -F "output_formats=text" ^
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

REM ─── Step 5: Poll for Completion ──────────────────────────────
echo [5/5] Polling for completion...

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
echo   =============================================
echo   [OK] Job COMPLETED!
echo   =============================================
echo.

REM Retrieve result
echo Retrieving result...
curl -s %API_URL%/jobs/%JOB_ID%/result ^
    -H "Authorization: Bearer %API_KEY%" ^
    -o "demo_results\%JOB_ID%_result.json" 2>nul

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
del "%TEMP%\idep_upload.json" 2>nul
del "%TEMP%\idep_status.json" 2>nul
