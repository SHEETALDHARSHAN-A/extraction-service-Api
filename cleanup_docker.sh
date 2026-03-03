#!/bin/bash

echo "🧹 Starting comprehensive Docker cleanup..."
echo ""

# Stop all running containers
echo "⏹️  Stopping all Docker containers..."
docker-compose -f docker/docker-compose.yml down

# Remove all containers (including stopped ones)
echo "🗑️  Removing all containers..."
docker container prune -f

# Remove all volumes (including named volumes)
echo "💾 Removing all Docker volumes..."
docker volume rm -f $(docker volume ls -q) 2>/dev/null || echo "No volumes to remove"

# Specifically remove project volumes
echo "📦 Removing project-specific volumes..."
docker volume rm -f docker_postgres_data docker_minio_data docker_prometheus_data docker_grafana_data docker_idep_tmp docker_hf_cache 2>/dev/null || echo "Project volumes already removed"

# Remove all images
echo "🖼️  Removing all Docker images..."
docker image prune -a -f

# Remove build cache
echo "🏗️  Removing Docker build cache..."
docker builder prune -a -f

# Remove networks
echo "🌐 Removing unused networks..."
docker network prune -f

# System-wide cleanup
echo "🔧 Running system-wide Docker cleanup..."
docker system prune -a --volumes -f

# Clean up local HuggingFace cache directory
echo "🤗 Removing local HuggingFace cache..."
rm -rf hf_cache_probe

echo ""
echo "✅ Docker cleanup complete!"
echo ""
echo "📊 Current Docker disk usage:"
docker system df
