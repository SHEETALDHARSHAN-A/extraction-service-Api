"""Bug condition exploration test for build_line_bounding_boxes.

This test is designed to FAIL on unfixed code to confirm the bug exists.
The bug: last line bbox height is calculated incorrectly when height % len(lines) != 0.

**Validates: Requirements 2.1, 2.2, 2.3**
"""

import pytest
from hypothesis import given, strategies as st, example
from app.main import build_line_bounding_boxes


class TestBugConditionExploration:
    """Property 1: Fault Condition - Last Line Bbox Height Accuracy
    
    CRITICAL: This test MUST FAIL on unfixed code - failure confirms the bug exists.
    DO NOT attempt to fix the test or the code when it fails.
    
    The test verifies that for inputs where (height - i * line_h) < line_h AND 
    (height - i * line_h) >= 0, the bbox height calculation should be accurate.
    
    Expected behavior: last_line.bbox[3] == min(line_h, height - (len(result) - 1) * line_h)
    Current buggy behavior: Uses max(1, height - i * line_h) which produces incorrect heights
    """
    
    @pytest.mark.unit
    def test_last_line_height_100_3_lines(self):
        """Test case: height=100 with 3 lines.
        
        Expected: last line should have height=34 (remaining space)
        Bug: last line has height=33 (capped by line_h)
        
        Calculation:
        - line_h = 100 // 3 = 33
        - Line 0: y=0, height=min(33, max(1, 100-0*33))=min(33, 100)=33 ✓
        - Line 1: y=33, height=min(33, max(1, 100-1*33))=min(33, 67)=33 ✓
        - Line 2: y=66, height=min(33, max(1, 100-2*33))=min(33, 34)=33 ✗ (should be 34)
        """
        content = "Line 1\nLine 2\nLine 3"
        page_bbox = [0, 0, 100, 100]
        confidence = 0.95
        
        result = build_line_bounding_boxes(content, page_bbox, confidence)
        
        assert len(result) == 3, "Should have 3 lines"
        
        # Calculate expected values
        height = 100
        line_h = height // len(result)  # 33
        
        # Check last line
        last_line = result[-1]
        expected_last_height = height - (len(result) - 1) * line_h  # 100 - 2*33 = 34
        actual_last_height = last_line["bbox"][3]
        
        assert actual_last_height == min(line_h, expected_last_height), \
            f"Last line height should be {min(line_h, expected_last_height)}, got {actual_last_height}"
    
    @pytest.mark.unit
    def test_last_line_height_100_7_lines(self):
        """Test case: height=100 with 7 lines.
        
        Expected: last line should have height=16 (remaining space)
        Bug: last line has height=14 (capped by line_h)
        
        Calculation:
        - line_h = 100 // 7 = 14
        - Line 6: y=84, height=min(14, max(1, 100-6*14))=min(14, 16)=14 ✗ (should be 16)
        """
        content = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6\nLine 7"
        page_bbox = [0, 0, 100, 100]
        confidence = 0.95
        
        result = build_line_bounding_boxes(content, page_bbox, confidence)
        
        assert len(result) == 7, "Should have 7 lines"
        
        # Calculate expected values
        height = 100
        line_h = height // len(result)  # 14
        
        # Check last line
        last_line = result[-1]
        expected_last_height = height - (len(result) - 1) * line_h  # 100 - 6*14 = 16
        actual_last_height = last_line["bbox"][3]
        
        assert actual_last_height == min(line_h, expected_last_height), \
            f"Last line height should be {min(line_h, expected_last_height)}, got {actual_last_height}"
    
    @pytest.mark.unit
    def test_last_line_height_50_8_lines(self):
        """Test case: height=50 with 8 lines.
        
        Expected: last line should have height=8 (remaining space)
        Bug: last line has height=6 (capped by line_h)
        
        Calculation:
        - line_h = 50 // 8 = 6
        - Line 7: y=42, height=min(6, max(1, 50-7*6))=min(6, 8)=6 ✗ (should be 8)
        """
        content = "L1\nL2\nL3\nL4\nL5\nL6\nL7\nL8"
        page_bbox = [0, 0, 100, 50]
        confidence = 0.95
        
        result = build_line_bounding_boxes(content, page_bbox, confidence)
        
        assert len(result) == 8, "Should have 8 lines"
        
        # Calculate expected values
        height = 50
        line_h = height // len(result)  # 6
        
        # Check last line
        last_line = result[-1]
        expected_last_height = height - (len(result) - 1) * line_h  # 50 - 7*6 = 8
        actual_last_height = last_line["bbox"][3]
        
        assert actual_last_height == min(line_h, expected_last_height), \
            f"Last line height should be {min(line_h, expected_last_height)}, got {actual_last_height}"
    
    @pytest.mark.unit
    @given(
        height=st.integers(min_value=10, max_value=200),
        num_lines=st.integers(min_value=2, max_value=20)
    )
    @example(height=100, num_lines=3)
    @example(height=100, num_lines=7)
    @example(height=50, num_lines=8)
    def test_last_line_height_property(self, height: int, num_lines: int):
        """Property-based test: Last line bbox height should equal remaining vertical space.
        
        For any page height and number of lines where height % num_lines != 0,
        the last line's bbox height should be exactly the remaining space:
        height - (num_lines - 1) * line_h
        
        This property WILL FAIL on unfixed code when the remaining space is less than line_h.
        """
        # Create content with the specified number of lines
        content = "\n".join([f"Line {i+1}" for i in range(num_lines)])
        page_bbox = [0, 0, 100, height]
        confidence = 0.95
        
        result = build_line_bounding_boxes(content, page_bbox, confidence)
        
        assert len(result) == num_lines, f"Should have {num_lines} lines"
        
        # Calculate expected values
        line_h = height // num_lines
        
        # Check last line
        last_line = result[-1]
        expected_last_height = height - (num_lines - 1) * line_h
        actual_last_height = last_line["bbox"][3]
        
        # The correct behavior: last line height should be the remaining space
        # (capped by line_h if remaining space is larger)
        expected_height = min(line_h, expected_last_height)
        
        assert actual_last_height == expected_height, \
            f"Last line height should be {expected_height}, got {actual_last_height} " \
            f"(height={height}, num_lines={num_lines}, line_h={line_h}, remaining={expected_last_height})"
