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
  1. NATIVE " Direct model loading via Transformers +
              PP-DocLayout-V3 via paddlepaddle/paddleocr.
  2. MOCK   " Deterministic rich output for local dev / CI (no GPU needed).

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
from typing import Any, TypedDict, Union

import numpy as np

logger = logging.getLogger(__name__)

# """ Output Format Schemas """"""""""""""""""""""""""""""""""""""""""""""""""

class JsonOutputSchema(TypedDict, total=False):
    """Schema for JSON output format - flat structure with document_type, fields, and line_items."""
    document_type: str
    fields: dict[str, Any]
    line_items: list[dict[str, Any]]

class TableOutputSchema(TypedDict, total=False):
    """Schema for table output format - structured table with headers, rows, and optional coordinates."""
    table_id: int
    title: str
    headers: list[str]
    rows: list[list[str]]
    footer: list[str]
    bbox_2d: list[int]
    cell_coordinates: dict[str, Any]

class KeyValueOutputSchema(TypedDict, total=False):
    """Schema for key-value output format - flat dict with string values or value objects."""
    pass  # Dynamic keys, values are either strings or {"value": str, "bbox_2d": list, "confidence": float}

class StructuredOutputSchema(TypedDict, total=False):
    """Schema for structured output format - comprehensive document structure."""
    document_type: str
    language: str
    page_count: int
    raw_text: str
    fields: dict[str, Any]
    tables: list[dict[str, Any]]
    handwritten_sections: list[Any]

# """ Environment """"""""""""""""""""""""""""""""""""""""""""""""""""""""""""

MODEL_PATH: str  = os.getenv("GLM_MODEL_PATH", "zai-org/GLM-OCR")
MOCK_MODE: bool  = os.getenv("IDEP_MOCK_INFERENCE", "false").lower() == "true"
STRICT_REAL: bool = os.getenv("IDEP_STRICT_REAL",    "true").lower() == "true"
DEFAULT_PRECISION: str = os.getenv("GLM_PRECISION_MODE", "normal").lower()

# """ Error Hierarchy """""""""""""""""""""""""""""""""""""""""""""""""""""""

class FatalError(Exception):
    """Fatal errors that cannot be recovered from (missing model, invalid config)."""
    pass

class RecoverableError(Exception):
    """Recoverable errors that can be handled with fallback (OOM, timeout)."""
    pass

# """ Optional heavy imports """"""""""""""""""""""""""""""""""""""""""""""""""

torch = None
Image = None
AutoProcessor = None
AutoModelForImageTextToText = None
_TRANSFORMERS_OK = False
_PADDLEOCR_OK    = False

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

def _validate_output_schema(content: str, output_format: str) -> bool:
    """Validate that output content matches the expected schema for the format."""
    if output_format in ("text", "markdown", "formula"):
        # Text-based formats don't need JSON validation
        return True
    
    try:
        obj = json.loads(content)
        
        if output_format == "json":
            # JSON format should have document_type, fields, and optionally line_items
            if not isinstance(obj, dict):
                return False
            if "document_type" not in obj or "fields" not in obj:
                return False
            if not isinstance(obj["fields"], dict):
                return False
            if "line_items" in obj and not isinstance(obj["line_items"], list):
                return False
            return True
        
        elif output_format == "table":
            # Table format should be a list of table objects
            if not isinstance(obj, list):
                return False
            for table in obj:
                if not isinstance(table, dict):
                    return False
                if "headers" not in table or "rows" not in table:
                    return False
                if not isinstance(table["headers"], list) or not isinstance(table["rows"], list):
                    return False
            return True
        
        elif output_format == "key_value":
            # Key-value format should be a flat dict
            if not isinstance(obj, dict):
                return False
            return True
        
        elif output_format == "structured":
            # Structured format should have document_type, raw_text, fields, tables
            if not isinstance(obj, dict):
                return False
            required_keys = ["document_type", "raw_text", "fields", "tables"]
            if not all(k in obj for k in required_keys):
                return False
            if not isinstance(obj["fields"], dict) or not isinstance(obj["tables"], list):
                return False
            return True
        
        return True
    except (json.JSONDecodeError, ValueError):
        return False


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
# Input Validation
# ****************************************************************************

def _validate_inputs(image_ref: str, prompt_override: str, options: dict) -> tuple[str, str, dict]:
    """
    Validate and sanitize inputs before processing.
    
    Args:
        image_ref: Image file path or data URI
        prompt_override: Custom prompt text
        options: Processing options dict
    
    Returns:
        Tuple of (validated_image_ref, validated_prompt, validated_options)
    
    Raises:
        ValueError: If inputs are invalid
    """
    # Validate image_ref
    if not image_ref:
        raise ValueError("image_ref is required")
    
    if len(image_ref) > 4096:
        raise ValueError(f"image_ref exceeds maximum length of 4096 characters (got {len(image_ref)})")
    
    # Check format: file path or data: URI
    if not (image_ref.startswith("data:") or image_ref.startswith("/") or 
            os.path.isabs(image_ref) or os.path.exists(image_ref)):
        # Try relative path
        test_path = os.path.join("/tmp/idep", image_ref)
        if not os.path.exists(test_path):
            raise ValueError(
                f"image_ref must be a valid file path or data: URI. "
                f"File not found: {image_ref}"
            )
    
    # Validate prompt_override
    if prompt_override and len(prompt_override) > 2048:
        raise ValueError(
            f"prompt_override exceeds maximum length of 2048 characters (got {len(prompt_override)})"
        )
    
    # Sanitize special characters in prompt (basic sanitization)
    if prompt_override:
        # Remove null bytes and other control characters
        prompt_override = "".join(char for char in prompt_override if ord(char) >= 32 or char in "\n\r\t")
    
    # Validate options
    validated_options = {}
    
    if "include_coordinates" in options:
        if not isinstance(options["include_coordinates"], bool):
            raise ValueError("include_coordinates must be a boolean")
        validated_options["include_coordinates"] = options["include_coordinates"]
    
    if "include_word_confidence" in options:
        if not isinstance(options["include_word_confidence"], bool):
            raise ValueError("include_word_confidence must be a boolean")
        validated_options["include_word_confidence"] = options["include_word_confidence"]
    
    if "include_page_layout" in options:
        if not isinstance(options["include_page_layout"], bool):
            raise ValueError("include_page_layout must be a boolean")
        validated_options["include_page_layout"] = options["include_page_layout"]
    
    if "output_format" in options:
        valid_formats = ["text", "json", "markdown", "table", "key_value", "structured", "formula"]
        output_format = str(options["output_format"]).lower()
        if output_format not in valid_formats:
            raise ValueError(
                f"output_format must be one of {valid_formats}, got '{output_format}'"
            )
        validated_options["output_format"] = output_format
    
    if "max_tokens" in options:
        try:
            max_tokens = int(options["max_tokens"])
            if max_tokens < 64 or max_tokens > 8192:
                raise ValueError("max_tokens must be between 64 and 8192")
            validated_options["max_tokens"] = max_tokens
        except (ValueError, TypeError) as e:
            raise ValueError(f"max_tokens must be an integer between 64 and 8192: {e}")
    
    if "extract_fields" in options:
        if not isinstance(options["extract_fields"], list):
            raise ValueError("extract_fields must be a list")
        validated_options["extract_fields"] = [str(f) for f in options["extract_fields"]]
    
    # Copy over any other options that weren't explicitly validated
    for key, value in options.items():
        if key not in validated_options:
            validated_options[key] = value
    
    return image_ref, prompt_override, validated_options


# ****************************************************************************
# TritonPythonModel
# ****************************************************************************

class TritonPythonModel:
    """Triton Python Backend for GLM-OCR with PP-DocLayout spatial pipeline."""

    # "" Triton lifecycle """"""""""""""""""""""""""""""""""""""""""""""""""""

    def initialize(self, args: dict) -> None:
        """
        Initialize the GLM-OCR model with Triton Python Backend.
        
        Loads the model on GPU if available, falls back to CPU, and finally to MOCK mode
        if model loading fails. Also initializes PP-DocLayout-V3 for layout detection.
        
        Args:
            args: Triton initialization arguments containing model_config
        """
        global MOCK_MODE
        self.model_config: dict = json.loads(args.get("model_config", "{}"))
        self.model_name: str   = MODEL_PATH
        self.precision: str    = DEFAULT_PRECISION
        self.processor         = None
        self.model             = None
        self._device: str      = "cpu"
        self.layout_engine     = None
        self.sdk_parser        = None  # Removed but kept for backward compatibility

        # Validate configuration
        logger.info(
            "Initializing GLM-OCR  mock=%s strict_real=%s precision=%s model=%s",
            MOCK_MODE, STRICT_REAL, self.precision, MODEL_PATH,
        )
        
        # Validate precision mode
        valid_precision_modes = ["normal", "high", "precision"]
        if self.precision not in valid_precision_modes:
            logger.warning(
                "Invalid precision mode '%s', defaulting to 'normal'. Valid modes: %s",
                self.precision, valid_precision_modes
            )
            self.precision = "normal"

        if MOCK_MODE:
            logger.warning("  MOCK inference mode active -- no GPU used")
            return

        # "" Native Transformers Path """""""""""""""""""""""""""""""""""""""
        if not _TRANSFORMERS_OK:
            if STRICT_REAL:
                raise RuntimeError("Transformers unavailable in strict-real mode")
            MOCK_MODE = True
            return

        try:
            # Validate MODEL_PATH exists (for local paths) or is valid HuggingFace ID
            if not MODEL_PATH.startswith("zai-org/") and not os.path.exists(MODEL_PATH):
                raise ValueError(f"MODEL_PATH does not exist: {MODEL_PATH}")
            
            logger.info("Loading %s ", MODEL_PATH)
            
            # Set environment variable to enable trust_remote_code
            os.environ["TRANSFORMERS_TRUST_REMOTE_CODE"] = "1"
            
            # Add model cache directory to sys.path for custom tokenizer imports
            import sys
            try:
                # Try older transformers API first
                from transformers.utils import TRANSFORMERS_CACHE
                cache_dir = os.getenv("TRANSFORMERS_CACHE", TRANSFORMERS_CACHE)
            except ImportError:
                # Fallback for newer transformers versions (5.x+)
                try:
                    from transformers.utils import default_cache_path
                    cache_dir = os.getenv("TRANSFORMERS_CACHE", str(default_cache_path))
                except ImportError:
                    # Final fallback - use HF_HOME or default
                    import pathlib
                    hf_home = os.getenv("HF_HOME", os.path.join(pathlib.Path.home(), ".cache", "huggingface"))
                    cache_dir = os.path.join(hf_home, "hub")
            
            model_cache_path = os.path.join(cache_dir, "models--" + MODEL_PATH.replace("/", "--"))
            if os.path.exists(model_cache_path) and model_cache_path not in sys.path:
                sys.path.insert(0, model_cache_path)
                logger.info("Added model cache to sys.path: %s", model_cache_path)
            
            # Try explicit tokenizer import first
            try:
                self.processor = AutoProcessor.from_pretrained(
                    MODEL_PATH, trust_remote_code=True
                )
                logger.info("... Tokenizer loaded successfully")
            except Exception as tokenizer_exc:
                logger.error(
                    "Tokenizer import failed: %s\nModel path: %s\nCache dir: %s\n"
                    "Ensure trust_remote_code=True and custom tokenizer class is available",
                    tokenizer_exc, MODEL_PATH, cache_dir
                )
                raise
            
            # Use float16 instead of bfloat16 -- RTX 2050 (Turing/Ada) handles
            # fp16 natively, while bf16 may be software-emulated and very slow.
            #
            # On small-VRAM GPUs (RTX 2050, 4 GB) we must be careful:
            #   - device_map="auto" hangs computing the shard map
            #   - .to("cuda") can OOM if framework overhead is too high
            # Strategy: load on CPU first, then try GPU; fall back to CPU
            # inference (slow but won't crash the system).
            self.model = AutoModelForImageTextToText.from_pretrained(
                MODEL_PATH,
                torch_dtype=torch.float16,
                trust_remote_code=True,
                low_cpu_mem_usage=True,
            )
            
            # Try GPU first, fall back to CPU if OOM
            try:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    self.model = self.model.to("cuda")
                    self._device = "cuda"
                    logger.info("... Model loaded on GPU (CUDA)")
                else:
                    logger.info("CUDA not available, using CPU")
                    self._device = "cpu"
                    self.model = self.model.float()  # fp32 for CPU
            except (torch.cuda.OutOfMemoryError, RuntimeError) as gpu_err:
                logger.warning("GPU OOM (%s) -- falling back to CPU (slower)", gpu_err)
                torch.cuda.empty_cache()
                self._device = "cpu"
                self.model = self.model.to("cpu").float()  # fp32 for CPU
            
            self.model.eval()
            logger.info(
                "... GLM-OCR model loaded successfully | device=%s | precision=%s | model=%s",
                self._device, self.precision, MODEL_PATH
            )

            # GPU warm-up pass disabled -- on RTX 2050 (4 GB) the first
            # generate() triggers CUDA JIT compilation which can take 20+ min
            # with device_map="auto" layer offloading.  Better to let the first
            # real request absorb the one-time cost.
            logger.info("GPU warm-up skipped (will JIT on first request)")
        except Exception as exc:
            tb = traceback.format_exc()
            logger.error("Model load failed: %s\n%s", exc, tb)
            if STRICT_REAL:
                raise RuntimeError(f"Model load failed in strict-real mode: {exc}") from exc
            logger.warning("Falling back to MOCK mode due to initialization failure")
            MOCK_MODE = True
            return

        # "" PP-DocLayout for spatial stage """"""""""""""""""""""""""""""""
        if _PADDLEOCR_OK:
            try:
                paddleocr_home = os.getenv("PADDLEOCR_HOME", "/opt/paddleocr")
                if not os.path.exists(paddleocr_home):
                    logger.warning(
                        "PADDLEOCR_HOME directory does not exist: %s -- layout stage disabled",
                        paddleocr_home
                    )
                else:
                    from paddleocr import PPStructure  # type: ignore
                    self.layout_engine = PPStructure(
                        table=True, ocr=False, show_log=False,
                        layout_model_dir=paddleocr_home,
                    )
                    logger.info("... PP-DocLayout-V3 ready")
            except Exception as exc:
                logger.warning("PP-DocLayout init failed (%s) -- layout stage disabled", exc)

    def finalize(self) -> None:
        """
        Clean up resources when the model is unloaded.
        
        Releases GPU memory and deletes model/processor objects.
        """
        logger.info("Finalizing GLM-OCR backend")
        if self.model is not None and torch is not None:
            del self.model
            del self.processor
            torch.cuda.empty_cache()

    # "" Request dispatch """"""""""""""""""""""""""""""""""""""""""""""""""""

    def execute(self, requests):
        """
        Execute inference requests.
        
        Processes each request through _handle method and catches any exceptions,
        returning them as Triton errors.
        
        Args:
            requests: List of Triton inference requests
        
        Returns:
            List of Triton inference responses
        """
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

        # Validate inputs
        try:
            image_ref, prompt_override, options = _validate_inputs(image_ref, prompt_override, options)
        except ValueError as e:
            logger.error("Input validation failed: %s", e)
            if pb_utils:
                return pb_utils.InferenceResponse(error=pb_utils.TritonError(f"Invalid input: {e}"))
            raise

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

        if MOCK_MODE or self.model is None:
            result = _MockEngine.run(
                image_ref=image_ref,
                prompt_override=prompt_override,
                output_format=output_format,
                include_coords=include_coords,
                include_word_conf=include_word_conf,
                include_page_layout=include_page_layout,
                precision=precision,
            )
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

        # Validate output schema for structured formats
        if output_format in ("json", "table", "key_value", "structured"):
            for page in result.get("pages", []):
                for element in page.get("elements", []):
                    content = element.get("content", "")
                    if not _validate_output_schema(content, output_format):
                        logger.warning(
                            "Output schema validation failed for format '%s'. Content may not match expected structure.",
                            output_format
                        )

        result_json = json.dumps(result, ensure_ascii=False, indent=2)
        conf = float(result.get("confidence", 0.90))

        if pb_utils:
            text_np = np.array([result_json], dtype=np.object_)
            out_text = pb_utils.Tensor("generated_text", text_np)
            conf_np = np.array([conf], dtype=np.float32)
            out_conf = pb_utils.Tensor("confidence", conf_np)
            return pb_utils.InferenceResponse(output_tensors=[out_text, out_conf])
        return result

    # "" SDK inference path """"""""""""""""""""""""""""""""""""""""""""""""""

    # "" Native two-stage inference """"""""""""""""""""""""""""""""""""""""""

    def _create_generation_kwargs(self, precision: str, max_new_tokens: int) -> dict:
        """
        Create generation parameters based on precision mode.
        
        Args:
            precision: Precision mode ("normal", "high", or "precision")
            max_new_tokens: Maximum number of tokens to generate
        
        Returns:
            Dictionary of generation parameters
        """
        gen_kwargs = {
            "max_new_tokens": max_new_tokens,
            "do_sample": False,
            "repetition_penalty": 1.05 if precision not in ("high", "precision") else 1.15,
        }
        if precision in ("high", "precision"):
            gen_kwargs["length_penalty"] = 1.0
        return gen_kwargs

    def _native_inference(
        self, 
        image_ref: str, 
        prompt_override: str, 
        output_format: str,
        include_coords: bool, 
        include_word_conf: bool, 
        max_tokens: int, 
        precision: str,
    ) -> dict:
        """
        Two-stage pipeline: PP-DocLayout-V3 → GLM-OCR.
        
        Args:
            image_ref: Image file path or data URI
            prompt_override: Custom prompt (overrides default task prompts)
            output_format: Output format type
            include_coords: Whether to include bounding box coordinates
            include_word_conf: Whether to include word-level confidence
            max_tokens: Maximum tokens to generate
            precision: Precision mode
        
        Returns:
            Result dict with pages, markdown, confidence, and usage
        
        Falls back to single full-page pass when layout engine is absent.
        """
        img = _load_image(image_ref)
        page_w, page_h = img.size
        elements: list = []
        total_pt = total_ct = 0

        if self.layout_engine is not None and include_coords and not prompt_override:
            # Use layout detection with task-specific prompts only when no custom prompt provided
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
            # Use custom prompt if provided, otherwise use format-based prompt
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

    def _detect_layout(self, img) -> list[dict]:
        """
        Run PP-DocLayout-V3 to detect document regions.
        
        Args:
            img: PIL Image object
        
        Returns:
            List of region dicts sorted in reading order, each with bbox, label, and confidence
        """
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

    def _run_glm_ocr(self, img, prompt: str, max_new_tokens: int, precision: str, output_format: str) -> tuple[str, int, int]:
        """
        Single GLM-OCR inference call.
        
        Args:
            img: PIL Image object
            prompt: Prompt text for the model
            max_new_tokens: Maximum number of tokens to generate
            precision: Precision mode ("normal", "high", or "precision")
                      - Affects repetition_penalty (1.05 for normal, 1.15 for high/precision)
                      - High/precision modes also set length_penalty=1.0
            output_format: Output format (used for logging)
        
        Returns:
            Tuple of (content, prompt_tokens, completion_tokens)
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

        # Generation parameters based on precision mode (see _create_generation_kwargs)
        # - do_sample=False for deterministic output
        # - repetition_penalty: 1.05 (normal) or 1.15 (high/precision)
        # - length_penalty: 1.0 (high/precision only)
        gen_kwargs = self._create_generation_kwargs(precision, max_new_tokens)

        with torch.no_grad():
            outputs = self.model.generate(**inputs, **gen_kwargs)

        prompt_len = inputs["input_ids"].shape[1]
        new_ids    = outputs[:, prompt_len:]
        text = self.processor.decode(new_ids[0], skip_special_tokens=False)
        for tok in ("<|endoftext|>", "<|user|>", "<|assistant|>", "</s>"):
            text = text.replace(tok, "").strip()

        return text, prompt_len, int(new_ids.shape[1])

    def _enrich_word_confidence(self, elements: list[dict], img) -> list[dict]:
        """
        Precision-mode: word-level recognition pass for each detected region.
        
        Args:
            elements: List of element dicts with bbox_2d
            img: PIL Image object
        
        Returns:
            Updated elements list with word-level confidence data
        """
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
        # Return flat structure as per schema
        payload: JsonOutputSchema = {
            "document_type": "invoice",
            "fields": {
                "invoice_number": "INV-2026-0042",
                "date": "2026-02-25",
                "vendor": "Acme Corp",
                "bill_to": "Customer Inc.",
                "subtotal": "$1,234.56",
                "tax": "$123.46",
                "total_amount": "$1,358.02",
            },
            "line_items": [
                {"description": "Widget A", "quantity": 10, "unit_price": "$100.00", "total": "$1,000.00"},
                {"description": "Widget B", "quantity": 5, "unit_price": "$46.91", "total": "$234.56"},
            ],
        }
        # Add coordinates at top level if requested (not inside fields)
        if coords:
            payload["_coordinates"] = {
                "invoice_number": [280, 100, 460, 125],
                "date": [280, 130, 430, 155],
                "vendor": [280, 160, 420, 185],
                "bill_to": [280, 210, 460, 235],
                "subtotal": [400, 440, 520, 460],
                "tax": [400, 465, 500, 485],
                "total_amount": [400, 495, 530, 520],
            }
            payload["line_items"][0]["bbox_2d"] = [100, 330, 540, 355]
            payload["line_items"][1]["bbox_2d"] = [100, 358, 540, 383]
        
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
        # Return structured table object as per schema (list of tables)
        table: TableOutputSchema = {
            "table_id": 1,
            "title": "Invoice Line Items",
            "headers": ["Description", "Qty", "Unit Price", "Total"],
            "rows": [
                ["Widget A", "10", "$100.00", "$1,000.00"],
                ["Widget B", "5", "$46.91", "$234.56"]
            ],
            "footer": ["", "", "Subtotal", "$1,234.56"],
        }
        if coords:
            table["bbox_2d"] = [80, 300, 540, 420]
            table["cell_coordinates"] = {
                "header_row": [
                    [80, 300, 215, 325], [215, 300, 265, 325],
                    [265, 300, 405, 325], [405, 300, 540, 325]
                ],
                "data_rows": [
                    [[80, 330, 215, 355], [215, 330, 265, 355],
                     [265, 330, 405, 355], [405, 330, 540, 355]],
                    [[80, 358, 215, 383], [215, 358, 265, 383],
                     [265, 358, 405, 383], [405, 358, 540, 383]]
                ],
            }
        
        payload = [table]  # Return as list of tables
        return [_make_element(0, "table", json.dumps(payload, indent=2),
                              [80, 300, 540, 420] if coords else None, 0.97)]

    @classmethod
    def _key_value(cls, coords):
        # Return flat dict with string values (coordinates separate if needed)
        kv: KeyValueOutputSchema = {
            "invoice_number": "INV-2026-0042",
            "date": "2026-02-25",
            "vendor": "Acme Corp",
            "bill_to": "Customer Inc.",
            "subtotal": "$1,234.56",
            "tax": "$123.46",
            "total_amount": "$1,358.02",
            "payment_terms": "Net 30",
        }
        # Add coordinates as separate field if requested
        if coords:
            kv["_coordinates"] = {
                "invoice_number": [280, 100, 460, 125],
                "date": [280, 130, 430, 155],
                "vendor": [280, 160, 420, 185],
                "bill_to": [280, 210, 460, 235],
                "subtotal": [400, 440, 520, 460],
                "tax": [400, 465, 500, 485],
                "total_amount": [400, 495, 530, 520],
                "payment_terms": [280, 525, 380, 545],
            }
            kv["_confidence"] = {
                "invoice_number": 0.97,
                "date": 0.96,
                "vendor": 0.95,
                "bill_to": 0.94,
                "subtotal": 0.97,
                "tax": 0.96,
                "total_amount": 0.98,
                "payment_terms": 0.92,
            }
        
        return [_make_element(0, "key_value", json.dumps(kv, indent=2),
                              [80, 80, 540, 545] if coords else None, 0.96)]

    @classmethod
    def _structured(cls, coords):
        # Return complete structured output as per schema
        s: StructuredOutputSchema = {
            "document_type": "invoice",
            "language": "en",
            "page_count": 1,
            "raw_text": "INVOICE\nInvoice #: INV-2026-0042\nDate: 2026-02-25\nTotal Due: $1,358.02",
            "fields": {
                "invoice_number": "INV-2026-0042",
                "date": "2026-02-25",
                "total_amount": "$1,358.02",
            },
            "tables": [{
                "headers": ["Description", "Qty", "Unit Price", "Total"],
                "rows": [
                    ["Widget A", "10", "$100.00", "$1,000.00"],
                    ["Widget B", "5", "$46.91", "$234.56"]
                ],
            }],
            "handwritten_sections": [],
        }
        
        # Add coordinates at top level if requested (not inside fields)
        if coords:
            s["_coordinates"] = {
                "invoice_number": [280, 100, 460, 125],
                "date": [280, 130, 430, 155],
                "total_amount": [400, 495, 530, 520],
            }
            s["tables"][0]["bbox_2d"] = [80, 300, 540, 420]
            s["tables"][0]["cell_coordinates"] = {
                "header_row": [
                    [80, 300, 215, 325], [215, 300, 265, 325],
                    [265, 300, 405, 325], [405, 300, 540, 325]
                ],
                "data_rows": [
                    [[80, 330, 215, 355], [215, 330, 265, 355],
                     [265, 330, 405, 355], [405, 330, 540, 355]],
                    [[80, 358, 215, 383], [215, 358, 265, 383],
                     [265, 358, 405, 383], [405, 358, 540, 383]]
                ],
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

