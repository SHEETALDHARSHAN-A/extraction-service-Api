FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir flask

COPY docker/mock-triton-server.py /app/docker/mock-triton-server.py

EXPOSE 8000 8001 8002

CMD ["python", "/app/docker/mock-triton-server.py"]
