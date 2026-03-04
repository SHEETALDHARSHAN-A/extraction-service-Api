#!/usr/bin/env python3
"""
Interactive Document Extraction Demo
=====================================
Full-featured demo with all API options configurable.

Usage:
    # Interactive mode (asks for all options)
    python demo_interactive.py
    
    # Command-line mode (specify everything)
    python demo_interactive.py --document invoice.pdf --formats json,table --fields invoice_number,date,total --coordinates yes
"""

import argparse
import base64
import json
from pathlib import Path
from datetime import datetime
import sys

# ============================================================================
# CONFIGURATION
# ============================================================================

DEMO_CONFIG = {
    "company_name": "IDEP Document Intelligence",
    "presenter": "Sheetal",
    "demo_version": "v2.0",
}

# Available output formats
AVAILABLE_FORMATS = {
    "text": "Plain text extraction",
    "json": "Structured JSON with fields",
    "markdown": "Markdown with tables",
    "table": "Tables only",
    "key_value": "Field name → value pairs",
    "structured": "Complete with coordinates"
}

# Sample extraction data by document type
SAMPLE_DATA = {
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
            {"description": "Widget A", "quantity": 10, "unit_price": "$100.00", "total": "$1,000.00"},
            {"description": "Widget B", "quantity": 5, "unit_price": "$46.91", "total": "$234.56"}
        ]
    }
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def print_header(title, width=80):
    """Print formatted header."""
    print("\n" + "=" * width)
    print(title.center(width))
    print("=" * width)

def print_section(title, width=80):
    """Print section divider."""
    print("\n" + "-" * width)
    print(f"  {title}")
    print("-" * width)

def print_field(label, value, indent=2):
    """Print field with label."""
    spaces = " " * indent
    print(f"{spaces}{label:.<35} {value}")

def print_success(message):
    """Print success message."""
    print(f"✅ {message}")

def print_info(message):
    """Print info message."""
    print(f"ℹ️  {message}")

def detect_document_type(file_path):
    """Detect document type from filename."""
    name = Path(file_path).stem.lower()
    if 'invoice' in name or 'inv' in name:
        return 'invoice'
    elif 'receipt' in name:
        return 'receipt'
    elif 'contract' in name:
        return 'contract'
    return 'invoice'

# ============================================================================
# EXTRACTION RESULT GENERATION
# ============================================================================

def create_extraction_result(doc_type, file_path, options):
    """Create extraction result based on options."""
    
    job_id = f"demo-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    # Base result
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
        },
        "options": options
    }
    
    # Get sample data
    sample_data = SAMPLE_DATA.get(doc_type, SAMPLE_DATA['invoice'])
    
    # Build result based on requested formats
    result['result'] = {}
    
    for fmt in options['output_formats']:
        if fmt == 'text':
            result['result']['text'] = generate_text_output(sample_data, options)
        
        elif fmt == 'json':
            result['result']['json'] = generate_json_output(sample_data, options)
        
        elif fmt == 'markdown':
            result['result']['markdown'] = generate_markdown_output(sample_data, options)
        
        elif fmt == 'table':
            result['result']['tables'] = generate_table_output(sample_data, options)
        
        elif fmt == 'key_value':
            result['result']['key_values'] = generate_keyvalue_output(sample_data, options)
        
        elif fmt == 'structured':
            result['result']['structured'] = generate_structured_output(sample_data, options)
    
    return result

def generate_text_output(data, options):
    """Generate text format output."""
    lines = [data['document_type'].upper(), ""]
    
    # Filter fields if specific fields requested
    fields = data['fields']
    if options.get('extract_fields'):
        fields = {k: v for k, v in fields.items() if k in options['extract_fields']}
    
    for key, value in fields.items():
        label = key.replace('_', ' ').title()
        lines.append(f"{label}: {value}")
    
    if 'line_items' in data:
        lines.append("\nLine Items:")
        lines.append("-" * 60)
        for item in data['line_items']:
            lines.append(f"{item['description']}: {item['total']}")
    
    return "\n".join(lines)

def generate_json_output(data, options):
    """Generate JSON format output."""
    output = {"document_type": data['document_type']}
    
    # Filter fields if requested
    fields = data['fields']
    if options.get('extract_fields'):
        fields = {k: v for k, v in fields.items() if k in options['extract_fields']}
    
    # Add coordinates if requested
    if options.get('include_coordinates'):
        output['fields'] = {}
        y_pos = 100
        for key, value in fields.items():
            output['fields'][key] = {
                "value": value,
                "bbox": [100, y_pos, 400, 25],
                "confidence": round(0.90 + (hash(key) % 10) / 100, 2)
            }
            y_pos += 30
    else:
        output['fields'] = fields
    
    # Add line items
    if 'line_items' in data:
        if options.get('include_coordinates'):
            output['line_items'] = []
            for idx, item in enumerate(data['line_items']):
                item_with_bbox = item.copy()
                item_with_bbox['bbox'] = [100, 400 + idx * 30, 500, 25]
                item_with_bbox['confidence'] = 0.93
                output['line_items'].append(item_with_bbox)
        else:
            output['line_items'] = data['line_items']
    
    return output

def generate_markdown_output(data, options):
    """Generate markdown format output."""
    lines = [f"# {data['document_type'].upper()}", ""]
    
    # Filter fields
    fields = data['fields']
    if options.get('extract_fields'):
        fields = {k: v for k, v in fields.items() if k in options['extract_fields']}
    
    for key, value in fields.items():
        label = key.replace('_', ' ').title()
        lines.append(f"**{label}:** {value}  ")
    
    if 'line_items' in data:
        lines.append("\n## Line Items\n")
        lines.append("| Description | Qty | Unit Price | Total |")
        lines.append("|-------------|-----|------------|-------|")
        for item in data['line_items']:
            lines.append(f"| {item['description']} | {item['quantity']} | {item['unit_price']} | {item['total']} |")
    
    return "\n".join(lines)

def generate_table_output(data, options):
    """Generate table format output."""
    if 'line_items' not in data:
        return []
    
    table = {
        "table_id": 1,
        "title": "Line Items",
        "headers": ["Description", "Qty", "Unit Price", "Total"],
        "rows": []
    }
    
    for item in data['line_items']:
        table['rows'].append([
            item['description'],
            str(item['quantity']),
            item['unit_price'],
            item['total']
        ])
    
    if options.get('include_coordinates'):
        table['bbox'] = [80, 280, 540, 120]
        table['cell_coordinates'] = {
            "header_row": [[80, 280, 135, 25], [215, 280, 50, 25], [265, 280, 100, 25], [365, 280, 100, 25]],
            "data_rows": [
                [[80, 310, 135, 25], [215, 310, 50, 25], [265, 310, 100, 25], [365, 310, 100, 25]],
                [[80, 340, 135, 25], [215, 340, 50, 25], [265, 340, 100, 25], [365, 340, 100, 25]]
            ]
        }
    
    return [table]

def generate_keyvalue_output(data, options):
    """Generate key-value format output."""
    fields = data['fields']
    if options.get('extract_fields'):
        fields = {k: v for k, v in fields.items() if k in options['extract_fields']}
    return fields

def generate_structured_output(data, options):
    """Generate structured format with all details."""
    output = {
        "document_type": data['document_type'],
        "language": "en",
        "fields": {}
    }
    
    # Filter fields
    fields = data['fields']
    if options.get('extract_fields'):
        fields = {k: v for k, v in fields.items() if k in options['extract_fields']}
    
    # Always include coordinates in structured format
    y_pos = 100
    for key, value in fields.items():
        output['fields'][key] = {
            "value": value,
            "bbox": [100, y_pos, 400, 25],
            "confidence": round(0.90 + (hash(key) % 10) / 100, 2)
        }
        y_pos += 30
    
    # Add line items with coordinates
    if 'line_items' in data:
        output['line_items'] = []
        for idx, item in enumerate(data['line_items']):
            item_with_bbox = item.copy()
            item_with_bbox['bbox'] = [100, 400 + idx * 30, 500, 25]
            item_with_bbox['confidence'] = 0.93
            output['line_items'].append(item_with_bbox)
    
    return output

# ============================================================================
# DISPLAY FUNCTIONS
# ============================================================================

def display_intro(options):
    """Display demo introduction."""
    print_header(f"{DEMO_CONFIG['company_name']} - Interactive Demo", 80)
    print(f"\n  Version: {DEMO_CONFIG['demo_version']}")
    print(f"  Presenter: {DEMO_CONFIG['presenter']}")
    print(f"  Date: {datetime.now().strftime('%B %d, %Y at %H:%M')}")

def display_options(options):
    """Display selected options."""
    print_section("⚙️  Extraction Options")
    
    print_field("Document", options['document'])
    print_field("Output Formats", ", ".join(options['output_formats']))
    
    if options.get('extract_fields'):
        print_field("Extract Fields", ", ".join(options['extract_fields']))
    else:
        print_field("Extract Fields", "All fields")
    
    print_field("Include Coordinates", "Yes" if options.get('include_coordinates') else "No")
    print_field("Include Word Confidence", "Yes" if options.get('include_word_confidence') else "No")
    print_field("Granularity", options.get('granularity', 'block'))

def display_result(result, format_type):
    """Display extraction result."""
    
    if format_type == 'text':
        print_section("📝 Text Format Output")
        text = result['result'].get('text', '')
        lines = text.split('\n')
        print("\n  Extracted Text:")
        print("  " + "─" * 76)
        for line in lines:
            print(f"  │ {line:<74} │")
        print("  " + "─" * 76)
    
    elif format_type == 'json':
        print_section("📊 JSON Format Output")
        data = result['result'].get('json', {})
        
        print(f"\n  Document Type: {data.get('document_type', 'Unknown').upper()}")
        
        if 'fields' in data:
            print("\n  Extracted Fields:")
            for key, value in data['fields'].items():
                label = key.replace('_', ' ').title()
                
                if isinstance(value, dict):
                    val_str = value.get('value', 'N/A')
                    conf = value.get('confidence', 0)
                    bbox = value.get('bbox', [])
                    print_field(label, f"{val_str} (conf: {conf:.0%}, bbox: {bbox})", indent=4)
                else:
                    print_field(label, value, indent=4)
        
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
    
    elif format_type == 'markdown':
        print_section("📄 Markdown Format Output")
        markdown = result['result'].get('markdown', '')
        print("\n" + markdown)
    
    elif format_type == 'table':
        print_section("📋 Table Format Output")
        tables = result['result'].get('tables', [])
        
        for table in tables:
            print(f"\n  Table: {table.get('title', 'Untitled')}")
            if 'bbox' in table:
                print(f"  Bounding Box: {table['bbox']}")
            
            print("\n  " + "─" * 76)
            
            # Headers
            headers = table.get('headers', [])
            header_row = "  │ " + " │ ".join(f"{h:<18}" for h in headers) + " │"
            print(header_row)
            print("  " + "─" * 76)
            
            # Rows
            for row in table.get('rows', []):
                row_str = "  │ " + " │ ".join(f"{cell:<18}" for cell in row) + " │"
                print(row_str)
            
            print("  " + "─" * 76)
    
    elif format_type == 'key_value':
        print_section("🔑 Key-Value Format Output")
        kv_data = result['result'].get('key_values', {})
        
        print("\n  Extracted Key-Value Pairs:")
        for key, value in kv_data.items():
            label = key.replace('_', ' ').title()
            print_field(label, value, indent=4)
    
    elif format_type == 'structured':
        print_section("🎯 Structured Format Output")
        data = result['result'].get('structured', {})
        
        print(f"\n  Document Type: {data.get('document_type', 'Unknown').upper()}")
        print(f"  Language: {data.get('language', 'en').upper()}")
        
        if 'fields' in data:
            print("\n  Fields with Spatial Coordinates:")
            print("    " + "─" * 72)
            print(f"    {'Field':<25} {'Value':<20} {'Conf':<8} {'BBox'}")
            print("    " + "─" * 72)
            
            for key, field_data in data['fields'].items():
                label = key.replace('_', ' ').title()
                value = str(field_data.get('value', 'N/A'))[:18]
                conf = f"{field_data.get('confidence', 0):.0%}"
                bbox = str(field_data.get('bbox', []))
                print(f"    {label:<25} {value:<20} {conf:<8} {bbox}")
            
            print("    " + "─" * 72)

def display_statistics(result):
    """Display extraction statistics."""
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

def display_api_example(options):
    """Display API usage example."""
    print_section("💻 API Usage Example")
    
    formats_str = ",".join(options['output_formats'])
    coords_str = "true" if options.get('include_coordinates') else "false"
    
    print("\n  Using cURL:")
    print("  " + "─" * 76)
    print(f'''  curl -X POST http://localhost:8000/jobs/upload \\
    -H "Authorization: Bearer tp-proj-dev-key-123" \\
    -F "document=@{Path(options['document']).name}" \\
    -F "output_formats={formats_str}" \\
    -F "include_coordinates={coords_str}"''')
    
    if options.get('extract_fields'):
        fields_str = ",".join(options['extract_fields'])
        print(f'''    -F "extract_fields={fields_str}"''')
    
    print("  " + "─" * 76)

# ============================================================================
# INTERACTIVE MODE
# ============================================================================

def get_interactive_options():
    """Get options interactively from user."""
    print_header("Interactive Configuration", 80)
    print("\nAnswer the following questions to configure your extraction:")
    
    options = {}
    
    # Document path
    print("\n1. Document Path")
    doc_path = input("   Enter document path [test_invoice_local.png]: ").strip()
    options['document'] = doc_path if doc_path else "test_invoice_local.png"
    
    # Output formats
    print("\n2. Output Formats")
    print("   Available formats:")
    for idx, (fmt, desc) in enumerate(AVAILABLE_FORMATS.items(), 1):
        print(f"     {idx}. {fmt:<12} - {desc}")
    
    formats_input = input("\n   Enter format numbers (comma-separated) or 'all' [1,2]: ").strip()
    
    if formats_input.lower() == 'all':
        options['output_formats'] = list(AVAILABLE_FORMATS.keys())
    elif formats_input:
        format_list = list(AVAILABLE_FORMATS.keys())
        selected_indices = [int(x.strip()) - 1 for x in formats_input.split(',') if x.strip().isdigit()]
        options['output_formats'] = [format_list[i] for i in selected_indices if 0 <= i < len(format_list)]
    else:
        options['output_formats'] = ['text', 'json']
    
    # Extract specific fields
    print("\n3. Extract Specific Fields (optional)")
    print("   Common fields: invoice_number, date, vendor, total_amount")
    fields_input = input("   Enter field names (comma-separated) or press Enter for all: ").strip()
    
    if fields_input:
        options['extract_fields'] = [f.strip() for f in fields_input.split(',')]
    
    # Include coordinates
    print("\n4. Include Spatial Coordinates?")
    coords_input = input("   Include bounding boxes? (yes/no) [no]: ").strip().lower()
    options['include_coordinates'] = coords_input in ['yes', 'y', 'true', '1']
    
    # Include word confidence
    print("\n5. Include Word-Level Confidence?")
    word_conf_input = input("   Include per-word confidence? (yes/no) [no]: ").strip().lower()
    options['include_word_confidence'] = word_conf_input in ['yes', 'y', 'true', '1']
    
    # Granularity
    print("\n6. Granularity Level")
    print("   Options: block, line, word")
    granularity_input = input("   Enter granularity [block]: ").strip().lower()
    options['granularity'] = granularity_input if granularity_input in ['block', 'line', 'word'] else 'block'
    
    return options

# ============================================================================
# MAIN DEMO FUNCTION
# ============================================================================

def run_demo(options):
    """Run the demo with given options."""
    
    # Display intro
    display_intro(options)
    
    # Display options
    display_options(options)
    
    # Check document
    if not Path(options['document']).exists():
        print_info(f"Document not found: {options['document']}")
        print_info("Using simulated data for demo")
    
    # Detect document type
    doc_type = detect_document_type(options['document'])
    
    # Processing
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
    
    # Generate result
    result = create_extraction_result(doc_type, options['document'], options)
    
    # Display results for each format
    for fmt in options['output_formats']:
        display_result(result, fmt)
    
    # Display statistics
    display_statistics(result)
    
    # Display API example
    display_api_example(options)
    
    # Save results
    print_section("💾 Saving Results")
    output_dir = Path("demo_results")
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = output_dir / f"extraction_result_{timestamp}.json"
    
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"\n  Results saved to: {output_file}")
    
    # Conclusion
    print_header("Demo Complete", 80)
    print("\n  Configuration Summary:")
    print(f"    • Formats: {', '.join(options['output_formats'])}")
    print(f"    • Coordinates: {'Yes' if options.get('include_coordinates') else 'No'}")
    if options.get('extract_fields'):
        print(f"    • Fields: {', '.join(options['extract_fields'])}")
    print("\n  Thank you for watching!")
    print("=" * 80 + "\n")

# ============================================================================
# COMMAND LINE INTERFACE
# ============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Interactive Document Extraction Demo',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Interactive mode
  python demo_interactive.py
  
  # Command-line mode
  python demo_interactive.py --document invoice.pdf --formats json,table
  
  # With specific fields
  python demo_interactive.py --document invoice.pdf --formats json --fields invoice_number,date,total
  
  # With coordinates
  python demo_interactive.py --document invoice.pdf --formats structured --coordinates yes
  
  # All options
  python demo_interactive.py --document invoice.pdf --formats json,table,structured --fields invoice_number,date,vendor,total_amount --coordinates yes --word-confidence yes --granularity word
        '''
    )
    
    parser.add_argument('--document', '-d', help='Path to document file')
    parser.add_argument('--formats', '-f', help='Output formats (comma-separated): text,json,markdown,table,key_value,structured')
    parser.add_argument('--fields', help='Specific fields to extract (comma-separated)')
    parser.add_argument('--coordinates', '-c', choices=['yes', 'no'], help='Include spatial coordinates')
    parser.add_argument('--word-confidence', '-w', choices=['yes', 'no'], help='Include word-level confidence')
    parser.add_argument('--granularity', '-g', choices=['block', 'line', 'word'], help='Granularity level')
    parser.add_argument('--interactive', '-i', action='store_true', help='Force interactive mode')
    
    args = parser.parse_args()
    
    # Determine if interactive mode
    if args.interactive or not any([args.document, args.formats]):
        options = get_interactive_options()
    else:
        # Build options from command line
        options = {
            'document': args.document or 'test_invoice_local.png',
            'output_formats': args.formats.split(',') if args.formats else ['text', 'json'],
            'include_coordinates': args.coordinates == 'yes' if args.coordinates else False,
            'include_word_confidence': args.word_confidence == 'yes' if args.word_confidence else False,
            'granularity': args.granularity or 'block'
        }
        
        if args.fields:
            options['extract_fields'] = [f.strip() for f in args.fields.split(',')]
    
    try:
        run_demo(options)
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
