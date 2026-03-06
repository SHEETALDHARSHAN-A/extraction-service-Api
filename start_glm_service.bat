@echo off
echo ================================================================================
echo STARTING GLM-OCR SERVICE
echo ================================================================================
echo.
echo Starting GLM-OCR Service on port 8002...
echo.

set USE_ISOLATED_GPU_EXECUTOR=false

cd services\glm-ocr-service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload

pause
