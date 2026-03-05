"""Simple GLM-OCR Service Test

This script tests the GLM-OCR service directly with a simple document.
"""
import requests
import json
import base64
from PIL import Image, ImageDraw, ImageFont
import io

# Configuration
GLM_SERVICE_URL = "http://localhost:8002"
EXTRACT_ENDPOINT = f"{GLM_SERVICE_URL}/extract"

def generate_test_image():
    """Generate a simple test invoice image."""
    print("=" * 80)
    print("GENERATING TEST IMAGE")
    print("=" * 80)
    
    # Create image
    width, height = 1200, 900
    image = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(image)
    
    # Try to use a font
    try:
        font_large = ImageFont.truetype("arial.ttf", 60)
        font_small = ImageFont.truetype("arial.ttf", 40)
    except:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()
    
    # Draw invoice content
    draw.text((50, 50), "INVOICE #A-1001", fill='black', font=font_large)
    draw.text((50, 200), "DATE: 2026-03-05", fill='black', font=font_small)
    draw.text((50, 300), "CUSTOMER: ACME Corp", fill='black', font=font_small)
    draw.text((50, 500), "ITEM: Widget A", fill='black', font=font_small)
    draw.text((50, 600), "QUANTITY: 10", fill='black', font=font_small)
    draw.text((50, 700), "TOTAL: $999.00", fill='black', font=font_large)
    
    # Convert to base64
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    image_base64 = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
    
    print(f"✓ Generated test invoice image")
    print(f"  Dimensions: {width}x{height}px")
    print(f"  Size: {len(img_byte_arr.getvalue())} bytes")
    print()
    
    return image_base64, width, height

def test_extraction(image_base64, width, height):
    """Test GLM-OCR extraction with fast mode."""
    print("=" * 80)
    print("TESTING GLM-OCR EXTRACTION")
    print("=" * 80)
    
    # Prepare request
    request_data = {
        "image": image_base64,
        "options": {
            "fast_mode": True,
            "include_coordinates": True,
            "include_confidence": True,
            "granularity": "word",
            "output_format": "text",
            "max_tokens": 512
        },
        "image_width": width,
        "image_height": height
    }
    
    print(f"\nSending request to: {EXTRACT_ENDPOINT}")
    print(f"Options:")
    print(f"  - fast_mode: True")
    print(f"  - include_coordinates: True")
    print(f"  - granularity: word")
    print()
    
    try:
        response = requests.post(
            EXTRACT_ENDPOINT,
            json=request_data,
            headers={"Content-Type": "application/json"},
            timeout=60
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✓ Extraction successful!")
            print()
            
            # Print extracted content
            if result.get('content'):
                print("Extracted Content:")
                print("-" * 80)
                print(result['content'])
                print("-" * 80)
                print()
            
            # Print bounding boxes
            if result.get('bounding_boxes'):
                bboxes = result['bounding_boxes']
                print(f"Bounding Boxes: {len(bboxes)} found")
                print()
                
                for i, bbox_data in enumerate(bboxes[:5]):  # Show first 5
                    bbox = bbox_data.get('bbox', [])
                    text = bbox_data.get('text', '')
                    confidence = bbox_data.get('confidence', 0)
                    
                    print(f"  [{i+1}] {text[:50]}")
                    print(f"      Position: {bbox}")
                    print(f"      Confidence: {confidence:.2%}")
                
                if len(bboxes) > 5:
                    print(f"  ... and {len(bboxes) - 5} more")
                print()
            
            # Print performance metrics
            if result.get('processing_time_ms'):
                print(f"Processing Time: {result['processing_time_ms']}ms")
            
            if result.get('model_info'):
                model_info = result['model_info']
                print(f"Model: {model_info.get('name', 'unknown')}")
                print(f"Mode: {model_info.get('mode', 'unknown')}")
            
            print()
            
            # Save result
            with open('glm_test_result.json', 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print("✓ Result saved to: glm_test_result.json")
            
            return True
        else:
            print(f"✗ Extraction failed: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"✗ Request failed: {e}")
        return False

def check_service_health():
    """Check if GLM-OCR service is running."""
    print("=" * 80)
    print("CHECKING SERVICE HEALTH")
    print("=" * 80)
    
    health_url = f"{GLM_SERVICE_URL}/health"
    
    try:
        response = requests.get(health_url, timeout=5)
        if response.status_code == 200:
            print(f"✓ GLM-OCR Service is healthy")
            print(f"  URL: {GLM_SERVICE_URL}")
            print()
            return True
        else:
            print(f"✗ GLM-OCR Service returned status {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"✗ GLM-OCR Service is not available: {e}")
        print()
        print("To start the service, run:")
        print("  start_glm_service.bat")
        print()
        return False

def main():
    """Run the GLM-OCR service test."""
    print()
    print("=" * 80)
    print("GLM-OCR SERVICE TEST")
    print("=" * 80)
    print()
    
    # Check service health
    if not check_service_health():
        return
    
    # Generate test image
    image_base64, width, height = generate_test_image()
    
    # Test extraction
    success = test_extraction(image_base64, width, height)
    
    # Final summary
    print()
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    if success:
        print("✓✓✓ TEST PASSED ✓✓✓")
        print("GLM-OCR service is working correctly!")
    else:
        print("✗✗✗ TEST FAILED ✗✗✗")
        print("Check the error messages above.")
    
    print("=" * 80)
    print()

if __name__ == "__main__":
    main()
