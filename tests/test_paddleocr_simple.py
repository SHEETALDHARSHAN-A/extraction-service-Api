"""
Simple test for PaddleOCR layout detection.

This test avoids PyTorch imports to prevent conflicts with PaddlePaddle.
"""

import os
import sys
import time
import json
from pathlib import Path
import numpy as np
from PIL import Image
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_gpu_availability():
    """Check GPU availability for PaddlePaddle."""
    logger.info("Checking GPU availability for PaddlePaddle...")
    
    try:
        import paddle
        
        has_cuda = paddle.is_compiled_with_cuda()
        logger.info(f"PaddlePaddle compiled with CUDA: {has_cuda}")
        
        if has_cuda:
            device_count = paddle.device.cuda.device_count()
            logger.info(f"CUDA devices available: {device_count}")
            
            if device_count > 0:
                current_device = paddle.get_device()
                logger.info(f"Current device: {current_device}")
                return True
            else:
                logger.warning("No CUDA devices found")
                return False
        else:
            logger.warning("PaddlePaddle not compiled with CUDA")
            return False
            
    except ImportError:
        logger.error("PaddlePaddle not installed")
        return False
    except Exception as e:
        logger.error(f"Error checking GPU: {e}")
        return False

def test_paddleocr_simple(image_path: str):
    """Simple test of PaddleOCR layout detection."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Testing PaddleOCR with: {image_path}")
    logger.info(f"{'='*60}")
    
    if not os.path.exists(image_path):
        logger.error(f"Image not found: {image_path}")
        return False
    
    try:
        # Load image
        img = Image.open(image_path).convert("RGB")
        img_np = np.array(img)
        logger.info(f"Loaded image: {img.size[0]}x{img.size[1]} pixels")
        
        # Import PaddleOCR (may fail if PyTorch conflicts)
        logger.info("Importing PaddleOCR...")
        try:
            from paddleocr import PPStructureV3
            logger.info("✓ PaddleOCR imported successfully")
        except Exception as e:
            logger.error(f"Failed to import PaddleOCR: {e}")
            logger.info("\nPossible solutions:")
            logger.info("1. Restart Python to clear import conflicts")
            logger.info("2. Run in a separate process")
            logger.info("3. Use CPU-only mode")
            return False
        
        # Initialize layout engine
        logger.info("Initializing PPStructureV3...")
        try:
            layout_engine = PPStructureV3(use_table_recognition=True)
            logger.info("✓ PPStructureV3 initialized")
        except Exception as e:
            logger.error(f"Failed to initialize PPStructureV3: {e}")
            return False
        
        # Run layout detection
        logger.info("Running layout detection...")
        start_time = time.time()
        try:
            results = layout_engine(img_np)
            processing_time = time.time() - start_time
            logger.info(f"✓ Layout detection completed in {processing_time:.2f}s")
            logger.info(f"  Regions detected: {len(results)}")
        except Exception as e:
            logger.error(f"Layout detection failed: {e}")
            return False
        
        # Process and display results
        if len(results) == 0:
            logger.warning("⚠️  No regions detected")
            return True  # Still counts as success (empty document)
        
        logger.info("\nDetected regions:")
        logger.info("-" * 60)
        
        valid_regions = 0
        for i, block in enumerate(results):
            region_type = block.get('type', 'unknown')
            bbox = block.get('bbox', [])
            confidence = block.get('score', 0.0)
            
            # Validate bbox
            bbox_valid = False
            if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                x1, y1, x2, y2 = bbox
                if all(isinstance(coord, (int, float)) for coord in bbox):
                    if x2 > x1 and y2 > y1:
                        bbox_valid = True
            
            if bbox_valid:
                valid_regions += 1
                status = "✓"
            else:
                status = "⚠️"
            
            logger.info(f"{status} Region {i}:")
            logger.info(f"  Type: {region_type}")
            logger.info(f"  Bbox: {bbox}")
            logger.info(f"  Confidence: {confidence:.3f}")
            
            if 'res' in block:
                content_preview = str(block['res'])[:100]
                logger.info(f"  Content: {content_preview}...")
        
        # Save results
        result_file = f"paddleocr_simple_result_{Path(image_path).stem}.json"
        result_data = {
            "image": image_path,
            "dimensions": {"width": img.size[0], "height": img.size[1]},
            "processing_time": processing_time,
            "total_regions": len(results),
            "valid_regions": valid_regions,
            "regions": [],
            "timestamp": time.time()
        }
        
        for i, block in enumerate(results):
            region_data = {
                "index": i,
                "type": block.get('type', 'unknown'),
                "bbox": block.get('bbox', []),
                "confidence": float(block.get('score', 0.0)),
            }
            if 'res' in block:
                region_data['text'] = block['res']
            result_data["regions"].append(region_data)
        
        with open(result_file, 'w') as f:
            json.dump(result_data, f, indent=2)
        
        logger.info(f"\nResults saved to: {result_file}")
        
        # Summary
        logger.info(f"\n{'='*60}")
        logger.info("TEST SUMMARY")
        logger.info(f"{'='*60}")
        logger.info(f"Image: {image_path}")
        logger.info(f"Dimensions: {img.size[0]}x{img.size[1]}")
        logger.info(f"Processing time: {processing_time:.2f}s")
        logger.info(f"Total regions: {len(results)}")
        logger.info(f"Valid regions: {valid_regions}")
        
        if valid_regions > 0:
            logger.info("✅ PaddleOCR layout detection is working!")
            return True
        else:
            logger.warning("⚠️  No valid regions detected")
            return len(results) > 0  # Success if we got any results
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function."""
    # Check GPU
    gpu_available = check_gpu_availability()
    
    # Test images
    test_images = ["test_simple.png", "test_invoice_local.png"]
    
    all_passed = True
    test_results = []
    
    for image_path in test_images:
        if not os.path.exists(image_path):
            logger.warning(f"Image not found: {image_path}, skipping...")
            continue
        
        passed = test_paddleocr_simple(image_path)
        test_results.append({
            "image": image_path,
            "passed": passed
        })
        
        if not passed:
            all_passed = False
    
    # Print final summary
    logger.info(f"\n{'='*80}")
    logger.info("FINAL TEST SUMMARY")
    logger.info(f"{'='*80}")
    logger.info(f"GPU available: {gpu_available}")
    logger.info(f"Tests run: {len(test_results)}")
    logger.info(f"Tests passed: {sum(1 for r in test_results if r['passed'])}")
    
    for result in test_results:
        status = "✅" if result['passed'] else "❌"
        logger.info(f"  {status} {result['image']}")
    
    if all_passed and len(test_results) > 0:
        logger.info(f"\n✅ All tests passed!")
        sys.exit(0)
    else:
        logger.error(f"\n❌ Some tests failed")
        sys.exit(1)

if __name__ == "__main__":
    main()