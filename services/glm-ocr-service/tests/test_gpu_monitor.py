"""Tests for GPU monitor module."""

import pytest
from app.gpu_monitor import GPUMonitor


def test_gpu_monitor_initialization():
    """Test GPU monitor can be initialized."""
    monitor = GPUMonitor()
    assert monitor is not None
    assert hasattr(monitor, 'device')
    assert hasattr(monitor, 'gpu_available')


def test_get_memory_stats():
    """Test getting memory statistics."""
    monitor = GPUMonitor()
    stats = monitor.get_memory_stats()
    
    # Should return dict (empty if no GPU, populated if GPU available)
    assert isinstance(stats, dict)
    
    if monitor.gpu_available:
        assert 'allocated_gb' in stats
        assert 'free_gb' in stats
        assert 'total_gb' in stats
        assert all(isinstance(v, float) for v in stats.values())


def test_has_sufficient_memory():
    """Test memory sufficiency check."""
    monitor = GPUMonitor()
    
    # Should return bool
    result = monitor.has_sufficient_memory(required_gb=2.0)
    assert isinstance(result, bool)
    
    # If no GPU, should return False
    if not monitor.gpu_available:
        assert result is False


def test_clear_cache():
    """Test cache clearing doesn't raise errors."""
    monitor = GPUMonitor()
    
    # Should not raise any exceptions
    monitor.clear_cache()


def test_log_memory_usage():
    """Test memory logging doesn't raise errors."""
    monitor = GPUMonitor()
    
    # Should not raise any exceptions
    monitor.log_memory_usage("test context")


def test_get_utilization_percent():
    """Test GPU utilization percentage."""
    monitor = GPUMonitor()
    utilization = monitor.get_utilization_percent()
    
    if monitor.gpu_available:
        assert isinstance(utilization, float)
        assert 0 <= utilization <= 100
    else:
        assert utilization is None
