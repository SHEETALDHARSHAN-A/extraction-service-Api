#!/usr/bin/env python3
"""
Simple extraction test script that simulates the extraction workflow
without requiring all services to be running.
"""

import base64
import json
from pathlib import Path
from datetime import datetime

def encode_image_to_base64(image_path):
    """Encode an image file to base64 string."""
    with open(image_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')

def simulate_extraction(image_path, output_format='json'):
    """
    Simulate document extraction process.
    This creates a mock extraction result similar to what the real service would return.
    """
    
    # Read and encode the image
    image_base64 = encode_image_to_base64(image_path)
    
    # Create mock extraction result
    result = {
        "job_id": f"test-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "model": "glm-ocr",
        "created_at": datetime.now().isoformat(),
        "processing_time_ms": 3200,
        "document_confidence": 0.93,
        "page_count": 1,
        "usage": {
            "prompt_tokens": 45,
            "completion_tokens": 512
        },
        "result": {}
    }
    
    # Add format-specific results
    if output_format == 'text':
        result["result"] = {
            "text": "INVOICE\nInvoice #: INV-2026-0042\nDate: February 25, 2026\n\nBill To:\nCustomer Inc.\n123 Business Ave, Suite 456\nNew York, NY 10001\n\nDescription          Qty    Unit Price    Total\nWidget A              10      $100.00    $1,000.00\nWidget B               5       $46.91      $234.56\n\nSubtotal: $1,234.56\nTax (10%): $123.46\nTotal Due: $1,358.02"
        }
    
    elif output_format == 'json':
        result["result"] = {
            "document_type": "invoice",
            "fields": {
                "invoice_number": "INV-2026-0042",
                "date": "2026-02-25",
                "vendor": "Acme Corp",
                "bill_to": "Customer Inc.",
                "subtotal": "$1,234.56",
                "tax": "$123.46",
                "total_amount": "$1,358.02",
                "payment_terms": "Net 30"
            },
            "line_items": [
                {"description": "Widget A", "quantity": 10, "unit_price": "$100.00", "total": "$1,000.00"},
                {"description": "Widget B", "quantity": 5, "unit_price": "$46.91", "total": "$234.56"}
            ]
        }
    
    elif output_format == 'structured':
        result["result"] = {
            "document_type": "invoice",
            "language": "en",
            "raw_text": "INVOICE\nInvoice #: INV-2026-0042\n...",
            "fields": {
                "invoice_number": {"value": "INV-2026-0042", "bbox": [280, 100, 180, 25], "confidence": 0.97},
                "date": {"value": "2026-02-25", "bbox": [280, 130, 150, 25], "confidence": 0.96},
                "total_amount": {"value": "$1,358.02", "bbox": [400, 440, 130, 25], "confidence": 0.98}
            },
            "tables": [
                {
                    "table_id": 1,
                    "bbox": [80, 280, 540, 120],
                    "headers": ["Description", "Qty", "Unit Price", "Total"],
                    "rows": [
                        ["Widget A", "10", "$100.00", "$1,000.00"],
                        ["Widget B", "5", "$46.91", "$234.56"]
                    ]
                }
            ]
        }
    
    return result

def main():
    """Main test function."""
    print("=" * 60)
    print("Document Extraction Test (Simulated)")
    print("=" * 60)
    print()
    
    # Find test images
    test_images = [
        "test_invoice_local.png",
        "test_simple.png"
    ]
    
    available_images = []
    for img in test_images:
        if Path(img).exists():
            available_images.append(img)
    
    if not available_images:
        print("❌ No test images found in current directory")
        print("   Looking for: test_invoice_local.png or test_simple.png")
        return
    
    # Use the first available image
    test_image = available_images[0]
    print(f"📄 Using test image: {test_image}")
    print()
    
    # Test different output formats
    formats = ['text', 'json', 'structured']
    
    for fmt in formats:
        print(f"\n{'=' * 60}")
        print(f"Testing format: {fmt}")
        print('=' * 60)
        
        result = simulate_extraction(test_image, output_format=fmt)
        
        # Save result to file
        output_file = f"extraction_result_{fmt}.json"
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"✅ Extraction completed")
        print(f"   Job ID: {result['job_id']}")
        print(f"   Confidence: {result['document_confidence']}")
        print(f"   Processing time: {result['processing_time_ms']}ms")
        print(f"   Result saved to: {output_file}")
        
        # Print a preview of the result
        print(f"\n   Result preview:")
        result_preview = json.dumps(result['result'], indent=4)
        lines = result_preview.split('\n')
        for line in lines[:15]:  # Show first 15 lines
            print(f"   {line}")
        if len(lines) > 15:
            print(f"   ... ({len(lines) - 15} more lines)")
    
    print(f"\n{'=' * 60}")
    print("✅ All tests completed!")
    print(f"{'=' * 60}")
    print()
    print("📁 Generated files:")
    for fmt in formats:
        print(f"   - extraction_result_{fmt}.json")
    print()
    print("💡 To test with real services, start Docker Compose:")
    print("   docker-compose -f docker/docker-compose.yml up -d")

if __name__ == "__main__":
    main()
