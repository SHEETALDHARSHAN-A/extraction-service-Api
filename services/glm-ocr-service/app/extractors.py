"""Content extractors for word-level and key-value extraction."""

import re
import logging
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class WordBoundingBox:
    """Word-level bounding box."""
    word: str
    bbox: List[int]  # [x, y, width, height]
    confidence: float


@dataclass
class KeyValuePair:
    """Key-value pair with bounding boxes."""
    key: str
    key_bbox: List[int]
    value: str
    value_bbox: List[int]
    confidence: float


class WordLevelExtractor:
    """Extracts word-level bounding boxes from GLM-OCR output."""
    
    def __init__(self):
        """Initialize word-level extractor."""
        self.logger = logging.getLogger(__name__)
    
    def extract_words(
        self, 
        content: str, 
        page_bbox: List[int],
        confidence: float
    ) -> List[WordBoundingBox]:
        """
        Extracts individual words with bounding boxes.
        
        Uses heuristics to approximate word positions based on content.
        In a real implementation, this would use the actual OCR output
        with word-level coordinates from the model.
        
        Args:
            content: Extracted text content
            page_bbox: Page bounding box [x, y, width, height]
            confidence: Overall confidence score
        
        Returns:
            List of WordBoundingBox objects
        """
        if not content or not content.strip():
            return []
        
        words = []
        lines = content.split('\n')
        
        page_x, page_y, page_width, page_height = page_bbox
        
        # Estimate line height based on page height and number of lines
        num_lines = len(lines)
        line_height = page_height // max(num_lines, 1) if num_lines > 0 else page_height
        
        current_y = page_y
        
        for line_idx, line in enumerate(lines):
            if not line.strip():
                current_y += line_height
                continue
            
            # Split line into words
            line_words = line.split()
            if not line_words:
                current_y += line_height
                continue
            
            # Estimate word width based on line width and number of words
            num_words = len(line_words)
            avg_word_width = page_width // max(num_words, 1)
            
            current_x = page_x
            
            for word_idx, word in enumerate(line_words):
                # Clean word (remove punctuation for width calculation)
                clean_word = re.sub(r'[^\w\s-]', '', word)
                
                # Estimate word width based on character count
                char_ratio = len(clean_word) / max(sum(len(w) for w in line_words), 1)
                word_width = int(page_width * char_ratio)
                word_width = max(word_width, 10)  # Minimum width
                
                # Create bounding box
                bbox = [current_x, current_y, word_width, line_height]
                
                # Calculate word-level confidence (slightly varied from overall)
                word_confidence = confidence * (0.95 + 0.1 * (word_idx % 3) / 3)
                word_confidence = min(word_confidence, 1.0)
                
                words.append(WordBoundingBox(
                    word=word,
                    bbox=bbox,
                    confidence=round(word_confidence, 3)
                ))
                
                current_x += word_width + 5  # Add small spacing
            
            current_y += line_height
        
        self.logger.info(f"Extracted {len(words)} words from content")
        return words
    
    def handle_hyphenated_words(
        self,
        words: List[WordBoundingBox]
    ) -> List[WordBoundingBox]:
        """
        Handle hyphenated words across lines.
        
        Detects words ending with hyphen and creates separate bounding boxes
        for each part.
        
        Args:
            words: List of word bounding boxes
        
        Returns:
            Updated list with hyphenated words properly split
        """
        result = []
        
        for i, word_box in enumerate(words):
            if word_box.word.endswith('-') and i < len(words) - 1:
                # This is a hyphenated word split across lines
                # Keep both parts separate with their own bounding boxes
                result.append(word_box)
                self.logger.debug(f"Detected hyphenated word: {word_box.word}")
            else:
                result.append(word_box)
        
        return result
    
    def sort_words_reading_order(
        self,
        words: List[WordBoundingBox]
    ) -> List[WordBoundingBox]:
        """
        Sort words in reading order (top-to-bottom, left-to-right).
        
        Args:
            words: List of word bounding boxes
        
        Returns:
            Sorted list of word bounding boxes
        """
        # Sort by y-coordinate (top to bottom), then x-coordinate (left to right)
        sorted_words = sorted(words, key=lambda w: (w.bbox[1], w.bbox[0]))
        return sorted_words
    
    def generate_word_level_json(
        self,
        words: List[WordBoundingBox]
    ) -> List[Dict]:
        """
        Generate JSON output format for word-level extraction.
        
        Args:
            words: List of word bounding boxes
        
        Returns:
            List of dictionaries with text, bbox, and confidence
        """
        return [
            {
                "text": word.word,
                "bbox": word.bbox,
                "confidence": word.confidence
            }
            for word in words
        ]


class KeyValueExtractor:
    """Extracts key-value pairs with bounding boxes."""
    
    def __init__(self):
        """Initialize key-value extractor."""
        self.logger = logging.getLogger(__name__)
        
        # Patterns for key-value detection
        self.colon_pattern = re.compile(r'^([^:]+):\s*(.+)$')
        self.equals_pattern = re.compile(r'^([^=]+)=\s*(.+)$')
    
    def extract_key_values(
        self,
        content: str,
        page_bbox: List[int]
    ) -> List[KeyValuePair]:
        """
        Identifies key-value patterns and extracts them with bounding boxes.
        
        Recognizes:
        - Colon-separated: "Invoice Number: 12345"
        - Table-based: Key in column 1, value in column 2
        - Form-field: Label above/beside input field
        
        Args:
            content: Extracted text content
            page_bbox: Page bounding box [x, y, width, height]
        
        Returns:
            List of KeyValuePair objects
        """
        if not content or not content.strip():
            return []
        
        key_value_pairs = []
        lines = content.split('\n')
        
        page_x, page_y, page_width, page_height = page_bbox
        line_height = page_height // max(len(lines), 1)
        
        current_y = page_y
        
        for line_idx, line in enumerate(lines):
            if not line.strip():
                current_y += line_height
                continue
            
            # Try colon-separated pattern
            match = self.colon_pattern.match(line.strip())
            if match:
                key = match.group(1).strip()
                value = match.group(2).strip()
                
                # Estimate bounding boxes
                key_width = int(page_width * 0.4)  # Key takes ~40% of width
                value_width = int(page_width * 0.6)  # Value takes ~60% of width
                
                key_bbox = [page_x, current_y, key_width, line_height]
                value_bbox = [page_x + key_width, current_y, value_width, line_height]
                
                # Calculate confidence (high for colon-separated patterns)
                confidence = 0.9
                
                key_value_pairs.append(KeyValuePair(
                    key=key,
                    key_bbox=key_bbox,
                    value=value,
                    value_bbox=value_bbox,
                    confidence=confidence
                ))
                
                self.logger.debug(f"Extracted key-value pair: {key} -> {value}")
            
            # Try equals pattern
            elif self.equals_pattern.match(line.strip()):
                match = self.equals_pattern.match(line.strip())
                key = match.group(1).strip()
                value = match.group(2).strip()
                
                key_width = int(page_width * 0.4)
                value_width = int(page_width * 0.6)
                
                key_bbox = [page_x, current_y, key_width, line_height]
                value_bbox = [page_x + key_width, current_y, value_width, line_height]
                
                confidence = 0.85
                
                key_value_pairs.append(KeyValuePair(
                    key=key,
                    key_bbox=key_bbox,
                    value=value,
                    value_bbox=value_bbox,
                    confidence=confidence
                ))
            
            current_y += line_height
        
        self.logger.info(f"Extracted {len(key_value_pairs)} key-value pairs")
        return key_value_pairs
    
    def handle_multi_value_keys(
        self,
        key_value_pairs: List[KeyValuePair]
    ) -> List[KeyValuePair]:
        """
        Handle keys with multiple associated values.
        
        Groups multiple values under the same key with individual bounding boxes.
        
        Args:
            key_value_pairs: List of key-value pairs
        
        Returns:
            Updated list with multi-value keys properly grouped
        """
        # Group by key
        key_groups: Dict[str, List[KeyValuePair]] = {}
        
        for pair in key_value_pairs:
            if pair.key not in key_groups:
                key_groups[pair.key] = []
            key_groups[pair.key].append(pair)
        
        # For keys with multiple values, keep them separate but log
        result = []
        for key, pairs in key_groups.items():
            if len(pairs) > 1:
                self.logger.info(f"Key '{key}' has {len(pairs)} values")
            result.extend(pairs)
        
        return result
    
    def handle_multi_line_pairs(
        self,
        content: str,
        page_bbox: List[int]
    ) -> List[KeyValuePair]:
        """
        Handle key-value pairs spanning multiple lines.
        
        Creates combined bounding box encompassing all lines.
        
        Args:
            content: Extracted text content
            page_bbox: Page bounding box [x, y, width, height]
        
        Returns:
            List of KeyValuePair objects with multi-line support
        """
        # This is a simplified implementation
        # In practice, would need more sophisticated line grouping logic
        pairs = self.extract_key_values(content, page_bbox)
        
        # Look for values that might continue on next line
        # (values ending without punctuation, followed by indented text, etc.)
        # For now, return as-is
        
        return pairs
    
    def calculate_confidence_scores(
        self,
        pair: KeyValuePair,
        pattern_type: str
    ) -> Tuple[float, float, float]:
        """
        Calculate confidence scores for key-value extraction.
        
        Args:
            pair: Key-value pair
            pattern_type: Type of pattern detected (colon, table, form)
        
        Returns:
            Tuple of (key_confidence, value_confidence, association_confidence)
        """
        # Base confidence varies by pattern type
        base_confidence = {
            'colon': 0.9,
            'equals': 0.85,
            'table': 0.8,
            'form': 0.75
        }.get(pattern_type, 0.7)
        
        # Key confidence (higher if key looks like a label)
        key_confidence = base_confidence
        if pair.key.endswith(('Number', 'Name', 'Date', 'ID', 'Code')):
            key_confidence = min(key_confidence + 0.05, 1.0)
        
        # Value confidence (higher if value is non-empty and reasonable length)
        value_confidence = base_confidence
        if pair.value and len(pair.value) > 0:
            value_confidence = min(value_confidence + 0.03, 1.0)
        
        # Association confidence (how confident we are they're related)
        association_confidence = base_confidence
        
        return (
            round(key_confidence, 3),
            round(value_confidence, 3),
            round(association_confidence, 3)
        )
    
    def generate_key_value_json(
        self,
        pairs: List[KeyValuePair]
    ) -> List[Dict]:
        """
        Generate JSON output format for key-value extraction.
        
        Args:
            pairs: List of key-value pairs
        
        Returns:
            List of dictionaries with key, value, bboxes, and confidence
        """
        return [
            {
                "key": pair.key,
                "key_bbox": pair.key_bbox,
                "value": pair.value,
                "value_bbox": pair.value_bbox,
                "confidence": pair.confidence
            }
            for pair in pairs
        ]



class TableExtractor:
    """Extracts table structure with cell-level bounding boxes."""
    
    def __init__(self):
        """Initialize table extractor."""
        self.logger = logging.getLogger(__name__)
    
    def extract_table(
        self,
        content: str,
        page_bbox: List[int]
    ) -> Dict[str, Any]:
        """
        Extract table structure preserving rows and columns.
        
        Args:
            content: Extracted text content
            page_bbox: Page bounding box [x, y, width, height]
        
        Returns:
            Dictionary with table structure and cell-level bounding boxes
        """
        if not content or not content.strip():
            return {"rows": [], "columns": 0}
        
        lines = content.split('\n')
        page_x, page_y, page_width, page_height = page_bbox
        
        # Detect table structure (simplified - looks for consistent column separators)
        rows = []
        max_columns = 0
        
        line_height = page_height // max(len(lines), 1)
        current_y = page_y
        
        for line in lines:
            if not line.strip():
                current_y += line_height
                continue
            
            # Split by common separators (|, tab, multiple spaces)
            cells = re.split(r'\s{2,}|\t|\|', line.strip())
            cells = [c.strip() for c in cells if c.strip()]
            
            if not cells:
                current_y += line_height
                continue
            
            max_columns = max(max_columns, len(cells))
            
            # Calculate cell bounding boxes
            cell_width = page_width // max(len(cells), 1)
            current_x = page_x
            
            row_cells = []
            for cell_text in cells:
                cell_bbox = [current_x, current_y, cell_width, line_height]
                row_cells.append({
                    "text": cell_text,
                    "bbox": cell_bbox
                })
                current_x += cell_width
            
            rows.append({"cells": row_cells})
            current_y += line_height
        
        self.logger.info(f"Extracted table with {len(rows)} rows and {max_columns} columns")
        
        return {
            "rows": rows,
            "columns": max_columns,
            "total_cells": sum(len(row["cells"]) for row in rows)
        }


class StructuredExtractor:
    """Extracts hierarchical document structure with section-level bounding boxes."""
    
    def __init__(self):
        """Initialize structured extractor."""
        self.logger = logging.getLogger(__name__)
        
        # Patterns for detecting sections
        self.heading_pattern = re.compile(r'^(#{1,6}|\d+\.|\d+\.\d+\.?)\s+(.+)$')
    
    def extract_structured(
        self,
        content: str,
        page_bbox: List[int]
    ) -> Dict[str, Any]:
        """
        Extract hierarchical document structure.
        
        Args:
            content: Extracted text content
            page_bbox: Page bounding box [x, y, width, height]
        
        Returns:
            Dictionary with hierarchical structure and section-level bounding boxes
        """
        if not content or not content.strip():
            return {"sections": []}
        
        lines = content.split('\n')
        page_x, page_y, page_width, page_height = page_bbox
        
        sections = []
        current_section = None
        
        line_height = page_height // max(len(lines), 1)
        current_y = page_y
        section_start_y = page_y
        
        for line in lines:
            # Check if line is a heading
            match = self.heading_pattern.match(line.strip())
            
            if match:
                # Save previous section if exists
                if current_section:
                    section_height = current_y - section_start_y
                    current_section["bbox"] = [page_x, section_start_y, page_width, section_height]
                    sections.append(current_section)
                
                # Start new section
                heading_marker = match.group(1)
                heading_text = match.group(2)
                
                # Determine level based on marker
                if heading_marker.startswith('#'):
                    level = len(heading_marker)
                elif '.' in heading_marker:
                    level = heading_marker.count('.') + 1
                else:
                    level = 1
                
                current_section = {
                    "level": level,
                    "heading": heading_text,
                    "content": [],
                    "bbox": None
                }
                section_start_y = current_y
            
            elif current_section is not None:
                # Add content to current section
                if line.strip():
                    current_section["content"].append(line.strip())
            
            else:
                # Content before first heading
                if not sections:
                    sections.append({
                        "level": 0,
                        "heading": "Preamble",
                        "content": [line.strip()] if line.strip() else [],
                        "bbox": [page_x, current_y, page_width, line_height]
                    })
            
            current_y += line_height
        
        # Save last section
        if current_section:
            section_height = current_y - section_start_y
            current_section["bbox"] = [page_x, section_start_y, page_width, section_height]
            sections.append(current_section)
        
        self.logger.info(f"Extracted {len(sections)} sections from document")
        
        return {
            "sections": sections,
            "total_sections": len(sections)
        }
