"""Integration tests for GLM-OCR service API."""

import pytest
import base64
from io import BytesIO
from PIL import Image
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from app.main import app
from app import main as main_module

# Mock the inference engine and GPU monitor before creating the test client
mock_inference_engine = Mock()
mock_inference_engine.is_ready.return_value = True
mock_inference_engine.device = "cpu"
mock_inference_engine.extract_content.return_value = ("Extracted content", 0.95, 100, 200)
mock_inference_engine.cleanup = Mock()

mock_gpu_monitor = Mock()
mock_gpu_monitor.gpu_available = False  # Disable GPU checks for tests
mock_gpu_monitor.has_sufficient_memory.return_value = True
mock_gpu_monitor.get_memory_stats.return_value = {"free_gb": 10.0}
mock_gpu_monitor.log_memory_usage = Mock()

# Patch the global variables
main_module.inference_engine = mock_inference_engine
main_module.gpu_monitor = mock_gpu_monitor

client = TestClient(app)


def create_test_image_base64():
    """Create a test image and return as base64."""
    img = Image.new('RGB', (100, 100), color='white')
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    img_bytes = buffer.getvalue()
    return base64.b64encode(img_bytes).decode('utf-8')


class TestHealthEndpoint:
    """Tests for /health endpoint."""
    
    def test_health_check(self):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "glm-ocr-service"
        assert "status" in data
        assert "uptime_seconds" in data
        assert "model_loaded" in data


class TestRootEndpoint:
    """Tests for root endpoint."""
    
    def test_root(self):
        """Test root endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "glm-ocr-service"
        assert "endpoints" in data


class TestExtractRegionEndpoint:
    """Tests for /extract-region endpoint."""
    
    def test_extract_region_success(self):
        """Test successful region extraction."""
        image_base64 = create_test_image_base64()
        
        request_data = {
            "image": image_base64,
            "region_type": "text",
            "prompt": "Text Recognition:",
            "options": {"max_tokens": 2048}
        }
        
        response = client.post("/extract-region", json=request_data)
        assert response.status_code == 200
        
        data = response.json()
        assert "content" in data
        assert "confidence" in data
        assert "processing_time_ms" in data
        assert "tokens_used" in data
        assert data["tokens_used"]["prompt"] == 100
        assert data["tokens_used"]["completion"] == 200
    
    def test_extract_region_invalid_type(self):
        """Test extraction with invalid region type."""
        image_base64 = create_test_image_base64()
        
        request_data = {
            "image": image_base64,
            "region_type": "invalid_type"
        }
        
        response = client.post("/extract-region", json=request_data)
        assert response.status_code == 422  # Validation error
    
    def test_extract_region_missing_image(self):
        """Test extraction without image."""
        request_data = {
            "region_type": "text"
        }
        
        response = client.post("/extract-region", json=request_data)
        assert response.status_code == 422  # Validation error
    
    def test_extract_region_table_type(self):
        """Test extraction with table region type."""
        image_base64 = create_test_image_base64()
        
        request_data = {
            "image": image_base64,
            "region_type": "table"
        }
        
        response = client.post("/extract-region", json=request_data)
        assert response.status_code == 200
        
        data = response.json()
        assert "content" in data
    
    def test_extract_region_formula_type(self):
        """Test extraction with formula region type."""
        image_base64 = create_test_image_base64()
        
        request_data = {
            "image": image_base64,
            "region_type": "formula"
        }
        
        response = client.post("/extract-region", json=request_data)
        assert response.status_code == 200


class TestExtractRegionsBatchEndpoint:
    """Tests for /extract-regions-batch endpoint."""
    
    def test_batch_extraction_success(self):
        """Test successful batch extraction."""
        image_base64 = create_test_image_base64()
        
        request_data = {
            "regions": [
                {
                    "region_id": "region_0",
                    "image": image_base64,
                    "region_type": "text"
                },
                {
                    "region_id": "region_1",
                    "image": image_base64,
                    "region_type": "table"
                }
            ],
            "options": {"max_tokens": 2048}
        }
        
        response = client.post("/extract-regions-batch", json=request_data)
        assert response.status_code == 200
        
        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 2
        assert data["results"][0]["region_id"] == "region_0"
        assert data["results"][1]["region_id"] == "region_1"
        assert "total_processing_time_ms" in data
        assert "tokens_used" in data
    
    def test_batch_extraction_empty_regions(self):
        """Test batch extraction with empty regions list."""
        request_data = {
            "regions": []
        }
        
        response = client.post("/extract-regions-batch", json=request_data)
        assert response.status_code == 422  # Validation error
    
    def test_batch_extraction_single_region(self):
        """Test batch extraction with single region."""
        image_base64 = create_test_image_base64()
        
        request_data = {
            "regions": [
                {
                    "region_id": "region_0",
                    "image": image_base64,
                    "region_type": "text"
                }
            ]
        }
        
        response = client.post("/extract-regions-batch", json=request_data)
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["results"]) == 1
    
    def test_batch_extraction_mixed_types(self):
        """Test batch extraction with mixed region types."""
        image_base64 = create_test_image_base64()
        
        request_data = {
            "regions": [
                {
                    "region_id": "region_0",
                    "image": image_base64,
                    "region_type": "text"
                },
                {
                    "region_id": "region_1",
                    "image": image_base64,
                    "region_type": "table"
                },
                {
                    "region_id": "region_2",
                    "image": image_base64,
                    "region_type": "formula"
                }
            ]
        }
        
        response = client.post("/extract-regions-batch", json=request_data)
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["results"]) == 3


class TestRequestHeaders:
    """Tests for request headers and middleware."""
    
    def test_request_id_header(self):
        """Test that request ID is added to response headers."""
        response = client.get("/health")
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) > 0
    
    def test_process_time_header(self):
        """Test that process time is added to response headers."""
        response = client.get("/health")
        assert "X-Process-Time" in response.headers
        assert "ms" in response.headers["X-Process-Time"]
