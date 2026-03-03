# Technical Design: PaddleOCR Microservice Architecture

## 1. Architecture Overview

### 1.1 System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Client Application                          │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ HTTP REST
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          API Gateway (Go)                            │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Job Management │ Auth │ Rate Limiting │ Result Assembly    │  │
│  └──────────────────────────────────────────────────────────────┘  │
└───────┬─────────────────────────────────────────────────┬───────────┘
        │                                                   │
        │ HTTP REST                                         │ HTTP REST
        ▼                                                   ▼
┌──────────────────────────┐                    ┌──────────────────────┐
│  PaddleOCR Service       │                    │  GLM-OCR Service     │
│  (Python + FastAPI)      │                    │  (Python + FastAPI)  │
│  ┌────────────────────┐  │                    │  ┌────────────────┐  │
│  │ PPStructureV3      │  │                    │  │ GLM-OCR Model  │  │
│  │ Layout Detection   │  │                    │  │ Content Extract│  │
│  └────────────────────┘  │                    │  └────────────────┘  │
│  CPU/GPU                 │                    │  GPU (CUDA)          │
└──────────────────────────┘                    └──────────────────────┘
        │                                                   │
        └───────────────────┬───────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Supporting Services                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │  Redis   │  │  MinIO   │  │ Temporal │  │  Preprocessing   │   │
│  │  Cache   │  │  Storage │  │ Workflow │  │  Service         │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 Service Responsibilities

#### API Gateway
- Receive document upload requests
- Authenticate and authorize requests
- Orchestrate two-stage pipeline
- Crop images into regions
- Assemble final results
- Cache layout detection results
- Handle fallback scenarios

#### PaddleOCR Service
- Initialize PPStructureV3 layout detection model
- Detect document regions (text, table, formula, etc.)
- Return bounding boxes for each region
- Classify region types
- Filter by confidence threshold

#### GLM-OCR Service
- Initialize GLM-OCR vision-language model
- Extract content from image regions
- Support multiple output formats
- Handle batch region processing
- Apply task-specific prompts

### 1.3 Data Flow

```
1. Client uploads document
   ↓
2. API Gateway receives request
   ↓
3. API Gateway → PaddleOCR Service (layout detection)
   ↓
4. PaddleOCR returns regions with bboxes
   ↓
5. API Gateway crops image into regions
   ↓
6. API Gateway → GLM-OCR Service (batch content extraction)
   ↓
7. GLM-OCR returns content for each region
   ↓
8. API Gateway assembles final result
   ↓
9. API Gateway returns response to client
```

## 2. Service Specifications

### 2.1 PaddleOCR Layout Detection Service

#### 2.1.1 Technology Stack
- **Language**: Python 3.11
- **Framework**: FastAPI 0.100+
- **ML Library**: PaddleOCR 3.4.0, PaddlePaddle 2.5.0
- **Image Processing**: Pillow, NumPy
- **Deployment**: Docker container
- **Hardware**: CPU (2 cores, 4GB RAM) or GPU (1 GPU, 6GB VRAM)

#### 2.1.2 API Endpoints

**POST /detect-layout**

Request:
```json
{
  "image": "base64_encoded_image_data",
  "options": {
    "min_confidence": 0.5,
    "detect_tables": true,
    "detect_formulas": true,
    "return_image_dimensions": true
  }
}
```

Response:
```json
{
  "regions": [
    {
      "index": 0,
      "type": "text",
      "bbox": [100, 50, 400, 80],
      "confidence": 0.95
    },
    {
      "index": 1,
      "type": "table",
      "bbox": [100, 100, 700, 400],
      "confidence": 0.92
    }
  ],
  "page_dimensions": {
    "width": 800,
    "height": 600
  },
  "processing_time_ms": 150,
  "model_version": "PPStructureV3"
}
```

**GET /health**

Response:
```json
{
  "status": "healthy",
  "service": "paddleocr-layout-detection",
  "version": "1.0.0",
  "uptime_seconds": 3600,
  "models_loaded": true,
  "gpu_available": false,
  "device": "cpu"
}
```

#### 2.1.3 Implementation Details

**Service Structure**:
```
services/paddleocr-service/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── models.py            # Pydantic models
│   ├── layout_detector.py   # PPStructureV3 wrapper
│   └── config.py            # Configuration
├── Dockerfile
├── requirements.txt
└── README.md
```

**Key Classes**:

```python
class LayoutDetector:
    """Wrapper for PPStructureV3 layout detection."""
    
    def __init__(self, use_gpu: bool = False):
        self.layout_engine = PPStructureV3(
            use_table_recognition=True
        )
    
    def detect_regions(
        self, 
        image: np.ndarray,
        min_confidence: float = 0.5
    ) -> List[Region]:
        """Detect document regions."""
        results = self.layout_engine(image)
        regions = []
        for i, block in enumerate(results):
            if block.get('score', 0) >= min_confidence:
                regions.append(Region(
                    index=i,
                    type=block['type'],
                    bbox=block['bbox'],
                    confidence=block['score']
                ))
        return regions
```

**Configuration**:
- `PADDLEOCR_USE_GPU`: Enable GPU mode (default: false)
- `PADDLEOCR_MODEL_DIR`: Model cache directory
- `MIN_CONFIDENCE_DEFAULT`: Default confidence threshold (0.5)
- `MAX_IMAGE_SIZE_MB`: Maximum image size (10MB)
- `REQUEST_TIMEOUT_SECONDS`: Request timeout (30s)
