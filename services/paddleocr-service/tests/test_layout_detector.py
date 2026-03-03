"""Unit tests for layout_detector.py."""

import unittest
from unittest.mock import Mock, patch, MagicMock
import numpy as np
from PIL import Image
import tempfile
import os

# Import the module to test
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.layout_detector import LayoutDetector, get_layout_detector, detect_regions


class TestLayoutDetector(unittest.TestCase):
    """Test cases for LayoutDetector class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.detector = LayoutDetector(use_gpu=False, model_dir="./test_models")
        self.test_image = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        self.test_pil_image = Image.fromarray(self.test_image)
        
        # Mock PPStructureV3 to avoid actual model loading
        self.ppstructure_mock = Mock()
        self.ppstructure_mock.return_value = [
            {
                'type': 'text',
                'bbox': [10, 20, 90, 80],
                'score': 0.95,
                'res': 'Sample text'
            },
            {
                'type': 'table',
                'bbox': [15, 25, 85, 75],
                'score': 0.85
            },
            {
                'type': 'formula',
                'bbox': [20, 30, 80, 70],
                'score': 0.45  # Below default confidence threshold
            }
        ]
    
    def test_initialization(self):
        """Test LayoutDetector initialization."""
        detector = LayoutDetector(use_gpu=True, model_dir="/custom/path")
        self.assertEqual(detector.use_gpu, True)
        self.assertEqual(detector.model_dir, "/custom/path")
        self.assertEqual(detector.model_version, "PPStructureV3")
        self.assertFalse(detector.initialized)
    
    def test_type_mapping(self):
        """Test region type mapping."""
        # Test exact matches
        self.assertEqual(self.detector._standardize_region_type("text"), "text")
        self.assertEqual(self.detector._standardize_region_type("table"), "table")
        self.assertEqual(self.detector._standardize_region_type("formula"), "formula")
        
        # Test case-insensitive
        self.assertEqual(self.detector._standardize_region_type("TEXT"), "text")
        self.assertEqual(self.detector._standardize_region_type("Table"), "table")
        
        # Test partial matches
        self.assertEqual(self.detector._standardize_region_type("paragraph"), "text")
        self.assertEqual(self.detector._standardize_region_type("heading"), "title")
        
        # Test unknown type (defaults to text)
        self.assertEqual(self.detector._standardize_region_type("unknown_type"), "text")
    
    def test_convert_image_to_numpy(self):
        """Test image conversion to numpy array."""
        # Test numpy array input
        result = self.detector._convert_image_to_numpy(self.test_image)
        self.assertIsInstance(result, np.ndarray)
        self.assertEqual(result.shape, (100, 100, 3))
        
        # Test PIL Image input
        result = self.detector._convert_image_to_numpy(self.test_pil_image)
        self.assertIsInstance(result, np.ndarray)
        self.assertEqual(result.shape, (100, 100, 3))
        
        # Test grayscale numpy array
        gray_image = np.random.randint(0, 255, (100, 100), dtype=np.uint8)
        result = self.detector._convert_image_to_numpy(gray_image)
        self.assertEqual(result.shape, (100, 100, 3))
        
        # Test RGBA numpy array
        rgba_image = np.random.randint(0, 255, (100, 100, 4), dtype=np.uint8)
        result = self.detector._convert_image_to_numpy(rgba_image)
        self.assertEqual(result.shape, (100, 100, 3))
        
        # Test invalid input - should raise ValueError (not TypeError due to wrapper)
        with self.assertRaises(ValueError):
            self.detector._convert_image_to_numpy(123)  # Integer
    
    def test_extract_page_dimensions(self):
        """Test page dimension extraction."""
        dimensions = self.detector._extract_page_dimensions(self.test_image)
        self.assertEqual(dimensions, {"width": 100, "height": 100})
        
        # Test with different shape
        tall_image = np.random.randint(0, 255, (200, 50, 3), dtype=np.uint8)
        dimensions = self.detector._extract_page_dimensions(tall_image)
        self.assertEqual(dimensions, {"width": 50, "height": 200})
    
    def test_detect_regions_with_mock(self):
        """Test region detection with mocked PPStructureV3."""
        # Create detector and manually set engine
        detector = LayoutDetector(use_gpu=False)
        
        # Mock the engine directly (avoiding import patch issues)
        mock_engine = Mock()
        mock_engine.return_value = [
            {
                'type': 'text',
                'bbox': [10, 20, 90, 80],
                'score': 0.95,
                'res': 'Sample text'
            },
            {
                'type': 'table',
                'bbox': [15, 25, 85, 75],
                'score': 0.85
            },
            {
                'type': 'formula',
                'bbox': [20, 30, 80, 70],
                'score': 0.45  # Below confidence threshold
            }
        ]
        
        detector.layout_engine = mock_engine
        detector.initialized = True
        
        # Test detection
        regions, dimensions = detector.detect_regions(
            self.test_image,
            min_confidence=0.5,
            detect_tables=True,
            detect_formulas=True
        )
        
        # Verify results
        self.assertEqual(len(regions), 2)  # Only 2 regions above 0.5 confidence
        self.assertEqual(dimensions, {"width": 100, "height": 100})
        
        # Verify first region
        self.assertEqual(regions[0]["index"], 0)
        self.assertEqual(regions[0]["type"], "text")
        self.assertEqual(regions[0]["bbox"], [10, 20, 90, 80])
        self.assertEqual(regions[0]["confidence"], 0.95)
        self.assertEqual(regions[0]["raw_type"], "text")
        self.assertEqual(regions[0]["text"], "Sample text")
        
        # Verify second region
        self.assertEqual(regions[1]["index"], 1)
        self.assertEqual(regions[1]["type"], "table")
        self.assertEqual(regions[1]["bbox"], [15, 25, 85, 75])
        self.assertEqual(regions[1]["confidence"], 0.85)
        self.assertEqual(regions[1]["raw_type"], "table")
    
    def test_detect_regions_invalid_confidence(self):
        """Test detection with invalid confidence threshold."""
        with self.assertRaises(ValueError):
            self.detector.detect_regions(self.test_image, min_confidence=1.5)
        
        with self.assertRaises(ValueError):
            self.detector.detect_regions(self.test_image, min_confidence=-0.5)
    
    def test_validate_image_size(self):
        """Test image size validation."""
        # Create a small image (100x100x3 = 30,000 bytes ≈ 0.03MB)
        small_image = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        
        # Should pass with default 10MB limit
        self.assertTrue(self.detector.validate_image_size(small_image))
        
        # Should pass with custom 0.1MB limit (image is 0.03MB)
        self.assertTrue(self.detector.validate_image_size(small_image, max_size_mb=0.1))
        
        # Create a larger image (1000x1000x3 = 3,000,000 bytes ≈ 2.86MB)
        large_image = np.random.randint(0, 255, (1000, 1000, 3), dtype=np.uint8)
        
        # Should fail with 0.1MB limit
        with self.assertRaises(ValueError):
            self.detector.validate_image_size(large_image, max_size_mb=0.1)
    
    def test_get_model_info(self):
        """Test model information retrieval."""
        info = self.detector.get_model_info()
        
        self.assertEqual(info["model"], "PPStructureV3")
        self.assertEqual(info["version"], "PPStructureV3")
        self.assertEqual(info["use_gpu"], False)
        self.assertEqual(info["model_dir"], "./test_models")
        self.assertIn("type_mapping", info)
        self.assertIsNone(info["initialization_time"])
        self.assertFalse(info["initialized"])


class TestSingletonFunctions(unittest.TestCase):
    """Test cases for singleton pattern functions."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_image = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    
    def test_get_layout_detector(self):
        """Test get_layout_detector singleton function."""
        # Note: The singleton may already be initialized from previous tests
        # So we just verify it returns a valid detector instance
        detector = get_layout_detector()
        self.assertIsNotNone(detector)
        self.assertIsInstance(detector, LayoutDetector)
    
    @patch('app.layout_detector.get_layout_detector')
    def test_detect_regions_function(self, mock_get_detector):
        """Test convenience detect_regions function."""
        # Mock detector
        mock_detector = Mock()
        mock_detector.detect_regions.return_value = (
            [{"type": "text", "bbox": [0, 0, 100, 100]}],
            {"width": 100, "height": 100}
        )
        mock_get_detector.return_value = mock_detector
        
        # Test function
        regions, dimensions = detect_regions(
            self.test_image,
            min_confidence=0.7,
            detect_tables=False,
            detect_formulas=True,
            use_gpu=True,
            model_dir="/custom/path"
        )
        
        # Verify detector was called with correct parameters
        mock_get_detector.assert_called_once_with(use_gpu=True, model_dir="/custom/path")
        mock_detector.detect_regions.assert_called_once_with(
            image=self.test_image,
            min_confidence=0.7,
            detect_tables=False,
            detect_formulas=True
        )
        
        # Verify results
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0]["type"], "text")
        self.assertEqual(dimensions, {"width": 100, "height": 100})


class TestErrorHandling(unittest.TestCase):
    """Test error handling in LayoutDetector."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_image = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    
    def test_invalid_image_format(self):
        """Test handling of invalid image format."""
        detector = LayoutDetector()
        
        # Test with invalid type - should raise ValueError (not TypeError due to wrapper)
        with self.assertRaises(ValueError):
            detector._convert_image_to_numpy(123)
        
        # Test with invalid file path
        with self.assertRaises(ValueError):
            detector._convert_image_to_numpy("/nonexistent/path/image.jpg")
    
    def test_detection_failure(self):
        """Test handling of detection failures."""
        detector = LayoutDetector()
        
        # Mock engine to raise exception
        mock_engine = Mock()
        mock_engine.side_effect = RuntimeError("Detection failed")
        
        detector.layout_engine = mock_engine
        detector.initialized = True
        
        with self.assertRaises(RuntimeError):
            detector.detect_regions(self.test_image)
    
    def test_initialization_failure(self):
        """Test handling of initialization failures."""
        detector = LayoutDetector()
        
        # Mock the import to fail by patching the import inside the method
        # We need to patch at the module level where PPStructureV3 is imported
        with patch('paddleocr.PPStructureV3', side_effect=ImportError("No module")):
            with self.assertRaises(RuntimeError):
                # Force re-initialization
                detector.initialized = False
                detector.layout_engine = None
                detector._initialize_engine()


if __name__ == '__main__':
    unittest.main()