#!/usr/bin/env python3
"""
Check the status of PaddleOCR and GLM-OCR services.
This helps identify what needs to be implemented before testing.
"""

import requests
import sys
import os
from pathlib import Path

def check_paddleocr_service():
    """Check if PaddleOCR service is implemented and running."""
    print("="*60)
    print("PaddleOCR Service Status Check")
    print("="*60)
    
    # Check if files exist
    required_files = [
        "services/paddleocr-service/app/config.py",
        "services/paddleocr-service/app/main.py",
        "services/paddleocr-service/app/layout_detector.py",
        "services/paddleocr-service/app/models.py",
    ]
    
    for file_path in required_files:
        if Path(file_path).exists():
            print(f"✅ {file_path} exists")
        else:
            print(f"❌ {file_path} missing")
    
    # Check if service is running
    try:
        response = requests.get("http://localhost:8001/health", timeout=2)
        if response.status_code == 200:
            print(f"✅ PaddleOCR service is running on http://localhost:8001")
            print(f"   Response: {response.json()}")
            return True
        else:
            print(f"⚠️ PaddleOCR service returned {response.status_code}")
            return False
    except requests.exceptions.RequestException:
        print("❌ PaddleOCR service is not running")
        print("   To start it, you need to complete these tasks first:")
        print("   1. Task 1.3: Implement PPStructureV3 model wrapper")
        print("   2. Task 1.4: Implement Pydantic models")
        print("   3. Task 1.5: Implement FastAPI application")
        print("   4. Task 1.6: Implement image preprocessing")
        print("   5. Task 1.7: Add logging and monitoring")
        return False

def check_glmocr_service():
    """Check if GLM-OCR service is running."""
    print("\n" + "="*60)
    print("GLM-OCR Service Status Check")
    print("="*60)
    
    # Check common endpoints
    endpoints_to_try = [
        "http://localhost:8002/health",
        "http://localhost:8002/",
        "http://localhost:8002/jobs/upload",
    ]
    
    for endpoint in endpoints_to_try:
        try:
            response = requests.get(endpoint, timeout=2)
            if response.status_code < 500:
                print(f"✅ GLM-OCR service is reachable at {endpoint}")
                print(f"   Status: {response.status_code}")
                return True
        except requests.exceptions.RequestException:
            continue
    
    print("❌ GLM-OCR service is not reachable")
    print("   The GLM-OCR service needs to be running for testing.")
    print("   Check if it's started or if you need to modify it for the new endpoints.")
    return False

def check_test_images():
    """Check if test images are available."""
    print("\n" + "="*60)
    print("Test Images Check")
    print("="*60)
    
    test_images = []
    
    # Check for PNG test images
    for img in Path(".").glob("test_*.png"):
        test_images.append(str(img))
    
    # Check for PDF test images
    testfiles_dir = Path("testfiles")
    if testfiles_dir.exists():
        for img in testfiles_dir.glob("*.pdf"):
            test_images.append(str(img))
    
    if test_images:
        print(f"✅ Found {len(test_images)} test images:")
        for img in test_images[:5]:  # Show first 5
            print(f"   - {img}")
        if len(test_images) > 5:
            print(f"   ... and {len(test_images) - 5} more")
        return True
    else:
        print("❌ No test images found")
        print("   Create test images or use the existing ones:")
        print("   - test_simple.png (should exist)")
        print("   - test_invoice_local.png (should exist)")
        return False

def main():
    print("Microservices Architecture Implementation Status")
    print("="*60)
    
    paddleocr_ready = check_paddleocr_service()
    glmocr_ready = check_glmocr_service()
    images_ready = check_test_images()
    
    print("\n" + "="*60)
    print("IMPLEMENTATION ROADMAP")
    print("="*60)
    
    if not paddleocr_ready:
        print("\n🚧 PaddleOCR Service needs implementation:")
        print("   1. Complete Task 1.3: Implement PPStructureV3 model wrapper")
        print("      - Create services/paddleocr-service/app/layout_detector.py")
        print("      - Initialize PPStructureV3 with configurable options")
        print("      - Implement detect_regions() method")
        print("      - Add confidence filtering logic")
        print("      - Handle both CPU and GPU execution modes")
        print("      - Add model version tracking")
        print("")
        print("   2. Complete Task 1.4: Implement Pydantic models")
        print("      - Create services/paddleocr-service/app/models.py")
        print("      - Define Region, PageDimensions, DetectLayoutRequest models")
        print("      - Define DetectLayoutResponse, HealthResponse models")
        print("")
        print("   3. Complete Task 1.5: Implement FastAPI application")
        print("      - Create services/paddleocr-service/app/main.py")
        print("      - Implement /detect-layout POST endpoint")
        print("      - Implement /health GET endpoint")
        print("      - Add request validation and error handling")
        print("")
        print("   4. Complete remaining tasks (1.6, 1.7)")
        print("")
        print("   Once implemented, start the service:")
        print("   $ cd services/paddleocr-service")
        print("   $ python -m app.main")
    
    if not glmocr_ready:
        print("\n🚧 GLM-OCR Service needs to be running:")
        print("   The GLM-OCR service exists but needs to be started.")
        print("   Check the documentation for how to start it.")
        print("   It should run on http://localhost:8002")
    
    if not images_ready:
        print("\n🚧 Test images needed:")
        print("   Create test images or ensure existing ones are available")
    
    if paddleocr_ready and glmocr_ready and images_ready:
        print("\n🎉 Ready for real-time extraction testing!")
        print("   Run: python test_realtime_extraction.py --image test_simple.png")
    else:
        print("\n🔧 Work needed before testing real-time extraction.")
        print("   Complete the implementation steps above first.")

if __name__ == "__main__":
    main()