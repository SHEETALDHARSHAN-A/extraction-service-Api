Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Docker Fresh Build Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "This will build all services from scratch" -ForegroundColor Yellow
Write-Host ""
$confirmation = Read-Host "Continue? (y/n)"
if ($confirmation -ne 'y') {
    Write-Host "Build cancelled" -ForegroundColor Red
    exit
}

Write-Host ""
Write-Host "[1/3] Building all services (this may take 10-20 minutes)..." -ForegroundColor Green
docker-compose -f docker/docker-compose.yml build --no-cache --progress=plain

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "BUILD FAILED!" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "Check the error messages above" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "[2/3] Starting all services..." -ForegroundColor Green
docker-compose -f docker/docker-compose.yml up -d

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "STARTUP FAILED!" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "Check the error messages above" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "[3/3] Checking service status..." -ForegroundColor Green
Start-Sleep -Seconds 5
docker-compose -f docker/docker-compose.yml ps

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Build Complete!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Services are starting up. This may take a few minutes." -ForegroundColor Yellow
Write-Host ""
Write-Host "Useful commands:" -ForegroundColor Cyan
Write-Host "- Check logs: docker-compose -f docker/docker-compose.yml logs -f" -ForegroundColor White
Write-Host "- Check status: docker-compose -f docker/docker-compose.yml ps" -ForegroundColor White
Write-Host "- Stop services: docker-compose -f docker/docker-compose.yml down" -ForegroundColor White
Write-Host ""
Read-Host "Press Enter to exit"
