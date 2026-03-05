"""Configuration management for PaddleOCR Layout Detection Service."""

import os
import logging
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=(),
    )
    
    # Service configuration
    service_name: str = Field(default="paddleocr-layout-detection")
    service_version: str = Field(default="1.0.0")
    
    # Environment variable configuration
    service_host: str = Field(default="0.0.0.0", alias="SERVICE_HOST")
    service_port: int = Field(default=8001, alias="SERVICE_PORT")
    
    # PaddleOCR configuration
    use_gpu: str = Field(default="false", alias="PADDLEOCR_USE_GPU")
    model_dir: str = Field(default="./models", alias="PADDLEOCR_MODEL_DIR")
    min_confidence_default: float = Field(default=0.5, alias="PADDLEOCR_MIN_CONFIDENCE_DEFAULT")
    max_image_size_mb: int = Field(default=10, alias="PADDLEOCR_MAX_IMAGE_SIZE_MB")
    request_timeout_seconds: int = Field(default=30, alias="PADDLEOCR_REQUEST_TIMEOUT_SECONDS")
    
    # Logging configuration
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="standard")  # Changed default to standard for compatibility
    
    @field_validator("use_gpu")
    @classmethod
    def validate_use_gpu(cls, v: str) -> str:
        """Validate that PADDLEOCR_USE_GPU is a valid boolean string."""
        valid_true = ("true", "1", "yes")
        valid_false = ("false", "0", "no")
        
        lower_v = v.lower()
        if lower_v in valid_true or lower_v in valid_false:
            return v
        raise ValueError(f"PADDLEOCR_USE_GPU must be a valid boolean string (true/false/1/0/yes/no), got: {v}")
    
    @property
    def use_gpu_bool(self) -> bool:
        """Return use_gpu as a boolean."""
        return self.use_gpu.lower() in ("true", "1", "yes")
    
    @field_validator("min_confidence_default")
    @classmethod
    def validate_min_confidence(cls, v: float) -> float:
        """Validate confidence threshold is between 0 and 1."""
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"PADDLEOCR_MIN_CONFIDENCE_DEFAULT must be between 0.0 and 1.0, got {v}")
        return v
    
    @field_validator("max_image_size_mb")
    @classmethod
    def validate_max_image_size_mb(cls, v: int) -> int:
        """Validate that max image size is a positive integer."""
        if v <= 0:
            raise ValueError(f"PADDLEOCR_MAX_IMAGE_SIZE_MB must be a positive integer, got {v}")
        return v
    
    @field_validator("request_timeout_seconds")
    @classmethod
    def validate_request_timeout_seconds(cls, v: int) -> int:
        """Validate that request timeout is a positive integer."""
        if v <= 0:
            raise ValueError(f"PADDLEOCR_REQUEST_TIMEOUT_SECONDS must be a positive integer, got {v}")
        return v
    
    @field_validator("service_port")
    @classmethod
    def validate_service_port(cls, v: int) -> int:
        """Validate that service port is a positive integer."""
        if v <= 0 or v > 65535:
            raise ValueError(f"SERVICE_PORT must be a valid port number (1-65535), got {v}")
        return v
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate that LOG_LEVEL is one of: DEBUG, INFO, WARNING, ERROR, CRITICAL."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        upper_v = v.upper()
        if upper_v not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}, got: {v}")
        return upper_v
    
    @property
    def logging_config(self) -> dict:
        """Return logging configuration dictionary."""
        # Try to use JSON formatter if available, fall back to standard
        try:
            from pythonjsonlogger import jsonlogger
            formatter_class = "pythonjsonlogger.jsonlogger.JsonFormatter"
            formatter_format = "%(asctime)s %(levelname)s %(name)s %(message)s"
        except ImportError:
            formatter_class = None
            formatter_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        
        formatters = {
            "standard": {
                "format": formatter_format,
            },
        }
        
        if formatter_class:
            formatters["json"] = {
                "()": formatter_class,
                "format": formatter_format,
            }
        
        # Use json formatter if available, otherwise use standard
        formatter_name = "json" if formatter_class else "standard"
        
        return {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": formatters,
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": formatter_name,
                    "level": self.log_level,
                },
            },
            "root": {
                "level": self.log_level,
                "handlers": ["console"],
            },
        }


def get_settings() -> Settings:
    """Get application settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()


def setup_logging() -> None:
    """Configure logging based on settings."""
    import logging.config
    
    logging.config.dictConfig(settings.logging_config)
    logging.info(f"Logging configured with level: {settings.log_level}")


def validate_config() -> bool:
    """Validate all configuration values."""
    try:
        # Validate GPU settings
        if settings.use_gpu_bool:
            try:
                import paddle
                
                if not paddle.is_compiled_with_cuda():
                    raise ValueError("GPU enabled but PaddlePaddle not compiled with CUDA")
                logging.info(f"GPU mode enabled, using device: {paddle.get_device()}")
            except ImportError:
                logging.warning("PaddlePaddle not installed, skipping GPU validation")
        
        # Validate model directory
        if not os.path.exists(settings.model_dir):
            try:
                os.makedirs(settings.model_dir, exist_ok=True)
                logging.info(f"Created model directory: {settings.model_dir}")
            except OSError as e:
                logging.warning(f"Could not create model directory: {e}")
        
        return True
    except Exception as e:
        logging.error(f"Configuration validation failed: {e}")
        raise
