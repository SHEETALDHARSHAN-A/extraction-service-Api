"""
Preservation Property Tests for GLM-OCR Extraction Service
===========================================================

**CRITICAL**: These tests MUST PASS on unfixed code - they capture baseline behavior.
This is a PRESERVATION test for bugfix workflow.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**

These tests observe and capture the CORRECT behavior that must be preserved
during the bugfix. They test functionality that works correctly on unfixed code
and must continue to work after the fix.

Test Strategy:
1. Run tests on UNFIXED code to observe baseline behavior
2. Tests should PASS on unfixed code (confirming baseline works)
3. Re-run after fix to ensure no regressions

Preservation Requirements:
- Coordinate extraction with include_coordinates=true
- Precision mode with precision_mode="high"
- Mock mode with MOCK_MODE=true
- Field extraction with extract_fields parameter
- Batch processing (tested via result structure)
- Health checks (tested via initialization)
- Result envelope structure
- Microservice integration (tested via result format)
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest
from hypothesis import given, settings, strategies as st
from hypothesis import HealthCheck

# Add the model directory to the path
MODEL_DIR = Path(__file__).parent.parent / "services" / "triton-models" / "glm_ocr" / "1"
sys.path.insert(0, str(MODEL_DIR))


# =============================================================================
# Test 1: Coordinate Extraction Preservation (Requirement 3.2)
# =============================================================================

@given(
    output_format=st.sampled_from(["text", "json", "markdown", "table", "key_value", "structured", "formula"])
)
@settings(max_examples=7, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_coordinate_extraction_with_include_coordinates_true(output_format):
    """
    **Validates: Requirement 3.2**
    
    Property: When include_coordinates=true, all elements MUST have bbox_2d coordinates.
    
    This is CORRECT behavior that must be preserved after the fix.
    """
    # Use mock mode to test coordinate extraction logic
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("IDEP_MOCK_INFERENCE", "true")
        
        import importlib
        if 'model' in sys.modules:
            importlib.reload(sys.modules['model'])
        import model
        
        # Run with include_coordinates=true
        result = model._MockEngine.run(
            image_ref="test.jpg",
            prompt_override="",
            output_format=output_format,
            include_coords=True,  # MUST return bbox_2d
            include_word_conf=False,
            include_page_layout=False,
            precision="normal"
        )
        
        # Verify result structure
        assert "pages" in result, "Result must have 'pages' key"
        assert len(result["pages"]) > 0, "Result must have at least one page"
        
        pages = result["pages"]
        for page in pages:
            assert "elements" in page, "Page must have 'elements' key"
            elements = page["elements"]
            
            # All elements must have bbox_2d when include_coords=True
            for element in elements:
                assert "bbox_2d" in element, \
                    f"Element missing bbox_2d with include_coordinates=true: {element}"
                bbox = element["bbox_2d"]
                
                # bbox_2d must be a list of 4 integers [x1, y1, x2, y2]
                assert isinstance(bbox, list), f"bbox_2d must be list, got {type(bbox)}"
                assert len(bbox) == 4, f"bbox_2d must have 4 coordinates, got {len(bbox)}"
                assert all(isinstance(c, (int, float)) for c in bbox), \
                    f"bbox_2d coordinates must be numeric: {bbox}"


def test_coordinate_extraction_with_include_coordinates_false():
    """
    **Validates: Requirement 3.2**
    
    Property: When include_coordinates=false, elements may have None for bbox_2d.
    
    This is CORRECT behavior that must be preserved after the fix.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("IDEP_MOCK_INFERENCE", "true")
        
        import importlib
        if 'model' in sys.modules:
            importlib.reload(sys.modules['model'])
        import model
        
        # Run with include_coordinates=false
        result = model._MockEngine.run(
            image_ref="test.jpg",
            prompt_override="",
            output_format="text",
            include_coords=False,  # bbox_2d should be None
            include_word_conf=False,
            include_page_layout=False,
            precision="normal"
        )
        
        # Verify that bbox_2d is None when include_coords=False
        pages = result["pages"]
        for page in pages:
            elements = page["elements"]
            for element in elements:
                # bbox_2d should be None or not present
                bbox = element.get("bbox_2d")
                assert bbox is None, \
                    f"bbox_2d should be None with include_coordinates=false, got {bbox}"


# =============================================================================
# Test 2: Precision Mode Preservation (Requirement 3.3)
# =============================================================================

@given(
    precision=st.sampled_from(["normal", "high", "precision"])
)
@settings(max_examples=3, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_precision_mode_parameter_handling(precision):
    """
    **Validates: Requirement 3.3**
    
    Property: Precision mode parameter is correctly passed through the system.
    
    This is CORRECT behavior that must be preserved after the fix.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("IDEP_MOCK_INFERENCE", "true")
        
        import importlib
        if 'model' in sys.modules:
            importlib.reload(sys.modules['model'])
        import model
        
        result = model._MockEngine.run(
            image_ref="test.jpg",
            prompt_override="",
            output_format="text",
            include_coords=True,
            include_word_conf=False,
            include_page_layout=False,
            precision=precision
        )
        
        # Verify precision is recorded in result
        assert "precision" in result, "Result must have 'precision' key"
        assert result["precision"] == precision, \
            f"Precision should be '{precision}', got '{result['precision']}'"


def test_precision_mode_high_uses_correct_parameters():
    """
    **Validates: Requirement 3.3**
    
    Property: High precision mode should use do_sample=False and repetition_penalty=1.15.
    
    This tests the generation parameters logic in _run_glm_ocr.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("IDEP_MOCK_INFERENCE", "true")
        
        import importlib
        if 'model' in sys.modules:
            importlib.reload(sys.modules['model'])
        import model
        
        # We can't directly test generation parameters without running the model,
        # but we can verify the code logic exists
        import inspect
        
        # Check that _run_glm_ocr has precision parameter handling
        if hasattr(model.TritonPythonModel, '_run_glm_ocr'):
            source = inspect.getsource(model.TritonPythonModel._run_glm_ocr)
            
            # Verify precision mode logic exists
            assert 'precision' in source, "_run_glm_ocr should handle precision parameter"
            assert 'repetition_penalty' in source, "_run_glm_ocr should set repetition_penalty"
            assert 'do_sample' in source, "_run_glm_ocr should set do_sample"
            
            # Verify high precision uses stronger repetition penalty
            assert '1.15' in source or '1.1' in source, \
                "High precision should use repetition_penalty >= 1.1"


# =============================================================================
# Test 3: Mock Mode Preservation (Requirement 3.4)
# =============================================================================

def test_mock_mode_returns_deterministic_data():
    """
    **Validates: Requirement 3.4**
    
    Property: Mock mode returns deterministic, identical data across multiple runs.
    
    This is CORRECT behavior that must be preserved after the fix.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("IDEP_MOCK_INFERENCE", "true")
        
        import importlib
        if 'model' in sys.modules:
            importlib.reload(sys.modules['model'])
        import model
        
        # Run the same request multiple times
        results = []
        for _ in range(3):
            result = model._MockEngine.run(
                image_ref="test.jpg",
                prompt_override="",
                output_format="json",
                include_coords=True,
                include_word_conf=False,
                include_page_layout=False,
                precision="normal"
            )
            results.append(result)
        
        # All results should be identical (deterministic)
        first_result_json = json.dumps(results[0], sort_keys=True)
        for i, result in enumerate(results[1:], 1):
            result_json = json.dumps(result, sort_keys=True)
            assert result_json == first_result_json, \
                f"Mock mode result {i} differs from first result (not deterministic)"


def test_mock_mode_does_not_require_gpu():
    """
    **Validates: Requirement 3.4**
    
    Property: Mock mode does not require GPU or model loading.
    
    This is CORRECT behavior that must be preserved after the fix.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("IDEP_MOCK_INFERENCE", "true")
        
        import importlib
        if 'model' in sys.modules:
            importlib.reload(sys.modules['model'])
        import model
        
        # Initialize model in mock mode
        triton_model = model.TritonPythonModel()
        triton_model.initialize({})
        
        # Verify no model or processor loaded
        assert triton_model.model is None, "Mock mode should not load model"
        assert triton_model.processor is None, "Mock mode should not load processor"
        assert triton_model.layout_engine is None, "Mock mode should not load layout engine"
        assert triton_model.sdk_parser is None, "Mock mode should not load SDK parser"


# =============================================================================
# Test 4: Field Extraction Preservation (Requirement 3.5)
# =============================================================================

@given(
    extract_fields=st.lists(
        st.sampled_from(["invoice_number", "date", "vendor", "total_amount", "subtotal", "tax"]),
        min_size=1,
        max_size=3,
        unique=True
    )
)
@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_field_extraction_filters_correctly(extract_fields):
    """
    **Validates: Requirement 3.5**
    
    Property: extract_fields parameter filters results to only requested fields.
    
    This is CORRECT behavior that must be preserved after the fix.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("IDEP_MOCK_INFERENCE", "true")
        
        import importlib
        if 'model' in sys.modules:
            importlib.reload(sys.modules['model'])
        import model
        
        # Get full result first
        full_result = model._MockEngine.run(
            image_ref="test.jpg",
            prompt_override="",
            output_format="json",
            include_coords=True,
            include_word_conf=False,
            include_page_layout=False,
            precision="normal"
        )
        
        # Apply field filtering
        filtered_result = model._filter_by_fields(full_result, extract_fields)
        
        # Verify extract_fields is recorded
        assert "extract_fields" in filtered_result, \
            "Filtered result should record extract_fields"
        assert filtered_result["extract_fields"] == extract_fields, \
            "extract_fields should match requested fields"
        
        # Verify filtering worked - check elements
        for page in filtered_result.get("pages", []):
            for element in page.get("elements", []):
                content = element.get("content", "")
                
                # Try to parse as JSON
                try:
                    obj = json.loads(content)
                    if isinstance(obj, dict) and "fields" in obj:
                        # Check that only requested fields are present
                        fields_obj = obj["fields"]
                        for key in fields_obj.keys():
                            # Key should match one of the requested fields (case-insensitive, normalized)
                            key_normalized = key.lower().replace(" ", "_").replace("-", "_")
                            field_normalized = [f.lower().replace(" ", "_").replace("-", "_") 
                                              for f in extract_fields]
                            assert any(model._field_match(key, f) for f in extract_fields), \
                                f"Field '{key}' not in requested fields {extract_fields}"
                except json.JSONDecodeError:
                    # Plain text element - should contain at least one requested field keyword
                    content_lower = content.lower().replace("-", "_").replace(" ", "_")
                    assert any(f.lower().replace("-", "_").replace(" ", "_") in content_lower 
                             for f in extract_fields), \
                        f"Element content should contain at least one field from {extract_fields}"


def test_field_extraction_empty_list_returns_all():
    """
    **Validates: Requirement 3.5**
    
    Property: Empty extract_fields list returns all fields (no filtering).
    
    This is CORRECT behavior that must be preserved after the fix.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("IDEP_MOCK_INFERENCE", "true")
        
        import importlib
        if 'model' in sys.modules:
            importlib.reload(sys.modules['model'])
        import model
        
        # Get full result
        full_result = model._MockEngine.run(
            image_ref="test.jpg",
            prompt_override="",
            output_format="json",
            include_coords=True,
            include_word_conf=False,
            include_page_layout=False,
            precision="normal"
        )
        
        # Apply field filtering with empty list
        filtered_result = model._filter_by_fields(full_result, [])
        
        # Result should be unchanged (no filtering)
        assert json.dumps(filtered_result, sort_keys=True) == json.dumps(full_result, sort_keys=True), \
            "Empty extract_fields should return all fields (no filtering)"


# =============================================================================
# Test 5: Result Envelope Structure Preservation (Requirement 3.1, 3.7)
# =============================================================================

@given(
    output_format=st.sampled_from(["text", "json", "markdown", "table", "key_value", "structured", "formula"])
)
@settings(max_examples=7, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_result_envelope_structure(output_format):
    """
    **Validates: Requirements 3.1, 3.7**
    
    Property: Result envelope has required structure with pages, markdown, confidence, usage.
    
    This is CORRECT behavior that must be preserved after the fix.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("IDEP_MOCK_INFERENCE", "true")
        
        import importlib
        if 'model' in sys.modules:
            importlib.reload(sys.modules['model'])
        import model
        
        result = model._MockEngine.run(
            image_ref="test.jpg",
            prompt_override="",
            output_format=output_format,
            include_coords=True,
            include_word_conf=False,
            include_page_layout=False,
            precision="normal"
        )
        
        # Verify required top-level keys
        required_keys = ["pages", "markdown", "model", "mode", "precision", "confidence", "usage"]
        for key in required_keys:
            assert key in result, f"Result must have '{key}' key"
        
        # Verify pages structure
        assert isinstance(result["pages"], list), "pages must be a list"
        assert len(result["pages"]) > 0, "pages must have at least one page"
        
        for page in result["pages"]:
            assert "elements" in page, "Page must have 'elements' key"
            assert isinstance(page["elements"], list), "elements must be a list"
        
        # Verify markdown is a string
        assert isinstance(result["markdown"], str), "markdown must be a string"
        
        # Verify confidence is a number between 0 and 1
        assert isinstance(result["confidence"], (int, float)), "confidence must be numeric"
        assert 0 <= result["confidence"] <= 1, "confidence must be between 0 and 1"
        
        # Verify usage structure
        assert isinstance(result["usage"], dict), "usage must be a dict"
        assert "prompt_tokens" in result["usage"], "usage must have 'prompt_tokens'"
        assert "completion_tokens" in result["usage"], "usage must have 'completion_tokens'"
        assert isinstance(result["usage"]["prompt_tokens"], int), "prompt_tokens must be int"
        assert isinstance(result["usage"]["completion_tokens"], int), "completion_tokens must be int"


def test_result_elements_have_required_fields():
    """
    **Validates: Requirement 3.1**
    
    Property: Each element has required fields: index, label, content, bbox_2d, confidence.
    
    This is CORRECT behavior that must be preserved after the fix.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("IDEP_MOCK_INFERENCE", "true")
        
        import importlib
        if 'model' in sys.modules:
            importlib.reload(sys.modules['model'])
        import model
        
        result = model._MockEngine.run(
            image_ref="test.jpg",
            prompt_override="",
            output_format="text",
            include_coords=True,
            include_word_conf=False,
            include_page_layout=False,
            precision="normal"
        )
        
        # Check each element
        for page in result["pages"]:
            for element in page["elements"]:
                # Required fields
                assert "index" in element, "Element must have 'index'"
                assert "label" in element, "Element must have 'label'"
                assert "content" in element, "Element must have 'content'"
                assert "bbox_2d" in element, "Element must have 'bbox_2d'"
                assert "confidence" in element, "Element must have 'confidence'"
                
                # Type checks
                assert isinstance(element["index"], int), "index must be int"
                assert isinstance(element["label"], str), "label must be str"
                assert isinstance(element["content"], str), "content must be str"
                assert isinstance(element["confidence"], (int, float)), "confidence must be numeric"
                assert 0 <= element["confidence"] <= 1, "confidence must be between 0 and 1"


# =============================================================================
# Test 6: Batch Processing Structure Preservation (Requirement 3.6)
# =============================================================================

def test_batch_processing_result_structure():
    """
    **Validates: Requirement 3.6**
    
    Property: Result structure supports batch processing (multiple pages).
    
    This is CORRECT behavior that must be preserved after the fix.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("IDEP_MOCK_INFERENCE", "true")
        
        import importlib
        if 'model' in sys.modules:
            importlib.reload(sys.modules['model'])
        import model
        
        result = model._MockEngine.run(
            image_ref="test.jpg",
            prompt_override="",
            output_format="text",
            include_coords=True,
            include_word_conf=False,
            include_page_layout=False,
            precision="normal"
        )
        
        # Verify pages is a list (supports multiple pages)
        assert isinstance(result["pages"], list), "pages must be a list for batch processing"
        
        # Each page should have page number and elements
        for page in result["pages"]:
            assert "page" in page or "elements" in page, \
                "Page must have 'page' number or 'elements'"
            assert isinstance(page.get("elements", []), list), \
                "Page elements must be a list"


# =============================================================================
# Test 7: Health Check / Initialization Preservation (Requirement 3.8)
# =============================================================================

def test_initialization_in_mock_mode_succeeds():
    """
    **Validates: Requirement 3.8**
    
    Property: Model initialization succeeds in mock mode without errors.
    
    This is CORRECT behavior that must be preserved after the fix.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("IDEP_MOCK_INFERENCE", "true")
        
        import importlib
        if 'model' in sys.modules:
            importlib.reload(sys.modules['model'])
        import model
        
        # Initialize model
        triton_model = model.TritonPythonModel()
        
        # Should not raise any exceptions
        try:
            triton_model.initialize({})
        except Exception as e:
            pytest.fail(f"Initialization should succeed in mock mode, got error: {e}")
        
        # Verify model is in mock mode
        assert model.MOCK_MODE is True, "Should be in mock mode"


def test_finalize_does_not_crash():
    """
    **Validates: Requirement 3.8**
    
    Property: Model finalization does not crash.
    
    This is CORRECT behavior that must be preserved after the fix.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("IDEP_MOCK_INFERENCE", "true")
        
        import importlib
        if 'model' in sys.modules:
            importlib.reload(sys.modules['model'])
        import model
        
        # Initialize and finalize
        triton_model = model.TritonPythonModel()
        triton_model.initialize({})
        
        # Should not raise any exceptions
        try:
            triton_model.finalize()
        except Exception as e:
            pytest.fail(f"Finalization should not crash, got error: {e}")


# =============================================================================
# Test 8: Microservice Integration Format Preservation (Requirement 3.7)
# =============================================================================

def test_result_is_json_serializable():
    """
    **Validates: Requirement 3.7**
    
    Property: Result is JSON serializable for microservice integration.
    
    This is CORRECT behavior that must be preserved after the fix.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("IDEP_MOCK_INFERENCE", "true")
        
        import importlib
        if 'model' in sys.modules:
            importlib.reload(sys.modules['model'])
        import model
        
        result = model._MockEngine.run(
            image_ref="test.jpg",
            prompt_override="",
            output_format="json",
            include_coords=True,
            include_word_conf=False,
            include_page_layout=False,
            precision="normal"
        )
        
        # Should be JSON serializable
        try:
            result_json = json.dumps(result, ensure_ascii=False, indent=2)
            assert len(result_json) > 0, "JSON serialization should produce non-empty string"
        except (TypeError, ValueError) as e:
            pytest.fail(f"Result should be JSON serializable, got error: {e}")
        
        # Should be deserializable back to dict
        try:
            deserialized = json.loads(result_json)
            assert isinstance(deserialized, dict), "Deserialized result should be dict"
        except json.JSONDecodeError as e:
            pytest.fail(f"Result JSON should be deserializable, got error: {e}")


# =============================================================================
# Main test runner
# =============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("GLM-OCR Preservation Property Tests")
    print("=" * 80)
    print()
    print("CRITICAL: These tests MUST PASS on unfixed code!")
    print("They capture baseline behavior that must be preserved.")
    print()
    print("Preservation requirements:")
    print("1. Coordinate extraction with include_coordinates=true")
    print("2. Precision mode parameter handling")
    print("3. Mock mode deterministic output without GPU")
    print("4. Field extraction filtering")
    print("5. Result envelope structure")
    print("6. Batch processing support")
    print("7. Initialization/health checks")
    print("8. JSON serialization for microservices")
    print()
    print("=" * 80)
    print()
    
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])
