# GLM-OCR Standalone Testing (No Docker)

Test the GLM-OCR model directly without Docker/Triton infrastructure.

## Prerequisites

1. **Python 3.10+** with required packages:
   ```bash
   pip install torch torchvision transformers pillow numpy
   ```

2. **NVIDIA GPU** with CUDA support (RTX 2050 in your case)

3. **GPU drivers** installed and working

## Quick Test

### Run Comprehensive Test Suite

```bash
python test_standalone_api.py --test
```

This will:
- ✅ Initialize the GLM-OCR model on GPU
- ✅ Test JSON extraction
- ✅ Test custom prompts
- ✅ Test all output formats (text, json, markdown, table, key_value, structured)
- ✅ Test high precision mode
- ✅ Test field extraction
- ✅ Show GPU memory usage

### Expected Output

```
================================================================================
GLM-OCR Standalone API Test
================================================================================

Initializing GLM-OCR model...
CUDA available: True
GPU: NVIDIA GeForce RTX 2050
Memory: 4.00 GB
✅ Model initialized in 145.41s
   Device: cuda
   MOCK mode: False
   Model loaded: True
   Processor loaded: True

Using test file: test_invoice_local.png

[Test 1] JSON Format with Coordinates
----------------------------------------
✅ Success
   Processing time: 3200ms
   Confidence: 0.9300
   Device: cuda
   Mode: NATIVE

Result preview:
{
  "document_type": "invoice",
  "fields": {
    "invoice_number": "INV-2026-0042",
    "date": "2026-02-25",
    "total_amount": "$1,358.02"
  }
}...

[Test 2] Custom Prompt
----------------------------------------
✅ Success
   Processing time: 2800ms

[Test 3] All Output Formats
----------------------------------------
   text         - ✅ OK (2500ms)
   json         - ✅ OK (3100ms)
   markdown     - ✅ OK (2900ms)
   table        - ✅ OK (2700ms)
   key_value    - ✅ OK (2600ms)
   structured   - ✅ OK (3500ms)

[Test 4] High Precision Mode
----------------------------------------
✅ Success
   Processing time: 3800ms
   Confidence: 0.9500

[Test 5] Field Extraction
----------------------------------------
✅ Success
   Extracted fields: ['invoice_number', 'date', 'total_amount']

[GPU Statistics]
----------------------------------------
   Device: NVIDIA GeForce RTX 2050
   Allocated: 2.10 GB
   Reserved: 2.50 GB
   Total: 4.00 GB
   Usage: 52.5%

================================================================================
✅ All tests completed!
================================================================================
```

## Single Document Extraction

### Basic JSON Extraction

```bash
python test_standalone_api.py \
  --input test_invoice_local.png \
  --format json \
  --output result.json
```

### With Coordinates

```bash
python test_standalone_api.py \
  --input test_invoice_local.png \
  --format json \
  --coordinates \
  --output result.json
```

### Custom Prompt

```bash
python test_standalone_api.py \
  --input test_invoice_local.png \
  --prompt "Extract invoice number, date, and total amount as JSON" \
  --output result.json
```

### High Precision Mode

```bash
python test_standalone_api.py \
  --input test_invoice_local.png \
  --format json \
  --precision high \
  --coordinates \
  --output result.json
```

### Extract Specific Fields

```bash
python test_standalone_api.py \
  --input test_invoice_local.png \
  --format json \
  --fields "invoice_number,date,total_amount" \
  --output result.json
```

### All Formats

```bash
# Text
python test_standalone_api.py -i test_invoice_local.png -f text -o text_result.json

# Markdown
python test_standalone_api.py -i test_invoice_local.png -f markdown -o md_result.json

# Table
python test_standalone_api.py -i test_invoice_local.png -f table -o table_result.json

# Key-Value
python test_standalone_api.py -i test_invoice_local.png -f key_value -o kv_result.json

# Structured (all formats combined)
python test_standalone_api.py -i test_invoice_local.png -f structured --coordinates -o full_result.json
```

## Command Line Options

```
usage: test_standalone_api.py [-h] [--test] [--input INPUT] [--output OUTPUT]
                              [--format {text,json,markdown,table,key_value,structured}]
                              [--coordinates] [--word-confidence]
                              [--prompt PROMPT]
                              [--precision {normal,high,precision}]
                              [--fields FIELDS]

Options:
  --test                Run comprehensive test suite
  --input, -i          Input image/document path
  --output, -o         Output JSON file path
  --format, -f         Output format (default: json)
  --coordinates        Include bounding boxes
  --word-confidence    Include per-word confidence scores
  --prompt, -p         Custom extraction prompt
  --precision          Precision mode: normal, high, or precision
  --fields             Comma-separated list of fields to extract
```

## Test with Real Documents

```bash
# Test with PDF
python test_standalone_api.py \
  --input testfiles/Jio_Rs_730.pdf \
  --format json \
  --coordinates \
  --output jio_result.json

# Test with another invoice
python test_standalone_api.py \
  --input "testfiles/HDFC Ergo General Insurance Limited Rs.6,218.pdf" \
  --format structured \
  --coordinates \
  --word-confidence \
  --output hdfc_result.json
```

## Verify GPU Usage

While the test is running, open another terminal and check GPU usage:

```bash
# Windows
nvidia-smi

# Or watch in real-time
nvidia-smi -l 1
```

Expected: You should see ~2-3 GB GPU memory used by the Python process.

## Result Format

The standalone API returns results in the same format as the Docker API:

```json
{
  "model": "glm-ocr",
  "processing_time_ms": 3200,
  "document_confidence": 0.93,
  "page_count": 1,
  "mode": "NATIVE",
  "device": "cuda",
  "result": {
    "document_type": "invoice",
    "fields": {
      "invoice_number": "INV-2026-0042",
      "date": "2026-02-25",
      "vendor": "Acme Corp",
      "total_amount": "$1,358.02"
    },
    "line_items": [
      {
        "description": "Widget A",
        "quantity": 10,
        "unit_price": "$100.00",
        "total": "$1,000.00"
      }
    ]
  }
}
```

## Troubleshooting

### CUDA Out of Memory

If you get OOM errors:

```bash
# The model will automatically fall back to CPU
# Check the logs for "Falling back to CPU" message
```

### Model Download Issues

First run will download the model (~2GB):

```bash
# Model downloads to: ~/.cache/huggingface/hub/
# Make sure you have internet connection and ~5GB free space
```

### Import Errors

```bash
# Install missing packages
pip install torch torchvision transformers pillow numpy

# For GPU support, install CUDA-enabled PyTorch:
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

### Slow Initialization

First initialization takes 2-3 minutes:
- Model download: ~1 minute
- Model loading: ~2 minutes
- Subsequent runs are faster (model cached)

## Performance Comparison

| Mode | Device | Init Time | Inference Time | Memory |
|------|--------|-----------|----------------|--------|
| NATIVE | GPU (RTX 2050) | 145s | 2-4s | 2.1 GB |
| NATIVE | CPU | 60s | 30-60s | 4 GB RAM |
| MOCK | N/A | <1s | <0.1s | <100 MB |

## Differences from Docker API

### Standalone (No Docker)
- ✅ Direct model access
- ✅ Faster for single documents
- ✅ No Docker overhead
- ✅ Easier debugging
- ❌ No workflow orchestration
- ❌ No batch processing
- ❌ No preprocessing pipeline
- ❌ No PII redaction

### Docker API
- ✅ Full workflow (preprocessing → OCR → postprocessing)
- ✅ Batch processing
- ✅ PII redaction
- ✅ Image enhancement
- ✅ Archive extraction
- ✅ Temporal workflow management
- ❌ More complex setup
- ❌ Docker overhead

## When to Use Standalone

Use standalone testing when:
- Testing model fixes quickly
- Debugging model behavior
- Developing new features
- Running single document extractions
- No need for preprocessing/postprocessing

Use Docker API when:
- Production deployment
- Batch processing
- Need preprocessing (deskew, enhance)
- Need postprocessing (PII redaction)
- Need workflow management

## Next Steps

1. **Run the comprehensive test:**
   ```bash
   python test_standalone_api.py --test
   ```

2. **Test with your documents:**
   ```bash
   python test_standalone_api.py -i your_document.pdf -f json --coordinates -o result.json
   ```

3. **Check GPU usage:**
   ```bash
   nvidia-smi
   ```

4. **Compare with Docker API:**
   - Standalone: Direct model testing
   - Docker: Full production workflow

## Summary

✅ Standalone testing provides:
- Direct model access without Docker
- Fast iteration for development
- Easy debugging
- Same model behavior as Docker deployment
- GPU acceleration (2.10 GB memory usage)
- All output formats supported
- Custom prompts supported

The model works identically in both standalone and Docker modes!
