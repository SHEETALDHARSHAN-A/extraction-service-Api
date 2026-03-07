"""GLM-OCR inference wrapper."""

import io
import base64
import logging
import time
import os
import tempfile
import re
from typing import Dict, Any, Optional, Tuple
from PIL import Image
from .config import settings

logger = logging.getLogger(__name__)


class GLMInferenceEngine:
    """Wrapper for GLM-OCR model inference."""
    
    def __init__(self, model_path: str, precision_mode: str = "normal"):
        """
        Initialize the GLM-OCR inference engine.
        
        Args:
            model_path: Path to model or HuggingFace model ID
            precision_mode: Inference precision mode (normal, high, precision)
        """
        self.model_path = model_path
        self.precision_mode = precision_mode
        self.model = None
        self.processor = None
        self.device = "cpu"
        self._initialized = False
        
        # Try to load model
        self._load_model()
    
    def _load_model(self) -> None:
        """Load the GLM-OCR model."""
        try:
            # Helps reduce CUDA allocator fragmentation on small VRAM cards.
            os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
            import torch
            from transformers import AutoProcessor, AutoModelForImageTextToText
            
            logger.info(f"Loading GLM-OCR model from {self.model_path}")
            requested_device = (settings.glm_device_preference or "auto").strip().lower()
            if requested_device not in {"auto", "cpu", "cuda"}:
                logger.warning(
                    "Invalid GLM_DEVICE_PREFERENCE='%s'; defaulting to 'auto'",
                    requested_device,
                )
                requested_device = "auto"
            
            # Load processor
            self.processor = AutoProcessor.from_pretrained(
                self.model_path
            )
            
            # Load model
            model_kwargs = {
                "low_cpu_mem_usage": True,
            }
            try:
                # Newer transformers versions prefer `dtype`.
                self.model = AutoModelForImageTextToText.from_pretrained(
                    self.model_path,
                    dtype=torch.float16,
                    **model_kwargs,
                )
            except TypeError:
                # Backward compatibility for older transformers versions.
                self.model = AutoModelForImageTextToText.from_pretrained(
                    self.model_path,
                    torch_dtype=torch.float16,
                    **model_kwargs,
                )
            
            # Try to move to GPU
            if requested_device == "cpu":
                logger.info("GLM_DEVICE_PREFERENCE=cpu set; forcing CPU inference")
                self.device = "cpu"
                self.model = self.model.to("cpu").float()
            elif torch.cuda.is_available():
                try:
                    torch.cuda.empty_cache()
                    self.model = self.model.to("cuda")
                    self.device = "cuda"
                    logger.info("Model loaded on GPU (CUDA)")
                except (torch.cuda.OutOfMemoryError, RuntimeError) as e:
                    if self._is_cuda_recoverable_error(e):
                        logger.warning(f"CUDA unavailable/busy/OOM ({e}), falling back to CPU")
                    else:
                        raise
                    torch.cuda.empty_cache()
                    self.device = "cpu"
                    self.model = self.model.to("cpu").float()
            else:
                if requested_device == "cuda":
                    logger.warning("GLM_DEVICE_PREFERENCE=cuda set, but CUDA is not available. Using CPU")
                else:
                    logger.info("CUDA not available, using CPU")
                self.device = "cpu"
                self.model = self.model.to("cpu").float()
            
            self.model.eval()
            self._initialized = True
            logger.info(f"GLM-OCR model loaded successfully on {self.device}")
            
        except Exception as e:
            logger.error(f"Failed to load GLM-OCR model: {e}")
            self._initialized = False
            raise

    @staticmethod
    def _is_cuda_recoverable_error(error: Exception) -> bool:
        """Return True when CUDA failure should trigger CPU fallback instead of hard-fail."""
        message = str(error).lower()
        markers = (
            "out of memory",
            "cuda-capable device",
            "device(s) is/are busy or unavailable",
            "cuda error",
            "cublas",
            "cudnn",
        )
        return any(marker in message for marker in markers)
    
    def is_ready(self) -> bool:
        """Check if the model is ready for inference."""
        return self._initialized and self.model is not None
    
    def extract_content(
        self,
        image_base64: str,
        prompt: str,
        max_tokens: int = 2048,
        output_format: str = "text"
    ) -> Tuple[str, float, int, int]:
        """
        Extract content from an image region.
        
        Args:
            image_base64: Base64 encoded image
            prompt: Prompt for extraction
            max_tokens: Maximum tokens to generate
            output_format: Output format (text, json, markdown, etc.)
        
        Returns:
            Tuple of (content, confidence, prompt_tokens, completion_tokens)
        """
        if not self.is_ready():
            raise RuntimeError("Model not initialized")
        
        try:
            # Decode image
            image = self._decode_base64_image(image_base64)

            # Chunk large pages before global downscale so each segment retains more detail.
            if self._should_chunk_image(image):
                return self._extract_content_chunked(image, prompt, max_tokens)

            image = self._resize_for_low_vram(image)

            return self._extract_single_image(image, prompt, max_tokens)
            
        except Exception as e:
            logger.error(f"Inference failed: {e}")
            raise

    def _extract_single_image(self, image: Image.Image, prompt: str, max_tokens: int) -> Tuple[str, float, int, int]:
        """Run inference for a single prepared image with low-VRAM retry logic."""
        import torch

        run_configs = [{
            "max_tokens": max_tokens,
            "max_edge": settings.low_vram_max_image_edge,
            "label": "primary",
        }]
        if self.device == "cuda" and settings.low_vram_mode:
            run_configs.append({
                "max_tokens": min(max_tokens, int(settings.low_vram_retry_max_tokens)),
                "max_edge": int(settings.low_vram_retry_image_edge),
                "label": "low-vram-retry",
            })

        last_error = None
        for cfg in run_configs:
            run_image = self._resize_image_to_edge(image, int(cfg["max_edge"]))
            inputs = self._build_model_inputs(run_image, prompt)

            if self.device == "cuda":
                inputs = {k: v.to(self.device) for k, v in inputs.items()}

            try:
                logger.info(
                    "Generation attempt=%s max_tokens=%s max_edge=%s max_time=%ss",
                    cfg["label"], cfg["max_tokens"], cfg["max_edge"], settings.request_timeout_seconds,
                )
                with torch.no_grad():
                    outputs = self.model.generate(
                        **inputs,
                        max_new_tokens=int(cfg["max_tokens"]),
                        max_time=float(settings.request_timeout_seconds),
                        use_cache=False,
                        do_sample=False,
                        num_beams=1,
                    )
                generated_text = self.processor.decode(
                    outputs[0][inputs["input_ids"].shape[1]:],
                    skip_special_tokens=False,
                )
                content = generated_text.replace(prompt, "").strip() if prompt in generated_text else generated_text
                prompt_tokens = len(inputs.get("input_ids", [[]])[0])
                completion_tokens = len(outputs[0]) - prompt_tokens
                return content, 0.90, prompt_tokens, completion_tokens
            except (torch.cuda.OutOfMemoryError, RuntimeError) as e:
                error_str = str(e).lower()
                if self.device == "cuda" and ("out of memory" in error_str or "cuda" in error_str):
                    last_error = e
                    logger.warning(
                        "CUDA OOM during %s attempt (max_tokens=%s, max_edge=%s): %s",
                        cfg["label"], cfg["max_tokens"], cfg["max_edge"], e,
                    )
                    torch.cuda.empty_cache()
                    continue
                raise

        raise torch.cuda.OutOfMemoryError(
            f"CUDA out of memory during inference after retries: {last_error}"
        )

    def _should_chunk_image(self, image: Image.Image) -> bool:
        """Determine if image should be split into segments before OCR."""
        if not settings.chunk_large_pages:
            return False
        if self.device != "cuda":
            return False
        width, height = image.size
        return max(width, height) >= int(settings.chunk_trigger_max_edge)

    def _extract_content_chunked(self, image: Image.Image, prompt: str, max_tokens: int) -> Tuple[str, float, int, int]:
        """Split large page into overlapping vertical segments, OCR each, then merge text."""
        segment_count = max(2, int(settings.chunk_segment_count))
        overlap = max(0, int(settings.chunk_overlap_px))
        segment_token_cap = max(256, int(settings.chunk_segment_max_tokens))
        per_segment_tokens = min(int(max_tokens), segment_token_cap)

        segments = self._split_into_vertical_segments(image, segment_count, overlap)
        logger.info(
            "Chunked OCR active: segments=%s overlap_px=%s per_segment_tokens=%s",
            len(segments), overlap, per_segment_tokens,
        )

        contents = []
        prompt_total = 0
        completion_total = 0
        conf_total = 0.0

        for idx, seg in enumerate(segments):
            logger.info("Processing chunk %s/%s", idx + 1, len(segments))
            content, confidence, p_tokens, c_tokens = self._extract_single_image(seg, prompt, per_segment_tokens)
            if content.strip():
                contents.append(content.strip())
            prompt_total += p_tokens
            completion_total += c_tokens
            conf_total += confidence

        merged = self._merge_chunk_contents(contents)
        avg_conf = conf_total / float(len(segments)) if segments else 0.0
        return merged, avg_conf, prompt_total, completion_total

    def _split_into_vertical_segments(self, image: Image.Image, segment_count: int, overlap_px: int) -> list[Image.Image]:
        """Split image into overlapping top-to-bottom segments."""
        width, height = image.size
        band_h = max(1, height // segment_count)
        segments: list[Image.Image] = []

        for i in range(segment_count):
            top = max(0, i * band_h - overlap_px)
            bottom = min(height, (i + 1) * band_h + overlap_px)
            if i == segment_count - 1:
                bottom = height
            if bottom <= top:
                continue
            segments.append(image.crop((0, top, width, bottom)))

        if not segments:
            segments.append(image)
        return segments

    def _merge_chunk_contents(self, chunk_texts: list[str]) -> str:
        """Merge chunk OCR outputs and de-duplicate overlap lines."""
        merged_lines: list[str] = []
        seen_recent: set[str] = set()
        recent_window: list[str] = []

        for text in chunk_texts:
            for line in text.splitlines():
                raw = line.strip()
                if not raw:
                    continue

                # Normalize minor whitespace noise for overlap de-duplication.
                norm = re.sub(r"\s+", " ", raw).lower()
                if norm in seen_recent:
                    continue

                merged_lines.append(raw)
                recent_window.append(norm)
                seen_recent.add(norm)

                # Keep only a bounded recent set so repeated headers far apart can remain.
                if len(recent_window) > 120:
                    dropped = recent_window.pop(0)
                    if dropped not in recent_window:
                        seen_recent.discard(dropped)

        return "\n".join(merged_lines)

    def _build_model_inputs(self, image: Image.Image, prompt: str):
        """Prepare chat-template inputs for GLM-OCR from image and prompt."""
        temp_image_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_image_file:
                image.save(temp_image_file.name, format="PNG")
                temp_image_path = temp_image_file.name

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "url": temp_image_path},
                        {"type": "text", "text": prompt},
                    ],
                }
            ]

            inputs = self.processor.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_dict=True,
                return_tensors="pt",
            )
            inputs.pop("token_type_ids", None)
            return inputs
        finally:
            if temp_image_path and os.path.exists(temp_image_path):
                try:
                    os.remove(temp_image_path)
                except OSError:
                    pass

    def _resize_image_to_edge(self, image: Image.Image, max_edge: int) -> Image.Image:
        """Resize image so its largest edge is at most max_edge."""
        width, height = image.size
        current_max = max(width, height)
        if current_max <= max_edge:
            return image

        scale = max_edge / float(current_max)
        new_width = max(1, int(width * scale))
        new_height = max(1, int(height * scale))
        return image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    def _decode_base64_image(self, image_base64: str) -> Image.Image:
        """
        Decode base64 image string to PIL Image, or load directly from path.
        
        Args:
            image_base64: Base64 encoded image or local file path.
        
        Returns:
            PIL Image object
        """
        try:
            # Check if it's a file path
            import os
            if len(image_base64) < 2000 and os.path.exists(image_base64):
                import logging
                logging.getLogger(__name__).info(f"Loading image from path directly: {image_base64}")
                return Image.open(image_base64).convert("RGB")

            # Remove data URI prefix if present
            if image_base64.startswith("data:"):
                image_base64 = image_base64.split(",", 1)[1]
            
            # Decode base64
            image_bytes = base64.b64decode(image_base64)
            
            # Open image
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            
            return image
            
        except Exception as e:
            logger.error(f"Failed to decode image: {e}")
            raise ValueError(f"Invalid base64 image processing: {e}")

    def _resize_for_low_vram(self, image: Image.Image) -> Image.Image:
        """Downscale very large images to reduce GPU memory spikes during generation."""
        if not settings.low_vram_mode:
            return image

        max_edge = max(256, int(settings.low_vram_max_image_edge))
        width, height = image.size
        current_max = max(width, height)

        if current_max <= max_edge:
            return image

        scale = max_edge / float(current_max)
        new_width = max(1, int(width * scale))
        new_height = max(1, int(height * scale))

        logger.info(
            f"Low-VRAM resize applied: {width}x{height} -> {new_width}x{new_height}"
        )
        return image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    def cleanup(self) -> None:
        """Clean up resources."""
        if self.model is not None:
            try:
                import torch
                del self.model
                del self.processor
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                logger.info("Model resources cleaned up")
            except Exception as e:
                logger.warning(f"Error during cleanup: {e}")
