"""Validation module for extraction results."""

import logging
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ValidationWarning:
    """Represents a validation warning."""
    code: str
    message: str
    severity: str  # "low", "medium", "high"
    details: Optional[Dict[str, Any]] = None


class ExtractionValidator:
    """Validates extraction results for correctness and completeness."""
    
    def __init__(self):
        """Initialize extraction validator."""
        self.logger = logging.getLogger(__name__)
        self.warnings: List[ValidationWarning] = []
    
    def validate_bounding_box(
        self,
        bbox: List[int],
        page_bbox: List[int],
        element_type: str = "element"
    ) -> bool:
        """
        Validate that bounding box is within page boundaries.
        
        Args:
            bbox: Bounding box [x, y, width, height]
            page_bbox: Page bounding box [x, y, width, height]
            element_type: Type of element for error messages
        
        Returns:
            True if valid, False otherwise
        """
        if not bbox or len(bbox) != 4:
            self.warnings.append(ValidationWarning(
                code="INVALID_BBOX_FORMAT",
                message=f"{element_type} has invalid bounding box format",
                severity="high",
                details={"bbox": bbox}
            ))
            return False
        
        x, y, width, height = bbox
        page_x, page_y, page_width, page_height = page_bbox
        
        # Check if bbox is within page boundaries
        if x < page_x or y < page_y:
            self.warnings.append(ValidationWarning(
                code="BBOX_OUTSIDE_PAGE",
                message=f"{element_type} bounding box starts outside page boundaries",
                severity="high",
                details={
                    "bbox": bbox,
                    "page_bbox": page_bbox,
                    "x": x,
                    "y": y,
                    "page_x": page_x,
                    "page_y": page_y
                }
            ))
            return False
        
        if x + width > page_x + page_width or y + height > page_y + page_height:
            self.warnings.append(ValidationWarning(
                code="BBOX_EXCEEDS_PAGE",
                message=f"{element_type} bounding box extends beyond page boundaries",
                severity="high",
                details={
                    "bbox": bbox,
                    "page_bbox": page_bbox,
                    "bbox_right": x + width,
                    "bbox_bottom": y + height,
                    "page_right": page_x + page_width,
                    "page_bottom": page_y + page_height
                }
            ))
            return False
        
        # Check for negative dimensions
        if width <= 0 or height <= 0:
            self.warnings.append(ValidationWarning(
                code="INVALID_BBOX_DIMENSIONS",
                message=f"{element_type} has invalid dimensions (width or height <= 0)",
                severity="high",
                details={"bbox": bbox, "width": width, "height": height}
            ))
            return False
        
        return True
    
    def validate_confidence_score(
        self,
        confidence: float,
        element_type: str = "element"
    ) -> bool:
        """
        Validate that confidence score is in range 0.0-1.0.
        
        Args:
            confidence: Confidence score
            element_type: Type of element for error messages
        
        Returns:
            True if valid, False otherwise
        """
        if not isinstance(confidence, (int, float)):
            self.warnings.append(ValidationWarning(
                code="INVALID_CONFIDENCE_TYPE",
                message=f"{element_type} confidence is not a number",
                severity="high",
                details={"confidence": confidence, "type": type(confidence).__name__}
            ))
            return False
        
        if confidence < 0.0 or confidence > 1.0:
            self.warnings.append(ValidationWarning(
                code="CONFIDENCE_OUT_OF_RANGE",
                message=f"{element_type} confidence score is outside valid range [0.0, 1.0]",
                severity="high",
                details={"confidence": confidence}
            ))
            return False
        
        # Warn about low confidence
        if confidence < 0.5:
            self.warnings.append(ValidationWarning(
                code="LOW_CONFIDENCE",
                message=f"{element_type} has low confidence score",
                severity="medium",
                details={"confidence": confidence}
            ))
        
        return True
    
    def validate_word_boxes(
        self,
        word_boxes: List[Any],
        page_bbox: List[int]
    ) -> Tuple[bool, int]:
        """
        Validate word-level bounding boxes.
        
        Checks:
        - All boxes within page boundaries
        - Confidence scores in valid range
        - Boxes don't overlap incorrectly
        
        Args:
            word_boxes: List of word bounding boxes
            page_bbox: Page bounding box [x, y, width, height]
        
        Returns:
            Tuple of (all_valid, num_invalid)
        """
        if not word_boxes:
            return True, 0
        
        all_valid = True
        num_invalid = 0
        
        for i, word_box in enumerate(word_boxes):
            # Extract bbox and confidence
            if hasattr(word_box, 'bbox'):
                bbox = word_box.bbox
                confidence = word_box.confidence
                word_text = getattr(word_box, 'word', f"word_{i}")
            elif isinstance(word_box, dict):
                bbox = word_box.get('bbox', [])
                confidence = word_box.get('confidence', 0.0)
                word_text = word_box.get('text', word_box.get('word', f"word_{i}"))
            else:
                self.warnings.append(ValidationWarning(
                    code="INVALID_WORD_BOX_FORMAT",
                    message=f"Word box {i} has invalid format",
                    severity="high",
                    details={"index": i, "type": type(word_box).__name__}
                ))
                all_valid = False
                num_invalid += 1
                continue
            
            # Validate bbox
            if not self.validate_bounding_box(bbox, page_bbox, f"Word '{word_text}'"):
                all_valid = False
                num_invalid += 1
            
            # Validate confidence
            if not self.validate_confidence_score(confidence, f"Word '{word_text}'"):
                all_valid = False
                num_invalid += 1
        
        # Check for incorrect overlaps
        overlap_count = self._check_word_overlaps(word_boxes)
        if overlap_count > 0:
            self.warnings.append(ValidationWarning(
                code="WORD_BOXES_OVERLAP",
                message=f"Found {overlap_count} incorrectly overlapping word boxes",
                severity="medium",
                details={"overlap_count": overlap_count}
            ))
        
        return all_valid, num_invalid
    
    def _check_word_overlaps(self, word_boxes: List[Any]) -> int:
        """
        Check for incorrect word box overlaps.
        
        Allows small overlaps (ligatures, kerning) but flags significant overlaps.
        
        Args:
            word_boxes: List of word bounding boxes
        
        Returns:
            Number of incorrect overlaps found
        """
        overlap_count = 0
        
        for i in range(len(word_boxes)):
            for j in range(i + 1, len(word_boxes)):
                # Extract bboxes
                if hasattr(word_boxes[i], 'bbox'):
                    bbox1 = word_boxes[i].bbox
                    bbox2 = word_boxes[j].bbox
                elif isinstance(word_boxes[i], dict):
                    bbox1 = word_boxes[i].get('bbox', [])
                    bbox2 = word_boxes[j].get('bbox', [])
                else:
                    continue
                
                if len(bbox1) != 4 or len(bbox2) != 4:
                    continue
                
                # Calculate overlap
                x1, y1, w1, h1 = bbox1
                x2, y2, w2, h2 = bbox2
                
                # Check if boxes overlap
                overlap_x = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
                overlap_y = max(0, min(y1 + h1, y2 + h2) - max(y1, y2))
                
                if overlap_x > 0 and overlap_y > 0:
                    overlap_area = overlap_x * overlap_y
                    box1_area = w1 * h1
                    box2_area = w2 * h2
                    
                    # Allow small overlaps (< 10% of smaller box)
                    min_area = min(box1_area, box2_area)
                    overlap_ratio = overlap_area / min_area if min_area > 0 else 0
                    
                    if overlap_ratio > 0.1:  # More than 10% overlap is suspicious
                        overlap_count += 1
                        self.logger.debug(
                            f"Word boxes {i} and {j} overlap by {overlap_ratio:.1%}"
                        )
        
        return overlap_count
    
    def validate_key_value_pairs(
        self,
        key_value_pairs: List[Any],
        page_bbox: List[int]
    ) -> Tuple[bool, int]:
        """
        Validate key-value pair structural integrity.
        
        Checks:
        - Each value has an associated key (no orphaned values)
        - Key and value bboxes are valid
        - Confidence scores are valid
        
        Args:
            key_value_pairs: List of key-value pairs
            page_bbox: Page bounding box [x, y, width, height]
        
        Returns:
            Tuple of (all_valid, num_invalid)
        """
        if not key_value_pairs:
            return True, 0
        
        all_valid = True
        num_invalid = 0
        
        for i, pair in enumerate(key_value_pairs):
            # Extract fields
            if hasattr(pair, 'key'):
                key = pair.key
                key_bbox = pair.key_bbox
                value = pair.value
                value_bbox = pair.value_bbox
                confidence = pair.confidence
            elif isinstance(pair, dict):
                key = pair.get('key', '')
                key_bbox = pair.get('key_bbox', [])
                value = pair.get('value', '')
                value_bbox = pair.get('value_bbox', [])
                confidence = pair.get('confidence', 0.0)
            else:
                self.warnings.append(ValidationWarning(
                    code="INVALID_KV_PAIR_FORMAT",
                    message=f"Key-value pair {i} has invalid format",
                    severity="high",
                    details={"index": i, "type": type(pair).__name__}
                ))
                all_valid = False
                num_invalid += 1
                continue
            
            # Check for orphaned values (value without key)
            if not key or not key.strip():
                self.warnings.append(ValidationWarning(
                    code="ORPHANED_VALUE",
                    message=f"Key-value pair {i} has empty key (orphaned value)",
                    severity="high",
                    details={"index": i, "value": value}
                ))
                all_valid = False
                num_invalid += 1
            
            # Validate key bbox
            if not self.validate_bounding_box(key_bbox, page_bbox, f"Key '{key}'"):
                all_valid = False
                num_invalid += 1
            
            # Validate value bbox
            if not self.validate_bounding_box(value_bbox, page_bbox, f"Value for key '{key}'"):
                all_valid = False
                num_invalid += 1
            
            # Validate confidence
            if not self.validate_confidence_score(confidence, f"Key-value pair '{key}'"):
                all_valid = False
                num_invalid += 1
        
        return all_valid, num_invalid
    
    def validate_extraction_result(
        self,
        result: Dict[str, Any],
        page_bbox: List[int]
    ) -> Dict[str, Any]:
        """
        Validate complete extraction result.
        
        Args:
            result: Extraction result dictionary
            page_bbox: Page bounding box [x, y, width, height]
        
        Returns:
            Validation summary with warnings
        """
        self.warnings = []  # Reset warnings
        
        validation_summary = {
            "valid": True,
            "warnings": [],
            "stats": {
                "total_elements": 0,
                "invalid_elements": 0,
                "low_confidence_count": 0
            }
        }
        
        # Validate word boxes if present
        if 'word_boxes' in result and result['word_boxes']:
            word_boxes = result['word_boxes']
            all_valid, num_invalid = self.validate_word_boxes(word_boxes, page_bbox)
            
            validation_summary["stats"]["total_elements"] += len(word_boxes)
            validation_summary["stats"]["invalid_elements"] += num_invalid
            
            if not all_valid:
                validation_summary["valid"] = False
        
        # Validate key-value pairs if present
        if 'key_value_pairs' in result and result['key_value_pairs']:
            kv_pairs = result['key_value_pairs']
            all_valid, num_invalid = self.validate_key_value_pairs(kv_pairs, page_bbox)
            
            validation_summary["stats"]["total_elements"] += len(kv_pairs)
            validation_summary["stats"]["invalid_elements"] += num_invalid
            
            if not all_valid:
                validation_summary["valid"] = False
        
        # Validate general bounding boxes if present
        if 'bounding_boxes' in result and result['bounding_boxes']:
            for i, bbox_item in enumerate(result['bounding_boxes']):
                if isinstance(bbox_item, dict):
                    bbox = bbox_item.get('bbox', [])
                    confidence = bbox_item.get('confidence', 1.0)
                    
                    self.validate_bounding_box(bbox, page_bbox, f"Element {i}")
                    self.validate_confidence_score(confidence, f"Element {i}")
                    
                    validation_summary["stats"]["total_elements"] += 1
        
        # Count low confidence warnings
        low_conf_warnings = [w for w in self.warnings if w.code == "LOW_CONFIDENCE"]
        validation_summary["stats"]["low_confidence_count"] = len(low_conf_warnings)
        
        # Check if more than 20% have low confidence
        total = validation_summary["stats"]["total_elements"]
        if total > 0:
            low_conf_ratio = len(low_conf_warnings) / total
            if low_conf_ratio > 0.2:
                self.warnings.append(ValidationWarning(
                    code="HIGH_LOW_CONFIDENCE_RATIO",
                    message=f"{low_conf_ratio:.1%} of extracted content has low confidence (>20% threshold)",
                    severity="high",
                    details={
                        "low_confidence_count": len(low_conf_warnings),
                        "total_elements": total,
                        "ratio": low_conf_ratio
                    }
                ))
                validation_summary["valid"] = False
        
        # Convert warnings to dict format
        validation_summary["warnings"] = [
            {
                "code": w.code,
                "message": w.message,
                "severity": w.severity,
                "details": w.details
            }
            for w in self.warnings
        ]
        
        # Log summary
        if self.warnings:
            self.logger.warning(
                f"Validation found {len(self.warnings)} warnings "
                f"({validation_summary['stats']['invalid_elements']} invalid elements)"
            )
        else:
            self.logger.info("Validation passed with no warnings")
        
        return validation_summary
    
    def get_warnings(self) -> List[ValidationWarning]:
        """Get all validation warnings."""
        return self.warnings
    
    def clear_warnings(self):
        """Clear all validation warnings."""
        self.warnings = []
    
    def validate_structured_format_roundtrip(
        self,
        original_content: str,
        structured_output: Dict[str, Any]
    ) -> Tuple[bool, float]:
        """
        Validate structured format extraction via round-trip test.
        
        Extracts with structured format, reconstructs document,
        and verifies content preservation.
        
        Args:
            original_content: Original extracted text content
            structured_output: Structured format output with sections
        
        Returns:
            Tuple of (content_preserved, similarity_score)
        """
        if not structured_output or 'sections' not in structured_output:
            self.warnings.append(ValidationWarning(
                code="INVALID_STRUCTURED_FORMAT",
                message="Structured output missing 'sections' field",
                severity="high",
                details={"structured_output": structured_output}
            ))
            return False, 0.0
        
        # Reconstruct content from structured format
        reconstructed_lines = []
        
        for section in structured_output['sections']:
            # Add heading if present
            if 'heading' in section and section['heading']:
                heading = section['heading']
                level = section.get('level', 1)
                
                # Format heading based on level
                if level > 0:
                    reconstructed_lines.append(f"{'#' * level} {heading}")
                else:
                    reconstructed_lines.append(heading)
            
            # Add content
            if 'content' in section and section['content']:
                if isinstance(section['content'], list):
                    reconstructed_lines.extend(section['content'])
                else:
                    reconstructed_lines.append(str(section['content']))
            
            # Add blank line between sections
            reconstructed_lines.append('')
        
        reconstructed_content = '\n'.join(reconstructed_lines).strip()
        
        # Normalize both contents for comparison
        original_normalized = self._normalize_text(original_content)
        reconstructed_normalized = self._normalize_text(reconstructed_content)
        
        # Calculate similarity score
        similarity = self._calculate_text_similarity(
            original_normalized,
            reconstructed_normalized
        )
        
        # Check if content is preserved (>95% similarity)
        content_preserved = similarity >= 0.95
        
        if not content_preserved:
            self.warnings.append(ValidationWarning(
                code="CONTENT_NOT_PRESERVED",
                message=f"Structured format round-trip lost content (similarity: {similarity:.1%})",
                severity="high",
                details={
                    "similarity_score": similarity,
                    "original_length": len(original_normalized),
                    "reconstructed_length": len(reconstructed_normalized)
                }
            ))
        elif similarity < 1.0:
            self.warnings.append(ValidationWarning(
                code="MINOR_CONTENT_DIFFERENCES",
                message=f"Minor differences in round-trip (similarity: {similarity:.1%})",
                severity="low",
                details={"similarity_score": similarity}
            ))
        
        self.logger.info(
            f"Structured format round-trip validation: "
            f"preserved={content_preserved}, similarity={similarity:.1%}"
        )
        
        return content_preserved, similarity
    
    def _normalize_text(self, text: str) -> str:
        """
        Normalize text for comparison.
        
        Removes extra whitespace, normalizes line endings, etc.
        
        Args:
            text: Text to normalize
        
        Returns:
            Normalized text
        """
        if not text:
            return ""
        
        # Normalize line endings
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # Remove extra whitespace
        lines = [line.strip() for line in text.split('\n')]
        
        # Remove empty lines
        lines = [line for line in lines if line]
        
        # Join with single newline
        return '\n'.join(lines)
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate similarity between two texts.
        
        Uses a simple character-based similarity metric.
        For production, could use more sophisticated metrics like
        Levenshtein distance or semantic similarity.
        
        Args:
            text1: First text
            text2: Second text
        
        Returns:
            Similarity score between 0.0 and 1.0
        """
        if not text1 and not text2:
            return 1.0
        
        if not text1 or not text2:
            return 0.0
        
        # Simple character-level similarity
        # Count matching characters in order
        len1 = len(text1)
        len2 = len(text2)
        
        # Use longest common subsequence approach (simplified)
        # For production, use difflib or similar
        import difflib
        
        matcher = difflib.SequenceMatcher(None, text1, text2)
        similarity = matcher.ratio()
        
        return similarity
