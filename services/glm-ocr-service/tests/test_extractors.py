"""Tests for extractor modules."""

import pytest
from app.extractors import (
    WordLevelExtractor,
    KeyValueExtractor,
    TableExtractor,
    StructuredExtractor
)


class TestWordLevelExtractor:
    """Tests for WordLevelExtractor."""
    
    def test_initialization(self):
        """Test extractor can be initialized."""
        extractor = WordLevelExtractor()
        assert extractor is not None
    
    def test_extract_words_basic(self):
        """Test basic word extraction."""
        extractor = WordLevelExtractor()
        content = "Hello world\nThis is a test"
        page_bbox = [0, 0, 1000, 1000]
        confidence = 0.95
        
        words = extractor.extract_words(content, page_bbox, confidence)
        
        assert len(words) > 0
        assert all(hasattr(w, 'word') for w in words)
        assert all(hasattr(w, 'bbox') for w in words)
        assert all(hasattr(w, 'confidence') for w in words)
        assert all(len(w.bbox) == 4 for w in words)
    
    def test_extract_words_empty(self):
        """Test word extraction with empty content."""
        extractor = WordLevelExtractor()
        words = extractor.extract_words("", [0, 0, 1000, 1000], 0.9)
        assert len(words) == 0
    
    def test_sort_words_reading_order(self):
        """Test word sorting in reading order."""
        extractor = WordLevelExtractor()
        content = "First line\nSecond line"
        words = extractor.extract_words(content, [0, 0, 1000, 1000], 0.9)
        sorted_words = extractor.sort_words_reading_order(words)
        
        assert len(sorted_words) == len(words)
        # Words should be sorted by y then x
        for i in range(len(sorted_words) - 1):
            curr_y = sorted_words[i].bbox[1]
            next_y = sorted_words[i + 1].bbox[1]
            assert curr_y <= next_y
    
    def test_generate_word_level_json(self):
        """Test JSON generation for word-level data."""
        extractor = WordLevelExtractor()
        content = "Test words"
        words = extractor.extract_words(content, [0, 0, 1000, 1000], 0.9)
        json_output = extractor.generate_word_level_json(words)
        
        assert isinstance(json_output, list)
        assert all('text' in item for item in json_output)
        assert all('bbox' in item for item in json_output)
        assert all('confidence' in item for item in json_output)


class TestKeyValueExtractor:
    """Tests for KeyValueExtractor."""
    
    def test_initialization(self):
        """Test extractor can be initialized."""
        extractor = KeyValueExtractor()
        assert extractor is not None
    
    def test_extract_key_values_colon(self):
        """Test key-value extraction with colon separator."""
        extractor = KeyValueExtractor()
        content = "Name: John Doe\nAge: 30\nCity: New York"
        page_bbox = [0, 0, 1000, 1000]
        
        pairs = extractor.extract_key_values(content, page_bbox)
        
        assert len(pairs) > 0
        assert all(hasattr(p, 'key') for p in pairs)
        assert all(hasattr(p, 'value') for p in pairs)
        assert all(hasattr(p, 'key_bbox') for p in pairs)
        assert all(hasattr(p, 'value_bbox') for p in pairs)
        assert all(hasattr(p, 'confidence') for p in pairs)
    
    def test_extract_key_values_empty(self):
        """Test key-value extraction with empty content."""
        extractor = KeyValueExtractor()
        pairs = extractor.extract_key_values("", [0, 0, 1000, 1000])
        assert len(pairs) == 0
    
    def test_handle_multi_value_keys(self):
        """Test handling of multi-value keys."""
        extractor = KeyValueExtractor()
        content = "Tags: Python\nTags: FastAPI\nTags: Testing"
        pairs = extractor.extract_key_values(content, [0, 0, 1000, 1000])
        result = extractor.handle_multi_value_keys(pairs)
        
        assert len(result) > 0
    
    def test_generate_key_value_json(self):
        """Test JSON generation for key-value data."""
        extractor = KeyValueExtractor()
        content = "Name: Test\nValue: 123"
        pairs = extractor.extract_key_values(content, [0, 0, 1000, 1000])
        json_output = extractor.generate_key_value_json(pairs)
        
        assert isinstance(json_output, list)
        assert all('key' in item for item in json_output)
        assert all('value' in item for item in json_output)
        assert all('key_bbox' in item for item in json_output)
        assert all('value_bbox' in item for item in json_output)


class TestTableExtractor:
    """Tests for TableExtractor."""
    
    def test_initialization(self):
        """Test extractor can be initialized."""
        extractor = TableExtractor()
        assert extractor is not None
    
    def test_extract_table_basic(self):
        """Test basic table extraction."""
        extractor = TableExtractor()
        content = "Col1  Col2  Col3\nVal1  Val2  Val3\nVal4  Val5  Val6"
        page_bbox = [0, 0, 1000, 1000]
        
        table = extractor.extract_table(content, page_bbox)
        
        assert 'rows' in table
        assert 'columns' in table
        assert isinstance(table['rows'], list)
        assert table['columns'] > 0
    
    def test_extract_table_empty(self):
        """Test table extraction with empty content."""
        extractor = TableExtractor()
        table = extractor.extract_table("", [0, 0, 1000, 1000])
        assert table['rows'] == []
        assert table['columns'] == 0


class TestStructuredExtractor:
    """Tests for StructuredExtractor."""
    
    def test_initialization(self):
        """Test extractor can be initialized."""
        extractor = StructuredExtractor()
        assert extractor is not None
    
    def test_extract_structured_basic(self):
        """Test basic structured extraction."""
        extractor = StructuredExtractor()
        content = "# Heading 1\nContent for heading 1\n## Heading 2\nContent for heading 2"
        page_bbox = [0, 0, 1000, 1000]
        
        structured = extractor.extract_structured(content, page_bbox)
        
        assert 'sections' in structured
        assert isinstance(structured['sections'], list)
        assert len(structured['sections']) > 0
    
    def test_extract_structured_empty(self):
        """Test structured extraction with empty content."""
        extractor = StructuredExtractor()
        structured = extractor.extract_structured("", [0, 0, 1000, 1000])
        assert structured['sections'] == []
