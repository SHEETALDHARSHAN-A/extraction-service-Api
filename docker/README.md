# Docker Configuration

This directory contains Docker Compose configuration for the PaddleOCR Microservice Architecture.

## Files

- **docker-compose.yml** - Main production configuration
- **docker-compose.override.yml** - Development overrides (auto-loaded)
- **DEPLOYMENT.md** - Comprehensive deployment guide
- **prometheus.yml** - Prometheus monitoring configuration
- **triton.Dockerfile** - Triton Inference Server Dockerfile

## Quick Start

```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f

# Stop all services
docker-compose down
```

## Services

### Core Services
- **api-gateway** (8000) - Main API endpoint
- **paddleocr-service** (8001) - Layout detection
- **glm-ocr-service** (8002) - Content extraction
- **temporal-worker** - Background job processing

### Infrastructure
- **db** (5432) - PostgreSQL database
- **redis** (6379) - Cache
- **minio** (9000, 9001) - Object storage
- **temporal** (7233, 8080) - Workflow engine
- **triton** (18000, 8001, 8002) - ML serving

### Observability
- **prometheus** (9090) - Metrics
- **grafana** (3000) - Dashboards
- **jaeger** (16686) - Tracing

## Configuration

1. Copy environment file:
   ```bash
   cp ../.env.example ../.env
   ```

2. Edit `.env` with your settings

3. Key variables:
   - `PADDLEOCR_USE_GPU` - Enable GPU for PaddleOCR
   - `ENABLE_LAYOUT_DETECTION` - Enable two-stage pipeline
   - `CACHE_LAYOUT_RESULTS` - Cache layout detection
   - `MAX_PARALLEL_REGIONS` - Parallel processing limit

## Development Mode

Development mode is enabled by default using `docker-compose.override.yml`:

- Hot-reloading for code changes
- Debug logging enabled
- Development tools included (Redis Commander, Adminer)

To disable development mode:
```bash
docker-compose -f docker-compose.yml up -d
```

## GPU Support

GLM-OCR service requires NVIDIA GPU with CUDA support.

**Prerequisites:**
- NVIDIA GPU with 8GB+ VRAM
- NVIDIA Container Toolkit installed

**Verify GPU access:**
```bash
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

## Resource Requirements

**Minimum:**
- CPU: 8 cores
- RAM: 32GB
- GPU: NVIDIA GPU with 8GB VRAM
- Disk: 50GB

**Recommended:**
- CPU: 16 cores
- RAM: 64GB
- GPU: NVIDIA GPU with 12GB+ VRAM
- Disk: 100GB (SSD)

## Health Checks

All services include health checks:

```bash
# Check all services
docker-compose ps

# Manual health check
curl http://localhost:8001/health  # PaddleOCR
curl http://localhost:8002/health  # GLM-OCR
curl http://localhost:8000/health  # API Gateway
```

## Troubleshooting

### Service won't start
```bash
# Check logs
docker-compose logs <service-name>

# Rebuild
docker-compose up -d --build <service-name>
```

### GPU not available
```bash
# Verify GPU access
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi

# Check NVIDIA Container Toolkit
sudo systemctl status docker
```

### Out of memory
```bash
# Check resource usage
docker stats

# Reduce parallel processing
# Edit .env: MAX_PARALLEL_REGIONS=2
```

## Volumes

Persistent data is stored in Docker volumes:

- `postgres_data` - Database
- `redis_data` - Cache
- `minio_data` - Object storage
- `paddleocr_models` - PaddleOCR models
- `glm_models` - GLM-OCR models
- `hf_cache` - HuggingFace cache

**Backup volumes:**
```bash
docker run --rm -v paddleocr_models:/data -v $(pwd):/backup alpine tar czf /backup/paddleocr_models.tar.gz -C /data .
```

**Remove all data:**
```bash
docker-compose down -v  # WARNING: Deletes all data!
```

## Monitoring

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/idep-admin)
- **Jaeger**: http://localhost:16686
- **MinIO Console**: http://localhost:9001 (minioadmin/minioadmin)
- **Temporal UI**: http://localhost:8080

## Documentation

See [DEPLOYMENT.md](./DEPLOYMENT.md) for comprehensive deployment guide including:
- Prerequisites and installation
- Configuration details
- Troubleshooting guide
- Production deployment checklist
- Security recommendations

## Support

For issues:
1. Check logs: `docker-compose logs -f`
2. Review [DEPLOYMENT.md](./DEPLOYMENT.md)
3. Check service health: `docker-compose ps`
4. Verify configuration: `docker-compose config`
