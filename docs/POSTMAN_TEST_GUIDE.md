# IDEP Postman Guide (Complete, Current State)

This is a complete Postman guide for the current implementation in this repo, including:

- exact endpoints
- full upload option reference
- defaults and allowed values
- how each option affects output
- full end-to-end request sequence
- direct GLM debug request for coordinate validation

## 0. Current Runtime State

- API Gateway HTTP: `http://localhost:8000`
- GLM OCR HTTP: `http://localhost:8002`
- GLM OCR gRPC: `localhost:50062`
- Paddle OCR HTTP: `http://localhost:8001`
- Paddle OCR gRPC: `localhost:50061`
- Local mode currently configured with `USE_ISOLATED_GPU_EXECUTOR=false`

## 1. Postman Environment Setup

Create environment `IDEP Local`:

- `baseUrl` = `http://localhost:8000`
- `glmUrl` = `http://localhost:8002`
- `apiKey` = `tp-proj-dev-key-123`
- `jobId` = ``

Use this auth header in protected requests:

- `Authorization: Bearer {{apiKey}}`

## 2. End-to-End Request Flow

Use this order in your collection:

1. `GET {{baseUrl}}/health`
2. `POST {{baseUrl}}/jobs/upload`
3. `GET {{baseUrl}}/jobs/{{jobId}}` (repeat until terminal state)
4. `GET {{baseUrl}}/jobs/{{jobId}}/result`
5. Optional debug: `POST {{glmUrl}}/extract-region`

Alternative single-call flow:

1. `GET {{baseUrl}}/health`
2. `POST {{baseUrl}}/jobs/extract` (returns final output directly, or `202` with status/result URLs on timeout)

## 3. Request 1: Health

- Method: `GET`
- URL: `{{baseUrl}}/health`
- Header: `Authorization: Bearer {{apiKey}}`

Expected:

- HTTP `200`
- Component health payload

## 4. Request 2: Upload Document (Full Options)

- Method: `POST`
- URL: `{{baseUrl}}/jobs/upload`
- Header: `Authorization: Bearer {{apiKey}}`
- Body: `form-data`

### 4.1 Required field

- `document` (type `File`): PDF/PNG/JPG/JPEG/TIFF/BMP/WEBP

### 4.2 Full option list (API Gateway `/jobs/upload`)

All options are sent as `form-data` text fields.

| Option | Type | Default | Allowed / Example | What it does |
|---|---|---|---|---|
| `output_formats` | string | `text` | `text,json,structured` | Final output format(s), comma-separated |
| `prompt` | string | empty | `Extract invoice fields...` | Custom extraction instruction |
| `fast_mode` | bool | `false` | `true` | Faster generation profile |
| `include_coordinates` | bool | `false` | `true` | Include bounding boxes |
| `include_word_confidence` | bool | `false` | `true` | Include word-level confidence |
| `include_line_confidence` | bool | `false` | `true` | Include line-level confidence |
| `include_page_layout` | bool | `false` | `true` | Include page layout metadata |
| `language` | string | `auto` | `auto`, `en`, `hi` | Language hint |
| `granularity` | string | `block` | `block`, `line`, `word` | Extraction granularity |
| `redact_pii` | bool | `false` | `true` | Redact sensitive values |
| `enhance` | bool | `true` | `false` | Toggle preprocessing enhancement |
| `deskew` | bool | `true` | `false` | Toggle deskew |
| `max_pages` | string/int | `0` | `0`, `1`, `5` | Page limit (`0` = all pages) |
| `temperature` | string/float | `0.0` | `0.0`, `0.2` | Generation randomness |
| `max_tokens` | string/int | `4096` | `512`, `1024` | Output token cap |
| `precision_mode` | string | `high` | `normal`, `high` | Extraction quality mode |
| `extract_fields` | string | empty | `invoice_no,total_amount` | Restrict to selected fields |
| `enable_layout_detection` | bool | `false` | `true` | Enable layout-based region detection |
| `min_confidence` | string/float | `0.5` | `0.5`, `0.7` | Layout region confidence threshold |
| `detect_tables` | bool | `true` | `true` | Enable table region detection |
| `detect_formulas` | bool | `true` | `true` | Enable formula region detection |
| `parallel_region_processing` | bool | `true` | `true` | Process regions in parallel |
| `max_parallel_regions` | string/int | `5` | `5`, `8` | Max concurrent regions |
| `cache_layout_results` | bool | `true` | `true` | Cache layout-detection output |

### 4.3 Recommended full test payload values

Use these values for a full-feature run:

- `output_formats=text,json,structured`
- `fast_mode=true`
- `include_coordinates=true`
- `include_word_confidence=true`
- `include_line_confidence=true`
- `include_page_layout=true`
- `language=auto`
- `granularity=word`
- `redact_pii=false`
- `enhance=false`
- `deskew=false`
- `max_pages=0`
- `temperature=0.0`
- `max_tokens=512`
- `precision_mode=high`
- `enable_layout_detection=true`
- `min_confidence=0.5`
- `detect_tables=true`
- `detect_formulas=true`
- `parallel_region_processing=true`
- `max_parallel_regions=5`
- `cache_layout_results=true`

### 4.4 Detailed Explanation of Options and Values

Use this section when deciding values for quality, speed, and output shape.

#### Output shaping options

- `output_formats`
  - Purpose: controls which output representations are generated.
  - Typical values: `text`, `json`, `structured`, or comma-separated combinations.
  - Recommendation:
    - Use `text` for simplest reading.
    - Use `json` when downstream code parses fields.
    - Use `text,json,structured` when you want all artifacts.

- `prompt`
  - Purpose: custom extraction instruction.
  - Example: `Extract invoice number, date, total amount, vendor GSTIN as JSON.`
  - Behavior: if empty, default extraction behavior is used.

- `extract_fields`
  - Purpose: restrict output to specific requested fields.
  - Input format in `/jobs/upload`: comma-separated string.
  - Examples:
    - `extract_fields=amount`
    - `extract_fields=total_amount`
    - `extract_fields=invoice_number,date,total_amount`
  - Important behavior:
    - Matching is flexible (substring-style), so `amount` can match keys like `total_amount`.
    - Empty `extract_fields` means no field filtering (all detected fields are returned).
  - Recommendation:
    - For invoices, prefer explicit names like `total_amount` for best consistency.
    - If documents vary, use `amount,total_amount`.

#### Speed and quality controls

- `fast_mode`
  - `true`: faster response, may reduce detail in difficult documents.
  - `false`: generally better quality on complex layouts.

- `precision_mode`
  - `normal`: lower latency, good for cleaner docs.
  - `high`: better extraction quality, often preferred for production invoice parsing.

- `max_tokens`
  - Caps output length from model generation.
  - Low values (`256`, `512`) reduce latency but can truncate long outputs.
  - Higher values (`1024+`) are safer for multi-section documents.

- `temperature`
  - Lower (`0.0`) is deterministic and stable for extraction.
  - Higher values may increase variability and are usually not needed for OCR extraction.

#### Geometry and confidence options

- `include_coordinates`
  - Adds box coordinates for detected content.
  - Useful for overlays and UI highlighting.

- `include_word_confidence`
  - Adds confidence at word granularity.
  - Useful when low-confidence tokens should be flagged.

- `include_line_confidence`
  - Adds line-level confidence.
  - Useful for line-based validation workflows.

- `include_page_layout`
  - Adds page layout metadata.
  - Useful for post-analysis and debugging region extraction.

- `granularity`
  - `block`: coarser chunks, lower payload size.
  - `line`: medium detail.
  - `word`: highest detail and largest payload.

#### Layout detection controls

- `enable_layout_detection`
  - Enables region detection stage before region extraction.
  - Recommended `true` for complex docs with tables/forms.

- `min_confidence`
  - Threshold for layout regions.
  - Lower values capture more candidates (more noise possible).
  - Higher values reduce noise but may miss weak regions.

- `detect_tables`
  - When `true`, attempts to detect and process table regions.

- `detect_formulas`
  - When `true`, attempts to detect formula/math regions.

- `parallel_region_processing`
  - Enables concurrent processing of detected regions.
  - Usually improves latency on multi-region pages.

- `max_parallel_regions`
  - Hard limit for region concurrency.
  - Increase carefully to avoid GPU/CPU contention.

- `cache_layout_results`
  - Reuses layout output where applicable.
  - Useful for repeated extraction workflows.

#### Document preprocessing and scope options

- `enhance`
  - Enables image enhancement in preprocessing.
  - Helpful for low-quality scans; may add processing time.

- `deskew`
  - Corrects tilted/skewed page orientation.
  - Usually useful for scanned invoices/photos.

- `max_pages`
  - `0`: process all pages.
  - Positive integer: process only first N pages.
  - Useful to reduce time/cost on large PDFs.

- `language`
  - `auto`: automatic language detection.
  - Set explicit language when documents are known and consistent.

- `redact_pii`
  - Masks sensitive values in output when enabled.
  - Use `true` for compliance-focused workflows.

### 4.5 Single-Field Extraction Example (`amount` only)

If you want only amount, set:

- `extract_fields=amount`

Expected behavior:

- System tries to return only amount-related fields.
- Because matching is flexible, it may return `total_amount` as the key.
- If no amount-like field is found in the document, that field can be missing.

For stricter invoice behavior, use one of these:

- `extract_fields=total_amount`
- `extract_fields=amount,total_amount`

Practical tip:

- Keep `output_formats=json` (or include `json`) when you need deterministic field parsing downstream.

Expected upload response:

- HTTP `202` for new job
- HTTP `200` if duplicate document was returned from cache
- JSON includes `job_id`, `status_url`, `result_url`, and accepted `options`

## 4A. Request 2A: Single Call Extract (`/jobs/extract`)

- Method: `POST`
- URL: `{{baseUrl}}/jobs/extract`
- Header: `Authorization: Bearer {{apiKey}}`
- Body: `form-data`

Use the same fields as `/jobs/upload` (`document`, `output_formats`, coordinates/confidence/layout flags, etc.) plus these wait controls:

| Option | Type | Default | Allowed / Example | What it does |
|---|---|---|---|---|
| `wait_timeout_seconds` | int | `1200` | `1200`, `1800`, `3600` | Maximum sync wait before timeout response |
| `poll_interval_ms` | int | `1000` | `500`, `1000`, `2000` | Poll interval while waiting for completion |

Server clamp rules:
- `wait_timeout_seconds` is clamped to `10..7200`
- `poll_interval_ms` is clamped to `200..5000`

Recommended long-run payload in Postman:
- `output_formats=structured`
- `include_coordinates=true`
- `include_word_confidence=true`
- `include_page_layout=true`
- `wait_timeout_seconds=1200`
- `poll_interval_ms=1000`

Expected responses:
- `200` when extraction completes within wait window (full final `result` returned inline)
- `202` when still processing after timeout (`job_id`, `status_url`, `result_url` returned)
- `401` when bearer token is missing/invalid

## 5. Save `jobId` Automatically in Postman

Add this in the `Tests` tab of upload request:

```javascript
const body = pm.response.json();
if (body.job_id) {
  pm.environment.set("jobId", body.job_id);
}
```

## 6. Request 3: Poll Job Status

- Method: `GET`
- URL: `{{baseUrl}}/jobs/{{jobId}}`
- Header: `Authorization: Bearer {{apiKey}}`

Status lifecycle:

- `QUEUED`
- `PROCESSING`
- `COMPLETED` or `FAILED`

Tip: Keep sending every 2-5 seconds until terminal state.

## 7. Request 4: Get Final Result

- Method: `GET`
- URL: `{{baseUrl}}/jobs/{{jobId}}/result`
- Header: `Authorization: Bearer {{apiKey}}`

Expected (completed jobs):

- HTTP `200`
- Envelope fields such as:
  - `schema_version`
  - `job_id`
  - `model`
  - `output_formats`
  - `result`
  - `result_text`
  - `raw_pages`

## 8. Coordinates and Confidence: Where They Appear

Current behavior:

- Upload accepts and forwards coordinate/confidence options.
- Direct GLM endpoint (`/extract-region`) reliably returns coordinate-rich fields like `bounding_boxes`.
- Final gateway result may expose details under `raw_pages`, while `result` may be post-processed/flattened depending on path.

If you need guaranteed coordinate-first final output in `/jobs/{id}/result`, keep `raw_pages` in consumer logic or patch post-processing aggregation to preserve `bounding_boxes` and `word_boxes` directly in `result`.

## 9. Direct GLM Debug (Raw Coordinate Validation)

Use this only for debugging model output independently of the full workflow.

- Method: `POST`
- URL: `{{glmUrl}}/extract-region`
- Header: `Content-Type: application/json`
- Body type: `raw` -> `JSON`

```json
{
  "image": "<BASE64_IMAGE>",
  "region_type": "text",
  "options": {
    "fast_mode": true,
    "include_coordinates": true,
    "include_confidence": true,
    "include_word_confidence": true,
    "include_line_confidence": true,
    "include_page_layout": true,
    "granularity": "word",
    "output_format": "json",
    "max_tokens": 512
  }
}
```

Typical direct response fields:

- `content`
- `confidence`
- `processing_time_ms`
- `bounding_boxes`
- `word_boxes`
- `key_value_pairs`

## 10. Common Errors and Fixes

- `401 Unauthorized`: wrong/missing bearer token.
- `404 Job not found`: invalid `jobId` or cleared state.
- `503 Service Unavailable`: model loading, GPU memory pressure, or dependency unavailable.
- Job `FAILED` quickly: inspect GLM service logs and worker logs; verify `50062` listener.
- Unexpected cached response: change file bytes (rename alone is not always enough).

## 11. Recommended Minimal vs Full Profiles

Use one of these option profiles depending on need.

### Minimal fast profile

- `output_formats=text`
- `fast_mode=true`
- `max_tokens=512`
- `precision_mode=normal`
- `enhance=false`
- `deskew=false`

### Full detail profile

- `output_formats=text,json,structured`
- `include_coordinates=true`
- `include_word_confidence=true`
- `include_line_confidence=true`
- `include_page_layout=true`
- `enable_layout_detection=true`
- `detect_tables=true`
- `detect_formulas=true`
- `granularity=word`

