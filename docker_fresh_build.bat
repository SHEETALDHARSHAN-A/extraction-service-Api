@echo off
echo ========================================
echo Docker Fresh Build Script
echo ========================================
echo.
echo This will build all services from scratch
echo.
pause

echo.
echo [1/3] Building all services (this may take 10-20 minutes)...
docker-compose -f docker/docker-compose.yml build --no-cache --progress=plain

if %errorlevel% neq 0 (
    echo.
    echo ========================================
    echo BUILD FAILED!
    echo ========================================
    echo Check the error messages above
    pause
    exit /b 1
)

echo.
echo [2/3] Starting all services...
docker-compose -f docker/docker-compose.yml up -d

if %errorlevel% neq 0 (
    echo.
    echo ========================================
    echo STARTUP FAILED!
    echo ========================================
    echo Check the error messages above
    pause
    exit /b 1
)

echo.
echo [3/3] Checking service status...
timeout /t 5 /nobreak >nul
docker-compose -f docker/docker-compose.yml ps

echo.
echo ========================================
echo Build Complete!
echo ========================================
echo.
echo Services are starting up. This may take a few minutes.
echo.
echo To check logs: docker-compose -f docker/docker-compose.yml logs -f
echo To check status: docker-compose -f docker/docker-compose.yml ps
echo.
pause
