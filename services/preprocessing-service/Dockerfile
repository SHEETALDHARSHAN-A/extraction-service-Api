FROM python:3.11-slim

ARG PREPROCESSING_PROFILE=full

ENV PIP_NO_CACHE_DIR=1

# PREPROCESSING_PROFILE options:
# - full: includes OpenCV and OCR/image tooling
# - lean: keeps only core PDF + archive tooling for smaller deployments
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl poppler-utils unrar-free p7zip-full; \
    if [ "$PREPROCESSING_PROFILE" = "full" ]; then \
        apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng imagemagick libgl1 libglib2.0-0 libreoffice; \
    fi; \
    curl -fsSL -o /bin/grpc_health_probe https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/v0.4.19/grpc_health_probe-linux-amd64; \
    chmod +x /bin/grpc_health_probe; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /root/
COPY services/preprocessing-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN if [ "$PREPROCESSING_PROFILE" = "full" ]; then \
        pip install --no-cache-dir opencv-python-headless==4.9.0.80 numpy==1.26.4 Pillow==10.2.0; \
    fi

COPY services/preprocessing-service/main.py .
COPY services/preprocessing-service/image_enhancer.py .
COPY services/preprocessing-service/archive_extractor.py .

EXPOSE 50051
CMD ["python", "main.py"]
