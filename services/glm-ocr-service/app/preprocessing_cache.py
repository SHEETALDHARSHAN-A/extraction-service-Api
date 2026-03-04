"""Preprocessing cache for storing preprocessed images with TTL."""

import time
import hashlib
import logging
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from collections import OrderedDict
import threading

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry with preprocessed data and metadata."""
    data: Any
    created_at: float
    last_accessed: float
    access_count: int
    size_bytes: int


class PreprocessingCache:
    """
    LRU cache for preprocessed images with TTL support.
    
    Caches preprocessed images to avoid redundant preprocessing for retry attempts.
    Uses LRU eviction policy when cache is full.
    """
    
    def __init__(self, max_size_mb: int = 500, ttl_seconds: int = 3600):
        """
        Initialize preprocessing cache.
        
        Args:
            max_size_mb: Maximum cache size in megabytes
            ttl_seconds: Time-to-live for cache entries in seconds (default: 1 hour)
        """
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.ttl_seconds = ttl_seconds
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.current_size_bytes = 0
        self.lock = threading.RLock()
        
        # Statistics
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        
        logger.info(f"Preprocessing cache initialized: max_size={max_size_mb}MB, ttl={ttl_seconds}s")
    
    def _generate_key(self, image_data: str, preprocessing_params: Dict[str, Any]) -> str:
        """
        Generate cache key from image data and preprocessing parameters.
        
        Args:
            image_data: Base64 encoded image data
            preprocessing_params: Preprocessing parameters (resize, normalize, etc.)
        
        Returns:
            Cache key (SHA256 hash)
        """
        # Create a unique key based on image data and preprocessing params
        key_data = f"{image_data}:{str(sorted(preprocessing_params.items()))}"
        return hashlib.sha256(key_data.encode()).hexdigest()
    
    def _is_expired(self, entry: CacheEntry) -> bool:
        """
        Check if cache entry has expired.
        
        Args:
            entry: Cache entry to check
        
        Returns:
            True if expired, False otherwise
        """
        return (time.time() - entry.created_at) > self.ttl_seconds
    
    def _evict_lru(self, required_bytes: int):
        """
        Evict least recently used entries to make space.
        
        Args:
            required_bytes: Number of bytes needed
        """
        while self.current_size_bytes + required_bytes > self.max_size_bytes and self.cache:
            # Remove oldest (least recently used) entry
            key, entry = self.cache.popitem(last=False)
            self.current_size_bytes -= entry.size_bytes
            self.evictions += 1
            logger.debug(f"Evicted cache entry: key={key[:16]}..., size={entry.size_bytes} bytes")
    
    def _cleanup_expired(self):
        """Remove expired entries from cache."""
        current_time = time.time()
        expired_keys = []
        
        for key, entry in self.cache.items():
            if self._is_expired(entry):
                expired_keys.append(key)
        
        for key in expired_keys:
            entry = self.cache.pop(key)
            self.current_size_bytes -= entry.size_bytes
            logger.debug(f"Removed expired cache entry: key={key[:16]}...")
    
    def get(
        self,
        image_data: str,
        preprocessing_params: Dict[str, Any]
    ) -> Optional[Any]:
        """
        Get preprocessed data from cache.
        
        Args:
            image_data: Base64 encoded image data
            preprocessing_params: Preprocessing parameters
        
        Returns:
            Cached preprocessed data if found and not expired, None otherwise
        """
        key = self._generate_key(image_data, preprocessing_params)
        
        with self.lock:
            # Cleanup expired entries periodically
            if len(self.cache) > 0 and self.misses % 10 == 0:
                self._cleanup_expired()
            
            if key in self.cache:
                entry = self.cache[key]
                
                # Check if expired
                if self._is_expired(entry):
                    self.cache.pop(key)
                    self.current_size_bytes -= entry.size_bytes
                    self.misses += 1
                    logger.debug(f"Cache miss (expired): key={key[:16]}...")
                    return None
                
                # Move to end (most recently used)
                self.cache.move_to_end(key)
                
                # Update access metadata
                entry.last_accessed = time.time()
                entry.access_count += 1
                
                self.hits += 1
                logger.debug(
                    f"Cache hit: key={key[:16]}..., "
                    f"age={time.time() - entry.created_at:.1f}s, "
                    f"access_count={entry.access_count}"
                )
                return entry.data
            else:
                self.misses += 1
                logger.debug(f"Cache miss: key={key[:16]}...")
                return None
    
    def put(
        self,
        image_data: str,
        preprocessing_params: Dict[str, Any],
        preprocessed_data: Any,
        size_bytes: int
    ):
        """
        Store preprocessed data in cache.
        
        Args:
            image_data: Base64 encoded image data
            preprocessing_params: Preprocessing parameters
            preprocessed_data: Preprocessed data to cache
            size_bytes: Size of preprocessed data in bytes
        """
        key = self._generate_key(image_data, preprocessing_params)
        
        with self.lock:
            # Check if we need to evict entries
            if size_bytes > self.max_size_bytes:
                logger.warning(
                    f"Preprocessed data too large for cache: "
                    f"{size_bytes} bytes > {self.max_size_bytes} bytes"
                )
                return
            
            # Evict LRU entries if needed
            self._evict_lru(size_bytes)
            
            # Create cache entry
            entry = CacheEntry(
                data=preprocessed_data,
                created_at=time.time(),
                last_accessed=time.time(),
                access_count=0,
                size_bytes=size_bytes
            )
            
            # Add to cache (or update if exists)
            if key in self.cache:
                old_entry = self.cache[key]
                self.current_size_bytes -= old_entry.size_bytes
            
            self.cache[key] = entry
            self.current_size_bytes += size_bytes
            
            logger.debug(
                f"Cached preprocessed data: key={key[:16]}..., "
                f"size={size_bytes} bytes, "
                f"cache_size={self.current_size_bytes}/{self.max_size_bytes} bytes"
            )
    
    def clear(self):
        """Clear all cache entries."""
        with self.lock:
            self.cache.clear()
            self.current_size_bytes = 0
            logger.info("Preprocessing cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        with self.lock:
            total_requests = self.hits + self.misses
            hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
            
            return {
                "entries": len(self.cache),
                "size_bytes": self.current_size_bytes,
                "size_mb": round(self.current_size_bytes / (1024 * 1024), 2),
                "max_size_mb": self.max_size_bytes / (1024 * 1024),
                "utilization_percent": round(
                    (self.current_size_bytes / self.max_size_bytes * 100), 2
                ) if self.max_size_bytes > 0 else 0,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate_percent": round(hit_rate, 2),
                "evictions": self.evictions,
                "ttl_seconds": self.ttl_seconds
            }
    
    def log_stats(self):
        """Log cache statistics."""
        stats = self.get_stats()
        logger.info(
            f"Preprocessing cache stats: "
            f"entries={stats['entries']}, "
            f"size={stats['size_mb']}MB/{stats['max_size_mb']}MB "
            f"({stats['utilization_percent']}%), "
            f"hit_rate={stats['hit_rate_percent']}%, "
            f"hits={stats['hits']}, "
            f"misses={stats['misses']}, "
            f"evictions={stats['evictions']}"
        )
