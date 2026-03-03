"""GLM-OCR inference wrapper."""

import io
import base64
import logging
import time
from typing import Dict, Any, Optional, Tuple
from PIL import Image

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
            import torch
            from transformers import AutoProcessor, AutoModelForImageTextToText
            
            logger.info(f"Loading GLM-OCR model from {self.model_path}")
            
            # Load processor
            self.processor = AutoProcessor.from_pretrained(
                self.model_path,
                trust_remote_code=True
            )
            
            # Load model
            self.model = AutoModelForImageTextToText.from_pretrained(
                self.model_path,
                torch_dtype=torch.float16,
                trust_remote_code=True,
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
            
            # Prepare inputs
            inputs = self.processor(
                text=prompt,
                images=image,
                return_tensors="pt"
            )
            
            # Move inputs to device
            if self.device == "cuda":
                inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            # Generate
            import torch
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=max_tokens,
                    do_sample=False,
                    num_beams=1
                )
            
            # Decode output
            generated_text = self.processor.batch_decode(
                outputs,
                skip_special_tokens=True
            )[0]
            
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
