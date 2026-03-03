# Bounding Box Implementation Status

## Current State

The GLM-OCR model implementation includes support for per-field bounding boxes through a two-stage pipeline:

1. **Stage 1: Layout Detection** - PaddleOCR's PPStructureV3 detects document regions
2. **Stage 2: Content Extraction** - GLM-OCR extracts content from each region

## Implementation Details

### Code Location
- File: `services/triton-models/glm_ocr/1/model.py`
- Lines 550-580: PaddleOCR initialization
- Lines 770-850: Two-stage inference pipeline with bbox support

### How It Works

When `include_coordinates=True` is set in the options:

1. **With PaddleOCR** (multi-region mode):
   - PPStructureV3 detects multiple regions (text blocks, tables, formulas, etc.)
   - Each region gets its own bbox: `[x1, y1, x2, y2]`
   - GLM-OCR processes each region separately with task-specific prompts
   - Output contains multiple elements, each with its own bbox

2. **Without PaddleOCR** (full-page mode):
   - Single bbox for the entire page: `[0, 0, page_width, page_height]`
   - GLM-OCR processes the whole image at once
   - Output contains one element with full-page bbox

### Output Format

```json
{
  "pages": [
    {
      "page": 1,
      "width": 800,
      "height": 600,
      "elements": [
        {
          "index": 0,
          "label": "text",
          "content": "Invoice Number: INV-12345",
          "bbox_2d": [100, 50, 400, 80],
          "confidence": 0.95
        },
        {
          "index": 1,
          "label": "table",
          "content": "{...}",
          "bbox_2d": [100, 100, 700, 400],
          "confidence": 0.92
        }
      ]
    }
  ]
}
```

## Known Limitation: PyTorch + PaddlePaddle Conflict

### The Problem

PaddlePaddle and PyTorch cannot coexist in the same Python process when both use CUDA. This causes the error:

```
ImportError: generic_type: type "_gpuDeviceProperties" is already registered!
```

### Why This Happens

Both frameworks register CUDA device properties with Python's type system. When both are loaded:
1. PyTorch registers `_gpuDeviceProperties` first (when loading GLM-OCR model)
2. PaddlePaddle tries to register the same type
3. Python's pybind11 throws an error because the type is already registered

### Current Workaround

The model code attempts to initialize PaddleOCR at startup:

```python
# In model.py, lines 550-580
if paddleocr_available:
    try:
        from paddleocr import PPStructureV3
        self.layout_engine = PPStructureV3(use_table_recognition=True)
        logger.info("... PP-DocLayout-V3 ready (PaddleOCR layout detection enabled)")
    except Exception as exc:
        logger.warning("PP-DocLayout init failed (%s) -- layout stage disabled", exc)
```

If PaddleOCR initialization fails, the model falls back to full-page mode (single bbox).

## Alternative Solutions

### Option 1: Separate Processes (Recommended for Production)

Run PaddleOCR and GLM-OCR in separate processes:

1. **Process 1: Layout Detection Service**
   - Runs PaddleOCR only
   - Detects regions and returns bboxes
   - No PyTorch dependency

2. **Process 2: GLM-OCR Service**
   - Runs GLM-OCR only
   - Receives cropped regions from Process 1
   - Extracts content

3. **Orchestrator**
   - Sends image to Process 1 for layout detection
   - Crops regions based on bboxes
   - Sends each crop to Process 2 for content extraction
   - Assembles final result

### Option 2: Use GLM-OCR's Built-in Layout Understanding

GLM-OCR is a vision-language model that can understand document layout without explicit region detection:

```python
# Use structured output format with custom prompt
options = {
    "output_format": "key_value",
    "include_coordinates": True,
}

# GLM-OCR will extract fields and provide approximate bboxes
# based on its internal attention mechanisms
```

**Limitations:**
- Bboxes are less precise than PaddleOCR's layout detection
- Single bbox per page instead of per-field
- Works well for simple documents but may struggle with complex layouts

### Option 3: Use PaddleOCR-only Mode

For applications that only need layout detection without content extraction:

```python
# Separate script using only PaddleOCR
from paddleocr import PPStructureV3
import numpy as np
from PIL import Image

layout_engine = PPStructureV3(use_table_recognition=True)
img = Image.open("document.png").convert("RGB")
img_np = np.array(img)
results = layout_engine(img_np)

# Results contain bboxes for each detected region
for block in results:
    bbox = block['bbox']  # [x1, y1, x2, y2]
    region_type = block['type']  # 'text', 'table', 'formula', etc.
    confidence = block['score']
```

## Testing Status

### ✓ Completed
- [x] PaddleOCR installation verified (version 3.4.0)
- [x] Model code updated to support PPStructureV3
- [x] Fallback to full-page mode when PaddleOCR unavailable
- [x] Output format includes bbox_2d field
- [x] Standalone PaddleOCR import test

### ❌ Blocked
- [ ] PaddleOCR + PyTorch integration test (blocked by CUDA conflict)
- [ ] Multi-region bbox verification (requires PaddleOCR to work with PyTorch)

### ⚠️ Workaround Needed
- Current implementation falls back to full-page bbox when PaddleOCR fails to initialize
- For per-field bboxes, need to implement Option 1 (separate processes) or use Option 2 (GLM-OCR built-in)

## Recommendations

### For Development/Testing
- Use full-page mode (current implementation)
- Single bbox per document: `[0, 0, width, height]`
- Fast and reliable, no dependency conflicts

### For Production with Per-Field Bboxes
- Implement Option 1: Separate microservices
  - Layout Detection Service (PaddleOCR only, CPU-based)
  - Content Extraction Service (GLM-OCR only, GPU-based)
  - API Gateway to orchestrate both services

### For Simple Use Cases
- Use Option 2: GLM-OCR's built-in layout understanding
- Acceptable for documents with simple layouts
- No additional infrastructure needed

## Next Steps

1. **Immediate**: Document the limitation and current behavior
2. **Short-term**: Implement Option 1 (separate processes) if per-field bboxes are required
3. **Long-term**: Investigate alternative layout detection libraries compatible with PyTorch

## References

- PaddleOCR GitHub: https://github.com/PaddlePaddle/PaddleOCR
- GLM-OCR GitHub: https://github.com/zai-org/GLM-OCR
- PyTorch + PaddlePaddle conflict discussion: https://github.com/PaddlePaddle/Paddle/issues/48106
