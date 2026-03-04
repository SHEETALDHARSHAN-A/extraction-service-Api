"""GPU memory monitoring module for GLM-OCR service."""

import logging
from typing import Dict, Optional
import torch

logger = logging.getLogger(__name__)


class GPUMonitor:
    """Monitors GPU memory usage and availability."""
    
    def __init__(self):
        """Initialize GPU monitor."""
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.gpu_available = torch.cuda.is_available()
        
        if self.gpu_available:
            logger.info(f"GPU monitor initialized on device: {torch.cuda.get_device_name(0)}")
            logger.info(f"Total GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB")
        else:
            logger.warning("GPU not available, running on CPU")
    
    def get_memory_stats(self) -> Dict[str, float]:
        """
        Returns current GPU memory statistics.
        
        Returns:
            Dictionary with memory statistics in GB:
            - allocated_gb: Currently allocated memory
            - reserved_gb: Reserved memory by PyTorch
            - max_allocated_gb: Maximum allocated memory since last reset
            - total_gb: Total GPU memory
            - free_gb: Available free memory
        """
        if not self.gpu_available:
            return {}
        
        try:
            allocated = torch.cuda.memory_allocated() / 1e9
            reserved = torch.cuda.memory_reserved() / 1e9
            max_allocated = torch.cuda.max_memory_allocated() / 1e9
            total = torch.cuda.get_device_properties(0).total_memory / 1e9
            free = total - allocated
            
            return {
                "allocated_gb": round(allocated, 3),
                "reserved_gb": round(reserved, 3),
                "max_allocated_gb": round(max_allocated, 3),
                "total_gb": round(total, 3),
                "free_gb": round(free, 3),
            }
        except Exception as e:
            logger.error(f"Failed to get GPU memory stats: {e}")
            return {}
    
    def has_sufficient_memory(self, required_gb: float = 2.0) -> bool:
        """
        Checks if sufficient GPU memory is available.
        
        Args:
            required_gb: Minimum required free memory in GB (default: 2.0)
        
        Returns:
            True if sufficient memory is available, False otherwise
        """
        if not self.gpu_available:
            return False
        
        stats = self.get_memory_stats()
        free_memory = stats.get("free_gb", 0)
        
        return free_memory >= required_gb
    
    def clear_cache(self):
        """Clears GPU cache to free memory."""
        if self.gpu_available:
            try:
                torch.cuda.empty_cache()
                logger.info("GPU cache cleared")
            except Exception as e:
                logger.error(f"Failed to clear GPU cache: {e}")
    
    def log_memory_usage(self, context: str = ""):
        """
        Logs current GPU memory usage.
        
        Args:
            context: Optional context string to include in log message
        """
        if not self.gpu_available:
            return
        
        stats = self.get_memory_stats()
        context_str = f" [{context}]" if context else ""
        
        logger.info(
            f"GPU memory{context_str}: "
            f"allocated={stats['allocated_gb']:.2f}GB, "
            f"free={stats['free_gb']:.2f}GB, "
            f"total={stats['total_gb']:.2f}GB"
        )
    
    def get_utilization_percent(self) -> Optional[float]:
        """
        Returns GPU memory utilization as a percentage.
        
        Returns:
            Utilization percentage (0-100) or None if GPU not available
        """
        if not self.gpu_available:
            return None
        
        stats = self.get_memory_stats()
        total = stats.get("total_gb", 0)
        allocated = stats.get("allocated_gb", 0)
        
        if total == 0:
            return None
        
        return round((allocated / total) * 100, 2)
