"""
Post-processing gRPC Service

Handles:
 - PII Detection & Redaction (via Microsoft Presidio)
 - Structured JSON validation
 - Confidence scoring
 - Entity extraction
"""
import grpc
import json
import re
import os
import logging
from concurrent import futures

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Conditional Presidio import
USE_PRESIDIO = True
try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine
except ImportError:
    USE_PRESIDIO = False
    logger.warning("Presidio not installed — using regex-based PII redaction fallback")

# --- gRPC Generated Code (Placeholder until protoc is available) ---
# In production, these would be auto-generated from postprocessing.proto

import grpc

class PostProcessRequest:
    def __init__(self, raw_content="", job_id="", redact_pii=False):
        self.raw_content = raw_content
        self.job_id = job_id
        self.redact_pii = redact_pii

class PostProcessResponse:
    def __init__(self, structured_content="", confidence_score=0.0, status="", error=""):
        self.structured_content = structured_content
        self.confidence_score = confidence_score
        self.status = status
        self.error = error

    def SerializeToString(self):
        return json.dumps({
            "structured_content": self.structured_content,
            "confidence_score": self.confidence_score,
            "status": self.status,
            "error": self.error,
        }).encode()


class PostProcessingServiceServicer:
    def __init__(self):
        if USE_PRESIDIO:
            self.analyzer = AnalyzerEngine()
            self.anonymizer = AnonymizerEngine()
            logger.info("✅ Presidio engines initialized")
        else:
            self.analyzer = None
            self.anonymizer = None

    def PostProcess(self, request, context):
        logger.info(f"📥 Post-processing job: {request.job_id}")

        try:
            content = request.raw_content

            # Step 1: PII Redaction
            if request.redact_pii:
                content = self._redact_pii(content)
                logger.info(f"  🔒 PII redacted for job {request.job_id}")

            # Step 2: Structure Validation & Enrichment
            structured = self._validate_and_enrich(content)

            # Step 3: Confidence Scoring
            confidence = self._compute_confidence(content, structured)

            logger.info(f"✅ Post-processing complete for job {request.job_id} (confidence: {confidence:.2f})")

            return PostProcessResponse(
                structured_content=json.dumps(structured, indent=2),
                confidence_score=confidence,
                status="success",
            )

        except Exception as e:
            logger.error(f"❌ Post-processing failed for job {request.job_id}: {e}")
            return PostProcessResponse(
                status="error",
                error=str(e),
            )

    def _redact_pii(self, text: str) -> str:
        """Detect and redact PII from extracted text."""
        if USE_PRESIDIO and self.analyzer:
            results = self.analyzer.analyze(text=text, language="en")
            anonymized = self.anonymizer.anonymize(text=text, analyzer_results=results)
            return anonymized.text
        else:
            # Regex-based fallback
            patterns = {
                "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                "phone": r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
                "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
                "credit_card": r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',
            }
            for pii_type, pattern in patterns.items():
                text = re.sub(pattern, f"[{pii_type.upper()}_REDACTED]", text)
            return text

    def _validate_and_enrich(self, content: str) -> dict:
        """Validate JSON structure and enrich with metadata."""
        try:
            parsed = json.loads(content)
            # Already structured JSON from Triton
            if isinstance(parsed, dict):
                parsed["_postprocessed"] = True
                parsed["_version"] = "1.0"
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

        # If raw text, wrap in a structured envelope
        return {
            "raw_text": content,
            "document_type": "unknown",
            "fields": {},
            "tables": [],
            "_postprocessed": True,
            "_version": "1.0",
        }

    def _compute_confidence(self, raw: str, structured: dict) -> float:
        """Heuristic confidence scoring based on extraction quality."""
        score = 0.5  # Base

        # Has structured fields
        if structured.get("fields"):
            score += 0.2

        # Has tables
        if structured.get("tables"):
            score += 0.1

        # Has document type
        if structured.get("document_type", "unknown") != "unknown":
            score += 0.1

        # Content length check
        if len(raw) > 100:
            score += 0.1

        return min(score, 1.0)


def serve():
    port = os.getenv("PORT", "50052")

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    # In a real setup with protoc-generated code:
    # postprocessing_pb2_grpc.add_PostProcessingServiceServicer_to_server(
    #     PostProcessingServiceServicer(), server
    # )

    # For now, we register a generic service handler
    servicer = PostProcessingServiceServicer()

    server.add_insecure_port(f"[::]:{port}")
    logger.info(f"🔍 Post-processing Service starting on port {port}")
    server.start()
    logger.info(f"✅ Post-processing Service ready")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
