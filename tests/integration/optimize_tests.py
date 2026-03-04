#!/usr/bin/env python3
"""
Test Optimization Script

This script provides optimizations for the integration test suite:
1. Add test markers for selective execution
2. Add performance profiling
3. Generate test execution report
4. Provide recommendations
"""

import subprocess
import sys
from pathlib import Path


def add_test_markers():
    """Add pytest markers to tests for selective execution."""
    print("=" * 80)
    print("Test Markers Recommendation")
    print("=" * 80)
    
    markers = {
        "fast": [
            "test_complete_extraction_flow_basic",
            "test_queue_status_polling",
            "test_error_handling_invalid_document",
        ],
        "slow": [
            "test_large_document_processing",
            "test_queue_full_scenario",
        ],
        "concurrent": [
            "test_concurrent_request_handling",
        ],
        "retry": [
            "test_error_recovery_with_retry",
        ],
        "extraction": [
            "test_complete_extraction_flow_with_word_granularity",
            "test_complete_extraction_flow_with_key_value",
        ],
    }
    
    print("\nRecommended pytest markers to add to pytest.ini:")
    print("\n[pytest]")
    print("markers =")
    for marker, tests in markers.items():
        print(f"    {marker}: {marker} tests")
    
    print("\n\nExample usage:")
    print("  # Run only fast tests")
    print("  pytest -m fast")
    print("\n  # Run all except slow tests")
    print("  pytest -m 'not slow'")
    print("\n  # Run concurrent and retry tests")
    print("  pytest -m 'concurrent or retry'")
    
    print("\n\nTo add markers to test functions, add decorators:")
    print("  @pytest.mark.fast")
    print("  def test_complete_extraction_flow_basic(...):")
    print("      ...")


def check_dependencies():
    """Check if optimization dependencies are installed."""
    print("\n" + "=" * 80)
    print("Checking Optimization Dependencies")
    print("=" * 80)
    
    dependencies = {
        "pytest-xdist": "Parallel test execution",
        "pytest-cov": "Code coverage reporting",
        "pytest-html": "HTML test reports",
        "pytest-json-report": "JSON test reports",
        "pytest-timeout": "Test timeout management",
    }
    
    installed = []
    missing = []
    
    for package, description in dependencies.items():
        try:
            __import__(package.replace("-", "_"))
            installed.append((package, description))
            print(f"✅ {package:20} - {description}")
        except ImportError:
            missing.append((package, description))
            print(f"❌ {package:20} - {description}")
    
    if missing:
        print("\n\nTo install missing dependencies:")
        print(f"  pip install {' '.join(pkg for pkg, _ in missing)}")
    
    return len(missing) == 0


def generate_optimization_commands():
    """Generate optimization commands for running tests."""
    print("\n" + "=" * 80)
    print("Optimization Commands")
    print("=" * 80)
    
    commands = [
        ("Run tests in parallel (4 workers)", 
         "pytest tests/integration/test_complete_extraction_flow.py -n 4"),
        
        ("Run with coverage report",
         "pytest tests/integration/test_complete_extraction_flow.py --cov=. --cov-report=html"),
        
        ("Run with HTML report",
         "pytest tests/integration/test_complete_extraction_flow.py --html=report.html --self-contained-html"),
        
        ("Run with JSON report",
         "pytest tests/integration/test_complete_extraction_flow.py --json-report --json-report-file=report.json"),
        
        ("Run with duration reporting (slowest 10 tests)",
         "pytest tests/integration/test_complete_extraction_flow.py --durations=10"),
        
        ("Run with timeout (5 minutes per test)",
         "pytest tests/integration/test_complete_extraction_flow.py --timeout=300"),
        
        ("Run with verbose output and no capture",
         "pytest tests/integration/test_complete_extraction_flow.py -v -s"),
        
        ("Run specific test with detailed output",
         "pytest tests/integration/test_complete_extraction_flow.py::test_complete_extraction_flow_basic -v -s"),
    ]
    
    for i, (description, command) in enumerate(commands, 1):
        print(f"\n{i}. {description}")
        print(f"   {command}")


def create_pytest_ini():
    """Create pytest.ini configuration file."""
    print("\n" + "=" * 80)
    print("Creating pytest.ini Configuration")
    print("=" * 80)
    
    pytest_ini_content = """[pytest]
# Pytest configuration for integration tests

# Test discovery
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# Test markers
markers =
    fast: Fast tests (< 30 seconds)
    slow: Slow tests (> 2 minutes)
    concurrent: Tests involving concurrent requests
    retry: Tests involving retry mechanisms
    extraction: Tests for extraction features
    queue: Tests for queue functionality
    error: Tests for error handling

# Output options
addopts = 
    -v
    --strict-markers
    --tb=short
    --disable-warnings

# Timeout settings
timeout = 600
timeout_method = thread

# Coverage settings
[coverage:run]
source = .
omit = 
    */tests/*
    */venv/*
    */.venv/*

[coverage:report]
precision = 2
show_missing = True
skip_covered = False

[coverage:html]
directory = htmlcov
"""
    
    pytest_ini_path = Path("pytest.ini")
    
    if pytest_ini_path.exists():
        print(f"\n⚠️  pytest.ini already exists at {pytest_ini_path}")
        print("   Skipping creation to avoid overwriting existing configuration")
    else:
        with open(pytest_ini_path, 'w') as f:
            f.write(pytest_ini_content)
        print(f"\n✅ Created pytest.ini at {pytest_ini_path}")
        print("\nConfiguration includes:")
        print("  - Test discovery patterns")
        print("  - Test markers for selective execution")
        print("  - Output formatting options")
        print("  - Timeout settings (10 minutes per test)")
        print("  - Coverage reporting configuration")


def generate_makefile():
    """Generate Makefile for common test commands."""
    print("\n" + "=" * 80)
    print("Creating Makefile for Test Commands")
    print("=" * 80)
    
    makefile_content = """# Makefile for Integration Tests

.PHONY: help test test-fast test-slow test-parallel test-coverage test-report clean

help:
\t@echo "Integration Test Commands:"
\t@echo "  make test          - Run all integration tests"
\t@echo "  make test-fast     - Run only fast tests"
\t@echo "  make test-slow     - Run only slow tests"
\t@echo "  make test-parallel - Run tests in parallel"
\t@echo "  make test-coverage - Run tests with coverage report"
\t@echo "  make test-report   - Run tests and generate HTML report"
\t@echo "  make clean         - Clean test artifacts"

test:
\tpytest tests/integration/test_complete_extraction_flow.py -v

test-fast:
\tpytest tests/integration/test_complete_extraction_flow.py -v -m fast

test-slow:
\tpytest tests/integration/test_complete_extraction_flow.py -v -m slow

test-parallel:
\tpytest tests/integration/test_complete_extraction_flow.py -n auto

test-coverage:
\tpytest tests/integration/test_complete_extraction_flow.py --cov=. --cov-report=html --cov-report=term

test-report:
\tpytest tests/integration/test_complete_extraction_flow.py --html=test-report.html --self-contained-html

clean:
\trm -rf .pytest_cache htmlcov test-report.html report.json .coverage
"""
    
    makefile_path = Path("Makefile")
    
    if makefile_path.exists():
        print(f"\n⚠️  Makefile already exists at {makefile_path}")
        print("   Skipping creation to avoid overwriting existing configuration")
    else:
        with open(makefile_path, 'w') as f:
            f.write(makefile_content)
        print(f"\n✅ Created Makefile at {makefile_path}")
        print("\nUsage:")
        print("  make help          - Show available commands")
        print("  make test          - Run all tests")
        print("  make test-fast     - Run fast tests only")
        print("  make test-coverage - Run with coverage")


def main():
    """Main optimization function."""
    print("=" * 80)
    print("Integration Test Optimization Tool")
    print("=" * 80)
    
    # 1. Add test markers
    add_test_markers()
    
    # 2. Check dependencies
    all_deps_installed = check_dependencies()
    
    # 3. Generate optimization commands
    generate_optimization_commands()
    
    # 4. Create pytest.ini
    create_pytest_ini()
    
    # 5. Generate Makefile
    generate_makefile()
    
    # Final summary
    print("\n" + "=" * 80)
    print("Optimization Complete")
    print("=" * 80)
    
    if all_deps_installed:
        print("\n✅ All optimization dependencies are installed")
    else:
        print("\n⚠️  Some optimization dependencies are missing")
        print("   Install them to enable all optimization features")
    
    print("\nNext steps:")
    print("1. Review pytest.ini configuration")
    print("2. Add test markers to test functions")
    print("3. Run tests with optimization commands")
    print("4. Review test reports and coverage")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
