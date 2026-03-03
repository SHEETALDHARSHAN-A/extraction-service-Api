"""PPStructureV3 layout detector for document region detection."""

import logging
import time
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from PIL import Image

from .config import settings

logger = logging.getLogger(__name__)


class LayoutDetector:
    """Wrapper for PPStructureV3 layout detection model."""
    
    def __init__(self, use_gpu: Optional[bool] = None, model_dir: Optional[str] = None):
        """
        Initialize PPStructureV3 layout detection model.
        
        Args:
            use_gpu: Whether to use GPU (overrides config)
            model_dir: Model directory path (overrides config)
        """
        self.use_gpu = use_gpu if use_gpu is not None else settings.use_gpu_bool
        self.model_dir = model_dir if model_dir is not None else settings.model_dir
        self.layout_engine = None
        self.model_version = "PPStructureV3"
        self.initialized = False
        self.initialization_time = None
        
        # Map PPStructureV3 region types to standardized types
        self.type_mapping = {
            "text": "text",
            "title": "title",
            "table": "table",
            "figure": "figure",
            "formula": "formula",
            "list": "list_item",
            "header": "header",
            "footer": "footer",
            "caption": "caption",
            "reference": "reference",
            "abstract": "abstract",
            "code": "code",
            "seal": "seal",
            "handwriting": "handwriting",
            "paragraph": "text",
            "heading": "title",
            "table_caption": "caption",
            "figure_caption": "caption",
            "footnote": "text",
            "page_number": "text",
        }
        
        logger.info(f"LayoutDetector initialized (GPU: {self.use_gpu}, Model dir: {self.model_dir})")
    
    def _initialize_engine(self) -> None:
        """Initialize PPStructureV3 engine if not already initialized."""
        if self.initialized and self.layout_engine is not None:
            return
        
        try:
            start_time = time.time()
            
            # Import PaddleOCR (may trigger download on first import)
            from paddleocr import PPStructureV3
            
            # Initialize PPStructureV3 with configuration
            init_kwargs = {
                "use_table_recognition": True,
                "ocr_version": "PP-OCRv4",
            }
            
            # Add model directory if specified
            if self.model_dir:
                init_kwargs["layout_detection_model_dir"] = self.model_dir
            
            # Initialize the engine
            self.layout_engine = PPStructureV3(**init_kwargs)
            
            self.initialized = True
            self.initialization_time = time.time() - start_time
            
            logger.info(
                f"PPStructureV3 initialized successfully in {self.initialization_time:.2f}s "
                f"(GPU: {self.use_gpu}, Model dir: {self.model_dir})"
            )
            
        except ImportError as e:
            logger.error(f"Failed to import PaddleOCR: {e}")
            raise RuntimeError(f"PaddleOCR not installed: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize PPStructureV3: {e}")
            raise RuntimeError(f"PPStructureV3 initialization failed: {e}")
    
    def _convert_image_to_numpy(self, image: Any) -> np.ndarray:
        """
        Convert various image formats to numpy array.
        
        Args:
            image: PIL Image, numpy array, or file path
            
        Returns:
            numpy array in RGB format
        """
        try:
            if isinstance(image, str):
                # Load from file path
                pil_image = Image.open(image).convert("RGB")
                return np.array(pil_image)
            elif isinstance(image, Image.Image):
                # Convert PIL Image to numpy
                if image.mode != "RGB":
                    image = image.convert("RGB")
                return np.array(image)
            elif isinstance(image, np.ndarray):
                # Ensure it's RGB format
                if len(image.shape) == 2:
                    # Grayscale to RGB
                    return np.stack([image] * 3, axis=-1)
                elif image.shape[2] == 4:
                    # RGBA to RGB
                    return image[:, :, :3]
                elif image.shape[2] == 3:
                    return image
                else:
                    raise ValueError(f"Unsupported numpy array shape: {image.shape}")
            else:
                raise TypeError(f"Unsupported image type: {type(image)}")
                
        except Exception as e:
            logger.error(f"Failed to convert image to numpy array: {e}")
            raise ValueError(f"Invalid image format: {e}")
    
    def _standardize_region_type(self, region_type: str) -> str:
        """
        Standardize region type using mapping.
        
        Args:
            region_type: Raw region type from PPStructureV3
            
        Returns:
            Standardized region type
        """
        # Convert to lowercase for case-insensitive matching
        lower_type = region_type.lower()
        
        # Try exact match first
        if lower_type in self.type_mapping:
            return self.type_mapping[lower_type]
        
        # Try partial matching
        for key, value in self.type_mapping.items():
            if key in lower_type:
                return value
        
        # Default to text if unknown
        logger.warning(f"Unknown region type '{region_type}', defaulting to 'text'")
        return "text"
    
    def _extract_page_dimensions(self, image: np.ndarray) -> Dict[str, int]:
        """
        Extract page dimensions from image.
        
        Args:
            image: numpy array
            
        Returns:
            Dictionary with width and height
        """
        height, width = image.shape[:2]
        return {"width": width, "height": height}
    
    def detect_regions(
        self, 
        image: Any, 
        min_confidence: Optional[float] = None,
        detect_tables: bool = True,
        detect_formulas: bool = True
    ) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """
        Detect document regions in an image.
        
        Args:
            image: PIL Image, numpy array, or file path
            min_confidence: Minimum confidence threshold (0.0-1.0)
            detect_tables: Whether to detect tables
            detect_formulas: Whether to detect formulas
            
        Returns:
            Tuple of (regions list, page dimensions dict)
            
        Raises:
            ValueError: If image is invalid
            RuntimeError: If detection fails
        """
        if min_confidence is None:
            min_confidence = settings.min_confidence_default
        
        # Validate confidence threshold
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError(f"min_confidence must be between 0.0 and 1.0, got {min_confidence}")
        
        # Initialize engine if needed
        if not self.initialized:
            self._initialize_engine()
        
        # Convert image to numpy array
        try:
            numpy_image = self._convert_image_to_numpy(image)
        except Exception as e:
            logger.error(f"Image conversion failed: {e}")
            raise ValueError(f"Invalid image: {e}")
        
        # Extract page dimensions
        page_dimensions = self._extract_page_dimensions(numpy_image)
        logger.info(f"Processing image: {page_dimensions['width']}x{page_dimensions['height']} pixels")
        
        # Perform layout detection
        try:
            start_time = time.time()
            
            # Run PPStructureV3 detection
            results = self.layout_engine(numpy_image)
            
            processing_time = time.time() - start_time
            logger.info(f"Layout detection completed in {processing_time:.2f}s")
            
        except Exception as e:
            logger.error(f"Layout detection failed: {e}")
            raise RuntimeError(f"Layout detection error: {e}")
        
        # Process and filter results
        regions = []
        total_regions = 0
        filtered_regions = 0
        
        for i, block in enumerate(results):
            total_regions += 1
            
            # Extract confidence score (default to 1.0 if not present)
            confidence = block.get('score', 1.0)
            
            # Apply confidence filter
            if confidence < min_confidence:
                filtered_regions += 1
                continue
            
            # Extract region type
            raw_type = block.get('type', 'text')
            region_type = self._standardize_region_type(raw_type)
            
            # Extract bounding box
            bbox = block.get('bbox', [0, 0, 0, 0])
            
            # Ensure bbox is list of 4 integers
            if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                bbox = [int(coord) for coord in bbox]
            else:
                logger.warning(f"Invalid bbox format for region {i}: {bbox}")
                bbox = [0, 0, 0, 0]
            
            # Create region dictionary
            region = {
                "index": i,
                "type": region_type,
                "bbox": bbox,
                "confidence": float(confidence),
                "raw_type": raw_type,
            }
            
            # Add additional properties if available
            if 'res' in block:
                region['text'] = block['res']
            
            regions.append(region)
        
        # Log statistics
        logger.info(
            f"Detected {len(regions)} regions (filtered {filtered_regions} below confidence {min_confidence})"
        )
        
        if regions:
            # Log region type distribution
            type_counts = {}
            for region in regions:
                region_type = region['type']
                type_counts[region_type] = type_counts.get(region_type, 0) + 1
            
            logger.info(f"Region type distribution: {type_counts}")
        
        return regions, page_dimensions
    
    def get_model_info(self) -> Dict[str, Any]:
        """
        Get model information and status.
        
        Returns:
            Dictionary with model information
        """
        return {
            "model": "PPStructureV3",
            "version": self.model_version,
            "initialized": self.initialized,
            "use_gpu": self.use_gpu,
            "model_dir": self.model_dir,
            "initialization_time": self.initialization_time,
            "type_mapping": self.type_mapping,
        }
    
    def validate_image_size(self, image: Any, max_size_mb: Optional[int] = None) -> bool:
        """
        Validate image size against maximum allowed size.
        
        Args:
            image: PIL Image, numpy array, or file path
            max_size_mb: Maximum size in MB (overrides config)
            
        Returns:
            True if image size is valid
            
        Raises:
            ValueError: If image is too large
        """
        if max_size_mb is None:
            max_size_mb = settings.max_image_size_mb
        
        try:
            # Convert to numpy to get size
            numpy_image = self._convert_image_to_numpy(image)
            
            # Calculate size in bytes
            height, width, channels = numpy_image.shape
            size_bytes = height * width * channels
            
            # Convert to MB
            size_mb = size_bytes / (1024 * 1024)
            
            if size_mb > max_size_mb:
                raise ValueError(
                    f"Image size {size_mb:.2f}MB exceeds maximum {max_size_mb}MB "
                    f"(dimensions: {width}x{height})"
                )
            
            logger.debug(f"Image size validation passed: {size_mb:.2f}MB")
            return True
            
        except Exception as e:
            logger.error(f"Image size validation failed: {e}")
            raise ValueError(f"Image size validation failed: {e}")


# Global detector instance for singleton pattern
_detector_instance = None


def get_layout_detector(
    use_gpu: Optional[bool] = None, 
    model_dir: Optional[str] = None
) -> LayoutDetector:
    """
    Get or create global LayoutDetector instance.
    
    Args:
        use_gpu: Whether to use GPU (overrides config)
        model_dir: Model directory path (overrides config)
        
    Returns:
        LayoutDetector instance
    """
    global _detector_instance
    
    if _detector_instance is None:
        _detector_instance = LayoutDetector(use_gpu=use_gpu, model_dir=model_dir)
    
    return _detector_instance


def detect_regions(
    image: Any,
    min_confidence: Optional[float] = None,
    detect_tables: bool = True,
    detect_formulas: bool = True,
    use_gpu: Optional[bool] = None,
    model_dir: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Convenience function for detecting regions.
    
    Args:
        image: PIL Image, numpy array, or file path
        min_confidence: Minimum confidence threshold (0.0-1.0)
        detect_tables: Whether to detect tables
        detect_formulas: Whether to detect formulas
        use_gpu: Whether to use GPU (overrides config)
        model_dir: Model directory path (overrides config)
        
    Returns:
        Tuple of (regions list, page dimensions dict)
    """
    detector = get_layout_detector(use_gpu=use_gpu, model_dir=model_dir)
    return detector.detect_regions(
        image=image,
        min_confidence=min_confidence,
        detect_tables=detect_tables,
        detect_formulas=detect_formulas
    )