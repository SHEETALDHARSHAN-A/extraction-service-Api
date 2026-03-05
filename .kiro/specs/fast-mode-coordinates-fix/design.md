# Fast Mode Coordinates Fix - Bugfix Design

## Overview

The `build_line_bounding_boxes()` function in the GLM-OCR service has a bug in its bbox height calculation for the last line. The current implementation uses `max(1, height - i * line_h)` which can produce a height of 1 pixel even when there's more vertical space available. This causes the last line's bbox to be incorrectly sized, potentially extending beyond the page boundary or being too small. The fix simplifies the calculation to `height - i * line_h`, ensuring the last line's bbox height accurately represents the remaining vertical space within the page boundaries.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug - when calculating the last line's bbox height and the remaining height is less than line_h
- **Property (P)**: The desired behavior - the last line's bbox height should equal the remaining vertical space (height - i * line_h) without artificial constraints
- **Preservation**: All other bbox calculations and function behavior must remain unchanged
- **build_line_bounding_boxes**: The function in `services/glm-ocr-service/app/main.py` that creates approximate line-level bounding boxes for fast mode OCR
- **line_h**: The calculated height per line using integer division (height // len(lines))
- **page_bbox**: The [x, y, width, height] coordinates defining the page boundaries

## Bug Details

### Fault Condition

The bug manifests when calculating the bbox height for any line where the remaining vertical space (height - i * line_h) is less than the standard line_h. The current implementation uses `max(1, height - i * line_h)` which forces a minimum height of 1 pixel, but this is unnecessary and can cause incorrect bbox sizing.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type {i: int, line_h: int, height: int}
  OUTPUT: boolean
  
  RETURN (height - i * line_h) < line_h
         AND (height - i * line_h) >= 0
         AND currentImplementationUsesMax1
END FUNCTION
```

### Examples

- **Example 1**: Page height=100, 3 lines, line_h=33
  - Line 0: y=0, height=min(33, max(1, 100))=33 ✓
  - Line 1: y=33, height=min(33, max(1, 67))=33 ✓
  - Line 2: y=66, height=min(33, max(1, 34))=33 ✓ (should be 34)
  
- **Example 2**: Page height=100, 4 lines, line_h=25
  - Line 3: y=75, height=min(25, max(1, 25))=25 ✓ (correct by coincidence)
  
- **Example 3**: Page height=100, 7 lines, line_h=14
  - Line 6: y=84, height=min(14, max(1, 16))=14 ✗ (should be 16)

- **Edge case**: Page height=10, 15 lines, line_h=1
  - Last line: height=min(1, max(1, negative))=1 ✗ (remaining space could be 0 or negative)

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Fast mode disabled with coordinates must continue to return page-level bounding boxes
- Empty or whitespace-only content must continue to return empty list
- Fast mode without coordinates must continue to skip bbox calculation
- Non-empty lines filtering must continue to work as before
- The x, y, and width components of bboxes must remain unchanged
- The line_h calculation (height // len(lines)) must remain unchanged
- The iteration order and line text extraction must remain unchanged

**Scope:**
All inputs that do NOT involve the last line's height calculation (or any line where remaining space < line_h) should be completely unaffected by this fix. This includes:
- All x, y, width calculations for all lines
- The line_h calculation itself
- Line text extraction and filtering
- Confidence and type fields in the bbox objects
- Function behavior for empty content or disabled fast mode

## Hypothesized Root Cause

Based on the bug description and code analysis, the root cause is:

1. **Overly Defensive Height Calculation**: The `max(1, height - i * line_h)` was likely added to prevent negative or zero heights, but this creates an artificial floor that doesn't reflect the actual remaining space. When the remaining height is legitimately less than line_h (due to integer division), the max(1, ...) constraint forces it to be at least 1, which is incorrect.

2. **Unnecessary Constraint**: The `min(line_h, ...)` already provides sufficient protection by capping the height at line_h. The additional `max(1, ...)` is redundant and causes incorrect sizing when the remaining space is naturally smaller than line_h.

3. **Integer Division Remainder**: When height is not evenly divisible by len(lines), the last line should get the remainder. The current code attempts to handle this but the max(1, ...) interferes with the correct calculation.

## Correctness Properties

Property 1: Fault Condition - Last Line Bbox Height Accuracy

_For any_ input where a line's remaining vertical space (height - i * line_h) is less than line_h and non-negative, the fixed function SHALL calculate the bbox height as exactly the remaining space without applying a minimum constraint of 1, ensuring accurate representation of the line's vertical extent within page boundaries.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation - Non-Last-Line Bbox Calculations

_For any_ input where a line's remaining vertical space (height - i * line_h) is greater than or equal to line_h, the fixed function SHALL produce exactly the same bbox calculations as the original function, preserving all x, y, width, and height values for lines that are not affected by the bug condition.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

## Fix Implementation

### Changes Required

**File**: `services/glm-ocr-service/app/main.py`

**Function**: `build_line_bounding_boxes`

**Specific Changes**:
1. **Line 134 - Simplify Height Calculation**: Remove the `max(1, ...)` wrapper from the height calculation
   - Current: `"bbox": [x, y + i * line_h, width, min(line_h, max(1, height - i * line_h))]`
   - Fixed: `"bbox": [x, y + i * line_h, width, min(line_h, height - i * line_h)]`
   - Rationale: The `min(line_h, ...)` already provides sufficient protection, and removing `max(1, ...)` allows the remaining space to be accurately represented

2. **No Additional Changes Required**: The fix is a single-line change that removes an unnecessary constraint. All other logic remains intact.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Fault Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm that the current implementation produces incorrect bbox heights when the remaining space is less than line_h.

**Test Plan**: Write tests that call `build_line_bounding_boxes()` with various page heights and line counts where height % len(lines) != 0. Run these tests on the UNFIXED code to observe incorrect height calculations for the last line.

**Test Cases**:
1. **Uneven Division Test**: height=100, 3 lines → last line should have height=34, not 33 (will fail on unfixed code)
2. **Large Remainder Test**: height=100, 7 lines → last line should have height=16, not 14 (will fail on unfixed code)
3. **Small Page Test**: height=50, 8 lines → last line should have height=8, not 6 (will fail on unfixed code)
4. **Edge Case Test**: height=10, 15 lines → verify behavior when remaining space approaches 0 (may fail on unfixed code)

**Expected Counterexamples**:
- Last line bbox heights are smaller than the actual remaining vertical space
- Possible causes: the `max(1, ...)` constraint interfering with accurate height calculation

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := build_line_bounding_boxes_fixed(content, page_bbox, confidence)
  last_line := result[len(result) - 1]
  expected_height := height - (len(result) - 1) * line_h
  ASSERT last_line.bbox[3] == min(line_h, expected_height)
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT build_line_bounding_boxes_original(input) = build_line_bounding_boxes_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for cases where height is evenly divisible by line count, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Even Division Preservation**: Observe that height=100, 4 lines produces correct bboxes on unfixed code, then verify this continues after fix
2. **Empty Content Preservation**: Observe that empty content returns [] on unfixed code, then verify this continues after fix
3. **Single Line Preservation**: Observe that single-line content produces correct bbox on unfixed code, then verify this continues after fix
4. **X/Y/Width Preservation**: Observe that x, y, width values are correct on unfixed code for all lines, then verify these remain unchanged after fix

### Unit Tests

- Test bbox height calculation for various page heights and line counts with remainders
- Test edge cases (height < len(lines), height == len(lines), single line, empty content)
- Test that x, y, width components remain correct after fix
- Test that confidence and type fields are preserved

### Property-Based Tests

- Generate random page dimensions and line counts to verify last line height is always correct
- Generate random content with varying newline counts to verify all bbox calculations
- Test that all non-height components (x, y, width, text, confidence, type) remain unchanged across many scenarios

### Integration Tests

- Test full OCR flow with fast mode enabled and coordinates requested
- Test that downstream consumers of bbox data receive accurate coordinates
- Test that page boundary constraints are respected in all scenarios
