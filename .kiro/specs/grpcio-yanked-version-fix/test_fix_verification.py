#!/usr/bin/env python3
"""
Property 1: Expected Behavior - Docker Build Success with Non-Yanked grpcio

This test verifies that the fix works by checking that the requirements.txt
specifies a non-yanked grpcio version and that it can be installed successfully.

**Validates: Requirements 2.1, 2.2**
"""

import subprocess
import sys
import tempfile
import os
import re


def test_fixed_grpcio_installation():
    """
    Test that the requirements.txt now specifies a non-yanked grpcio version
    and that it can be installed successfully.
    
    This verifies the expected behavior after the fix:
    - requirements.txt specifies a non-yanked grpcio version
    - pip install succeeds without errors or warnings
    - The installed version is not yanked
    """
    print("=" * 70, flush=True)
    print("FIX VERIFICATION TEST: Checking fixed requirements.txt", flush=True)
    print("=" * 70, flush=True)
    print(flush=True)
    
    # Read the requirements.txt file
    requirements_path = "services/post-processing-service/requirements.txt"
    
    if not os.path.exists(requirements_path):
        print(f"ERROR: {requirements_path} not found", flush=True)
        return False
    
    with open(requirements_path, 'r') as f:
        requirements_content = f.read()
    
    print(f"Requirements file content:", flush=True)
    print(requirements_content, flush=True)
    print(flush=True)

    
    # Extract grpcio version
    grpcio_match = re.search(r'grpcio==([0-9.]+)', requirements_content)
    
    if not grpcio_match:
        print("ERROR: grpcio version not found in requirements.txt", flush=True)
        return False
    
    grpcio_version = grpcio_match.group(1)
    print(f"Found grpcio version: {grpcio_version}", flush=True)
    print(flush=True)
    
    # Verify it's not the yanked version
    if grpcio_version == "1.78.1":
        print("ERROR: requirements.txt still contains yanked version 1.78.1", flush=True)
        return False
    
    print(f"✓ requirements.txt specifies non-yanked version: {grpcio_version}", flush=True)
    print(flush=True)
    
    # Create a temporary virtual environment to test installation
    with tempfile.TemporaryDirectory() as tmpdir:
        venv_path = os.path.join(tmpdir, "test_venv")
        
        # Create virtual environment
        print("Creating temporary virtual environment...", flush=True)
        result = subprocess.run(
            [sys.executable, "-m", "venv", venv_path],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Failed to create venv: {result.stderr}", flush=True)
            return False
        
        # Determine pip path based on OS
        if sys.platform == "win32":
            pip_path = os.path.join(venv_path, "Scripts", "pip.exe")
        else:
            pip_path = os.path.join(venv_path, "bin", "pip")
        
        # Attempt to install the fixed version
        print(f"Attempting to install grpcio=={grpcio_version}...", flush=True)
        print(flush=True)
        
        result = subprocess.run(
            [pip_path, "install", f"grpcio=={grpcio_version}", "--no-cache-dir"],
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout
        )
        
        print("STDOUT:", flush=True)
        print(result.stdout, flush=True)
        print(flush=True)
        
        if result.stderr:
            print("STDERR:", flush=True)
            print(result.stderr, flush=True)
            print(flush=True)
        
        print(f"Return code: {result.returncode}", flush=True)
        print(flush=True)
        
        # Check for success indicators
        output = result.stdout + result.stderr
        is_yanked = "yanked" in output.lower()
        installation_succeeded = result.returncode == 0
        
        print("=" * 70, flush=True)
        print("VERIFICATION RESULTS:", flush=True)
        print("=" * 70, flush=True)
        
        if installation_succeeded:
            print(f"✓ Installation succeeded for grpcio=={grpcio_version}", flush=True)
        else:
            print(f"✗ Installation failed for grpcio=={grpcio_version}", flush=True)
        
        if not is_yanked:
            print("✓ No yanked package warnings detected", flush=True)
        else:
            print("✗ Yanked package warning detected (unexpected)", flush=True)
        
        print(flush=True)
        
        if installation_succeeded and not is_yanked:
            print("SUCCESS: Fix verified - non-yanked grpcio version installs correctly", flush=True)
            print("=" * 70, flush=True)
            return True
        else:
            print("FAILURE: Fix verification failed", flush=True)
            print("=" * 70, flush=True)
            return False


if __name__ == "__main__":
    try:
        fix_verified = test_fixed_grpcio_installation()
        
        if fix_verified:
            print(flush=True)
            print("TEST RESULT: PASSED", flush=True)
            print("The fix is working correctly - non-yanked grpcio version installs successfully.", flush=True)
            sys.exit(0)
        else:
            print(flush=True)
            print("TEST RESULT: FAILED", flush=True)
            print("The fix verification failed - check the output above for details.", flush=True)
            sys.exit(1)
    
    except subprocess.TimeoutExpired:
        print(flush=True)
        print("=" * 70, flush=True)
        print("ERROR: Installation timed out after 2 minutes", flush=True)
        print("=" * 70, flush=True)
        print(flush=True)
        print("TEST RESULT: FAILED", flush=True)
        sys.exit(1)
    
    except Exception as e:
        print(f"Unexpected error: {e}", flush=True)
        sys.exit(1)
