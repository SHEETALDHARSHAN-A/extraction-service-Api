# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Fault Condition** - Last Line Bbox Height Accuracy
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope the property to concrete failing cases where height % len(lines) != 0
  - Test that for inputs where (height - i * line_h) < line_h AND (height - i * line_h) >= 0, the bbox height calculation is incorrect on unfixed code
  - Test cases: height=100 with 3 lines (last line should be 34, not 33), height=100 with 7 lines (last line should be 16, not 14), height=50 with 8 lines (last line should be 8, not 6)
  - The test assertions should verify: last_line.bbox[3] == min(line_h, height - (len(result) - 1) * line_h)
  - Run test on UNFIXED code in services/glm-ocr-service/app/main.py
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
  - Document counterexamples found (e.g., "Last line bbox height is 33 instead of 34 for height=100, 3 lines")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 2.1, 2.2, 2.3_

- [ ] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-Last-Line Bbox Calculations
  - **IMPORTANT**: Follow observation-first methodology
  - Observe behavior on UNFIXED code for cases where height is evenly divisible by line count (e.g., height=100 with 4 lines, height=80 with 5 lines)
  - Observe that x, y, width components are calculated correctly for all lines on unfixed code
  - Observe that empty content returns [] on unfixed code
  - Observe that single-line content produces correct bbox on unfixed code
  - Write property-based tests capturing observed behavior patterns: for all inputs where (height - i * line_h) >= line_h, bbox calculations remain unchanged
  - Property-based testing generates many test cases for stronger guarantees
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ] 3. Fix for last line bbox height calculation

  - [ ] 3.1 Implement the fix
    - Modify line 134 in services/glm-ocr-service/app/main.py
    - Change `"bbox": [x, y + i * line_h, width, min(line_h, max(1, height - i * line_h))]` to `"bbox": [x, y + i * line_h, width, min(line_h, height - i * line_h)]`
    - Remove the `max(1, ...)` wrapper to allow accurate representation of remaining vertical space
    - _Bug_Condition: isBugCondition(input) where (height - i * line_h) < line_h AND (height - i * line_h) >= 0_
    - _Expected_Behavior: last_line.bbox[3] == min(line_h, height - (len(result) - 1) * line_h) for all inputs_
    - _Preservation: All x, y, width calculations, line_h calculation, empty content handling, and non-last-line bbox calculations remain unchanged_
    - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4_

  - [ ] 3.2 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Last Line Bbox Height Accuracy
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - Verify that last line bbox heights now match the remaining vertical space for all test cases
    - _Requirements: 2.1, 2.2, 2.3_

  - [ ] 3.3 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-Last-Line Bbox Calculations
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions in x, y, width calculations, empty content handling, or even-division cases)

- [ ] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
