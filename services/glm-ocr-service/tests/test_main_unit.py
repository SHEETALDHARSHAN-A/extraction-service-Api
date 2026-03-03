"""Unit tests for GLM-OCR Service main module with mocked inference engine."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
import base64
from io import BytesIO
from PIL import Image


def create_test_image_base64():
    """Create a test image and return as base64."""
    img = Image.new('RGB', (100, 100), color='white')
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    img_bytes = buffer.getvalue()
    return base64.b64encode(img_bytes).decode('utf-8')


@pytest.fixture
def mock_inference_engine():
    """Create mock inference engine."""
    mock_engine = MagicMock()
    mock_engine.is_ready.return_value = True
    mock_engine.device = "cpu"
    mock_engine.extract_content.return_value = ("Extracted text", 0.95, 100, 50)
    mock_engine.cleanup.return_value = None
    return mock_engine


@pytest.fixture
def client_with_mock(mock_inference_engine):
    """Create test client with mocked inference engine."""
    with patch('app.main.inference_engine', mock_inference_engine):
        from app.main import app
        client = TestClient(app)
        yield client


class TestExtractRegionWithMock:
    """Tests for /extract-region endpoint with mocked inference engine."""
    
    def test_extract_region_success(self, client_with_mock, mock_inference_engine):
        """Test successful region extraction with mock."""
        image_base64 = create_test_image_base64()
        
        request_data = {
            "image": image_base64,
            "region_type": "text",
            "prompt": "Text Recognition:",
            "options": {"max_tokens": 2048, "output_format": "text"}
        }
        
        response = client_with_mock.post("/extract-region", json=request_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["content"] == "Extracted text"
        assert data["confidence"] == 0.95
        assert "processing_time_ms" in data
        assert data["tokens_used"]["prompt"] == 100
        assert data["tokens_used"]["completion"] == 50
        
        # Verify inference engine was called
        mock_inference_engine.extract_content.assert_called_once()
    
    def test_extract_region_with_custom_prompt(self, client_with_mock, mock_inference_engine):
        """Test extraction with custom prompt."""
        image_base64 = create_test_image_base64()
        
        request_data = {
            "image": image_base64,
            "region_type": "text",
            "prompt": "Custom prompt:"
        }
        
        response = client_with_mock.post("/extract-region", json=request_data)
        assert response.status_code == 200
        
        # Verify custom prompt was used
        call_args = mock_inference_engine.extract_content.call_args
        assert call_args[1]["prompt"] == "Custom prompt:"
    
    def test_extract_region_max_tokens_limit(self, client_with_mock, mock_inference_engine):
        """Test that max_tokens is limited to configured maximum."""
        image_base64 = create_test_image_base64()
        
        request_data = {
            "image": image_base64,
            "region_type": "text",
            "options": {"max_tokens": 999999}  # Exceeds limit
        }
        
        response = client_with_mock.post("/extract-region", json=request_data)
        assert response.status_code == 200
        
        # Verify max_tokens was capped
        call_args = mock_inference_engine.extract_content.call_args
        assert call_args[1]["max_tokens"] <= 8192  # Default limit from config
    
    def test_extract_region_inference_error(self, client_with_mock, mock_inference_engine):
        """Test handling of inference engine errors."""
        image_base64 = create_test_image_base64()
        
        # Make inference engine raise an error
        mock_inference_engine.extract_content.side_effect = Exception("Inference failed")
        
        request_data = {
            "image": image_base64,
            "region_type": "text"
        }
        
        response = client_with_mock.post("/extract-region", json=request_data)
        assert response.status_code == 500
        assert "Extraction failed" in response.json()["detail"]
    
    def test_extract_region_validation_error(self, client_with_mock, mock_inference_engine):
        """Test handling of validation errors."""
        image_base64 = create_test_image_base64()
        
        # Make inference engine raise a ValueError
        mock_inference_engine.extract_content.side_effect = ValueError("Invalid image format")
        
        request_data = {
            "image": image_base64,
            "region_type": "text"
        }
        
        response = client_with_mock.post("/extract-region", json=request_data)
        assert response.status_code == 400
        assert "Invalid image format" in response.json()["detail"]


class TestBatchExtractionWithMock:
    """Tests for /extract-regions-batch endpoint with mocked inference engine."""
    
    def test_batch_extraction_success(self, client_with_mock, mock_inference_engine):
        ""