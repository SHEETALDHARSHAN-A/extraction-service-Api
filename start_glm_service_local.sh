#!/bin/bash

# Start GLM-OCR Service Locally for Testing

echo "=========================================="
echo "Starting GLM-OCR Service Locally"
echo "=========================================="
echo ""

echo "Setting environment variables..."
export GLM_MODEL_PATH=zai-org/GLM-OCR
export GLM_PRECISION_MODE=normal
export SERVICE_HOST=0.0.0.0
export SERVICE_PORT=8002
export LOG_LEVEL=INFO
export MAX_TOKENS_DEFAULT=2048
export USE_ISOLATED_GPU_EXECUTOR=false

echo ""
echo "Starting service on http://localhost:8002"
echo "Press Ctrl+C to stop"
echo ""

cd services/glm-ocr-service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
