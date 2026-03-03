# PaddleOCR Layout Detection Service Testing

This guide covers testing the PaddleOCR Layout Detection Service with GPU support and bounding box verification.

## Overview

The PaddleOCR service provides document layout detection using PPStructureV3. It detects regions (text, tables, formulas, etc.) and returns bounding boxes for each region.

## Current Implementation Status

Based on the spec (`tasks.md`), Task 1 (PaddleOCR Service) is mostly complete:
- ✅ Service structure and configuration
- ✅ PPStructureV3 model wrapper
- ✅ Pydantic models
- ✅ FastAPI application
- ✅ Image preprocessing
- ✅ Logging and monitoring
- ❌ Dockerfile (pending)
- ❌ Unit tests (partial)
- ❌ Integration tests (pending)

## Test Files Created

1. **`test_paddleocr_service_local.py`** - Full service test
   - Starts the FastAPI service
   - Tests `/health` and `/detect-layout` endpoints
   - Validates bounding boxes
   - Tests both GPU and CPU modes

2. **`test_paddleocr_direct.py`** - Direct model test
   - Tests PaddleOCR PPStructureV3 directly
   - No service startup required
   - Faster for development/testing
   - Validates bounding boxes

3. **`install_paddleocr_deps.py`** - Dependency installer
   - Installs PaddlePaddle (CPU/GPU)
   - Installs PaddleOCR and dependencies
   - Verifies installation
   - Creates test environment

## Quick Start

### 1. Install Dependencies

```bash
# Install PaddleOCR dependencies
python install_paddleocr_deps.py

# Or manually:
pip install paddlepaddle-gpu==2.6.0  # For GPU
# pip install paddlepaddle==2.6.0    # For CPU
pip install paddleocr>=2.7.0
pip install pillow numpy requests
```

### 2. Test Direct Model (Recommended First)

```bash
# Check GPU availability
python test_paddleocr_direct.py --check-gpu

# Test with GPU (default)
python test_paddleocr_direct.py --gpu

# Test with CPU only
python test_paddleocr_direct.py --cpu

# Test specific image
python test_paddleocr_direct.py --image test_invoice_local.png
```

### 3. Test Full Service

```bash
# Test service with GPU
python test_paddleocr_service_local.py --gpu

# Test service with CPU
python test_paddleocr_service_local.py --cpu

# Test both modes
python test_paddleocr_service_local.py --both
```

## Expected Results

### Successful Test Output

```
============================================================
Testing: test_invoice_local.png
============================================================
Loaded image: 800x600 pixels
Running layout detection (confidence threshold: 0.3)...
✓ Layout detection completed in 1.23s
  Raw regions detected: 8
  Regions after confidence filter: 6

Results:
  Image dimensions: 800x600
  Regions detected: 6
  Valid bboxes: 6/6
  Region types: {'text': 4, 'table': 1, 'title': 1}

Sample regions (first 5):
  Region 0: text - bbox: [100, 50, 400, 80] - confidence: 0.950
  Region 1: table - bbox: [100, 100, 700, 400] - confidence: 0.920
  Region 2: text - bbox: [120, 420, 680, 450] - confidence: 0.870
  Region 3: title - bbox: [200, 30, 600, 60] - confidence: 0.910
  Region 4: text - bbox: [150, 480, 650, 510] - confidence: 0.820

Detailed results saved to: paddleocr_direct_result_test_invoice_local.json
✓ Multiple valid regions detected - layout detection is working!
```

### Bounding Box Validation

The test validates:
- Bbox format: `[x1, y1, x2, y2]` (4 integers)
- Coordinates: `x2 > x1` and `y2 > y1`
- Bounds: Within image dimensions
- Confidence: Above threshold (default: 0.3)

## GPU Support Verification

### Check GPU Availability

```bash
# Check if GPU is detected
python -c "import paddle; print(f'CUDA: {paddle.is_compiled_with_cuda()}'); print(f'Devices: {paddle.device.cuda.device_count()}')"

# Check NVIDIA GPU
nvidia-smi
```

### GPU vs CPU Mode

- **GPU mode**: Faster inference, requires CUDA-enabled PaddlePaddle
- **CPU mode**: Slower but more reliable, no CUDA dependencies

The test scripts automatically fall back to CPU if GPU is not available.

## Test Images

Default test images:
1. `test_simple.png` - Simple test image
2. `test_invoice_local.png` - Sample invoice document

You can add more test images to the `TEST_IMAGES` list in the test scripts.

## Output Files

Tests generate JSON result files:
- `paddleocr_direct_result_*.json` - Direct test results
- `paddleocr_test_result_*.json` - Service test results

These files contain:
- Detected regions with bounding boxes
- Validation results
- Performance metrics
- Configuration details

## Troubleshooting

### Common Issues

1. **ImportError: No module named 'paddle'**
   ```bash
   pip install paddlepaddle-gpu==2.6.0  # or paddlepaddle==2.6.0
   ```

2. **CUDA not available**
   - Check CUDA toolkit installation
   - Use CPU mode: `--cpu` flag
   - Install CPU version: `pip install paddlepaddle==2.6.0`

3. **Model download slow on first run**
   - First run downloads PPStructureV3 models (~200MB)
   - Subsequent runs use cached models
   - Models stored in `~/.paddleocr/` or configured `PADDLEOCR_MODEL_DIR`

4. **Memory issues with large images**
   - Reduce image size before testing
   - Adjust `PADDLEOCR_MAX_IMAGE_SIZE_MB` in configuration
   - Use `options.min_confidence` to filter low-confidence regions

### Debug Mode

Enable debug logging:
```bash
export LOG_LEVEL=DEBUG
python test_paddleocr_direct.py
```

## Integration with GLM-OCR

The PaddleOCR service is designed to work with GLM-OCR in a two-stage pipeline:

1. **Stage 1**: PaddleOCR detects regions and bounding boxes
2. **Stage 2**: GLM-OCR extracts content from each region

### Current Limitation

There's a known conflict between PyTorch (GLM-OCR) and PaddlePaddle (PaddleOCR) when both use CUDA in the same process. The current workaround:

1. **Option 1**: Separate processes (recommended for production)
   - PaddleOCR service (CPU or GPU)
   - GLM-OCR service (GPU)
   - API Gateway orchestrates both

2. **Option 2**: Use PaddleOCR in CPU mode with GLM-OCR in GPU mode
   - Less performance impact for layout detection
   - Content extraction still uses GPU

3. **Option 3**: Fallback to full-page mode
   - Single bbox for entire page
   - GLM-OCR processes whole image

## Next Steps

### Complete Task 1 Implementation

1. **Create Dockerfile** (`1.8` in tasks.md)
   ```dockerfile
   FROM python:3.11-slim
   # Install PaddleOCR and dependencies
   # Copy application code
   # Set up non-root user
   # Expose port 8001
   # Add health check
   ```

2. **Write remaining unit tests** (`1.10` in tasks.md)
   - `test_layout_detector.py`
   - `test_models.py`
   - `test_api.py`

3. **Write integration tests** (`1.11` in tasks.md)
   - Test with real model
   - Test error responses
   - Test image validation

### Performance Testing

1. **Latency tests**: Layout detection < 500ms
2. **Throughput tests**: 20 requests/second
3. **Memory tests**: Monitor GPU/CPU memory usage

### Integration Testing

1. **Test with API Gateway**: Verify service discovery
2. **Test with GLM-OCR**: Verify two-stage pipeline
3. **Test fallback behavior**: Service unavailable scenarios

## References

- [PaddleOCR GitHub](https://github.com/PaddlePaddle/PaddleOCR)
- [PPStructureV3 Documentation](https://github.com/PaddlePaddle/PaddleOCR/blob/release/2.7/ppstructure/README.md)
- [PaddlePaddle Installation Guide](https://www.paddlepaddle.org.cn/install/quick)
- [BBOX Implementation Status](BBOX_IMPLEMENTATION_STATUS.md)

## Summary

The PaddleOCR Layout Detection Service is functional and ready for testing. The test scripts provide comprehensive validation of:

✅ GPU support verification  
✅ Bounding box validation  
✅ Multiple region detection  
✅ Performance metrics  
✅ Error handling  

Use the test scripts to verify the implementation before proceeding with Task 2 (GLM-OCR Service Modifications).