#!/usr/bin/env python3
"""
GPU Extraction Test with Real-Time Service Logs
================================================
Tests GPU extraction functionality while monitoring all service logs.
"""

import subprocess
import threading
import time
import requests
import json
from pathlib import Path
from datetime import datetime
import sys

# Configuration
API_BASE_URL = "http://localhost:8000"
API_KEY = "tp-proj-dev-key-123"  # Must match format in auth.go
TEST_DOCUMENT = "testfiles/Prompt Consultancy Invoice no.PC_120_24-25.pdf"

# Service containers to monitor
SERVICES = [
    "docker-glm-ocr-service-1",      # GPU service
    "docker-paddleocr-service-1",     # PaddleOCR service
    "docker-api-gateway-1",           # API Gateway
    "docker-temporal-worker-1",       # Temporal worker
    "docker-postprocessing-service-1" # Post-processing
]

class ServiceLogMonitor:
    """Monitor Docker service logs in real-time."""
    
    def __init__(self, service_name):
        self.service_name = service_name
        self.process = None
        self.thread = None
        self.logs = []
        self.running = False
    
    def start(self):
        """Start monitoring logs."""
        self.running = True
        self.thread = threading.Thread(target=self._monitor_logs, daemon=True)
        self.thread.start()
    
    def _monitor_logs(self):
        """Monitor logs in background thread."""
        try:
            self.process = subprocess.Popen(
                ["docker", "logs", "-f", "--tail", "0", self.service_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            for line in self.process.stdout:
                if not self.running:
                    break
                timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                log_entry = f"[{timestamp}] {line.rstrip()}"
                self.logs.append(log_entry)
                print(f"[{self.service_name}] {log_entry}")
        
        except Exception as e:
            print(f"Error monitoring {self.service_name}: {e}")
    
    def stop(self):
        """Stop monitoring logs."""
        self.running = False
        if self.process:
            self.process.terminate()
            self.process.wait()
    
    def get_logs(self):
        """Get collected logs."""
        return self.logs.copy()

def print_header(title):
    """Print section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def check_services():
    """Check if all services are running."""
    print_header("Checking Services")
    
    all_running = True
    for service in SERVICES:
        try:
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Status}}", service],
                capture_output=True,
                text=True,
                timeout=5
            )
            status = result.stdout.strip()
            
            if status == "running":
                print(f"  ✓ {service}: {status}")
            else:
                print(f"  ✗ {service}: {status}")
                all_running = False
        
        except Exception as e:
            print(f"  ✗ {service}: Error - {e}")
            all_running = False
    
    return all_running

def check_api_health():
    """Check API health endpoint."""
    print_header("Checking API Health")
    
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print(f"  ✓ API is healthy: {response.json()}")
            return True
        else:
            print(f"  ✗ API returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"  ✗ API health check failed: {e}")
        return False

def upload_document():
    """Upload document for extraction."""
    print_header("Uploading Document")
    
    if not Path(TEST_DOCUMENT).exists():
        print(f"  ✗ Test document not found: {TEST_DOCUMENT}")
        return None
    
    print(f"  Document: {TEST_DOCUMENT}")
    print(f"  Size: {Path(TEST_DOCUMENT).stat().st_size / 1024:.2f} KB")
    
    headers = {"Authorization": f"Bearer {API_KEY}"}
    data = {
        "output_formats": "json",
        "include_coordinates": "true"
    }
    
    try:
        with open(TEST_DOCUMENT, "rb") as f:
            files = {"document": (Path(TEST_DOCUMENT).name, f, "image/png")}
            
            print("  Uploading...")
            response = requests.post(
                f"{API_BASE_URL}/jobs/upload",
                headers=headers,
                files=files,
                data=data,
                timeout=30
            )
        
        if response.status_code in [200, 202]:
            result = response.json()
            job_id = result.get("job_id")
            print(f"  ✓ Upload successful")
            print(f"  Job ID: {job_id}")
            print(f"  Status: {result.get('status')}")
            return job_id
        else:
            print(f"  ✗ Upload failed: {response.status_code}")
            print(f"  Response: {response.text}")
            return None
    
    except Exception as e:
        print(f"  ✗ Upload error: {e}")
        return None

def poll_job_status(job_id, timeout=300):
    """Poll job status until complete."""
    print_header("Processing Document")
    
    headers = {"Authorization": f"Bearer {API_KEY}"}
    start_time = time.time()
    
    print(f"  Job ID: {job_id}")
    print(f"  Polling for completion (timeout: {timeout}s)...")
    
    while True:
        try:
            response = requests.get(
                f"{API_BASE_URL}/jobs/{job_id}",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                job_data = response.json()
                status = job_data.get("status", "UNKNOWN")
                elapsed = time.time() - start_time
                
                print(f"  [{elapsed:.1f}s] Status: {status}")
                
                if status == "COMPLETED":
                    print(f"  ✓ Processing completed in {elapsed:.1f}s")
                    return job_data
                elif status == "FAILED":
                    print(f"  ✗ Job failed: {job_data.get('error', 'Unknown error')}")
                    return None
                elif status in ["PROCESSING", "UPLOADED", "QUEUED"]:
                    time.sleep(2)
                else:
                    print(f"  ⚠ Unknown status: {status}")
                    time.sleep(2)
            else:
                print(f"  ✗ Status check failed: {response.status_code}")
                return None
        
        except Exception as e:
            print(f"  ✗ Polling error: {e}")
            return None
        
        if time.time() - start_time > timeout:
            print(f"  ✗ Timeout after {timeout}s")
            return None

def get_job_result(job_id):
    """Get extraction result."""
    print_header("Retrieving Result")
    
    headers = {"Authorization": f"Bearer {API_KEY}"}
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/jobs/{job_id}/result",
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"  ✓ Result retrieved successfully")
            
            # Display summary
            print(f"\n  Summary:")
            print(f"    Model: {result.get('model', 'N/A')}")
            print(f"    Processing Time: {result.get('processing_time_ms', 0)}ms")
            print(f"    Document Confidence: {result.get('document_confidence', 0):.1%}")
            print(f"    Page Count: {result.get('page_count', 0)}")
            
            if "usage" in result:
                usage = result["usage"]
                print(f"    Token Usage: {usage.get('total_tokens', 0)} tokens")
            
            return result
        else:
            print(f"  ✗ Failed to get result: {response.status_code}")
            print(f"  Response: {response.text}")
            return None
    
    except Exception as e:
        print(f"  ✗ Error getting result: {e}")
        return None

def save_results(result, logs_by_service):
    """Save test results and logs."""
    print_header("Saving Results")
    
    output_dir = Path("test_results")
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save extraction result
    result_file = output_dir / f"extraction_result_{timestamp}.json"
    with open(result_file, "w") as f:
        json.dump(result, f, indent=2)
    print(f"  ✓ Extraction result: {result_file}")
    
    # Save service logs
    logs_file = output_dir / f"service_logs_{timestamp}.txt"
    with open(logs_file, "w") as f:
        f.write(f"GPU Extraction Test - Service Logs\n")
        f.write(f"Timestamp: {datetime.now().isoformat()}\n")
        f.write("=" * 80 + "\n\n")
        
        for service, logs in logs_by_service.items():
            f.write(f"\n{'=' * 80}\n")
            f.write(f"Service: {service}\n")
            f.write(f"{'=' * 80}\n\n")
            
            if logs:
                for log in logs:
                    f.write(log + "\n")
            else:
                f.write("No logs captured\n")
    
    print(f"  ✓ Service logs: {logs_file}")
    
    return result_file, logs_file

def analyze_logs(logs_by_service):
    """Analyze logs for errors and warnings."""
    print_header("Log Analysis")
    
    issues_found = False
    
    for service, logs in logs_by_service.items():
        errors = [log for log in logs if "ERROR" in log.upper() or "FAIL" in log.upper()]
        warnings = [log for log in logs if "WARN" in log.upper()]
        
        if errors:
            print(f"\n  ⚠ {service} - {len(errors)} error(s) found:")
            for error in errors[:5]:  # Show first 5
                print(f"    {error}")
            if len(errors) > 5:
                print(f"    ... and {len(errors) - 5} more")
            issues_found = True
        
        if warnings:
            print(f"\n  ⚠ {service} - {len(warnings)} warning(s) found:")
            for warning in warnings[:3]:  # Show first 3
                print(f"    {warning}")
            if len(warnings) > 3:
                print(f"    ... and {len(warnings) - 3} more")
    
    if not issues_found:
        print("\n  ✓ No errors or warnings found in logs")
    
    return issues_found

def main():
    """Main test execution."""
    print("\n" + "=" * 80)
    print("  GPU EXTRACTION TEST WITH REAL-TIME SERVICE LOGS")
    print("=" * 80)
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Check services
    if not check_services():
        print("\n✗ Some services are not running. Please start them first.")
        print("  Command: docker-compose -f docker/docker-compose.yml up -d")
        return False
    
    # Check API health
    if not check_api_health():
        print("\n✗ API is not healthy. Please check service logs.")
        return False
    
    # Start log monitors
    print_header("Starting Log Monitors")
    monitors = {}
    for service in SERVICES:
        print(f"  Starting monitor for {service}...")
        monitor = ServiceLogMonitor(service)
        monitor.start()
        monitors[service] = monitor
        time.sleep(0.5)
    
    print("  ✓ All log monitors started")
    
    try:
        # Upload document
        job_id = upload_document()
        if not job_id:
            return False
        
        # Poll for completion
        job_status = poll_job_status(job_id)
        if not job_status:
            return False
        
        # Get result
        result = get_job_result(job_id)
        if not result:
            return False
        
        # Wait a bit for final logs
        print("\n  Waiting for final logs...")
        time.sleep(3)
        
        # Stop monitors and collect logs
        print_header("Stopping Log Monitors")
        logs_by_service = {}
        for service, monitor in monitors.items():
            monitor.stop()
            logs_by_service[service] = monitor.get_logs()
            print(f"  ✓ Stopped {service} ({len(logs_by_service[service])} log entries)")
        
        # Analyze logs
        issues_found = analyze_logs(logs_by_service)
        
        # Save results
        result_file, logs_file = save_results(result, logs_by_service)
        
        # Final summary
        print_header("TEST SUMMARY")
        print(f"  ✓ Extraction completed successfully")
        print(f"  ✓ Results saved to: {result_file}")
        print(f"  ✓ Logs saved to: {logs_file}")
        
        if issues_found:
            print(f"\n  ⚠ Issues found in logs - review {logs_file} for details")
            return False
        else:
            print(f"\n  ✓ No issues found - GPU extraction is working properly")
            return True
    
    finally:
        # Ensure monitors are stopped
        for monitor in monitors.values():
            monitor.stop()

if __name__ == "__main__":
    try:
        success = main()
        print("\n" + "=" * 80)
        if success:
            print("  ✓ TEST PASSED")
        else:
            print("  ✗ TEST FAILED")
        print("=" * 80 + "\n")
        sys.exit(0 if success else 1)
    
    except KeyboardInterrupt:
        print("\n\n⚠ Test interrupted by user")
        sys.exit(0)
    
    except Exception as e:
        print(f"\n✗ Test error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
