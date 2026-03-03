Write-Host "Starting comprehensive Docker cleanup..." -ForegroundColor Cyan
Write-Host ""

# Stop all running containers
Write-Host "Stopping all Docker containers..." -ForegroundColor Yellow
docker-compose -f docker/docker-compose.yml down

# Remove all containers (including stopped ones)
Write-Host "Removing all containers..." -ForegroundColor Yellow
docker container prune -f

# Remove all volumes (including named volumes)
Write-Host "Removing all Docker volumes..." -ForegroundColor Yellow
$volumes = docker volume ls -q
if ($volumes) {
    $volumes | ForEach-Object { docker volume rm -f $_ 2>$null }
} else {
    Write-Host "No volumes to remove"
}

# Specifically remove project volumes
Write-Host "Removing project-specific volumes..." -ForegroundColor Yellow
@('docker_postgres_data', 'docker_minio_data', 'docker_prometheus_data', 'docker_grafana_data', 'docker_idep_tmp', 'docker_hf_cache') | ForEach-Object {
    docker volume rm -f $_ 2>$null
}

# Remove all images
Write-Host "Removing all Docker images..." -ForegroundColor Yellow
docker image prune -a -f

# Remove build cache
Write-Host "Removing Docker build cache..." -ForegroundColor Yellow
docker builder prune -a -f

# Remove networks
Write-Host "Removing unused networks..." -ForegroundColor Yellow
docker network prune -f

# System-wide cleanup
Write-Host "Running system-wide Docker cleanup..." -ForegroundColor Yellow
docker system prune -a --volumes -f

# Clean up local HuggingFace cache directory
Write-Host "Removing local HuggingFace cache..." -ForegroundColor Yellow
if (Test-Path "hf_cache_probe") {
    Remove-Item -Recurse -Force "hf_cache_probe"
    Write-Host "HuggingFace cache removed"
} else {
    Write-Host "No local HuggingFace cache found"
}

Write-Host ""
Write-Host "Docker cleanup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Current Docker disk usage:" -ForegroundColor Cyan
docker system df
