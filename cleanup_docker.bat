@echo off
echo 🧹 Starting comprehensive Docker cleanup...
echo.

REM Stop all running containers
echo ⏹️  Stopping all Docker containers...
docker-compose -f docker/docker-compose.yml down

REM Remove all containers (including stopped ones)
echo 🗑️  Removing all containers...
docker container prune -f

REM Remove all volumes (including named volumes)
echo 💾 Removing all Docker volumes...
FOR /F "tokens=*" %%i IN ('docker volume ls -q') DO docker volume rm -f %%i 2>nul

REM Specifically remove project volumes
echo 📦 Removing project-specific volumes...
docker volume rm -f docker_postgres_data docker_minio_data docker_prometheus_data docker_grafana_data docker_idep_tmp docker_hf_cache 2>nul

REM Remove all images
echo 🖼️  Removing all Docker images...
docker image prune -a -f

REM Remove build cache
echo 🏗️  Removing Docker build cache...
docker builder prune -a -f

REM Remove networks
echo 🌐 Removing unused networks...
docker network prune -f

REM System-wide cleanup
echo 🔧 Running system-wide Docker cleanup...
docker system prune -a --volumes -f

REM Clean up local HuggingFace cache directory
echo 🤗 Removing local HuggingFace cache...
if exist hf_cache_probe rmdir /s /q hf_cache_probe

echo.
echo ✅ Docker cleanup complete!
echo.
echo 📊 Current Docker disk usage:
docker system df
