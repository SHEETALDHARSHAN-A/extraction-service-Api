"""FastAPI application for PaddleOCR Layout Detection Service."""

import base64
import io
import time
import uuid
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import numpy as np

from .config import settings, setup_logging, validate_config
from .models import (
    DetectLayoutRequest,
    DetectLayoutResponse,
    HealthResponse,
    ErrorResponse,
    Region,
    PageDimensions,
)
from .layout_detector import get_layout_detector

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Service start time for uptime calculation
SERVICE_START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    logger.info(f"Starting {settings.service_name} v{settings.service_version}")
    logger.info(f"Configuration: GPU={settings.use_gpu_bool}, Model dir={settings.model_dir}")
    
    # Validate configuration
    try:
        validate_config()
        logger.info("Configuration validation passed")
    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        raise
    
    # Initialize layout detector (lazy loading, will initialize on first use)
    try:
        detector = get_layout_detector()
        logger.info("Layout detector initialized (lazy loading enabled)")
    except Exception as e:
        logger.error(f"Failed to initialize layout detector: {e}")
        # Don't raise here, allow service to start in degraded mode
    
    logger.info(f"Service started successfully on {settings.service_host}:{settings.service_port}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down service...")
    logger.info("Service shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="PaddleOCR Layout Detection Service",
    description="Microservice for document layout detection using PPStructureV3",
    version=settings.service_version,
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Middleware for request ID and logging
@app.middleware("http")
async def add_request_id_and_logging(request: Request, call_next):
    """Add request ID to all requests and log request/response."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    start_time = time.time()
    logger.info(f"Request {request_id}: {request.method} {request.url.path}")
    
    try:
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000
        
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{process_time:.2f}ms"
        
        logger.info(
            f"Request {request_id} completed: "
            f"status={response.status_code} time={process_time:.2f}ms"
        )
        
        return response
    except Exception as e:
        process_time = (time.time() - start_time) * 1000
        logger.error(
            f"Request {request_id} failed: {str(e)} time={process_time:.2f}ms",
            exc_info=True
        )
        raise


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions."""
    request_id = getattr(request.state, "request_id", "unknown")
    
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=f"HTTP{exc.status_code}",
            message=exc.detail,
            request_id=request_id
        ).model_dump()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions."""
    request_id = getattr(request.state, "request_id", "unknown")
    
    logger.error(f"Unhandled exception in request {request_id}: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="InternalServerError",
            message="An internal server error occurred",
            detail=str(exc) if settings.log_level == "DEBUG" else None,
            request_id=request_id
        ).model_dump()
    )


# Helper functions
def decode_base64_image(image_data: str) -> Image.Image:
    """
    Decode base64 image data to PIL Image.
    
    Args:
        image_data: Base64-encoded image string
        
    Returns:
        PIL Image object
        
    Raises:
        ValueError: If image data is invalid
    """
    try:
        # Remove data URI prefix if present
        if image_data.startswith("data:image"):
            image_data = image_data.split(",", 1)[1]
        
        # Decode base64
        image_bytes = base64.b64decode(image_data)
        
        # Open image
        image = Image.open(io.BytesIO(image_bytes))
        
        # Convert to RGB if necessary
        if image.mode != "RGB":
            image = image.convert("RGB")
        
        return image
        
    except Exception as e:
        logger.error(f"Failed to decode base64 image: {e}")
        raise ValueError(f"Invalid image data: {e}")


# API Endpoints
@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with service information."""
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "status": "running",
        "endpoints": {
            "health": "/health",
            "detect_layout": "/detect-layout",
            "docs": "/docs"
        }
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint.
    
    Returns service health status and model information.
    """
    try:
        detector = get_layout_detector()
        model_info = detector.get_model_info()
        
        uptime = time.time() - SERVICE_START_TIME
        
        return HealthResponse(
            status="healthy",
            service=settings.service_name,
            version=settings.service_version,
            uptime_seconds=uptime,
            models_loaded=model_info["initialized"],
            gpu_available=settings.use_gpu_bool,
            device="cuda" if settings.use_gpu_bool else "cpu",
            model_info=model_info
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        uptime = time.time() - SERVICE_START_TIME
        
        return HealthResponse(
            status="degraded",
            service=settings.service_name,
            version=settings.service_version,
            uptime_seconds=uptime,
            models_loaded=False,
            gpu_available=settings.use_gpu_bool,
            device="cuda" if settings.use_gpu_bool else "cpu",
            model_info={"error": str(e)}
        )


@app.post("/detect-layout", response_model=DetectLayoutResponse, tags=["Layout Detection"])
async def detect_layout(request: DetectLayoutRequest, req: Request):
    """
    Detect document layout regions.
    
    Processes an image and returns detected regions with bounding boxes.
    
    Args:
        request: Layout detection request with image and options
        req: FastAPI request object
        
    Returns:
        Layout detection response with regions and metadata
        
    Raises:
        HTTPException: If detection fails
    """
    request_id = getattr(req.state, "request_id", "unknown")
    start_time = time.time()
    
    try:
        # Decode image
        logger.info(f"Request {request_id}: Decoding image...")
        try:
            pil_image = decode_base64_image(request.image)
            logger.info(f"Request {request_id}: Image decoded successfully: {pil_image.size}")
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid image data: {str(e)}"
            )
        
        # Validate image size
        detector = get_layout_detector()
        try:
            detector.validate_image_size(pil_image, max_size_mb=settings.max_image_size_mb)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=str(e)
            )
        
        # Convert to numpy array
        numpy_image = np.array(pil_image)
        
        # Get detection options
        options = request.options or DetectLayoutRequest.model_fields["options"].default_factory()
        min_confidence = options.min_confidence or settings.min_confidence_default
        
        logger.info(
            f"Request {request_id}: Starting layout detection "
            f"(confidence={min_confidence}, tables={options.detect_tables}, "
            f"formulas={options.detect_formulas})"
        )
        
        # Perform layout detection
        try:
            regions_data, page_dims = detector.detect_regions(
                image=numpy_image,
                min_confidence=min_confidence,
                detect_tables=options.detect_tables,
                detect_formulas=options.detect_formulas
            )
        except Exception as e:
            logger.error(f"Request {request_id}: Layout detection failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Layout detection failed: {str(e)}"
            )
        
        # Convert to Pydantic models
        regions = [Region(**region) for region in regions_data]
        page_dimensions = PageDimensions(**page_dims) if options.return_image_dimensions else None
        
        # Calculate processing time
        processing_time_ms = (time.time() - start_time) * 1000
        
        # Get model info
        model_info = detector.get_model_info()
        
        logger.info(
            f"Request {request_id}: Layout detection completed "
            f"({len(regions)} regions, {processing_time_ms:.2f}ms)"
        )
        
        return DetectLayoutResponse(
            regions=regions,
            page_dimensions=page_dimensions,
            processing_time_ms=processing_time_ms,
            model_version=model_info["version"],
            total_regions_detected=len(regions_data),
            regions_filtered=0  # TODO: Track filtered regions in detector
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Request {request_id}: Unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )


# Run the application
if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.service_host,
        port=settings.service_port,
        log_level=settings.log_level.lower(),
        reload=False  # Set to True for development
    )
