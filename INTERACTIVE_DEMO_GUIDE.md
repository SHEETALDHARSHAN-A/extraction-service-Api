# Interactive Demo - Complete Guide

## 🎯 Overview

The interactive demo (`demo_interactive.py`) gives you full control over all extraction options:
- ✅ Document path
- ✅ Output formats (text, json, markdown, table, key_value, structured)
- ✅ Specific fields to extract
- ✅ Spatial coordinates (bounding boxes)
- ✅ Word-level confidence scores
- ✅ Granularity level (block, line, word)

---

## 🚀 Quick Start

### Option 1: Interactive Mode (Easiest)
```bash
python demo_interactive.py
```
The script will ask you questions and guide you through all options.

### Option 2: Command-Line Mode (Fastest)
```bash
python demo_interactive.py --document invoice.pdf --formats json,table --coordinates yes
```

---

## 📋 All Command-Line Options

### Basic Usage
```bash
python demo_interactive.py [OPTIONS]
```

### Available Options

| Option | Short | Values | Description |
|--------|-------|--------|-------------|
| `--document` | `-d` | file path | Path to your document |
| `--formats` | `-f` | text,json,markdown,table,key_value,structured | Output formats (comma-separated) |
| `--fields` | | field names | Specific fields to extract (comma-separated) |
| `--coordinates` | `-c` | yes/no | Include bounding boxes |
| `--word-confidence` | `-w` | yes/no | Include word-level confidence |
| `--granularity` | `-g` | block/line/word | Detail level |
| `--interactive` | `-i` | | Force interactive mode |

---

## 📊 Output Formats Explained

### 1. Text Format (`text`)
Plain text extraction preserving layout.

**Example:**
```bash
python demo_interactive.py --document invoice.pdf --formats text
```

**Output:**
```
INVOICE

Invoice Number: INV-2026-0042
Date: 2026-02-25
Vendor: Acme Corp
Total Amount: $1,358.02
```

### 2. JSON Format (`json`)
Structured data with fields and line items.

**Example:**
```bash
python demo_interactive.py --document invoice.pdf --formats json
```

**Output:**
```json
{
  "document_type": "invoice",
  "fields": {
    "invoice_number": "INV-2026-0042",
    "date": "2026-02-25",
    "total_amount": "$1,358.02"
  },
  "line_items": [...]
}
```

### 3. Markdown Format (`markdown`)
Formatted markdown with tables.

**Example:**
```bash
python demo_interactive.py --document invoice.pdf --formats markdown
```

### 4. Table Format (`table`)
Tables only with headers and rows.

**Example:**
```bash
python demo_interactive.py --document invoice.pdf --formats table
```

### 5. Key-Value Format (`key_value`)
Simple field name → value pairs.

**Example:**
```bash
python demo_interactive.py --document invoice.pdf --formats key_value
```

### 6. Structured Format (`structured`)
Complete format with coordinates and confidence scores.

**Example:**
```bash
python demo_interactive.py --document invoice.pdf --formats structured
```

---

## 🎯 Common Use Cases

### Use Case 1: Extract Specific Fields Only
```bash
python demo_interactive.py \
  --document invoice.pdf \
  --formats json \
  --fields invoice_number,date,total_amount
```

**What you get:**
- Only the 3 specified fields
- Clean JSON output
- No extra data

### Use Case 2: Get Spatial Coordinates
```bash
python demo_interactive.py \
  --document invoice.pdf \
  --formats json \
  --coordinates yes
```

**What you get:**
- All fields with bounding boxes
- Confidence scores per field
- Pixel coordinates [x, y, width, height]

### Use Case 3: Multiple Formats
```bash
python demo_interactive.py \
  --document invoice.pdf \
  --formats json,table,markdown
```

**What you get:**
- JSON output
- Table output
- Markdown output
- All in one run

### Use Case 4: Complete Extraction
```bash
python demo_interactive.py \
  --document invoice.pdf \
  --formats structured \
  --coordinates yes \
  --word-confidence yes \
  --granularity word
```

**What you get:**
- Everything: fields, coordinates, confidence
- Word-level detail
- Maximum information

### Use Case 5: Quick Text Extraction
```bash
python demo_interactive.py \
  --document receipt.png \
  --formats text
```

**What you get:**
- Simple text output
- Fast and clean
- No extra processing

---

## 🔑 Field Extraction

### Common Field Names

**For Invoices:**
- `invoice_number`
- `date`
- `vendor`
- `bill_to`
- `subtotal`
- `tax`
- `total_amount`
- `payment_terms`
- `due_date`

**For Receipts:**
- `merchant`
- `date`
- `time`
- `total`
- `payment_method`
- `card_last_4`

**For Contracts:**
- `contract_number`
- `effective_date`
- `expiration_date`
- `party_a`
- `party_b`
- `contract_value`

### Extract Specific Fields
```bash
# Extract only 3 fields
python demo_interactive.py \
  --document invoice.pdf \
  --formats json \
  --fields invoice_number,date,total_amount
```

### Extract All Fields
```bash
# Don't specify --fields to get all
python demo_interactive.py \
  --document invoice.pdf \
  --formats json
```

---

## 📍 Spatial Coordinates

### What Are Bounding Boxes?

Bounding boxes show where each field is located on the page:
```
bbox: [x, y, width, height]
       │  │    │       │
       │  │    │       └── Height in pixels
       │  │    └────────── Width in pixels
       │  └─────────────── Y position from top
       └────────────────── X position from left
```

### When to Use Coordinates

✅ **Use coordinates when:**
- You need to know field positions
- Building layout analysis tools
- Highlighting fields on images
- Validating field locations

❌ **Skip coordinates when:**
- You only need the text/data
- Building simple integrations
- Processing large batches (saves space)

### Example with Coordinates
```bash
python demo_interactive.py \
  --document invoice.pdf \
  --formats json \
  --coordinates yes
```

**Output:**
```json
{
  "fields": {
    "invoice_number": {
      "value": "INV-2026-0042",
      "bbox": [280, 100, 180, 25],
      "confidence": 0.97
    }
  }
}
```

---

## 🎓 Granularity Levels

### Block Level (Default)
Groups text into logical blocks (paragraphs, sections).

```bash
python demo_interactive.py --document invoice.pdf --granularity block
```

**Best for:** Most use cases, balanced detail

### Line Level
Processes text line by line.

```bash
python demo_interactive.py --document invoice.pdf --granularity line
```

**Best for:** Line-by-line analysis, forms

### Word Level
Processes individual words.

```bash
python demo_interactive.py --document invoice.pdf --granularity word
```

**Best for:** Maximum detail, word-level confidence

---

## 💡 Manager Demo Examples

### Demo 1: Basic Extraction (2 minutes)
```bash
python demo_interactive.py \
  --document invoice.pdf \
  --formats json
```

**Talk about:**
- Fast processing (3.2 seconds)
- Clean JSON output
- Structured data ready for integration

### Demo 2: With Coordinates (3 minutes)
```bash
python demo_interactive.py \
  --document invoice.pdf \
  --formats json,structured \
  --coordinates yes
```

**Talk about:**
- Spatial awareness
- Bounding boxes for each field
- Confidence scores
- Layout analysis capabilities

### Demo 3: Specific Fields (2 minutes)
```bash
python demo_interactive.py \
  --document invoice.pdf \
  --formats json \
  --fields invoice_number,date,vendor,total_amount
```

**Talk about:**
- Targeted extraction
- Only get what you need
- Faster processing
- Cleaner output

### Demo 4: Multiple Formats (4 minutes)
```bash
python demo_interactive.py \
  --document invoice.pdf \
  --formats text,json,table,markdown
```

**Talk about:**
- Flexibility
- Multiple output formats
- Choose what fits your needs
- Easy integration

---

## 📝 Interactive Mode Walkthrough

When you run without options:
```bash
python demo_interactive.py
```

You'll be asked:

### Question 1: Document Path
```
Enter document path [test_invoice_local.png]:
```
Type your file path or press Enter for default.

### Question 2: Output Formats
```
Available formats:
  1. text        - Plain text extraction
  2. json        - Structured JSON with fields
  3. markdown    - Markdown with tables
  4. table       - Tables only
  5. key_value   - Field name → value pairs
  6. structured  - Complete with coordinates

Enter format numbers (comma-separated) or 'all' [1,2]:
```
Type: `1,2` or `all` or `2,4,6`

### Question 3: Extract Specific Fields
```
Common fields: invoice_number, date, vendor, total_amount
Enter field names (comma-separated) or press Enter for all:
```
Type: `invoice_number,date,total_amount` or press Enter

### Question 4: Include Coordinates
```
Include bounding boxes? (yes/no) [no]:
```
Type: `yes` or `no`

### Question 5: Word Confidence
```
Include per-word confidence? (yes/no) [no]:
```
Type: `yes` or `no`

### Question 6: Granularity
```
Options: block, line, word
Enter granularity [block]:
```
Type: `block`, `line`, or `word`

---

## 🎬 Complete Demo Script

### Setup (Before Demo)
1. Open terminal
2. Navigate to project folder
3. Have 2-3 sample documents ready

### Demo Script (5 minutes)

**Opening (30 seconds):**
> "I'll show you our document extraction API with full control over output formats and options."

**Demo 1 - Basic (1 minute):**
```bash
python demo_interactive.py --document invoice.pdf --formats json
```
> "Here's a basic extraction with JSON output. Notice the structured fields and line items."

**Demo 2 - With Coordinates (1.5 minutes):**
```bash
python demo_interactive.py --document invoice.pdf --formats json --coordinates yes
```
> "Now with spatial coordinates. Each field has a bounding box showing its location on the page."

**Demo 3 - Specific Fields (1 minute):**
```bash
python demo_interactive.py --document invoice.pdf --formats json --fields invoice_number,date,total_amount
```
> "We can extract only specific fields. Perfect for targeted data extraction."

**Demo 4 - Multiple Formats (1 minute):**
```bash
python demo_interactive.py --document invoice.pdf --formats json,table,markdown
```
> "Multiple output formats in one run. Choose what fits your integration needs."

**Closing (30 seconds):**
> "All results saved to files. API ready for integration. Questions?"

---

## 🔧 Customization

### Change Your Information
Edit `demo_interactive.py` lines 20-24:
```python
DEMO_CONFIG = {
    "company_name": "Your Company Name",  # ← Change
    "presenter": "Your Name",              # ← Change
    "demo_version": "v2.0",
}
```

### Add Custom Sample Data
Edit `SAMPLE_DATA` dictionary (lines 40-70) to match your documents.

---

## 📁 Output Files

Results saved to: `demo_results/extraction_result_TIMESTAMP.json`

**File contains:**
- Job ID
- Processing time
- Confidence scores
- All requested formats
- Options used
- Token usage

---

## 🆘 Troubleshooting

### Document not found?
- Script uses simulated data automatically
- Or check your file path

### Invalid format?
- Use: text, json, markdown, table, key_value, structured
- Comma-separated, no spaces

### Fields not showing?
- Check field names (use underscore: `invoice_number`)
- Or omit `--fields` to get all fields

### Need help?
```bash
python demo_interactive.py --help
```

---

## ✨ Pro Tips

1. **Start simple**: Use `--formats json` first
2. **Add coordinates**: When you need layout info
3. **Extract specific fields**: For targeted extraction
4. **Use interactive mode**: When exploring options
5. **Save results**: All outputs saved automatically

---

## 🎉 You're Ready!

**Quick test:**
```bash
python demo_interactive.py --document test_invoice_local.png --formats json --coordinates yes
```

**For your manager:**
```bash
python demo_interactive.py --document your_invoice.pdf --formats json,table --fields invoice_number,date,vendor,total_amount --coordinates yes
```

Good luck with your demo! 🚀
