"""Structured error logging utilities."""

import json
import logging
import traceback
import sys
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def log_structured_error(
    error: Exception,
    error_type: str,
    request_id: str = "unknown",
    context: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log an error with structured JSON format including full context.
    
    Args:
        error: The exception that occurred
        error_type: Type/category of error (e.g., "GPU_MEMORY_ERROR", "VALIDATION_ERROR")
        request_id: Request ID for tracing
        context: Additional context information (document size, GPU stats, etc.)
    """
    # Get stack trace
    exc_type, exc_value, exc_traceback = sys.exc_info()
    stack_trace = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    
    # Build structured error log
    error_log = {
        "timestamp": None,  # Will be added by logging formatter
        "level": "ERROR",
        "service": "glm-ocr-service",
        "request_id": request_id,
        "error_type": error_type,
        "error_message": str(error),
        "error_class": error.__class__.__name__,
        "stack_trace": stack_trace,
        "context": context or {}
    }
    
    # Log as JSON string
    logger.error(json.dumps(error_log))


def log_gpu_memory_error(
    error: Exception,
    request_id: str,
    gpu_stats: Optional[Dict[str, float]] = None,
    document_size_mb: Optional[float] = None,
    batch_size: Optional[int] = None,
    retry_attempt: Optional[int] = None
) -> None:
    """
    Log a GPU memory error with relevant context.
    
    Args:
        error: The CUDA OOM exception
        request_id: Request ID for tracing
        gpu_stats: GPU memory statistics
        document_size_mb: Size of document being processed
        batch_size: Batch size if applicable
        retry_attempt: Retry attempt number if applicable
    """
    context = {}
    
    if document_size_mb is not None:
        context["document_size_mb"] = document_size_mb
    
    if gpu_stats:
        context.update({
            "gpu_memory_allocated_gb": gpu_stats.get("allocated_gb", 0),
            "gpu_memory_free_gb": gpu_stats.get("free_gb", 0),
            "gpu_memory_total_gb": gpu_stats.get("total_gb", 0),
            "gpu_memory_reserved_gb": gpu_stats.get("reserved_gb", 0),
        })
    
    if batch_size is not None:
        context["batch_size"] = batch_size
    
    if retry_attempt is not None:
        context["retry_attempt"] = retry_attempt
    
    log_structured_error(error, "GPU_MEMORY_ERROR", request_id, context)


def log_model_unavailable_error(
    error: Exception,
    request_id: str,
    gpu_stats: Optional[Dict[str, float]] = None,
    uptime_seconds: Optional[int] = None
) -> None:
    """
    Log a model unavailable error (potential stub crash).
    
    Args:
        error: The exception
        request_id: Request ID for tracing
        gpu_stats: GPU memory statistics at time of failure
        uptime_seconds: Service uptime in seconds
    """
    context = {}
    
    if gpu_stats:
        context.update({
            "gpu_memory_allocated_gb": gpu_stats.get("allocated_gb", 0),
            "gpu_memory_free_gb": gpu_stats.get("free_gb", 0),
            "gpu_memory_total_gb": gpu_stats.get("total_gb", 0),
        })
    
    if uptime_seconds is not None:
        context["service_uptime_seconds"] = uptime_seconds
    
    log_structured_error(error, "MODEL_UNAVAILABLE_ERROR", request_id, context)


def log_validation_error(
    error: Exception,
    request_id: str,
    validation_type: str,
    validation_details: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log a validation error with details.
    
    Args:
        error: The validation exception
        request_id: Request ID for tracing
        validation_type: Type of validation that failed
        validation_details: Details about the validation failure
    """
    context = {
        "validation_type": validation_type
    }
    
    if validation_details:
        context["validation_details"] = validation_details
    
    log_structured_error(error, "VALIDATION_ERROR", request_id, context)


def log_inference_error(
    error: Exception,
    request_id: str,
    prompt: Optional[str] = None,
    max_tokens: Optional[int] = None,
    output_format: Optional[str] = None,
    processing_time_ms: Optional[int] = None
) -> None:
    """
    Log an inference error with request parameters.
    
    Args:
        error: The inference exception
        request_id: Request ID for tracing
        prompt: Prompt used for inference
        max_tokens: Max tokens parameter
        output_format: Output format requested
        processing_time_ms: Time spent before error
    """
    context = {}
    
    if prompt:
        # Truncate prompt for logging
        context["prompt_preview"] = prompt[:100] + "..." if len(prompt) > 100 else prompt
    
    if max_tokens is not None:
        context["max_tokens"] = max_tokens
    
    if output_format:
        context["output_format"] = output_format
    
    if processing_time_ms is not None:
        context["processing_time_ms"] = processing_time_ms
    
    log_structured_error(error, "INFERENCE_ERROR", request_id, context)
