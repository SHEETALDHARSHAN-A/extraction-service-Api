.PHONY: help preflight test test-advanced test-batch clean logs health

WORKSPACE_ROOT := $(shell pwd)
COMPOSE_FILE := docker/docker-compose.yml
SCRIPTS_DIR := scripts

help:
	@echo "╔════════════════════════════════════════════════════════════════╗"
	@echo "║     IDEP Testing & Development Commands                        ║"
	@echo "╚════════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "Testing Commands:"
	@echo "  make preflight       - Run GPU and Docker pre-flight checks"
	@echo "  make test            - Run full E2E test with GPU (PowerShell)"
	@echo "  make test-linux      - Run full E2E test with GPU (Bash/Linux)"
	@echo "  make test-advanced   - Run advanced Python testing with metrics"
	@echo "  make test-batch      - Test batch upload with multiple files"
	@echo ""
	@echo "Service Commands:"
	@echo "  make start           - Start all Docker services"
	@echo "  make stop            - Stop all Docker services"
	@echo "  make restart         - Restart Docker services"
	@echo "  make clean           - Stop and remove all containers/volumes"
	@echo ""
	@echo "Monitoring Commands:"
	@echo "  make logs            - View all service logs"
	@echo "  make logs-api        - View API Gateway logs"
	@echo "  make logs-triton     - View Triton GPU logs"
	@echo "  make logs-worker     - View Temporal Worker logs"
	@echo "  make health          - Check all services health"
	@echo "  make stats           - Show container resource usage"
	@echo ""
	@echo "Verification Commands:"
	@echo "  make verify-gpu      - Verify GPU access in Docker"
	@echo "  make verify-ports    - Check if required ports are free"
	@echo "  make verify-files    - Verify testfiles exist"
	@echo ""

# Testing
preflight:
	@powershell $(SCRIPTS_DIR)/preflight_check.ps1

test:
	@powershell $(SCRIPTS_DIR)/test_e2e_gpu.ps1

test-linux:
	@bash $(SCRIPTS_DIR)/test_e2e_gpu.sh

test-advanced:
	@echo "Running advanced Python testing..."
	@python $(SCRIPTS_DIR)/test_e2e_advanced.py \
		--testfiles testfiles \
		--limit 5 \
		--batch \
		--output testfiles/.results/metrics.json

test-batch:
	@echo "Testing batch upload..."
	@python $(SCRIPTS_DIR)/test_e2e_advanced.py \
		--testfiles testfiles \
		--limit 5 \
		--batch \
		--output testfiles/.results/batch_metrics.json

# Services
start:
	@echo "Starting Docker Compose services..."
	@docker-compose -f $(COMPOSE_FILE) up -d

stop:
	@echo "Stopping services..."
	@docker-compose -f $(COMPOSE_FILE) stop

restart:
	@echo "Restarting services..."
	@docker-compose -f $(COMPOSE_FILE) restart

clean:
	@echo "Stopping and removing containers..."
	@docker-compose -f $(COMPOSE_FILE) down -v
	@echo "Removing dangling images..."
	@docker system prune -a -f

# Logging
logs:
	@docker-compose -f $(COMPOSE_FILE) logs -f

logs-api:
	@docker-compose -f $(COMPOSE_FILE) logs -f api-gateway

logs-triton:
	@docker-compose -f $(COMPOSE_FILE) logs -f triton

logs-worker:
	@docker-compose -f $(COMPOSE_FILE) logs -f temporal-worker

logs-temporal:
	@docker-compose -f $(COMPOSE_FILE) logs -f temporal

logs-db:
	@docker-compose -f $(COMPOSE_FILE) logs -f db

# Health & Status
health:
	@echo "Checking service health..."
	@curl -s http://localhost:8000/health | jq . || echo "API Gateway not ready"
	@echo ""
	@echo "Container Status:"
	@docker-compose -f $(COMPOSE_FILE) ps

stats:
	@echo "Container Resource Usage:"
	@docker stats --no-stream

# Verification
verify-gpu:
	@echo "Checking GPU access in Docker..."
	@docker run --rm --gpus all nvidia/cuda:12.2.2-base-ubuntu22.04 nvidia-smi

verify-ports:
	@echo "Checking required ports..."
	@for port in 8000 8001 8002 8080 5432 6379 9000 9090 3000 16686; do \
		if nc -z localhost $$port 2>/dev/null; then \
			echo "[WARN] Port $$port is in use"; \
		else \
			echo "[OK] Port $$port is free"; \
		fi; \
	done

verify-files:
	@echo "Checking required files..."
	@test -f $(WORKSPACE_ROOT)/services/api-gateway/main.go && echo "[OK] API Gateway" || echo "[FAIL] API Gateway"
	@test -f $(WORKSPACE_ROOT)/services/triton-models/glm_ocr/1/model.py && echo "[OK] Triton Model" || echo "[FAIL] Triton Model"
	@test -d $(WORKSPACE_ROOT)/testfiles && echo "[OK] Test files directory" || echo "[FAIL] Test files directory"
	@test $$(find $(WORKSPACE_ROOT)/testfiles -name "*.pdf" | wc -l) -gt 0 && echo "[OK] PDF test files found" || echo "[WARN] No PDF test files"

# URLs
urls:
	@echo "╔════════════════════════════════════════════════╗"
	@echo "║  Service URLs                                  ║"
	@echo "╚════════════════════════════════════════════════╝"
	@echo ""
	@echo "API & Testing:"
	@echo "  API Gateway Health:  http://localhost:8000/health"
	@echo "  API Metrics:         http://localhost:8000/metrics"
	@echo ""
	@echo "Workflow & Orchestration:"
	@echo "  Temporal Web UI:     http://localhost:8080"
	@echo ""
	@echo "Storage & Data:"
	@echo "  MinIO Console:       http://localhost:9001"
	@echo "    Username: minioadmin"
	@echo "    Password: minioadmin"
	@echo "  PostgreSQL:          localhost:5432"
	@echo "    User: postgres"
	@echo "    Password: postgres"
	@echo ""
	@echo "Observability:"
	@echo "  Prometheus:          http://localhost:9090"
	@echo "  Grafana:             http://localhost:3000"
	@echo "    Username: admin"
	@echo "    Password: idep-admin"
	@echo "  Jaeger Tracing:      http://localhost:16686"
	@echo ""
	@echo "Inference:"
	@echo "  Triton HTTP:         http://localhost:8000"
	@echo "  Triton gRPC:         localhost:8001"
	@echo "  Triton Metrics:      http://localhost:8002/metrics"
	@echo ""

# Development
build:
	@echo "Building services locally..."
	@cd services/api-gateway && go build -o /tmp/api-gateway . && echo "[OK] API Gateway"
	@cd $(WORKSPACE_ROOT)/services/temporal-worker && go build -o /tmp/temporal-worker ./worker && echo "[OK] Temporal Worker"
	@cd $(WORKSPACE_ROOT)/services/preprocessing-service && go build -o /tmp/preprocessing . && echo "[OK] Preprocessing Service"

docker-build:
	@echo "Building Docker images..."
	@docker-compose -f $(COMPOSE_FILE) build

docker-build-no-cache:
	@echo "Building Docker images without cache..."
	@docker-compose -f $(COMPOSE_FILE) build --no-cache

# Documentation
docs:
	@echo "Opening testing guide..."
	@$(shell [ -f TESTING_GUIDE.md ] && cat TESTING_GUIDE.md | head -50)

# Quick start
quick-start: preflight start health
	@echo "✅ Services started! Now run: make test"
