"""
Triton Python Backend " GLM-OCR  (zai-org/GLM-OCR)
====================================================
Industry-standard two-stage document-understanding pipeline:

  Stage 1 " Layout Detection
    PP-DocLayout-V3 detects every region (text, table, formula, title,
    figure, ) and returns pixel-level bounding boxes (bbox_2d).

  Stage 2 " Parallel Region Recognition
    Each detected region is cropped and sent to the GLM-OCR vision-language
    model with the task-appropriate prompt:
         "Text Recognition:"
         "Table Recognition:"
         "Formula Recognition:"

  Assembly
    Results are merged into the official SDK output schema:
        [{"index": N, "label": "text", "content": "", "bbox_2d": [x1,y1,x2,y2]}]

Execution paths (chosen automatically at start-up):
  1. SDK    " glmocr Python SDK (GlmOcr) with embedded vLLM endpoint;
              provides the complete PP-DocLayout + parallel-OCR pipeline.
  2. NATIVE " Direct model loading via -- Transformers +
              PP-DocLayout-V3 via paddlepaddle/paddleocr.
  3. MOCK   " Deterministic rich output for local dev / CI (no GPU needed).

Environment variables:
  GLM_MODEL_PATH      HuggingFace model ID or local path
                      default: "zai-org/GLM-OCR"
  IDEP_MOCK_INFERENCE "true" forces MOCK mode            default: "false"
  IDEP_STRICT_REAL    "true" raises if model fails load  default: "true"
  GLM_PRECISION_MODE  "high" enables precision inference  default: "normal"
  PADDLEOCR_HOME      Where PaddleOCR caches models       default: /opt/paddleocr
"""

from __future__ import annotations

import io as _io
import json
import logging
import os
import traceback
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# """ Environment """"""""""""""""""""""""""""""""""""""""""""""""""""""""""""

MODEL_PATH: str  = os.getenv("GLM_MODEL_PATH", "zai-org/GLM-OCR")
MOCK_MODE: bool  = os.getenv("IDEP_MOCK_INFERENCE", "false").lower() == "true"
STRICT_REAL: bool = os.getenv("IDEP_STRICT_REAL",    "true").lower() == "true"
DEFAULT_PRECISION: str = os.getenv("GLM_PRECISION_MODE", "normal").lower()

# """ Optional heavy imports """"""""""""""""""""""""""""""""""""""""""""""""""

torch = None
Image = None
AutoProcessor = None
AutoModelForImageTextToText = None
_TRANSFORMERS_OK = False
_PADDLEOCR_OK    = False
_GLMOCR_SDK_OK   = False

try:
    import triton_python_backend_utils as pb_utils  # type: ignore
except ImportError:
    pb_utils = None  # outside Triton (unit-test / standalone)

import struct as _struct

if not MOCK_MODE:
    try:
        import torch as _torch
        from transformers import AutoProcessor as _AP, AutoModelForImageTextToText as _AMFITT
        from PIL import Image as _Image
        torch = _torch
        AutoProcessor = _AP
        AutoModelForImageTextToText = _AMFITT
        Image = _Image
        _TRANSFORMERS_OK = True
        logger.info("... Transformers + PIL available")
    except ImportError as exc:
        logger.warning("Transformers/PIL not available: %s", exc)
        if STRICT_REAL:
            raise RuntimeError(f"ML deps missing in strict-real mode: {exc}") from exc
        MOCK_MODE = True

    if _TRANSFORMERS_OK:
        try:
            from paddleocr import PPStructure as _PPStructure  # type: ignore  # noqa: F401
            _PADDLEOCR_OK = True
            logger.info("... PaddleOCR / PP-DocLayout available (stage-1 layout)")
        except ImportError:
            logger.info("PaddleOCR not installed -- running full-page OCR (no layout split)")

    try:
        from glmocr import GlmOcr  # type: ignore  # noqa: F401
        _GLMOCR_SDK_OK = True
        logger.info("... glmocr SDK available")
    except ImportError:
        logger.info("glmocr SDK not installed -- using native transformers path")


# """ GLM-OCR Official Task Prompts """"""""""""""""""""""""""""""""""""""""""
# Reference: https://huggingface.co/zai-org/GLM-OCR

TASK_PROMPTS: dict[str, str] = {
    # Core GLM-OCR document-parsing tasks
    "text":    "Text Recognition:",
    "table":   "Table Recognition:",
    "formula": "Formula Recognition:",
    # Extended tasks (structured output)
    "markdown": (
        "Text Recognition: Convert this document region to well-structured Markdown. "
        "Use proper heading levels (#, ##, ###), bold for field labels, "
        "pipe-syntax tables, and bullet lists where appropriate."
    ),
    "key_value": (
        "Text Recognition: Extract all key-value pairs from this document region. "
        "Return a flat JSON object with label names as keys."
    ),
    "structured": (
        "Text Recognition: Perform comprehensive extraction on this document region. "
        "Return JSON with keys: document_type, raw_text, fields, tables, "
        "handwritten_sections."
    ),
    "json": (
        "Text Recognition: Extract all information from this document region as "
        "structured JSON. Include document_type, fields as key-value pairs, "
        "line_items as arrays, and any tables. Return valid JSON only."
    ),
}

# Maps PP-DocLayout-V3 region labels ' task prompt key
LABEL_TO_TASK: dict[str, str] = {
    "text":          "text",  "title":         "text",  "heading":       "text",
    "paragraph":     "text",  "caption":        "text",  "footnote":      "text",
    "header":        "text",  "footer":         "text",  "page_number":   "text",
    "list_item":     "text",  "handwriting":    "text",  "seal":          "text",
    "table":         "table", "table_caption":  "text",
    "formula":       "formula",
    "figure":        "text",  "figure_caption": "text",
    "code":          "text",  "reference":      "text",  "abstract":      "text",
}

# """ Output schema (mirrors official glmocr SDK) """""""""""""""""""""""""""""

def _make_element(
    index: int,
    label: str,
    content: str,
    bbox_2d: "list[int] | None",
    confidence: float,
    extra: "dict | None" = None,
) -> "dict[str, Any]":
    """Single element in the official glmocr SDK JSON format."""
    elem: dict = {
        "index":      index,
        "label":      label,
        "content":    content,
        "bbox_2d":    bbox_2d,
        "confidence": round(confidence, 4),
    }
    if extra:
        elem.update(extra)
    return elem


def _assemble_result(
    elements: list,
    page_w: int,
    page_h: int,
    model_name: str,
    mode: str,
    precision: str,
    prompt_tokens: int,
    completion_tokens: int,
    output_format: str = "text",
) -> dict:
    """Assemble the canonical result dict returned by this Triton model."""
    md_parts: list = []
    for el in elements:
        lbl     = el.get("label", "text")
        content = el.get("content", "")
        if not content:
            continue
        if lbl in ("title", "heading"):
            md_parts.append(f"## {content}")
        elif lbl == "formula":
            md_parts.append(f"$$\n{content}\n$$")
        else:
            md_parts.append(content)

    confs    = [el.get("confidence", 0.9) for el in elements if el.get("bbox_2d") is not None]
    avg_conf = round(sum(confs) / len(confs), 4) if confs else 0.90

    return {
        "pages": [{"page": 1, "width": page_w, "height": page_h, "elements": elements}],
        "markdown":   "\n\n".join(md_parts),
        "model":      model_name,
        "mode":       mode,
        "precision":  precision,
        "confidence": avg_conf,
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    }


# ****************************************************************************
# TritonPythonModel
# ****************************************************************************

class TritonPythonModel:
    """Triton Python Backend for GLM-OCR with PP-DocLayout spatial pipeline."""

    # "" Triton lifecycle """"""""""""""""""""""""""""""""""""""""""""""""""""

    def initialize(self, args: dict) -> None:
        global MOCK_MODE
        self.model_config: dict = json.loads(args.get("model_config", "{}"))
        self.model_name: str   = MODEL_PATH
        self.precision: str    = DEFAULT_PRECISION
        self.processor         = None
        self.model             = None
        self.layout_engine     = None
        self.sdk_parser        = None

        logger.info(
            "Initializing GLM-OCR  mock=%s strict_real=%s precision=%s model=%s",
            MOCK_MODE, STRICT_REAL, self.precision, MODEL_PATH,
        )


        if MOCK_MODE:
            logger.warning("  MOCK inference mode active -- no GPU used")
            return

        # "" Path A: official glmocr SDK """""""""""""""""""""""""""""""""""
        if _GLMOCR_SDK_OK:
            try:
                from glmocr import GlmOcr  # type: ignore
                self.sdk_parser = GlmOcr()
                logger.info("... GLM-OCR via official SDK")
                return
            except Exception as exc:
                logger.warning("glmocr SDK init failed (%s) -- falling back to native", exc)

        # "" Path B: Native Transformers """""""""""""""""""""""""""""""""""
        if not _TRANSFORMERS_OK:
            if STRICT_REAL:
                raise RuntimeError("Transformers unavailable in strict-real mode")
            MOCK_MODE = True
            return

        try:
            logger.info("Loading %s ", MODEL_PATH)
            self.processor = AutoProcessor.from_pretrained(
                MODEL_PATH, trust_remote_code=True
            )
            # Use float16 instead of bfloat16 -- RTX 2050 (Turing/Ada) handles
            # fp16 natively, while bf16 may be software-emulated and very slow.
            self.model = AutoModelForImageTextToText.from_pretrained(
                MODEL_PATH,
                torch_dtype=torch.float16,
                device_map="auto",
                trust_remote_code=True,
            )
            self.model.eval()
            logger.info("... GLM-OCR model loaded  device=%s", next(self.model.parameters()).device)

            # GPU warm-up pass disabled -- on RTX 2050 (4 GB) the first
            # generate() triggers CUDA JIT compilation which can take 20+ min
            # with device_map="auto" layer offloading.  Better to let the first
            # real request absorb the one-time cost.
            logger.info("GPU warm-up skipped (will JIT on first request)")
        except Exception as exc:
            if STRICT_REAL:
                raise RuntimeError(f"Model load failed in strict-real mode: {exc}") from exc
            logger.error("Model load failed: %s -- MOCK mode", exc)
            MOCK_MODE = True
            return

        # "" Path B-ext: PP-DocLayout for spatial stage """"""""""""""""""""
        if _PADDLEOCR_OK:
            try:
                from paddleocr import PPStructure  # type: ignore
                self.layout_engine = PPStructure(
                    table=True, ocr=False, show_log=False,
                    layout_model_dir=os.getenv("PADDLEOCR_HOME", "/opt/paddleocr"),
                )
                logger.info("... PP-DocLayout-V3 ready")
            except Exception as exc:
                logger.warning("PP-DocLayout init failed (%s) -- layout stage disabled", exc)

    def finalize(self) -> None:
        logger.info("Finalizing GLM-OCR backend")
        if self.model is not None and torch is not None:
            del self.model
            del self.processor
            torch.cuda.empty_cache()

    # "" Request dispatch """"""""""""""""""""""""""""""""""""""""""""""""""""

    def execute(self, requests):
        responses = []
        for request in requests:
            try:
                responses.append(self._handle(request))
            except Exception as exc:
                tb = traceback.format_exc()
                logger.error("Inference error: %s\n%s", exc, tb)
                if pb_utils:
                    responses.append(
                        pb_utils.InferenceResponse(error=pb_utils.TritonError(str(exc)))
                    )
                else:
                    responses.append({"error": str(exc), "traceback": tb})
        return responses

    def _handle(self, request):
        image_ref: str       = ""
        prompt_override: str = ""
        options: dict        = {}
        precision_flag: str  = self.precision

        req_params: dict = {}
        if pb_utils and hasattr(request, "parameters"):
            try:
                p = request.parameters()
                if isinstance(p, str):
                    req_params = json.loads(p) if p else {}
                elif isinstance(p, dict):
                    req_params = p
            except Exception:
                req_params = {}

        # Prefer request-level parameters to avoid Python backend tensor
        # IPC corruption for variable-length string payloads in this setup.
        if req_params:
            image_ref = str(req_params.get("image_ref", image_ref) or image_ref)
            prompt_override = str(req_params.get("prompt", prompt_override) or prompt_override)
            precision_flag = str(req_params.get("precision_mode", precision_flag) or precision_flag)
            raw_options = req_params.get("options_json", "")
            if isinstance(raw_options, (dict, list)):
                options = raw_options if isinstance(raw_options, dict) else {"_list": raw_options}
            elif isinstance(raw_options, str) and raw_options.strip():
                options = json.loads(raw_options)

        if pb_utils:
            img_t = pb_utils.get_input_tensor_by_name(request, "images")
            if img_t is not None and not image_ref:
                v = _first(img_t)
                image_ref = v.decode() if isinstance(v, bytes) else str(v)

            p_t = pb_utils.get_input_tensor_by_name(request, "prompt")
            if p_t is not None and not prompt_override:
                v = _first(p_t)
                prompt_override = v.decode() if isinstance(v, bytes) else str(v)

            o_t = pb_utils.get_input_tensor_by_name(request, "options")
            if o_t is not None and not options:
                v = _first(o_t)
                raw = v.decode('utf-8') if isinstance(v, bytes) else str(v)
                options = json.loads(raw) if raw.strip() else {}

            pm_t = pb_utils.get_input_tensor_by_name(request, "precision_mode")
            if pm_t is not None and not precision_flag:
                v = _first(pm_t)
                precision_flag = v.decode() if isinstance(v, bytes) else str(v)

        include_coords: bool      = bool(options.get("include_coordinates",     True))
        include_word_conf: bool   = bool(options.get("include_word_confidence", False))
        include_page_layout: bool = bool(options.get("include_page_layout",     False))
        output_format: str        = str(options.get("output_format",  "text")).lower()
        max_tokens: int           = int(str(options.get("max_tokens", "8192")))
        max_tokens                = max(64, min(max_tokens, 8192))
        precision: str            = precision_flag if precision_flag else self.precision
        # extract_fields: list of field names the caller wants back (e.g. ["date", "amount"])
        # Empty list means "return everything".
        extract_fields: list      = [str(f) for f in options.get("extract_fields") or []]

        if MOCK_MODE or (self.model is None and self.sdk_parser is None):

            result = _MockEngine.run(
                image_ref=image_ref,
                prompt_override=prompt_override,
                output_format=output_format,
                include_coords=include_coords,
                include_word_conf=include_word_conf,
                include_page_layout=include_page_layout,
                precision=precision,
            )
        elif self.sdk_parser is not None:
            result = self._sdk_inference(image_ref, output_format, include_coords, precision)
        else:
            result = self._native_inference(
                image_ref=image_ref,
                prompt_override=prompt_override,
                output_format=output_format,
                include_coords=include_coords,
                include_word_conf=include_word_conf,
                max_tokens=max_tokens,
                precision=precision,
            )

        # Apply field-level filtering when the caller only wants specific fields
        if extract_fields:
            result = _filter_by_fields(result, extract_fields)

        result_json = json.dumps(result, ensure_ascii=False, indent=2)
        conf = float(result.get("confidence", 0.90))

        if pb_utils:
            text_obj = np.array([result_json], dtype=np.object_)
            text_serialized = pb_utils.serialize_byte_tensor(text_obj)
            if isinstance(text_serialized, (bytes, bytearray)):
                text_serialized = np.frombuffer(text_serialized, dtype=np.uint8)
            try:
                import sys as _sys
                _sys.stderr.write(
                    f"[OUT_SHAPE] serialized dtype={getattr(text_serialized, 'dtype', type(text_serialized))} "
                    f"shape={getattr(text_serialized, 'shape', '?')} size={getattr(text_serialized, 'size', '?')}\n"
                )
                _sys.stderr.flush()
            except Exception:
                pass
            out_text = pb_utils.Tensor("generated_text", text_serialized)
            out_conf = pb_utils.Tensor("confidence",     np.array([conf],       dtype=np.float32))
            return pb_utils.InferenceResponse(output_tensors=[out_text, out_conf])
        return result

    # "" SDK inference path """"""""""""""""""""""""""""""""""""""""""""""""""

    def _sdk_inference(self, image_ref, output_format, include_coords, precision):
        """Use official glmocr SDK -- PP-DocLayout + parallel OCR out of the box."""
        result_obj   = self.sdk_parser.parse(image_ref)
        raw_elements = result_obj.json_result if hasattr(result_obj, "json_result") else []
        markdown     = result_obj.markdown     if hasattr(result_obj, "markdown")     else ""

        elements = [
            _make_element(
                index=i,
                label=el.get("label", "text"),
                content=el.get("content", ""),
                bbox_2d=el.get("bbox_2d"),
                confidence=el.get("confidence", 0.92),
            )
            for i, el in enumerate(raw_elements)
        ]
        confs    = [e["confidence"] for e in elements]
        avg_conf = round(sum(confs) / len(confs), 4) if confs else 0.92
        return {
            "pages":      [{"page": 1, "elements": elements}],
            "markdown":   markdown,
            "model":      "zai-org/GLM-OCR",
            "mode":       "sdk",
            "precision":  precision,
            "confidence": avg_conf,
            "usage":      {"prompt_tokens": 0, "completion_tokens": 0},
        }

    # "" Native two-stage inference """"""""""""""""""""""""""""""""""""""""""

    def _native_inference(
        self, image_ref, prompt_override, output_format,
        include_coords, include_word_conf, max_tokens, precision,
    ):
        """
        Two-stage pipeline:
          1. PP-DocLayout-V3  '  region bboxes + labels
          2. GLM-OCR          '  text/table/formula for each region
        Falls back to single full-page pass when layout engine is absent.
        """
        img = _load_image(image_ref)
        page_w, page_h = img.size
        elements: list = []
        total_pt = total_ct = 0

        if self.layout_engine is not None and include_coords:
            regions = self._detect_layout(img)
            for i, region in enumerate(regions):
                bbox   = region["bbox"]          # [x1, y1, x2, y2]
                label  = region["label"]
                task   = LABEL_TO_TASK.get(label, "text")
                prompt = TASK_PROMPTS[task]
                crop   = img.crop(bbox)
                content, pt, ct = self._run_glm_ocr(crop, prompt, max_tokens, precision, output_format)
                total_pt += pt; total_ct += ct
                elements.append(_make_element(i, label, content, list(map(int, bbox)),
                                              region.get("confidence", 0.90)))
        else:
            prompt  = prompt_override if prompt_override else _format_to_prompt(output_format)
            content, pt, ct = self._run_glm_ocr(img, prompt, max_tokens, precision, output_format)
            total_pt += pt; total_ct += ct
            elements.append(_make_element(
                0, "page", content,
                [0, 0, page_w, page_h] if include_coords else None, 0.92,
            ))

        if include_word_conf and precision in ("high", "precision"):
            elements = self._enrich_word_confidence(elements, img)

        return _assemble_result(elements, page_w, page_h, "zai-org/GLM-OCR",
                                "native", precision, total_pt, total_ct, output_format)

    def _detect_layout(self, img):
        """Run PP-DocLayout-V3 ' list of region dicts sorted in reading order."""
        img_np  = np.array(img.convert("RGB"))
        results = self.layout_engine(img_np)
        regions = []
        for block in results:
            if "bbox" not in block:
                continue
            x1, y1, x2, y2 = (int(v) for v in block["bbox"])
            regions.append({
                "bbox":       [x1, y1, x2, y2],
                "label":      str(block.get("type", "text")).lower(),
                "confidence": float(block.get("score", 0.90)),
            })
        regions.sort(key=lambda r: (r["bbox"][1], r["bbox"][0]))
        return regions

    def _run_glm_ocr(self, img, prompt, max_new_tokens, precision, output_format):
        """
        Single GLM-OCR inference call.
        Returns (content, prompt_tokens, completion_tokens).
        Precision mode: do_sample=False + stronger repetition_penalty.
        """
        messages = [{
            "role": "user",
            "content": [{"type": "image", "image": img}, {"type": "text", "text": prompt}],
        }]
        inputs = self.processor.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True,
            return_dict=True, return_tensors="pt",
        ).to(self.model.device)
        inputs.pop("token_type_ids", None)

        gen_kwargs: dict = {
            "max_new_tokens":     max_new_tokens,
            "do_sample":          False,
            "repetition_penalty": 1.05 if precision not in ("high", "precision") else 1.15,
        }
        if precision in ("high", "precision"):
            gen_kwargs["length_penalty"] = 1.0

        with torch.no_grad():
            outputs = self.model.generate(**inputs, **gen_kwargs)

        prompt_len = inputs["input_ids"].shape[1]
        new_ids    = outputs[:, prompt_len:]
        text = self.processor.decode(new_ids[0], skip_special_tokens=False)
        for tok in ("<|endoftext|>", "<|user|>", "<|assistant|>", "</s>"):
            text = text.replace(tok, "").strip()

        return text, prompt_len, int(new_ids.shape[1])

    def _enrich_word_confidence(self, elements, img):
        """Precision-mode: word-level recognition pass for each detected region."""
        for el in elements:
            bbox = el.get("bbox_2d")
            if not bbox:
                continue
            crop = img.crop(bbox)
            word_text, _, _ = self._run_glm_ocr(
                crop,
                "Text Recognition: List every individual word on a separate line.",
                1024, "high", "text",
            )
            words = [w.strip() for w in word_text.splitlines() if w.strip()]
            el["words"] = _approximate_word_bboxes(words, bbox)
        return elements


# ****************************************************************************
# Mock engine  (rich, deterministic, full official-SDK spatial schema)
# ****************************************************************************

class _MockEngine:
    PAGE_W, PAGE_H = 612, 792

    @classmethod
    def run(cls, *, image_ref, prompt_override, output_format, include_coords,
            include_word_conf, include_page_layout, precision):
        build_fn = {
            "markdown":   cls._markdown,
            "table":      cls._table,
            "key_value":  cls._key_value,
            "structured": cls._structured,
            "json":       cls._json_format,
            "formula":    cls._formula,
        }.get(output_format, cls._text)

        elements = build_fn(include_coords)

        if include_word_conf:
            for el in elements:
                if el.get("bbox_2d"):
                    el["words"] = cls._words(el["bbox_2d"])
        if include_page_layout:
            for el in elements:
                el["layout_type"] = el.get("label", "text")

        return _assemble_result(
            elements, cls.PAGE_W, cls.PAGE_H,
            "zai-org/GLM-OCR", "mock", precision, 47, 312, output_format,
        )

    # "" Element builders """"""""""""""""""""""""""""""""""""""""""""""""""

    @classmethod
    def _text(cls, coords):
        rows = [
            (0, "title",   "INVOICE",                                       [100,  50, 312,  90], 0.99),
            (1, "text",    "Invoice #: INV-2026-0042",                       [100, 100, 450, 125], 0.97),
            (2, "text",    "Date: February 25, 2026",                        [100, 130, 420, 155], 0.96),
            (3, "heading", "Bill To:",                                       [100, 180, 200, 205], 0.98),
            (4, "text",    "Customer Inc.\n123 Business Ave\nNew York, NY", [100, 210, 400, 290], 0.95),
            (5, "table",   cls._invoice_table_md(),                          [ 80, 300, 540, 420], 0.97),
            (6, "text",    "Subtotal: $1,234.56",                            [100, 440, 300, 460], 0.96),
            (7, "text",    "Tax (10%): $123.46",                             [100, 465, 300, 485], 0.95),
            (8, "text",    "Total Due: $1,358.02",                           [100, 495, 320, 520], 0.98),
        ]
        return [_make_element(i, lbl, c, bbox if coords else None, conf)
                for i, lbl, c, bbox, conf in rows]

    @classmethod
    def _json_format(cls, coords):
        payload = {
            "document_type": "invoice",
            "fields": {
                "invoice_number": cls._fv("INV-2026-0042", [280, 100, 460, 125], 0.97, coords),
                "date":           cls._fv("2026-02-25",    [280, 130, 430, 155], 0.96, coords),
                "vendor":         cls._fv("Acme Corp",     [280, 160, 420, 185], 0.95, coords),
                "bill_to":        cls._fv("Customer Inc.", [280, 210, 460, 235], 0.94, coords),
                "subtotal":       cls._fv("$1,234.56",     [400, 440, 520, 460], 0.97, coords),
                "tax":            cls._fv("$123.46",       [400, 465, 500, 485], 0.96, coords),
                "total_amount":   cls._fv("$1,358.02",     [400, 495, 530, 520], 0.98, coords),
            },
            "line_items": [
                cls._line_item("Widget A", 10, "$100.00", "$1,000.00", [100, 330, 540, 355], coords),
                cls._line_item("Widget B",  5,  "$46.91",   "$234.56", [100, 358, 540, 383], coords),
            ],
        }
        return [_make_element(0, "json", json.dumps(payload, indent=2),
                              [80, 80, 540, 530] if coords else None, 0.96)]

    @classmethod
    def _markdown(cls, coords):
        md = (
            "# INVOICE\n\n"
            "**Invoice #:** INV-2026-0042  \n**Date:** February 25, 2026\n\n"
            "## Bill To\nCustomer Inc.  \n123 Business Ave, Suite 456  \nNew York, NY 10001\n\n"
            "## Line Items\n\n" + cls._invoice_table_md() +
            "\n\n---\n- **Subtotal:** $1,234.56\n- **Tax (10%):** $123.46\n- **Total Due:** $1,358.02"
        )
        return [_make_element(0, "markdown", md, [80, 50, 540, 530] if coords else None, 0.97)]

    @classmethod
    def _table(cls, coords):
        payload = [{
            "table_id": 1,
            "title":   "Invoice Line Items",
            "headers": ["Description", "Qty", "Unit Price", "Total"],
            "rows":    [["Widget A", "10", "$100.00", "$1,000.00"],
                        ["Widget B",  "5",  "$46.91",   "$234.56"]],
            "footer":  ["", "", "Subtotal", "$1,234.56"],
            **({"bbox_2d": [80, 300, 540, 420],
                "cell_coordinates": {
                    "header_row": [[80, 300, 215, 325], [215, 300, 265, 325],
                                   [265, 300, 405, 325], [405, 300, 540, 325]],
                    "data_rows":  [[[80, 330, 215, 355], [215, 330, 265, 355],
                                    [265, 330, 405, 355], [405, 330, 540, 355]],
                                   [[80, 358, 215, 383], [215, 358, 265, 383],
                                    [265, 358, 405, 383], [405, 358, 540, 383]]],
                }} if coords else {}),
        }]
        return [_make_element(0, "table", json.dumps(payload, indent=2),
                              [80, 300, 540, 420] if coords else None, 0.97)]

    @classmethod
    def _key_value(cls, coords):
        kv = {
            "invoice_number": cls._fv("INV-2026-0042", [280, 100, 460, 125], 0.97, coords),
            "date":           cls._fv("2026-02-25",    [280, 130, 430, 155], 0.96, coords),
            "vendor":         cls._fv("Acme Corp",     [280, 160, 420, 185], 0.95, coords),
            "bill_to":        cls._fv("Customer Inc.", [280, 210, 460, 235], 0.94, coords),
            "subtotal":       cls._fv("$1,234.56",     [400, 440, 520, 460], 0.97, coords),
            "tax":            cls._fv("$123.46",       [400, 465, 500, 485], 0.96, coords),
            "total_amount":   cls._fv("$1,358.02",     [400, 495, 530, 520], 0.98, coords),
            "payment_terms":  cls._fv("Net 30",        [280, 525, 380, 545], 0.92, coords),
        }
        return [_make_element(0, "key_value", json.dumps(kv, indent=2),
                              [80, 80, 540, 545] if coords else None, 0.96)]

    @classmethod
    def _structured(cls, coords):
        s = {
            "document_type": "invoice",
            "language": "en",
            "page_count": 1,
            "raw_text": "INVOICE\nInvoice #: INV-2026-0042\nDate: 2026-02-25\nTotal Due: $1,358.02",
            "fields": {
                "invoice_number": cls._fv("INV-2026-0042", [280, 100, 460, 125], 0.97, coords),
                "date":           cls._fv("2026-02-25",    [280, 130, 430, 155], 0.96, coords),
                "total_amount":   cls._fv("$1,358.02",     [400, 495, 530, 520], 0.98, coords),
            },
            "tables": [{
                "headers": ["Description", "Qty", "Unit Price", "Total"],
                "rows":    [["Widget A", "10", "$100.00", "$1,000.00"],
                            ["Widget B",  "5",  "$46.91",   "$234.56"]],
                **({"bbox_2d": [80, 300, 540, 420],
                    "cell_coordinates": {
                        "header_row": [[80, 300, 215, 325], [215, 300, 265, 325],
                                       [265, 300, 405, 325], [405, 300, 540, 325]],
                        "data_rows":  [[[80, 330, 215, 355], [215, 330, 265, 355],
                                        [265, 330, 405, 355], [405, 330, 540, 355]],
                                       [[80, 358, 215, 383], [215, 358, 265, 383],
                                        [265, 358, 405, 383], [405, 358, 540, 383]]],
                    }} if coords else {}),
            }],
            "handwritten_sections": [],
        }
        return [_make_element(0, "structured", json.dumps(s, indent=2),
                              [80, 50, 540, 545] if coords else None, 0.96)]

    @classmethod
    def _formula(cls, coords):
        formulas = [
            (r"E = mc^2",                  [100, 100, 300, 135], 0.98),
            (r"\int_0^\infty e^{-x^2}dx",  [100, 160, 350, 195], 0.95),
            (r"F = G\frac{m_1 m_2}{r^2}",  [100, 220, 380, 255], 0.96),
        ]
        return [
            _make_element(i, "formula", tex, bbox if coords else None, conf)
            for i, (tex, bbox, conf) in enumerate(formulas)
        ]

    # "" Helpers """""""""""""""""""""""""""""""""""""""""""""""""""""""""""

    @staticmethod
    def _invoice_table_md():
        return (
            "| Description | Qty | Unit Price | Total |\n"
            "|-------------|-----|------------|-------|\n"
            "| Widget A    |  10 | $100.00    | $1,000.00 |\n"
            "| Widget B    |   5 |  $46.91    |   $234.56 |"
        )

    @staticmethod
    def _fv(value, bbox, conf, include):
        return {"value": value, "bbox_2d": bbox, "confidence": round(conf, 2)} if include else value

    @staticmethod
    def _line_item(desc, qty, unit, total, bbox, include):
        item = {"description": desc, "quantity": qty, "unit_price": unit, "total": total}
        if include:
            item["bbox_2d"]    = bbox
            item["confidence"] = 0.94
        return item

    @classmethod
    def _words(cls, parent_bbox):
        x1, y1, x2, y2 = parent_bbox
        sample = ["INVOICE", "INV-2026-0042", "February", "25,",
                  "2026", "Widget", "A", "$100.00", "$1,000.00", "Total"]
        step = max(1, (x2 - x1) // len(sample))
        return [
            {"word": w, "bbox_2d": [x1 + i*step, y1, x1 + i*step + min(step, 80), y2],
             "confidence": round(0.94 + (i % 5) * 0.01, 2)}
            for i, w in enumerate(sample)
        ]


# ****************************************************************************
# Standalone helpers
# ****************************************************************************

def _first(tensor):
    """Extract the first scalar value from a Triton tensor.

    For TYPE_UINT8 tensors (used as a workaround for the Triton 2.42.0
    BYTES serialization bug), decodes the raw uint8 array to bytes.
    For TYPE_STRING/BYTES tensors, unwraps the numpy object array.
    """
    arr = tensor.as_numpy()
    # UINT8 workaround: the client encodes strings as raw UTF-8 byte arrays
    if hasattr(arr, 'dtype') and arr.dtype == np.uint8:
        return arr.tobytes()
    while isinstance(arr, np.ndarray):
        if arr.size == 0:
            raise ValueError("Empty tensor")
        arr = arr.flat[0]
    return arr


def _load_image(image_ref: str):
    if image_ref.startswith("data:"):
        import base64
        _, b64 = image_ref.split(",", 1)
        return Image.open(_io.BytesIO(base64.b64decode(b64))).convert("RGB")
    if not os.path.isabs(image_ref):
        image_ref = os.path.join("/tmp/idep", image_ref)
    if not os.path.exists(image_ref):
        raise FileNotFoundError(f"Image not found: {image_ref}")
    return Image.open(image_ref).convert("RGB")


def _format_to_prompt(output_format: str) -> str:
    return TASK_PROMPTS.get(output_format.strip().lower(), TASK_PROMPTS["text"])


def _approximate_word_bboxes(words: list, parent_bbox: list) -> list:
    x1, y1, x2, y2 = parent_bbox
    if not words:
        return []
    step = max(1, (x2 - x1) // len(words))
    return [
        {"word": w, "bbox_2d": [x1 + i*step, y1, min(x1 + i*step + max(step, 10), x2), y2],
         "confidence": 0.93}
        for i, w in enumerate(words)
    ]


def _field_match(key: str, field: str) -> bool:
    """True when *key* and *field* are a case-insensitive substring match."""
    k = key.lower().replace(" ", "_").replace("-", "_")
    f = field.lower().replace(" ", "_").replace("-", "_")
    return f in k or k in f


def _filter_by_fields(result: dict, fields: "list[str]") -> dict:
    """Post-filter a GLM-OCR result envelope to retain only elements related to
    the requested *fields* (e.g. ``["date", "amount"]``).

    Strategy
    --------
    * For JSON / key-value content (element content is a valid JSON object):
      only the matching keys are kept.
    * For plain-text elements: kept when any field keyword appears in the
      element's content or label.
    * A flat ``"fields"`` convenience dict is always attached at the top level
      with the best-effort extracted values so consumers don't have to walk
      ``pages[].elements[]``.
    """
    import re  # local import -- only used when extract_fields is set

    if not fields:
        return result

    field_keys = [f.lower().replace(" ", "_").replace("-", "_") for f in fields]
    result["extract_fields"] = fields  # echo what was requested

    flat: dict = {}

    for page in result.get("pages", []):
        kept = []
        for el in page.get("elements", []):
            content = el.get("content", "")
            label   = el.get("label",   "text")

            # -- Try JSON content (key_value / json / structured output) ------
            try:
                obj = json.loads(content)
                if isinstance(obj, dict):
                    filtered_obj = {
                        k: v for k, v in obj.items()
                        if any(_field_match(k, fk) for fk in field_keys)
                    }
                    if filtered_obj:
                        flat.update(filtered_obj)
                        el = dict(el)
                        el["content"] = json.dumps(filtered_obj, ensure_ascii=False)
                        kept.append(el)
                    continue
            except (json.JSONDecodeError, ValueError):
                pass

            # -- Plain-text element: keep when any keyword appears ------------
            searchable = (content + " " + label).lower().replace("-", "_").replace(" ", "_")
            if any(fk in searchable for fk in field_keys):
                kept.append(el)
                # Best-effort: extract "key: value" patterns
                for fk, orig in zip(field_keys, fields):
                    pattern = rf'{re.escape(fk.replace("_", "[ _-]?"))}[:\s]+([^\n]+)'
                    m = re.search(pattern, content.lower())
                    if m and orig not in flat:
                        flat[orig] = m.group(1).strip()

        page["elements"] = kept

    if flat:
        result["fields"] = flat
    return result

