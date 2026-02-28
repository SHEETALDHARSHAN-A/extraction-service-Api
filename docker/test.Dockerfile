# ─────────────────────────────────────────────────────────────────────────────
# Lightweight GLM-OCR model.py test container
#
# Does NOT use the 8 GB nvcr.io/nvidia/tritonserver base image.
# Instead it stubs triton_python_backend_utils and runs model.py directly,
# exactly as scripts/test_model_unit.py does in local Python.
#
# Build:
#   docker build -f docker/test.Dockerfile -t idep-glmocr-test .
# Run:
#   docker run --rm idep-glmocr-test
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Only the packages actually imported by model.py in mock mode (no torch/paddle)
RUN pip install --no-cache-dir pillow numpy

# Copy just the files needed for the test
COPY services/triton-models/glm_ocr/1/model.py  services/triton-models/glm_ocr/1/model.py
COPY scripts/test_model_unit.py                 scripts/test_model_unit.py

# Env: force mock mode
ENV IDEP_MOCK_INFERENCE=true \
    IDEP_STRICT_REAL=false \
    GLM_MODEL_PATH=zai-org/GLM-OCR

CMD ["python", "scripts/test_model_unit.py"]
