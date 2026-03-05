"""Configuration management for GLM-OCR service."""

import os
import logging
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Service configuration settings."""
    
    # Service settings
    service_name: str = "glm-ocr-service"
    service_version: str = "1.0.0"
    host: str = "0.0.0.0"
    port: int = 8002
    
    # Model settings
    glm_model_path: str = os.getenv("GLM_MODEL_PATH", "zai-org/GLM-OCR")
    glm_precision_mode: str = os.getenv("GLM_PRECISION_MODE", "high")
    cuda_visible_devices: Optional[str] = os.getenv("CUDA_VISIBLE_DEVICES")
    
    # Processing settings
    max_image_size_mb: int = 10
    max_batch_size: int = 10
    request_timeout_seconds: int = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "90"))
    max_tokens_default: int = 2048
    max_tokens_limit: int = 8192
    # Low-VRAM guardrails for consumer GPUs (e.g., 4GB cards)
    low_vram_mode: bool = os.getenv("LOW_VRAM_MODE", "true").lower() == "true"
    low_vram_max_tokens: int = int(os.getenv("LOW_VRAM_MAX_TOKENS", "2048"))
    low_vram_max_image_edge: int = int(os.getenv("LOW_VRAM_MAX_IMAGE_EDGE", "896"))
    low_vram_retry_max_tokens: int = int(os.getenv("LOW_VRAM_RETRY_MAX_TOKENS", "512"))
    low_vram_retry_image_edge: int = int(os.getenv("LOW_VRAM_RETRY_IMAGE_EDGE", "640"))
    # Chunk very large pages into overlapping vertical segments to reduce VRAM spikes
    # while preserving extraction quality.
    chunk_large_pages: bool = os.getenv("CHUNK_LARGE_PAGES", "true").lower() == "true"
    chunk_trigger_max_edge: int = int(os.getenv("CHUNK_TRIGGER_MAX_EDGE", "1400"))
    chunk_segment_count: int = int(os.getenv("CHUNK_SEGMENT_COUNT", "3"))
    chunk_overlap_px: int = int(os.getenv("CHUNK_OVERLAP_PX", "120"))
    chunk_segment_max_tokens: int = int(os.getenv("CHUNK_SEGMENT_MAX_TOKENS", "1024"))
    
    # Logging settings
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Triton backend settings (if using Triton)
    use_triton_backend: bool = os.getenv("USE_TRITON_BACKEND", "false").lower() == "true"
    triton_model_dir: Optional[str] = os.getenv("TRITON_MODEL_DIR")
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra environment variables


def setup_logging(log_level: str = "INFO") -> None:
    """Configure structured logging."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "service": "glm-ocr-service", "message": "%(message)s"}',
        datefmt="%Y-%m-%dT%H:%M:%S"
    )


settings = Settings()
setup_logging(settings.log_level)
