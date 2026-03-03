"""
Direct test of PaddleOCR layout detection without starting the full service.

This script tests:
1. PaddleOCR installation and GPU support
2. Direct layout detection with PPStructureV3
3. Bounding box verification
4. Performance with different images
"""

import os
import sys
import time
import json
from pathlib import Path
from typing import List, Dict, Any
import numpy as np
from PIL import Image
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Test images
TEST_IMAGES = [
    "test_simple.png",
    "test_invoice_local.png",
]

class PaddleOCRDirectTester:
    """Direct test of PaddleOCR layout detection."""
    
    def __init__(self, use_gpu: bool = True):
        self.use_gpu = use_gpu
        self.layout_engine = None
        self.gpu_available = False
        
    def check_gpu_availability(self) -> bool:
        """Check if GPU is available for PaddlePaddle."""
        logger.info("Checking GPU availability...")
        
        try:
            import paddle
            
            # Check CUDA compilation
            has_cuda = paddle.is_compiled_with_cuda()
            logger.info(f"PaddlePaddle compiled with CUDA: {has_cuda}")
            
            if has_cuda:
                device_count = paddle.device.cuda.device_count()
                logger.info(f"CUDA devices available: {device_count}")
                
                if device_count > 0:
                    self.gpu_available = True
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
    
    def initialize_paddleocr(self) -> bool:
        """Initialize PaddleOCR PPStructureV3."""
        logger.info("Initializing PaddleOCR PPStructureV3...")
        
        try:
            from paddleocr import PPStructureV3
            
            # Initialize with GPU if available
            init_kwargs = {
                "use_table_recognition": True,
                "ocr_version": "PP-OCRv4",
            }
            
            # Note: PPStructureV3 doesn't have a direct use_gpu parameter
            # It uses the device context from paddle.set_device()
            if self.use_gpu and self.gpu_available:
                try:
                    import paddle
                    paddle.set_device('gpu')
                    logger.info("Set PaddlePaddle to use GPU")
                except Exception as e:
                    logger.warning(f"Failed to set GPU device: {e}")
            
            self.layout_engine = PPStructureV3(**init_kwargs)
            logger.info("✓ PPStructureV3 initialized successfully")
            return True
            
        except ImportError as e:
            logger.error(f"Failed to import PaddleOCR: {e}")
            logger.info("Install with: pip install paddleocr paddlepaddle-gpu")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize PPStructureV3: {e}")
            return False
    
    def load_image(self, image_path: str) -> np.ndarray:
        """Load image as numpy array."""
        try:
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Image not found: {image_path}")
            
            img = Image.open(image_path).convert("RGB")
            img_np = np.array(img)
            
            logger.info(f"Loaded image: {img.size[0]}x{img.size[1]} pixels")
            return img_np
            
        except Exception as e:
            logger.error(f"Failed to load image {image_path}: {e}")
            raise
    
    def detect_layout(self, image_np: np.ndarray, min_confidence: float = 0.3) -> List[Dict[str, Any]]:
        """Detect layout in image."""
        if self.layout_engine is None:
            raise RuntimeError("Layout engine not initialized")
        
        logger.info(f"Running layout detection (confidence threshold: {min_confidence})...")
        
        start_time = time.time()
        try:
            results = self.layout_engine(image_np)
            processing_time = time.time() - start_time
            
            logger.info(f"✓ Layout detection completed in {processing_time:.2f}s")
            logger.info(f"  Raw regions detected: {len(results)}")
            
            # Process results
            processed_results = []
            for i, block in enumerate(results):
                region_type = block.get('type', 'unknown')
                bbox = block.get('bbox', [0, 0, 0, 0])
                confidence = block.get('score', 1.0)
                
                # Convert bbox to integers
                if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                    bbox = [int(coord) for coord in bbox]
                
                region = {
                    "index": i,
                    "type": region_type,
                    "bbox": bbox,
                    "confidence": float(confidence),
                    "raw_type": region_type,
                }
                
                # Add text if available
                if 'res' in block:
                    region['text'] = block['res']
                
                processed_results.append(region)
            
            # Filter by confidence
            filtered_results = [r for r in processed_results if r['confidence'] >= min_confidence]
            logger.info(f"  Regions after confidence filter: {len(filtered_results)}")
            
            return filtered_results
            
        except Exception as e:
            logger.error(f"Layout detection failed: {e}")
            raise
    
    def validate_bboxes(self, regions: List[Dict[str, Any]], image_width: int, image_height: int) -> Dict[str, Any]:
        """Validate bounding boxes."""
        validation = {
            "total_regions": len(regions),
            "valid_bboxes": 0,
            "invalid_bboxes": 0,
            "issues": []
        }
        
        for i, region in enumerate(regions):
            bbox = region.get('bbox', [])
            region_type = region.get('type', 'unknown')
            
            # Check bbox format
            if not isinstance(bbox, list):
                validation["issues"].append(f"Region {i} ({region_type}): bbox is not a list")
                validation["invalid_bboxes"] += 1
                continue
            
            if len(bbox) != 4:
                validation["issues"].append(f"Region {i} ({region_type}): bbox has {len(bbox)} elements, expected 4")
                validation["invalid_bboxes"] += 1
                continue
            
            x1, y1, x2, y2 = bbox
            
            # Check coordinates are valid
            issues = []
            
            if not all(isinstance(coord, (int, float)) for coord in bbox):
                issues.append("coordinates are not numbers")
            
            if x2 <= x1:
                issues.append(f"x2 ({x2}) <= x1 ({x1})")
            
            if y2 <= y1:
                issues.append(f"y2 ({y2}) <= y1 ({y1})")
            
            if x1 < 0 or y1 < 0 or x2 > image_width or y2 > image_height:
                issues.append(f"outside image bounds [{image_width}x{image_height}]")
            
            if issues:
                validation["issues"].append(f"Region {i} ({region_type}): {', '.join(issues)}")
                validation["invalid_bboxes"] += 1
            else:
                validation["valid_bboxes"] += 1
        
        return validation
    
    def analyze_region_types(self, regions: List[Dict[str, Any]]) -> Dict[str, int]:
        """Analyze distribution of region types."""
        type_counts = {}
        for region in regions:
            region_type = region.get('type', 'unknown')
            type_counts[region_type] = type_counts.get(region_type, 0) + 1
        return type_counts
    
    def test_image(self, image_path: str) -> bool:
        """Test layout detection on a single image."""
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing: {image_path}")
        logger.info(f"{'='*60}")
        
        try:
            # Load image
            image_np = self.load_image(image_path)
            height, width = image_np.shape[:2]
            
            # Detect layout
            regions = self.detect_layout(image_np, min_confidence=0.3)
            
            if not regions:
                logger.warning("⚠️  No regions detected")
                return False
            
            # Validate bboxes
            validation = self.validate_bboxes(regions, width, height)
            
            # Analyze region types
            type_counts = self.analyze_region_types(regions)
            
            # Print results
            logger.info(f"\nResults:")
            logger.info(f"  Image dimensions: {width}x{height}")
            logger.info(f"  Regions detected: {len(regions)}")
            logger.info(f"  Valid bboxes: {validation['valid_bboxes']}/{validation['total_regions']}")
            logger.info(f"  Region types: {type_counts}")
            
            if validation['invalid_bboxes'] > 0:
                logger.warning(f"  Invalid bboxes: {validation['invalid_bboxes']}")
                for issue in validation['issues']:
                    logger.warning(f"    {issue}")
            
            # Print sample regions
            logger.info(f"\nSample regions (first 5):")
            for i, region in enumerate(regions[:5]):
                bbox = region.get('bbox', [])
                region_type = region.get('type', 'unknown')
                confidence = region.get('confidence', 0)
                logger.info(f"  Region {i}: {region_type} - bbox: {bbox} - confidence: {confidence:.3f}")
            
            # Save detailed results
            result_file = f"paddleocr_direct_result_{Path(image_path).stem}.json"
            result_data = {
                "image": image_path,
                "dimensions": {"width": width, "height": height},
                "regions": regions,
                "validation": validation,
                "type_counts": type_counts,
                "timestamp": time.time(),
                "gpu_mode": self.use_gpu,
                "gpu_available": self.gpu_available
            }
            
            with open(result_file, 'w') as f:
                json.dump(result_data, f, indent=2)
            
            logger.info(f"\nDetailed results saved to: {result_file}")
            
            # Check if we have multiple valid regions
            if validation['valid_bboxes'] > 1:
                logger.info("✓ Multiple valid regions detected - layout detection is working!")
                return True
            else:
                logger.warning("⚠️  Only one or no valid regions detected")
                return validation['valid_bboxes'] > 0
            
        except Exception as e:
            logger.error(f"Test failed for {image_path}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run_comprehensive_test(self) -> bool:
        """Run comprehensive test suite."""
        logger.info("=" * 80)
        logger.info(f"PaddleOCR Direct Layout Detection Test ({'GPU' if self.use_gpu else 'CPU'} mode)")
        logger.info("=" * 80)
        
        # Check GPU availability
        if self.use_gpu:
            if not self.check_gpu_availability():
                logger.warning("GPU not available, falling back to CPU mode")
                self.use_gpu = False
        
        # Initialize PaddleOCR
        if not self.initialize_paddleocr():
            logger.error("Failed to initialize PaddleOCR")
            return False
        
        # Test each image
        all_passed = True
        test_results = []
        
        for image_path in TEST_IMAGES:
            if not os.path.exists(image_path):
                logger.warning(f"Image not found: {image_path}, skipping...")
                continue
            
            passed = self.test_image(image_path)
            test_results.append({
                "image": image_path,
                "passed": passed
            })
            
            if not passed:
                all_passed = False
        
        # Print summary
        logger.info(f"\n{'='*80}")
        logger.info("TEST SUMMARY")
        logger.info(f"{'='*80}")
        
        total_tests = len(test_results)
        passed_tests = sum(1 for r in test_results if r['passed'])
        
        logger.info(f"Mode: {'GPU' if self.use_gpu else 'CPU'}")
        logger.info(f"GPU available: {self.gpu_available}")
        logger.info(f"Tests run: {total_tests}")
        logger.info(f"Tests passed: {passed_tests}")
        
        for result in test_results:
            status = "✓" if result['passed'] else "✗"
            logger.info(f"  {status} {result['image']}")
        
        if all_passed and total_tests > 0:
            logger.info(f"\n✅ All tests passed!")
            return True
        else:
            logger.error(f"\n❌ Some tests failed")
            return False


def main():
    """Main test function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Direct test of PaddleOCR layout detection")
    parser.add_argument("--gpu", action="store_true", help="Test with GPU support")
    parser.add_argument("--cpu", action="store_true", help="Test with CPU only")
    parser.add_argument("--image", type=str, help="Specific image to test")
    parser.add_argument("--check-gpu", action="store_true", help="Check GPU availability only")
    
    args = parser.parse_args()
    
    # Update test images if specific image provided
    if args.image:
        global TEST_IMAGES
        TEST_IMAGES = [args.image]
    
    # Check GPU only
    if args.check_gpu:
        tester = PaddleOCRDirectTester(use_gpu=True)
        tester.check_gpu_availability()
        return
    
    # Determine test mode
    use_gpu = not args.cpu  # Default to GPU unless CPU specified
    
    tester = PaddleOCRDirectTester(use_gpu=use_gpu)
    
    if tester.run_comprehensive_test():
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()