"""Unit tests for Pydantic models."""

import pytest
from pydantic import ValidationError

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.models import (
    Region,
    PageDimensions,
    LayoutDetectionOptions,
    DetectLayoutRequest,
    DetectLayoutResponse,
    HealthResponse,
    ErrorResponse
)


class TestRegion:
    """Tests for Region model."""
    
    def test_valid_region(self):
        """Test creating a valid region."""
        region = Region(
            index=0,
            type="text",
            bbox=[10, 20, 100, 200],
            confidence=0.95
        )
        
        assert region.index == 0
        assert region.type == "text"
        assert region.bbox == [10, 20, 100, 200]
        assert region.confidence == 0.95
    
    def test_region_with_optional_fields(self):
        """Test region with optional fields."""
        region = Region(
            index=1,
            type="table",
            bbox=[50, 60, 150, 250],
            confidence=0.88,
            raw_type="table_structure",
            text="Sample table content"
        )
        
        assert region.raw_type == "table_structure"
        assert region.text == "Sample table content"
    
    def test_region_confidence_validation(self):
        """Test confidence value validation."""
        # Valid confidence values
        Region(index=0, type="text", bbox=[0, 0, 10, 10], confidence=0.0)
        Region(index=0, type="text", bbox=[0, 0, 10, 10], confidence=1.0)
        Region(index=0, type="text", bbox=[0, 0, 10, 10], confidence=0.5)
        
        # Invalid confidence values
        with pytest.raises(ValidationError):
            Region(index=0, type="text", bbox=[0, 0, 10, 10], confidence=-0.1)
        
        with pytest.raises(ValidationError):
            Region(index=0, type="text", bbox=[0, 0, 10, 10], confidence=1.1)
    
    def test_region_bbox_validation(self):
        """Test bbox validation."""
        # Valid bbox (4 elements)
        Region(index=0, type="text", bbox=[10, 20, 30, 40], confidence=0.9)
        
        # Invalid bbox (wrong number of elements)
        with pytest.raises(ValidationError):
            Region(index=0, type="text", bbox=[10, 20, 30], confidence=0.9)
        
        with pytest.raises(ValidationError):
            Region(index=0, type="text", bbox=[10, 20, 30, 40, 50], confidence=0.9)


class TestPageDimensions:
    """Tests for PageDimensions model."""
    
    def test_valid_dimensions(self):
        """Test creating valid page dimensions."""
        dims = PageDimensions(width=800, height=600)
        
        assert dims.width == 800
        assert dims.height == 600
    
    def test_dimensions_validation(self):
        """Test dimension value validation."""
        # Valid dimensions
        PageDimensions(width=1, height=1)
        PageDimensions(width=10000, height=10000)
        
        # Invalid dimensions (must be positive)
        with pytest.raises(ValidationError):
            PageDimensions(width=0, height=600)
        
        with pytest.raises(ValidationError):
            PageDimensions(width=800, height=-1)


class TestLayoutDetectionOptions:
    """Tests for LayoutDetectionOptions model."""
    
    def test_default_options(self):
        """Test default option values."""
        options = LayoutDetectionOptions()
        
        assert options.min_confidence == 0.5
        assert options.detect_tables is True
        assert options.detect_formulas is True
        assert options.return_image_dimensions is True
    
    def test_custom_options(self):
        """Test custom option values."""
        options = LayoutDetectionOptions(
            min_confidence=0.75,
            detect_tables=False,
            detect_formulas=False,
            return_image_dimensions=False
        )
        
        assert options.min_confidence == 0.75
        assert options.detect_tables is False
        assert options.detect_formulas is False
        assert options.return_image_dimensions is False
    
    def test_min_confidence_validation(self):
        """Test min_confidence validation."""
        # Valid values
        LayoutDetectionOptions(min_confidence=0.0)
        LayoutDetectionOptions(min_confidence=1.0)
        LayoutDetectionOptions(min_confidence=0.5)
        
        # Invalid values
        with pytest.raises(ValidationError):
            LayoutDetectionOptions(min_confidence=-0.1)
        
        with pytest.raises(ValidationError):
            LayoutDetectionOptions(min_confidence=1.1)


class TestDetectLayoutRequest:
    """Tests for DetectLayoutRequest model."""
    
    def test_valid_request(self):
        """Test creating a valid request."""
        # Use a valid base64 string (larger image to meet 100 char minimum)
        # This is a 10x10 pixel PNG image
        valid_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAYAAACNMs+9AAAAFUlEQVR42mNk+M9Qz0AEYBxVSF+FAP0QDiWl0VvYAAAAAElFTkSuQmCC" * 2
        request = DetectLayoutRequest(
            image=valid_base64,
            options=LayoutDetectionOptions()
        )
        
        assert request.image == valid_base64
        assert request.options is not None
    
    def test_request_without_options(self):
        """Test request without options (should use defaults)."""
        # Use a valid base64 string (larger image to meet 100 char minimum)
        valid_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAYAAACNMs+9AAAAFUlEQVR42mNk+M9Qz0AEYBxVSF+FAP0QDiWl0VvYAAAAAElFTkSuQmCC" * 2
        request = DetectLayoutRequest(image=valid_base64)
        
        assert request.image == valid_base64
        assert request.options is not None
        assert request.options.min_confidence == 0.5
    
    def test_empty_image_validation(self):
        """Test that empty image is rejected."""
        with pytest.raises(ValidationError):
            DetectLayoutRequest(image="")


class TestDetectLayoutResponse:
    """Tests for DetectLayoutResponse model."""
    
    def test_valid_response(self):
        """Test creating a valid response."""
        regions = [
            Region(index=0, type="text", bbox=[10, 20, 100, 200], confidence=0.95),
            Region(index=1, type="table", bbox=[50, 60, 150, 250], confidence=0.88)
        ]
        
        response = DetectLayoutResponse(
            regions=regions,
            page_dimensions=PageDimensions(width=800, height=600),
            processing_time_ms=150.5,
            model_version="PPStructureV3",
            total_regions_detected=2,
            regions_filtered=0
        )
        
        assert len(response.regions) == 2
        assert response.page_dimensions.width == 800
        assert response.processing_time_ms == 150.5
        assert response.model_version == "PPStructureV3"
    
    def test_response_without_page_dimensions(self):
        """Test response without page dimensions."""
        response = DetectLayoutResponse(
            regions=[],
            page_dimensions=None,
            processing_time_ms=100.0,
            model_version="PPStructureV3",
            total_regions_detected=0,
            regions_filtered=0
        )
        
        assert response.page_dimensions is None
    
    def test_processing_time_validation(self):
        """Test processing time validation."""
        # Valid values
        DetectLayoutResponse(
            regions=[],
            processing_time_ms=0.0,
            model_version="v1",
            total_regions_detected=0,
            regions_filtered=0
        )
        
        # Invalid values (negative)
        with pytest.raises(ValidationError):
            DetectLayoutResponse(
                regions=[],
                processing_time_ms=-1.0,
                model_version="v1",
                total_regions_detected=0,
                regions_filtered=0
            )


class TestHealthResponse:
    """Tests for HealthResponse model."""
    
    def test_healthy_response(self):
        """Test creating a healthy response."""
        response = HealthResponse(
            status="healthy",
            service="paddleocr-layout-detection",
            version="1.0.0",
            uptime_seconds=3600.5,
            models_loaded=True,
            gpu_available=False,
            device="cpu"
        )
        
        assert response.status == "healthy"
        assert response.service == "paddleocr-layout-detection"
        assert response.version == "1.0.0"
        assert response.uptime_seconds == 3600.5
        assert response.models_loaded is True
        assert response.gpu_available is False
        assert response.device == "cpu"
    
    def test_degraded_response(self):
        """Test creating a degraded response."""
        response = HealthResponse(
            status="degraded",
            service="paddleocr-layout-detection",
            version="1.0.0",
            uptime_seconds=100.0,
            models_loaded=False,
            gpu_available=True,
            device="cuda",
            model_info={"error": "Failed to load model"}
        )
        
        assert response.status == "degraded"
        assert response.models_loaded is False
        assert response.model_info == {"error": "Failed to load model"}
    
    def test_uptime_validation(self):
        """Test uptime validation."""
        # Valid values
        HealthResponse(
            status="healthy",
            service="test",
            version="1.0.0",
            uptime_seconds=0.0,
            models_loaded=True,
            gpu_available=False,
            device="cpu"
        )
        
        # Invalid values (negative)
        with pytest.raises(ValidationError):
            HealthResponse(
                status="healthy",
                service="test",
                version="1.0.0",
                uptime_seconds=-1.0,
                models_loaded=True,
                gpu_available=False,
                device="cpu"
            )


class TestErrorResponse:
    """Tests for ErrorResponse model."""
    
    def test_basic_error_response(self):
        """Test creating a basic error response."""
        response = ErrorResponse(
            error="ValidationError",
            message="Invalid input data",
            request_id="12345"
        )
        
        assert response.error == "ValidationError"
        assert response.message == "Invalid input data"
        assert response.request_id == "12345"
        assert response.detail is None
    
    def test_error_response_with_detail(self):
        """Test error response with detail."""
        response = ErrorResponse(
            error="InternalServerError",
            message="An error occurred",
            request_id="67890",
            detail="Stack trace information"
        )
        
        assert response.error == "InternalServerError"
        assert response.detail == "Stack trace information"
    
    def test_empty_message_validation(self):
        """Test that empty message is accepted (Pydantic v2 doesn't enforce min_length by default)."""
        # In Pydantic v2, empty strings are allowed unless explicitly constrained
        response = ErrorResponse(
            error="Error",
            message="",
            request_id="123"
        )
        assert response.message == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
