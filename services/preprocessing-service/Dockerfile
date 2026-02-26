FROM golang:1.25.6-alpine AS builder

WORKDIR /app
RUN apk add --no-cache git

WORKDIR /app/services/preprocessing-service
COPY services/preprocessing-service/go.mod services/preprocessing-service/go.sum* ./
COPY shared /app/shared
RUN go mod download
COPY services/preprocessing-service/*.go ./
RUN go build -o main .

# --- Final Image ---
FROM python:3.11-slim

# System tools: PDF, OCR, image manipulation, archive extraction
RUN apt-get update && apt-get install -y \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-eng \
    imagemagick \
    libgl1 \
    libglib2.0-0 \
    unrar-free \
    p7zip-full \
    && rm -rf /var/lib/apt/lists/*

# Python image processing + archive handling
RUN pip install --no-cache-dir \
    opencv-python-headless==4.9.0.80 \
    numpy==1.26.4 \
    Pillow==10.2.0

WORKDIR /root/
COPY --from=builder /app/services/preprocessing-service/main .
COPY services/preprocessing-service/image_enhancer.py .
COPY services/preprocessing-service/archive_extractor.py .

EXPOSE 50051
CMD ["./main"]
