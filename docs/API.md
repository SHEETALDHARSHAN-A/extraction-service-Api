# IDEP Extraction API — Complete Reference

> **Base URL**: `http://localhost:8000`  
> **Version**: v1  
> **Style**: REST (OpenAI / Azure Document Intelligence inspired)

---

## Quick Start

```bash
# 1. Extract text from a document
curl -X POST http://localhost:8000/jobs/upload \
  -H "Authorization: Bearer tp-proj-dev-key-123" \
  -F "document=@invoice.pdf" \
  -F "output_formats=json"

# 2. Poll status
curl http://localhost:8000/jobs/<job_id> \
  -H "Authorization: Bearer tp-proj-dev-key-123"

# 3. Get result
curl http://localhost:8000/jobs/<job_id>/result \
  -H "Authorization: Bearer tp-proj-dev-key-123"
```

---

## Authentication

Authenticate every request with your API key in the `Authorization` header:

```
Authorization: Bearer tp-proj-xxxxxxxxxxxx
```

| Key Prefix | Type |
|-----------|------|
| `tp-proj-*` | Production key |
| `tp-test-*` | Test key (same access, flagged in logs) |

Set keys via environment variable:
```bash
IDEP_API_KEYS=tp-proj-abc123,tp-proj-def456
```

Default dev key: `tp-proj-dev-key-123`

---

## POST /jobs/upload — Extract Document

### All Parameters

Every parameter except `document` is **optional**. Use only what you need.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| **`document`** | **File** | **required** | Document file to process |
| `output_formats` | String | `"text"` | Prebuilt format(s), comma-separated |
| `prompt` | String | — | Custom prompt (overrides `output_formats`) |
| `include_coordinates` | Bool | `false` | Bounding boxes `[x, y, w, h]` for every element |
| `include_word_confidence` | Bool | `false` | Per-word confidence scores |
| `include_line_confidence` | Bool | `false` | Per-line confidence scores |
| `include_page_layout` | Bool | `false` | Full page layout with typed blocks |
| `language` | String | `"auto"` | Language hint: `en`, `es`, `de`, `zh`, `ja`, `hi`, etc. |
| `granularity` | String | `"block"` | Spatial detail: `block`, `line`, `word` |
| `redact_pii` | Bool | `false` | Redact emails, phones, SSNs, credit cards |
| `deskew` | Bool | `true` | Auto-straighten tilted scans |
| `enhance` | Bool | `true` | Run image preprocessing pipeline |
| `max_pages` | Int | `0` (all) | Limit pages to process (PDFs) |
| `temperature` | Float | `0.0` | GLM sampling temperature (0 = deterministic) |
| `max_tokens` | Int | `4096` | Max output tokens from GLM |

### Prebuilt Output Formats

| Format | What you get |
|--------|-------------|
| `text` | Raw text preserving layout and reading order |
| `json` | Structured JSON: document_type, fields, line_items |
| `markdown` | Markdown with headings, tables, bold labels |
| `table` | Tables only: headers + rows + footer |
| `key_value` | Field name → value pairs |
| `structured` | **All of the above combined** |

Combine any: `"text,table"`, `"json,markdown"`, `"key_value,table,json"`

---

## Request Examples

### 1. Simple text extraction
```bash
curl -X POST http://localhost:8000/jobs/upload \
  -H "Authorization: Bearer tp-proj-dev-key-123" \
  -F "document=@letter.pdf"
```

### 2. JSON + Tables
```bash
curl -X POST http://localhost:8000/jobs/upload \
  -H "Authorization: Bearer tp-proj-dev-key-123" \
  -F "document=@invoice.pdf" \
  -F "output_formats=json,table"
```

### 3. Custom prompt
```bash
curl -X POST http://localhost:8000/jobs/upload \
  -H "Authorization: Bearer tp-proj-dev-key-123" \
  -F "document=@medical_form.pdf" \
  -F 'prompt=Extract patient name, DOB, medications, and diagnosis. Return as JSON.'
```

### 4. Full spatial + confidence (like Azure)
```bash
curl -X POST http://localhost:8000/jobs/upload \
  -H "Authorization: Bearer tp-proj-dev-key-123" \
  -F "document=@scan.png" \
  -F "output_formats=structured" \
  -F "include_coordinates=true" \
  -F "include_word_confidence=true" \
  -F "include_page_layout=true" \
  -F "granularity=word"
```

### 5. With PII redaction
```bash
curl -X POST http://localhost:8000/jobs/upload \
  -H "Authorization: Bearer tp-proj-dev-key-123" \
  -F "document=@contract.pdf" \
  -F "output_formats=json" \
  -F "redact_pii=true"
```

### 6. ZIP archive
```bash
curl -X POST http://localhost:8000/jobs/upload \
  -H "Authorization: Bearer tp-proj-dev-key-123" \
  -F "document=@invoices.zip" \
  -F "output_formats=json,table" \
  -F "include_coordinates=true"
```

### Upload Response (HTTP 202)
```json
{
  "job_id": "a1b2c3d4-e5f6-...",
  "filename": "invoice.pdf",
  "status": "PROCESSING",
  "workflow_id": "doc-processing-a1b2c3d4-...",
  "output_formats": "json,table",
  "options": {
    "prompt": "",
    "include_coordinates": true,
    "include_word_confidence": false,
    "language": "auto",
    "granularity": "block"
  },
  "result_url": "/jobs/a1b2c3d4-.../result",
  "status_url": "/jobs/a1b2c3d4-..."
}
```

---

## Result Schemas — What You Get Back

> `GET /jobs/:id/result`

Every result is wrapped in a **standard envelope**:

```json
{
  "job_id": "a1b2c3d4-...",
  "model": "glm-ocr",
  "created_at": "2026-02-26T00:30:00Z",
  "processing_time_ms": 3200,
  "document_confidence": 0.93,
  "page_count": 2,
  "usage": {
    "prompt_tokens": 45,
    "completion_tokens": 512
  },
  "result": { ... }
}
```

The `result` field changes based on your options. Here is the **exact schema** for every configuration:

---

### Result: `output_formats=text`

```json
{
  "job_id": "...",
  "model": "glm-ocr",
  "document_confidence": 0.93,
  "page_count": 1,
  "usage": {"prompt_tokens": 45, "completion_tokens": 256},
  "result": {
    "text": "INVOICE\nInvoice #: INV-2026-0042\nDate: February 25, 2026\n\nBill To:\nCustomer Inc.\n123 Business Ave, Suite 456\nNew York, NY 10001\n\nDescription          Qty    Unit Price    Total\nWidget A              10      $100.00    $1,000.00\nWidget B               5       $46.91      $234.56\n\nSubtotal: $1,234.56\nTax (10%): $123.46\nTotal Due: $1,358.02"
  }
}
```

---

### Result: `output_formats=text` + `include_coordinates=true`

The same text, but every block gets a bounding box and confidence:

```json
{
  "job_id": "...",
  "document_confidence": 0.93,
  "result": {
    "text": "INVOICE\nInvoice #: INV-2026-0042...",
    "blocks": [
      {
        "text": "INVOICE",
        "bbox": [100, 50, 200, 40],
        "confidence": 0.99
      },
      {
        "text": "Invoice #: INV-2026-0042",
        "bbox": [100, 100, 350, 25],
        "confidence": 0.97
      },
      {
        "text": "Widget A   10   $100.00   $1,000.00",
        "bbox": [100, 320, 500, 25],
        "confidence": 0.94
      }
    ]
  }
}
```

---

### Result: `output_formats=text` + `include_word_confidence=true`

Every individual word gets its own bounding box and confidence:

```json
{
  "job_id": "...",
  "document_confidence": 0.93,
  "result": {
    "text": "INVOICE\nInvoice #: INV-2026-0042...",
    "words": [
      {"word": "INVOICE",       "bbox": [100, 50, 80, 30],   "confidence": 0.99},
      {"word": "Invoice",       "bbox": [100, 100, 60, 20],  "confidence": 0.98},
      {"word": "#:",            "bbox": [162, 100, 15, 20],  "confidence": 0.97},
      {"word": "INV-2026-0042", "bbox": [180, 100, 130, 20], "confidence": 0.96},
      {"word": "Widget",        "bbox": [100, 320, 55, 20],  "confidence": 0.93},
      {"word": "A",             "bbox": [158, 320, 10, 20],  "confidence": 0.95},
      {"word": "$1,000.00",     "bbox": [440, 320, 80, 20],  "confidence": 0.95}
    ]
  }
}
```

---

### Result: `output_formats=json`

```json
{
  "job_id": "...",
  "document_confidence": 0.93,
  "result": {
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
}
```

---

### Result: `output_formats=json` + `include_coordinates=true`

Every field gets `value`, `bbox`, and `confidence`:

```json
{
  "job_id": "...",
  "document_confidence": 0.93,
  "result": {
    "document_type": "invoice",
    "fields": {
      "invoice_number": {
        "value": "INV-2026-0042",
        "bbox": [280, 100, 180, 25],
        "confidence": 0.97
      },
      "date": {
        "value": "2026-02-25",
        "bbox": [280, 130, 150, 25],
        "confidence": 0.96
      },
      "total_amount": {
        "value": "$1,358.02",
        "bbox": [400, 440, 130, 25],
        "confidence": 0.98
      }
    },
    "line_items": [
      {
        "description": "Widget A",
        "quantity": 10,
        "unit_price": "$100.00",
        "total": "$1,000.00",
        "bbox": [100, 320, 500, 25],
        "confidence": 0.94
      }
    ]
  }
}
```

---

### Result: `output_formats=table`

```json
{
  "job_id": "...",
  "document_confidence": 0.91,
  "result": {
    "tables": [
      {
        "table_id": 1,
        "title": "Line Items",
        "headers": ["Description", "Qty", "Unit Price", "Total"],
        "rows": [
          ["Widget A", "10", "$100.00", "$1,000.00"],
          ["Widget B", "5", "$46.91", "$234.56"]
        ],
        "footer": ["", "", "Total", "$1,234.56"]
      }
    ]
  }
}
```

---

### Result: `output_formats=table` + `include_coordinates=true`

Tables with per-cell bounding boxes:

```json
{
  "job_id": "...",
  "document_confidence": 0.91,
  "result": {
    "tables": [
      {
        "table_id": 1,
        "title": "Line Items",
        "bbox": [80, 280, 540, 120],
        "headers": ["Description", "Qty", "Unit Price", "Total"],
        "rows": [
          ["Widget A", "10", "$100.00", "$1,000.00"],
          ["Widget B", "5", "$46.91", "$234.56"]
        ],
        "cell_coordinates": {
          "header_row": [
            [80, 280, 135, 25],
            [215, 280, 50, 25],
            [265, 280, 100, 25],
            [365, 280, 100, 25]
          ],
          "data_rows": [
            [[80, 310, 135, 25], [215, 310, 50, 25], [265, 310, 100, 25], [365, 310, 100, 25]],
            [[80, 340, 135, 25], [215, 340, 50, 25], [265, 340, 100, 25], [365, 340, 100, 25]]
          ]
        }
      }
    ]
  }
}
```

---

### Result: `output_formats=markdown`

```json
{
  "job_id": "...",
  "document_confidence": 0.94,
  "result": {
    "markdown": "# INVOICE\n\n**Invoice #:** INV-2026-0042  \n**Date:** February 25, 2026\n\n## Bill To\nCustomer Inc.  \n123 Business Ave, Suite 456\n\n## Line Items\n\n| Description | Qty | Unit Price | Total |\n|-------------|-----|-----------|-------|\n| Widget A | 10 | $100.00 | $1,000.00 |\n| Widget B | 5 | $46.91 | $234.56 |\n\n---\n- **Subtotal:** $1,234.56\n- **Tax (10%):** $123.46\n- **Total Due:** $1,358.02"
  }
}
```

---

### Result: `output_formats=key_value`

```json
{
  "job_id": "...",
  "document_confidence": 0.93,
  "result": {
    "key_values": {
      "invoice_number": "INV-2026-0042",
      "date": "2026-02-25",
      "vendor": "Acme Corp",
      "bill_to": "Customer Inc.",
      "subtotal": "$1,234.56",
      "tax": "$123.46",
      "total_amount": "$1,358.02",
      "payment_terms": "Net 30"
    }
  }
}
```

---

### Result: `output_formats=structured` (Everything)

```json
{
  "job_id": "...",
  "document_confidence": 0.95,
  "page_count": 1,
  "result": {
    "document_type": "invoice",
    "language": "en",
    "raw_text": "INVOICE\nInvoice #: INV-2026-0042\n...",
    "fields": {
      "invoice_number": "INV-2026-0042",
      "date": "2026-02-25",
      "total_amount": "$1,358.02"
    },
    "tables": [
      {
        "headers": ["Description", "Qty", "Unit Price", "Total"],
        "rows": [
          ["Widget A", "10", "$100.00", "$1,000.00"],
          ["Widget B", "5", "$46.91", "$234.56"]
        ]
      }
    ],
    "handwritten_sections": []
  }
}
```

---

### Result: `output_formats=structured` + ALL options ON

The maximum possible output:

```json
{
  "job_id": "a1b2c3d4-...",
  "model": "glm-ocr",
  "created_at": "2026-02-26T00:30:00Z",
  "processing_time_ms": 4500,
  "document_confidence": 0.95,
  "page_count": 1,
  "usage": {
    "prompt_tokens": 120,
    "completion_tokens": 1024
  },
  "result": {
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
        ],
        "cell_coordinates": {
          "header_row": [[80, 280, 135, 25], [215, 280, 50, 25], [265, 280, 100, 25], [365, 280, 100, 25]],
          "data_rows": [
            [[80, 310, 135, 25], [215, 310, 50, 25], [265, 310, 100, 25], [365, 310, 100, 25]]
          ]
        }
      }
    ],
    "handwritten_sections": [],
    "blocks": [
      {"text": "INVOICE", "bbox": [100, 50, 200, 40], "confidence": 0.99},
      {"text": "Invoice #: INV-2026-0042", "bbox": [100, 100, 350, 25], "confidence": 0.97}
    ],
    "words": [
      {"word": "INVOICE", "bbox": [100, 50, 80, 30], "confidence": 0.99},
      {"word": "Invoice", "bbox": [100, 100, 60, 20], "confidence": 0.98},
      {"word": "#:", "bbox": [162, 100, 15, 20], "confidence": 0.97},
      {"word": "INV-2026-0042", "bbox": [180, 100, 130, 20], "confidence": 0.96}
    ],
    "pages": [
      {
        "page_number": 1,
        "width": 612,
        "height": 792,
        "unit": "pixel",
        "blocks": [
          {"type": "title", "text": "INVOICE", "bbox": [100, 50, 200, 40], "confidence": 0.99},
          {"type": "field", "text": "Invoice #: INV-2026-0042", "bbox": [100, 100, 350, 25], "confidence": 0.97},
          {"type": "table", "bbox": [80, 280, 540, 120], "confidence": 0.95,
            "cells": [
              {"text": "Description", "bbox": [80, 280, 135, 25], "row": 0, "col": 0, "is_header": true, "confidence": 0.98},
              {"text": "Widget A", "bbox": [80, 310, 135, 25], "row": 1, "col": 0, "is_header": false, "confidence": 0.94}
            ]
          }
        ]
      }
    ]
  }
}
```

---

### Result: Custom `prompt`

The response wraps whatever GLM returns:

```json
{
  "job_id": "...",
  "document_confidence": 0.92,
  "prompt_used": "Extract patient name, DOB, medications...",
  "result": {
    "content": "{ ... whatever the model returns based on your prompt ... }"
  }
}
```

---

## Confidence Scores — 3 Levels

| Level | Field | When present | Range |
|-------|-------|-------------|-------|
| **Document** | `document_confidence` | **Always** | 0.0–1.0 |
| **Element** | `fields.*.confidence`, `blocks[].confidence` | `include_coordinates=true` | 0.0–1.0 |
| **Word** | `words[].confidence` | `include_word_confidence=true` | 0.0–1.0 |

---

## Bounding Box Format

```
bbox: [x, y, width, height]    (pixels, from top-left of page)
       │  │    │       │
       │  │    │       └── Height
       │  │    └────────── Width  
       │  └─────────────── Y (from top)
       └────────────────── X (from left)
```

Page dimensions in `pages[].width` and `pages[].height`.

---

## POST /jobs/batch — Batch Upload

Up to **10,000 documents** per request. All parameters from `/jobs/upload` apply to every file.

```bash
curl -X POST http://localhost:8000/jobs/batch \
  -H "Authorization: Bearer tp-proj-dev-key-123" \
  -F "documents=@inv1.pdf" \
  -F "documents=@inv2.pdf" \
  -F "documents=@receipt.png" \
  -F "output_formats=json" \
  -F "include_coordinates=true" \
  -F "webhook_url=https://your-server.com/webhook/extraction-done"
```

**Response (HTTP 202):**
```json
{
  "batch_id": "b5c6d7e8-...",
  "total": 3,
  "succeeded": 3,
  "failed": 0,
  "output_formats": "json",
  "status_url": "/jobs/batch/b5c6d7e8-...",
  "jobs": [
    {"job_id": "aaa...", "filename": "inv1.pdf", "status": "PROCESSING"},
    {"job_id": "bbb...", "filename": "inv2.pdf", "status": "PROCESSING"},
    {"job_id": "ccc...", "filename": "receipt.png", "status": "PROCESSING"}
  ]
}
```

---

## GET /jobs/batch/:batch_id — Batch Progress

**This is how you track 10,000 files.** Poll this endpoint to see which files are done.

```bash
curl http://localhost:8000/jobs/batch/b5c6d7e8-... \
  -H "Authorization: Bearer tp-proj-dev-key-123"
```

**Response — In Progress:**
```json
{
  "batch_id": "b5c6d7e8-...",
  "status": "PROCESSING",
  "progress": "66.7%",
  "total": 3,
  "completed": 2,
  "failed": 0,
  "processing": 1,
  "uploaded": 0,
  "files": [
    {
      "job_id": "aaa...",
      "filename": "inv1.pdf",
      "status": "COMPLETED",
      "confidence": 0.93,
      "page_count": 2,
      "result_url": "/jobs/aaa.../result",
      "created_at": "2026-02-26T01:30:00Z",
      "updated_at": "2026-02-26T01:30:12Z"
    },
    {
      "job_id": "bbb...",
      "filename": "inv2.pdf",
      "status": "COMPLETED",
      "confidence": 0.91,
      "page_count": 1,
      "result_url": "/jobs/bbb.../result",
      "created_at": "2026-02-26T01:30:00Z",
      "updated_at": "2026-02-26T01:30:15Z"
    },
    {
      "job_id": "ccc...",
      "filename": "receipt.png",
      "status": "PROCESSING",
      "created_at": "2026-02-26T01:30:00Z",
      "updated_at": "2026-02-26T01:30:00Z"
    }
  ]
}
```

**Response — All Done:**
```json
{
  "batch_id": "b5c6d7e8-...",
  "status": "COMPLETED",
  "progress": "100.0%",
  "total": 3,
  "completed": 3,
  "failed": 0,
  "processing": 0,
  "uploaded": 0,
  "files": [ ... ]
}
```

**Response — Some Failed:**
```json
{
  "batch_id": "b5c6d7e8-...",
  "status": "COMPLETED_WITH_ERRORS",
  "progress": "100.0%",
  "total": 3,
  "completed": 2,
  "failed": 1,
  "files": [
    {"job_id": "aaa...", "filename": "inv1.pdf", "status": "COMPLETED", "result_url": "/jobs/aaa.../result"},
    {"job_id": "bbb...", "filename": "inv2.pdf", "status": "COMPLETED", "result_url": "/jobs/bbb.../result"},
    {"job_id": "ccc...", "filename": "corrupt.pdf", "status": "FAILED", "error": "Preprocessing failed: invalid PDF"}
  ]
}
```

### Filter by Status

Only show completed files:
```bash
GET /jobs/batch/b5c6d7e8-...?status=COMPLETED
```

Only show failed files:
```bash
GET /jobs/batch/b5c6d7e8-...?status=FAILED
```

### Batch Status Lifecycle

| Status | Meaning |
|--------|---------|
| `PROCESSING` | Some files still running |
| `COMPLETED` | All files done, zero failures |
| `COMPLETED_WITH_ERRORS` | All done, but some failed |
| `FAILED` | Every file failed |

### Recommended Polling Pattern

```python
import time, requests

HEADERS = {"Authorization": "Bearer tp-proj-dev-key-123"}
batch_id = "b5c6d7e8-..."

while True:
    r = requests.get(f"http://localhost:8000/jobs/batch/{batch_id}", headers=HEADERS)
    data = r.json()
    print(f"{data['progress']} — {data['completed']}/{data['total']} done")

    if data["status"] in ["COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED"]:
        break
    time.sleep(2)  # Poll every 2 seconds

# Get results for completed files
for f in data["files"]:
    if f["status"] == "COMPLETED":
        result = requests.get(f"http://localhost:8000{f['result_url']}", headers=HEADERS)
        print(f"{f['filename']}: {result.json()}")
```

---

## Queue Management Endpoints

### GET /queue/status — Queue Status

Get current queue status including length and estimated wait time.

```bash
curl http://localhost:8000/queue/status \
  -H "Authorization: Bearer tp-proj-dev-key-123"
```

**Response (HTTP 200)**:
```json
{
  "queue_length": 5,
  "estimated_wait_time_seconds": 75,
  "processing_count": 1,
  "avg_wait_time_seconds": 15.3,
  "avg_processing_time_seconds": 12.8,
  "throughput_per_hour": 280
}
```

### Queue Behavior

The system implements a Redis-based request queue with the following characteristics:

- **Concurrency Control**: Only 1 GPU inference request executes at a time to prevent GPU memory exhaustion
- **Priority Levels**: Requests can be assigned priority (0=normal, 1=high, 2=urgent)
- **FIFO Processing**: Within the same priority level, requests are processed in order
- **Automatic Retry**: Failed requests are automatically retried with exponential backoff (max 3 attempts)
- **Queue Capacity**: Maximum 50 pending requests (returns HTTP 429 when full)

### Queue Position in Job Status

When you check job status, you'll see queue information:

```bash
curl http://localhost:8000/jobs/<JOB_ID> \
  -H "Authorization: Bearer tp-proj-dev-key-123"
```

**Response when queued**:
```json
{
  "job_id": "abc-123-...",
  "status": "QUEUED",
  "queue_position": 3,
  "estimated_wait_time_seconds": 45,
  "enqueued_at": "2026-02-26T10:30:00Z"
}
```

**Response when processing**:
```json
{
  "job_id": "abc-123-...",
  "status": "PROCESSING",
  "started_at": "2026-02-26T10:30:45Z",
  "progress": "Processing page 2 of 5"
}
```

## Enhanced Extraction Options

### Granularity Levels

The `granularity` parameter controls the level of detail in bounding box extraction:

| Granularity | Description | Use Case |
|-------------|-------------|----------|
| `block` | Paragraph/section level boxes | General document layout |
| `line` | Line-level boxes | Line-by-line analysis |
| `word` | Individual word boxes | Word highlighting, search |

**Example with word-level granularity**:
```bash
curl -X POST http://localhost:8000/jobs/upload \
  -H "Authorization: Bearer tp-proj-dev-key-123" \
  -F "document=@invoice.pdf" \
  -F "granularity=word" \
  -F "include_coordinates=true"
```

**Response includes word-level boxes**:
```json
{
  "result": {
    "words": [
      {"word": "Invoice", "bbox": [100, 50, 60, 20], "confidence": 0.98},
      {"word": "Number:", "bbox": [165, 50, 55, 20], "confidence": 0.97},
      {"word": "INV-2026-0042", "bbox": [225, 50, 110, 20], "confidence": 0.96}
    ]
  }
}
```

### Key-Value Pair Extraction

The `key_value` output format extracts structured key-value pairs with separate bounding boxes for keys and values:

```bash
curl -X POST http://localhost:8000/jobs/upload \
  -H "Authorization: Bearer tp-proj-dev-key-123" \
  -F "document=@form.pdf" \
  -F "output_formats=key_value" \
  -F "include_coordinates=true"
```

**Response**:
```json
{
  "result": {
    "key_values": [
      {
        "key": "Invoice Number",
        "key_bbox": [100, 50, 120, 20],
        "value": "INV-2026-0042",
        "value_bbox": [230, 50, 130, 20],
        "confidence": 0.95,
        "key_confidence": 0.97,
        "value_confidence": 0.94,
        "association_confidence": 0.96
      },
      {
        "key": "Date",
        "key_bbox": [100, 80, 40, 20],
        "value": "2026-02-25",
        "value_bbox": [150, 80, 100, 20],
        "confidence": 0.93,
        "key_confidence": 0.96,
        "value_confidence": 0.92,
        "association_confidence": 0.91
      }
    ]
  }
}
```

**Supported Key-Value Patterns**:
- Colon-separated: "Label: Value"
- Table-based: Key in first column, value in second column
- Form-field: Label above or beside input field
- Multi-value: One key with multiple associated values

### Extraction Format Combinations

You can combine multiple output formats:

```bash
curl -X POST http://localhost:8000/jobs/upload \
  -H "Authorization: Bearer tp-proj-dev-key-123" \
  -F "document=@invoice.pdf" \
  -F "output_formats=text,json,key_value,table" \
  -F "granularity=word" \
  -F "include_coordinates=true" \
  -F "include_word_confidence=true"
```

**Response includes all requested formats**:
```json
{
  "result": {
    "text": "INVOICE\nInvoice Number: INV-2026-0042...",
    "json": {
      "document_type": "invoice",
      "fields": {...}
    },
    "key_values": [...],
    "tables": [...],
    "words": [...]
  }
}
```

## Error Responses and Retry Behavior

### Error Response Format

All errors follow a consistent structure:

```json
{
  "error": {
    "message": "Descriptive error message",
    "type": "error_type",
    "code": "error_code",
    "retry_after_seconds": 60,
    "details": {
      "additional": "context"
    }
  }
}
```

### HTTP Status Codes

| Code | Type | Description | Retry? |
|------|------|-------------|--------|
| 400 | `invalid_request_error` | Bad parameters, invalid format | No |
| 401 | `invalid_request_error` | Missing/invalid API key | No |
| 413 | `document_too_large` | Document exceeds 10MB limit | No |
| 429 | `rate_limit_error` | Queue full or rate limit exceeded | Yes |
| 503 | `service_unavailable` | GPU memory insufficient or service restart | Yes |
| 500 | `server_error` | Internal server error | Yes |

### Automatic Retry Behavior

The system automatically retries failed requests with exponential backoff:

- **Initial Interval**: 1 second
- **Backoff Coefficient**: 2.0 (doubles each retry)
- **Maximum Interval**: 60 seconds
- **Maximum Attempts**: 3
- **Jitter**: ±10% to prevent thundering herd

**Example retry sequence**:
1. First attempt fails → Wait 1 second
2. Second attempt fails → Wait 2 seconds
3. Third attempt fails → Wait 4 seconds
4. Final failure → Job marked as FAILED

### Retryable Errors

The following errors trigger automatic retry:
- GPU memory errors (503)
- Triton stub process restarts (503)
- Temporary network failures
- Transient model inference errors

### Non-Retryable Errors

The following errors do NOT trigger retry:
- Document too large (413)
- Invalid request format (400)
- Authentication failures (401)
- Unsupported extraction format (400)

### Error Examples

**Queue Full (HTTP 429)**:
```json
{
  "error": {
    "message": "Queue is full, please retry later",
    "type": "rate_limit_error",
    "code": "queue_full",
    "retry_after_seconds": 120,
    "details": {
      "queue_length": 50,
      "max_queue_length": 50
    }
  }
}
```

**GPU Memory Insufficient (HTTP 503)**:
```json
{
  "error": {
    "message": "Insufficient GPU memory available",
    "type": "service_unavailable",
    "code": "gpu_memory_error",
    "retry_after_seconds": 60,
    "details": {
      "available_memory_gb": 1.2,
      "required_memory_gb": 2.0
    }
  }
}
```

**Document Too Large (HTTP 413)**:
```json
{
  "error": {
    "message": "Document exceeds maximum size limit",
    "type": "document_too_large",
    "code": "document_size_exceeded",
    "details": {
      "document_size_mb": 15.3,
      "max_size_mb": 10.0
    }
  }
}
```

**Processing Timeout (HTTP 500)**:
```json
{
  "error": {
    "message": "Processing timeout exceeded",
    "type": "server_error",
    "code": "processing_timeout",
    "details": {
      "timeout_seconds": 1800,
      "pages_completed": 5,
      "total_pages": 20
    }
  }
}
```

### Client Retry Recommendations

When implementing client-side retry logic:

1. **Respect `retry_after_seconds`**: Wait at least this long before retrying
2. **Implement exponential backoff**: Increase wait time between retries
3. **Add jitter**: Randomize retry timing to prevent thundering herd
4. **Set maximum retries**: Limit to 3-5 attempts
5. **Check error type**: Only retry retryable errors (429, 503, 500)

**Example Python retry logic**:
```python
import time
import requests

def upload_with_retry(file_path, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = requests.post(
                "http://localhost:8000/jobs/upload",
                headers={"Authorization": "Bearer tp-proj-dev-key-123"},
                files={"document": open(file_path, "rb")}
            )
            
            if response.status_code == 202:
                return response.json()
            
            if response.status_code in [429, 503]:
                error = response.json()["error"]
                wait_time = error.get("retry_after_seconds", 60)
                print(f"Retrying after {wait_time}s...")
                time.sleep(wait_time)
                continue
            
            # Non-retryable error
            response.raise_for_status()
            
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                time.sleep(wait_time)
            else:
                raise
    
    raise Exception("Max retries exceeded")
```

## Other Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/health` | No | Service health check |
| GET | `/queue/status` | Bearer | Queue status and metrics |
| GET | `/jobs` | Bearer | List all jobs |
| GET | `/jobs/:id` | Bearer | Job status + metadata |
| GET | `/jobs/:id/result` | Bearer | Download extraction result |
| GET | `/jobs/batch/:id` | Bearer | Batch progress |
| GET | `/metrics` | No | Prometheus metrics |
| GET | `/admin/stats` | Bearer | Job statistics |
| GET | `/admin/cache` | Bearer | Redis cache stats |

---

## Supported Files

| Category | Formats |
|----------|---------|
| Documents | `.pdf`, `.docx`, `.xlsx`, `.pptx` |
| Images | `.png`, `.jpg`, `.jpeg`, `.tiff`, `.bmp`, `.webp` |
| Text | `.txt`, `.csv` |
| Archives | `.zip`, `.rar`, `.7z`, `.tar`, `.tar.gz`, `.tar.bz2`, `.tar.xz` |

---

## Image Preprocessing (Automatic)

| Step | Adaptive? | Can disable? |
|------|-----------|-------------|
| Quality profiling | — | No |
| Auto-rotate (90°/180°/270°) | ✅ | No |
| Perspective fix (camera) | ✅ | `enhance=false` |
| Shadow removal | ✅ | `enhance=false` |
| CLAHE contrast | ✅ scales with input | `enhance=false` |
| NL-Means denoise | ✅ h=3–15 | `enhance=false` |
| Unsharp mask | ✅ | `enhance=false` |
| Hough deskew | ✅ | `deskew=false` |
| Bicubic upscale | ✅ | `enhance=false` |

Table borders are **never affected**.

---

## Caching

| Cache | TTL | Effect |
|-------|-----|--------|
| Document dedup (SHA-256) | 24h | Identical file → instant result |
| Result cache | 1h | Fast retrieval |
| Status cache | 5min | Fast polling |

---

## Rate Limiting

**100 requests/minute** per API key.

| Header | Value |
|--------|-------|
| `x-ratelimit-limit-requests` | `100` |
| `x-ratelimit-remaining-requests` | Remaining count |
| `x-ratelimit-reset-requests` | `60s` |

---

## Errors

All errors follow this structure (same pattern as OpenAI):

```json
{
  "error": {
    "message": "Incorrect API key provided.",
    "type": "invalid_request_error",
    "code": "invalid_api_key"
  }
}
```

| Code | Type | When |
|------|------|------|
| 400 | `invalid_request_error` | Bad params, missing file |
| 401 | `invalid_request_error` | Missing or wrong API key |
| 429 | `rate_limit_error` | Too many requests |
| 500 | `server_error` | Internal failure |

---

## Architecture

```
Client → API Gateway (Go/Gin)
              ├── Auth (Bearer tp-proj-*)
              ├── Rate Limit (100/min per key)
              ├── Cache Dedup (Redis SHA-256)
              ├── Upload → MinIO
              └── Temporal Workflow
                    ├── 1. Preprocess (Go + Python/OpenCV)
                    ├── 2. GLM-OCR (Triton + GPU)
                    │     ├── Prebuilt format prompts
                    │     ├── Custom user prompts
                    │     └── Spatial + confidence output
                    └── 3. Post-Process (Python)
                          ├── PII redaction
                          └── Confidence scoring
```
