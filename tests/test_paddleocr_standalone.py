"""
Standalone test for PaddleOCR layout detection (without GLM-OCR).

This test verifies that PaddleOCR can detect document regions independently.
"""

import os
from PIL import Image
import numpy as np


def test_paddleocr_standalone():
    """Test PaddleOCR layout detection in isolation."""
    
    print("=" * 80)
    print("Testing PaddleOCR Layout Detection (Standalone)")
    print("=" * 80)
    
    # Import PaddleOCR
    print("\n1. Importing PaddleOCR...")
    try:
        from paddleocr import PPStructureV3
        print("✓ PaddleOCR imported successfully")
    except ImportError as e:
        print(f"❌ FAILED: Could not import PaddleOCR: {e}")
        return False
    
    # Initialize layout engine
    print("\n2. Initializing PPStructureV3...")
    try:
        layout_engine = PPStructureV3(use_table_recognition=True)
        print("✓ PPStructureV3 initialized successfully")
    except Exception as e:
        print(f"❌ FAILED: Could not initialize PPStructureV3: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Find a test image
    test_images = [
        "testfiles/Jio_Rs_730.pdf",
        "test_invoice_local.png",
        "test_simple.png",
        "testfiles/Priya.pdf",
    ]
    
    test_image = None
    for img_path in test_images:
        if os.path.exists(img_path):
            test_image = img_path
            break
    
    if not test_image:
        print(f"❌ FAILED: No test image found. Tried: {test_images}")
        return False
    
    print(f"\n3. Testing with image: {test_image}")
    
    # Load image
    try:
        if test_image.endswith('.pdf'):
            # For PDF, we need to convert to image first
            print("   Note: PDF files require conversion. Using a PNG instead...")
            # Try to find a PNG
            for img_path in test_images:
                if img_path.endswith('.png') and os.path.exists(img_path):
                    test_image = img_path
                    break
            else:
                print("   No PNG test image found. Skipping...")
                return False
        
        img = Image.open(test_image).convert("RGB")
        img_np = np.array(img)
        print(f"   Image loaded: {img.size[0]}x{img.size[1]} pixels")
    except Exception as e:
        print(f"❌ FAILED: Could not load image: {e}")
        return False
    
    # Run layout detection
    print("\n4. Running layout detection...")
    try:
        results = layout_engine(img_np)
        print(f"✓ Layout detection completed")
        print(f"   Number of regions detected: {len(results)}")
    except Exception as e:
        print(f"❌ FAILED: Layout detection failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Display results
    if len(results) == 0:
        print("\n⚠️  WARNING: No regions detected")
        return False
    
    print("\n5. Detected regions:")
    print("-" * 80)
    for i, block in enumerate(results):
        print(f"\n   Region {i + 1}:")
        print(f"   - Type: {block.get('type', 'unknown')}")
        print(f"   - Bbox: {block.get('bbox', 'N/A')}")
        print(f"   - Score: {block.get('score', 'N/A')}")
        if 'res' in block:
            print(f"   - Content preview: {str(block['res'])[:100]}...")
    
    print("\n" + "=" * 80)
    print("✓ SUCCESS: PaddleOCR layout detection is working!")
    print("=" * 80)
    
    return True


if __name__ == "__main__":
    import sys
    success = test_paddleocr_standalone()
    sys.exit(0 if success else 1)
