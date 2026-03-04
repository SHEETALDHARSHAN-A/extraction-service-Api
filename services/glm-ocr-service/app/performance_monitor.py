"""Performance monitoring and warnings for extraction operations."""

import time
import logging
from typing import Dict, Any, Optional
from collections import deque
from dataclasses import dataclass
import threading

logger = logging.getLogger(__name__)


@dataclass
class ProcessingMetrics:
    """Metrics for a single processing operation."""
    processing_time_ms: int
    page_size_bytes: Optional[int]
    complexity_score: Optional[float]
    timestamp: float


class PerformanceMonitor:
    """
    Monitor performance of extraction operations.
    
    Tracks processing times, logs warnings for slow operations,
    and maintains average processing time statistics.
    """
    
    def __init__(
        self,
        slow_page_threshold_ms: int = 30000,  # 30 seconds
        history_size: int = 1000
    ):
        """
        Initialize performance monitor.
        
        Args:
            slow_page_threshold_ms: Threshold for logging slow page warnings (milliseconds)
            history_size: Number of recent operations to keep for statistics
        """
        self.slow_page_threshold_ms = slow_page_threshold_ms
        self.history_size = history_size
        
        # Circular buffer for recent processing metrics
        self.metrics_history: deque[ProcessingMetrics] = deque(maxlen=history_size)
        self.lock = threading.RLock()
        
        # Statistics
        self.total_operations = 0
        self.slow_operations = 0
        self.total_processing_time_ms = 0
        
        logger.info(
            f"Performance monitor initialized: "
            f"slow_threshold={slow_page_threshold_ms}ms, "
            f"history_size={history_size}"
        )
    
    def record_operation(
        self,
        processing_time_ms: int,
        page_size_bytes: Optional[int] = None,
        complexity_score: Optional[float] = None,
        request_id: Optional[str] = None,
        page_number: Optional[int] = None
    ):
        """
        Record a processing operation and check for performance warnings.
        
        Args:
            processing_time_ms: Processing time in milliseconds
            page_size_bytes: Size of the page/document in bytes
            complexity_score: Complexity score (0.0-1.0, higher = more complex)
            request_id: Request ID for logging
            page_number: Page number if processing multi-page document
        """
        with self.lock:
            # Create metrics entry
            metrics = ProcessingMetrics(
                processing_time_ms=processing_time_ms,
                page_size_bytes=page_size_bytes,
                complexity_score=complexity_score,
                timestamp=time.time()
            )
            
            # Add to history
            self.metrics_history.append(metrics)
            
            # Update statistics
            self.total_operations += 1
            self.total_processing_time_ms += processing_time_ms
            
            # Check for slow operation
            if processing_time_ms > self.slow_page_threshold_ms:
                self.slow_operations += 1
                self._log_slow_operation_warning(
                    processing_time_ms=processing_time_ms,
                    page_size_bytes=page_size_bytes,
                    complexity_score=complexity_score,
                    request_id=request_id,
                    page_number=page_number
                )
    
    def _log_slow_operation_warning(
        self,
        processing_time_ms: int,
        page_size_bytes: Optional[int],
        complexity_score: Optional[float],
        request_id: Optional[str],
        page_number: Optional[int]
    ):
        """
        Log warning for slow operation with context.
        
        Args:
            processing_time_ms: Processing time in milliseconds
            page_size_bytes: Size of the page/document in bytes
            complexity_score: Complexity score
            request_id: Request ID
            page_number: Page number
        """
        context = {
            "processing_time_ms": processing_time_ms,
            "threshold_ms": self.slow_page_threshold_ms,
            "exceeded_by_ms": processing_time_ms - self.slow_page_threshold_ms,
            "exceeded_by_percent": round(
                ((processing_time_ms - self.slow_page_threshold_ms) / self.slow_page_threshold_ms) * 100,
                1
            )
        }
        
        if page_size_bytes is not None:
            context["page_size_bytes"] = page_size_bytes
            context["page_size_kb"] = round(page_size_bytes / 1024, 2)
            context["page_size_mb"] = round(page_size_bytes / (1024 * 1024), 2)
        
        if complexity_score is not None:
            context["complexity_score"] = round(complexity_score, 3)
            context["complexity_level"] = self._get_complexity_level(complexity_score)
        
        if request_id:
            context["request_id"] = request_id
        
        if page_number is not None:
            context["page_number"] = page_number
        
        # Build warning message
        message_parts = [
            f"Slow page processing detected: {processing_time_ms}ms "
            f"(threshold: {self.slow_page_threshold_ms}ms)"
        ]
        
        if page_size_bytes:
            message_parts.append(f"size={context['page_size_kb']}KB")
        
        if complexity_score is not None:
            message_parts.append(f"complexity={context['complexity_level']}")
        
        if page_number is not None:
            message_parts.append(f"page={page_number}")
        
        if request_id:
            message_parts.append(f"[request_id={request_id}]")
        
        message = ", ".join(message_parts)
        
        # Log with structured context
        log_record = logger.makeRecord(
            logger.name, logging.WARNING, "", 0,
            message, (), None
        )
        log_record.context = context
        logger.handle(log_record)
    
    def _get_complexity_level(self, complexity_score: float) -> str:
        """
        Get human-readable complexity level.
        
        Args:
            complexity_score: Complexity score (0.0-1.0)
        
        Returns:
            Complexity level string
        """
        if complexity_score < 0.3:
            return "low"
        elif complexity_score < 0.6:
            return "medium"
        elif complexity_score < 0.8:
            return "high"
        else:
            return "very_high"
    
    def get_average_processing_time(self, window_size: Optional[int] = None) -> float:
        """
        Get average processing time per page.
        
        Args:
            window_size: Number of recent operations to consider (None = all history)
        
        Returns:
            Average processing time in milliseconds
        """
        with self.lock:
            if not self.metrics_history:
                return 0.0
            
            if window_size is None:
                # Use all history
                total_time = sum(m.processing_time_ms for m in self.metrics_history)
                count = len(self.metrics_history)
            else:
                # Use recent window
                recent_metrics = list(self.metrics_history)[-window_size:]
                total_time = sum(m.processing_time_ms for m in recent_metrics)
                count = len(recent_metrics)
            
            return total_time / count if count > 0 else 0.0
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get performance statistics.
        
        Returns:
            Dictionary with performance statistics
        """
        with self.lock:
            avg_time_all = (
                self.total_processing_time_ms / self.total_operations
                if self.total_operations > 0 else 0.0
            )
            
            avg_time_recent = self.get_average_processing_time(window_size=100)
            
            slow_rate = (
                (self.slow_operations / self.total_operations * 100)
                if self.total_operations > 0 else 0.0
            )
            
            # Calculate percentiles from history
            if self.metrics_history:
                sorted_times = sorted(m.processing_time_ms for m in self.metrics_history)
                count = len(sorted_times)
                
                p50_idx = int(count * 0.5)
                p95_idx = int(count * 0.95)
                p99_idx = int(count * 0.99)
                
                p50 = sorted_times[p50_idx] if p50_idx < count else 0
                p95 = sorted_times[p95_idx] if p95_idx < count else 0
                p99 = sorted_times[p99_idx] if p99_idx < count else 0
            else:
                p50 = p95 = p99 = 0
            
            return {
                "total_operations": self.total_operations,
                "slow_operations": self.slow_operations,
                "slow_operation_rate_percent": round(slow_rate, 2),
                "slow_threshold_ms": self.slow_page_threshold_ms,
                "average_processing_time_ms": round(avg_time_all, 2),
                "average_processing_time_recent_100_ms": round(avg_time_recent, 2),
                "p50_processing_time_ms": p50,
                "p95_processing_time_ms": p95,
                "p99_processing_time_ms": p99,
                "history_size": len(self.metrics_history),
                "max_history_size": self.history_size
            }
    
    def log_stats(self):
        """Log performance statistics."""
        stats = self.get_stats()
        logger.info(
            f"Performance stats: "
            f"operations={stats['total_operations']}, "
            f"avg_time={stats['average_processing_time_ms']:.0f}ms, "
            f"p50={stats['p50_processing_time_ms']}ms, "
            f"p95={stats['p95_processing_time_ms']}ms, "
            f"p99={stats['p99_processing_time_ms']}ms, "
            f"slow_rate={stats['slow_operation_rate_percent']}%"
        )
    
    def estimate_complexity(
        self,
        page_size_bytes: int,
        text_length: Optional[int] = None,
        has_tables: bool = False,
        has_images: bool = False
    ) -> float:
        """
        Estimate page complexity score.
        
        Args:
            page_size_bytes: Size of the page in bytes
            text_length: Length of extracted text (if available)
            has_tables: Whether page contains tables
            has_images: Whether page contains images
        
        Returns:
            Complexity score (0.0-1.0)
        """
        complexity = 0.0
        
        # Size-based complexity (0-0.4)
        size_mb = page_size_bytes / (1024 * 1024)
        if size_mb < 0.5:
            complexity += 0.1
        elif size_mb < 1.0:
            complexity += 0.2
        elif size_mb < 2.0:
            complexity += 0.3
        else:
            complexity += 0.4
        
        # Text length complexity (0-0.3)
        if text_length is not None:
            if text_length < 500:
                complexity += 0.05
            elif text_length < 2000:
                complexity += 0.15
            elif text_length < 5000:
                complexity += 0.25
            else:
                complexity += 0.3
        
        # Structural complexity (0-0.3)
        if has_tables:
            complexity += 0.15
        if has_images:
            complexity += 0.15
        
        return min(complexity, 1.0)
