# Docker Complete Cleanup and Fresh Build Guide

## Step 1: Complete Cleanup

Run ONE of these commands to clean everything:

### Option A: Using PowerShell (Recommended)
```powershell
.\docker_full_cleanup.ps1
```

### Option B: Using Command Prompt
```cmd
docker_full_cleanup.bat
```

### Option C: Manual Commands
```powershell
# Stop all containers
docker stop $(docker ps -aq)

# Remove all containers
docker rm -f $(docker ps -aq)

# Remove all images
docker rmi -f $(docker images -aq)

# Remove all volumes
docker volume rm $(docker volume ls -q)

# Remove all networks
docker network prune -f

# Remove all build cache
docker builder prune -af

# Verify cleanup
docker system df
```

## Step 2: Fresh Build

After cleanup, run ONE of these:

### Option A: Using PowerShell (Recommended)
```powershell
.\docker_fresh_build.ps1
```

### Option B: Using Command Prompt
```cmd
docker_fresh_build.bat
```

### Option C: Manual Commands
```powershell
# Build all services from scratch (takes 10-20 minutes)
docker-compose -f docker/docker-compose.yml build --no-cache

# Start all services
docker-compose -f docker/docker-compose.yml up -d

# Check status
docker-compose -f docker/docker-compose.yml ps
```

## Step 3: Verify Services

Check if services are running:
```powershell
docker-compose -f docker/docker-compose.yml ps
```

Check logs:
```powershell
# All services
docker-compose -f docker/docker-compose.yml logs -f

# Specific service
docker-compose -f docker/docker-compose.yml logs -f paddleocr-service
docker-compose -f docker/docker-compose.yml logs -f glm-ocr-service
docker-compose -f docker/docker-compose.yml logs -f api-gateway
```

## Step 4: Test Extraction

Once services are healthy, test with:
```powershell
python real_extraction.py --document "testfiles\Mr.P.Vaidyanathan Rs.4,95,000.pdf" --formats json --coordinates yes
```

## Troubleshooting

### If build fails:
1. Check error messages in the output
2. Make sure Docker Desktop is running
3. Make sure you have enough disk space (at least 20GB free)
4. Try building one service at a time:
   ```powershell
   docker-compose -f docker/docker-compose.yml build paddleocr-service
   docker-compose -f docker/docker-compose.yml build glm-ocr-service
   docker-compose -f docker/docker-compose.yml build api-gateway
   ```

### If services won't start:
1. Check logs: `docker-compose -f docker/docker-compose.yml logs`
2. Check if ports are already in use
3. Restart Docker Desktop

### Common Issues:
- **Out of disk space**: Run cleanup script again
- **Port conflicts**: Stop other services using ports 8000, 8001, 8002, 5432, 6379, 9000
- **GPU issues**: Make sure NVIDIA drivers are installed for glm-ocr-service

## Quick Reference

| Command | Description |
|---------|-------------|
| `docker-compose -f docker/docker-compose.yml ps` | Check service status |
| `docker-compose -f docker/docker-compose.yml logs -f SERVICE` | View logs |
| `docker-compose -f docker/docker-compose.yml restart SERVICE` | Restart a service |
| `docker-compose -f docker/docker-compose.yml down` | Stop all services |
| `docker-compose -f docker/docker-compose.yml up -d` | Start all services |
| `docker system df` | Check disk usage |
