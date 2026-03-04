"""Distributed tracing with Jaeger."""

import logging
from typing import Optional
from jaeger_client import Config
from opentracing import Tracer, Span
from opentracing.ext import tags
from opentracing.propagation import Format

logger = logging.getLogger(__name__)


def init_jaeger_tracer(service_name: str, jaeger_host: str = "localhost", jaeger_port: int = 6831) -> Optional[Tracer]:
    """
    Initialize Jaeger tracer.
    
    Args:
        service_name: Name of the service
        jaeger_host: Jaeger agent host
        jaeger_port: Jaeger agent port
    
    Returns:
        Tracer instance or None if initialization fails
    """
    try:
        config = Config(
            config={
                'sampler': {
                    'type': 'const',
                    'param': 1,  # Sample all traces
                },
                'local_agent': {
                    'reporting_host': jaeger_host,
                    'reporting_port': jaeger_port,
                },
                'logging': True,
            },
            service_name=service_name,
            validate=True,
        )
        
        tracer = config.initialize_tracer()
        logger.info(f"Jaeger tracer initialized for service: {service_name}")
        return tracer
    except Exception as e:
        logger.error(f"Failed to initialize Jaeger tracer: {e}")
        return None


def extract_span_context(tracer: Tracer, headers: dict):
    """
    Extract span context from HTTP headers.
    
    Args:
        tracer: Tracer instance
        headers: HTTP headers dictionary
    
    Returns:
        Span context or None
    """
    try:
        span_ctx = tracer.extract(Format.HTTP_HEADERS, headers)
        return span_ctx
    except Exception as e:
        logger.debug(f"Failed to extract span context: {e}")
        return None


def start_span(tracer: Tracer, operation_name: str, parent_span_context=None) -> Optional[Span]:
    """
    Start a new span.
    
    Args:
        tracer: Tracer instance
        operation_name: Name of the operation
        parent_span_context: Parent span context
    
    Returns:
        Span instance or None
    """
    if not tracer:
        return None
    
    try:
        if parent_span_context:
            span = tracer.start_span(
                operation_name=operation_name,
                child_of=parent_span_context
            )
        else:
            span = tracer.start_span(operation_name=operation_name)
        
        return span
    except Exception as e:
        logger.error(f"Failed to start span: {e}")
        return None


def set_span_tag(span: Optional[Span], key: str, value):
    """
    Set a tag on the span.
    
    Args:
        span: Span instance
        key: Tag key
        value: Tag value
    """
    if span:
        try:
            span.set_tag(key, value)
        except Exception as e:
            logger.debug(f"Failed to set span tag: {e}")


def log_span_error(span: Optional[Span], error: Exception):
    """
    Log an error to the span.
    
    Args:
        span: Span instance
        error: Exception that occurred
    """
    if span:
        try:
            span.set_tag(tags.ERROR, True)
            span.log_kv({
                'event': 'error',
                'error.object': error,
                'message': str(error),
            })
        except Exception as e:
            logger.debug(f"Failed to log span error: {e}")


def finish_span(span: Optional[Span]):
    """
    Finish a span.
    
    Args:
        span: Span instance
    """
    if span:
        try:
            span.finish()
        except Exception as e:
            logger.debug(f"Failed to finish span: {e}")


def get_trace_id(span: Optional[Span]) -> str:
    """
    Get trace ID from span.
    
    Args:
        span: Span instance
    
    Returns:
        Trace ID as string or empty string
    """
    if not span:
        return ""
    
    try:
        span_context = span.context
        if hasattr(span_context, 'trace_id'):
            return format(span_context.trace_id, 'x')
        return ""
    except Exception as e:
        logger.debug(f"Failed to get trace ID: {e}")
        return ""
