#!/usr/bin/env python3
"""
Test Validation Script

This script validates the integration test file for:
1. Syntax errors
2. Import issues
3. Test function structure
4. Documentation completeness
5. Code quality issues
"""

import ast
import sys
from pathlib import Path
from typing import List, Tuple


def validate_syntax(file_path: Path) -> Tuple[bool, List[str]]:
    """Validate Python syntax."""
    errors = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
        ast.parse(code)
        return True, []
    except SyntaxError as e:
        errors.append(f"Syntax error at line {e.lineno}: {e.msg}")
        return False, errors


def validate_imports(file_path: Path) -> Tuple[bool, List[str]]:
    """Validate that all imports are available."""
    errors = []
    warnings = []
    
    required_imports = [
        'requests',
        'pytest',
        'PIL',  # Pillow
    ]
    
    optional_imports = [
        'reportlab',  # For PDF generation
    ]
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        tree = ast.parse(code)
        
        # Extract all imports
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split('.')[0])
        
        # Check required imports
        for req in required_imports:
            if req not in imports:
                errors.append(f"Missing required import: {req}")
        
        # Check optional imports
        for opt in optional_imports:
            if opt not in imports:
                warnings.append(f"Optional import not found: {opt} (may be conditionally imported)")
        
        return len(errors) == 0, errors + warnings
        
    except Exception as e:
        errors.append(f"Error checking imports: {e}")
        return False, errors


def validate_test_functions(file_path: Path) -> Tuple[bool, List[str]]:
    """Validate test function structure."""
    errors = []
    warnings = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        tree = ast.parse(code)
        
        # Find all test functions
        test_functions = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.name.startswith('test_'):
                    test_functions.append(node)
        
        print(f"\nFound {len(test_functions)} test functions:")
        for func in test_functions:
            print(f"  - {func.name}")
            
            # Check for docstring
            docstring = ast.get_docstring(func)
            if not docstring:
                warnings.append(f"Test function {func.name} missing docstring")
            elif len(docstring) < 50:
                warnings.append(f"Test function {func.name} has short docstring")
            
            # Check for parameters
            if len(func.args.args) == 0:
                warnings.append(f"Test function {func.name} has no parameters (should have fixture)")
        
        if len(test_functions) == 0:
            errors.append("No test functions found")
        
        return len(errors) == 0, errors + warnings
        
    except Exception as e:
        errors.append(f"Error validating test functions: {e}")
        return False, errors


def validate_helper_functions(file_path: Path) -> Tuple[bool, List[str]]:
    """Validate helper function structure."""
    errors = []
    warnings = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        tree = ast.parse(code)
        
        # Find all non-test functions
        helper_functions = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if not node.name.startswith('test_') and not node.name.startswith('_'):
                    helper_functions.append(node)
        
        print(f"\nFound {len(helper_functions)} helper functions:")
        for func in helper_functions:
            print(f"  - {func.name}")
            
            # Check for docstring
            docstring = ast.get_docstring(func)
            if not docstring:
                warnings.append(f"Helper function {func.name} missing docstring")
            
            # Check for type hints
            if not func.returns:
                warnings.append(f"Helper function {func.name} missing return type hint")
        
        return len(errors) == 0, errors + warnings
        
    except Exception as e:
        errors.append(f"Error validating helper functions: {e}")
        return False, errors


def check_code_quality(file_path: Path) -> Tuple[bool, List[str]]:
    """Check code quality issues."""
    warnings = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Check line length
        long_lines = []
        for i, line in enumerate(lines, 1):
            if len(line.rstrip()) > 120:
                long_lines.append(i)
        
        if long_lines:
            warnings.append(f"Lines exceeding 120 characters: {len(long_lines)} lines")
            if len(long_lines) <= 5:
                warnings.append(f"  Lines: {', '.join(map(str, long_lines))}")
        
        # Check for print statements (should use logging in production)
        print_count = sum(1 for line in lines if 'print(' in line and not line.strip().startswith('#'))
        if print_count > 50:
            warnings.append(f"Many print statements found: {print_count} (consider using logging)")
        
        # Check for TODO/FIXME comments
        todos = [i for i, line in enumerate(lines, 1) if 'TODO' in line or 'FIXME' in line]
        if todos:
            warnings.append(f"TODO/FIXME comments found at lines: {', '.join(map(str, todos))}")
        
        return True, warnings
        
    except Exception as e:
        return False, [f"Error checking code quality: {e}"]


def main():
    """Main validation function."""
    print("=" * 80)
    print("Integration Test Validation")
    print("=" * 80)
    
    test_file = Path("tests/integration/test_complete_extraction_flow.py")
    
    if not test_file.exists():
        print(f"\n❌ Test file not found: {test_file}")
        return 1
    
    print(f"\nValidating: {test_file}")
    print(f"File size: {test_file.stat().st_size / 1024:.1f} KB")
    
    all_passed = True
    all_messages = []
    
    # 1. Validate syntax
    print("\n" + "-" * 80)
    print("1. Checking Python syntax...")
    passed, messages = validate_syntax(test_file)
    if passed:
        print("   ✅ Syntax is valid")
    else:
        print("   ❌ Syntax errors found")
        all_passed = False
    all_messages.extend(messages)
    
    # 2. Validate imports
    print("\n" + "-" * 80)
    print("2. Checking imports...")
    passed, messages = validate_imports(test_file)
    if passed:
        print("   ✅ All required imports present")
    else:
        print("   ❌ Import issues found")
        all_passed = False
    all_messages.extend(messages)
    
    # 3. Validate test functions
    print("\n" + "-" * 80)
    print("3. Checking test functions...")
    passed, messages = validate_test_functions(test_file)
    if passed:
        print("   ✅ Test functions are valid")
    else:
        print("   ❌ Test function issues found")
        all_passed = False
    all_messages.extend(messages)
    
    # 4. Validate helper functions
    print("\n" + "-" * 80)
    print("4. Checking helper functions...")
    passed, messages = validate_helper_functions(test_file)
    if passed:
        print("   ✅ Helper functions are valid")
    else:
        print("   ❌ Helper function issues found")
        all_passed = False
    all_messages.extend(messages)
    
    # 5. Check code quality
    print("\n" + "-" * 80)
    print("5. Checking code quality...")
    passed, messages = check_code_quality(test_file)
    if passed:
        print("   ✅ Code quality checks passed")
    else:
        print("   ⚠️  Code quality issues found")
    all_messages.extend(messages)
    
    # Print all messages
    if all_messages:
        print("\n" + "=" * 80)
        print("Issues and Warnings:")
        print("=" * 80)
        for msg in all_messages:
            if "❌" in msg or "Error" in msg:
                print(f"❌ {msg}")
            else:
                print(f"⚠️  {msg}")
    
    # Final summary
    print("\n" + "=" * 80)
    if all_passed:
        print("✅ VALIDATION PASSED")
        print("=" * 80)
        print("\nThe integration test file is valid and ready to run.")
        print("\nNext steps:")
        print("1. Install dependencies: pip install -r tests/integration/requirements.txt")
        print("2. Start services: cd docker && docker-compose up -d")
        print("3. Run tests: pytest tests/integration/test_complete_extraction_flow.py -v")
        return 0
    else:
        print("❌ VALIDATION FAILED")
        print("=" * 80)
        print("\nPlease fix the errors above before running the tests.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
