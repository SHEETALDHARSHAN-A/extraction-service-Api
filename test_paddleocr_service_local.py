"""
Comprehensive local test for PaddleOCR Layout Detection Service.

This script tests:
1. Service startup with GPU support
2. Layout detection with bounding boxes
3. Multiple test images
4. Configuration validation
5. Performance metrics
"""

import os
import sys
import time
import json
import base64
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
import subprocess
import requests
from PIL import Image
import io

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Service configuration
SERVICE_HOST = "localhost"
SERVICE_PORT = 8001
SERVICE_URL = f"http://{SERVICE_HOST}:{SERVICE_PORT}"
HEALTH_ENDPOINT = f"{SERVICE_URL}/health"
DETECT_ENDPOINT = f"{SERVICE_URL}/detect-layout"

# Test images
TEST_IMAGES = [
    "test_simple.png",
    "test_invoice_local.png",
    # Add more test images as needed
]

# GPU test configuration
GPU_TEST_ENV = {
    "PADDLEOCR_USE_GPU": "true",
    "LOG_LEVEL": "DEBUG",
    "SERVICE_HOST": "0.0.0.0",
    "SERVICE_PORT": str(SERVICE_PORT),
}

CPU_TEST_ENV = {
    "PADDLEOCR_USE_GPU": "false",
    "LOG_LEVEL": "DEBUG",
    "SERVICE_HOST": "0.0.0.0",
    "SERVICE_PORT": str(SERVICE_PORT),
}


class PaddleOCRServiceTester:
    """Test the PaddleOCR Layout Detection Service."""
    
    def __init__(self, use_gpu: bool = True):
        self.use_gpu = use_gpu
        self.env_vars = GPU_TEST_ENV if use_gpu else CPU_TEST_ENV
        self.service_process = None
        self.test_results = []
        
    def encode_image_to_base64(self, image_path: str) -> str:
        """Encode image to base64 string."""
        try:
            with open(image_path, "rb") as image_file:
                image_bytes = image_file.read()
                return base64.b64encode(image_bytes).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to encode image {image_path}: {e}")
            raise
    
    def check_service_health(self, timeout: int = 30) -> bool:
        """Check if service is healthy."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(HEALTH_ENDPOINT, timeout=5)
                if response.status_code == 200:
                    health_data = response.json()
                    logger.info(f"Service health: {health_data}")
                    
                    # Check if GPU is available if we're testing GPU mode
                    if self.use_gpu:
                        gpu_available = health_data.get("gpu_available", False)
                        device = health_data.get("device", "cpu")
                        models_loaded = health_data.get("models_loaded", False)
                        
                        if not models_loaded:
                            logger.warning("Models not loaded yet, waiting...")
                            time.sleep(2)
                            continue
                        
                        if gpu_available and device == "cuda":
                            logger.info("✓ GPU mode is active")
                        else:
                            logger.warning(f"GPU not active: gpu_available={gpu_available}, device={device}")
                    
                    return True
            except requests.exceptions.RequestException as e:
                logger.debug(f"Service not ready yet: {e}")
                time.sleep(1)
        
        logger.error(f"Service health check failed after {timeout} seconds")
        return False
    
    def start_service(self) -> bool:
        """Start the PaddleOCR service."""
        logger.info(f"Starting PaddleOCR service with {'GPU' if self.use_gpu else 'CPU'} support...")
        
        # Change to service directory
        service_dir = Path("services/paddleocr-service")
        if not service_dir.exists():
            logger.error(f"Service directory not found: {service_dir}")
            return False
        
        # Set environment variables
        env = os.environ.copy()
        env.update(self.env_vars)
        
        # Start the service
        try:
            self.service_process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app.main:app", 
                 "--host", "0.0.0.0", "--port", str(SERVICE_PORT)],
                cwd=service_dir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            logger.info(f"Service started with PID: {self.service_process.pid}")
            
            # Wait for service to start
            time.sleep(5)
            
            # Check health
            if self.check_service_health():
                logger.info("✓ Service started successfully")
                return True
            else:
                logger.error("Service failed to start")
                return False
                
        except Exception as e:
            logger.error(f"Failed to start service: {e}")
            return False
    
    def stop_service(self):
        """Stop the PaddleOCR service."""
        if self.service_process:
            logger.info("Stopping service...")
            self.service_process.terminate()
            try:
                self.service_process.wait(timeout=10)
                logger.info("Service stopped")
            except subprocess.TimeoutExpired:
                logger.warning("Service did not stop gracefully, forcing...")
                self.service_process.kill()
            self.service_process = None
    
    def test_detect_layout(self, image_path: str) -> Optional[Dict[str, Any]]:
        """Test the /detect-layout endpoint."""
        logger.info(f"Testing layout detection for: {image_path}")
        
        if not os.path.exists(image_path):
            logger.error(f"Test image not found: {image_path}")
            return None
        
        try:
            # Encode image
            image_base64 = self.encode_image_to_base64(image_path)
            
            # Prepare request
            request_data = {
                "image": image_base64,
                "options": {
                    "min_confidence": 0.3,
                    "detect_tables": True,
                    "detect_formulas": True,
                    "return_image_dimensions": True
                }
            }
            
            # Send request
            start_time = time.time()
            response = requests.post(
                DETECT_ENDPOINT,
                json=request_data,
                timeout=30
            )
            processing_time = time.time() - start_time
            
            if response.status_code != 200:
                logger.error(f"Request failed: {response.status_code} - {response.text}")
                return None
            
            result = response.json()
            
            # Log results
            logger.info(f"✓ Layout detection completed in {processing_time:.2f}s")
            logger.info(f"  Regions detected: {len(result.get('regions', []))}")
            logger.info(f"  Processing time: {result.get('processing_time_ms', 0):.2f}ms")
            logger.info(f"  Model version: {result.get('model_version', 'unknown')}")
            
            # Validate bounding boxes
            regions = result.get('regions', [])
            if regions:
                logger.info("  Bounding boxes found:")
                for i, region in enumerate(regions):
                    bbox = region.get('bbox', [])
                    region_type = region.get('type', 'unknown')
                    confidence = region.get('confidence', 0)
                    logger.info(f"    Region {i}: {region_type} - bbox: {bbox} - confidence: {confidence:.3f}")
            
            return result
            
        except Exception as e:
            logger.error(f"Layout detection test failed: {e}")
            return None
    
    def validate_bboxes(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate bounding boxes in the result."""
        validation_result = {
            "total_regions": 0,
            "valid_bboxes": 0,
            "invalid_bboxes": 0,
            "bbox_details": []
        }
        
        regions = result.get('regions', [])
        validation_result["total_regions"] = len(regions)
        
        for i, region in enumerate(regions):
            bbox = region.get('bbox', [])
            region_type = region.get('type', 'unknown')
            
            bbox_info = {
                "index": i,
                "type": region_type,
                "bbox": bbox,
                "valid": False,
                "issues": []
            }
            
            # Check bbox format
            if not isinstance(bbox, list):
                bbox_info["issues"].append("bbox is not a list")
            elif len(bbox) != 4:
                bbox_info["issues"].append(f"bbox has {len(bbox)} elements, expected 4")
            else:
                x1, y1, x2, y2 = bbox
                
                # Check coordinates are integers
                if not all(isinstance(coord, (int, float)) for coord in bbox):
                    bbox_info["issues"].append("bbox coordinates are not numbers")
                
                # Check bbox dimensions
                elif x2 <= x1:
                    bbox_info["issues"].append(f"x2 ({x2}) <= x1 ({x1})")
                elif y2 <= y1:
                    bbox_info["issues"].append(f"y2 ({y2}) <= y1 ({y1})")
                
                # Check bbox is within page dimensions
                else:
                    page_dims = result.get('page_dimensions')
                    if page_dims:
                        width = page_dims.get('width', 0)
                        height = page_dims.get('height', 0)
                        
                        if x1 < 0 or y1 < 0 or x2 > width or y2 > height:
                            bbox_info["issues"].append(
                                f"bbox [{x1}, {y1}, {x2}, {y2}] outside page [{width}x{height}]"
                            )
                        else:
                            bbox_info["valid"] = True
                            validation_result["valid_bboxes"] += 1
                    else:
                        bbox_info["valid"] = True
                        validation_result["valid_bboxes"] += 1
            
            if not bbox_info["valid"]:
                validation_result["invalid_bboxes"] += 1
            
            validation_result["bbox_details"].append(bbox_info)
        
        return validation_result
    
    def run_comprehensive_test(self) -> bool:
        """Run comprehensive test suite."""
        logger.info("=" * 80)
        logger.info(f"Starting PaddleOCR Service Test ({'GPU' if self.use_gpu else 'CPU'} mode)")
        logger.info("=" * 80)
        
        all_passed = True
        
        try:
            # Step 1: Start service
            if not self.start_service():
                logger.error("Failed to start service")
                return False
            
            # Step 2: Test with each image
            for image_path in TEST_IMAGES:
                if not os.path.exists(image_path):
                    logger.warning(f"Test image not found: {image_path}, skipping...")
                    continue
                
                logger.info(f"\n{'='*60}")
                logger.info(f"Testing: {image_path}")
                logger.info(f"{'='*60}")
                
                # Test layout detection
                result = self.test_detect_layout(image_path)
                if not result:
                    logger.error(f"✗ Layout detection failed for {image_path}")
                    all_passed = False
                    continue
                
                # Validate bounding boxes
                validation = self.validate_bboxes(result)
                
                logger.info(f"\nBounding Box Validation:")
                logger.info(f"  Total regions: {validation['total_regions']}")
                logger.info(f"  Valid bboxes: {validation['valid_bboxes']}")
                logger.info(f"  Invalid bboxes: {validation['invalid_bboxes']}")
                
                if validation['invalid_bboxes'] > 0:
                    logger.warning("  Issues found:")
                    for bbox_info in validation['bbox_details']:
                        if not bbox_info['valid']:
                            logger.warning(f"    Region {bbox_info['index']} ({bbox_info['type']}): {bbox_info['issues']}")
                
                # Save result for inspection
                result_file = f"paddleocr_test_result_{Path(image_path).stem}.json"
                with open(result_file, 'w') as f:
                    json.dump({
                        "image": image_path,
                        "result": result,
                        "validation": validation,
                        "timestamp": time.time(),
                        "gpu_mode": self.use_gpu
                    }, f, indent=2)
                
                logger.info(f"  Result saved to: {result_file}")
                
                # Check if we got multiple regions (not just full-page)
                regions = result.get('regions', [])
                if len(regions) <= 1:
                    logger.warning("⚠️  Only one region detected - may be full-page mode")
                else:
                    logger.info("✓ Multiple regions detected - layout detection is working!")
                
                self.test_results.append({
                    "image": image_path,
                    "success": True,
                    "regions": len(regions),
                    "validation": validation
                })
            
            # Step 3: Print summary
            logger.info(f"\n{'='*80}")
            logger.info("TEST SUMMARY")
            logger.info(f"{'='*80}")
            
            total_tests = len(self.test_results)
            passed_tests = sum(1 for r in self.test_results if r['success'])
            
            logger.info(f"Mode: {'GPU' if self.use_gpu else 'CPU'}")
            logger.info(f"Tests run: {total_tests}")
            logger.info(f"Tests passed: {passed_tests}")
            
            if total_tests > 0:
                for result in self.test_results:
                    status = "✓" if result['success'] else "✗"
                    logger.info(f"  {status} {result['image']}: {result['regions']} regions")
            
            if passed_tests == total_tests and total_tests > 0:
                logger.info(f"\n✅ All tests passed!")
                all_passed = True
            else:
                logger.error(f"\n❌ Some tests failed")
                all_passed = False
            
        finally:
            # Step 4: Stop service
            self.stop_service()
        
        return all_passed
    
    def test_gpu_detection(self) -> bool:
        """Test if GPU is properly detected and used."""
        logger.info("\nTesting GPU detection...")
        
        # Check if paddlepaddle-gpu is installed
        try:
            import paddle
            has_cuda = paddle.is_compiled_with_cuda()
            device_count = paddle.device.cuda.device_count()
            
            logger.info(f"PaddlePaddle CUDA support: {has_cuda}")
            logger.info(f"CUDA devices available: {device_count}")
            
            if has_cuda and device_count > 0:
                current_device = paddle.get_device()
                logger.info(f"Current device: {current_device}")
                return True
            else:
                logger.warning("CUDA not available in PaddlePaddle")
                return False
                
        except ImportError:
            logger.error("PaddlePaddle not installed")
            return False
        except Exception as e:
            logger.error(f"GPU detection failed: {e}")
            return False


def main():
    """Main test function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test PaddleOCR Layout Detection Service")
    parser.add_argument("--gpu", action="store_true", help="Test with GPU support")
    parser.add_argument("--cpu", action="store_true", help="Test with CPU only")
    parser.add_argument("--both", action="store_true", help="Test both GPU and CPU modes")
    parser.add_argument("--image", type=str, help="Specific image to test")
    parser.add_argument("--check-gpu", action="store_true", help="Check GPU availability only")
    
    args = parser.parse_args()
    
    # Update test images if specific image provided
    if args.image:
        global TEST_IMAGES
        TEST_IMAGES = [args.image]
    
    # Check GPU only
    if args.check_gpu:
        tester = PaddleOCRServiceTester(use_gpu=True)
        tester.test_gpu_detection()
        return
    
    # Determine test modes
    if args.both:
        test_modes = [True, False]  # GPU then CPU
    elif args.cpu:
        test_modes = [False]
    else:
        test_modes = [True]  # Default to GPU
    
    all_passed = True
    
    for use_gpu in test_modes:
        tester = PaddleOCRServiceTester(use_gpu=use_gpu)
        
        # Check GPU availability if testing GPU mode
        if use_gpu:
            if not tester.test_gpu_detection():
                logger.warning("GPU not available, falling back to CPU mode")
                use_gpu = False
                tester = PaddleOCRServiceTester(use_gpu=False)
        
        passed = tester.run_comprehensive_test()
        all_passed = all_passed and passed
        
        # Small delay between tests
        if len(test_modes) > 1 and use_gpu != test_modes[-1]:
            time.sleep(2)
    
    if all_passed:
        logger.info("\n" + "="*80)
        logger.info("✅ ALL TESTS COMPLETED SUCCESSFULLY!")
        logger.info("="*80)
        sys.exit(0)
    else:
        logger.error("\n" + "="*80)
        logger.error("❌ SOME TESTS FAILED")
        logger.error("="*80)
        sys.exit(1)


if __name__ == "__main__":
    main()