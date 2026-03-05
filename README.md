# IDEP - Intelligent Document Extraction Platform

A simple, clean document OCR service powered by GLM-4V-9B model.

## Quick Start

### 1. Start the GLM-OCR Service

```bash
start_glm_service.bat
```

The service will start on `http://localhost:8002`

### 2. Test the Service

```bash
python test_glm_service.py
```

This will:
- Check if the service is running
- Generate a test invoice image
- Extract text with bounding boxes
- Save results to `glm_test_result.json`

## Service Features

- **Fast Mode**: Quick text extraction with coordinates
- **Bounding Boxes**: Precise location of each text element
- **Confidence Scores**: Per-element confidence metrics
- **Multiple Formats**: Text, Markdown, JSON output

## API Endpoint

### POST /extract

Extract text from an image with bounding boxes.

**Request:**
```json
{
  "image": "base64_encoded_image",
  "options": {
    "fast_mode": true,
    "include_coordinates": true,
    "include_confidence": true,
    "granularity": "word",
    "output_format": "text",
    "max_tokens": 512
  },
  "image_width": 1200,
  "image_height": 900
}
```

**Response:**
```json
{
  "content": "Extracted text content...",
  "bounding_boxes": [
    {
      "text": "INVOICE",
      "bbox": [50, 50, 300, 110],
      "confidence": 0.98
    }
  ],
  "processing_time_ms": 1234,
  "model_info": {
    "name": "glm-4v-9b",
    "mode": "fast"
  }
}
```

## Project Structure

```
├── services/
│   └── glm-ocr-service/     # GLM-4V-9B OCR service
├── start_glm_service.bat    # Start the service
├── test_glm_service.py      # Test the service
└── README.md                # This file
```

## Requirements

- Python 3.11+
- PyTorch with CUDA support
- GLM-4V-9B model
- See `services/glm-ocr-service/requirements.txt` for full dependencies

## Notes

- The service uses GPU acceleration if available
- First run will download the GLM-4V-9B model (~18GB)
- Fast mode provides quick results with good accuracy
- Bounding boxes are in [x, y, x2, y2] format
