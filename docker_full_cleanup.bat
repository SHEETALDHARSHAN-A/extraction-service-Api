@echo off
echo ========================================
echo Docker Complete Cleanup Script
echo ========================================
echo.
echo This will remove:
echo - All containers (running and stopped)
echo - All images
echo - All volumes
echo - All networks
echo - All build cache
echo.
pause

echo.
echo [1/6] Stopping all running containers...
docker stop $(docker ps -aq) 2>nul
if %errorlevel% equ 0 (
    echo Containers stopped successfully
) else (
    echo No running containers found
)

echo.
echo [2/6] Removing all containers...
docker rm -f $(docker ps -aq) 2>nul
if %errorlevel% equ 0 (
    echo Containers removed successfully
) else (
    echo No containers to remove
)

echo.
echo [3/6] Removing all images...
docker rmi -f $(docker images -aq) 2>nul
if %errorlevel% equ 0 (
    echo Images removed successfully
) else (
    echo No images to remove
)

echo.
echo [4/6] Removing all volumes...
docker volume rm $(docker volume ls -q) 2>nul
if %errorlevel% equ 0 (
    echo Volumes removed successfully
) else (
    echo No volumes to remove
)

echo.
echo [5/6] Removing all networks...
docker network prune -f
echo Networks cleaned

echo.
echo [6/6] Removing all build cache...
docker builder prune -af
echo Build cache cleared

echo.
echo ========================================
echo Cleanup Complete!
echo ========================================
echo.
echo Docker system status:
docker system df

echo.
echo Press any key to exit...
pause >nul
