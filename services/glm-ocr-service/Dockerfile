# GLM-OCR Service Dockerfile
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    TRANSFORMERS_CACHE=/opt/models \
    HF_HOME=/opt/models

# Install Python and dependencies
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3.10-dev \
    python3.10-venv \
    git \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set python3.10 as default
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1

# Install pip using get-pip.py to get the latest version
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3

# Create app directory
WORKDIR /app

# Copy requirements first for better caching
COPY services/glm-ocr-service/requirements.txt .

# Install Python dependencies with upgraded pip
RUN python3 -m pip install --upgrade pip setuptools wheel && \
    python3 -m pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/glm-ocr-service/app/ ./app/

# Create non-root user
RUN useradd -m -u 1000 glmocr && \
    chown -R glmocr:glmocr /app && \
    mkdir -p /opt/models && \
    chown -R glmocr:glmocr /opt/models

USER glmocr

# Expose port
EXPOSE 8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import requests; requests.get('http://localhost:8002/health').raise_for_status()"

# Run the application
CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
