"""GLM-OCR inference wrapper."""

import io
import base64
import logging
import time
import os
import tempfile
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
            
            # Load processor
            self.processor = AutoProcessor.from_pretrained(
                self.model_path
            )
            
            # Load model
            self.model = AutoModelForImageTextToText.from_pretrained(
                self.model_path,
                torch_dtype=torch.float16,
                low_cpu_mem_usage=True
            )
            
            # Try to move to GPU
            if torch.cuda.is_available():
                try:
                    torch.cuda.empty_cache()
                    self.model = self.model.to("cuda")
                    self.device = "cuda"
                    logger.info("Model loaded on GPU (CUDA)")
                except (torch.cuda.OutOfMemoryError, RuntimeError) as e:
                    logger.warning(f"GPU OOM ({e}), falling back to CPU")
                    torch.cuda.empty_cache()
                    self.device = "cpu"
                    self.model = self.model.to("cpu").float()
            else:
                logger.info("CUDA not available, using CPU")
                self.device = "cpu"
                self.model = self.model.float()
            
            self.model.eval()
            self._initialized = True
            logger.info(f"GLM-OCR model loaded successfully on {self.device}")
            
        except Exception as e:
            logger.error(f"Failed to load GLM-OCR model: {e}")
            self._initialized = False
            raise
    
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
            image = self._resize_for_low_vram(image)

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

                # Move inputs to device
                if self.device == "cuda":
                    inputs = {k: v.to(self.device) for k, v in inputs.items()}

                try:
                    with torch.no_grad():
                        outputs = self.model.generate(
                            **inputs,
                            max_new_tokens=int(cfg["max_tokens"]),
                            use_cache=False,
                            do_sample=False,
                            num_beams=1,
                        )
                    break
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
            else:
                raise torch.cuda.OutOfMemoryError(
                    f"CUDA out of memory during inference after retries: {last_error}"
                )
            
            # Decode output
            generated_text = self.processor.decode(
                outputs[0][inputs["input_ids"].shape[1]:],
                skip_special_tokens=False,
            )
            
            # Extract content (remove prompt if present)
            content = generated_text
            if prompt in content:
                content = content.replace(prompt, "").strip()
            
            # Estimate token counts (approximate)
            prompt_tokens = len(inputs.get("input_ids", [[]])[0])
            completion_tokens = len(outputs[0]) - prompt_tokens
            
            # Confidence is approximate (GLM-OCR doesn't provide confidence scores)
            confidence = 0.90
            
            return content, confidence, prompt_tokens, completion_tokens
            
        except Exception as e:
            logger.error(f"Inference failed: {e}")
            raise

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
        Decode base64 image string to PIL Image.
        
        Args:
            image_base64: Base64 encoded image (with or without data URI prefix)
        
        Returns:
            PIL Image object
        """
        try:
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
            raise ValueError(f"Invalid base64 image: {e}")

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
