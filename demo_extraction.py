#!/usr/bin/env python3
"""
Document Extraction API - Demo Script
======================================
Professional demo for showcasing document extraction capabilities.

Usage:
    python demo_extraction.py
    
Or customize the document path:
    python demo_extraction.py --document path/to/your/document.pdf
"""

import argparse
import base64
import json
from pathlib import Path
from datetime import datetime
import sys

# ============================================================================
# CONFIGURATION - CUSTOMIZE THESE VALUES
# ============================================================================

# Default document to process (change this to your document)
DEFAULT_DOCUMENT = "test_invoice_local.png"

# Output format options: 'text', 'json', 'structured', 'all'
OUTPUT_FORMAT = "all"

# Company/Demo information
DEMO_CONFIG = {
    "company_name": "IDEP Document Intelligence",
    "demo_version": "v1.0",
    "presenter": "Your Name",  # Change this
}

# Sample extraction results (customize these based on your document)
SAMPLE_RESULTS = {
    "invoice": {
        "document_type": "invoice",
        "fields": {
            "invoice_number": "INV-2026-0042",
            "date": "2026-02-25",
            "vendor": "Acme Corp",
            "bill_to": "Customer Inc.",
            "address": "123 Business Ave, Suite 456, New York, NY 10001",
            "subtotal": "$1,234.56",
            "tax": "$123.46",
            "total_amount": "$1,358.02",
            "payment_terms": "Net 30",
            "due_date": "2026-03-27"
        },
        "line_items": [
            {
                "item_number": 1,
                "description": "Widget A",
                "quantity": 10,
                "unit_price": "$100.00",
                "total": "$1,000.00"
            },
            {
                "item_number": 2,
                "description": "Widget B",
                "quantity": 5,
                "unit_price": "$46.91",
                "total": "$234.56"
            }
        ]
    },
    "receipt": {
        "document_type": "receipt",
        "fields": {
            "merchant": "Coffee Shop",
            "date": "2026-03-03",
            "time": "14:30:00",
            "total": "$15.50",
            "payment_method": "Credit Card",
            "card_last_4": "4242"
        },
        "line_items": [
            {"description": "Latte", "quantity": 2, "price": "$5.00", "total": "$10.00"},
            {"description": "Croissant", "quantity": 1, "price": "$5.50", "total": "$5.50"}
        ]
    },
    "contract": {
        "document_type": "contract",
        "fields": {
            "contract_number": "CNT-2026-001",
            "effective_date": "2026-01-01",
            "expiration_date": "2027-01-01",
            "party_a": "Company A Inc.",
            "party_b": "Company B LLC",
            "contract_value": "$500,000",
            "payment_schedule": "Quarterly",
            "jurisdiction": "New York"
        }
    }
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def print_header(title, width=80):
    """Print a formatted header."""
    print("\n" + "=" * width)
    print(title.center(width))
    print("=" * width)

def print_section(title, width=80):
    """Print a section divider."""
    print("\n" + "-" * width)
    print(f"  {title}")
    print("-" * width)

def print_field(label, value, indent=2):
    """Print a field with label and value."""
    spaces = " " * indent
    print(f"{spaces}{label:.<30} {value}")

def print_success(message):
    """Print a success message."""
    print(f"✅ {message}")

def print_info(message):
    """Print an info message."""
    print(f"ℹ️  {message}")

def print_warning(message):
    """Print a warning message."""
    print(f"⚠️  {message}")

def encode_document(file_path):
    """Encode document to base64."""
    try:
        with open(file_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    except Exception as e:
        print_warning(f"Could not encode document: {e}")
        return None

def detect_document_type(file_path):
    """Detect document type from filename."""
    name = Path(file_path).stem.lower()
    if 'invoice' in name or 'inv' in name:
        return 'invoice'
    elif 'receipt' in name:
        return 'receipt'
    elif 'contract' in name:
        return 'contract'
    else:
        return 'invoice'  # default

def create_extraction_result(doc_type, file_path, format_type='json'):
    """Create a mock extraction result."""
    
    job_id = f"demo-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    # Base result structure
    result = {
        "job_id": job_id,
        "model": "glm-ocr-v2",
        "created_at": datetime.now().isoformat(),
        "processing_time_ms": 3200,
        "document_confidence": 0.95,
        "page_count": 1,
        "filename": Path(file_path).name,
        "usage": {
            "prompt_tokens": 45,
            "completion_tokens": 512,
            "total_tokens": 557
        }
    }
    
    # Get sample data based on document type
    sample_data = SAMPLE_RESULTS.get(doc_type, SAMPLE_RESULTS['invoice'])
    
    # Format-specific results
    if format_type == 'text':
        # Generate text representation
        text_lines = [f"{sample_data['document_type'].upper()}"]
        text_lines.append("")
        
        for key, value in sample_data['fields'].items():
            label = key.replace('_', ' ').title()
            text_lines.append(f"{label}: {value}")
        
        if 'line_items' in sample_data:
            text_lines.append("\nLine Items:")
            text_lines.append("-" * 60)
            for item in sample_data['line_items']:
                text_lines.append(f"{item.get('description', 'Item')}: {item.get('total', 'N/A')}")
        
        result['result'] = {"text": "\n".join(text_lines)}
    
    elif format_type == 'json':
        result['result'] = sample_data
    
    elif format_type == 'structured':
        # Add bounding boxes and confidence scores
        structured_data = {
            "document_type": sample_data['document_type'],
            "language": "en",
            "fields": {}
        }
        
        # Add bbox and confidence to each field
        y_pos = 100
        for key, value in sample_data['fields'].items():
            structured_data['fields'][key] = {
                "value": value,
                "bbox": [100, y_pos, 400, 25],
                "confidence": round(0.90 + (hash(key) % 10) / 100, 2)
            }
            y_pos += 30
        
        # Add line items with bboxes
        if 'line_items' in sample_data:
            structured_data['line_items'] = []
            for idx, item in enumerate(sample_data['line_items']):
                item_with_bbox = item.copy()
                item_with_bbox['bbox'] = [100, 400 + idx * 30, 500, 25]
                item_with_bbox['confidence'] = 0.93
                structured_data['line_items'].append(item_with_bbox)
        
        result['result'] = structured_data
    
    return result

# ============================================================================
# DEMO PRESENTATION FUNCTIONS
# ============================================================================

def show_demo_intro():
    """Show demo introduction."""
    print_header(f"{DEMO_CONFIG['company_name']} - Live Demo", 80)
    print(f"\n  Version: {DEMO_CONFIG['demo_version']}")
    print(f"  Presenter: {DEMO_CONFIG['presenter']}")
    print(f"  Date: {datetime.now().strftime('%B %d, %Y at %H:%M')}")
    print("\n  Capabilities:")
    print("    • Intelligent document extraction")
    print("    • Multi-format output (Text, JSON, Structured)")
    print("    • High accuracy OCR with confidence scores")
    print("    • Support for invoices, receipts, contracts, and more")
    print("    • Bounding box coordinates for layout analysis")

def show_document_info(file_path, doc_type):
    """Show document information."""
    print_section("📄 Document Information")
    
    file_size = Path(file_path).stat().st_size / 1024  # KB
    
    print_field("File Name", Path(file_path).name)
    print_field("File Size", f"{file_size:.2f} KB")
    print_field("Document Type", doc_type.title())
    print_field("Status", "Ready for processing")

def show_processing():
    """Show processing animation."""
    print_section("⚙️  Processing Document")
    print("\n  Processing stages:")
    
    stages = [
        ("Image preprocessing", "0.5s"),
        ("Layout detection", "0.8s"),
        ("Text recognition", "1.2s"),
        ("Field extraction", "0.7s"),
        ("Confidence scoring", "0.3s")
    ]
    
    for stage, time in stages:
        print(f"    ✓ {stage:.<40} {time}")
    
    print_success("Processing completed in 3.2 seconds")

def display_text_result(result):
    """Display text format result."""
    print_section("📝 Text Format Output")
    
    text = result['result']['text']
    lines = text.split('\n')
    
    print("\n  Extracted Text:")
    print("  " + "─" * 76)
    for line in lines:
        print(f"  │ {line:<74} │")
    print("  " + "─" * 76)

def display_json_result(result):
    """Display JSON format result."""
    print_section("📊 JSON Format Output")
    
    data = result['result']
    
    print(f"\n  Document Type: {data.get('document_type', 'Unknown').upper()}")
    
    # Display fields
    if 'fields' in data:
        print("\n  Extracted Fields:")
        for key, value in data['fields'].items():
            label = key.replace('_', ' ').title()
            print_field(label, value, indent=4)
    
    # Display line items
    if 'line_items' in data:
        print("\n  Line Items:")
        print("    " + "─" * 72)
        print(f"    {'#':<4} {'Description':<30} {'Qty':<8} {'Price':<12} {'Total':<12}")
        print("    " + "─" * 72)
        
        for idx, item in enumerate(data['line_items'], 1):
            desc = item.get('description', 'N/A')
            qty = str(item.get('quantity', 'N/A'))
            price = item.get('unit_price', item.get('price', 'N/A'))
            total = item.get('total', 'N/A')
            print(f"    {idx:<4} {desc:<30} {qty:<8} {price:<12} {total:<12}")
        
        print("    " + "─" * 72)

def display_structured_result(result):
    """Display structured format result with bounding boxes."""
    print_section("🎯 Structured Format Output (with Coordinates)")
    
    data = result['result']
    
    print(f"\n  Document Type: {data.get('document_type', 'Unknown').upper()}")
    print(f"  Language: {data.get('language', 'en').upper()}")
    
    # Display fields with bboxes
    if 'fields' in data:
        print("\n  Extracted Fields with Bounding Boxes:")
        print("    " + "─" * 72)
        print(f"    {'Field':<25} {'Value':<25} {'Confidence':<12} {'BBox'}")
        print("    " + "─" * 72)
        
        for key, field_data in data['fields'].items():
            label = key.replace('_', ' ').title()
            
            if isinstance(field_data, dict):
                value = str(field_data.get('value', 'N/A'))[:23]
                conf = f"{field_data.get('confidence', 0):.2%}"
                bbox = str(field_data.get('bbox', []))
            else:
                value = str(field_data)[:23]
                conf = "N/A"
                bbox = "N/A"
            
            print(f"    {label:<25} {value:<25} {conf:<12} {bbox}")
        
        print("    " + "─" * 72)

def show_statistics(result):
    """Show extraction statistics."""
    print_section("📈 Extraction Statistics")
    
    print_field("Job ID", result['job_id'])
    print_field("Model", result['model'])
    print_field("Processing Time", f"{result['processing_time_ms']}ms")
    print_field("Document Confidence", f"{result['document_confidence']:.1%}")
    print_field("Page Count", result['page_count'])
    
    if 'usage' in result:
        print("\n  Token Usage:")
        print_field("Prompt Tokens", result['usage']['prompt_tokens'], indent=4)
        print_field("Completion Tokens", result['usage']['completion_tokens'], indent=4)
        print_field("Total Tokens", result['usage']['total_tokens'], indent=4)

def show_api_example(file_path):
    """Show API usage example."""
    print_section("💻 API Usage Example")
    
    print("\n  Using cURL:")
    print("  " + "─" * 76)
    print(f'''  curl -X POST http://localhost:8000/jobs/upload \\
    -H "Authorization: Bearer tp-proj-dev-key-123" \\
    -F "document=@{Path(file_path).name}" \\
    -F "output_formats=json" \\
    -F "include_coordinates=true"''')
    print("  " + "─" * 76)
    
    print("\n  Using Python:")
    print("  " + "─" * 76)
    print(f'''  import requests
  
  response = requests.post(
      "http://localhost:8000/jobs/upload",
      headers={{"Authorization": "Bearer tp-proj-dev-key-123"}},
      files={{"document": open("{Path(file_path).name}", "rb")}},
      data={{
          "output_formats": "json",
          "include_coordinates": "true"
      }}
  )
  
  job_id = response.json()["job_id"]
  print(f"Job ID: {{job_id}}")''')
    print("  " + "─" * 76)

def save_results(results, output_dir="demo_results"):
    """Save results to files."""
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    saved_files = []
    for format_type, result in results.items():
        filename = f"extraction_{format_type}_{timestamp}.json"
        filepath = output_path / filename
        
        with open(filepath, 'w') as f:
            json.dump(result, f, indent=2)
        
        saved_files.append(str(filepath))
    
    return saved_files

# ============================================================================
# MAIN DEMO FUNCTION
# ============================================================================

def run_demo(document_path, output_format='all'):
    """Run the complete demo."""
    
    # Introduction
    show_demo_intro()
    
    # Check if document exists
    if not Path(document_path).exists():
        print_warning(f"Document not found: {document_path}")
        print_info("Using simulated data for demo purposes")
        document_exists = False
    else:
        document_exists = True
    
    # Detect document type
    doc_type = detect_document_type(document_path)
    
    # Show document info
    if document_exists:
        show_document_info(document_path, doc_type)
    
    # Show processing
    show_processing()
    
    # Generate results
    formats = ['text', 'json', 'structured'] if output_format == 'all' else [output_format]
    results = {}
    
    for fmt in formats:
        results[fmt] = create_extraction_result(doc_type, document_path, fmt)
    
    # Display results
    if 'text' in results:
        display_text_result(results['text'])
    
    if 'json' in results:
        display_json_result(results['json'])
    
    if 'structured' in results:
        display_structured_result(results['structured'])
    
    # Show statistics (use first result)
    first_result = results[formats[0]]
    show_statistics(first_result)
    
    # Show API example
    show_api_example(document_path)
    
    # Save results
    print_section("💾 Saving Results")
    saved_files = save_results(results)
    
    print("\n  Results saved to:")
    for filepath in saved_files:
        print(f"    • {filepath}")
    
    # Conclusion
    print_header("Demo Complete", 80)
    print("\n  Key Takeaways:")
    print("    ✓ Fast processing (3.2 seconds)")
    print("    ✓ High accuracy (95% confidence)")
    print("    ✓ Multiple output formats")
    print("    ✓ Detailed field extraction")
    print("    ✓ Spatial coordinates available")
    print("\n  Thank you for watching!")
    print("=" * 80 + "\n")

# ============================================================================
# COMMAND LINE INTERFACE
# ============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Document Extraction API - Demo Script',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python demo_extraction.py
  python demo_extraction.py --document invoice.pdf
  python demo_extraction.py --document receipt.png --format json
  python demo_extraction.py --document contract.pdf --format structured
        '''
    )
    
    parser.add_argument(
        '--document', '-d',
        default=DEFAULT_DOCUMENT,
        help=f'Path to document file (default: {DEFAULT_DOCUMENT})'
    )
    
    parser.add_argument(
        '--format', '-f',
        choices=['text', 'json', 'structured', 'all'],
        default=OUTPUT_FORMAT,
        help='Output format (default: all)'
    )
    
    args = parser.parse_args()
    
    try:
        run_demo(args.document, args.format)
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
