@echo off
echo ============================================================
echo Starting Document Extraction Services
echo ============================================================
echo.

echo Checking Docker...
docker --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker is not installed or not running!
    echo Please install Docker Desktop and start it.
    pause
    exit /b 1
)

echo Docker is available
echo.

echo Starting services with Docker Compose...
docker-compose -f docker/docker-compose.yml up -d

echo.
echo ============================================================
echo Services are starting...
echo This may take 30-60 seconds
echo ============================================================
echo.

echo Waiting for services to be ready...
timeout /t 30 /nobreak >nul

echo.
echo Checking API health...
curl http://localhost:8000/health 2>nul
if errorlevel 1 (
    echo.
    echo WARNING: API not responding yet
    echo Services may still be starting up
    echo Wait a bit longer and try: curl http://localhost:8000/health
) else (
    echo.
    echo SUCCESS: API is ready!
)

echo.
echo ============================================================
echo Services Status:
echo ============================================================
docker-compose -f docker/docker-compose.yml ps

echo.
echo ============================================================
echo Ready to extract documents!
echo ============================================================
echo.
echo Run: python real_extraction.py --document "testfiles\your_file.pdf"
echo.
pause
