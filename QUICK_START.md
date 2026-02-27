# 🚀 IDEP GPU Testing - Quick Start Guide
 instead of rebuilding the entire Docker image (which took 90 minutes), let me install protobuf directly in the running container 
Complete end-to-end testing with GPU support for your NVIDIA RTX 2050.

---

## ⚡ TL;DR (5 minutes)

```powershell
# 1. Verify GPU support (2 min)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\preflight_check.ps1

# 2. Run full E2E test (20 min)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\test_e2e_gpu.ps1

# 3. View results
cat testfiles\.results\result_*.json | jq .
```

---

## 📋 What's Included

I've created a complete testing suite with multiple options:

### PowerShell Scripts (Windows)
- **`scripts\preflight_check.ps1`** - GPU & Docker verification (2 min)
- **`scripts\test_e2e_gpu.ps1`** - Full E2E test with GPU (20-30 min)

### Python Scripts (Cross-platform)
- **`scripts\test_e2e_advanced.py`** - Advanced testing with metrics & analysis

### Shell Scripts (Linux/WSL)
- **`scripts\test_e2e_gpu.sh`** - Bash version of E2E test

### Helper Scripts
- **`idep.bat`** - Windows command shortcut (Windows)
- **`Makefile`** - Development commands (Linux/WSL/macOS)

### Documentation
- **`TESTING_GUIDE.md`** - Comprehensive testing & troubleshooting guide
- **`QUICK_START.md`** - This file

---

## 🎯 Getting Started (Choose One)

### Option A: Windows Users (Recommended)

```powershell
# Open PowerShell, navigate to workspace root

# 1. Pre-flight check (verify GPU access)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\preflight_check.ps1

# 2. Run E2E test
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\test_e2e_gpu.ps1

# 3. (Optional) Advanced testing with Python
python scripts\test_e2e_advanced.py --limit 5 --output results.json
```

**What to expect:**
- Startup: 60-90 seconds (pulling Docker images, initializing services)
- Single document test: 20-40 seconds (including upload + processing)
- Total: ~15-30 minutes

### Option B: Linux / WSL Users

```bash
# 1. Make script executable
chmod +x scripts/test_e2e_gpu.sh

# 2. Run E2E test
bash scripts/test_e2e_gpu.sh

# 3. Or use Makefile
make preflight
make test-linux
```

### Option C: Use Command Shortcuts (Windows)

```powershell
# Copy idep.bat to workspace root (already done)

# Then use:
idep.bat preflight
idep.bat test
idep.bat urls         # Show all service endpoints
idep.bat health       # Check service health
idep.bat logs-triton  # View Triton logs
```

---

## 🔍 Understanding the Test Flow

```
1. Verify Prerequisites
   ├─ Docker is installed & running
   ├─ GPU is accessible in Docker
   ├─ Required ports are free (8000, 8001, 6379, etc.)
   └─ testfiles directory exists with PDFs

2. Start Services (Docker Compose)
   ├─ API Gateway (Go) on :8000
   ├─ Temporal Worker (Go)
   ├─ Preprocessing Service (gRPC on :50051)
   ├─ Postprocessing Service (gRPC on :50052)
   ├─ Triton Inference Server (GPU) on :8001, :8002
   ├─ PostgreSQL, Redis, MinIO
   └─ Prometheus, Grafana, Jaeger

3. Wait for Services (60-90 seconds)
   └─ Health check API Gateway: /health

4. Test Single Document Upload
   ├─ Upload first PDF from testfiles/
   ├─ Request formats: json, structured
   ├─ Enable: coordinates, enhance, deskew
   └─ Get Job ID

5. Monitor Processing
   ├─ Poll job status every 5 seconds
   ├─ Show progress: PROCESSING → COMPLETED
   └─ Timeout after 5 minutes

6. Retrieve Results
   ├─ Download extracted data (JSON)
   ├─ Save to: testfiles/.results/result_TIMESTAMP.json
   ├─ Show summary: document type, pages, text length, tables
   └─ Check GPU usage metrics

7. Optional: Batch Upload Test
   └─ Test 3 PDFs in batch mode

8. Display Summary
   ├─ Container resource usage
   ├─ GPU metrics from Triton
   └─ Links to dashboards
```

---

## 📊 Expected Results

### Successful Test Output

```
✅ Docker is installed: Docker version 24.x+
✅ GPU is accessible in Docker
✅ Found 8 PDF files in testfiles

Starting Docker Compose services...
✅ Docker compose started.

Waiting for services to be healthy...
✅ API Gateway is healthy
✅ Temporal UI is healthy

Uploading test file: Invoice_123.pdf (2.5 MB)
✅ Document uploaded successfully
  Job ID: abc-123-def-456

Monitoring job: abc-123-def-456
[1/60] Job status: PROCESSING
[5/60] Job status: PROCESSING (elapsed: 25.2s)
[10/60] Job status: PROCESSING (elapsed: 50.5s)
✅ Job completed! (87.34s total)

✅ Results retrieved successfully
  - Document Type: invoice
  - Pages: 2
  - Text Content Length: 2847 characters
  - Tables Found: 1
  - Confidence: 94.32%

✅ Results saved to: testfiles/.results/result_20260227_143025.json
```

### Sample Result JSON

```json
{
  "job_id": "abc-123-...",
  "status": "COMPLETED",
  "document_type": "invoice",
  "pages": 2,
  "confidence": 0.9432,
  "text_content": "Invoice No. 123...",
  "json_data": {
    "customer": "John Doe Inc.",
    "items": [
      {
        "description": "Service A",
        "quantity": 2,
        "unit_price": 100.00,
        "total": 200.00
      }
    ],
    "total_amount": 200.00
  },
  "tables": [
    {
      "headers": ["Item", "Qty", "Unit Price", "Total"],
      "rows": [[...]]
    }
  ],
  "coordinates": [...]
}
```

---

## 🎯 Monitoring Dashboards

While test is running, open these in your browser:

| Dashboard | URL | Purpose |
|-----------|-----|---------|
| **Temporal Web UI** | http://localhost:8080 | View workflow execution details |
| **Grafana** | http://localhost:3000 | GPU metrics & dashboards |
| **Prometheus** | http://localhost:9090 | Query metrics (nvidia_gpu_memory_used_mb) |
| **Jaeger Tracing** | http://localhost:16686 | Distributed request tracing |
| **MinIO Console** | http://localhost:9001 | Check uploaded documents |

---

## ❌ Troubleshooting

### GPU Not Found

```powershell
# Verify GPU in Docker
docker run --rm --gpus all nvidia/cuda:12.2.2-base-ubuntu22.04 nvidia-smi

# If fails: Enable in Docker Desktop
# Settings → Resources → WSL Integration → Enable your WSL distro
# Settings → General → "Use WSL 2 based engine" ✓
```

### API Not Responding

```powershell
# Check if running
docker ps | findstr "api-gateway"

# View logs
docker-compose -f docker/docker-compose.yml logs api-gateway

# Services take 60-90 seconds to start
```

### Job Processing Timeout

```powershell
# Check Triton logs
docker-compose -f docker/docker-compose.yml logs triton

# Check GPU memory
docker exec idep-triton nvidia-smi

# First run may take longer (model downloading)
```

### Port Already in Use

```powershell
# Stop existing containers
docker-compose -f docker/docker-compose.yml down

# Or kill specific port
netstat -ano | findstr ":8000"
taskkill /PID <PID> /F
```

---

## 📝 Test Files

The `testfiles/` folder contains sample PDFs to test with:

- **Invoices** (2-3 pages, structured)
- **Insurance Documents** (larger, complex layout)
- **Bank Statements** (tables, multiple columns)

All are real-world examples that test different extraction capabilities.

---

## ⚙️ Configuration

### Adjust Test Options

Edit `scripts\test_e2e_gpu.ps1` line ~190:

```powershell
$uploadResponse = Invoke-WebRequest ... `
    -Form @{
        document = $testFile
        output_formats = "json,structured"      # Change formats here
        include_coordinates = "true"             # Enable bounding boxes
        include_word_confidence = "false"        # Per-word scores
        deskew = "true"                         # Auto-straighten
        enhance = "true"                        # Preprocessing
        redact_pii = "false"                    # Redact sensitive info
    }
```

### Change API Key

Edit `.env` or `docker/docker-compose.yml`:

```bash
API_KEYS=your-custom-key:admin
```

---

## 🏃 Running Custom Documents

1. Copy your PDFs to `testfiles/` folder
2. Run the test script
3. Results saved to `testfiles/.results/`

```powershell
# Single file
cp "C:\My Documents\my_document.pdf" testfiles\

# Batch of files
cp "C:\Documents\*.pdf" testfiles\

# Run test
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\test_e2e_gpu.ps1
```

---

## 🛑 Stopping Everything

```powershell
# Stop services (keeps data)
docker-compose -f docker/docker-compose.yml stop

# Stop and remove (removes data)
docker-compose -f docker/docker-compose.yml down

# Full cleanup
docker-compose -f docker/docker-compose.yml down -v
docker system prune -a
```

---

## 📚 Next Steps

1. **Review Results**: `testfiles/.results/result_*.json`
2. **Check Logs**: `docker-compose -f docker/docker-compose.yml logs -f`
3. **Monitor GPU**: `docker exec idep-triton nvidia-smi -l 1`
4. **Test with Your Docs**: Add PDFs to `testfiles/` and rerun
5. **Adjust Settings**: Modify upload options for different extraction modes

---

## 📖 Full Documentation

For comprehensive details, troubleshooting, and advanced usage:

👉 **See [TESTING_GUIDE.md](TESTING_GUIDE.md)**

---

## 💡 Pro Tips

### Speed Up Testing
```powershell
# Skip waiting for all services, just wait for API
# Edit test_e2e_gpu.ps1 line 180, remove Temporal check
```

### Monitor GPU Real-time
```powershell
# In another terminal during test
docker exec idep-triton nvidia-smi -l 1
```

### Batch Multiple Documents
```python
python scripts/test_e2e_advanced.py --limit 10 --batch --output results.json
```

### View Request/Response Details
```powershell
# Enable verbose logging
$DebugPreference = "Continue"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\test_e2e_gpu.ps1
```

---

## ✨ Success!

If you see ✅ at the end of the test, you have:

✅ **GPU working** in Docker containers  
✅ **Full microservice stack** running  
✅ **GLM-OCR model** performing inference on GPU  
✅ **Temporal workflows** orchestrating complex pipelines  
✅ **Complete E2E testing** validation  

You're ready for:
- Production deployment to AWS GPU clusters
- Custom document processing
- Advanced extraction configurations
- Integration with external systems

---

## 🤝 Support

**Issue with test?**
1. Run `preflight_check.ps1` first
2. Check logs: `docker-compose logs <service>`
3. Review [TESTING_GUIDE.md](TESTING_GUIDE.md) troubleshooting section

**Need help?**
- Check Temporal UI: http://localhost:8080
- Check logs: `docker-compose -f docker/docker-compose.yml logs -f`
- Review error messages carefully

---

**Ready to test? Run:**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\test_e2e_gpu.ps1
```

**Happy Testing! 🚀**
