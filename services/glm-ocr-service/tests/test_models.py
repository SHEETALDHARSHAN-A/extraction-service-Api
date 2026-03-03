"""Tests for Pydantic models."""

import pytest
from pydantic import ValidationError

from app.models import (
    RegionExtractionRequest,
    BatchRegionRequest,
    BatchRegionExtractionRequest,
    TokenUsage,
    RegionExtractionResponse,
    BatchRegionResult,
    BatchRegionExtractionResponse,
    HealthResponse
)


class TestRegionExtractionRequest:
    """Tests for RegionExtractionRequest model."""
    
    def test_valid_request(self):
        """Test valid region extraction request."""
        request = RegionExtractionRequest(
            image="base64encodedimagedata",
            region_type="text",
            prompt="Text Recognition:",
            options={"max_tokens": 2048}
        )
        assert request.image == "base64encodedimagedata"
        assert request.region_type == "text"
        assert request.prompt == "Text Recognition:"
        assert request.options["max_tokens"] == 2048
    
    def test_invalid_region_type(self):
        """Test invalid region type."""
        with pytest.raises(ValidationError):
            RegionExtractionRequest(
                image="base64encodedimagedata",
                region_type="invalid_type",
                prompt="Text Recognition:"
            )
    
    def test_empty_image(self):
        """Test empty image."""
        with pytest.raises(ValidationError):
            RegionExtractionRequest(
                image="",
                region_type="text"
            )
    
    def test_region_type_normalization(self):
        """Test region type is normalized to lowercase."""
        request = RegionExtractionRequest(
            image="base64encodedimagedata",
            region_type="TEXT"
        )
        assert request.region_type == "text"


class TestBatchRegionExtractionRequest:
    """Tests for BatchRegionExtractionRequest model."""
    
    def test_valid_batch_request(self):
        """Test valid batch request."""
        request = BatchRegionExtractionRequest(
            regions=[
                BatchRegionRequest(
                    region_id="region_0",
                    image="base64data1",
                    region_type="text"
                ),
                BatchRegionRequest(
                    region_id="region_1",
                    image="base64data2",
                    region_type="table"
                )
            ],
            options={"max_tokens": 2048}
        )
        assert len(request.regions) == 2
        assert request.regions[0].region_id == "region_0"
        assert request.regions[1].region_type == "table"
    
    def test_empty_regions_list(self):
        """Test empty regions list."""
        with pytest.raises(ValidationError):
            BatchRegionExtractionRequest(regions=[])
    
    def test_too_many_regions(self):
        """Test too many regions."""
        regions = [
            BatchRegionRequest(
                region_id=f"region_{i}",
                image="base64data",
                region_type="text"
            )
            for i in range(51)
        ]
        with pytest.raises(ValidationError):
            BatchRegionExtractionRequest(regions=regions)


class TestRegionExtractionResponse:
    """Tests for RegionExtractionResponse model."""
    
    def test_valid_response(self):
        """Test valid response."""
        response = RegionExtractionResponse(
            content="Extracted text content",
            confidence=0.95,
            processing_time_ms=1500,
            tokens_used=TokenUsage(prompt=100, completion=200)
        )
        assert response.content == "Extracted text content"
        assert response.confidence == 0.95
        assert response.processing_time_ms == 1500
        assert response.tokens_used.prompt == 100
        assert response.tokens_used.completion == 200


class TestBatchRegionExtractionResponse:
    """Tests for BatchRegionExtractionResponse model."""
    
    def test_valid_batch_response(self):
        """Test valid batch response."""
        response = BatchRegionExtractionResponse(
            results=[
                BatchRegionResult(
                    region_id="region_0",
                    content="Content 1",
                    confidence=0.95
                ),
                BatchRegionResult(
                    region_id="region_1",
                    content="Content 2",
                    confidence=0.92
                )
            ],
            total_processing_time_ms=3000,
            tokens_used=TokenUsage(prompt=200, completion=400)
        )
        assert len(response.results) == 2
        assert response.total_processing_time_ms == 3000
        assert response.tokens_used.prompt == 200
    
    def test_batch_result_with_error(self):
        """Test batch result with error."""
        result = BatchRegionResult(
            region_id="region_0",
            content="",
            confidence=0.0,
            error="Processing failed"
        )
        assert result.error == "Processing failed"
        assert result.confidence == 0.0


class TestHealthResponse:
    """Tests for HealthResponse model."""
    
    def test_healthy_status(self):
        """Test healthy status."""
        response = HealthResponse(
            status="healthy",
            service="glm-ocr-service",
            version="1.0.0",
            uptime_seconds=3600,
            model_loaded=True,
            gpu_available=True,
            device="cuda"
        )
        assert response.status == "healthy"
        assert response.model_loaded is True
        assert response.gpu_available is True
        assert response.device == "cuda"
    
    def test_unhealthy_status(self):
        """Test unhealthy status."""
        response = HealthResponse(
            status="unhealthy",
            service="glm-ocr-service",
            version="1.0.0",
            uptime_seconds=100,
            model_loaded=False,
            gpu_available=False,
            device="cpu"
        )
        assert response.status == "unhealthy"
        assert response.model_loaded is False
