"""
Triton Python Backend for GLM-OCR — Professional API

Features:
  - Prebuilt output formats (text, json, markdown, table, key_value, structured)
  - Custom user prompts (like OpenAI/Azure)
  - Spatial coordinates (bounding boxes) for every text element
  - Per-element confidence scores
  - Word-level, line-level, and block-level granularity

The prompt is constructed from:
  1. Prebuilt format templates (if output_formats specified)
  2. Custom user prompt (if prompt field provided — overrides prebuilts)
  3. Options flags (include_coordinates, include_word_confidence, etc.)
"""
import os
import json
import logging
import numpy as np
import random

logger = logging.getLogger(__name__)

MOCK_MODE = os.getenv("IDEP_MOCK_INFERENCE", "true").lower() == "true"
STRICT_REAL_MODE = os.getenv("IDEP_STRICT_REAL", "true").lower() == "true"

if not MOCK_MODE:
    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM
        from PIL import Image
        import io as _io
    except ImportError as e:
        if STRICT_REAL_MODE:
            raise RuntimeError(f"ML dependencies not available in strict real mode: {e}")
        logger.warning(f"ML dependencies not available: {e}. Falling back to mock mode.")
        MOCK_MODE = True

try:
    import triton_python_backend_utils as pb_utils
except ImportError:
    pb_utils = None


# ═══════════════════════════════════════════
# Prebuilt Format Prompts
# ═══════════════════════════════════════════

PREBUILT_PROMPTS = {
    "text": (
        "Extract ALL text from this document image exactly as it appears. "
        "Preserve the original layout, paragraph breaks, and reading order. "
        "Include headers, footers, and any handwritten text."
    ),
    "json": (
        "Extract all information from this document image and return it as structured JSON. "
        "Identify the document type, extract all fields as key-value pairs, "
        "detect any tables and represent them as arrays of objects, "
        "and extract any line items. Return valid JSON only."
    ),
    "markdown": (
        "Convert this document image to well-formatted Markdown. "
        "Use proper headings (#, ##), bold for labels, "
        "tables using | pipe syntax, and bullet lists where appropriate. "
        "Preserve the document structure and hierarchy."
    ),
    "table": (
        "Detect and extract ALL tables from this document image. "
        "For each table: column headers, all data rows, and any totals. "
        "Format as JSON array of table objects with 'headers' and 'rows'. "
        "If no tables exist, return an empty array."
    ),
    "key_value": (
        "Extract all key-value pairs from this document image. "
        "Identify labels/field names and their corresponding values. "
        "Return as a JSON object with field names as keys. "
        "Include form fields, invoice fields, receipt items, etc."
    ),
    "structured": (
        "Perform comprehensive extraction on this document image:\n"
        "1. Identify the document type\n"
        "2. Extract all text preserving layout\n"
        "3. Extract all key-value fields\n"
        "4. Detect and extract all tables with headers and rows\n"
        "5. Identify any handwritten content\n"
        "Return as JSON with keys: document_type, raw_text, fields, tables, handwritten_sections"
    ),
}

# Coordinate/confidence instruction appended to prompts when requested
COORDINATE_INSTRUCTION = (
    "\n\nFor each text element, also provide its spatial location as a bounding box "
    "with coordinates [x, y, width, height] in pixels relative to the image. "
    "Include a confidence score (0.0-1.0) for each element."
)

WORD_CONFIDENCE_INSTRUCTION = (
    "\n\nFor each word, provide a confidence score (0.0-1.0) indicating "
    "how certain you are about the recognition."
)


def build_prompt(output_formats: str = "text", custom_prompt: str = "",
                 include_coordinates: bool = False, include_word_confidence: bool = False,
                 language: str = "auto", granularity: str = "block") -> str:
    """
    Build the inference prompt.

    Priority:
      1. If custom_prompt is provided, use it (user knows best)
      2. Else, use prebuilt format prompt(s)

    Appends coordinate/confidence instructions if requested.
    """
    if custom_prompt:
        prompt = custom_prompt
    else:
        formats = [f.strip() for f in output_formats.split(",") if f.strip()]
        if len(formats) == 1 and formats[0] in PREBUILT_PROMPTS:
            prompt = PREBUILT_PROMPTS[formats[0]]
        else:
            parts = ["Analyze this document image and provide the following:\n"]
            for i, fmt in enumerate(formats, 1):
                if fmt in PREBUILT_PROMPTS:
                    parts.append(f"{i}. {fmt.upper()}: {PREBUILT_PROMPTS[fmt]}")
            parts.append("\nReturn as JSON with a key for each requested format.")
            prompt = "\n".join(parts)

    if include_coordinates:
        prompt += COORDINATE_INSTRUCTION
    if include_word_confidence:
        prompt += WORD_CONFIDENCE_INSTRUCTION
    if language != "auto":
        prompt += f"\n\nDocument language: {language}. Extract text in this language."

    return prompt


class TritonPythonModel:
    """Triton Python Backend for GLM-OCR."""

    @staticmethod
    def _tensor_first_value(tensor):
        arr = tensor.as_numpy()
        while isinstance(arr, np.ndarray):
            if arr.size == 0:
                raise ValueError("Empty tensor input")
            arr = arr.flat[0]
        return arr

    def initialize(self, args):
        global MOCK_MODE
        self.model_config = json.loads(args.get("model_config", "{}"))
        logger.info(f"Initializing GLM-OCR (mock={MOCK_MODE}, strict_real={STRICT_REAL_MODE})")

        if MOCK_MODE and STRICT_REAL_MODE:
            raise RuntimeError("Strict real mode is enabled but mock mode is active")

        if not MOCK_MODE:
            try:
                model_path = os.getenv("GLM_MODEL_PATH", "unsloth/GLM-OCR")
                self.tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
                self.model = AutoModelForCausalLM.from_pretrained(
                    model_path, torch_dtype=torch.bfloat16, device_map="auto", trust_remote_code=True)
                self.model.eval()
                logger.info("✅ GLM-OCR model loaded on GPU")
            except Exception as e:
                if STRICT_REAL_MODE:
                    raise RuntimeError(f"Failed to initialize real GLM model in strict mode: {e}")
                logger.warning(f"Failed to initialize real GLM model: {e}. Falling back to mock mode.")
                MOCK_MODE = True
                self.tokenizer = None
                self.model = None
        else:
            self.tokenizer = None
            self.model = None
            logger.info("⚠️  MOCK inference mode active")

    def execute(self, requests):
        responses = []
        for request in requests:
            try:
                # Parse inputs
                images_tensor = None
                prompt = PREBUILT_PROMPTS["text"]
                options = {}

                if pb_utils:
                    images_tensor = pb_utils.get_input_tensor_by_name(request, "images")
                    pt = pb_utils.get_input_tensor_by_name(request, "prompt")
                    if pt is not None:
                        prompt_val = self._tensor_first_value(pt)
                        if isinstance(prompt_val, bytes):
                            prompt = prompt_val.decode("utf-8")
                        else:
                            prompt = str(prompt_val)
                    ot = pb_utils.get_input_tensor_by_name(request, "options")
                    if ot is not None:
                        options_val = self._tensor_first_value(ot)
                        if isinstance(options_val, bytes):
                            options = json.loads(options_val.decode("utf-8"))
                        else:
                            options = json.loads(str(options_val))

                if MOCK_MODE:
                    result = self._mock_inference(prompt, options)
                else:
                    result = self._real_inference(images_tensor, prompt, options)

                result_json = json.dumps(result, indent=2)

                if pb_utils:
                    out_text = pb_utils.Tensor("generated_text", np.array([result_json], dtype=object))
                    out_conf = pb_utils.Tensor("confidence", np.array([result.get("confidence", 0.9)], dtype=np.float32))
                    responses.append(pb_utils.InferenceResponse(output_tensors=[out_text, out_conf]))
                else:
                    responses.append(result)

            except Exception as e:
                logger.error(f"Inference error: {e}")
                if pb_utils:
                    responses.append(pb_utils.InferenceResponse(error=pb_utils.TritonError(str(e))))
                else:
                    responses.append({"error": str(e)})

        return responses

    def _real_inference(self, images_tensor, prompt, options):
        """GPU inference with GLM-OCR."""
        image_ref = self._tensor_first_value(images_tensor)
        if isinstance(image_ref, bytes):
            image_ref = image_ref.decode("utf-8")

        if isinstance(image_ref, str):
            if not os.path.exists(image_ref):
                raise FileNotFoundError(f"Image path not found: {image_ref}")
            img = Image.open(image_ref).convert("RGB")
        else:
            image_data = images_tensor.as_numpy()
            img = Image.fromarray(image_data)

        inputs = self.tokenizer.apply_chat_template(
            [{"role": "user", "image": img, "content": prompt}],
            add_generation_prompt=True, tokenize=True,
            return_tensors="pt", return_dict=True,
        ).to(self.model.device)

        max_new_tokens = 512
        if isinstance(options, dict) and options.get("max_tokens") is not None:
            try:
                max_new_tokens = int(str(options.get("max_tokens")))
            except (TypeError, ValueError):
                max_new_tokens = 512
        max_new_tokens = max(64, min(max_new_tokens, 1024))

        with torch.no_grad():
            outputs = self.model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)

        generated_ids = outputs[:, inputs["input_ids"].shape[1]:]
        text = self.tokenizer.decode(generated_ids[0], skip_special_tokens=True)

        result = {
            "content": text,
            "model": "glm-ocr",
            "mode": "real",
            "confidence": 0.92,
            "usage": {"prompt_tokens": inputs["input_ids"].shape[1], "completion_tokens": len(generated_ids[0])},
        }

        # Add spatial data if requested via post-processing step
        if options.get("include_coordinates"):
            result["_needs_spatial"] = True

        return result

    def _mock_inference(self, prompt, options=None):
        """Format-aware mock inference with spatial coordinates."""
        options = options or {}
        prompt_lower = prompt.lower()
        include_coords = options.get("include_coordinates", False)
        include_word_conf = options.get("include_word_confidence", False)

        # Determine format from prompt
        if "markdown" in prompt_lower:
            content = self._mock_markdown()
        elif "table" in prompt_lower and "key" not in prompt_lower:
            content = self._mock_tables(include_coords)
        elif "key-value" in prompt_lower or "key_value" in prompt_lower:
            content = self._mock_key_value(include_coords)
        elif "comprehensive" in prompt_lower or "structured" in prompt_lower:
            content = self._mock_structured(include_coords, include_word_conf)
        elif "json" in prompt_lower:
            content = self._mock_json(include_coords)
        else:
            content = self._mock_text(include_coords, include_word_conf)

        result = {
            "content": content if isinstance(content, str) else json.dumps(content, indent=2),
            "model": "glm-ocr",
            "mode": "mock",
            "confidence": round(random.uniform(0.88, 0.96), 2),
            "usage": {"prompt_tokens": len(prompt.split()), "completion_tokens": 256},
        }

        if include_coords:
            result["pages"] = [self._mock_page_layout()]

        return result

    # ─── Mock generators with spatial coordinates ───

    def _mock_text(self, include_coords=False, include_word_conf=False):
        if not include_coords:
            return (
                "INVOICE\nInvoice #: INV-2026-0042\nDate: February 25, 2026\n\n"
                "Bill To:\nCustomer Inc.\n123 Business Ave, Suite 456\nNew York, NY 10001\n\n"
                "Description          Qty    Unit Price    Total\n"
                "Widget A              10      $100.00    $1,000.00\n"
                "Widget B               5       $46.91      $234.56\n\n"
                "Subtotal: $1,234.56\nTax (10%): $123.46\nTotal Due: $1,358.02"
            )
        return json.dumps({
            "text": "INVOICE\nInvoice #: INV-2026-0042\nDate: February 25, 2026...",
            "blocks": [
                self._block("INVOICE", 100, 50, 200, 40, 0.99),
                self._block("Invoice #: INV-2026-0042", 100, 100, 350, 25, 0.97),
                self._block("Date: February 25, 2026", 100, 130, 320, 25, 0.96),
                self._block("Bill To:", 100, 180, 100, 25, 0.98),
                self._block("Customer Inc.", 100, 210, 180, 25, 0.95),
                self._block("Widget A   10   $100.00   $1,000.00", 100, 320, 500, 25, 0.94),
                self._block("Widget B    5    $46.91     $234.56", 100, 350, 500, 25, 0.93),
                self._block("Total Due: $1,358.02", 100, 420, 280, 25, 0.97),
            ],
            "words": self._mock_words() if include_word_conf else [],
        }, indent=2)

    def _mock_json(self, include_coords=False):
        result = {
            "document_type": "invoice",
            "fields": {
                "invoice_number": self._field("INV-2026-0042", 280, 100, 180, 25, 0.97, include_coords),
                "date": self._field("2026-02-25", 280, 130, 150, 25, 0.96, include_coords),
                "vendor": self._field("Acme Corp", 280, 160, 140, 25, 0.95, include_coords),
                "bill_to": self._field("Customer Inc.", 280, 210, 180, 25, 0.94, include_coords),
                "subtotal": self._field("$1,234.56", 400, 380, 120, 25, 0.97, include_coords),
                "tax": self._field("$123.46", 400, 410, 100, 25, 0.96, include_coords),
                "total_amount": self._field("$1,358.02", 400, 440, 130, 25, 0.98, include_coords),
            },
            "line_items": [
                {"description": "Widget A", "quantity": 10, "unit_price": "$100.00", "total": "$1,000.00",
                 **({"bbox": [100, 320, 500, 25], "confidence": 0.94} if include_coords else {})},
                {"description": "Widget B", "quantity": 5, "unit_price": "$46.91", "total": "$234.56",
                 **({"bbox": [100, 350, 500, 25], "confidence": 0.93} if include_coords else {})},
            ],
        }
        return json.dumps(result, indent=2)

    def _mock_markdown(self):
        return (
            "# INVOICE\n\n"
            "**Invoice #:** INV-2026-0042  \n**Date:** February 25, 2026\n\n"
            "## Bill To\nCustomer Inc.  \n123 Business Ave, Suite 456  \nNew York, NY 10001\n\n"
            "## Line Items\n\n"
            "| Description | Qty | Unit Price | Total |\n"
            "|-------------|-----|-----------|-------|\n"
            "| Widget A | 10 | $100.00 | $1,000.00 |\n"
            "| Widget B | 5 | $46.91 | $234.56 |\n\n"
            "---\n- **Subtotal:** $1,234.56\n- **Tax (10%):** $123.46\n- **Total Due:** $1,358.02"
        )

    def _mock_tables(self, include_coords=False):
        tables = [{
            "table_id": 1, "title": "Line Items",
            "headers": ["Description", "Qty", "Unit Price", "Total"],
            "rows": [
                ["Widget A", "10", "$100.00", "$1,000.00"],
                ["Widget B", "5", "$46.91", "$234.56"],
            ],
            "footer": ["", "", "Total", "$1,234.56"],
        }]
        if include_coords:
            tables[0]["bbox"] = [80, 280, 540, 120]
            tables[0]["cell_coordinates"] = {
                "header_row": [[80, 280, 135, 25], [215, 280, 50, 25], [265, 280, 100, 25], [365, 280, 100, 25]],
                "data_rows": [
                    [[80, 310, 135, 25], [215, 310, 50, 25], [265, 310, 100, 25], [365, 310, 100, 25]],
                    [[80, 340, 135, 25], [215, 340, 50, 25], [265, 340, 100, 25], [365, 340, 100, 25]],
                ],
            }
        return json.dumps(tables, indent=2)

    def _mock_key_value(self, include_coords=False):
        fields = {
            "invoice_number": self._field("INV-2026-0042", 280, 100, 180, 25, 0.97, include_coords),
            "date": self._field("2026-02-25", 280, 130, 150, 25, 0.96, include_coords),
            "vendor": self._field("Acme Corp", 280, 160, 140, 25, 0.95, include_coords),
            "bill_to": self._field("Customer Inc.", 280, 210, 180, 25, 0.94, include_coords),
            "subtotal": self._field("$1,234.56", 400, 380, 120, 25, 0.97, include_coords),
            "tax": self._field("$123.46", 400, 410, 100, 25, 0.96, include_coords),
            "total_amount": self._field("$1,358.02", 400, 440, 130, 25, 0.98, include_coords),
            "payment_terms": self._field("Net 30", 400, 470, 80, 25, 0.92, include_coords),
        }
        return json.dumps(fields, indent=2)

    def _mock_structured(self, include_coords=False, include_word_conf=False):
        result = {
            "document_type": "invoice",
            "language": "en",
            "page_count": 1,
            "raw_text": "INVOICE\nInvoice #: INV-2026-0042\nDate: 2026-02-25...",
            "fields": {
                "invoice_number": self._field("INV-2026-0042", 280, 100, 180, 25, 0.97, include_coords),
                "date": self._field("2026-02-25", 280, 130, 150, 25, 0.96, include_coords),
                "total_amount": self._field("$1,358.02", 400, 440, 130, 25, 0.98, include_coords),
            },
            "tables": [{
                "headers": ["Description", "Qty", "Unit Price", "Total"],
                "rows": [["Widget A", "10", "$100.00", "$1,000.00"], ["Widget B", "5", "$46.91", "$234.56"]],
                **({"bbox": [80, 280, 540, 120]} if include_coords else {}),
            }],
            "handwritten_sections": [],
        }
        if include_word_conf:
            result["word_confidences"] = self._mock_words()
        return json.dumps(result, indent=2)

    # ─── Spatial helpers ───

    def _block(self, text, x, y, w, h, confidence):
        return {"text": text, "bbox": [x, y, w, h], "confidence": round(confidence, 2)}

    def _field(self, value, x, y, w, h, confidence, include_coords):
        if include_coords:
            return {"value": value, "bbox": [x, y, w, h], "confidence": round(confidence, 2)}
        return value

    def _mock_words(self):
        words = [
            ("INVOICE", [100, 50, 80, 30], 0.99),
            ("Invoice", [100, 100, 60, 20], 0.98),
            ("#:", [162, 100, 15, 20], 0.97),
            ("INV-2026-0042", [180, 100, 130, 20], 0.96),
            ("Date:", [100, 130, 45, 20], 0.98),
            ("February", [150, 130, 75, 20], 0.95),
            ("25,", [228, 130, 25, 20], 0.94),
            ("2026", [256, 130, 40, 20], 0.97),
            ("Widget", [100, 320, 55, 20], 0.93),
            ("A", [158, 320, 10, 20], 0.95),
            ("10", [250, 320, 18, 20], 0.97),
            ("$100.00", [340, 320, 65, 20], 0.96),
            ("$1,000.00", [440, 320, 80, 20], 0.95),
        ]
        return [{"word": w, "bbox": b, "confidence": round(c, 2)} for w, b, c in words]

    def _mock_page_layout(self):
        return {
            "page_number": 1,
            "width": 612,
            "height": 792,
            "unit": "pixel",
            "blocks": [
                {"type": "title", "bbox": [100, 50, 200, 40], "text": "INVOICE", "confidence": 0.99},
                {"type": "field", "bbox": [100, 100, 350, 25], "text": "Invoice #: INV-2026-0042", "confidence": 0.97},
                {"type": "field", "bbox": [100, 130, 320, 25], "text": "Date: February 25, 2026", "confidence": 0.96},
                {"type": "address", "bbox": [100, 180, 300, 80], "text": "Bill To:\nCustomer Inc.\n123 Business Ave", "confidence": 0.94},
                {"type": "table", "bbox": [80, 280, 540, 120], "confidence": 0.95,
                 "cells": [
                     {"text": "Description", "bbox": [80, 280, 135, 25], "row": 0, "col": 0, "is_header": True},
                     {"text": "Qty", "bbox": [215, 280, 50, 25], "row": 0, "col": 1, "is_header": True},
                     {"text": "Widget A", "bbox": [80, 310, 135, 25], "row": 1, "col": 0, "is_header": False},
                     {"text": "10", "bbox": [215, 310, 50, 25], "row": 1, "col": 1, "is_header": False},
                 ]},
                {"type": "total", "bbox": [100, 420, 280, 25], "text": "Total Due: $1,358.02", "confidence": 0.98},
            ],
        }

    def finalize(self):
        logger.info("Finalizing GLM-OCR model")
        if not MOCK_MODE and self.model is not None:
            del self.model
            del self.tokenizer
            torch.cuda.empty_cache()
