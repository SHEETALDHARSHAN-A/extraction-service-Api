"""GLM-OCR Service - FastAPI application."""

import time
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .models import (
    RegionExtractionRequest,
    RegionExtractionResponse,
    BatchRegionExtractionRequest,
    BatchRegionExtractionResponse,
    BatchRegionResult,
    HealthResponse,
    ErrorResponse,
    TokenUsage
)
from .prompts import get_prompt_for_region_type
from .glm_inference import GLMInferenceEngine

logger = logging.getLogger(__name__)

# Global inference engine
inference_engine: GLMInferenceEngine = None
service_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    global inference_engine
    
    # Startup
    logger.info(f"Starting {settings.service_name} v{settings.service_version}")
    try:
        inference_engine = GLMInferenceEngine(
            model_path=settings.glm_model_path,
            precision_mode=settings.glm_precision_mode
        )
        logger.info("GLM-OCR inference engine initialized")
    except Exception as e:
        logger.error(f"Failed to initialize inference engine: {e}")
        # Continue anyway - health check will report unhealthy
    
    yield
    
    # Shutdown
    logger.info("Shutting down GLM-OCR service")
    if inference_engine:
        inference_engine.cleanup()


# Create FastAPI app
app = FastAPI(
    title="GLM-OCR Service",
    description="Region-based content extraction service using GLM-OCR",
    version=settings.service_version,
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Middleware for request ID and logging
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add request ID to all requests."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    start_time = time.time()
    logger.info(f"Request started: {request.method} {request.url.path} [request_id={request_id}]")
    
    response = await call_next(request)
    
    process_time = (time.time() - start_time) * 1000
    logger.info(f"Request completed: {request.method} {request.url.path} [request_id={request_id}] [time={process_time:.2f}ms] [status={response.status_code}]")
    
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{process_time:.2f}ms"
    
    return response


# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(f"Unhandled exception: {exc} [request_id={request_id}]", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal server error",
            detail=str(exc),
            request_id=request_id
        ).dict()
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.
    
    Returns service status and model availability.
    """
    uptime = int(time.time() - service_start_time)
    
    model_loaded = inference_engine is not None and inference_engine.is_ready()
    gpu_available = False
    device = "cpu"
    
    if inference_engine:
        device = inference_engine.device
        gpu_available = device == "cuda"
    
    status = "healthy" if model_loaded else "unhealthy"
    
    return HealthResponse(
        status=status,
        service=settings.service_name,
        version=settings.service_version,
        uptime_seconds=uptime,
        model_loaded=model_loaded,
        gpu_available=gpu_available,
        device=device
    )


@app.post("/extract-region", response_model=RegionExtractionResponse)
async def extract_region(request: RegionExtractionRequest, req: Request):
    """
    Extract content from a single image region.
    
    Args:
        request: Region extraction request with image, region_type, and options
    
    Returns:
        Extracted content with confidence and timing information
    """
    request_id = getattr(req.state, "request_id", "unknown")
    
    if not inference_engine or not inference_engine.is_ready():
        raise HTTPException(
            status_code=503,
            detail="Model not initialized or unavailable"
        )
    
    start_time = time.time()
    
    try:
        # Get prompt for region type
        prompt = get_prompt_for_region_type(
            request.region_type,
            request.prompt
        )
        
        # Get options
        options = request.options or {}
        max_tokens = options.get("max_tokens", settings.max_tokens_default)
        max_tokens = min(max_tokens, settings.max_tokens_limit)
        output_format = options.get("output_format", "text")
        
        logger.info(f"Extracting region: type={request.region_type}, prompt={prompt[:50]}... [request_id={request_id}]")
        
        # Extract content
        content, confidence, prompt_tokens, completion_tokens = inference_engine.extract_content(
            image_base64=request.image,
            prompt=prompt,
            max_tokens=max_tokens,
            output_format=output_format
        )
        
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        logger.info(f"Region extraction completed: confidence={confidence:.2f}, time={processing_time_ms}ms [request_id={request_id}]")
        
        return RegionExtractionResponse(
            content=content,
            confidence=confidence,
            processing_time_ms=processing_time_ms,
            tokens_used=TokenUsage(
                prompt=prompt_tokens,
                completion=completion_tokens
            )
        )
        
    except ValueError as e:
        logger.error(f"Validation error: {e} [request_id={request_id}]")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Extraction failed: {e} [request_id={request_id}]", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")


@app.post("/extract-regions-batch", response_model=BatchRegionExtractionResponse)
async def extract_regions_batch(request: BatchRegionExtractionRequest, req: Request):
    """
    Extract content from multiple image regions in batch.
    
    Args:
        request: Batch extraction request with list of regions
    
    Returns:
        Results for each region with total timing information
    """
    request_id = getattr(req.state, "request_id", "unknown")
    
    if not inference_engine or not inference_engine.is_ready():
        raise HTTPException(
            status_code=503,
            detail="Model not initialized or unavailable"
        )
    
    start_time = time.time()
    
    # Validate batch size
    if len(request.regions) > settings.max_batch_size:
        raise HTTPException(
            status_code=400,
            detail=f"Batch size exceeds maximum of {settings.max_batch_size}"
        )
    
    logger.info(f"Processing batch of {len(request.regions)} regions [request_id={request_id}]")
    
    results = []
    total_prompt_tokens = 0
    total_completion_tokens = 0
    
    # Get options
    options = request.options or {}
    max_tokens = options.get("max_tokens", settings.max_tokens_default)
    max_tokens = min(max_tokens, settings.max_tokens_limit)
    output_format = options.get("output_format", "text")
    
    # Process each region
    for region in request.regions:
        try:
            # Get prompt for region type
            prompt = get_prompt_for_region_type(
                region.region_type,
                region.prompt
            )
            
            # Extract content
            content, confidence, prompt_tokens, completion_tokens = inference_engine.extract_content(
                image_base64=region.image,
                prompt=prompt,
                max_tokens=max_tokens,
                output_format=output_format
            )
            
            total_prompt_tokens += prompt_tokens
            total_completion_tokens += completion_tokens
            
            results.append(BatchRegionResult(
                region_id=region.region_id,
                content=content,
                confidence=confidence,
                error=None
            ))
            
            logger.info(f"Region {region.region_id} processed successfully [request_id={request_id}]")
            
        except Exception as e:
            logger.error(f"Failed to process region {region.region_id}: {e} [request_id={request_id}]")
            results.append(BatchRegionResult(
                region_id=region.region_id,
                content="",
                confidence=0.0,
                error=str(e)
            ))
    
    total_processing_time_ms = int((time.time() - start_time) * 1000)
    
    logger.info(f"Batch processing completed: {len(results)} regions, time={total_processing_time_ms}ms [request_id={request_id}]")
    
    return BatchRegionExtractionResponse(
        results=results,
        total_processing_time_ms=total_processing_time_ms,
        tokens_used=TokenUsage(
            prompt=total_prompt_tokens,
            completion=total_completion_tokens
        )
    )


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "status": "running",
        "endpoints": {
            "health": "/health",
            "extract_region": "/extract-region",
            "extract_regions_batch": "/extract-regions-batch"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level=settings.log_level.lower()
    )
