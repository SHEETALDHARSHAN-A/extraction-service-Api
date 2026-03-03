"""
Test PaddleOCR integration for per-field bounding boxes.

This test verifies that:
1. PaddleOCR layout detection is working
2. Multiple regions are detected (not just one full-page bbox)
3. Each region has its own bbox coordinates
"""

import sys
import os

# Add the model directory to Python path
sys.path.insert(0, "services/triton-models/glm_ocr/1")

# Force reload of the module to pick up PaddleOCR if it was installed after first import
import importlib
if 'model' in sys.modules:
    importlib.reload(sys.modules['model'])

from model import TritonPythonModel
import json


def test_paddleocr_bbox():
    """Test that PaddleOCR detects multiple regions with individual bboxes."""
    
    print("=" * 80)
    print("Testing PaddleOCR Integration for Per-Field Bounding Boxes")
    print("=" * 80)
    
    # Enable logging to see what's happening
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # Initialize the model
    print("\n1. Initializing GLM-OCR model...")
    model = TritonPythonModel()
    model.initialize({"model_config": "{}"})
    
    # Check if PaddleOCR is enabled
    if model.layout_engine is None:
        print("❌ FAILED: PaddleOCR layout engine is not initialized!")
        print("   This means _PADDLEOCR_OK was False during initialization.")
        print("   Try restarting Python or reimporting the module.")
        return False
    
    print("✓ PaddleOCR layout engine initialized successfully")
    
    # Test with a sample invoice image
    test_image = "testfiles/Jio_Rs_730.pdf"
    if not os.path.exists(test_image):
        # Try alternative test images
        test_images = [
            "test_invoice_local.png",
            "test_simple.png",
            "testfiles/Priya.pdf",
        ]
        for img in test_images:
            if os.path.exists(img):
                test_image = img
                break
        else:
            print(f"❌ FAILED: No test image found. Tried: {test_image}, {test_images}")
            return False
    
    print(f"\n2. Testing with image: {test_image}")
    
    # Create a mock request object
    class MockRequest:
        def __init__(self, image_path):
            self.image_path = image_path
        
        def parameters(self):
            return {
                "image_ref": self.image_path,
                "prompt": "",  # No custom prompt - use task-specific prompts
                "options_json": {
                    "include_coordinates": True,
                    "output_format": "key_value",
                }
            }
    
    request = MockRequest(test_image)
    
    # Execute inference
    print("\n3. Running inference with PaddleOCR layout detection...")
    try:
        response = model._handle(request)
        
        # Parse the result
        if isinstance(response, dict):
            result = response
        else:
            # It's a Triton response, extract the JSON
            result_json = response.output_tensors()[0].as_numpy()[0]
            if isinstance(result_json, bytes):
                result_json = result_json.decode('utf-8')
            result = json.loads(result_json)
        
        print("\n4. Analyzing results...")
        print(f"   Result keys: {list(result.keys())}")
        
        # Check pages
        pages = result.get("pages", [])
        if not pages:
            print("❌ FAILED: No pages in result")
            return False
        
        print(f"   Number of pages: {len(pages)}")
        
        # Check elements (regions detected)
        elements = pages[0].get("elements", [])
        print(f"   Number of elements detected: {len(elements)}")
        
        if len(elements) == 0:
            print("❌ FAILED: No elements detected")
            return False
        
        if len(elements) == 1:
            # Check if it's just a full-page bbox
            bbox = elements[0].get("bbox_2d", [])
            label = elements[0].get("label", "")
            if label == "page":
                print("⚠️  WARNING: Only one element detected with label 'page'")
                print("   This suggests PaddleOCR layout detection is not active.")
                print(f"   Bbox: {bbox}")
                print("\n   Possible reasons:")
                print("   - PaddleOCR models not downloaded yet (first run)")
                print("   - Layout detection disabled due to custom prompt")
                print("   - Image format not supported by PaddleOCR")
                return False
        
        # Display detected regions
        print("\n5. Detected regions:")
        print("-" * 80)
        for i, element in enumerate(elements):
            label = element.get("label", "unknown")
            bbox = element.get("bbox_2d", [])
            confidence = element.get("confidence", 0.0)
            content_preview = element.get("content", "")[:100]
            
            print(f"\n   Region {i + 1}:")
            print(f"   - Label: {label}")
            print(f"   - Bbox: {bbox}")
            print(f"   - Confidence: {confidence:.4f}")
            print(f"   - Content preview: {content_preview}...")
        
        print("\n" + "=" * 80)
        print("✓ SUCCESS: PaddleOCR detected multiple regions with individual bboxes!")
        print("=" * 80)
        
        # Save full result for inspection
        with open("paddleocr_bbox_result.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\nFull result saved to: paddleocr_bbox_result.json")
        
        return True
        
    except Exception as e:
        print(f"\n❌ FAILED: Exception during inference: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_paddleocr_bbox()
    sys.exit(0 if success else 1)
