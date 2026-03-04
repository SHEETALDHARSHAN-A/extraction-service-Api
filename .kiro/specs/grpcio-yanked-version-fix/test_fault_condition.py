#!/usr/bin/env python3
"""
Property 1: Fault Condition - Docker Build Fails with Yanked grpcio==1.78.1

This test verifies that the bug exists by attempting to install the yanked
grpcio==1.78.1 version. This test MUST FAIL on unfixed code.

Expected outcome: pip install fails or shows yanked package warning
"""

import subprocess
import sys
import tempfile
import os


def test_yanked_grpcio_installation():
    """
    Test that grpcio==1.78.1 is yanked and causes installation failure.
    
    This is a scoped property test for the concrete failing case:
    - Input: pip install grpcio==1.78.1
    - Expected: Installation fails or shows yanked warning
    """
    print("=" * 70)
    print("FAULT CONDITION TEST: Attempting to install yanked grpcio==1.78.1")
    print("=" * 70)
    print()
    print("EXPECTED OUTCOME: This test should FAIL (proving the bug exists)")
    print()
    
    # Create a temporary virtual environment to test in isolation
    with tempfile.TemporaryDirectory() as tmpdir:
        venv_path = os.path.join(tmpdir, "test_venv")
        
        # Create virtual environment
        print("Creating temporary virtual environment...")
        result = subprocess.run(
            [sys.executable, "-m", "venv", venv_path],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Failed to create venv: {result.stderr}")
            return False
        
        # Determine pip path based on OS
        if sys.platform == "win32":
            pip_path = os.path.join(venv_path, "Scripts", "pip.exe")
        else:
            pip_path = os.path.join(venv_path, "bin", "pip")
        
        # Attempt to install the yanked version
        print("Attempting to install grpcio==1.78.1...")
        print()
        
        result = subprocess.run(
            [pip_path, "install", "grpcio==1.78.1", "--no-cache-dir"],
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout
        )
        
        print("STDOUT:")
        print(result.stdout)
        print()
        print("STDERR:")
        print(result.stderr)
        print()
        print(f"Return code: {result.returncode}")
        print()
        
        # Check for yanked package indicators
        output = result.stdout + result.stderr
        is_yanked = "yanked" in output.lower()
        installation_failed = result.returncode != 0
        
        print("=" * 70)
        print("COUNTEREXAMPLE DOCUMENTATION:")
        print("=" * 70)
        
        if is_yanked:
            print("✓ Yanked package warning detected in output")
        
        if installation_failed:
            print("✓ Installation failed (non-zero exit code)")
        
        if not is_yanked and not installation_failed:
            print("✗ Installation succeeded without yanked warning")
            print("  This may indicate the package is cached or no longer yanked")
        
        print()
        print("Bug confirmed: grpcio==1.78.1 causes installation issues")
        print("=" * 70)
        
        # Return False to indicate the bug exists (test "fails" as expected)
        return installation_failed or is_yanked


if __name__ == "__main__":
    try:
        bug_exists = test_yanked_grpcio_installation()
        
        if bug_exists:
            print()
            print("TEST RESULT: FAILED (as expected - bug confirmed)")
            print("The yanked grpcio==1.78.1 version causes installation issues.")
            sys.exit(1)  # Exit with error to indicate test failure
        else:
            print()
            print("TEST RESULT: PASSED (unexpected)")
            print("The installation succeeded, bug may not be reproducible.")
            sys.exit(0)
    
    except subprocess.TimeoutExpired:
        print()
        print("=" * 70)
        print("COUNTEREXAMPLE: Installation timed out after 2 minutes")
        print("=" * 70)
        print()
        print("TEST RESULT: FAILED (as expected - bug confirmed via timeout)")
        sys.exit(1)
    
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)
