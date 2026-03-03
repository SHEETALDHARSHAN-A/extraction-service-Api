"""
Standalone GLM-OCR API Test (No Docker)
========================================
Tests the GLM-OCR model directly without Docker/Triton infrastructure.
Simulates the full API workflow: upload → process → result
"""

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any
import argparse

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add model to path
MODEL_DIR = Path(__file__).parent / "services" / "triton-models" / "glm_ocr" / "1"
sys.path.insert(0, str(MODEL_DIR))

# Configure environment
os.environ["IDEP_MOCK_INFERENCE"] = "false"
os.environ["IDEP_STRICT_REAL"] = "false"
os.environ["GLM_MODEL_PATH"] = "zai-org/GLM-OCR"


class StandaloneGLMOCR:
    """Standalone GLM-OCR service without Docker/Triton"""
    
    def __init__(self):
        self.model = None
        self.initialized = False
        
    def initialize(self):
        """Initialize the GLM-OCR model"""
        logger.info("Initializing GLM-OCR model...")
        
        try:
            import torch
            logger.info(f"CUDA available: {torch.cuda.is_available()}")
            if torch.cuda.is_available():
                logger.info(f"GPU: {torch.cuda.get_device_name(0)}")
                logger.info(f"Memory: {torch.cuda.get_device_properties(0).total_memory / (1024**3):.2f} GB")
        except Exception as e:
            logger.warning(f"GPU check failed: {e}")
        
        try:
            import model as triton_model
            
            self.model = triton_model.TritonPythonModel()
            start_time = time.time()
            self.model.initialize({})
            init_time = time.time() - start_time
            
            logger.info(f"✅ Model initialized in {init_time:.2f}s")
            logger.info(f"   Device: {self.model._device}")
            logger.info(f"   MOCK mode: {triton_model.MOCK_MODE}")
            logger.info(f"   Model loaded: {self.model.model is not None}")
            logger.info(f"   Processor loaded: {self.model.processor is not None}")
            
            self.initialized = True
            return True
            
        except Exception as e:
            logger.error(f"❌ Model initialization failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def extract_document(
        self,
        image_path: str,
        output_format: str = "json",
        include_coordinates: bool = True,
        include_word_confidence: bool = False,
        include_page_layout: bool = False,
        custom_prompt: str = "",
        precision_mode: str = "normal",
        max_tokens: int = 4096,
        extract_fields: list = None
    ) -> Dict[str, Any]:
        """
        Extract content from document
        
        Args:
            image_path: Path to image/document file
            output_format: One of: text, json, markdown, table, key_value, structured
            include_coordinates: Include bounding boxes
            include_word_confidence: Include per-word confidence
            include_page_layout: Include page layout analysis
            custom_prompt: Custom extraction prompt (overrides output_format)
            precision_mode: normal, high, or precision
            max_tokens: Maximum tokens to generate
            extract_fields: List of specific fields to extract
            
        Returns:
            Dictionary with extraction results
        """
        if not self.initialized:
            raise RuntimeError("Model not initialized. Call initialize() first.")
        
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")
        
        logger.info(f"Processing: {image_path}")
        logger.info(f"  Format: {output_format}")
        logger.info(f"  Coordinates: {include_coordinates}")
        logger.info(f"  Custom prompt: {bool(custom_prompt)}")
        
        start_time = time.time()
        
        try:
            import model as triton_model
            
            # Call inference
            if not triton_model.MOCK_MODE:
                result = self.model._native_inference(
                    image_ref=image_path,
                    prompt_override=custom_prompt,
                    output_format=output_format,
                    include_coords=include_coordinates,
                    include_word_conf=include_word_confidence,
                    max_tokens=max_tokens,
                    precision=precision_mode
                )
            else:
                result = triton_model._MockEngine.run(
                    image_ref=image_path,
                    prompt_override=custom_prompt,
                    output_format=output_format,
                    include_coords=include_coordinates,
                    include_word_conf=include_word_confidence,
                    include_page_layout=include_page_layout,
                    precision=precision_mode
                )
            
            processing_time = time.time() - start_time
            
            # Build API-like response
            response = {
                "model": "glm-ocr",
                "processing_time_ms": int(processing_time * 1000),
                "document_confidence": result.get("confidence", 0.0),
                "page_count": len(result.get("pages", [])),
                "mode": result.get("mode", "unknown"),
                "device": str(self.model._device),
                "result": self._format_result(result, output_format, extract_fields)
            }
            
            logger.info(f"✅ Processing completed in {processing_time:.2f}s")
            logger.info(f"   Confidence: {response['document_confidence']:.4f}")
            logger.info(f"   Pages: {response['page_count']}")
            logger.info(f"   Mode: {response['mode']}")
            
            return response
            
        except Exception as e:
            logger.error(f"❌ Extraction failed: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def _format_result(self, raw_result: Dict, output_format: str, extract_fields: list = None) -> Dict:
        """Format raw result into API response format"""
        
        if not raw_result.get("pages"):
            return {"error": "No pages extracted"}
        
        page = raw_result["pages"][0]
        
        if not page.get("elements"):
            return {"error": "No elements extracted"}
        
        element = page["elements"][0]
        content = element.get("content", "")
        
        # Parse JSON formats
        if output_format in ("json", "table", "key_value", "structured"):
            try:
                parsed_content = json.loads(content)
                
                # Filter fields if requested
                if extract_fields and output_format == "json":
                    if "fields" in parsed_content:
                        filtered_fields = {
                            k: v for k, v in parsed_content["fields"].items()
                            if k in extract_fields
                        }
                        parsed_content["fields"] = filtered_fields
                
                return parsed_content
                
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse {output_format} content as JSON")
                return {"raw_content": content}
        
        # Text formats
        return {"content": content}
    
    def get_gpu_stats(self) -> Dict[str, Any]:
        """Get GPU memory usage statistics"""
        try:
            import torch
            
            if not torch.cuda.is_available():
                return {"status": "no_cuda"}
            
            torch.cuda.synchronize()
            
            return {
                "status": "cuda_available",
                "device": torch.cuda.get_device_name(0),
                "allocated_gb": torch.cuda.memory_allocated(0) / (1024**3),
                "reserved_gb": torch.cuda.memory_reserved(0) / (1024**3),
                "total_gb": torch.cuda.get_device_properties(0).total_memory / (1024**3)
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def finalize(self):
        """Cleanup resources"""
        if self.model:
            self.model.finalize()
            logger.info("Model finalized")


def run_comprehensive_test():
    """Run comprehensive test suite"""
    
    print("="*80)
    print("GLM-OCR Standalone API Test")
    print("="*80)
    print()
    
    # Initialize service
    service = StandaloneGLMOCR()
    if not service.initialize():
        print("❌ Initialization failed")
        return False
    
    print()
    
    # Test file
    test_image = "test_invoice_local.png"
    if not os.path.exists(test_image):
        print(f"❌ Test file not found: {test_image}")
        print("Available test files:")
        for ext in ["*.png", "*.jpg", "*.pdf"]:
            import glob
            files = glob.glob(ext) + glob.glob(f"testfiles/{ext}")
            for f in files[:5]:
                print(f"  - {f}")
        return False
    
    print(f"Using test file: {test_image}")
    print()
    
    # Test 1: JSON extraction
    print("[Test 1] JSON Format with Coordinates")
    print("-" * 40)
    try:
        result = service.extract_document(
            image_path=test_image,
            output_format="json",
            include_coordinates=True
        )
        
        print(f"✅ Success")
        print(f"   Processing time: {result['processing_time_ms']}ms")
        print(f"   Confidence: {result['document_confidence']:.4f}")
        print(f"   Device: {result['device']}")
        print(f"   Mode: {result['mode']}")
        print()
        print("Result preview:")
        print(json.dumps(result['result'], indent=2)[:500] + "...")
        
    except Exception as e:
        print(f"❌ Failed: {e}")
    
    print()
    
    # Test 2: Custom prompt
    print("[Test 2] Custom Prompt")
    print("-" * 40)
    try:
        result = service.extract_document(
            image_path=test_image,
            custom_prompt="Extract invoice number, date, and total amount. Return as JSON.",
            output_format="text"
        )
        
        print(f"✅ Success")
        print(f"   Processing time: {result['processing_time_ms']}ms")
        print()
        print("Result:")
        print(json.dumps(result['result'], indent=2)[:300] + "...")
        
    except Exception as e:
        print(f"❌ Failed: {e}")
    
    print()
    
    # Test 3: All formats
    print("[Test 3] All Output Formats")
    print("-" * 40)
    formats = ["text", "json", "markdown", "table", "key_value", "structured"]
    
    for fmt in formats:
        try:
            result = service.extract_document(
                image_path=test_image,
                output_format=fmt,
                include_coordinates=False
            )
            print(f"   {fmt:12s} - ✅ OK ({result['processing_time_ms']}ms)")
            
        except Exception as e:
            print(f"   {fmt:12s} - ❌ FAILED: {e}")
    
    print()
    
    # Test 4: High precision mode
    print("[Test 4] High Precision Mode")
    print("-" * 40)
    try:
        result = service.extract_document(
            image_path=test_image,
            output_format="json",
            precision_mode="high",
            include_coordinates=True
        )
        
        print(f"✅ Success")
        print(f"   Processing time: {result['processing_time_ms']}ms")
        print(f"   Confidence: {result['document_confidence']:.4f}")
        
    except Exception as e:
        print(f"❌ Failed: {e}")
    
    print()
    
    # Test 5: Field extraction
    print("[Test 5] Field Extraction")
    print("-" * 40)
    try:
        result = service.extract_document(
            image_path=test_image,
            output_format="json",
            extract_fields=["invoice_number", "date", "total_amount"]
        )
        
        print(f"✅ Success")
        print(f"   Extracted fields: {list(result['result'].get('fields', {}).keys())}")
        
    except Exception as e:
        print(f"❌ Failed: {e}")
    
    print()
    
    # GPU stats
    print("[GPU Statistics]")
    print("-" * 40)
    stats = service.get_gpu_stats()
    if stats["status"] == "cuda_available":
        print(f"   Device: {stats['device']}")
        print(f"   Allocated: {stats['allocated_gb']:.2f} GB")
        print(f"   Reserved: {stats['reserved_gb']:.2f} GB")
        print(f"   Total: {stats['total_gb']:.2f} GB")
        print(f"   Usage: {stats['allocated_gb']/stats['total_gb']*100:.1f}%")
    else:
        print(f"   Status: {stats['status']}")
    
    print()
    
    # Cleanup
    service.finalize()
    
    print("="*80)
    print("✅ All tests completed!")
    print("="*80)
    
    return True


def run_single_extraction(args):
    """Run single document extraction"""
    
    service = StandaloneGLMOCR()
    if not service.initialize():
        return False
    
    try:
        result = service.extract_document(
            image_path=args.input,
            output_format=args.format,
            include_coordinates=args.coordinates,
            include_word_confidence=args.word_confidence,
            custom_prompt=args.prompt,
            precision_mode=args.precision,
            extract_fields=args.fields.split(",") if args.fields else None
        )
        
        # Save result
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"✅ Result saved to: {args.output}")
        else:
            print(json.dumps(result, indent=2))
        
        return True
        
    except Exception as e:
        print(f"❌ Extraction failed: {e}")
        return False
    
    finally:
        service.finalize()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Standalone GLM-OCR API Test")
    parser.add_argument("--test", action="store_true", help="Run comprehensive test suite")
    parser.add_argument("--input", "-i", help="Input image/document path")
    parser.add_argument("--output", "-o", help="Output JSON file path")
    parser.add_argument("--format", "-f", default="json", 
                       choices=["text", "json", "markdown", "table", "key_value", "structured"],
                       help="Output format")
    parser.add_argument("--coordinates", action="store_true", help="Include bounding boxes")
    parser.add_argument("--word-confidence", action="store_true", help="Include word confidence")
    parser.add_argument("--prompt", "-p", default="", help="Custom extraction prompt")
    parser.add_argument("--precision", default="normal", 
                       choices=["normal", "high", "precision"],
                       help="Precision mode")
    parser.add_argument("--fields", help="Comma-separated list of fields to extract")
    
    args = parser.parse_args()
    
    if args.test or (not args.input):
        # Run comprehensive test
        success = run_comprehensive_test()
        sys.exit(0 if success else 1)
    else:
        # Run single extraction
        success = run_single_extraction(args)
        sys.exit(0 if success else 1)
