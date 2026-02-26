# IDEP End-to-End Testing Guide with GPU Support

Complete guide to testing the Intelligent Document Extraction Platform end-to-end with GPU acceleration on your RTX 2050.

---

## 📋 Quick Start

```powershell
# 1. Run pre-flight checks
powershell scripts\preflight_check.ps1

# 2. Run the main E2E test
powershell scripts\test_e2e_gpu.ps1

# 3. (Optional) Run Python advanced testing for metrics
python scripts\test_e2e_advanced.py --limit 5 --output results.json
```

---

## 🔧 Prerequisites

### Hardware
- **GPU**: NVIDIA RTX 2050 (or any CUDA-capable GPU)
- **CPU**: 4+ cores recommended
- **RAM**: 16GB minimum
- **Storage**: 20GB free for Docker images & cache

### Software
- **Docker Desktop**: 4.x+ with WSL 2 integration
- **NVIDIA Container Toolkit**: Latest
- **NVIDIA Driver**: 535+
- **PowerShell**: 5.1+
- **Python**: 3.9+ (optional, for advanced testing)
- **Go**: 1.22+ (optional, for local builds)

---

## ✅ Verification Steps

### Step 1: Verify NVIDIA GPU in Docker

```powershell
docker run --rm --gpus all nvidia/cuda:12.2.2-base-ubuntu22.04 nvidia-smi
```

**Expected Output:**
```
+-------------------------+
| NVIDIA-SMI 535.x        |
|                         |
| RTX 2050    10GB        |
+-------------------------+
```

If this fails:
1. Check Docker Desktop **Settings → Resources → WSL Integration**
2. Ensure GPU is enabled in Docker: **Settings → General → "Use WSL 2 based engine"**
3. Install NVIDIA Container Toolkit: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html

### Step 2: Verify Workspace Structure

```bash
# From workspace root
ls services/api-gateway/main.go
ls services/triton-models/glm_ocr/1/model.py
ls testfiles/*.pdf
```

All three should exist.

---

## 🚀 Running Tests

### Option 1: Quick Pre-Flight Check (2 minutes)

```powershell
powershell scripts\preflight_check.ps1
```

This verifies:
- ✅ Docker is installed and running
- ✅ GPU is accessible from Docker
- ✅ All required ports are free
- ✅ Test files exist
- ✅ Workspace structure is correct

### Option 2: Full E2E Test with GPU (15-30 minutes)

```powershell
powershell scripts\test_e2e_gpu.ps1
```

This will:
1. **Start Services**: Docker Compose with GPU support
   - API Gateway (Go/Gin)
   - Temporal Worker
   - Preprocessing Service
   - Postprocessing Service
   - Triton Inference Server (GPU)
   - PostgreSQL, Redis, MinIO
   - Prometheus, Grafana, Jaeger

2. **Verify Health**: Wait for all services to be ready
   
3. **Test Upload**: Single document with GPU OCR
   - Uses first PDF from testfiles/
   - Requests: `json,structured` formats
   - Options: `include_coordinates=true`, `enhance=true`, `deskew=true`

4. **Monitor Job**: Polls job status until completion
   - Shows progress every 5 seconds
   - Timeout: 5 minutes

5. **Retrieve Results**: Downloads extracted data
   - Saves to: `testfiles/.results/result_TIMESTAMP.json`
   - Shows summary: document type, pages, text length, tables, confidence

6. **GPU Metrics**: Checks Triton GPU utilization
   - CPU/Memory usage per container
   - GPU memory consumption

7. **Batch Test**: (Optional) Tests 3 PDFs in batch mode

**Expected Timeline:**
- Startup: 60-90 seconds (pulling images, initializing services)
- First upload: 5-10 seconds
- Processing: 30-120 seconds (depends on document size & model)
- Total: ~15-30 minutes

### Option 3: Advanced Python Testing (For Metrics)

```powershell
python scripts\test_e2e_advanced.py `
  --testfiles testfiles `
  --limit 5 `
  --batch `
  --output testfiles/.results/metrics.json
```

**Features:**
- Detailed timing metrics (upload, processing, average)
- Result analysis (document type, tables, confidence)
- Batch upload testing
- JSON results export
- Color-coded logging

**Output Example:**
```
[SUCCESS] Upload complete in 3.45s (Job: abc-123-...)
[INFO] Status: PROCESSING (elapsed: 45.2s)
[SUCCESS] Job completed in 87.34s
[METRIC] Result Analysis for invoice.pdf:
  - Document Type: invoice
  - Pages: 2
  - Text Extracted: 2847 chars
  - Tables Found: 1
  - Confidence: 94.32%
```

---

## 📊 Monitoring & Observability

While tests are running, open these dashboards:

### API Gateway Health
```
http://localhost:8000/health
```

### Temporal Workflows
```
http://localhost:8080
```
- View workflow details
- See task queue progress
- Check worker status

### Grafana Dashboards
```
http://localhost:3000
```
- Username: `admin`
- Password: `idep-admin`
- Add Prometheus data source: `http://prometheus:9090`
- View GPU metrics

### Prometheus Metrics
```
http://localhost:9090
```
- Query: `nvidia_gpu_memory_used_mb`
- Query: `triton_inference_request_duration_us`
- Query: `idep_api_requests_total`

### Jaeger Tracing
```
http://localhost:16686
```
- View distributed traces
- See service dependencies
- Check latency breakdowns

### MinIO Object Storage
```
http://localhost:9001
```
- Username: `minioadmin`
- Password: `minioadmin`
- Browse: `idep-documents` bucket

---

## 📝 Understanding Results

### Result JSON Structure

```json
{
  "job_id": "abc-123-...",
  "status": "COMPLETED",
  "document_type": "invoice",
  "pages": 2,
  "confidence": 0.94,
  "text_content": "Invoice No. 123...",
  "json_data": {
    "customer": "...",
    "items": [...]
  },
  "tables": [
    {
      "headers": [...],
      "rows": [...]
    }
  ],
  "layout": {
    "blocks": [...]
  }
}
```

### Key Fields
- `job_id`: Unique job identifier
- `status`: PROCESSING, COMPLETED, FAILED
- `document_type`: invoice, receipt, form, letter, contract, etc.
- `confidence`: 0-1, per-document confidence
- `text_content`: Extracted text with layout preserved
- `json_data`: Structured fields (customer, items, etc.)
- `tables`: Extracted tables with headers and rows
- `layout`: Bounding boxes and spatial information

---

## 🐛 Troubleshooting

### GPU Not Available

**Symptom:** Test fails with "GPU not accessible"

**Solution:**
```powershell
# 1. Check Docker settings
docker run --rm --gpus all nvidia/cuda:12.2.2-base-ubuntu22.04 nvidia-smi

# 2. If fails, enable in Docker Desktop:
#    Settings → Resources → WSL Integration → Enable WSL distro
#    Settings → General → "Use WSL 2 based engine" ✓

# 3. Restart Docker Desktop

# 4. Test again
docker run --rm --gpus all nvidia/cuda:12.2.2-base-ubuntu22.04 nvidia-smi
```

### Services Not Starting

**Symptom:** Containers exit immediately

**Solution:**
```powershell
# Check logs
docker-compose -f docker/docker-compose.yml logs api-gateway
docker-compose -f docker/docker-compose.yml logs triton

# Common issues:
# 1. Port conflicts → Stop other services: docker stop $(docker ps -q)
# 2. OOM → Increase Docker memory (Settings → Resources → Memory)
# 3. GPU memory → No other GPU apps running

# Reset everything
docker-compose -f docker/docker-compose.yml down -v
docker system prune -a
docker-compose -f docker/docker-compose.yml up --build -d
```

### API Gateway Unreachable

**Symptom:** `curl http://localhost:8000/health` fails

**Solution:**
```powershell
# 1. Check if container is running
docker ps -a | findstr "api-gateway"

# 2. Check logs
docker-compose -f docker/docker-compose.yml logs api-gateway

# 3. Wait longer (services take 60-90 seconds)
# 4. Check port 8000 is not in use: netstat -ano | findstr :8000
```

### Job Processing Timeout

**Symptom:** Job stays in PROCESSING after 5 minutes

**Solution:**
```powershell
# 1. Check Triton logs
docker-compose -f docker/docker-compose.yml logs triton

# 2. Check GPU usage
docker stats triton

# 3. Check CPU usage
docker stats temporal-worker

# Common issues:
# 1. Model still downloading → Wait 5+ minutes first time
# 2. Out of VRAM → Reduce batch size
# 3. Worker not connected → Check Temporal logs
#    docker-compose -f docker/docker-compose.yml logs temporal-worker
```

### High Memory Usage

**Symptom:** Docker using 8GB+ RAM

**Solution:**
```powershell
# This is normal! GLM is a 9B parameter model
# Requires: ~18GB VRAM (GPU) + ~8GB system RAM

# If constrained:
# 1. Reduce Temporal workers
# 2. Disable Prometheus/Grafana (remove from compose)
# 3. Use smaller test documents

# Check memory per container
docker stats --no-stream | sort -k3 -hr
```

### File Upload Error

**Symptom:** 400 Bad Request on upload

**Solution:**
```powershell
# Check file
if (Test-Path testfiles/yourfile.pdf) { "OK" } else { "Missing" }

# Verify format
file testfiles/yourfile.pdf  # Should be: PDF document

# Check format parameters
# Use only: text, json, markdown, table, key_value, structured
```

---

## 🎯 GPU Optimization Tips

### 1. Monitor GPU Usage

```powershell
# During test, in another terminal
docker exec idep-triton nvidia-smi -l 1
```

Should show:
- Memory Usage: 8-18GB (normal for GLM)
- GPU-Util: 80-95% (during processing)
- Temp: 50-75°C (healthy range)

### 2. Batch Processing

If processing single files slowly, batch multiple files:

```powershell
curl -X POST http://localhost:8000/jobs/batch `
  -H "Authorization: Bearer tp-proj-dev-key-123" `
  -F "documents=@file1.pdf" `
  -F "documents=@file2.pdf" `
  -F "documents=@file3.pdf" `
  -F "output_formats=json"
```

Triton's dynamic batching benefits from 3-5 parallel requests.

### 3. Reduce Latency

```powershell
# Pre-warm model (send dummy request)
curl -X POST http://localhost:8000/jobs/upload `
  -H "Authorization: Bearer tp-proj-dev-key-123" `
  -F "document=@testfiles/small.pdf"

# Next request will be faster (model cached)
```

---

## 📈 Expected Performance

### Single Document (2-page PDF)

| Metric | Expected | Your RTX 2050 |
|--------|----------|--------------|
| Upload Time | 3-5s | ~3-5s |
| Processing Time | 20-60s | ~20-40s |
| Total Time | 30-70s | ~25-50s |
| GPU Memory | ~18GB | ~18GB |
| GPU Util | 85-95% | 85-95% |
| Output Size | 20-50KB | 20-50KB |

### Batch Processing (5 files)

| Metric | With Batching | Individual |
|--------|---------------|-----------|
| Upload Time | 10s | 25s |
| Processing Time | 60s (parallelized) | 200s (sequential) |
| Total Time | 75s | 230s |
| GPU Util | 95%+ | 85-90% |

---

## 🔐 API Key Configuration

The default API key is **`tp-proj-dev-key-123`**.

To change:
1. Edit `docker/docker-compose.yml`
2. Update `api-gateway` environment: `API_KEYS=your-key:admin`
3. Restart: `docker-compose -f docker/docker-compose.yml restart api-gateway`

---

## 📚 Test Files

The `testfiles/` directory contains sample PDFs:
- **Invoices** (2-3 pages, structured)
- **Insurance Documents** (longer, complex layout)
- **Bank Statements** (tables, multiple columns)

For best results:
- Use 1-10 page PDFs
- Include mix of structured/unstructured
- Test with 300-600 DPI scans (optimal for OCR)

---

## 🛑 Stopping Services

```powershell
# Stop all containers
docker-compose -f docker/docker-compose.yml stop

# Stop and remove (keeps data)
docker-compose -f docker/docker-compose.yml down

# Stop and remove everything (cleanup)
docker-compose -f docker/docker-compose.yml down -v
docker system prune -a
```

---

## 📞 Support

### Common Commands

```powershell
# View all logs
docker-compose -f docker/docker-compose.yml logs -f

# View specific service
docker-compose -f docker/docker-compose.yml logs -f triton

# Check service status
docker-compose -f docker/docker-compose.yml ps

# Restart a service
docker-compose -f docker/docker-compose.yml restart triton

# View resource usage
docker stats

# Enter container shell
docker exec -it idep-api-gateway /bin/ash
docker exec -it idep-triton /bin/bash
```

### Useful Queries

```powershell
# Find running containers
docker ps | findstr "api-gateway\|triton\|temporal"

# Check port usage
netstat -ano | findstr ":8000"

# View network
docker network ls
docker network inspect idep_default
```

---

## 🎓 Next Steps

1. **Review Results**: Check `testfiles/.results/` for OCR output
2. **Inspect Traces**: Open http://localhost:16686 for distributed tracing
3. **Custom Documents**: Add your own PDFs to `testfiles/` and re-run
4. **Adjust Parameters**: Edit options in `test_e2e_gpu.ps1` for different extraction modes
5. **Production Deployment**: See `prompt.md` for AWS GPU deployment

---

**Happy Testing! 🚀**
