#!/usr/bin/env python3
"""
Real-time Integration Test Runner

This script runs integration tests with real-time output and GPU monitoring.
"""

import subprocess
import sys
import time
from pathlib import Path


def check_gpu():
    """Check GPU availability."""
    print("=" * 80)
    print("Checking GPU Availability")
    print("=" * 80)
    
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,memory.used", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            gpu_info = result.stdout.strip()
            print(f"✅ GPU Available: {gpu_info}")
            return True
        else:
            print("❌ GPU not available")
            return False
    except Exception as e:
        print(f"⚠️  Could not check GPU: {e}")
        return False


def check_services():
    """Check if Docker services are running."""
    print("\n" + "=" * 80)
    print("Checking Docker Services")
    print("=" * 80)
    
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            services = result.stdout.strip().split('\n')
            print(f"✅ Found {len(services)} running services:")
            for service in services[:10]:  # Show first 10
                print(f"   {service}")
            return True
        else:
            print("❌ Could not list Docker services")
            return False
    except Exception as e:
        print(f"⚠️  Could not check services: {e}")
        return False


def check_api_health():
    """Check API Gateway health."""
    print("\n" + "=" * 80)
    print("Checking API Gateway Health")
    print("=" * 80)
    
    try:
        import requests
        response = requests.get("http://localhost:8000/health", timeout=5)
        
        if response.status_code == 200:
            health = response.json()
            print(f"✅ API Gateway is healthy")
            print(f"   Service: {health.get('service')}")
            print(f"   Status: {health.get('status')}")
            return True
        else:
            print(f"❌ API Gateway returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Could not reach API Gateway: {e}")
        return False


def run_tests(test_name=None, verbose=True):
    """Run integration tests with real-time output."""
    print("\n" + "=" * 80)
    print("Running Integration Tests")
    print("=" * 80)
    
    # Build pytest command
    cmd = ["pytest", "tests/integration/test_complete_extraction_flow.py"]
    
    if test_name:
        cmd.append(f"::{test_name}")
    
    if verbose:
        cmd.extend(["-v", "-s"])
    
    # Add color output
    cmd.append("--color=yes")
    
    # Add duration reporting
    cmd.append("--durations=10")
    
    print(f"\nCommand: {' '.join(cmd)}")
    print("\n" + "-" * 80)
    
    # Run pytest with real-time output
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Print output in real-time
        for line in process.stdout:
            print(line, end='')
        
        process.wait()
        return process.returncode == 0
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Test execution interrupted by user")
        process.terminate()
        return False
    except Exception as e:
        print(f"\n\n❌ Error running tests: {e}")
        return False


def main():
    """Main function."""
    print("=" * 80)
    print("REAL-TIME INTEGRATION TEST RUNNER")
    print("=" * 80)
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Check prerequisites
    gpu_ok = check_gpu()
    services_ok = check_services()
    api_ok = check_api_health()
    
    if not all([gpu_ok, services_ok, api_ok]):
        print("\n" + "=" * 80)
        print("❌ PREREQUISITES NOT MET")
        print("=" * 80)
        print("\nPlease ensure:")
        print("1. GPU is available (nvidia-smi works)")
        print("2. Docker services are running (docker ps)")
        print("3. API Gateway is healthy (curl http://localhost:8000/health)")
        return 1
    
    print("\n" + "=" * 80)
    print("✅ ALL PREREQUISITES MET - STARTING TESTS")
    print("=" * 80)
    
    # Ask user which tests to run
    print("\nTest Options:")
    print("1. Run all tests (10 tests, ~5-25 minutes)")
    print("2. Run fast tests only (3 tests, ~1-2 minutes)")
    print("3. Run specific test")
    print("4. Run basic test only (1 test, ~30 seconds)")
    
    choice = input("\nEnter choice (1-4) [default: 4]: ").strip() or "4"
    
    test_name = None
    if choice == "1":
        print("\n▶️  Running ALL tests...")
    elif choice == "2":
        print("\n▶️  Running FAST tests...")
        # We'll run with -m fast marker (need to add markers first)
        print("⚠️  Fast marker not yet added, running basic test instead")
        test_name = "test_complete_extraction_flow_basic"
    elif choice == "3":
        print("\nAvailable tests:")
        print("  - test_complete_extraction_flow_basic")
        print("  - test_complete_extraction_flow_with_word_granularity")
        print("  - test_complete_extraction_flow_with_key_value")
        print("  - test_queue_status_polling")
        print("  - test_concurrent_request_handling")
        print("  - test_large_document_processing")
        print("  - test_error_recovery_with_retry")
        print("  - test_queue_full_scenario")
        print("  - test_error_handling_invalid_document")
        test_name = input("\nEnter test name: ").strip()
    else:  # choice == "4" or default
        print("\n▶️  Running BASIC test...")
        test_name = "test_complete_extraction_flow_basic"
    
    # Run tests
    success = run_tests(test_name=test_name, verbose=True)
    
    # Print summary
    print("\n" + "=" * 80)
    if success:
        print("✅ TESTS PASSED")
    else:
        print("❌ TESTS FAILED")
    print("=" * 80)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
