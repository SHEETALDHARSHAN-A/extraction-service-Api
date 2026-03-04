"""Pydantic models for GLM-OCR service API."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator


class ExtractionOptions(BaseModel):
    """Options for extraction granularity and output format."""
    
    granularity: str = Field(
        default="block",
        description="Granularity level: block, line, or word"
    )
    output_format: str = Field(
        default="text",
        description="Output format: text, json, markdown, table, key_value, or structured"
    )
    include_coordinates: bool = Field(
        default=True,
        description="Include bounding box coordinates in output"
    )
    include_confidence: bool = Field(
        default=True,
        description="Include confidence scores in output"
    )
    
    @validator("granularity")
    def validate_granularity(cls, v):
        valid_levels = ["block", "line", "word"]
        if v.lower() not in valid_levels:
            raise ValueError(f"granularity must be one of {valid_levels}")
        return v.lower()
    
    @validator("output_format")
    def validate_output_format(cls, v):
        valid_formats = ["text", "json", "markdown", "table", "key_value", "structured"]
        if v.lower() not in valid_formats:
            raise ValueError(f"output_format must be one of {valid_formats}")
        return v.lower()


class RegionExtractionRequest(BaseModel):
    """Request model for single region extraction."""
    
    image: str = Field(..., description="Base64 encoded cropped region image")
    region_type: str = Field(..., description="Type of region: text, table, formula, title, figure")
    prompt: Optional[str] = Field(None, description="Custom prompt override")
    options: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Processing options")
    
    @validator("region_type")
    def validate_region_type(cls, v):
        valid_types = ["text", "table", "formula", "title", "figure", "caption", "header", "footer"]
        if v.lower() not in valid_types:
            raise ValueError(f"region_type must be one of {valid_types}")
        return v.lower()
    
    @validator("image")
    def validate_image(cls, v):
        if not v or len(v) < 10:
            raise ValueError("image must be a valid base64 encoded string")
        return v


class TokenUsage(BaseModel):
    """Token usage information."""
    
    prompt: int = Field(0, description="Number of prompt tokens")
    completion: int = Field(0, description="Number of completion tokens")


class WordBoundingBox(BaseModel):
    """Word-level bounding box."""
    
    word: str = Field(..., description="Word text")
    bbox: List[int] = Field(..., description="Bounding box [x, y, width, height]")
    confidence: float = Field(..., description="Confidence score")


class KeyValuePair(BaseModel):
    """Key-value pair with bounding boxes."""
    
    key: str = Field(..., description="Key text")
    key_bbox: List[int] = Field(..., description="Key bounding box [x, y, width, height]")
    value: str = Field(..., description="Value text")
    value_bbox: List[int] = Field(..., description="Value bounding box [x, y, width, height]")
    confidence: float = Field(..., description="Confidence score")


class RegionExtractionResponse(BaseModel):
    """Response model for single region extraction."""
    
    content: str = Field(..., description="Extracted content")
    confidence: float = Field(..., description="Confidence score")
    processing_time_ms: int = Field(..., description="Processing time in milliseconds")
    tokens_used: TokenUsage = Field(default_factory=TokenUsage, description="Token usage statistics")
    gpu_memory_used_gb: Optional[float] = Field(None, description="GPU memory used in GB")
    word_boxes: Optional[List[WordBoundingBox]] = Field(None, description="Word-level bounding boxes")
    key_value_pairs: Optional[List[KeyValuePair]] = Field(None, description="Key-value pairs with bounding boxes")
    bounding_boxes: Optional[List[Dict[str, Any]]] = Field(None, description="General bounding boxes for other granularities")
    validation_warnings: Optional[List[Dict[str, Any]]] = Field(None, description="Validation warnings for extraction results")


class BatchRegionRequest(BaseModel):
    """Single region in a batch request."""
    
    region_id: str = Field(..., description="Unique identifier for this region")
    image: str = Field(..., description="Base64 encoded cropped region image")
    region_type: str = Field(..., description="Type of region")
    prompt: Optional[str] = Field(None, description="Custom prompt override")
    
    @validator("region_type")
    def validate_region_type(cls, v):
        valid_types = ["text", "table", "formula", "title", "figure", "caption", "header", "footer"]
        if v.lower() not in valid_types:
            raise ValueError(f"region_type must be one of {valid_types}")
        return v.lower()


class BatchRegionExtractionRequest(BaseModel):
    """Request model for batch region extraction."""
    
    regions: List[BatchRegionRequest] = Field(..., description="List of regions to process")
    options: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Processing options")
    
    @validator("regions")
    def validate_regions(cls, v):
        if not v:
            raise ValueError("regions list cannot be empty")
        if len(v) > 50:  # Reasonable limit
            raise ValueError("regions list cannot exceed 50 items")
        return v


class BatchRegionResult(BaseModel):
    """Result for a single region in batch processing."""
    
    region_id: str = Field(..., description="Region identifier")
    content: str = Field(..., description="Extracted content")
    confidence: float = Field(..., description="Confidence score")
    error: Optional[str] = Field(None, description="Error message if processing failed")


class BatchRegionExtractionResponse(BaseModel):
    """Response model for batch region extraction."""
    
    results: List[BatchRegionResult] = Field(..., description="Results for each region")
    total_processing_time_ms: int = Field(..., description="Total processing time in milliseconds")
    tokens_used: TokenUsage = Field(default_factory=TokenUsage, description="Total token usage")
    gpu_memory_used_gb: Optional[float] = Field(None, description="GPU memory used in GB")


class HealthResponse(BaseModel):
    """Health check response."""
    
    status: str = Field(..., description="Service status: healthy, degraded, unhealthy")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    uptime_seconds: int = Field(..., description="Service uptime in seconds")
    model_loaded: bool = Field(..., description="Whether the model is loaded")
    gpu_available: bool = Field(..., description="Whether GPU is available")
    device: str = Field(..., description="Device being used: cuda or cpu")
    gpu_memory_stats: Optional[Dict[str, float]] = Field(None, description="GPU memory statistics")


class ErrorResponse(BaseModel):
    """Error response model."""
    
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
    request_id: Optional[str] = Field(None, description="Request ID for tracking")
