# Real-Time Document Extraction Guide

## 🎯 Overview

You now have TWO scripts:

1. **`demo_interactive.py`** - Mock demo with sample data (for presentations)
2. **`real_extraction.py`** - Real extraction using actual API (for real documents)

---

## 🚀 Quick Start - Real Extraction

### Step 1: Start the API Services

```bash
# Start all services
docker-compose -f docker/docker-compose.yml up -d

# Wait 30-60 seconds for services to start

# Check if services are running
curl http://localhost:8000/health
```

### Step 2: Run Real Extraction

```bash
# Basic extraction
python real_extraction.py --document "testfiles\your_file.pdf"

# With all options
python real_extraction.py --document "testfiles\your_file.pdf" --formats json,table --coordinates yes
```

---

## 📋 Real Extraction Commands

### Basic Usage
```bash
python real_extraction.py --document FILE [OPTIONS]
```

### Options

| Option | Values | Description |
|--------|--------|-------------|
| `--document` | file path | **Required** - Path to your document |
| `--formats` | text,json,markdown,table,key_value,structured | Output formats |
| `--fields` | field names | Specific fields to extract |
| `--coordinates` | yes/no | Include bounding boxes |
| `--word-confidence` | yes/no | Word-level confidence |
| `--granularity` | block/line/word | Detail level |
| `--api-url` | URL | API endpoint (default: http://localhost:8000) |
| `--api-key` | key | API key (default: tp-proj-dev-key-123) |

### Examples

**Basic extraction:**
```bash
python real_extraction.py --document "testfiles\invoice.pdf"
```

**JSON with coordinates:**
```bash
python real_extraction.py --document "testfiles\invoice.pdf" --formats json --coordinates yes
```

**Specific fields:**
```bash
python real_extraction.py --document "testfiles\invoice.pdf" --formats json --fields invoice_number,date,total_amount
```

**Multiple formats:**
```bash
python real_extraction.py --document "testfiles\invoice.pdf" --formats json,table,markdown --coordinates yes
```

**Your PDF with spaces in name:**
```bash
python real_extraction.py --document "testfiles\Mr.P.Vaidyanathan Rs.4,95,000.pdf" --formats json --coordinates yes
```

---

## 🔧 Starting the Services

### Option 1: Docker Compose (Recommended)

```bash
# Start all services
docker-compose -f docker/docker-compose.yml up -d

# Check status
docker-compose -f docker/docker-compose.yml ps

# View logs
docker-compose -f docker/docker-compose.yml logs -f

# Stop services
docker-compose -f docker/docker-compose.yml down
```

### Option 2: Check Service Status

```bash
# Check API Gateway
curl http://localhost:8000/health

# Check if services are responding
python check_services_status.py
```

---

## 📊 What You Get

### Real Extraction Output

The script will:
1. ✅ Upload your document to the API
2. ✅ Wait for processing to complete
3. ✅ Retrieve the actual extraction result
4. ✅ Display the extracted data
5. ✅ Save result to `extraction_results/` folder

### Output File

Results saved to: `extraction_results/extraction_JOBID_TIMESTAMP.json`

Contains:
- **Actual extracted text** from your PDF
- **Real field values** detected by the OCR
- **Actual confidence scores** from the model
- **Real bounding boxes** if requested
- **Processing statistics**

---

## 🆚 Demo vs Real Extraction

### Demo Script (`demo_interactive.py`)

✅ **Use for:**
- Manager presentations
- Quick demos
- Showing API format
- No setup required

❌ **Limitations:**
- Uses sample data
- Not real extraction
- Same output every time

### Real Extraction (`real_extraction.py`)

✅ **Use for:**
- Actual document processing
- Real data extraction
- Testing with your PDFs
- Production use

❌ **Requirements:**
- Services must be running
- Requires Docker
- Takes longer (real processing)

---

## 🔍 Troubleshooting

### Error: "API is not available"

**Problem:** Services are not running

**Solution:**
```bash
# Start services
docker-compose -f docker/docker-compose.yml up -d

# Wait 30-60 seconds

# Check health
curl http://localhost:8000/health
```

### Error: "File not found"

**Problem:** Path has spaces or incorrect

**Solution:**
```bash
# Use quotes around path
python real_extraction.py --document "testfiles\file with spaces.pdf"

# Or use relative path
python real_extraction.py --document "testfiles\invoice.pdf"
```

### Error: "Upload failed"

**Problem:** API key or endpoint incorrect

**Solution:**
```bash
# Check API key
python real_extraction.py --document file.pdf --api-key tp-proj-dev-key-123

# Check endpoint
python real_extraction.py --document file.pdf --api-url http://localhost:8000
```

### Job stuck in PROCESSING

**Problem:** Service issue or large file

**Solution:**
- Wait longer (can take 30-60 seconds for large PDFs)
- Check service logs: `docker-compose -f docker/docker-compose.yml logs -f`
- Restart services if needed

---

## 📝 Complete Workflow

### 1. Start Services (One Time)
```bash
docker-compose -f docker/docker-compose.yml up -d
```

### 2. Extract Your Document
```bash
python real_extraction.py --document "testfiles\your_file.pdf" --formats json --coordinates yes
```

### 3. Check Results
```bash
# Results saved to extraction_results/
ls extraction_results
```

### 4. Stop Services (When Done)
```bash
docker-compose -f docker/docker-compose.yml down
```

---

## 🎬 For Your Manager Demo

### Option A: Use Demo Script (Recommended)
- Fast, reliable, professional
- No technical issues
- Consistent results
```bash
python demo_interactive.py --document file.pdf --formats json --coordinates yes
```

### Option B: Use Real Extraction
- Shows actual processing
- Real data from PDFs
- More impressive but riskier
```bash
# Make sure services are running first!
python real_extraction.py --document "testfiles\invoice.pdf" --formats json --coordinates yes
```

---

## 💡 Pro Tips

1. **Test before demo:** Run real extraction on your test files first
2. **Have backup:** Keep demo script ready if services fail
3. **Start services early:** Give them time to warm up
4. **Use simple files:** Start with small, clear PDFs
5. **Check logs:** Monitor service logs during demo

---

## 🆘 Quick Help

```bash
# Get help
python real_extraction.py --help

# Check if services are running
curl http://localhost:8000/health

# View service logs
docker-compose -f docker/docker-compose.yml logs -f api-gateway

# Restart services
docker-compose -f docker/docker-compose.yml restart
```

---

## ✅ Ready to Extract!

**Test command:**
```bash
python real_extraction.py --document "testfiles\test_invoice_local.png" --formats json
```

**Your PDF:**
```bash
python real_extraction.py --document "testfiles\Mr.P.Vaidyanathan Rs.4,95,000.pdf" --formats json,table --coordinates yes
```

Good luck! 🚀
