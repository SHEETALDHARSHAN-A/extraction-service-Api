@echo off
REM ============================================
REM  IDEP Platform - Test Suite (Windows)
REM  Run after docker-compose up
REM ============================================

echo.
echo ===== 1. HEALTH CHECK =====
curl -s http://localhost:8000/health
echo.

echo.
echo ===== 2. SINGLE FILE UPLOAD (with API Key) =====
echo Creating test PDF...
echo %%PDF-1.4 Test Document Content > test_document.pdf
curl -s -X POST http://localhost:8000/jobs/upload ^
  -H "Authorization: Bearer tp-proj-dev-key-123" ^
  -F "document=@test_document.pdf" ^
  -F "output_formats=json"
echo.

echo.
echo ===== 3. BATCH UPLOAD =====
echo Creating batch test files...
echo Test file 1 > test_batch_1.txt
echo Test file 2 > test_batch_2.txt
curl -s -X POST http://localhost:8000/jobs/batch ^
  -H "Authorization: Bearer tp-proj-dev-key-123" ^
  -F "documents=@test_batch_1.txt" ^
  -F "documents=@test_batch_2.txt" ^
  -F "output_formats=text"
echo.

echo.
echo ===== 4. LIST JOBS =====
curl -s http://localhost:8000/jobs -H "Authorization: Bearer tp-proj-dev-key-123"
echo.

echo.
echo ===== 5. PROMETHEUS METRICS =====
curl -s http://localhost:8000/metrics | findstr "idep_"
echo.

echo.
echo ===== 6. ADMIN STATS =====
curl -s http://localhost:8000/admin/stats -H "Authorization: Bearer tp-proj-dev-key-123"
echo.

echo.
echo ===== 7. RATE LIMIT CHECK =====
echo Sending rapid requests to test rate limiter...
for /L %%i in (1,1,5) do curl -s -o NUL -w "Request %%i: %%{http_code}\n" http://localhost:8000/health
echo.

echo.
echo ===== 8. UNAUTHORIZED ACCESS TEST =====
curl -s http://localhost:8000/jobs
echo.

echo.
echo ===== CLEANUP =====
del test_document.pdf test_batch_1.txt test_batch_2.txt 2>NUL
echo.
echo ===== ALL TESTS COMPLETE =====
echo.
echo Service URLs:
echo   API Gateway:   http://localhost:8000
echo   Temporal UI:   http://localhost:8080
echo   MinIO Console: http://localhost:9001  (minioadmin/minioadmin)
echo   Prometheus:    http://localhost:9090
echo   Grafana:       http://localhost:3000  (admin/idep-admin)
echo   Jaeger UI:     http://localhost:16686
echo   GPU Metrics:   http://localhost:8002/metrics
