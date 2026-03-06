"""Configuration management for GLM-OCR service."""

import os
import logging
from pathlib import Path
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
    # Isolated GPU executor: run inference in a dedicated child process that can be
    # force-killed on timeout (true cancellation semantics).
    use_isolated_gpu_executor: bool = os.getenv("USE_ISOLATED_GPU_EXECUTOR", "false").lower() == "true"
    
    # Logging settings
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Triton backend settings (if using Triton)
    use_triton_backend: bool = os.getenv("USE_TRITON_BACKEND", "false").lower() == "true"
    triton_model_dir: Optional[str] = os.getenv("TRITON_MODEL_DIR")
    
    class Config:
        env_file = str(Path(__file__).resolve().parents[3] / ".env")
        case_sensitive = False
        extra = "ignore"  # Ignore extra environment variables


def _parse_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def _validate_env_authority() -> None:
    """Fail fast if service-local and root env files conflict on critical keys."""
    repo_env = Path(__file__).resolve().parents[3] / ".env"
    service_env = Path(__file__).resolve().parents[1] / ".env"

    if not repo_env.exists() or not service_env.exists():
        return

    repo_vals = _parse_env_file(repo_env)
    svc_vals = _parse_env_file(service_env)

    critical_keys = {
        "GLM_MODEL_PATH",
        "GLM_PRECISION_MODE",
        "REQUEST_TIMEOUT_SECONDS",
        "LOW_VRAM_MAX_TOKENS",
        "LOW_VRAM_MAX_IMAGE_EDGE",
        "LOW_VRAM_RETRY_MAX_TOKENS",
        "LOW_VRAM_RETRY_IMAGE_EDGE",
        "CHUNK_LARGE_PAGES",
        "CHUNK_TRIGGER_MAX_EDGE",
        "CHUNK_SEGMENT_COUNT",
        "CHUNK_OVERLAP_PX",
        "CHUNK_SEGMENT_MAX_TOKENS",
        "USE_ISOLATED_GPU_EXECUTOR",
    }

    conflicts = []
    for key in critical_keys:
        rv = repo_vals.get(key)
        sv = svc_vals.get(key)
        if rv is not None and sv is not None and rv != sv:
            conflicts.append(f"{key}: root='{rv}' service='{sv}'")

    if conflicts:
        joined = "; ".join(conflicts)
        raise RuntimeError(
            f"Environment conflict detected between {repo_env} and {service_env}. "
            f"Use root .env as single authority. Conflicts: {joined}"
        )


def setup_logging(log_level: str = "INFO") -> None:
    """Configure structured logging."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "service": "glm-ocr-service", "message": "%(message)s"}',
        datefmt="%Y-%m-%dT%H:%M:%S"
    )


_validate_env_authority()
settings = Settings()
setup_logging(settings.log_level)
