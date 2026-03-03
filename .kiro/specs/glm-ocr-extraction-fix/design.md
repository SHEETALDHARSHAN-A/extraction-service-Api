# GLM-OCR Extraction Service Bugfix Design

## Overview

The GLM-OCR document extraction service has multiple critical issues preventing reliable operation in production. The service uses Triton Inference Server to host a GLM-OCR model for GPU-accelerated document understanding, but currently fails at initialization and produces inconsistent outputs.

The fix strategy focuses on simplification and reliability:
1. Fix tokenizer initialization by properly configuring trust_remote_code and environment
2. Standardize output formats with strict schema validation
3. Simplify the codebase from 3 execution paths (SDK/native/mock) to a single clear path with fallbacks
4. Implement robust input validation and error handling
5. Ensure GPU → CPU → mock fallback works consistently

This is a refactoring-heavy bugfix that removes unnecessary abstractions while maintaining all existing functionality (coordinates, precision modes, batch processing, field extraction).

## Glossary

- **Bug_Condition (C)**: The conditions that trigger service failures - tokenizer import errors, output format mismatches, or input handling failures
- **Property (P)**: The desired behavior - successful model initialization on GPU, correctly formatted outputs matching schemas, proper handling of all valid inputs
- **Preservation**: Existing functionality that must remain unchanged - coordinate extraction, precision modes, batch processing, field filtering, mock mode, health checks
- **ChatGLMTokenizer**: Custom tokenizer class from zai-org/GLM-OCR that fails to import despite trust_remote_code=True
- **AutoProcessor**: Transformers class that loads tokenizer and image processor; currently fails with "ChatGLMTokenizer does not exist"
- **Output Format**: One of 7 supported types (text, json, markdown, table, key_value, structured, formula) that must match documented schemas
- **Execution Path**: Current code has 3 paths (SDK via glmocr package, native via transformers, mock for testing) causing complexity
- **PP-DocLayout-V3**: Layout detection model (stage 1) that identifies document regions before OCR
- **GLM-OCR**: Vision-language model (stage 2) that performs text/table/formula recognition on detected regions

## Bug Details

### Fault Condition

The bug manifests in multiple scenarios across initialization and inference phases. The service fails when attempting to load the model, when returning results to clients, or when processing certain input types.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type (InitializationContext | InferenceRequest)
  OUTPUT: boolean
  
  RETURN (input.phase == "initialization" 
          AND input.action == "load_tokenizer"
          AND tokenizerImportFails(input.model_path))
         OR (input.phase == "inference"
             AND input.action == "return_result"
             AND NOT outputMatchesSchema(input.result, input.requested_format))
         OR (input.phase == "inference"
             AND input.action == "process_input"
             AND (input.content_is_dynamic OR input.content_is_variable)
             AND inputHandlingFails(input))
         OR (input.phase == "execution"
             AND codeComplexityScore(input.code) > THRESHOLD
             AND multipleUncoordinatedFallbackPaths(input.code))
         OR (input.phase == "inference"
             AND input.custom_prompt_provided
             AND customPromptIgnored(input))
END FUNCTION
```

### Examples

**Tokenizer Initialization Failure:**
- Input: Triton server starts, calls `AutoProcessor.from_pretrained("zai-org/GLM-OCR", trust_remote_code=True)`
- Expected: Tokenizer loads successfully on GPU
- Actual: Raises `ValueError: Tokenizer class ChatGLMTokenizer does not exist or is not currently imported`
- Root cause: Custom tokenizer class not properly imported despite trust_remote_code flag

**Output Format Mismatch (JSON):**
- Input: Client requests `output_format="json"` for invoice extraction
- Expected: Returns `{"document_type": "invoice", "fields": {...}, "line_items": [...]}`
- Actual: Returns nested structure or plain text that fails JSON.parse() on client
- Root cause: Format conversion logic produces inconsistent structures

**Output Format Mismatch (Table):**
- Input: Client requests `output_format="table"` for tabular data
- Expected: Returns `[{"table_id": 1, "headers": [...], "rows": [[...]], "bbox_2d": [...]}]`
- Actual: Returns markdown table string or missing required fields
- Root cause: Table format builder doesn't follow schema specification

**Dynamic Input Handling:**
- Input: Client sends variable-length document with custom prompt
- Expected: Processes full document with custom prompt applied
- Actual: Truncates content or ignores custom prompt, uses default task prompt
- Root cause: Input validation missing, prompt override logic broken

**Code Complexity:**
- Input: Developer reviews model.py (850+ lines)
- Expected: Clear, maintainable code with single execution path
- Actual: 3 execution paths (SDK/native/mock) with unclear fallback coordination, multiple abstraction layers
- Root cause: Over-engineering, unnecessary SDK wrapper when native transformers works

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Coordinate extraction with `include_coordinates=true` must continue to return bbox_2d for all detected regions
- Precision mode with `precision_mode="high"` must continue to use appropriate generation parameters (do_sample=False, repetition_penalty=1.15)
- Mock mode with `MOCK_MODE=true` must continue to return deterministic test data without GPU
- Field extraction with `extract_fields=["date", "amount"]` must continue to filter results to requested fields
- Batch processing through temporal-worker must continue to handle multiple documents
- Health check endpoints must continue to report service status accurately
- Integration with microservices (api-gateway, preprocessing, post-processing) must remain unchanged
- Result envelope structure with pages, markdown, confidence, usage fields must remain consistent

**Scope:**
All inputs that do NOT trigger the bug conditions should be completely unaffected by this fix. This includes:
- Successful model loads on systems where tokenizer imports work
- Output formats that already match schemas correctly
- Simple static inputs that don't expose input handling issues
- Code paths that are already simple and maintainable
- Mock mode execution (no model loading)

## Hypothesized Root Cause

Based on the bug description and code analysis, the most likely issues are:

1. **Tokenizer Import Configuration**: The `trust_remote_code=True` flag is set, but the Python environment may not be properly configured to import custom tokenizer classes from the model repository
   - Missing `__init__.py` or incorrect module structure in cached model directory
   - Transformers version incompatibility with custom tokenizer implementation
   - PYTHONPATH not including the model cache directory
   - Security restrictions preventing dynamic code execution

2. **Output Format Logic Inconsistency**: Each format builder (_text, _json_format, _markdown, _table, etc.) implements its own structure without schema validation
   - _json_format returns nested dict but clients expect flat structure
   - _table returns markdown string instead of structured table object
   - _key_value mixes string values with dict values (bbox/confidence)
   - _structured has inconsistent field names across different document types

3. **Input Handling Gaps**: The _handle method extracts inputs from multiple sources (request.parameters, tensors) but lacks validation
   - No max length validation for image_ref or prompt_override
   - No type checking for options_json (could be malformed)
   - Variable-length string tensors may be corrupted by Triton IPC
   - Custom prompts extracted but then overridden by TASK_PROMPTS lookup

4. **Execution Path Complexity**: Three separate paths (SDK, native, mock) with unclear fallback logic
   - SDK path (_sdk_inference) wraps glmocr package but adds no value over native
   - Native path (_native_inference) duplicates SDK functionality
   - Fallback from SDK to native happens silently in initialize() but not documented
   - Mock path has completely different output structure requiring separate maintenance

5. **Error Handling Inconsistency**: Errors during initialization and inference are handled differently
   - initialize() catches exceptions and falls back to MOCK_MODE silently
   - execute() catches exceptions and returns TritonError
   - No distinction between recoverable errors (OOM → CPU fallback) and fatal errors (missing model)
   - GPU → CPU fallback happens in initialize() but not documented or tested

## Correctness Properties

Property 1: Fault Condition - Model Initialization Success

_For any_ initialization request where the GLM-OCR model path is valid and trust_remote_code is enabled, the fixed initialize() function SHALL successfully load the tokenizer and model on the available device (GPU if available, CPU otherwise) without raising import errors, and SHALL log the device and execution path clearly.

**Validates: Requirements 2.1, 2.5, 2.6, 2.10**

Property 2: Fault Condition - Output Format Compliance

_For any_ inference request where a specific output_format is requested (text, json, markdown, table, key_value, structured, formula), the fixed service SHALL return a result where the content field exactly matches the documented schema for that format, validated by schema checker, enabling client-side parsing without errors.

**Validates: Requirements 2.2, 2.8**

Property 3: Fault Condition - Input Handling Robustness

_For any_ inference request where dynamic or variable input content is provided (including custom prompts, variable-length images, or complex options), the fixed _handle() function SHALL properly validate, sanitize, and process all inputs, returning complete well-formed results without truncation or data loss.

**Validates: Requirements 2.3, 2.7**

Property 4: Fault Condition - Code Simplicity

_For any_ code review of the fixed model.py, the implementation SHALL follow KISS principles with a single clear execution path (native transformers with optional mock fallback), minimal abstraction layers (no SDK wrapper), and cyclomatic complexity below 10 per function, making the code maintainable and understandable.

**Validates: Requirements 2.4, 2.9**

Property 5: Preservation - Existing Functionality

_For any_ inference request that does NOT trigger the bug conditions (successful initialization, formats that already work, simple inputs, working code paths), the fixed service SHALL produce exactly the same results as the original service, preserving all existing functionality including coordinates, precision modes, field filtering, batch processing, mock mode, and health checks.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `services/triton-models/glm_ocr/1/model.py`

**Function**: `TritonPythonModel.initialize()`

**Specific Changes**:

1. **Fix Tokenizer Import Configuration**:
   - Add explicit `sys.path` manipulation to include model cache directory before calling AutoProcessor
   - Set environment variable `TRANSFORMERS_TRUST_REMOTE_CODE=1` before import
   - Add try-except with detailed logging for tokenizer import failures
   - Implement explicit tokenizer class import: `from transformers import AutoTokenizer; tokenizer = AutoTokenizer.from_pretrained(...)`
   - Fall back to CPU if GPU initialization fails, with clear logging

2. **Standardize Output Format Schemas**:
   - Define Pydantic models or TypedDict schemas for each output format (TextOutput, JsonOutput, MarkdownOutput, TableOutput, KeyValueOutput, StructuredOutput, FormulaOutput)
   - Refactor _MockEngine methods to return validated schema-compliant structures
   - Add schema validation before returning results in _handle()
   - Ensure _json_format returns flat `{"document_type": str, "fields": dict, "line_items": list}`
   - Ensure _table returns `[{"table_id": int, "headers": list, "rows": list, "bbox_2d": list}]`
   - Ensure _key_value returns flat dict with string values (move bbox/confidence to separate field)
   - Ensure _structured returns `{"document_type": str, "language": str, "raw_text": str, "fields": dict, "tables": list, "handwritten_sections": list}`

3. **Simplify Execution Paths**:
   - Remove SDK path entirely (delete _sdk_inference, remove glmocr import, remove self.sdk_parser)
   - Keep only native transformers path as primary execution
   - Keep mock path as fallback for testing
   - Simplify initialize() to: try native → catch exception → fall back to mock (if not STRICT_REAL)
   - Remove _GLMOCR_SDK_OK flag and all SDK-related conditionals
   - Reduce code from 850+ lines to ~600 lines

4. **Implement Robust Input Validation**:
   - Add input validation function: `_validate_inputs(image_ref, prompt, options) -> tuple[str, str, dict]`
   - Validate image_ref: check max length (4096), check format (file path or data: URI), check file exists
   - Validate prompt_override: check max length (2048), sanitize special characters
   - Validate options: check types (include_coordinates: bool, output_format: str in VALID_FORMATS, max_tokens: int in range)
   - Raise clear ValueError with specific message for invalid inputs
   - Respect custom prompts: use prompt_override directly if provided, don't override with TASK_PROMPTS

5. **Implement Consistent Error Handling**:
   - Define error hierarchy: FatalError (missing model, invalid config) vs RecoverableError (OOM, timeout)
   - In initialize(): catch FatalError → raise if STRICT_REAL else fall back to mock; catch RecoverableError → try CPU fallback
   - In execute(): catch all exceptions → log with traceback → return TritonError with clear message
   - Add device fallback logic: try GPU → catch OOM → clear cache → try CPU → catch error → fall back to mock
   - Log all fallbacks clearly: "GPU OOM, falling back to CPU" or "Model load failed, falling back to mock mode"

6. **Add Configuration Validation**:
   - Validate MODEL_PATH exists or is valid HuggingFace ID before loading
   - Validate PADDLEOCR_HOME directory exists if layout detection enabled
   - Validate precision mode is in ["normal", "high", "precision"]
   - Log all configuration at startup: model path, device, precision, mock mode, strict mode

7. **Refactor for Maintainability**:
   - Split large functions: _native_inference (100+ lines) → _prepare_inputs, _run_inference, _postprocess_outputs
   - Extract common logic: _create_generation_kwargs(precision) → returns dict
   - Remove duplicate code: _detect_layout and _run_glm_ocr are fine, but _enrich_word_confidence duplicates _run_glm_ocr logic
   - Add type hints to all functions
   - Add docstrings to all public methods

### Architecture Changes

**Before (3 execution paths):**
```
initialize()
  ├─ Try SDK (glmocr package)
  ├─ Try Native (transformers)
  └─ Fallback to Mock

execute()
  ├─ _sdk_inference()      # Path 1: SDK wrapper
  ├─ _native_inference()   # Path 2: Direct transformers
  └─ _MockEngine.run()     # Path 3: Test data
```

**After (1 execution path + mock fallback):**
```
initialize()
  ├─ Try Native (transformers)
  │   ├─ Load on GPU
  │   └─ Fallback to CPU if OOM
  └─ Fallback to Mock if fatal error

execute()
  ├─ _validate_inputs()
  ├─ _native_inference()   # Single path
  │   ├─ _prepare_inputs()
  │   ├─ _run_inference()
  │   └─ _postprocess_outputs()
  └─ _validate_output_schema()
```

## Testing Strategy

### Validation Approach

The testing strategy follows a three-phase approach: first, surface counterexamples that demonstrate the bugs on unfixed code (exploratory); second, verify the fix works correctly for all bug conditions (fix checking); third, verify existing behavior is preserved for non-buggy inputs (preservation checking).

### Exploratory Fault Condition Checking

**Goal**: Surface counterexamples that demonstrate the bugs BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that attempt to initialize the model, request different output formats, send dynamic inputs, and analyze code complexity. Run these tests on the UNFIXED code to observe failures and understand the root causes.

**Test Cases**:

1. **Tokenizer Import Test**: Call `AutoProcessor.from_pretrained("zai-org/GLM-OCR", trust_remote_code=True)` in isolated environment (will fail on unfixed code)
   - Expected failure: `ValueError: Tokenizer class ChatGLMTokenizer does not exist or is not currently imported`
   - Confirms root cause: tokenizer import configuration issue

2. **Output Format Schema Test**: Request each format (text, json, markdown, table, key_value, structured, formula) and validate against schema (will fail on unfixed code)
   - Expected failures: json format returns nested structure, table format returns string, key_value mixes types
   - Confirms root cause: output format logic inconsistency

3. **Dynamic Input Test**: Send variable-length document with custom prompt, verify prompt is used and content not truncated (will fail on unfixed code)
   - Expected failure: custom prompt ignored, content truncated
   - Confirms root cause: input handling gaps

4. **Code Complexity Test**: Run cyclomatic complexity analyzer on model.py, count execution paths (will fail on unfixed code)
   - Expected failure: complexity > 10 per function, 3 execution paths
   - Confirms root cause: execution path complexity

5. **Error Handling Test**: Trigger OOM error, verify fallback to CPU with clear logging (may fail on unfixed code)
   - Expected failure: silent fallback to mock mode without logging
   - Confirms root cause: error handling inconsistency

**Expected Counterexamples**:
- Tokenizer import fails with "does not exist or is not currently imported"
- JSON output fails schema validation with extra nesting or missing fields
- Table output is string instead of structured object
- Custom prompts are overridden by default TASK_PROMPTS
- Code has 3 separate execution paths with unclear coordination
- Possible causes: missing environment config, inconsistent format builders, missing input validation, over-engineering, inconsistent error handling

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := fixed_model.execute(input)
  ASSERT expectedBehavior(result)
END FOR

FUNCTION expectedBehavior(result)
  IF input.phase == "initialization" THEN
    RETURN result.tokenizer_loaded == True
           AND result.model_loaded == True
           AND result.device IN ["cuda", "cpu"]
           AND result.error == None
  ELSE IF input.phase == "inference" AND input.action == "return_result" THEN
    RETURN validateSchema(result.content, input.requested_format) == True
           AND result.error == None
  ELSE IF input.phase == "inference" AND input.action == "process_input" THEN
    RETURN result.content_complete == True
           AND result.custom_prompt_used == input.custom_prompt_provided
           AND result.error == None
  ELSE IF input.phase == "execution" THEN
    RETURN codeComplexityScore(result.code) <= 10
           AND executionPathCount(result.code) == 1
  END IF
END FUNCTION
```

**Test Cases**:
1. **Tokenizer Load Test**: Initialize model on GPU, verify tokenizer loads without errors
2. **JSON Format Test**: Request json format, validate output matches `{"document_type": str, "fields": dict, "line_items": list}` schema
3. **Table Format Test**: Request table format, validate output matches `[{"table_id": int, "headers": list, "rows": list}]` schema
4. **Custom Prompt Test**: Send custom prompt, verify it's used in generation (check logs or output)
5. **Dynamic Input Test**: Send variable-length content, verify complete processing without truncation
6. **Code Complexity Test**: Analyze fixed code, verify complexity <= 10 per function, single execution path
7. **GPU Fallback Test**: Trigger OOM, verify fallback to CPU with clear logging
8. **CPU Fallback Test**: Disable GPU, verify model loads on CPU successfully
9. **Mock Fallback Test**: Trigger fatal error, verify fallback to mock mode (if not STRICT_REAL)

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT original_model.execute(input) == fixed_model.execute(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for successful cases, then write property-based tests capturing that behavior.

**Test Cases**:

1. **Coordinate Extraction Preservation**: Observe that `include_coordinates=true` returns bbox_2d on unfixed code, then verify this continues after fix
   - Generate random documents with different layouts
   - Verify bbox_2d present for all elements when include_coordinates=true
   - Verify bbox_2d absent when include_coordinates=false

2. **Precision Mode Preservation**: Observe that `precision_mode="high"` uses do_sample=False on unfixed code, then verify this continues after fix
   - Generate random documents with different precision modes
   - Verify generation parameters match expected values for each mode
   - Verify output quality is consistent with precision mode

3. **Mock Mode Preservation**: Observe that `MOCK_MODE=true` returns deterministic data on unfixed code, then verify this continues after fix
   - Run same request multiple times in mock mode
   - Verify output is identical across runs
   - Verify no GPU usage in mock mode

4. **Field Extraction Preservation**: Observe that `extract_fields=["date"]` filters results on unfixed code, then verify this continues after fix
   - Generate random documents with different field sets
   - Verify only requested fields are returned
   - Verify field matching logic (case-insensitive, underscore/hyphen normalization) works

5. **Batch Processing Preservation**: Observe that batch endpoints process multiple documents on unfixed code, then verify this continues after fix
   - Send batch of 10 documents through temporal-worker
   - Verify all documents processed successfully
   - Verify results match single-document processing

6. **Health Check Preservation**: Observe that health endpoints return status on unfixed code, then verify this continues after fix
   - Call health check endpoint before and after fix
   - Verify response format unchanged
   - Verify status reporting accurate

7. **Result Envelope Preservation**: Observe that result structure has pages/markdown/confidence/usage on unfixed code, then verify this continues after fix
   - Generate random documents
   - Verify result envelope structure unchanged
   - Verify all fields present with correct types

### Unit Tests

- Test tokenizer initialization with valid model path
- Test tokenizer initialization with invalid model path (should raise or fall back)
- Test each output format builder with schema validation
- Test input validation with valid and invalid inputs
- Test GPU → CPU fallback with mocked OOM error
- Test CPU → mock fallback with mocked fatal error
- Test custom prompt handling (used vs ignored)
- Test field extraction with various field lists
- Test coordinate extraction enabled/disabled
- Test precision mode parameter handling

### Property-Based Tests

- Generate random documents (varying sizes, layouts, content types) and verify all output formats produce valid schemas
- Generate random input combinations (image_ref, prompt, options) and verify robust handling without crashes
- Generate random field extraction requests and verify correct filtering
- Generate random precision modes and verify appropriate generation parameters
- Generate random coordinate flags and verify bbox_2d presence/absence
- Test that all non-buggy inputs produce identical results before and after fix (preservation property)

### Integration Tests

- Test full pipeline: upload document → preprocessing → triton inference → post-processing → result
- Test batch processing: upload 10 documents → temporal-worker → verify all processed
- Test health checks: call /health endpoint → verify status
- Test error scenarios: invalid image → verify clear error message
- Test GPU/CPU switching: start on GPU → trigger OOM → verify CPU fallback → verify results still correct
- Test mock mode: set MOCK_MODE=true → verify deterministic output → verify no GPU usage
- Test microservice integration: api-gateway → triton → verify response format matches API spec
