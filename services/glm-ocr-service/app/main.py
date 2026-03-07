"""GLM-OCR Service - FastAPI application."""
import asyncio
from concurrent import futures

import time
import logging
import logging.config
import uuid
import json
import os
import base64
import io
from contextlib import asynccontextmanager
from typing import Dict, Any
from types import SimpleNamespace
from PIL import Image

import grpc
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

from .config import settings
from .models import (
    RegionExtractionRequest,
    RegionExtractionResponse,
    BatchRegionExtractionRequest,
    BatchRegionExtractionResponse,
    BatchRegionResult,
    HealthResponse,
    ErrorResponse,
    TokenUsage,
    ExtractionOptions,
    WordBoundingBox,
    KeyValuePair
)
from .prompts import get_prompt_for_region_type
from .glm_inference import GLMInferenceEngine
from .gpu_executor import SingleFlightGPUExecutor
from .gpu_monitor import GPUMonitor
from .extractors import WordLevelExtractor, KeyValueExtractor
from .validators import ExtractionValidator
from .error_logger import (
    log_structured_error,
    log_gpu_memory_error,
    log_model_unavailable_error,
    log_inference_error
)
from .tracing import (
    init_jaeger_tracer,
    extract_span_context,
    start_span,
    set_span_tag,
    log_span_error,
    finish_span,
    get_trace_id
)
from .preprocessing_cache import PreprocessingCache
from .performance_monitor import PerformanceMonitor

# Configure structured JSON logging
class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record):
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "service": "glm-ocr-service",
            "message": record.getMessage(),
        }
        
        # Add request_id if available
        if hasattr(record, 'request_id'):
            log_entry["request_id"] = record.request_id
        
        # Add extra context if available
        if hasattr(record, 'context'):
            log_entry["context"] = record.context
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry)

# Configure logging
logging_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": JSONFormatter
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "stream": "ext://sys.stdout"
        }
    },
    "root": {
        "level": settings.log_level.upper(),
        "handlers": ["console"]
    }
}

logging.config.dictConfig(logging_config)
logger = logging.getLogger(__name__)


async def _extract_with_timeout(
    image_base64: str,
    prompt: str,
    max_tokens: int,
    output_format: str,
) -> tuple[str, float, int, int]:
    """Run inference with hard timeout; use isolated worker when configured."""
    if settings.use_isolated_gpu_executor and gpu_executor:
        return await asyncio.to_thread(
            gpu_executor.execute,
            image_base64=image_base64,
            prompt=prompt,
            max_tokens=max_tokens,
            output_format=output_format,
            timeout_seconds=float(settings.request_timeout_seconds),
        )

    return await asyncio.wait_for(
        asyncio.to_thread(
            inference_engine.extract_content,
            image_base64=image_base64,
            prompt=prompt,
            max_tokens=max_tokens,
            output_format=output_format,
        ),
        timeout=float(settings.request_timeout_seconds),
    )


def _inference_ready() -> bool:
    if settings.use_isolated_gpu_executor:
        return gpu_executor is not None and gpu_executor.is_ready()
    return inference_engine is not None and inference_engine.is_ready()


def infer_page_bbox(image_payload: str) -> list[int]:
    """Infer page bbox [x, y, w, h] from base64 image payload or path."""
    try:
        from PIL import Image
        import io
        import base64
        import os
        
        # If payload is a path
        if len(image_payload) < 2000 and os.path.exists(image_payload):
            image = Image.open(image_payload).convert("RGB")
        else:
            payload = image_payload.split(",", 1)[1] if image_payload.startswith("data:") else image_payload
            image_bytes = base64.b64decode(payload)
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            
        return [0, 0, int(image.width), int(image.height)]
    except Exception:
        return [0, 0, 1000, 1000]


def build_line_bounding_boxes(content: str, page_bbox: list[int], confidence: float) -> list[dict[str, Any]]:
    """Build lightweight approximate line-level bboxes from content for fast mode."""
    x, y, width, height = page_bbox
    lines = [line.strip() for line in (content or "").splitlines() if line.strip()]
    if not lines:
        lines = [(content or "").strip()] if (content or "").strip() else []
    if not lines:
        return []

    line_h = max(1, height // max(1, len(lines)))
    boxes = []
    for i, line in enumerate(lines):
        boxes.append({
            "text": line,
            "bbox": [x, y + i * line_h, width, min(line_h, height - i * line_h)],
            "confidence": confidence,
            "type": "line"
        })
    return boxes


def log_extraction_request(request_id: str, status: str, document_size: int = None, 
                          processing_time_ms: int = None, context: Dict[str, Any] = None,
                          trace_id: str = None):
    """
    Log extraction request with standard fields.
    
    Args:
        request_id: Request ID for tracing
        status: Request status (started, completed, failed)
        document_size: Size of document in bytes
        processing_time_ms: Processing time in milliseconds
        context: Additional context information
        trace_id: Distributed trace ID
    """
    log_context = context or {}
    
    if document_size is not None:
        log_context["document_size"] = document_size
    
    if processing_time_ms is not None:
        log_context["processing_time_ms"] = processing_time_ms
    
    log_context["status"] = status
    
    if trace_id:
        log_context["trace_id"] = trace_id
    
    message = f"Extraction request {status}"
    
    log_record = logger.makeRecord(
        logger.name, logging.INFO, "", 0,
        message, (), None
    )
    log_record.request_id = request_id
    log_record.context = log_context
    logger.handle(log_record)

# Prometheus metrics
gpu_memory_allocated = Gauge('gpu_memory_allocated_gb', 'GPU memory allocated in GB')
gpu_memory_free = Gauge('gpu_memory_free_gb', 'GPU memory free in GB')
gpu_memory_total = Gauge('gpu_memory_total_gb', 'Total GPU memory in GB')
gpu_memory_utilization = Gauge('gpu_memory_utilization_percent', 'GPU memory utilization percentage')

extraction_requests_total = Counter('extraction_requests_total', 'Total extraction requests', ['endpoint', 'status'])
extraction_duration_seconds = Histogram('extraction_duration_seconds', 'Extraction request duration', ['endpoint'])
extraction_tokens_total = Counter('extraction_tokens_total', 'Total tokens used', ['type'])

# Global inference engine and GPU monitor
inference_engine: GLMInferenceEngine = None
gpu_executor: SingleFlightGPUExecutor = None
gpu_monitor: GPUMonitor = None
word_extractor: WordLevelExtractor = None
kv_extractor: KeyValueExtractor = None
validator: ExtractionValidator = None
preprocessing_cache: PreprocessingCache = None
performance_monitor: PerformanceMonitor = None
service_start_time = time.time()
jaeger_tracer = None
grpc_server = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    global inference_engine, gpu_executor, gpu_monitor, word_extractor, kv_extractor, validator, preprocessing_cache, performance_monitor, jaeger_tracer
    
    # Startup
    logger.info(f"Starting {settings.service_name} v{settings.service_version}")
    
    # Initialize Jaeger tracer
    try:
        jaeger_host = os.getenv("JAEGER_AGENT_HOST", "localhost")
        jaeger_port = int(os.getenv("JAEGER_AGENT_PORT", "6831"))
        jaeger_tracer = init_jaeger_tracer(
            service_name=settings.service_name,
            jaeger_host=jaeger_host,
            jaeger_port=jaeger_port
        )
        if jaeger_tracer:
            logger.info("Jaeger tracer initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize Jaeger tracer: {e}")
    
    # Initialize GPU monitor
    try:
        gpu_monitor = GPUMonitor()
        logger.info("GPU monitor initialized")
    except Exception as e:
        logger.error(f"Failed to initialize GPU monitor: {e}")
    
    # Initialize extractors
    try:
        word_extractor = WordLevelExtractor()
        kv_extractor = KeyValueExtractor()
        logger.info("Extractors initialized")
    except Exception as e:
        logger.error(f"Failed to initialize extractors: {e}")
    
    # Initialize validator
    try:
        validator = ExtractionValidator()
        logger.info("Validator initialized")
    except Exception as e:
        logger.error(f"Failed to initialize validator: {e}")
    
    # Initialize preprocessing cache
    try:
        cache_size_mb = int(os.getenv("PREPROCESSING_CACHE_SIZE_MB", "500"))
        cache_ttl_seconds = int(os.getenv("PREPROCESSING_CACHE_TTL_SECONDS", "3600"))
        preprocessing_cache = PreprocessingCache(
            max_size_mb=cache_size_mb,
            ttl_seconds=cache_ttl_seconds
        )
        logger.info(f"Preprocessing cache initialized: size={cache_size_mb}MB, ttl={cache_ttl_seconds}s")
    except Exception as e:
        logger.error(f"Failed to initialize preprocessing cache: {e}")
    
    # Initialize performance monitor
    try:
        slow_threshold_ms = int(os.getenv("SLOW_PAGE_THRESHOLD_MS", "30000"))
        performance_monitor = PerformanceMonitor(
            slow_page_threshold_ms=slow_threshold_ms,
            history_size=1000
        )
        logger.info(f"Performance monitor initialized: slow_threshold={slow_threshold_ms}ms")
    except Exception as e:
        logger.error(f"Failed to initialize performance monitor: {e}")
    
    # Initialize inference engine or isolated executor
    try:
        if settings.use_isolated_gpu_executor:
            gpu_executor = SingleFlightGPUExecutor(
                model_path=settings.glm_model_path,
                precision_mode=settings.glm_precision_mode,
            )
            gpu_executor.start()
            logger.info("GLM-OCR isolated GPU executor initialized")
        else:
            inference_engine = GLMInferenceEngine(
                model_path=settings.glm_model_path,
                precision_mode=settings.glm_precision_mode
            )
            logger.info("GLM-OCR inference engine initialized")
        
        if gpu_monitor:
            gpu_monitor.log_memory_usage("after model load")
        
        # Model warmup: run dummy inference to reduce first-request latency.
        if settings.startup_warmup_enabled:
            skip_cpu_warmup = (
                not settings.use_isolated_gpu_executor
                and inference_engine is not None
                and inference_engine.device == "cpu"
                and not settings.startup_warmup_on_cpu
            )

            if skip_cpu_warmup:
                logger.info(
                    "Skipping startup warmup on CPU (set STARTUP_WARMUP_ON_CPU=true to enable)"
                )
            else:
                try:
                    logger.info("Starting model warmup...")
                    warmup_start = time.time()

                    # Create a tiny test image for one short warmup pass.
                    import base64
                    from PIL import Image
                    import io

                    dummy_img = Image.new('RGB', (100, 100), color='white')
                    buffer = io.BytesIO()
                    dummy_img.save(buffer, format='PNG')
                    dummy_image_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
                    warmup_max_tokens = max(1, int(settings.startup_warmup_max_tokens))

                    # Run dummy inference
                    if settings.use_isolated_gpu_executor and gpu_executor:
                        gpu_executor.execute(
                            image_base64=dummy_image_b64,
                            prompt="Extract text",
                            max_tokens=warmup_max_tokens,
                            output_format="text",
                            timeout_seconds=min(30, settings.request_timeout_seconds),
                        )
                    elif inference_engine:
                        _, _, _, _ = inference_engine.extract_content(
                            image_base64=dummy_image_b64,
                            prompt="Extract text",
                            max_tokens=warmup_max_tokens,
                            output_format="text"
                        )

                    warmup_time = time.time() - warmup_start
                    logger.info(f"Model warmup completed in {warmup_time:.2f}s")

                    if gpu_monitor:
                        gpu_monitor.log_memory_usage("after model warmup")

                except Exception as warmup_error:
                    logger.warning(f"Model warmup failed (non-critical): {warmup_error}")
        else:
            logger.info("Startup warmup disabled via STARTUP_WARMUP_ENABLED=false")
    
    except Exception as e:
        logger.error(f"Failed to initialize inference engine: {e}")
        # Continue anyway - health check will report unhealthy

    # Start internal gRPC server for service-to-service calls
    grpc_port = int(os.getenv("GRPC_PORT", "50062"))
    _start_grpc_server(grpc_port)
    
    yield
    
    # Shutdown
    logger.info("Shutting down GLM-OCR service")
    _stop_grpc_server()
    if gpu_executor:
        gpu_executor.stop()
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


def _deserialize_grpc_request(payload: bytes) -> dict:
    return json.loads(payload.decode("utf-8")) if payload else {}


def _serialize_grpc_response(response: dict) -> bytes:
    return json.dumps(response).encode("utf-8")


def _grpc_extract_regions_batch(request_payload: dict, _context) -> dict:
    request_id = str(uuid.uuid4())
    fake_req = SimpleNamespace(state=SimpleNamespace(request_id=request_id, trace_id="grpc"))

    try:
        request = BatchRegionExtractionRequest(**request_payload)
        response = asyncio.run(extract_regions_batch(request, fake_req))
        if hasattr(response, "model_dump"):
            return response.model_dump()
        return dict(response)
    except HTTPException as exc:
        raise RuntimeError(f"glm-ocr grpc batch extraction failed: {exc.detail}") from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"glm-ocr grpc batch extraction failed: {exc}") from exc


def _start_grpc_server(port: int) -> None:
    global grpc_server
    if grpc_server is not None:
        return

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    rpc_handlers = {
        "ExtractRegionsBatch": grpc.unary_unary_rpc_method_handler(
            _grpc_extract_regions_batch,
            request_deserializer=_deserialize_grpc_request,
            response_serializer=_serialize_grpc_response,
        )
    }
    generic_handler = grpc.method_handlers_generic_handler("glmocr.GLMOCRService", rpc_handlers)
    server.add_generic_rpc_handlers((generic_handler,))
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    grpc_server = server
    logger.info("GLM-OCR gRPC server started on port %s", port)


def _stop_grpc_server() -> None:
    global grpc_server
    if grpc_server is None:
        return
    grpc_server.stop(grace=3)
    grpc_server = None


def update_gpu_metrics():
    """Update Prometheus GPU metrics."""
    if gpu_monitor and gpu_monitor.gpu_available:
        stats = gpu_monitor.get_memory_stats()
        gpu_memory_allocated.set(stats.get('allocated_gb', 0))
        gpu_memory_free.set(stats.get('free_gb', 0))
        gpu_memory_total.set(stats.get('total_gb', 0))
        
        utilization = gpu_monitor.get_utilization_percent()
        if utilization is not None:
            gpu_memory_utilization.set(utilization)


# Middleware for request ID and logging
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add request ID to all requests."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    # Extract span context from headers and start span
    span = None
    trace_id = ""
    if jaeger_tracer:
        headers = dict(request.headers)
        span_context = extract_span_context(jaeger_tracer, headers)
        span = start_span(jaeger_tracer, f"{request.method} {request.url.path}", span_context)
        
        if span:
            set_span_tag(span, "http.method", request.method)
            set_span_tag(span, "http.url", str(request.url))
            set_span_tag(span, "component", "glm-ocr-service")
            set_span_tag(span, "request_id", request_id)
            trace_id = get_trace_id(span)
            request.state.span = span
            request.state.trace_id = trace_id
    
    start_time = time.time()
    
    # Log request start with structured logging
    log_record = logger.makeRecord(
        logger.name, logging.INFO, "", 0,
        f"Request started: {request.method} {request.url.path}",
        (), None
    )
    log_record.request_id = request_id
    log_record.context = {
        "method": request.method,
        "path": str(request.url.path),
        "client_host": request.client.host if request.client else "unknown"
    }
    if trace_id:
        log_record.context["trace_id"] = trace_id
    logger.handle(log_record)
    
    response = await call_next(request)
    
    process_time = (time.time() - start_time) * 1000
    
    # Log request completion with structured logging
    log_record = logger.makeRecord(
        logger.name, logging.INFO, "", 0,
        f"Request completed: {request.method} {request.url.path}",
        (), None
    )
    log_record.request_id = request_id
    log_record.context = {
        "method": request.method,
        "path": str(request.url.path),
        "processing_time_ms": round(process_time, 2),
        "status_code": response.status_code
    }
    if trace_id:
        log_record.context["trace_id"] = trace_id
    logger.handle(log_record)
    
    # Finish span
    if span:
        set_span_tag(span, "http.status_code", response.status_code)
        if response.status_code >= 400:
            set_span_tag(span, "error", True)
        finish_span(span)
    
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{process_time:.2f}ms"
    if trace_id:
        response.headers["X-Trace-ID"] = trace_id
    
    return response


# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler with structured error logging."""
    request_id = getattr(request.state, "request_id", "unknown")
    
    # Use structured error logging
    log_structured_error(
        error=exc,
        error_type="UNHANDLED_EXCEPTION",
        request_id=request_id,
        context={
            "method": request.method,
            "url": str(request.url),
            "client_host": request.client.host if request.client else "unknown"
        }
    )
    
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
    
    model_loaded = _inference_ready()
    gpu_available = False
    device = "cpu"
    gpu_memory_stats = None
    
    if settings.use_isolated_gpu_executor:
        device = "cuda" if model_loaded else "cpu"
        gpu_available = model_loaded
    elif inference_engine:
        device = inference_engine.device
        gpu_available = device == "cuda"
    
    if gpu_monitor and gpu_available:
        gpu_memory_stats = gpu_monitor.get_memory_stats()
        # Update Prometheus metrics
        update_gpu_metrics()
        
        # Log health check with GPU memory usage and timestamp
        log_record = logger.makeRecord(
            logger.name, logging.INFO, "", 0,
            "Triton stub process health check",
            (), None
        )
        log_record.context = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "model_loaded": model_loaded,
            "gpu_memory_allocated_gb": gpu_memory_stats.get('allocated_gb', 0),
            "gpu_memory_free_gb": gpu_memory_stats.get('free_gb', 0),
            "gpu_memory_total_gb": gpu_memory_stats.get('total_gb', 0),
            "gpu_memory_utilization_percent": gpu_monitor.get_utilization_percent(),
            "uptime_seconds": uptime,
            "health_status": "healthy" if model_loaded else "unhealthy"
        }
        logger.handle(log_record)
    
    status = "healthy" if model_loaded else "unhealthy"
    
    # If model is not loaded, log as potential stub crash
    if not model_loaded:
        log_record = logger.makeRecord(
            logger.name, logging.ERROR, "", 0,
            "Health check failed: model not loaded or unavailable. This may indicate a Triton stub process crash or restart.",
            (), None
        )
        log_record.context = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "uptime_seconds": uptime,
            "health_status": "unhealthy"
        }
        logger.handle(log_record)
    
    return HealthResponse(
        status=status,
        service=settings.service_name,
        version=settings.service_version,
        uptime_seconds=uptime,
        model_loaded=model_loaded,
        gpu_available=gpu_available,
        device=device,
        gpu_memory_stats=gpu_memory_stats
    )


@app.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint.
    
    Returns metrics in Prometheus format.
    """
    # Update GPU metrics before returning
    update_gpu_metrics()
    
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/cache/stats")
async def cache_stats():
    """
    Get preprocessing cache statistics.
    
    Returns cache performance metrics.
    """
    if preprocessing_cache:
        stats = preprocessing_cache.get_stats()
        return JSONResponse(content=stats)
    else:
        return JSONResponse(
            status_code=503,
            content={"error": "Preprocessing cache not initialized"}
        )


@app.get("/performance/stats")
async def performance_stats():
    """
    Get performance monitoring statistics.
    
    Returns processing time metrics and slow operation statistics.
    """
    if performance_monitor:
        stats = performance_monitor.get_stats()
        return JSONResponse(content=stats)
    else:
        return JSONResponse(
            status_code=503,
            content={"error": "Performance monitor not initialized"}
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
    trace_id = getattr(req.state, "trace_id", "")
    
    # Log extraction request start
    log_extraction_request(
        request_id=request_id,
        status="started",
        context={
            "region_type": request.region_type,
            "has_custom_prompt": bool(request.prompt)
        },
        trace_id=trace_id
    )
    
    if not _inference_ready():
        # Log stub process failure with structured logging
        gpu_stats = None
        if gpu_monitor and gpu_monitor.gpu_available:
            gpu_stats = gpu_monitor.get_memory_stats()
        
        uptime = int(time.time() - service_start_time)
        
        error = RuntimeError("Model not initialized or unavailable - possible Triton stub process crash")
        log_model_unavailable_error(
            error=error,
            request_id=request_id,
            gpu_stats=gpu_stats,
            uptime_seconds=uptime
        )
        
        raise HTTPException(
            status_code=503,
            detail="Service temporarily unavailable - model restart in progress",
            headers={"Retry-After": "30"}
        )
    
    # Check GPU memory availability
    if gpu_monitor and gpu_monitor.gpu_available:
        required_gb = 2.0
        if settings.low_vram_mode:
            required_gb = 1.2

        if not gpu_monitor.has_sufficient_memory(required_gb=required_gb):
            stats = gpu_monitor.get_memory_stats()
            logger.warning(
                f"Insufficient GPU memory: {stats.get('free_gb', 0):.2f}GB available, "
                f"{required_gb:.1f}GB required [request_id={request_id}]"
            )
            raise HTTPException(
                status_code=503,
                detail=f"Insufficient GPU memory. Available: {stats.get('free_gb', 0):.2f}GB, Required: {required_gb:.1f}GB",
                headers={"Retry-After": "60"}
            )
        
        # Log GPU memory before inference
        gpu_monitor.log_memory_usage(f"before inference [request_id={request_id}]")
    
    start_time = time.time()
    
    try:
        # Get prompt for region type
        prompt = get_prompt_for_region_type(
            request.region_type,
            request.prompt
        )
        
        # Get options
        options = request.options or {}
        max_tokens = int(options.get("max_tokens", settings.max_tokens_default))
        max_tokens = min(max_tokens, int(settings.max_tokens_limit))
        if settings.low_vram_mode and gpu_monitor and gpu_monitor.gpu_available:
            max_tokens = min(max_tokens, int(settings.low_vram_max_tokens))
        output_format = options.get("output_format", "text")
        
        # Parse extraction options
        extraction_opts = ExtractionOptions(
            granularity=options.get("granularity", "block"),
            output_format=output_format,
            include_coordinates=options.get("include_coordinates", True),
            include_confidence=options.get("include_confidence", True),
            fast_mode=options.get("fast_mode", False)
        )

        if extraction_opts.fast_mode:
            max_tokens = min(max_tokens, 512)
            logger.info(f"Fast mode enabled: max_tokens={max_tokens} [request_id={request_id}]")

        if settings.low_vram_mode and gpu_monitor and gpu_monitor.gpu_available:
            logger.info(
                f"Low-VRAM mode active: max_tokens={max_tokens}, "
                f"max_image_edge={settings.low_vram_max_image_edge} [request_id={request_id}]"
            )
        
        logger.info(f"Extracting region: type={request.region_type}, prompt={prompt[:50]}... [request_id={request_id}]")
        
        # Choose image source payload
        image_payload = request.image_path if request.image_path else request.image

        # Extract content
        content, confidence, prompt_tokens, completion_tokens = await _extract_with_timeout(
            image_base64=image_payload,
            prompt=prompt,
            max_tokens=max_tokens,
            output_format=output_format
        )

    except asyncio.TimeoutError:
        logger.error(
            f"Inference timeout after {settings.request_timeout_seconds}s [request_id={request_id}]"
        )
        extraction_requests_total.labels(endpoint='extract_region', status='timeout_error').inc()
        raise HTTPException(
            status_code=504,
            detail=f"Inference timeout after {settings.request_timeout_seconds}s",
            headers={"Retry-After": "10"}
        )
    
    except Exception as e:
        # Check if this is a CUDA out-of-memory error
        import torch
        if torch.cuda.is_available() and isinstance(e, (torch.cuda.OutOfMemoryError, RuntimeError)):
            error_str = str(e).lower()
            if "out of memory" in error_str or "cuda" in error_str:
                # Log GPU memory stats with structured error logging
                gpu_stats = None
                if gpu_monitor and gpu_monitor.gpu_available:
                    gpu_stats = gpu_monitor.get_memory_stats()
                    # Clear GPU cache to free memory
                    gpu_monitor.clear_cache()
                
                # Use structured error logging
                log_gpu_memory_error(
                    error=e,
                    request_id=request_id,
                    gpu_stats=gpu_stats,
                    document_size_mb=None,  # Not available at this level
                    batch_size=None,
                    retry_attempt=None
                )
                
                extraction_requests_total.labels(endpoint='extract_region', status='oom_error').inc()
                
                raise HTTPException(
                    status_code=503,
                    detail="Insufficient GPU memory to process request",
                    headers={"Retry-After": "60"}
                )
        
        # Re-raise other exceptions to be handled by existing error handlers
        raise
    
    try:
        
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        # Get GPU memory usage after inference
        gpu_memory_used = None
        if gpu_monitor and gpu_monitor.gpu_available:
            stats = gpu_monitor.get_memory_stats()
            gpu_memory_used = stats.get("allocated_gb")
            gpu_monitor.log_memory_usage(f"after inference [request_id={request_id}]")
            # Update Prometheus metrics
            update_gpu_metrics()
        
        # Process based on granularity and format
        word_boxes = None
        key_value_pairs = None
        bounding_boxes = None

        page_bbox = infer_page_bbox(image_payload)

        if extraction_opts.include_coordinates:
            if extraction_opts.fast_mode:
                bounding_boxes = build_line_bounding_boxes(content, page_bbox, confidence)
            else:
                bounding_boxes = [{
                    "text": content,
                    "bbox": page_bbox,
                    "confidence": confidence if extraction_opts.include_confidence else 1.0,
                    "type": request.region_type,
                }]

        if (not extraction_opts.fast_mode) and extraction_opts.granularity == "word" and word_extractor:
            words = word_extractor.extract_words(content, page_bbox, confidence)
            words = word_extractor.handle_hyphenated_words(words)
            words = word_extractor.sort_words_reading_order(words)
            
            if extraction_opts.include_coordinates:
                word_boxes = [
                    WordBoundingBox(
                        word=w.word,
                        bbox=w.bbox,
                        confidence=w.confidence if extraction_opts.include_confidence else 1.0
                    )
                    for w in words
                ]
        
        if (not extraction_opts.fast_mode) and extraction_opts.output_format == "key_value" and kv_extractor:
            pairs = kv_extractor.extract_key_values(content, page_bbox)
            pairs = kv_extractor.handle_multi_value_keys(pairs)
            
            if extraction_opts.include_coordinates:
                key_value_pairs = [
                    KeyValuePair(
                        key=p.key,
                        key_bbox=p.key_bbox,
                        value=p.value,
                        value_bbox=p.value_bbox,
                        confidence=p.confidence if extraction_opts.include_confidence else 1.0
                    )
                    for p in pairs
                ]
        
        # Record Prometheus metrics
        extraction_requests_total.labels(endpoint='extract_region', status='success').inc()
        extraction_duration_seconds.labels(endpoint='extract_region').observe(processing_time_ms / 1000.0)
        extraction_tokens_total.labels(type='prompt').inc(prompt_tokens)
        extraction_tokens_total.labels(type='completion').inc(completion_tokens)
        
        # Validate extraction results
        validation_warnings = None
        if validator and not extraction_opts.fast_mode:
            # Prepare result dict for validation
            result_dict = {
                'word_boxes': word_boxes,
                'key_value_pairs': key_value_pairs,
                'bounding_boxes': bounding_boxes
            }
            
            validation_summary = validator.validate_extraction_result(result_dict, page_bbox)
            
            # Include warnings in response if any
            if validation_summary['warnings']:
                validation_warnings = validation_summary['warnings']
                
                # Log validation warnings
                logger.warning(
                    f"Validation warnings: {len(validation_warnings)} issues found "
                    f"[request_id={request_id}]"
                )
                
                # Log if low confidence ratio is high
                low_conf_count = validation_summary['stats'].get('low_confidence_count', 0)
                total_elements = validation_summary['stats'].get('total_elements', 0)
                if total_elements > 0 and low_conf_count / total_elements > 0.2:
                    logger.warning(
                        f"High low-confidence ratio: {low_conf_count}/{total_elements} "
                        f"({low_conf_count/total_elements:.1%}) [request_id={request_id}]"
                    )
        
        logger.info(f"Region extraction completed: confidence={confidence:.2f}, time={processing_time_ms}ms [request_id={request_id}]")
        
        # Record performance metrics
        if performance_monitor:
            # Estimate page size (approximate from base64 image size)
            import sys
            page_size_bytes = sys.getsizeof(request.image)
            
            # Estimate complexity
            complexity_score = performance_monitor.estimate_complexity(
                page_size_bytes=page_size_bytes,
                text_length=len(content) if content else 0,
                has_tables=extraction_opts.output_format == "table",
                has_images=False  # Not available at this level
            )
            
            performance_monitor.record_operation(
                processing_time_ms=processing_time_ms,
                page_size_bytes=page_size_bytes,
                complexity_score=complexity_score,
                request_id=request_id
            )
        
        # Log extraction request completion
        log_extraction_request(
            request_id=request_id,
            status="completed",
            processing_time_ms=processing_time_ms,
            context={
                "confidence": confidence,
                "region_type": request.region_type,
                "output_format": extraction_opts.output_format,
                "granularity": extraction_opts.granularity,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "gpu_memory_used_gb": gpu_memory_used
            },
            trace_id=trace_id
        )
        
        return RegionExtractionResponse(
            content=content,
            confidence=confidence,
            processing_time_ms=processing_time_ms,
            tokens_used=TokenUsage(
                prompt=prompt_tokens,
                completion=completion_tokens
            ),
            gpu_memory_used_gb=gpu_memory_used,
            word_boxes=word_boxes,
            key_value_pairs=key_value_pairs,
            bounding_boxes=bounding_boxes,
            validation_warnings=validation_warnings
        )
        
    except ValueError as e:
        extraction_requests_total.labels(endpoint='extract_region', status='error').inc()
        
        # Log extraction request failure
        log_extraction_request(
            request_id=request_id,
            status="failed",
            processing_time_ms=int((time.time() - start_time) * 1000),
            context={
                "error_type": "VALIDATION_ERROR",
                "error_message": str(e)
            },
            trace_id=trace_id
        )
        
        logger.error(f"Validation error: {e} [request_id={request_id}]")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        extraction_requests_total.labels(endpoint='extract_region', status='error').inc()
        
        # Log extraction request failure
        log_extraction_request(
            request_id=request_id,
            status="failed",
            processing_time_ms=int((time.time() - start_time) * 1000),
            context={
                "error_type": "EXTRACTION_ERROR",
                "error_message": str(e)
            },
            trace_id=trace_id
        )
        
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
    trace_id = getattr(req.state, "trace_id", "")
    
    # Log batch extraction request start
    log_extraction_request(
        request_id=request_id,
        status="started",
        context={
            "batch_size": len(request.regions),
            "endpoint": "batch"
        },
        trace_id=trace_id
    )
    
    if not _inference_ready():
        # Log stub process failure with structured logging
        gpu_stats = None
        if gpu_monitor and gpu_monitor.gpu_available:
            gpu_stats = gpu_monitor.get_memory_stats()
        
        uptime = int(time.time() - service_start_time)
        
        error = RuntimeError("Model not initialized or unavailable for batch - possible Triton stub process crash")
        log_model_unavailable_error(
            error=error,
            request_id=request_id,
            gpu_stats=gpu_stats,
            uptime_seconds=uptime
        )
        
        raise HTTPException(
            status_code=503,
            detail="Service temporarily unavailable - model restart in progress",
            headers={"Retry-After": "30"}
        )
    
    # Get options early so resource checks can respect fast mode.
    options = request.options or {}
    fast_mode = bool(options.get("fast_mode", False))

    # Check GPU memory availability
    if gpu_monitor and gpu_monitor.gpu_available:
        required_gb = 2.0
        if settings.low_vram_mode:
            required_gb = 1.2
        if fast_mode:
            required_gb = min(required_gb, 1.0)

        if not gpu_monitor.has_sufficient_memory(required_gb=required_gb):
            stats = gpu_monitor.get_memory_stats()
            logger.warning(
                f"Insufficient GPU memory for batch: {stats.get('free_gb', 0):.2f}GB available, "
                f"{required_gb:.1f}GB required [request_id={request_id}]"
            )
            raise HTTPException(
                status_code=503,
                detail=f"Insufficient GPU memory. Available: {stats.get('free_gb', 0):.2f}GB, Required: {required_gb:.1f}GB",
                headers={"Retry-After": "60"}
            )
        
        # Log GPU memory before batch processing
        gpu_monitor.log_memory_usage(f"before batch [request_id={request_id}]")
    
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
    
    max_tokens = int(options.get("max_tokens", settings.max_tokens_default))
    max_tokens = min(max_tokens, int(settings.max_tokens_limit))
    if settings.low_vram_mode and gpu_monitor and gpu_monitor.gpu_available:
        max_tokens = min(max_tokens, int(settings.low_vram_max_tokens))

    if fast_mode:
        max_tokens = min(max_tokens, 512)
        logger.info(f"Fast mode enabled for batch: max_tokens={max_tokens} [request_id={request_id}]")

    output_format = options.get("output_format", "text")
    granularity = options.get("granularity", "block")
    include_coordinates = options.get("include_coordinates", True)
    include_confidence = options.get("include_confidence", True)
    
    # Process each region
    for region in request.regions:
        try:
            # Get prompt for region type
            prompt = get_prompt_for_region_type(
                region.region_type,
                region.prompt
            )
            
            # Choose image source payload
            image_payload = region.image_path if region.image_path else region.image

            # Extract content
            content, confidence, prompt_tokens, completion_tokens = await _extract_with_timeout(
                image_base64=image_payload,
                prompt=prompt,
                max_tokens=max_tokens,
                output_format=output_format
            )

        except asyncio.TimeoutError:
            logger.error(
                f"Batch inference timeout for region {region.region_id} after "
                f"{settings.request_timeout_seconds}s [request_id={request_id}]"
            )
            extraction_requests_total.labels(endpoint='extract_regions_batch', status='timeout_error').inc()
            raise HTTPException(
                status_code=504,
                detail=f"Batch inference timeout after {settings.request_timeout_seconds}s",
                headers={"Retry-After": "10"}
            )

        except Exception as e:
            # Check if this is a CUDA out-of-memory error
            import torch
            if torch.cuda.is_available() and isinstance(e, (torch.cuda.OutOfMemoryError, RuntimeError)):
                error_str = str(e).lower()
                if "out of memory" in error_str or "cuda" in error_str:
                    # Log GPU memory stats with structured error logging
                    gpu_stats = None
                    if gpu_monitor and gpu_monitor.gpu_available:
                        gpu_stats = gpu_monitor.get_memory_stats()
                        # Clear GPU cache to free memory
                        gpu_monitor.clear_cache()
                    
                    # Use structured error logging
                    log_gpu_memory_error(
                        error=e,
                        request_id=request_id,
                        gpu_stats=gpu_stats,
                        document_size_mb=None,
                        batch_size=len(request.regions),
                        retry_attempt=None
                    )
                    
                    # For batch processing, we fail the entire batch on OOM
                    extraction_requests_total.labels(endpoint='extract_regions_batch', status='oom_error').inc()
                    
                    raise HTTPException(
                        status_code=503,
                        detail="Insufficient GPU memory to process batch request",
                        headers={"Retry-After": "60"}
                    )
            
            logger.error(f"Failed to process region {region.region_id}: {e} [request_id={request_id}]")
            results.append(BatchRegionResult(
                region_id=region.region_id,
                content="",
                confidence=0.0,
                word_boxes=None,
                key_value_pairs=None,
                bounding_boxes=None,
                error=str(e)
            ))

        else:
            total_prompt_tokens += prompt_tokens
            total_completion_tokens += completion_tokens

            word_boxes = None
            key_value_pairs = None
            bounding_boxes = None

            page_bbox = infer_page_bbox(region.image)

            if include_coordinates:
                if fast_mode:
                    bounding_boxes = build_line_bounding_boxes(content, page_bbox, confidence)
                else:
                    bounding_boxes = [{
                        "text": content,
                        "bbox": page_bbox,
                        "confidence": confidence if include_confidence else 1.0,
                        "type": region.region_type,
                    }]

            if (not fast_mode) and granularity == "word" and word_extractor:
                words = word_extractor.extract_words(content, page_bbox, confidence)
                words = word_extractor.handle_hyphenated_words(words)
                words = word_extractor.sort_words_reading_order(words)

                if include_coordinates:
                    word_boxes = [
                        WordBoundingBox(
                            word=w.word,
                            bbox=w.bbox,
                            confidence=w.confidence if include_confidence else 1.0,
                        )
                        for w in words
                    ]

            if (not fast_mode) and output_format == "key_value" and kv_extractor:
                pairs = kv_extractor.extract_key_values(content, page_bbox)
                pairs = kv_extractor.handle_multi_value_keys(pairs)

                if include_coordinates:
                    key_value_pairs = [
                        KeyValuePair(
                            key=p.key,
                            key_bbox=p.key_bbox,
                            value=p.value,
                            value_bbox=p.value_bbox,
                            confidence=p.confidence if include_confidence else 1.0,
                        )
                        for p in pairs
                    ]

            results.append(BatchRegionResult(
                region_id=region.region_id,
                content=content,
                confidence=confidence,
                word_boxes=word_boxes,
                key_value_pairs=key_value_pairs,
                bounding_boxes=bounding_boxes,
                error=None
            ))

            logger.info(f"Region {region.region_id} processed successfully [request_id={request_id}]")
    
    total_processing_time_ms = int((time.time() - start_time) * 1000)
    
    # Get GPU memory usage after batch processing
    gpu_memory_used = None
    if gpu_monitor and gpu_monitor.gpu_available:
        stats = gpu_monitor.get_memory_stats()
        gpu_memory_used = stats.get("allocated_gb")
        gpu_monitor.log_memory_usage(f"after batch [request_id={request_id}]")
        # Update Prometheus metrics
        update_gpu_metrics()
    
    # Record Prometheus metrics
    extraction_requests_total.labels(endpoint='extract_regions_batch', status='success').inc()
    extraction_duration_seconds.labels(endpoint='extract_regions_batch').observe(total_processing_time_ms / 1000.0)
    extraction_tokens_total.labels(type='prompt').inc(total_prompt_tokens)
    extraction_tokens_total.labels(type='completion').inc(total_completion_tokens)
    
    logger.info(f"Batch processing completed: {len(results)} regions, time={total_processing_time_ms}ms [request_id={request_id}]")
    
    # Record performance metrics for batch
    if performance_monitor:
        # Calculate average per-region processing time
        avg_time_per_region = total_processing_time_ms / len(results) if results else 0
        
        # Estimate batch size
        import sys
        batch_size_bytes = sum(sys.getsizeof(r.image) for r in request.regions)
        
        performance_monitor.record_operation(
            processing_time_ms=total_processing_time_ms,
            page_size_bytes=batch_size_bytes,
            complexity_score=None,  # Not calculated for batch
            request_id=request_id
        )
    
    # Log batch extraction request completion
    log_extraction_request(
        request_id=request_id,
        status="completed",
        processing_time_ms=total_processing_time_ms,
        context={
            "batch_size": len(results),
            "endpoint": "batch",
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "gpu_memory_used_gb": gpu_memory_used,
            "successful_regions": sum(1 for r in results if not r.error),
            "failed_regions": sum(1 for r in results if r.error)
        },
        trace_id=trace_id
    )
    
    return BatchRegionExtractionResponse(
        results=results,
        total_processing_time_ms=total_processing_time_ms,
        tokens_used=TokenUsage(
            prompt=total_prompt_tokens,
            completion=total_completion_tokens
        ),
        gpu_memory_used_gb=gpu_memory_used
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
