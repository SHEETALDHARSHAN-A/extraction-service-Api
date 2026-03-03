"""
Install PaddleOCR dependencies for testing.

This script installs the required packages for PaddleOCR layout detection.
"""

import subprocess
import sys
import os
from pathlib import Path

def run_command(cmd, description):
    """Run a shell command and print output."""
    print(f"\n{'='*60}")
    print(f"{description}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        print(f"Command: {cmd}")
        print(f"Return code: {result.returncode}")
        
        if result.stdout:
            print(f"Output:\n{result.stdout}")
        
        if result.stderr:
            print(f"Errors:\n{result.stderr}")
        
        return result.returncode == 0
    except Exception as e:
        print(f"Error running command: {e}")
        return False

def check_python_version():
    """Check Python version."""
    print(f"\nPython version: {sys.version}")
    
    if sys.version_info < (3, 7):
        print("⚠️  Warning: Python 3.7+ is recommended for PaddleOCR")
        return False
    return True

def check_pip():
    """Check if pip is available."""
    try:
        import pip
        print(f"pip version: {pip.__version__}")
        return True
    except ImportError:
        print("❌ pip not found")
        return False

def check_gpu():
    """Check GPU availability."""
    print("\nChecking GPU availability...")
    
    # Check NVIDIA GPU
    try:
        result = subprocess.run("nvidia-smi", shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ NVIDIA GPU detected")
            print(f"Output:\n{result.stdout[:500]}...")  # First 500 chars
            return True
        else:
            print("❌ nvidia-smi failed or no NVIDIA GPU")
            return False
    except Exception as e:
        print(f"❌ Error checking GPU: {e}")
        return False

def install_paddlepaddle(gpu_available=False):
    """Install PaddlePaddle (CPU or GPU version)."""
    if gpu_available:
        print("\nInstalling PaddlePaddle GPU version...")
        cmd = "pip install paddlepaddle-gpu==2.6.0"
    else:
        print("\nInstalling PaddlePaddle CPU version...")
        cmd = "pip install paddlepaddle==2.6.0"
    
    return run_command(cmd, "Installing PaddlePaddle")

def install_paddleocr():
    """Install PaddleOCR."""
    print("\nInstalling PaddleOCR...")
    cmd = "pip install paddleocr>=2.7.0"
    return run_command(cmd, "Installing PaddleOCR")

def install_basic_deps():
    """Install basic dependencies."""
    deps = [
        "pillow>=10.0.0",
        "numpy>=1.24.0",
        "requests>=2.31.0",
    ]
    
    all_success = True
    for dep in deps:
        cmd = f"pip install {dep}"
        if not run_command(cmd, f"Installing {dep}"):
            all_success = False
    
    return all_success

def install_test_deps():
    """Install testing dependencies."""
    deps = [
        "pytest>=7.4.0",
        "pytest-asyncio>=0.21.0",
    ]
    
    all_success = True
    for dep in deps:
        cmd = f"pip install {dep}"
        if not run_command(cmd, f"Installing {dep}"):
            all_success = False
    
    return all_success

def verify_installation():
    """Verify PaddleOCR installation."""
    print("\nVerifying installation...")
    
    test_code = """
import sys
print(f"Python: {sys.version}")

try:
    import paddle
    print(f"PaddlePaddle: {paddle.__version__}")
    print(f"CUDA compiled: {paddle.is_compiled_with_cuda()}")
    print(f"CUDA devices: {paddle.device.cuda.device_count() if paddle.is_compiled_with_cuda() else 0}")
except ImportError as e:
    print(f"❌ PaddlePaddle import failed: {e}")
    sys.exit(1)

try:
    from paddleocr import PPStructureV3
    print("✅ PaddleOCR import successful")
except ImportError as e:
    print(f"❌ PaddleOCR import failed: {e}")
    sys.exit(1)

print("✅ All imports successful!")
"""
    
    # Write test script
    test_file = "verify_paddleocr.py"
    with open(test_file, 'w') as f:
        f.write(test_code)
    
    # Run test script
    success = run_command(f"{sys.executable} {test_file}", "Verifying imports")
    
    # Clean up
    if os.path.exists(test_file):
        os.remove(test_file)
    
    return success

def create_test_environment():
    """Create test environment file."""
    env_content = """# PaddleOCR Test Environment
PADDLEOCR_USE_GPU=true
PADDLEOCR_MODEL_DIR=./models
PADDLEOCR_MIN_CONFIDENCE_DEFAULT=0.5
PADDLEOCR_MAX_IMAGE_SIZE_MB=10
PADDLEOCR_REQUEST_TIMEOUT_SECONDS=30
LOG_LEVEL=INFO
SERVICE_HOST=0.0.0.0
SERVICE_PORT=8001
"""
    
    env_file = ".env.paddleocr-test"
    with open(env_file, 'w') as f:
        f.write(env_content)
    
    print(f"\n✅ Created test environment file: {env_file}")
    print("To use it, copy to .env or source it before running tests")
    
    return env_file

def main():
    """Main installation function."""
    print("=" * 80)
    print("PaddleOCR Dependencies Installation")
    print("=" * 80)
    
    # Check prerequisites
    if not check_python_version():
        print("❌ Python version check failed")
        return False
    
    if not check_pip():
        print("❌ pip check failed")
        return False
    
    # Check GPU
    gpu_available = check_gpu()
    
    # Install dependencies
    print("\n" + "=" * 80)
    print("Installing dependencies...")
    print("=" * 80)
    
    all_success = True
    
    # Install PaddlePaddle
    if not install_paddlepaddle(gpu_available):
        all_success = False
        print("⚠️  PaddlePaddle installation failed, trying CPU version...")
        if not install_paddlepaddle(False):  # Try CPU version
            all_success = False
    
    # Install PaddleOCR
    if not install_paddleocr():
        all_success = False
    
    # Install basic dependencies
    if not install_basic_deps():
        all_success = False
    
    # Install test dependencies (optional)
    install_test = input("\nInstall test dependencies? (y/n): ").lower().strip()
    if install_test in ['y', 'yes']:
        if not install_test_deps():
            all_success = False
    
    # Verify installation
    if all_success:
        print("\n" + "=" * 80)
        print("Verifying installation...")
        print("=" * 80)
        
        if not verify_installation():
            all_success = False
    
    # Create test environment
    if all_success:
        env_file = create_test_environment()
        
        print("\n" + "=" * 80)
        print("INSTALLATION COMPLETE")
        print("=" * 80)
        
        print("\n✅ Dependencies installed successfully!")
        print(f"\nNext steps:")
        print(f"1. Test PaddleOCR directly:")
        print(f"   python test_paddleocr_direct.py --check-gpu")
        print(f"   python test_paddleocr_direct.py")
        print(f"2. Test the full service:")
        print(f"   python test_paddleocr_service_local.py --check-gpu")
        print(f"   python test_paddleocr_service_local.py")
        print(f"3. Use the test environment:")
        print(f"   cp {env_file} .env")
        print(f"   # or source it: set -a; source {env_file}; set +a")
    else:
        print("\n" + "=" * 80)
        print("INSTALLATION FAILED")
        print("=" * 80)
        print("\n❌ Some installations failed")
        print("\nTroubleshooting tips:")
        print("1. Check your Python version (3.7+ required)")
        print("2. Make sure pip is up to date: pip install --upgrade pip")
        print("3. Try installing in a virtual environment")
        print("4. For GPU issues, check CUDA toolkit installation")
        print("5. Manual installation commands:")
        print("   pip install paddlepaddle-gpu==2.6.0")
        print("   pip install paddleocr>=2.7.0")
        print("   pip install pillow numpy requests")
    
    return all_success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)