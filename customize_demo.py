#!/usr/bin/env python3
"""
Demo Customization Helper
==========================
Quick script to customize demo data without editing the main script.

Usage:
    python customize_demo.py
"""

import json
from pathlib import Path

def get_input(prompt, default=""):
    """Get user input with default value."""
    if default:
        user_input = input(f"{prompt} [{default}]: ").strip()
        return user_input if user_input else default
    return input(f"{prompt}: ").strip()

def customize_demo():
    """Interactive demo customization."""
    print("=" * 70)
    print("Demo Customization Helper".center(70))
    print("=" * 70)
    print("\nThis will help you customize the demo data.")
    print("Press Enter to keep default values.\n")
    
    # Company info
    print("\n--- Company Information ---")
    company_name = get_input("Company Name", "IDEP Document Intelligence")
    presenter_name = get_input("Your Name", "Your Name")
    
    # Document info
    print("\n--- Document Information ---")
    doc_type = get_input("Document Type (invoice/receipt/contract)", "invoice")
    
    # Fields
    print("\n--- Document Fields ---")
    print("Enter the fields you want to extract (press Enter to finish):")
    
    fields = {}
    
    if doc_type == "invoice":
        default_fields = {
            "invoice_number": "INV-2026-0042",
            "date": "2026-02-25",
            "vendor": "Acme Corp",
            "bill_to": "Customer Inc.",
            "total_amount": "$1,358.02"
        }
    elif doc_type == "receipt":
        default_fields = {
            "merchant": "Coffee Shop",
            "date": "2026-03-03",
            "total": "$15.50",
            "payment_method": "Credit Card"
        }
    else:  # contract
        default_fields = {
            "contract_number": "CNT-2026-001",
            "effective_date": "2026-01-01",
            "party_a": "Company A Inc.",
            "party_b": "Company B LLC",
            "contract_value": "$500,000"
        }
    
    print("\nDefault fields for", doc_type.upper())
    for key, value in default_fields.items():
        custom_value = get_input(f"  {key.replace('_', ' ').title()}", value)
        fields[key] = custom_value
    
    # Line items (for invoice/receipt)
    line_items = []
    if doc_type in ["invoice", "receipt"]:
        print("\n--- Line Items ---")
        add_items = get_input("Add line items? (y/n)", "y").lower()
        
        if add_items == 'y':
            item_num = 1
            while True:
                print(f"\nItem {item_num}:")
                desc = get_input("  Description (or press Enter to finish)", "")
                if not desc:
                    break
                
                qty = get_input("  Quantity", "1")
                price = get_input("  Unit Price", "$0.00")
                total = get_input("  Total", "$0.00")
                
                line_items.append({
                    "item_number": item_num,
                    "description": desc,
                    "quantity": int(qty) if qty.isdigit() else qty,
                    "unit_price": price,
                    "total": total
                })
                item_num += 1
    
    # Create custom data structure
    custom_data = {
        "demo_config": {
            "company_name": company_name,
            "presenter": presenter_name,
            "demo_version": "v1.0"
        },
        "document": {
            "type": doc_type,
            "fields": fields,
            "line_items": line_items if line_items else None
        }
    }
    
    # Save to file
    output_file = "custom_demo_data.json"
    with open(output_file, 'w') as f:
        json.dump(custom_data, f, indent=2)
    
    print("\n" + "=" * 70)
    print("✅ Customization Complete!".center(70))
    print("=" * 70)
    print(f"\nCustom data saved to: {output_file}")
    print("\nTo use this data:")
    print("1. Open demo_extraction.py")
    print("2. Update DEMO_CONFIG with your company info")
    print("3. Update SAMPLE_RESULTS with your document data")
    print("\nOr copy the data below:\n")
    
    print("-" * 70)
    print(json.dumps(custom_data, indent=2))
    print("-" * 70)
    
    # Generate code snippet
    print("\n\nCode to add to demo_extraction.py:")
    print("-" * 70)
    print(f'''
DEMO_CONFIG = {{
    "company_name": "{company_name}",
    "demo_version": "v1.0",
    "presenter": "{presenter_name}",
}}

SAMPLE_RESULTS = {{
    "{doc_type}": {{
        "document_type": "{doc_type}",
        "fields": {json.dumps(fields, indent=8)},
        "line_items": {json.dumps(line_items, indent=8) if line_items else "[]"}
    }}
}}
''')
    print("-" * 70)

if __name__ == "__main__":
    try:
        customize_demo()
    except KeyboardInterrupt:
        print("\n\n⚠️  Customization cancelled")
    except Exception as e:
        print(f"\n❌ Error: {e}")
