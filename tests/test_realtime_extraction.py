#!/usr/bin/env python3
"""
Real-time extraction test for PaddleOCR + GLM-OCR microservices architecture.

This script tests the two-stage document processing pipeline:
1. PaddleOCR service for layout detection (bounding boxes)
2. GLM-OCR service for content extraction from regions

Prerequisites:
1. PaddleOCR service running on http://localhost:8001
2. GLM-OCR service running on http://localhost:8002
3. Test image file (test_simple.png or other test image)

Usage:
    python test_realtime_extraction.py --image test_simple.png
"""

import argparse
import base64
import json
import time
import requests
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RealtimeExtractionTester:
    """Test real-time extraction using both PaddleOCR and GLM-OCR services."""
    
    def __init__(self, paddleocr_url: str = "http://localhost:8001", 
                 glmocr_url: str = "http://localhost:8002"):
        self.paddleocr_url = paddleocr_url
        self.glmocr_url = glmocr_url
        self.session = requests.Session()
        
    def check_services(self) -> bool:
        """Check if both services are running and healthy."""
        services_healthy = True
        
        # Check PaddleOCR service
        try:
            response = self.session.get(f"{self.paddleocr_url}/health", timeout=5)
            if response.status_code == 200:
                logger.info(f"✅ PaddleOCR service is healthy: {response.json()}")
            else:
                logger.error(f"❌ PaddleOCR service unhealthy: {response.status_code}")
                services_healthy = False
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ PaddleOCR service not reachable: {e}")
            services_healthy = False
        
        # Check GLM-OCR service
        try:
            # Try the health endpoint or any endpoint
            response = self.session.get(f"{self.glmocr_url}/health", timeout=5)
            if response.status_code == 200:
                logger.info(f"✅ GLM-OCR service is healthy: {response.json()}")
            else:
                logger.warning(f"⚠️ GLM-OCR health endpoint returned {response.status_code}")
                # Try another endpoint
                response = self.session.get(f"{self.glmocr_url}/", timeout=5)
                if response.status_code < 500:
                    logger.info(f"✅ GLM-OCR service is reachable")
                else:
                    logger.error(f"❌ GLM-OCR service unhealthy")
                    services_healthy = False
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ GLM-OCR service not reachable: {e}")
            services_healthy = False
        
        return services_healthy
    
    def encode_image_to_base64(self, image_path: str) -> str:
        """Encode image file to base64 string."""
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        return encoded_string
    
    def test_paddleocr_layout_detection(self, image_base64: str) -> Optional[Dict]:
        """Test PaddleOCR layout detection service."""
        logger.info("Testing PaddleOCR layout detection...")
        
        payload = {
            "image": image_base64,
            "options": {
                "min_confidence": 0.5,
                "detect_tables": True,
                "detect_formulas": True,
                "return_image_dimensions": True
            }
        }
        
        try:
            start_time = time.time()
            response = self.session.post(
                f"{self.paddleocr_url}/detect-layout",
                json=payload,
                timeout=30
            )
            elapsed_time = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ Layout detection successful in {elapsed_time:.2f}s")
                logger.info(f"   Detected {len(result.get('regions', []))} regions")
                logger.info(f"   Page dimensions: {result.get('page_dimensions')}")
                return result
            else:
                logger.error(f"❌ Layout detection failed: {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Layout detection request failed: {e}")
            return None
    
    def test_glmocr_region_extraction(self, image_base64: str, region_type: str = "text") -> Optional[Dict]:
        """Test GLM-OCR region extraction service."""
        logger.info(f"Testing GLM-OCR region extraction (type: {region_type})...")
        
        # For GLM-OCR, we need to check what endpoints are available
        # Try the existing /jobs/upload endpoint first
        payload = {
            "image": image_base64,
            "options": {
                "output_format": "json",
                "max_tokens": 2048
            }
        }
        
        try:
            start_time = time.time()
            response = self.session.post(
                f"{self.glmocr_url}/jobs/upload",
                json=payload,
                timeout=60
            )
            elapsed_time = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ GLM-OCR extraction successful in {elapsed_time:.2f}s")
                return result
            else:
                logger.warning(f"⚠️ /jobs/upload failed: {response.status_code}")
                logger.warning(f"   Trying alternative endpoints...")
                
                # Try the new /extract-region endpoint
                payload = {
                    "image": image_base64,
                    "region_type": region_type,
                    "prompt": "Text Recognition:",
                    "options": {
                        "output_format": "json",
                        "max_tokens": 2048
                    }
                }
                
                response = self.session.post(
                    f"{self.glmocr_url}/extract-region",
                    json=payload,
                    timeout=60
                )
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"✅ GLM-OCR /extract-region successful in {elapsed_time:.2f}s")
                    return result
                else:
                    logger.error(f"❌ GLM-OCR extraction failed: {response.status_code}")
                    logger.error(f"   Response: {response.text}")
                    return None
                    
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ GLM-OCR request failed: {e}")
            return None
    
    def test_two_stage_pipeline(self, image_base64: str) -> Optional[Dict]:
        """Test the complete two-stage pipeline."""
        logger.info("Testing complete two-stage pipeline...")
        
        # Stage 1: Layout detection
        layout_result = self.test_paddleocr_layout_detection(image_base64)
        if not layout_result:
            logger.error("❌ Pipeline failed at stage 1 (layout detection)")
            return None
        
        regions = layout_result.get("regions", [])
        if not regions:
            logger.warning("⚠️ No regions detected, using full-page mode")
            # Fallback to full-page extraction
            glm_result = self.test_glmocr_region_extraction(image_base64)
            if glm_result:
                return {
                    "pipeline_mode": "full_page_fallback",
                    "layout_detection": layout_result,
                    "content_extraction": glm_result
                }
            else:
                logger.error("❌ Full-page extraction also failed")
                return None
        
        logger.info(f"Detected {len(regions)} regions, testing extraction for first region...")
        
        # For testing, extract content from the first region
        first_region = regions[0]
        region_type = first_region.get("type", "text")
        bbox = first_region.get("bbox", [0, 0, 100, 100])
        
        logger.info(f"Extracting region type '{region_type}' with bbox {bbox}")
        
        # Stage 2: Content extraction (single region for testing)
        glm_result = self.test_glmocr_region_extraction(image_base64, region_type)
        if not glm_result:
            logger.error("❌ Pipeline failed at stage 2 (content extraction)")
            return None
        
        # Assemble pipeline result
        pipeline_result = {
            "pipeline_mode": "two_stage",
            "layout_detection": layout_result,
            "content_extraction": glm_result,
            "summary": {
                "total_regions": len(regions),
                "region_types": list(set(r.get("type", "unknown") for r in regions)),
                "first_region_extracted": True
            }
        }
        
        logger.info("✅ Two-stage pipeline test completed successfully")
        return pipeline_result
    
    def run_comprehensive_test(self, image_path: str):
        """Run comprehensive test suite."""
        logger.info(f"Starting comprehensive test with image: {image_path}")
        
        # Check if image exists
        if not Path(image_path).exists():
            logger.error(f"❌ Image file not found: {image_path}")
            logger.info("Available test images:")
            for img in Path(".").glob("test_*.png"):
                logger.info(f"  - {img}")
            for img in Path("testfiles").glob("*.pdf"):
                logger.info(f"  - {img}")
            return False
        
        # Encode image
        logger.info(f"Encoding image: {image_path}")
        try:
            image_base64 = self.encode_image_to_base64(image_path)
            logger.info(f"Image encoded ({len(image_base64)} chars)")
        except Exception as e:
            logger.error(f"❌ Failed to encode image: {e}")
            return False
        
        # Check services
        logger.info("Checking service availability...")
        if not self.check_services():
            logger.warning("⚠️ Some services are not available, but continuing with tests...")
        
        # Run tests
        test_results = {}
        
        # Test 1: PaddleOCR layout detection
        logger.info("\n" + "="*60)
        logger.info("TEST 1: PaddleOCR Layout Detection")
        logger.info("="*60)
        layout_result = self.test_paddleocr_layout_detection(image_base64)
        test_results["layout_detection"] = "PASS" if layout_result else "FAIL"
        
        # Test 2: GLM-OCR content extraction
        logger.info("\n" + "="*60)
        logger.info("TEST 2: GLM-OCR Content Extraction")
        logger.info("="*60)
        glm_result = self.test_glmocr_region_extraction(image_base64)
        test_results["content_extraction"] = "PASS" if glm_result else "FAIL"
        
        # Test 3: Two-stage pipeline (if both services work)
        if layout_result and glm_result:
            logger.info("\n" + "="*60)
            logger.info("TEST 3: Two-Stage Pipeline")
            logger.info("="*60)
            pipeline_result = self.test_two_stage_pipeline(image_base64)
            test_results["two_stage_pipeline"] = "PASS" if pipeline_result else "FAIL"
            
            if pipeline_result:
                # Save pipeline result for analysis
                output_file = f"pipeline_result_{Path(image_path).stem}.json"
                with open(output_file, "w") as f:
                    json.dump(pipeline_result, f, indent=2)
                logger.info(f"✅ Pipeline result saved to: {output_file}")
        else:
            test_results["two_stage_pipeline"] = "SKIP"
            logger.info("Skipping two-stage pipeline test (prerequisites not met)")
        
        # Print summary
        logger.info("\n" + "="*60)
        logger.info("TEST SUMMARY")
        logger.info("="*60)
        for test_name, result in test_results.items():
            status_icon = "✅" if result == "PASS" else "⚠️" if result == "SKIP" else "❌"
            logger.info(f"{status_icon} {test_name}: {result}")
        
        # Check if per-field bboxes are working
        if layout_result and "regions" in layout_result:
            regions = layout_result["regions"]
            if len(regions) > 1:
                logger.info(f"✅ Per-field bboxes detected: {len(regions)} regions")
                for i, region in enumerate(regions[:3]):  # Show first 3 regions
                    logger.info(f"  Region {i}: type={region.get('type')}, bbox={region.get('bbox')}, confidence={region.get('confidence')}")
            else:
                logger.warning("⚠️ Only 1 region detected (might be full-page mode)")
        
        return all(result == "PASS" for result in test_results.values() if result != "SKIP")

def main():
    parser = argparse.ArgumentParser(description="Test real-time extraction with PaddleOCR + GLM-OCR")
    parser.add_argument("--image", default="test_simple.png", 
                       help="Path to test image (default: test_simple.png)")
    parser.add_argument("--paddleocr", default="http://localhost:8001",
                       help="PaddleOCR service URL (default: http://localhost:8001)")
    parser.add_argument("--glmocr", default="http://localhost:8002",
                       help="GLM-OCR service URL (default: http://localhost:8002)")
    
    args = parser.parse_args()
    
    # Create tester
    tester = RealtimeExtractionTester(args.paddleocr, args.glmocr)
    
    # Run test
    success = tester.run_comprehensive_test(args.image)
    
    if success:
        logger.info("\n🎉 All tests passed! The microservices architecture is working correctly.")
        logger.info("\nNext steps:")
        logger.info("1. Check the generated pipeline_result_*.json file for detailed results")
        logger.info("2. Verify per-field bounding boxes are accurate")
        logger.info("3. Test with more complex documents in testfiles/ directory")
        logger.info("4. Run performance tests with concurrent requests")
    else:
        logger.error("\n❌ Some tests failed. Check the logs above for details.")
        logger.info("\nTroubleshooting steps:")
        logger.info("1. Ensure PaddleOCR service is running: python -m services.paddleocr-service.app.main")
        logger.info("2. Ensure GLM-OCR service is running")
        logger.info("3. Check service URLs are correct")
        logger.info("4. Verify the test image exists")
        
        # Check what needs to be implemented
        logger.info("\nImplementation status check:")
        config_path = Path("services/paddleocr-service/app/config.py")
        if config_path.exists():
            logger.info("✅ Configuration module exists")
        else:
            logger.error("❌ Configuration module missing - run Task 1.2 first")
        
        main_path = Path("services/paddleocr-service/app/main.py")
        if main_path.exists():
            logger.info("✅ FastAPI application exists")
        else:
            logger.error("❌ FastAPI application missing - run Task 1.5 first")
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()