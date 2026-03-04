# Monitoring Setup Verification Script
# This script verifies that all monitoring components are properly configured

Write-Host "🔍 Verifying Monitoring Setup..." -ForegroundColor Cyan
Write-Host ""

# Check if required files exist
Write-Host "📁 Checking configuration files..." -ForegroundColor Yellow
$files = @(
    "docker/prometheus.yml",
    "docker/prometheus-alerts.yml",
    "docker/grafana/provisioning/datasources/prometheus.yml",
    "docker/grafana/provisioning/dashboards/dashboards.yml",
    "docker/grafana/dashboards/gpu-monitoring.json",
    "docker/grafana/dashboards/queue-monitoring.json",
    "docker/grafana/dashboards/request-processing.json"
)

$allFilesExist = $true
foreach ($file in $files) {
    if (Test-Path $file) {
        Write-Host "  ✅ $file" -ForegroundColor Green
    } else {
        Write-Host "  ❌ $file (missing)" -ForegroundColor Red
        $allFilesExist = $false
    }
}

if (-not $allFilesExist) {
    Write-Host ""
    Write-Host "❌ Some configuration files are missing!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "📊 Validating dashboard JSON files..." -ForegroundColor Yellow
$dashboards = Get-ChildItem -Path "docker/grafana/dashboards/*.json"
foreach ($dashboard in $dashboards) {
    try {
        $null = Get-Content $dashboard.FullName | ConvertFrom-Json
        Write-Host "  ✅ $($dashboard.Name) - valid JSON" -ForegroundColor Green
    } catch {
        Write-Host "  ❌ $($dashboard.Name) - invalid JSON" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "🔧 Checking Prometheus configuration..." -ForegroundColor Yellow
$prometheusConfig = Get-Content "docker/prometheus.yml" -Raw
if ($prometheusConfig -match "rule_files:") {
    Write-Host "  ✅ Alert rules configured" -ForegroundColor Green
} else {
    Write-Host "  ❌ Alert rules not configured" -ForegroundColor Red
    exit 1
}

if ($prometheusConfig -match "glm-ocr-service") {
    Write-Host "  ✅ GLM-OCR service scrape configured" -ForegroundColor Green
} else {
    Write-Host "  ❌ GLM-OCR service scrape not configured" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "🎯 Checking Grafana provisioning..." -ForegroundColor Yellow
$grafanaDatasource = Get-Content "docker/grafana/provisioning/datasources/prometheus.yml" -Raw
if ($grafanaDatasource -match "Prometheus") {
    Write-Host "  ✅ Prometheus datasource configured" -ForegroundColor Green
} else {
    Write-Host "  ❌ Prometheus datasource not configured" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "✅ All monitoring configuration files are valid!" -ForegroundColor Green
Write-Host ""
Write-Host "📝 Next steps:" -ForegroundColor Cyan
Write-Host "  1. Start services: docker-compose up -d"
Write-Host "  2. Access Grafana: http://localhost:3000"
Write-Host "     Username: admin, Password: idep-admin"
Write-Host "  3. Access Prometheus: http://localhost:9090"
Write-Host "  4. Access Jaeger: http://localhost:16686"
Write-Host ""
Write-Host "📚 See docker/MONITORING.md for detailed documentation" -ForegroundColor Cyan
