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
    glm_precision_mode: str = os.getenv("GLM_PRECISION_MODE", "normal")
    cuda_visible_devices: Optional[str] = os.getenv("CUDA_VISIBLE_DEVICES")
    
    # Processing settings
    max_image_size_mb: int = 10
    max_batch_size: int = 10
    request_timeout_seconds: int = 30
    max_tokens_default: int = 2048
    max_tokens_limit: int = 8192
    
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
