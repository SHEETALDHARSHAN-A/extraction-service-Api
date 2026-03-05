"""
Local E2E test for GLM-OCR service with fast mode and coordinates.
Tests the /extract-region endpoint directly (no Docker, no API Gateway).

Prerequisites:
1. Start the GLM-OCR service locally:
   cd services/glm-ocr-service
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8002

2. Run this test:
   python test_glm_service_local.py
"""

import base64
import io
import json
import requests
from PIL import Image, ImageDraw, ImageFont


def create_test_image():
    """Create a test invoice image with 3 lines of text."""
    print("\n" + "="*60)
    print("Creating test image...")
    print("="*60)
    
    # Create ima