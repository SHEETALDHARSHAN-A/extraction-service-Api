#!/usr/bin/env python3
"""
IDEP End-to-End GPU Test - Python Advanced Testing
Provides detailed metrics, performance analysis, and result validation
"""

import os
import sys
import json
import time
import requests
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import statistics

class IDEPTester:
    def __init__(self, api_base="http://localhost:8000", api_key="tp-proj-dev-key-123"):
        self.api_base = api_base
        self.api_key = api_key
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.test_results = []
        self.start_time = None
        self.metrics = {
            "upload_times": [],
            "processing_times": [],
            "job_sizes": [],
            "success_count": 0,
            "failure_count": 0,
        }
    
    def log(self, level: str, message: str):
        """Colored logging output"""
        colors = {
            "INFO": "\033[94m",      # Blue
            "SUCCESS": "\033[92m",   # Green
            "ERROR": "\033[91m",     # Red
            "WARN": "\033[93m",      # Yellow
            "METRIC": "\033[96m",    # Cyan
        }
        reset = "\033[0m"
        timestamp = datetime.now().strftime("%H:%M:%S")
        prefix = colors.get(level, "") + f"[{level}]" + reset
        print(f"{prefix} {timestamp} - {message}")
    
    def health_check(self) -> bool:
        """Verify API connectivity"""
        try:
            response = requests.get(f"{self.api_base}/health", timeout=5)
            if response.status_code == 200:
                data = response.json()
                self.log("SUCCESS", f"API Health: {data.get('status', 'OK')}")
                return True
            else:
                self.log("ERROR", f"Health check failed with status {response.status_code}")
                return False
        except Exception as e:
            self.log("ERROR", f"Health check error: {e}")
            return False
    
    def upload_document(self, file_path: str, options: Dict = None) -> Optional[str]:
        """Upload a single document and return job_id"""
        if options is None:
            options = {
                "output_formats": "json,structured",
                "include_coordinates": "true",
                "deskew": "true",
                "enhance": "true",
            }
        
        if not os.path.exists(file_path):
            self.log("ERROR", f"File not found: {file_path}")
            return None
        
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        self.metrics["job_sizes"].append(file_size_mb)
        
        try:
            self.log("INFO", f"Uploading {Path(file_path).name} ({file_size_mb:.2f} MB)")
            
            with open(file_path, "rb") as f:
                files = {"document": f}
                upload_start = time.time()
                
                response = requests.post(
                    f"{self.api_base}/jobs/upload",
                    headers=self.headers,
                    files=files,
                    data=options,
                    timeout=30
                )
                
                upload_time = time.time() - upload_start
                self.metrics["upload_times"].append(upload_time)
                
                if response.status_code in [200, 202]:
                    data = response.json()
                    job_id = data.get("job_id")
                    self.log("SUCCESS", f"Upload complete in {upload_time:.2f}s (Job: {job_id})")
                    return job_id
                else:
                    self.log("ERROR", f"Upload failed: {response.status_code} - {response.text}")
                    return None
        except Exception as e:
            self.log("ERROR", f"Upload error: {e}")
            return None
    
    def monitor_job(self, job_id: str, max_wait: int = 300, poll_interval: int = 5) -> Optional[Dict]:
        """Monitor job progress until completion"""
        self.log("INFO", f"Monitoring job: {job_id}")
        
        start_time = time.time()
        process_start = time.time()
        
        while True:
            elapsed = time.time() - start_time
            if elapsed > max_wait:
                self.log("ERROR", f"Job {job_id} timeout after {max_wait}s")
                self.metrics["failure_count"] += 1
                return None
            
            try:
                response = requests.get(
                    f"{self.api_base}/jobs/{job_id}",
                    headers=self.headers,
                    timeout=10
                )
                
                if response.status_code != 200:
                    self.log("ERROR", f"Status check failed: {response.status_code}")
                    continue
                
                data = response.json()
                status = data.get("status")
                
                self.log("INFO", f"  Status: {status} (elapsed: {elapsed:.1f}s)")
                
                if status == "COMPLETED":
                    process_time = time.time() - process_start
                    self.metrics["processing_times"].append(process_time)
                    self.metrics["success_count"] += 1
                    self.log("SUCCESS", f"Job completed in {process_time:.2f}s")
                    return data
                
                elif status == "FAILED":
                    self.log("ERROR", f"Job failed: {data.get('error', 'Unknown error')}")
                    self.metrics["failure_count"] += 1
                    return None
                
                time.sleep(poll_interval)
                
            except Exception as e:
                self.log("ERROR", f"Monitor error: {e}")
                time.sleep(poll_interval)
    
    def get_results(self, job_id: str) -> Optional[Dict]:
        """Retrieve job results"""
        try:
            response = requests.get(
                f"{self.api_base}/jobs/{job_id}/result",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                self.log("ERROR", f"Failed to retrieve results: {response.status_code}")
                return None
        except Exception as e:
            self.log("ERROR", f"Result retrieval error: {e}")
            return None
    
    def analyze_result(self, result: Dict, filename: str) -> Dict:
        """Analyze and validate result"""
        analysis = {
            "filename": filename,
            "timestamp": datetime.now().isoformat(),
            "document_type": result.get("document_type", "unknown"),
            "pages": result.get("pages", 0),
            "has_text": "text_content" in result and len(result.get("text_content", "")) > 0,
            "has_json": "json_data" in result,
            "has_tables": "tables" in result and len(result.get("tables", [])) > 0,
            "text_length": len(result.get("text_content", "")),
            "table_count": len(result.get("tables", [])),
            "extraction_confidence": result.get("confidence", 0),
        }
        
        self.log("METRIC", f"Result Analysis for {filename}:")
        self.log("METRIC", f"  - Document Type: {analysis['document_type']}")
        self.log("METRIC", f"  - Pages: {analysis['pages']}")
        self.log("METRIC", f"  - Text Extracted: {analysis['text_length']} chars")
        self.log("METRIC", f"  - Tables Found: {analysis['table_count']}")
        self.log("METRIC", f"  - Confidence: {analysis['extraction_confidence']:.2%}")
        
        return analysis
    
    def test_batch(self, file_paths: List[str]) -> bool:
        """Test batch upload"""
        if len(file_paths) < 2:
            self.log("WARN", "Batch test requires at least 2 files, skipping")
            return True
        
        self.log("INFO", f"Testing batch upload with {len(file_paths)} files")
        
        try:
            files = [("documents", open(f, "rb")) for f in file_paths if os.path.exists(f)]
            
            response = requests.post(
                f"{self.api_base}/jobs/batch",
                headers=self.headers,
                files=files,
                data={"output_formats": "json"},
                timeout=60
            )
            
            for _, f in files:
                f.close()
            
            if response.status_code in [200, 202]:
                data = response.json()
                self.log("SUCCESS", f"Batch uploaded: {data.get('batch_id')}")
                return True
            else:
                self.log("ERROR", f"Batch upload failed: {response.status_code}")
                return False
        except Exception as e:
            self.log("ERROR", f"Batch test error: {e}")
            return False
    
    def print_metrics(self):
        """Print final metrics summary"""
        self.log("INFO", "\n" + "=" * 60)
        self.log("METRIC", "FINAL METRICS SUMMARY")
        self.log("INFO", "=" * 60)
        
        if self.metrics["upload_times"]:
            avg_upload = statistics.mean(self.metrics["upload_times"])
            max_upload = max(self.metrics["upload_times"])
            self.log("METRIC", f"Upload Time - Avg: {avg_upload:.2f}s, Max: {max_upload:.2f}s")
        
        if self.metrics["processing_times"]:
            avg_process = statistics.mean(self.metrics["processing_times"])
            max_process = max(self.metrics["processing_times"])
            self.log("METRIC", f"Processing Time - Avg: {avg_process:.2f}s, Max: {max_process:.2f}s")
        
        if self.metrics["job_sizes"]:
            avg_size = statistics.mean(self.metrics["job_sizes"])
            self.log("METRIC", f"Average File Size: {avg_size:.2f} MB")
        
        self.log("METRIC", f"Success: {self.metrics['success_count']}, Failures: {self.metrics['failure_count']}")
        self.log("INFO", "=" * 60 + "\n")

def main():
    parser = argparse.ArgumentParser(description="IDEP E2E GPU Test (Python)")
    parser.add_argument("--testfiles", default="testfiles", help="Path to testfiles directory")
    parser.add_argument("--api-base", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--api-key", default="tp-proj-dev-key-123", help="API key")
    parser.add_argument("--limit", type=int, default=5, help="Max files to test")
    parser.add_argument("--batch", action="store_true", help="Test batch upload")
    parser.add_argument("--output", help="Save results to JSON file")
    
    args = parser.parse_args()
    
    # Initialize tester
    tester = IDEPTester(args.api_base, args.api_key)
    
    # Health check
    tester.log("INFO", "Starting IDEP E2E Test Suite")
    if not tester.health_check():
        tester.log("ERROR", "API is not healthy. Ensure services are running.")
        sys.exit(1)
    
    # Find test files
    testfiles_dir = Path(args.testfiles)
    if not testfiles_dir.exists():
        tester.log("ERROR", f"Test files directory not found: {args.testfiles}")
        sys.exit(1)
    
    pdf_files = list(testfiles_dir.glob("*.pdf"))[:args.limit]
    
    if not pdf_files:
        tester.log("ERROR", f"No PDF files found in {args.testfiles}")
        sys.exit(1)
    
    tester.log("INFO", f"Found {len(pdf_files)} test files")
    
    # Test single uploads
    all_results = []
    for pdf_file in pdf_files:
        tester.log("INFO", f"\n--- Testing: {pdf_file.name} ---")
        
        # Upload
        job_id = tester.upload_document(str(pdf_file))
        if not job_id:
            continue
        
        # Monitor
        status = tester.monitor_job(job_id)
        if not status:
            continue
        
        # Get results
        result = tester.get_results(job_id)
        if not result:
            continue
        
        # Analyze
        analysis = tester.analyze_result(result, pdf_file.name)
        all_results.append(analysis)
    
    # Batch test
    if args.batch and len(pdf_files) > 1:
        tester.log("INFO", "\n--- Testing Batch Upload ---")
        tester.test_batch([str(f) for f in pdf_files[:3]])
    
    # Metrics
    tester.print_metrics()
    
    # Save results
    if args.output:
        output_dir = Path(args.output).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_data = {
            "timestamp": datetime.now().isoformat(),
            "metrics": tester.metrics,
            "results": all_results,
        }
        
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2)
        
        tester.log("SUCCESS", f"Results saved to {args.output}")

if __name__ == "__main__":
    main()
