FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/post-processing-service/requirements.txt .
RUN pip install -r requirements.txt

COPY services/post-processing-service .
COPY shared /app/shared

ENV PYTHONPATH=/app

EXPOSE 50052

CMD ["python", "main.py"]
