# Bugfix Requirements Document

## Introduction

The GLM-OCR service's fast mode with coordinates feature has a bug in the `build_line_bounding_boxes()` function that causes incorrect bounding box calculations. When `fast_mode=True` and `include_coordinates=True`, the function splits content by newlines and calculates approximate line-level bounding boxes. However, the current implementation has several issues:

1. The bbox height calculation uses simple division which can result in incorrect heights for the last line
2. The bbox calculation doesn't account for actual text positioning within the page
3. Edge cases like single-line content or content without newlines may produce inaccurate coordinates

This affects users who rely on fast mode for quick OCR processing with coordinate data, potentially causing downstream issues in document processing pipelines.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN content has multiple lines and fast_mode is enabled with coordinates THEN the system calculates line bounding boxes using `height // len(lines)` which may produce incorrect heights for the last line when height is not evenly divisible

1.2 WHEN the last line's calculated bbox extends beyond the page boundary THEN the system uses `min(line_h, max(1, height - i * line_h))` which can still result in bbox coordinates that don't accurately represent the actual line position

1.3 WHEN content is split by newlines THEN the system assumes equal spacing between lines which doesn't reflect actual text layout and vertical positioning

### Expected Behavior (Correct)

2.1 WHEN content has multiple lines and fast_mode is enabled with coordinates THEN the system SHALL calculate line bounding boxes with accurate heights that properly fit within the page boundaries

2.2 WHEN the last line's bbox is calculated THEN the system SHALL ensure the bbox height correctly represents the remaining vertical space without extending beyond the page boundary

2.3 WHEN content is split by newlines THEN the system SHALL calculate bounding boxes that accurately represent line positions within the page, accounting for proper vertical distribution

### Unchanged Behavior (Regression Prevention)

3.1 WHEN fast_mode is disabled and coordinates are requested THEN the system SHALL CONTINUE TO return page-level bounding boxes as before

3.2 WHEN content is empty or contains only whitespace THEN the system SHALL CONTINUE TO return an empty list of bounding boxes

3.3 WHEN fast_mode is enabled without coordinates THEN the system SHALL CONTINUE TO skip bounding box calculation entirely

3.4 WHEN content has valid lines after stripping whitespace THEN the system SHALL CONTINUE TO filter out empty lines and process only non-empty lines
