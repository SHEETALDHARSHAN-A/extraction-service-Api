@echo off
REM Start GLM-OCR Service Locally for Testing

echo ==========================================
echo Starting GLM-OCR Service Locally
echo ==========================================
echo.

echo Setting environment variables...
set GLM_MODEL_PATH=zai-org/GLM-OCR
set GLM_PRECISION_MODE=normal
set SERVICE_HOST=0.0.0.0
set SERVICE_PORT=8002
set LOG_LEVEL=INFO
set MAX_TOKENS_DEFAULT=2048

echo.
echo Starting service on http://localhost:8002
echo Press Ctrl+C to stop
echo.

cd services\glm-ocr-service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
