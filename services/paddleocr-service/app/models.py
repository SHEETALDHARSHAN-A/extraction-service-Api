"""Pydantic models for PaddleOCR Layout Detection Service."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict


class AppBaseModel(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


class Region(AppBaseModel):
    """Model for a detected document region."""
    
    index: int = Field(..., description="Sequential index of the region", ge=0)
    type: str = Field(..., description="Type of region (text, table, formula, etc.)")
    bbox: List[int] = Field(..., description="Bounding box coordinates [x1, y1, x2, y2]", min_length=4, max_length=4)
    confidence: float = Field(..., description="Confidence score for the detection", ge=0.0, le=1.0)
    raw_type: Optional[str] = Field(None, description="Original type from PPStructureV3")
    text: Optional[str] = Field(None, description="Extracted text content (if available)")
    
    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, v: List[int]) -> List[int]:
        """Validate bounding box coordinates."""
        if len(v) != 4:
            raise ValueError("bbox must contain exactly 4 coordinates [x1, y1, x2, y2]")
        
        x1, y1, x2, y2 = v
        
        # Ensure coordinates are non-negative
        if any(coord < 0 for coord in v):
            raise ValueError("bbox coordinates must be non-negative")
        
        # Ensure x2 > x1 and y2 > y1
        if x2 <= x1:
            raise ValueError(f"x2 ({x2}) must be greater than x1 ({x1})")
        if y2 <= y1:
            raise ValueError(f"y2 ({y2}) must be greater than y1 ({y1})")
        
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "index": 0,
                "type": "text",
                "bbox": [100, 50, 400, 80],
                "confidence": 0.95,
                "raw_type": "text",
                "text": "Sample text content"
            }
        }


class PageDimensions(AppBaseModel):
    """Model for page dimensions."""
    
    width: int = Field(..., description="Page width in pixels", gt=0)
    height: int = Field(..., description="Page height in pixels", gt=0)
    
    class Config:
        json_schema_extra = {
            "example": {
                "width": 800,
                "height": 600
            }
        }


class LayoutDetectionOptions(AppBaseModel):
    """Options for layout detection."""
    
    min_confidence: Optional[float] = Field(
        default=0.5,
        description="Minimum confidence threshold for region detection",
        ge=0.0,
        le=1.0
    )
    detect_tables: Optional[bool] = Field(
        default=True,
        description="Whether to detect table regions"
    )
    detect_formulas: Optional[bool] = Field(
        default=True,
        description="Whether to detect formula regions"
    )
    return_image_dimensions: Optional[bool] = Field(
        default=True,
        description="Whether to return page dimensions"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "min_confidence": 0.5,
                "detect_tables": True,
                "detect_formulas": True,
                "return_image_dimensions": True
            }
        }


class DetectLayoutRequest(AppBaseModel):
    """Request model for layout detection endpoint."""
    
    image: str = Field(..., description="Base64-encoded image data")
    options: Optional[LayoutDetectionOptions] = Field(
        default_factory=LayoutDetectionOptions,
        description="Detection options"
    )
    
    @field_validator("image")
    @classmethod
    def validate_image(cls, v: str) -> str:
        """Validate base64 image data."""
        if not v:
            raise ValueError("image field cannot be empty")
        
        # Check if it's a reasonable length (not too short, not too long)
        if len(v) < 100:
            raise ValueError("image data seems too short to be a valid image")
        
        # Optional: Check for base64 format (basic check)
        # Base64 should only contain A-Z, a-z, 0-9, +, /, and = for padding
        import re
        if not re.match(r'^[A-Za-z0-9+/]*={0,2}$', v):
            raise ValueError("image data does not appear to be valid base64")
        
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "image": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                "options": {
                    "min_confidence": 0.5,
                    "detect_tables": True,
                    "detect_formulas": True
                }
            }
        }


class DetectLayoutResponse(AppBaseModel):
    """Response model for layout detection endpoint."""
    
    regions: List[Region] = Field(..., description="List of detected regions")
    page_dimensions: Optional[PageDimensions] = Field(None, description="Page dimensions")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds", ge=0)
    model_version: str = Field(default="PPStructureV3", description="Model version used")
    total_regions_detected: int = Field(..., description="Total number of regions detected", ge=0)
    regions_filtered: int = Field(default=0, description="Number of regions filtered by confidence", ge=0)
    
    class Config:
        json_schema_extra = {
            "example": {
                "regions": [
                    {
                        "index": 0,
                        "type": "text",
                        "bbox": [100, 50, 400, 80],
                        "confidence": 0.95,
                        "raw_type": "text"
                    },
                    {
                        "index": 1,
                        "type": "table",
                        "bbox": [100, 100, 700, 400],
                        "confidence": 0.92,
                        "raw_type": "table"
                    }
                ],
                "page_dimensions": {
                    "width": 800,
                    "height": 600
                },
                "processing_time_ms": 150.5,
                "model_version": "PPStructureV3",
                "total_regions_detected": 3,
                "regions_filtered": 1
            }
        }


class HealthResponse(AppBaseModel):
    """Response model for health check endpoint."""
    
    status: str = Field(..., description="Service status (healthy, unhealthy, degraded)")
    service: str = Field(default="paddleocr-layout-detection", description="Service name")
    version: str = Field(..., description="Service version")
    uptime_seconds: float = Field(..., description="Service uptime in seconds", ge=0)
    models_loaded: bool = Field(..., description="Whether models are loaded")
    gpu_available: bool = Field(..., description="Whether GPU is available")
    device: str = Field(..., description="Device being used (cpu or cuda)")
    model_info: Optional[Dict[str, Any]] = Field(None, description="Additional model information")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "service": "paddleocr-layout-detection",
                "version": "1.0.0",
                "uptime_seconds": 3600.5,
                "models_loaded": True,
                "gpu_available": False,
                "device": "cpu",
                "model_info": {
                    "model": "PPStructureV3",
                    "initialized": True
                }
            }
        }


class ErrorResponse(AppBaseModel):
    """Response model for error responses."""
    
    error: str = Field(..., description="Error type or code")
    message: str = Field(..., description="Human-readable error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
    request_id: Optional[str] = Field(None, description="Request ID for tracking")
    
    class Config:
        json_schema_extra = {
            "example": {
                "error": "ValidationError",
                "message": "Invalid image format",
                "detail": "Image data does not appear to be valid base64",
                "request_id": "req_123456"
            }
        }
