#!/usr/bin/env python3
"""
Real-Time Document Extraction
==============================
Connects to actual API endpoint for real document extraction.

Usage:
    python real_extraction.py --document file.pdf --formats json --coordinates yes
"""

import argparse
import requests
import json
import time
from pathlib import Path
from datetime import datetime
import sys

# ============================================================================
# CONFIGURATION
# ============================================================================

API_CONFIG = {
    "base_url": "http://localhost:8000",
    "api_key": "tp-proj-dev-key-123",
    "timeout": 300,  # 5 minutes
    "poll_interval": 2,  # seconds
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
    print(f"[OK] {message}")

def print_error(message):
    """Print error message."""
    print(f"[ERROR] {message}")

def print_info(message):
    """Print info message."""
    print(f"ℹ️  {message}")

def print_warning(message):
    """Print warning message."""
    print(f"⚠️  {message}")

# ============================================================================
# API FUNCTIONS
# ============================================================================

def check_api_health():
    """Check if API is available."""
    try:
        response = requests.get(
            f"{API_CONFIG['base_url']}/health",
            timeout=5
        )
        return response.status_code == 200
    except Exception as e:
        return False

def upload_document(file_path, options):
    """Upload document to API for extraction."""
    
    headers = {
        "Authorization": f"Bearer {API_CONFIG['api_key']}"
    }
    
    # Prepare form data
    data = {}
    
    if options.get('output_formats'):
        data['output_formats'] = ','.join(options['output_formats'])
    
    if options.get('include_coordinates'):
        data['include_coordinates'] = 'true'
    
    if options.get('include_word_confidence'):
        data['include_word_confidence'] = 'true'
    
    if options.get('granularity'):
        data['granularity'] = options['granularity']
    
    if options.get('extract_fields'):
        data['extract_fields'] = ','.join(options['extract_fields'])
    
    # Open and upload file
    try:
        with open(file_path, 'rb') as f:
            files = {'document': (Path(file_path).name, f, 'application/pdf')}
            
            response = requests.post(
                f"{API_CONFIG['base_url']}/jobs/upload",
                headers=headers,
                files=files,
                data=data,
                timeout=30
            )
        
        if response.status_code == 202:
            return response.json()
        elif response.status_code == 200:
            # Document was cached, already processed
            result = response.json()
            if result.get('cached') and result.get('job_id'):
                print_info("Document already processed (cached)")
                return result
            else:
                print_error(f"Unexpected response: {response.status_code}")
                print(response.text)
                return None
        else:
            print_error(f"Upload failed: {response.status_code}")
            print(response.text)
            return None
    
    except Exception as e:
        print_error(f"Upload error: {e}")
        return None

def poll_job_status(job_id):
    """Poll job status until complete."""
    
    headers = {
        "Authorization": f"Bearer {API_CONFIG['api_key']}"
    }
    
    start_time = time.time()
    
    while True:
        try:
            response = requests.get(
                f"{API_CONFIG['base_url']}/jobs/{job_id}",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                job_data = response.json()
                status = job_data.get('status', 'UNKNOWN')
                
                if status == 'COMPLETED':
                    return job_data
                elif status == 'FAILED':
                    print_error(f"Job failed: {job_data.get('error', 'Unknown error')}")
                    return None
                elif status in ['PROCESSING', 'UPLOADED', 'QUEUED']:
                    elapsed = time.time() - start_time
                    print(f"  Status: {status} (elapsed: {elapsed:.1f}s)")
                    time.sleep(API_CONFIG['poll_interval'])
                else:
                    print_warning(f"Unknown status: {status}")
                    time.sleep(API_CONFIG['poll_interval'])
            else:
                print_error(f"Status check failed: {response.status_code}")
                return None
        
        except Exception as e:
            print_error(f"Polling error: {e}")
            return None
        
        # Timeout check
        if time.time() - start_time > API_CONFIG['timeout']:
            print_error("Timeout waiting for job completion")
            return None

def get_job_result(job_id):
    """Get extraction result."""
    
    headers = {
        "Authorization": f"Bearer {API_CONFIG['api_key']}"
    }
    
    try:
        response = requests.get(
            f"{API_CONFIG['base_url']}/jobs/{job_id}/result",
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            print_error(f"Failed to get result: {response.status_code}")
            print(response.text)
            return None
    
    except Exception as e:
        print_error(f"Error getting result: {e}")
        return None

# ============================================================================
# DISPLAY FUNCTIONS
# ============================================================================

def display_intro(options):
    """Display introduction."""
    print_header("Real-Time Document Extraction", 80)
    print(f"\n  API Endpoint: {API_CONFIG['base_url']}")
    print(f"  Date: {datetime.now().strftime('%B %d, %Y at %H:%M')}")

def display_options(options):
    """Display extraction options."""
    print_section("[OPTIONS] Extraction Options")
    
    print_field("Document", options['document'])
    print_field("Output Formats", ", ".join(options.get('output_formats', ['text'])))
    
    if options.get('extract_fields'):
        print_field("Extract Fields", ", ".join(options['extract_fields']))
    else:
        print_field("Extract Fields", "All fields")
    
    print_field("Include Coordinates", "Yes" if options.get('include_coordinates') else "No")
    print_field("Include Word Confidence", "Yes" if options.get('include_word_confidence') else "No")
    print_field("Granularity", options.get('granularity', 'block'))

def display_result_summary(result):
    """Display result summary."""
    print_section("[SUMMARY] Extraction Result Summary")
    
    print_field("Job ID", result.get('job_id', 'N/A'))
    print_field("Model", result.get('model', 'N/A'))
    print_field("Processing Time", f"{result.get('processing_time_ms', 0)}ms")
    print_field("Document Confidence", f"{result.get('document_confidence', 0):.1%}")
    print_field("Page Count", result.get('page_count', 0))
    
    if 'usage' in result:
        print("\n  Token Usage:")
        print_field("Prompt Tokens", result['usage'].get('prompt_tokens', 0), indent=4)
        print_field("Completion Tokens", result['usage'].get('completion_tokens', 0), indent=4)
        print_field("Total Tokens", result['usage'].get('total_tokens', 0), indent=4)

def display_extracted_data(result):
    """Display extracted data."""
    print_section("[DATA] Extracted Data")
    
    result_data = result.get('result', {})
    
    # Display based on what's in the result
    if 'text' in result_data:
        print("\n  Text Output:")
        print("  " + "-" * 76)
        text = result_data['text']
        for line in text.split('\n')[:20]:  # Show first 20 lines
            print(f"  {line}")
        text_lines = text.split('\n')
        if len(text_lines) > 20:
            remaining_lines = len(text_lines) - 20
            print(f"  ... ({remaining_lines} more lines)")
        print("  " + "-" * 76)
    
    if 'json' in result_data or 'document_type' in result_data:
        json_data = result_data.get('json', result_data)
        print("\n  JSON Output:")
        print("  " + "-" * 76)
        
        if 'document_type' in json_data:
            print(f"  Document Type: {json_data['document_type']}")
        
        if 'fields' in json_data:
            print("\n  Fields:")
            for key, value in list(json_data['fields'].items())[:10]:
                if isinstance(value, dict):
                    val = value.get('value', 'N/A')
                    conf = value.get('confidence', 0)
                    print(f"    {key}: {val} (confidence: {conf:.0%})")
                else:
                    print(f"    {key}: {value}")
            
            if len(json_data['fields']) > 10:
                print(f"    ... ({len(json_data['fields']) - 10} more fields)")
        
        if 'line_items' in json_data:
            print(f"\n  Line Items: {len(json_data['line_items'])} items")
        
        print("  " + "-" * 76)
    
    if 'tables' in result_data:
        tables = result_data['tables']
        print(f"\n  Tables: {len(tables)} table(s) found")
    
    if 'markdown' in result_data:
        print("\n  Markdown Output:")
        print("  " + "-" * 76)
        markdown = result_data['markdown']
        markdown_lines = markdown.split('\n')
        for line in markdown_lines[:15]:
            print(f"  {line}")
        if len(markdown_lines) > 15:
            remaining_lines = len(markdown_lines) - 15
            print(f"  ... ({remaining_lines} more lines)")
        print("  " + "-" * 76)

def save_result(result, output_dir="extraction_results"):
    """Save result to file."""
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    job_id = result.get('job_id', 'unknown')
    
    output_file = output_path / f"extraction_{job_id}_{timestamp}.json"
    
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)
    
    return output_file

# ============================================================================
# MAIN EXTRACTION FUNCTION
# ============================================================================

def run_extraction(options):
    """Run real-time extraction."""
    
    # Display intro
    display_intro(options)
    
    # Check if file exists
    if not Path(options['document']).exists():
        print_error(f"File not found: {options['document']}")
        return False
    
    print_success(f"Document found: {Path(options['document']).name}")
    
    # Check API health
    print_section("[CHECK] Checking API Status")
    print("  Checking API endpoint...")
    
    if not check_api_health():
        print_error("API is not available!")
        print_info(f"Make sure services are running at {API_CONFIG['base_url']}")
        print_info("Start services with: docker-compose -f docker/docker-compose.yml up -d")
        return False
    
    print_success("API is available")
    
    # Display options
    display_options(options)
    
    # Upload document
    print_section("[UPLOAD] Uploading Document")
    print("  Uploading to API...")
    
    upload_response = upload_document(options['document'], options)
    
    if not upload_response:
        print_error("Upload failed")
        return False
    
    job_id = upload_response.get('job_id')
    print_success(f"Document uploaded successfully")
    print_field("Job ID", job_id)
    print_field("Status", upload_response.get('status', 'UNKNOWN'))
    
    # Poll for completion
    print_section("[PROCESSING] Processing Document")
    print("  Waiting for extraction to complete...")
    
    job_status = poll_job_status(job_id)
    
    if not job_status:
        print_error("Job processing failed")
        return False
    
    print_success("Processing completed")
    
    # Get result
    print_section("[RESULT] Retrieving Result")
    print("  Fetching extraction result...")
    
    result = get_job_result(job_id)
    
    if not result:
        print_error("Failed to retrieve result")
        return False
    
    print_success("Result retrieved successfully")
    
    # Display result
    display_result_summary(result)
    display_extracted_data(result)
    
    # Save result
    print_section("💾 Saving Result")
    output_file = save_result(result)
    print_success(f"Result saved to: {output_file}")
    
    # Completion
    print_header("Extraction Complete", 80)
    print("\n  ✅ Document processed successfully")
    print(f"  📁 Result saved to: {output_file}")
    print("=" * 80 + "\n")
    
    return True

# ============================================================================
# COMMAND LINE INTERFACE
# ============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Real-Time Document Extraction',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Basic extraction
  python real_extraction.py --document invoice.pdf
  
  # JSON with coordinates
  python real_extraction.py --document invoice.pdf --formats json --coordinates yes
  
  # Specific fields
  python real_extraction.py --document invoice.pdf --formats json --fields invoice_number,date,total
  
  # Multiple formats
  python real_extraction.py --document invoice.pdf --formats json,table,markdown --coordinates yes
        '''
    )
    
    parser.add_argument('--document', '-d', required=True, help='Path to document file')
    parser.add_argument('--formats', '-f', default='json', help='Output formats (comma-separated): text,json,markdown,table,key_value,structured')
    parser.add_argument('--fields', help='Specific fields to extract (comma-separated)')
    parser.add_argument('--coordinates', '-c', choices=['yes', 'no'], default='no', help='Include spatial coordinates')
    parser.add_argument('--word-confidence', '-w', choices=['yes', 'no'], default='no', help='Include word-level confidence')
    parser.add_argument('--granularity', '-g', choices=['block', 'line', 'word'], default='block', help='Granularity level')
    parser.add_argument('--api-url', help=f'API base URL (default: {API_CONFIG["base_url"]})')
    parser.add_argument('--api-key', help=f'API key (default: {API_CONFIG["api_key"]})')
    
    args = parser.parse_args()
    
    # Update config if provided
    if args.api_url:
        API_CONFIG['base_url'] = args.api_url
    if args.api_key:
        API_CONFIG['api_key'] = args.api_key
    
    # Build options
    options = {
        'document': args.document,
        'output_formats': args.formats.split(',') if args.formats else ['json'],
        'include_coordinates': args.coordinates == 'yes',
        'include_word_confidence': args.word_confidence == 'yes',
        'granularity': args.granularity
    }
    
    if args.fields:
        options['extract_fields'] = [f.strip() for f in args.fields.split(',')]
    
    try:
        success = run_extraction(options)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n[WARNING] Extraction interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
