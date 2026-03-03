# GLM-OCR Service

FastAPI-based service for region-based content extraction using GLM-OCR vision-language model.

## Features

- **Region-based extraction**: Extract content from cropped image regions
- **Batch processing**: Process multiple regions in a single request
- **Region-type-specific prompts**: Optimized prompts for text, table, formula, etc.
- **Input validation**: Comprehensive validation of requests
- **Logging and monitoring**: Structured JSON logging with request tracking
- **GPU support**: Automatic GPU detection with CPU fallback

## API Endpoints

### Health Check
```
GET /health
```

Returns service status and model availability.

### Extract Single Region
```
POST /extract-region
```

Extract content from a single image region.

**Request:**
```json
{
  "image": "base64_encoded_image",
  "region_type": "text",
  "prompt": "Text Recognition:",
  "options": {
    "max_tokens": 2048,
    "output_format": "text"
  }
}
```

**Response:**
```json
{
  "content": "Extracted text content",
  "confidence": 0.95,
  "processing_time_ms": 1500,
  "tokens_used": {
    "prompt": 100,
    "completion": 200
  }
}
```

### Extract Multiple Regions (Batch)
```
POST /extract-regions-batch
```

Extract content from multiple regions in batch.

**Request:**
```json
{
  "regions": [
    {
      "region_id": "region_0",
      "image": "base64_encoded_image",
      "region_type": "text"
    },
    {
      "region_id": "region_1",
      "image": "base64_encoded_image",
      "region_type": "table"
    }
  ],
  "options": {
    "max_tokens": 2048
  }
}
```

**Response:**
```json
{
  "results": [
    {
      "region_id": "region_0",
      "content": "Extracted content",
      "confidence": 0.95,
      "error": null
    },
    {
      "region_id": "region_1",
      "content": "Table data",
      "confidence": 0.92,
      "error": null
    }
  ],
  "total_processing_time_ms": 3000,
  "tokens_used": {
    "prompt": 200,
    "completion": 400
  }
}
```

## Region Types

Supported region types:
- `text` - Plain text blocks
- `table` - Tabular data
- `formula` - Mathematical formulas
- `title` - Document titles
- `figure` - Images and charts
- `caption` - Figure/table captions
- `header` - Page headers
- `footer` - Page footers

## Configuration

Environment variables:

- `GLM_MODEL_PATH` - Model path or HuggingFace ID (default: "zai-org/GLM-OCR")
- `GLM_PRECISION_MODE` - Inference precision (default: "normal")
- `CUDA_VISIBLE_DEVICES` - GPU device ID
- `LOG_LEVEL` - Logging level (default: "INFO")
- `MAX_BATCH_SIZE` - Maximum batch size (default: 10)

## Running the Service

### Using Docker

```bash
docker build -t glm-ocr-service .
docker run -p 8002:8002 --gpus all glm-ocr-service
```

### Using Python

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8002
```

## Testing

Run unit tests:
```bash
pytest tests/ -v
```

Run with coverage:
```bash
pytest tests/ --cov=app --cov-report=html
```

## Architecture

The service consists of:

1. **FastAPI Application** (`app/main.py`) - HTTP API endpoints
2. **Inference Engine** (`app/glm_inference.py`) - GLM-OCR model wrapper
3. **Pydantic Models** (`app/models.py`) - Request/response validation
4. **Prompt Mapping** (`app/prompts.py`) - Region-type-specific prompts
5. **Configuration** (`app/config.py`) - Settings management

## Backward Compatibility

The existing `/jobs/upload` endpoint from the Triton backend is maintained for backward compatibility. New clients should use the `/extract-region` and `/extract-regions-batch` endpoints for region-based processing.

## Performance

- Single region extraction: ~1-3 seconds (GPU)
- Batch processing: ~2-5 seconds for 5 regions (GPU)
- CPU fallback available (slower)

## Logging

All requests are logged with:
- Request ID for tracking
- Processing time
- Status codes
- Error details

Logs are in JSON format for easy parsing.
