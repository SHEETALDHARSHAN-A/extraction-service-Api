@echo off
REM ============================================
REM IDEP Testing Commands (Windows Batch)
REM Run: idep.bat help
REM ============================================

setlocal enabledelayedexpansion

if "%1"=="" (
    call :help
    exit /b 0
)

if /i "%1"=="help" (
    call :help
) else if /i "%1"=="preflight" (
    call :preflight
) else if /i "%1"=="test" (
    call :test
) else if /i "%1"=="advanced" (
    call :test_advanced
) else if /i "%1"=="batch" (
    call :test_batch
) else if /i "%1"=="start" (
    call :start_services
) else if /i "%1"=="stop" (
    call :stop_services
) else if /i "%1"=="restart" (
    call :restart_services
) else if /i "%1"=="clean" (
    call :clean
) else if /i "%1"=="logs" (
    call :logs
) else if /i "%1"=="logs-api" (
    call :logs_api
) else if /i "%1"=="logs-triton" (
    call :logs_triton
) else if /i "%1"=="logs-worker" (
    call :logs_worker
) else if /i "%1"=="health" (
    call :health
) else if /i "%1"=="stats" (
    call :stats
) else if /i "%1"=="verify-gpu" (
    call :verify_gpu
) else if /i "%1"=="verify-ports" (
    call :verify_ports
) else if /i "%1"=="urls" (
    call :urls
) else (
    echo Unknown command: %1
    echo Run: idep.bat help
    exit /b 1
)

goto :eof

:help
echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║  IDEP Platform - Testing Commands                          ║
echo ╚════════════════════════════════════════════════════════════╝
echo.
echo Testing Commands:
echo   idep.bat preflight       - Run GPU and Docker pre-flight checks
echo   idep.bat test            - Run full E2E test with GPU
echo   idep.bat advanced        - Run advanced Python testing with metrics
echo   idep.bat batch           - Test batch upload with multiple files
echo.
echo Service Commands:
echo   idep.bat start           - Start all Docker services
echo   idep.bat stop            - Stop all Docker services
echo   idep.bat restart         - Restart Docker services
echo   idep.bat clean           - Stop and remove all containers/volumes
echo.
echo Monitoring Commands:
echo   idep.bat logs            - View all service logs
echo   idep.bat logs-api        - View API Gateway logs
echo   idep.bat logs-triton     - View Triton GPU logs
echo   idep.bat logs-worker     - View Temporal Worker logs
echo   idep.bat health          - Check all services health
echo   idep.bat stats           - Show container resource usage
echo.
echo Verification Commands:
echo   idep.bat verify-gpu      - Verify GPU access in Docker
echo   idep.bat verify-ports    - Check if required ports are free
echo   idep.bat urls            - Show service endpoints
echo.
goto :eof

:preflight
echo Running pre-flight checks...
powershell scripts\preflight_check.ps1
goto :eof

:test
echo Running E2E test...
powershell scripts\test_e2e_gpu.ps1
goto :eof

:test_advanced
echo Running advanced Python testing...
python scripts\test_e2e_advanced.py ^
    --testfiles testfiles ^
    --limit 5 ^
    --batch ^
    --output testfiles/.results/metrics.json
goto :eof

:test_batch
echo Running batch upload test...
python scripts\test_e2e_advanced.py ^
    --testfiles testfiles ^
    --limit 5 ^
    --batch ^
    --output testfiles/.results/batch_metrics.json
goto :eof

:start_services
echo Starting Docker Compose services...
docker-compose -f docker\docker-compose.yml up -d
goto :eof

:stop_services
echo Stopping services...
docker-compose -f docker\docker-compose.yml stop
goto :eof

:restart_services
echo Restarting services...
docker-compose -f docker\docker-compose.yml restart
goto :eof

:clean
echo Stopping and removing containers...
docker-compose -f docker\docker-compose.yml down -v
echo Removing dangling images...
docker system prune -a -f
goto :eof

:logs
docker-compose -f docker\docker-compose.yml logs -f
goto :eof

:logs_api
docker-compose -f docker\docker-compose.yml logs -f api-gateway
goto :eof

:logs_triton
docker-compose -f docker\docker-compose.yml logs -f triton
goto :eof

:logs_worker
docker-compose -f docker\docker-compose.yml logs -f temporal-worker
goto :eof

:health
echo Checking service health...
curl -s http://localhost:8000/health | powershell -Command "Get-Content | ConvertFrom-Json | ConvertTo-Json"
echo.
echo Container Status:
docker-compose -f docker\docker-compose.yml ps
goto :eof

:stats
echo Container Resource Usage:
docker stats --no-stream
goto :eof

:verify_gpu
echo Checking GPU access in Docker...
docker run --rm --gpus all nvidia/cuda:12.2.2-base-ubuntu22.04 nvidia-smi
goto :eof

:verify_ports
echo Checking required ports...
for %%P in (8000 8001 8002 8080 5432 6379 9000 9090 3000 16686) do (
    netstat -ano | find ":%%P " > nul
    if !errorlevel! equ 0 (
        echo [WARN] Port %%P is in use
    ) else (
        echo [OK] Port %%P is free
    )
)
goto :eof

:urls
echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║  Service Endpoints                                         ║
echo ╚════════════════════════════════════════════════════════════╝
echo.
echo API ^& Testing:
echo   API Gateway Health:  http://localhost:8000/health
echo   API Metrics:         http://localhost:8000/metrics
echo.
echo Workflow ^& Orchestration:
echo   Temporal Web UI:     http://localhost:8080
echo.
echo Storage ^& Data:
echo   MinIO Console:       http://localhost:9001
echo     Username: minioadmin
echo     Password: minioadmin
echo   PostgreSQL:          localhost:5432
echo     User: postgres
echo     Password: postgres
echo.
echo Observability:
echo   Prometheus:          http://localhost:9090
echo   Grafana:             http://localhost:3000
echo     Username: admin
echo     Password: idep-admin
echo   Jaeger Tracing:      http://localhost:16686
echo.
echo Inference:
echo   Triton HTTP:         http://localhost:8000
echo   Triton gRPC:         localhost:8001
echo   Triton Metrics:      http://localhost:8002/metrics
echo.
goto :eof
