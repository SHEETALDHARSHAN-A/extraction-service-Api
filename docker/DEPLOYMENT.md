# Docker Compose Deployment Guide

This guide provides instructions for deploying the PaddleOCR Microservice Architecture using Docker Compose.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Service Architecture](#service-architecture)
- [Configuration](#configuration)
- [Starting Services](#starting-services)
- [Stopping Services](#stopping-services)
- [Health Checks](#health-checks)
- [Troubleshooting](#troubleshooting)
- [Resource Requirements](#resource-requirements)

## Prerequisites

### Required Software

- **Docker**: Version 20.10 or higher
- **Docker Compose**: Version 2.0 or higher
- **NVIDIA GPU** (for GLM-OCR service): RTX 2050 or better with CUDA support
- **NVIDIA Container Toolkit**: For GPU support in Docker

### System Requirements

**Minimum:**
- CPU: 8 cores
- RAM: 32GB
- GPU: NVIDIA GPU with 8GB VRAM (for GLM-OCR)
- Disk: 50GB free space

**Recommended:**
- CPU: 16 cores
- RAM: 64GB
- GPU: NVIDIA GPU with 12GB+ VRAM
- Disk: 100GB free space (SSD preferred)

### Installing NVIDIA Container Toolkit

For GPU support, install the NVIDIA Container Toolkit:

```bash
# Ubuntu/Debian
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

Verify GPU access:
```bash
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

## Quick Start

1. **Clone the repository** (if not already done):
   ```bash
   git clone <repository-url>
   cd <repository-directory>
   ```

2. **Create environment file**:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start all services**:
   ```bash
   cd docker
   docker-compose up -d
   ```

4. **Check service health**:
   ```bash
   docker-compose ps
   ```

5. **View logs**:
   ```bash
   docker-compose logs -f
   ```

## Service Architecture

The system consists of the following services:

### Core Services

| Service | Port | Description |
|---------|------|-------------|
| **api-gateway** | 8000 | Main API endpoint, orchestrates requests |
| **paddleocr-service** | 8001 | Layout detection using PaddleOCR |
| **glm-ocr-service** | 8002 | Content extraction using GLM-OCR |
| **temporal-worker** | - | Background job processing |

### Infrastructure Services

| Service | Port | Description |
|---------|------|-------------|
| **db** (PostgreSQL) | 5432 | Database for job metadata |
| **redis** | 6379 | Cache for layout detection results |
| **minio** | 9000, 9001 | Object storage for documents |
| **temporal** | 7233, 8080 | Workflow orchestration |
| **triton** | 18000, 8001, 8002 | ML model serving |

### Supporting Services

| Service | Port | Description |
|---------|------|-------------|
| **preprocessing-service** | 50051 | Document preprocessing |
| **postprocessing-service** | 50052 | Result post-processing |

### Observability Services

| Service | Port | Description |
|---------|------|-------------|
| **prometheus** | 9090 | Metrics collection |
| **grafana** | 3000 | Metrics visualization |
| **jaeger** | 16686 | Distributed tracing |

## Configuration

### Environment Variables

All configuration is done through environment variables. Copy `.env.example` to `.env` and adjust values:

```bash
cp ../.env.example ../.env
```

#### Key Configuration Options

**PaddleOCR Service:**
```bash
PADDLEOCR_USE_GPU=false          # Set to true for GPU mode
MIN_CONFIDENCE_DEFAULT=0.5       # Minimum confidence threshold
MAX_IMAGE_SIZE_MB=10             # Maximum image size
```

**GLM-OCR Service:**
```bash
GLM_MODEL_PATH=zai-org/GLM-OCR   # HuggingFace model ID
GLM_PRECISION_MODE=normal        # Options: normal, high, precision
CUDA_VISIBLE_DEVICES=0           # GPU device ID
```

**API Gateway:**
```bash
ENABLE_LAYOUT_DETECTION=true     # Enable two-stage pipeline
CACHE_LAYOUT_RESULTS=true        # Cache layout detection
LAYOUT_CACHE_TTL_SECONDS=3600    # Cache TTL (1 hour)
MAX_PARALLEL_REGIONS=5           # Max parallel region processing
```

**Circuit Breaker:**
```bash
CIRCUIT_BREAKER_THRESHOLD=5      # Failures before opening circuit
CIRCUIT_BREAKER_TIMEOUT_SECONDS=60  # Recovery timeout
```

### Development vs Production

**Development Mode:**
- Uses `docker-compose.override.yml` automatically
- Enables hot-reloading for code changes
- Includes development tools (Redis Commander, Adminer)
- Debug logging enabled

**Production Mode:**
- Disable override file: `docker-compose -f docker-compose.yml up -d`
- Set `LOG_LEVEL=INFO` or `WARN`
- Use strong passwords and secrets
- Configure proper resource limits

## Starting Services

### Start All Services

```bash
cd docker
docker-compose up -d
```

### Start Specific Services

```bash
# Start only core services
docker-compose up -d api-gateway paddleocr-service glm-ocr-service

# Start infrastructure only
docker-compose up -d db redis minio temporal
```

### Build and Start

Force rebuild of images:
```bash
docker-compose up -d --build
```

### View Startup Logs

```bash
# Follow all logs
docker-compose logs -f

# Follow specific service
docker-compose logs -f paddleocr-service

# View last 100 lines
docker-compose logs --tail=100
```

## Stopping Services

### Stop All Services

```bash
docker-compose down
```

### Stop and Remove Volumes

**WARNING:** This will delete all data including databases and model caches!

```bash
docker-compose down -v
```

### Stop Specific Services

```bash
docker-compose stop paddleocr-service glm-ocr-service
```

### Restart Services

```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart api-gateway
```

## Health Checks

### Check Service Status

```bash
docker-compose ps
```

Expected output:
```
NAME                    STATUS              PORTS
api-gateway             Up (healthy)        0.0.0.0:8000->8000/tcp
paddleocr-service       Up (healthy)        0.0.0.0:8001->8001/tcp
glm-ocr-service         Up (healthy)        0.0.0.0:8002->8002/tcp
...
```

### Manual Health Check

```bash
# PaddleOCR Service
curl http://localhost:8001/health

# GLM-OCR Service
curl http://localhost:8002/health

# API Gateway
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "paddleocr-layout-detection",
  "version": "1.0.0",
  "uptime_seconds": 3600,
  "models_loaded": true,
  "gpu_available": false
}
```

### Check Resource Usage

```bash
# View resource usage
docker stats

# View specific service
docker stats paddleocr-service glm-ocr-service
```

## Troubleshooting

### Common Issues

#### 1. Service Won't Start

**Symptom:** Service exits immediately or shows "Exited (1)"

**Solutions:**
```bash
# Check logs
docker-compose logs <service-name>

# Check if port is already in use
netstat -tulpn | grep <port>

# Rebuild the service
docker-compose up -d --build <service-name>
```

#### 2. GPU Not Available

**Symptom:** GLM-OCR service fails with CUDA errors

**Solutions:**
```bash
# Verify GPU access
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi

# Check NVIDIA Container Toolkit
sudo systemctl status docker

# Verify docker-compose.yml has GPU configuration
grep -A 5 "devices:" docker-compose.yml
```

#### 3. Out of Memory

**Symptom:** Services crash with OOM errors

**Solutions:**
```bash
# Check memory usage
docker stats

# Reduce resource limits in docker-compose.yml
# Or increase system memory

# Reduce MAX_PARALLEL_REGIONS in .env
MAX_PARALLEL_REGIONS=2
```

#### 4. Model Download Fails

**Symptom:** Service stuck at "Downloading models..."

**Solutions:**
```bash
# Check internet connectivity
ping huggingface.co

# Pre-download models manually
docker-compose exec glm-ocr-service python3 -c "from transformers import AutoModel; AutoModel.from_pretrained('zai-org/GLM-OCR')"

# Check disk space
df -h
```

#### 5. Service Unhealthy

**Symptom:** Health check fails, service shows "unhealthy"

**Solutions:**
```bash
# Check service logs
docker-compose logs <service-name>

# Restart the service
docker-compose restart <service-name>

# Check if dependencies are healthy
docker-compose ps
```

#### 6. Connection Refused

**Symptom:** API Gateway can't connect to PaddleOCR/GLM-OCR

**Solutions:**
```bash
# Verify services are on same network
docker network ls
docker network inspect idep-network

# Check service URLs in .env
cat ../.env | grep SERVICE_URL

# Test connectivity
docker-compose exec api-gateway curl http://paddleocr-service:8001/health
```

### Debugging Commands

```bash
# Enter service container
docker-compose exec <service-name> bash

# View service environment
docker-compose exec <service-name> env

# Check network connectivity
docker-compose exec api-gateway ping paddleocr-service

# View Docker Compose configuration
docker-compose config

# Remove all containers and start fresh
docker-compose down -v
docker-compose up -d --build
```

### Log Locations

Logs are available through Docker:
```bash
# View logs
docker-compose logs <service-name>

# Export logs to file
docker-compose logs <service-name> > service.log

# Follow logs in real-time
docker-compose logs -f <service-name>
```

## Resource Requirements

### Per-Service Resource Allocation

| Service | CPU | Memory | GPU | Notes |
|---------|-----|--------|-----|-------|
| paddleocr-service | 2 cores | 4GB | Optional | Can use GPU if available |
| glm-ocr-service | 4 cores | 16GB | Required | Needs NVIDIA GPU with 8GB+ VRAM |
| api-gateway | 2 cores | 2GB | No | |
| temporal-worker | 2 cores | 4GB | No | |
| db (PostgreSQL) | 2 cores | 4GB | No | |
| redis | 1 core | 2GB | No | |
| minio | 2 cores | 4GB | No | |
| temporal | 2 cores | 4GB | No | |
| triton | 4 cores | 16GB | Required | Shares GPU with glm-ocr-service |

**Total Requirements:**
- CPU: 21+ cores
- RAM: 56GB+
- GPU: 1x NVIDIA GPU with 8GB+ VRAM
- Disk: 50GB+ (100GB recommended)

### Scaling Recommendations

**For Higher Throughput:**
- Increase `MAX_PARALLEL_REGIONS` in .env
- Scale PaddleOCR service: `docker-compose up -d --scale paddleocr-service=3`
- Add load balancer (nginx) in front of services

**For Lower Resource Usage:**
- Reduce `MAX_PARALLEL_REGIONS` to 2-3
- Set `CACHE_LAYOUT_RESULTS=true` to reduce redundant processing
- Use CPU mode for PaddleOCR: `PADDLEOCR_USE_GPU=false`

## Monitoring

### Prometheus Metrics

Access Prometheus at http://localhost:9090

Key metrics:
- Request latency: `http_request_duration_seconds`
- Error rate: `http_requests_total{status="5xx"}`
- GPU utilization: `gpu_utilization_percent`

### Grafana Dashboards

Access Grafana at http://localhost:3000
- Username: `admin`
- Password: `idep-admin`

### Jaeger Tracing

Access Jaeger UI at http://localhost:16686

View distributed traces for request flows across services.

## Production Deployment

### Security Checklist

- [ ] Change default passwords in .env
- [ ] Use strong JWT_SECRET
- [ ] Configure API_KEYS with secure values
- [ ] Enable TLS/SSL for external endpoints
- [ ] Restrict network access with firewall rules
- [ ] Use secrets management (Docker Secrets, Vault)
- [ ] Enable audit logging
- [ ] Regular security updates

### Performance Tuning

- [ ] Adjust resource limits based on load
- [ ] Configure connection pooling
- [ ] Enable caching with appropriate TTL
- [ ] Monitor and optimize database queries
- [ ] Use CDN for static assets
- [ ] Configure auto-scaling policies

### Backup Strategy

```bash
# Backup PostgreSQL
docker-compose exec db pg_dump -U postgres idep > backup.sql

# Backup MinIO data
docker-compose exec minio mc mirror /data /backup

# Backup Redis (if needed)
docker-compose exec redis redis-cli SAVE
```

## Support

For issues and questions:
- Check logs: `docker-compose logs -f`
- Review this documentation
- Check GitHub issues
- Contact support team

## Next Steps

After deployment:
1. Test API endpoints (see [API.md](../docs/API.md))
2. Configure monitoring alerts
3. Set up backup automation
4. Review security settings
5. Load test the system
