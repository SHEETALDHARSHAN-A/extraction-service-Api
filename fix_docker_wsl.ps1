Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Docker WSL Fix Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "This will restart Docker Desktop and WSL" -ForegroundColor Yellow
Write-Host ""
$confirmation = Read-Host "Continue? (y/n)"
if ($confirmation -ne 'y') {
    Write-Host "Fix cancelled" -ForegroundColor Red
    exit
}

Write-Host ""
Write-Host "[1/4] Stopping Docker Desktop..." -ForegroundColor Green
Stop-Process -Name "Docker Desktop" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

Write-Host ""
Write-Host "[2/4] Restarting WSL..." -ForegroundColor Green
wsl --shutdown
Start-Sleep -Seconds 5

Write-Host ""
Write-Host "[3/4] Starting Docker Desktop..." -ForegroundColor Green
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
Write-Host "Waiting for Docker to start (30 seconds)..." -ForegroundColor Yellow
Start-Sleep -Seconds 30

Write-Host ""
Write-Host "[4/4] Checking Docker status..." -ForegroundColor Green
docker ps

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Fix Complete!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Now try starting services again:" -ForegroundColor Yellow
Write-Host "docker-compose -f docker/docker-compose.yml up -d" -ForegroundColor White
Write-Host ""
Read-Host "Press Enter to exit"
