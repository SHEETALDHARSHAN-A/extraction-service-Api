"""
Simple Direct GPU Test for GLM-OCR
===================================
Tests the fixed model directly without Triton request simulation.
"""

import json
import logging
import os
import sys
import time
from pathlib import Path
from PIL import Image, ImageDraw

# Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add model to path
MODEL_DIR = Path(__file__).parent / "services" / "triton-models" / "glm_ocr" / "1"
sys.path.insert(0, str(MODEL_DIR))

# Configure for real model
os.environ["IDEP_MOCK_INFERENCE"] = "false"
os.environ["IDEP_STRICT_REAL"] = "false"
os.environ["GLM_MODEL_PATH"] = "zai-org/GLM-OCR"

print("="*80)
print("GLM-OCR Simple GPU Test")
print("="*80)
print()

# Check GPU
print("1. GPU Check...")
try:
    import torch
    print(f"   CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"   GPU: {torch.cuda.get_device_name(0)}")
        print(f"   Memory: {torch.cuda.get_device_properties(0).total_memory / (1024**3):.2f} GB")
except Exception as e:
    print(f"   Error: {e}")

print()

# Initialize model
print("2. Model Initialization...")
try:
    import model
    
    triton_model = model.TritonPythonModel()
    start = time.time()
    triton_model.initialize({})
    print(f"   Initialized in {time.time()-start:.2f}s")
    print(f"   Device: {triton_model._device}")
    print(f"   MOCK mode: {model.MOCK_MODE}")
    print(f"   Model loaded: {triton_model.model is not None}")
    print(f"   Processor loaded: {triton_model.processor is not None}")
    
except Exception as e:
    print(f"   Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Create test image
print("3. Creating test image...")
img = Image.new('RGB', (800, 600), color='white')
draw = ImageDraw.Draw(img)
draw.text((50, 50), "INVOICE #12345", fill='black')
draw.text((50, 100), "Date: 2026-03-03", fill='black')
draw.text((50, 150), "Amount: $1,234.56", fill='black')
test_image = "test_simple.png"
img.save(test_image)
print(f"   Created: {test_image}")

print()

# Test inference directly
print("4. Testing inference (text format)...")
try:
    result = triton_model._native_inference(
        image_ref=test_image,
        prompt_override="",
        output_format="text",
        include_coords=True,
        include_word_conf=False,
        max_tokens=2048,
        precision="normal"
    ) if not model.MOCK_MODE else model._MockEngine.run(
        image_ref=test_image,
        prompt_override="",
        output_format="text",
        include_coords=True,
        include_word_conf=False,
        include_page_layout=False,
        precision="normal"
    )
    
    print(f"   Success!")
    print(f"   Pages: {len(result.get('pages', []))}")
    print(f"   Elements: {len(result['pages'][0]['elements']) if result.get('pages') else 0}")
    print(f"   Confidence: {result.get('confidence', 0):.4f}")
    print(f"   Mode: {result.get('mode', 'unknown')}")
    
    # Show first element content
    if result.get('pages') and result['pages'][0].get('elements'):
        content = result['pages'][0]['elements'][0].get('content', '')
        print(f"   Content preview: {content[:100]}...")
    
except Exception as e:
    print(f"   Error: {e}")
    import traceback
    traceback.print_exc()

print()

# Test all formats
print("5. Testing all output formats...")
formats = ["text", "json", "markdown", "table", "key_value", "structured"]
for fmt in formats:
    try:
        result = triton_model._native_inference(
            image_ref=test_image,
            prompt_override="",
            output_format=fmt,
            include_coords=True,
            include_word_conf=False,
            max_tokens=2048,
            precision="normal"
        ) if not model.MOCK_MODE else model._MockEngine.run(
            image_ref=test_image,
            prompt_override="",
            output_format=fmt,
            include_coords=True,
            include_word_conf=False,
            include_page_layout=False,
            precision="normal"
        )
        
        # Validate schema
        if fmt in ("json", "table", "key_value", "structured"):
            content = result['pages'][0]['elements'][0]['content']
            parsed = json.loads(content)
            print(f"   {fmt:12s} - OK (valid JSON)")
        else:
            print(f"   {fmt:12s} - OK")
            
    except Exception as e:
        print(f"   {fmt:12s} - FAILED: {e}")

print()

# Test custom prompt
print("6. Testing custom prompt...")
try:
    result = triton_model._native_inference(
        image_ref=test_image,
        prompt_override="Extract only the invoice number and amount.",
        output_format="text",
        include_coords=True,
        include_word_conf=False,
        max_tokens=2048,
        precision="normal"
    ) if not model.MOCK_MODE else model._MockEngine.run(
        image_ref=test_image,
        prompt_override="Extract only the invoice number and amount.",
        output_format="text",
        include_coords=True,
        include_word_conf=False,
        include_page_layout=False,
        precision="normal"
    )
    
    print(f"   Custom prompt accepted: OK")
    
except Exception as e:
    print(f"   Error: {e}")

print()

# GPU memory check
print("7. GPU Memory Usage...")
try:
    if torch.cuda.is_available() and not model.MOCK_MODE:
        torch.cuda.synchronize()
        allocated = torch.cuda.memory_allocated(0) / (1024**3)
        reserved = torch.cuda.memory_reserved(0) / (1024**3)
        print(f"   Allocated: {allocated:.2f} GB")
        print(f"   Reserved: {reserved:.2f} GB")
        if allocated > 0.1:
            print(f"   Status: Using GPU")
        else:
            print(f"   Status: Minimal GPU usage (might be CPU)")
    else:
        print(f"   Skipped (MOCK mode or no CUDA)")
except Exception as e:
    print(f"   Error: {e}")

print()

# Cleanup
print("8. Cleanup...")
triton_model.finalize()
print(f"   Done")

print()
print("="*80)
print("Summary:")
print(f"  Model mode: {'MOCK' if model.MOCK_MODE else 'NATIVE (Real Model)'}")
print(f"  Device: {triton_model._device}")
print(f"  All tests completed")
print("="*80)
