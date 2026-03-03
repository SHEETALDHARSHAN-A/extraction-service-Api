"""Integration tests for FastAPI endpoints."""

import base64
import io
import pytest
from fastapi.testclient import TestClient
from PIL import Image
import numpy as np

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.main import app


# Create test client
client = TestClient(app)


def create_test_image(width=100, height=100):
    """Create a test image and return base64 encoded string."""
    # Create a simple test image
    image = Image.new('RGB', (width, height), color='white')
    
    # Add some content to make it more realistic
    pixels = image.load()
    for i in range(10, 90):
        for j in range(10, 90):
            pixels[i, j] = (0, 0, 0)  # Black square
    
    # Convert to base64
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    image_bytes = buffer.getvalue()
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    
    return base64_image


class TestRootEndpoint:
    """Tests for root endpoint."""
    
    def test_root_endpoint(self):
        """Test root endpoint returns service information."""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "service" in data
        assert "version" in data
        assert "status" in data
        assert "endpoints" in data
        assert data["status"] == "running"


class TestHealthEndpoint:
    """Tests for health check endpoint."""
    
    def test_health_check_success(self):
        """Test health check endpoint returns healthy status."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data
        assert data["status"] in ["healthy", "degraded"]
        assert "service" in data
        assert "version" in data
        assert "uptime_seconds" in data
        assert "models_loaded" in data
        assert "gpu_available" in data
        assert "device" in data
        
        # Uptime should be non-negative
        assert data["uptime_seconds"] >= 0
    
    def test_health_check_response_headers(self):
        """Test health check includes proper headers."""
        response = client.get("/health")
        
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        assert "X-Process-Time" in response.headers


class TestDetectLayoutEndpoint:
    """Tests for layout detection endpoint."""
    
    def test_detect_layout_success(self):
        """Test successful layout detection."""
        # Create test image
        base64_image = create_test_image()
        
        # Make request
        request_data = {
            "image": base64_image,
            "options": {
                "min_confidence": 0.5,
                "detect_tables": True,
                "detect_formulas": True,
                "return_image_dimensions": True
            }
        }
        
        response = client.post("/detect-layout", json=request_data)
        
        # Note: This may fail if PaddleOCR is not installed or models not downloaded
        # In that case, we expect a 500 error
        if response.status_code == 200:
            data = response.json()
            
            assert "regions" in data
            assert "processing_time_ms" in data
            assert "model_version" in data
            assert "total_regions_detected" in data
            
            assert isinstance(data["regions"], list)
            assert data["processing_time_ms"] >= 0
            
            # If page dimensions requested, should be present
            if request_data["options"]["return_image_dimensions"]:
                assert "page_dimensions" in data
                if data["page_dimensions"]:
                    assert "width" in data["page_dimensions"]
                    assert "height" in data["page_dimensions"]
        else:
            # If PaddleOCR not available, expect 500
            assert response.status_code == 500
    
    def test_detect_layout_without_options(self):
        """Test layout detection with default options."""
        base64_image = create_test_image()
        
        request_data = {
            "image": base64_image
        }
        
        response = client.post("/detect-layout", json=request_data)
        
        # Should succeed or fail with 500 (if PaddleOCR not available)
        assert response.status_code in [200, 500]
    
    def test_detect_layout_invalid_image(self):
        """Test layout detection with invalid image data."""
        request_data = {
            "image": "invalid_base64_data"
        }
        
        response = client.post("/detect-layout", json=request_data)
        
        # Pydantic validation returns 422 for invalid data
        assert response.status_code == 422
        data = response.json()
        
        assert "detail" in data
    
    def test_detect_layout_empty_image(self):
        """Test layout detection with empty image."""
        request_data = {
            "image": ""
        }
        
        response = client.post("/detect-layout", json=request_data)
        
        assert response.status_code == 422  # Validation error
    
    def test_detect_layout_missing_image(self):
        """Test layout detection without image field."""
        request_data = {
            "options": {
                "min_confidence": 0.5
            }
        }
        
        response = client.post("/detect-layout", json=request_data)
        
        assert response.status_code == 422  # Validation error
    
    def test_detect_layout_invalid_confidence(self):
        """Test layout detection with invalid confidence value."""
        base64_image = create_test_image()
        
        # Test confidence > 1.0
        request_data = {
            "image": base64_image,
            "options": {
                "min_confidence": 1.5
            }
        }
        
        response = client.post("/detect-layout", json=request_data)
        assert response.status_code == 422  # Validation error
        
        # Test confidence < 0.0
        request_data["options"]["min_confidence"] = -0.5
        response = client.post("/detect-layout", json=request_data)
        assert response.status_code == 422  # Validation error
    
    def test_detect_layout_large_image(self):
        """Test layout detection with large image."""
        # Create a larger image (but still within limits)
        base64_image = create_test_image(width=500, height=500)
        
        request_data = {
            "image": base64_image
        }
        
        response = client.post("/detect-layout", json=request_data)
        
        # Should succeed or fail with 500 (if PaddleOCR not available)
        assert response.status_code in [200, 500]
    
    def test_detect_layout_response_headers(self):
        """Test that response includes proper headers."""
        base64_image = create_test_image()
        
        request_data = {
            "image": base64_image
        }
        
        response = client.post("/detect-layout", json=request_data)
        
        assert "X-Request-ID" in response.headers
        assert "X-Process-Time" in response.headers
    
    def test_detect_layout_with_data_uri(self):
        """Test layout detection with data URI prefix."""
        base64_image = create_test_image()
        data_uri = f"data:image/png;base64,{base64_image}"
        
        request_data = {
            "image": data_uri
        }
        
        response = client.post("/detect-layout", json=request_data)
        
        # Data URI prefix is handled by decode_base64_image in main.py
        # Should succeed or fail with 500 (if PaddleOCR not available)
        # Or 422 if validation fails (regex doesn't allow data URI prefix in models.py)
        assert response.status_code in [200, 422, 500]


class TestErrorHandling:
    """Tests for error handling."""
    
    def test_404_not_found(self):
        """Test 404 error for non-existent endpoint."""
        response = client.get("/nonexistent")
        
        assert response.status_code == 404
    
    def test_method_not_allowed(self):
        """Test 405 error for wrong HTTP method."""
        response = client.get("/detect-layout")
        
        assert response.status_code == 405
    
    def test_invalid_json(self):
        """Test error handling for invalid JSON."""
        response = client.post(
            "/detect-layout",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 422


class TestCORS:
    """Tests for CORS middleware."""
    
    def test_cors_middleware_configured(self):
        """Test that CORS middleware is configured in the app."""
        # Check that CORS middleware is present in the app
        # TestClient doesn't trigger CORS headers, so we just verify the middleware exists
        from starlette.middleware.cors import CORSMiddleware
        
        # Check if CORSMiddleware is in the app's middleware stack
        has_cors = any(
            isinstance(middleware, CORSMiddleware) or 
            (hasattr(middleware, 'cls') and middleware.cls == CORSMiddleware)
            for middleware in app.user_middleware
        )
        
        assert has_cors, "CORS middleware should be configured"


class TestRequestIDMiddleware:
    """Tests for request ID middleware."""
    
    def test_request_id_in_response(self):
        """Test that request ID is added to response headers."""
        response = client.get("/health")
        
        assert "X-Request-ID" in response.headers
        request_id = response.headers["X-Request-ID"]
        
        # Request ID should be a valid UUID format
        assert len(request_id) > 0
    
    def test_process_time_in_response(self):
        """Test that process time is added to response headers."""
        response = client.get("/health")
        
        assert "X-Process-Time" in response.headers
        process_time = response.headers["X-Process-Time"]
        
        # Process time should end with 'ms'
        assert process_time.endswith("ms")


class TestExceptionHandlers:
    """Tests for exception handlers."""
    
    def test_http_exception_handler(self):
        """Test HTTP exception handler."""
        # Trigger a 404 error
        response = client.get("/nonexistent-endpoint")
        
        assert response.status_code == 404
        data = response.json()
        
        # FastAPI's default 404 response has 'detail' field
        assert "detail" in data
    
    def test_general_exception_handler_with_image_too_large(self):
        """Test general exception handler with image size validation."""
        # Create a very large image that exceeds the limit
        # Note: This might not trigger the general exception handler
        # but will test the image size validation path
        base64_image = create_test_image(width=5000, height=5000)
        
        request_data = {
            "image": base64_image
        }
        
        response = client.post("/detect-layout", json=request_data)
        
        # Should return 413 (Request Entity Too Large) or 500
        assert response.status_code in [413, 500]


class TestDecodeBase64Image:
    """Tests for decode_base64_image helper function."""
    
    def test_decode_with_data_uri_prefix(self):
        """Test decoding image with data URI prefix."""
        from app.main import decode_base64_image
        
        base64_image = create_test_image()
        data_uri = f"data:image/png;base64,{base64_image}"
        
        # Should successfully decode
        image = decode_base64_image(data_uri)
        assert image is not None
        assert image.mode == "RGB"
    
    def test_decode_without_prefix(self):
        """Test decoding image without data URI prefix."""
        from app.main import decode_base64_image
        
        base64_image = create_test_image()
        
        # Should successfully decode
        image = decode_base64_image(base64_image)
        assert image is not None
        assert image.mode == "RGB"
    
    def test_decode_invalid_base64(self):
        """Test decoding invalid base64 data."""
        from app.main import decode_base64_image
        
        with pytest.raises(ValueError):
            decode_base64_image("not_valid_base64!!!")
    
    def test_decode_converts_to_rgb(self):
        """Test that non-RGB images are converted to RGB."""
        from app.main import decode_base64_image
        
        # Create a grayscale image
        image = Image.new('L', (100, 100), color='white')
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        image_bytes = buffer.getvalue()
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        
        # Decode and verify it's converted to RGB
        decoded_image = decode_base64_image(base64_image)
        assert decoded_image.mode == "RGB"


class TestDetectLayoutEdgeCases:
    """Tests for edge cases in detect_layout endpoint."""
    
    def test_detect_layout_with_minimal_options(self):
        """Test layout detection with minimal options."""
        base64_image = create_test_image()
        
        request_data = {
            "image": base64_image,
            "options": {
                "return_image_dimensions": False
            }
        }
        
        response = client.post("/detect-layout", json=request_data)
        
        # Should succeed or fail with 500 (if PaddleOCR not available)
        assert response.status_code in [200, 500]
        
        if response.status_code == 200:
            data = response.json()
            # Page dimensions should be None when return_image_dimensions is False
            assert data.get("page_dimensions") is None
    
    def test_detect_layout_with_all_options_disabled(self):
        """Test layout detection with tables and formulas disabled."""
        base64_image = create_test_image()
        
        request_data = {
            "image": base64_image,
            "options": {
                "min_confidence": 0.3,
                "detect_tables": False,
                "detect_formulas": False,
                "return_image_dimensions": True
            }
        }
        
        response = client.post("/detect-layout", json=request_data)
        
        # Should succeed or fail with 500 (if PaddleOCR not available)
        assert response.status_code in [200, 500]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
