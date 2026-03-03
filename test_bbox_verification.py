"""
Quick test to verify 2D bounding boxes are returned
"""

import json
import logging
import os
import sys
from pathlib import Path

# Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add model to path
MODEL_DIR = Path(__file__).parent / "services" / "triton-models" / "glm_ocr" / "1"
sys.path.insert(0, str(MODEL_DIR))

# Configure
os.environ["IDEP_MOCK_INFERENCE"] = "false"
os.environ["IDEP_STRICT_REAL"] = "false"
os.environ["GLM_MODEL_PATH"] = "zai-org/GLM-OCR"

print("="*80)
print("GLM-OCR Bounding Box Verification Test")
print("="*80)
print()

# Initialize
print("Initializing model...")
import model as triton_model

model_instance = triton_model.TritonPythonModel()
model_instance.initialize({})

print(f"✅ Model initialized")
print(f"   Device: {model_instance._device}")
print(f"   MOCK mode: {triton_model.MOCK_MODE}")
print()

# Test with coordinates
test_image = "test_invoice_local.png"
print(f"Testing with: {test_image}")
print(f"Options: include_coords=True")
print()

result = model_instance._native_inference(
    image_ref=test_image,
    prompt_override="",
    output_format="json",
    include_coords=True,
    include_word_conf=False,
    max_tokens=2048,
    precision="normal"
)

print("="*80)
print("RESULT STRUCTURE")
print("="*80)
print()

# Show full structure
print("Full result keys:", list(result.keys()))
print()

# Show pages structure
if "pages" in result:
    print(f"Number of pages: {len(result['pages'])}")
    page = result["pages"][0]
    print(f"Page keys: {list(page.keys())}")
    print(f"Page dimensions: {page['width']} x {page['height']}")
    print(f"Number of elements: {len(page['elements'])}")
    print()
    
    # Show each element
    for i, element in enumerate(page["elements"]):
        print(f"Element {i}:")
        print(f"  Label: {element.get('label')}")
        print(f"  Confidence: {element.get('confidence')}")
        print(f"  bbox_2d: {element.get('bbox_2d')}")
        print(f"  Content preview: {element.get('content', '')[:100]}...")
        print()

print("="*80)
print("BBOX VERIFICATION")
print("="*80)
print()

# Check if bboxes are present
has_bbox = False
for page in result.get("pages", []):
    for element in page.get("elements", []):
        if element.get("bbox_2d") is not None:
            has_bbox = True
            bbox = element["bbox_2d"]
            print(f"✅ Found bbox_2d: {bbox}")
            print(f"   Format: [x1={bbox[0]}, y1={bbox[1]}, x2={bbox[2]}, y2={bbox[3]}]")
            print(f"   Width: {bbox[2] - bbox[0]} pixels")
            print(f"   Height: {bbox[3] - bbox[1]} pixels")
            break
    if has_bbox:
        break

if not has_bbox:
    print("❌ No bbox_2d found in elements!")
else:
    print()
    print("✅ Bounding boxes are correctly included!")

print()
print("="*80)
print("FULL JSON OUTPUT")
print("="*80)
print()
print(json.dumps(result, indent=2))

# Cleanup
model_instance.finalize()
