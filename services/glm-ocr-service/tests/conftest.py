"""Pytest configuration and fixtures."""

import pytest
from unittest.mock import Mock


@pytest.fixture(scope="session")
def mock_inference_engine():
    """Create a mock inference engine for testing."""
    mock = Mock()
    mock.is_ready.return_value = True
    mock.device = "cpu"
    mock.extract_content.return_value = ("Extracted content", 0.95, 100, 200)
    mock.cleanup = Mock()
    return mock
