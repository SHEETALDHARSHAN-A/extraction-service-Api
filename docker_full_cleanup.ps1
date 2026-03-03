Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Docker Complete Cleanup Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "This will remove:" -ForegroundColor Yellow
Write-Host "- All containers (running and stopped)" -ForegroundColor Yellow
Write-Host "- All images" -ForegroundColor Yellow
Write-Host "- All volumes" -ForegroundColor Yellow
Write-Host "- All networks" -ForegroundColor Yellow
Write-Host "- All build cache" -ForegroundColor Yellow
Write-Host ""
$confirmation = Read-Host "Continue? (y/n)"
if ($confirmation -ne 'y') {
    Write-Host "Cleanup cancelled" -ForegroundColor Red
    exit
}

Write-Host ""
Write-Host "[1/6] Stopping all running containers..." -ForegroundColor Green
$containers = docker ps -aq
if ($containers) {
    docker stop $containers 2>$null
    Write-Host "Containers stopped successfully" -ForegroundColor Green
} else {
    Write-Host "No running containers found" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[2/6] Removing all containers..." -ForegroundColor Green
$containers = docker ps -aq
if ($containers) {
    docker rm -f $containers 2>$null
    Write-Host "Containers removed successfully" -ForegroundColor Green
} else {
    Write-Host "No containers to remove" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[3/6] Removing all images..." -ForegroundColor Green
$images = docker images -aq
if ($images) {
    docker rmi -f $images 2>$null
    Write-Host "Images removed successfully" -ForegroundColor Green
} else {
    Write-Host "No images to remove" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[4/6] Removing all volumes..." -ForegroundColor Green
$volumes = docker volume ls -q
if ($volumes) {
    docker volume rm $volumes 2>$null
    Write-Host "Volumes removed successfully" -ForegroundColor Green
} else {
    Write-Host "No volumes to remove" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[5/6] Removing all networks..." -ForegroundColor Green
docker network prune -f
Write-Host "Networks cleaned" -ForegroundColor Green

Write-Host ""
Write-Host "[6/6] Removing all build cache..." -ForegroundColor Green
docker builder prune -af
Write-Host "Build cache cleared" -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Cleanup Complete!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Docker system status:" -ForegroundColor Cyan
docker system df

Write-Host ""
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
