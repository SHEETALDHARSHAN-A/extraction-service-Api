#!/usr/bin/env python3
"""
Property 2: Preservation - gRPC Functionality Unchanged

This test verifies that gRPC server functionality remains unchanged after
updating the grpcio version. These tests should PASS with a working grpcio
version (e.g., 1.68.1) to establish the baseline behavior.

Tests cover:
- Server startup and port binding
- ThreadPoolExecutor configuration
- Server lifecycle (start, stop)
- Basic service registration
"""

import sys
import os
import time
import subprocess
import tempfile
from concurrent import futures


def test_grpc_import():
    """Test that grpcio can be imported successfully."""
    print("=" * 70)
    print("PRESERVATION TEST 1: grpcio Import")
    print("=" * 70)
    
    try:
        import grpc
        print(f"✓ grpcio imported successfully")
        print(f"  Version: {grpc.__version__}")
        return True
    except ImportError as e:
        print(f"✗ Failed to import grpcio: {e}")
        return False


def test_server_creation():
    """Test that gRPC server can be created with ThreadPoolExecutor."""
    print()
    print("=" * 70)
    print("PRESERVATION TEST 2: Server Creation")
    print("=" * 70)
    
    try:
        import grpc
        from concurrent import futures
        
        # Create server with ThreadPoolExecutor (as used in main.py)
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        print("✓ gRPC server created successfully")
        print("  ThreadPoolExecutor: max_workers=10")
        
        # Clean up
        server.stop(None)
        return True
    
    except Exception as e:
        print(f"✗ Failed to create server: {e}")
        return False


def test_port_binding():
    """Test that server can bind to an insecure port."""
    print()
    print("=" * 70)
    print("PRESERVATION TEST 3: Port Binding")
    print("=" * 70)
    
    try:
        import grpc
        from concurrent import futures
        
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        
        # Bind to a test port (use high port number to avoid conflicts)
        test_port = "50099"
        server.add_insecure_port(f"[::]:{test_port}")
        print(f"✓ Server bound to port {test_port} successfully")
        
        # Clean up
        server.stop(None)
        return True
    
    except Exception as e:
        print(f"✗ Failed to bind port: {e}")
        return False


def test_server_lifecycle():
    """Test server start and graceful shutdown."""
    print()
    print("=" * 70)
    print("PRESERVATION TEST 4: Server Lifecycle")
    print("=" * 70)
    
    try:
        import grpc
        from concurrent import futures
        import threading
        
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        test_port = "50098"
        server.add_insecure_port(f"[::]:{test_port}")
        
        # Start server in background
        print("  Starting server...")
        server.start()
        print("✓ Server started successfully")
        
        # Give it a moment to fully start
        time.sleep(0.5)
        
        # Stop server gracefully
        print("  Stopping server...")
        server.stop(grace=1)
        print("✓ Server stopped gracefully")
        
        return True
    
    except Exception as e:
        print(f"✗ Server lifecycle test failed: {e}")
        return False


def test_concurrent_executor():
    """Test that ThreadPoolExecutor works correctly with various worker counts."""
    print()
    print("=" * 70)
    print("PRESERVATION TEST 5: ThreadPoolExecutor Configuration")
    print("=" * 70)
    
    try:
        import grpc
        from concurrent import futures
        import socket
        
        # Test different worker configurations
        worker_counts = [1, 5, 10, 20]
        
        for workers in worker_counts:
            server = grpc.server(futures.ThreadPoolExecutor(max_workers=workers))
            # Use port 0 to let OS assign an available port
            port = server.add_insecure_port("[::]:0")
            print(f"✓ Server created with {workers} workers (port {port})")
            server.stop(None)
        
        return True
    
    except Exception as e:
        print(f"✗ ThreadPoolExecutor test failed: {e}")
        return False


def test_requirements_installation():
    """
    Test that requirements.txt can be installed successfully.
    This is the key preservation test - verifying the updated grpcio version works.
    """
    print()
    print("=" * 70)
    print("PRESERVATION TEST 6: Requirements Installation")
    print("=" * 70)
    
    requirements_path = "services/post-processing-service/requirements.txt"
    
    if not os.path.exists(requirements_path):
        print(f"✗ Requirements file not found: {requirements_path}")
        return False
    
    print(f"  Testing installation from: {requirements_path}")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        venv_path = os.path.join(tmpdir, "test_venv")
        
        # Create virtual environment
        print("  Creating temporary virtual environment...")
        result = subprocess.run(
            [sys.executable, "-m", "venv", venv_path],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"✗ Failed to create venv: {result.stderr}")
            return False
        
        # Determine pip path
        if sys.platform == "win32":
            pip_path = os.path.join(venv_path, "Scripts", "pip.exe")
        else:
            pip_path = os.path.join(venv_path, "bin", "pip")
        
        # Install requirements
        print("  Installing requirements...")
        result = subprocess.run(
            [pip_path, "install", "-r", requirements_path, "--no-cache-dir"],
            capture_output=True,
            text=True,
            timeout=180  # 3 minute timeout
        )
        
        if result.returncode != 0:
            print(f"✗ Installation failed:")
            print(result.stderr)
            return False
        
        # Check for yanked warnings
        output = result.stdout + result.stderr
        if "yanked" in output.lower():
            print("✗ Yanked package warning detected:")
            print(output)
            return False
        
        print("✓ Requirements installed successfully")
        print("  No yanked package warnings")
        return True


def run_all_tests():
    """Run all preservation tests and report results."""
    print()
    print("=" * 70)
    print("PRESERVATION PROPERTY TESTS")
    print("=" * 70)
    print()
    print("These tests verify that gRPC functionality remains unchanged")
    print("after updating the grpcio version from 1.78.1 to 1.68.1")
    print()
    
    tests = [
        ("grpcio Import", test_grpc_import),
        ("Server Creation", test_server_creation),
        ("Port Binding", test_port_binding),
        ("Server Lifecycle", test_server_lifecycle),
        ("ThreadPoolExecutor", test_concurrent_executor),
        ("Requirements Installation", test_requirements_installation),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"✗ Test '{name}' raised exception: {e}")
            results.append((name, False))
    
    # Summary
    print()
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")
    
    print()
    print(f"Results: {passed_count}/{total_count} tests passed")
    print("=" * 70)
    
    return all(passed for _, passed in results)


if __name__ == "__main__":
    try:
        all_passed = run_all_tests()
        
        if all_passed:
            print()
            print("TEST RESULT: ALL PRESERVATION TESTS PASSED")
            print("gRPC functionality is preserved with the updated grpcio version")
            sys.exit(0)
        else:
            print()
            print("TEST RESULT: SOME PRESERVATION TESTS FAILED")
            print("gRPC functionality may have regressions")
            sys.exit(1)
    
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)
