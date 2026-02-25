#!/bin/bash
set -e

echo "🚀 Starting IDEP Platform Local Setup..."

# 1. Initialize Go Modules and Dependencies
echo "📦 Initializing Go dependencies..."
services=("services/api-gateway" "services/preprocessing-service" "services/temporal-worker")
for service in "${services[@]}"; do
    echo "  -> Processing $service..."
    (cd "$service" && go mod tidy)
done

# 2. Python Dependencies (for Post-processing and Triton Client if needed)
echo "🐍 Checking Python requirements..."
pip install -r requirements.txt

# 3. Docker Launch
echo "🐋 Launching microservices with Docker Compose..."
docker-compose -f docker/docker-compose.yml build
docker-compose -f docker/docker-compose.yml up -d

echo "✅ Setup Complete!"
echo "------------------------------------------------"
echo "API Gateway: http://localhost:8000"
echo "Temporal UI: http://localhost:8080"
echo "MinIO Console: http://localhost:9001"
echo "------------------------------------------------"
echo "Run 'docker-compose -f docker/docker-compose.yml logs -f' to see logs."
