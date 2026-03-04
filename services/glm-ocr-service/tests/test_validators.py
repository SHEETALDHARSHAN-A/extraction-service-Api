"""Tests for extraction result validators."""

import pytest
from app.validators import ExtractionValidator, ValidationWarning


class TestExtractionValidator:
    """Test suite for ExtractionValidator."""
    
    def test_initialization(self):
        """Test validator initialization."""
        validator = ExtractionValidator()
        assert validator is not None
        assert validator.warnings == []
    
    def test_validate_bounding_box_valid(self):
        """Test validation of valid bounding box."""
        validator = ExtractionValidator()
        page_bbox = [0, 0, 1000, 1000]
        bbox = [100, 100, 200, 50]
        
        result = validator.validate_bounding_box(bbox, page_bbox, "test_element")
        
        assert result is True
        assert len(validator.warnings) == 0
    
    def test_validate_bounding_box_outside_page(self):
        """Test validation of bounding box outside page boundaries."""
        validator = ExtractionValidator()
        page_bbox = [0, 0, 1000, 1000]
        bbox = [-10, 100, 200, 50]  # x is negative
        
        result = validator.validate_bounding_box(bbox, page_bbox, "test_element")
        
        assert result is False
        assert len(validator.warnings) == 1
        assert validator.warnings[0].code == "BBOX_OUTSIDE_PAGE"
    
    def test_validate_bounding_box_exceeds_page(self):
        """Test validation of bounding box exceeding page boundaries."""
        validator = ExtractionValidator()
        page_bbox = [0, 0, 1000, 1000]
        bbox = [900, 900, 200, 200]  # Extends beyond page
        
        result = validator.validate_bounding_box(bbox, page_bbox, "test_element")
        
        assert result is False
        assert len(validator.warnings) == 1
        assert validator.warnings[0].code == "BBOX_EXCEEDS_PAGE"
    
    def test_validate_bounding_box_invalid_dimensions(self):
        """Test validation of bounding box with invalid dimensions."""
        validator = ExtractionValidator()
        page_bbox = [0, 0, 1000, 1000]
        bbox = [100, 100, 0, 50]  # Width is 0
        
        result = validator.validate_bounding_box(bbox, page_bbox, "test_element")
        
        assert result is False
        assert len(validator.warnings) == 1
        assert validator.warnings[0].code == "INVALID_BBOX_DIMENSIONS"
    
    def test_validate_confidence_score_valid(self):
        """Test validation of valid confidence score."""
        validator = ExtractionValidator()
        
        result = validator.validate_confidence_score(0.85, "test_element")
        
        assert result is True
        assert len(validator.warnings) == 0
    
    def test_validate_confidence_score_out_of_range(self):
        """Test validation of confidence score out of range."""
        validator = ExtractionValidator()
        
        result = validator.validate_confidence_score(1.5, "test_element")
        
        assert result is False
        assert len(validator.warnings) == 1
        assert validator.warnings[0].code == "CONFIDENCE_OUT_OF_RANGE"
    
    def test_validate_confidence_score_low(self):
        """Test validation of low confidence score."""
        validator = ExtractionValidator()
        
        result = validator.validate_confidence_score(0.3, "test_element")
        
        assert result is True  # Still valid, just low
        assert len(validator.warnings) == 1
        assert validator.warnings[0].code == "LOW_CONFIDENCE"
        assert validator.warnings[0].severity == "medium"
    
    def test_validate_word_boxes_valid(self):
        """Test validation of valid word boxes."""
        validator = ExtractionValidator()
        page_bbox = [0, 0, 1000, 1000]
        
        word_boxes = [
            {"text": "Hello", "bbox": [10, 10, 50, 20], "confidence": 0.9},
            {"text": "World", "bbox": [65, 10, 50, 20], "confidence": 0.85}
        ]
        
        all_valid, num_invalid = validator.validate_word_boxes(word_boxes, page_bbox)
        
        assert all_valid is True
        assert num_invalid == 0
    
    def test_validate_word_boxes_with_overlap(self):
        """Test validation of word boxes with overlap."""
        validator = ExtractionValidator()
        page_bbox = [0, 0, 1000, 1000]
        
        # Create overlapping boxes
        word_boxes = [
            {"text": "Hello", "bbox": [10, 10, 50, 20], "confidence": 0.9},
            {"text": "World", "bbox": [30, 10, 50, 20], "confidence": 0.85}  # Overlaps with first
        ]
        
        all_valid, num_invalid = validator.validate_word_boxes(word_boxes, page_bbox)
        
        # Boxes are valid individually, but overlap warning should be present
        assert all_valid is True
        # Check for overlap warning
        overlap_warnings = [w for w in validator.warnings if w.code == "WORD_BOXES_OVERLAP"]
        assert len(overlap_warnings) > 0
    
    def test_validate_key_value_pairs_valid(self):
        """Test validation of valid key-value pairs."""
        validator = ExtractionValidator()
        page_bbox = [0, 0, 1000, 1000]
        
        kv_pairs = [
            {
                "key": "Name",
                "key_bbox": [10, 10, 100, 20],
                "value": "John Doe",
                "value_bbox": [120, 10, 150, 20],
                "confidence": 0.9
            }
        ]
        
        all_valid, num_invalid = validator.validate_key_value_pairs(kv_pairs, page_bbox)
        
        assert all_valid is True
        assert num_invalid == 0
    
    def test_validate_key_value_pairs_orphaned_value(self):
        """Test validation of key-value pair with orphaned value."""
        validator = ExtractionValidator()
        page_bbox = [0, 0, 1000, 1000]
        
        kv_pairs = [
            {
                "key": "",  # Empty key
                "key_bbox": [10, 10, 100, 20],
                "value": "John Doe",
                "value_bbox": [120, 10, 150, 20],
                "confidence": 0.9
            }
        ]
        
        all_valid, num_invalid = validator.validate_key_value_pairs(kv_pairs, page_bbox)
        
        assert all_valid is False
        assert num_invalid == 1
        assert any(w.code == "ORPHANED_VALUE" for w in validator.warnings)
    
    def test_validate_extraction_result_complete(self):
        """Test validation of complete extraction result."""
        validator = ExtractionValidator()
        page_bbox = [0, 0, 1000, 1000]
        
        result = {
            "word_boxes": [
                {"text": "Hello", "bbox": [10, 10, 50, 20], "confidence": 0.9}
            ],
            "key_value_pairs": [
                {
                    "key": "Name",
                    "key_bbox": [10, 50, 100, 20],
                    "value": "John",
                    "value_bbox": [120, 50, 80, 20],
                    "confidence": 0.85
                }
            ]
        }
        
        validation_summary = validator.validate_extraction_result(result, page_bbox)
        
        assert validation_summary["valid"] is True
        assert validation_summary["stats"]["total_elements"] == 2
        assert validation_summary["stats"]["invalid_elements"] == 0
    
    def test_validate_extraction_result_high_low_confidence_ratio(self):
        """Test validation with high ratio of low confidence scores."""
        validator = ExtractionValidator()
        page_bbox = [0, 0, 1000, 1000]
        
        # Create 10 word boxes, 3 with low confidence (30%)
        word_boxes = []
        for i in range(10):
            confidence = 0.3 if i < 3 else 0.9
            word_boxes.append({
                "text": f"word{i}",
                "bbox": [10 + i * 60, 10, 50, 20],
                "confidence": confidence
            })
        
        result = {"word_boxes": word_boxes}
        
        validation_summary = validator.validate_extraction_result(result, page_bbox)
        
        # Should have warnings about low confidence
        assert len(validation_summary["warnings"]) > 0
        assert validation_summary["stats"]["low_confidence_count"] == 3
    
    def test_validate_structured_format_roundtrip_success(self):
        """Test successful round-trip validation for structured format."""
        validator = ExtractionValidator()
        
        original_content = """# Introduction
This is the introduction section.
It has multiple lines.

# Main Content
This is the main content.

# Conclusion
Final thoughts here."""
        
        structured_output = {
            "sections": [
                {
                    "level": 1,
                    "heading": "Introduction",
                    "content": [
                        "This is the introduction section.",
                        "It has multiple lines."
                    ]
                },
                {
                    "level": 1,
                    "heading": "Main Content",
                    "content": ["This is the main content."]
                },
                {
                    "level": 1,
                    "heading": "Conclusion",
                    "content": ["Final thoughts here."]
                }
            ]
        }
        
        content_preserved, similarity = validator.validate_structured_format_roundtrip(
            original_content,
            structured_output
        )
        
        assert content_preserved is True
        assert similarity >= 0.95
    
    def test_validate_structured_format_roundtrip_content_loss(self):
        """Test round-trip validation with content loss."""
        validator = ExtractionValidator()
        
        original_content = """# Introduction
This is the introduction section.
It has multiple lines.
And even more content here.

# Main Content
This is the main content.
With additional details.

# Conclusion
Final thoughts here."""
        
        # Structured output missing some content
        structured_output = {
            "sections": [
                {
                    "level": 1,
                    "heading": "Introduction",
                    "content": ["This is the introduction section."]
                },
                {
                    "level": 1,
                    "heading": "Conclusion",
                    "content": ["Final thoughts here."]
                }
            ]
        }
        
        content_preserved, similarity = validator.validate_structured_format_roundtrip(
            original_content,
            structured_output
        )
        
        assert content_preserved is False
        assert similarity < 0.95
        assert any(w.code == "CONTENT_NOT_PRESERVED" for w in validator.warnings)
    
    def test_clear_warnings(self):
        """Test clearing warnings."""
        validator = ExtractionValidator()
        
        # Generate some warnings
        validator.validate_confidence_score(1.5, "test")
        assert len(validator.warnings) > 0
        
        # Clear warnings
        validator.clear_warnings()
        assert len(validator.warnings) == 0
    
    def test_normalize_text(self):
        """Test text normalization."""
        validator = ExtractionValidator()
        
        text = """  Line 1  
        
        Line 2   
        
        
        Line 3  """
        
        normalized = validator._normalize_text(text)
        
        assert normalized == "Line 1\nLine 2\nLine 3"
    
    def test_calculate_text_similarity_identical(self):
        """Test similarity calculation for identical texts."""
        validator = ExtractionValidator()
        
        text1 = "Hello World"
        text2 = "Hello World"
        
        similarity = validator._calculate_text_similarity(text1, text2)
        
        assert similarity == 1.0
    
    def test_calculate_text_similarity_different(self):
        """Test similarity calculation for different texts."""
        validator = ExtractionValidator()
        
        text1 = "Hello World"
        text2 = "Goodbye World"
        
        similarity = validator._calculate_text_similarity(text1, text2)
        
        assert 0.0 < similarity < 1.0
    
    def test_calculate_text_similarity_empty(self):
        """Test similarity calculation for empty texts."""
        validator = ExtractionValidator()
        
        # Both empty
        similarity = validator._calculate_text_similarity("", "")
        assert similarity == 1.0
        
        # One empty
        similarity = validator._calculate_text_similarity("Hello", "")
        assert similarity == 0.0
