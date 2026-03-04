@echo off
echo ========================================
echo Docker WSL Fix Script
echo ========================================
echo.
echo This will restart Docker Desktop and WSL
echo.
pause

echo.
echo [1/4] Stopping Docker Desktop...
taskkill /F /IM "Docker Desktop.exe" 2>nul
timeout /t 3 /nobreak >nul

echo.
echo [2/4] Restarting WSL...
wsl --shutdown
timeout /t 5 /nobreak >nul

echo.
echo [3/4] Starting Docker Desktop...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
echo Waiting for Docker to start (30 seconds)...
timeout /t 30 /nobreak >nul

echo.
echo [4/4] Checking Docker status...
docker ps

echo.
echo ========================================
echo Fix Complete!
echo ========================================
echo.
echo Now try starting services again:
echo docker-compose -f docker/docker-compose.yml up -d
echo.
pause
