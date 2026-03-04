#!/bin/bash

# Monitoring Setup Verification Script
# This script verifies that all monitoring components are properly configured

set -e

echo "🔍 Verifying Monitoring Setup..."
echo ""

# Check if required files exist
echo "📁 Checking configuration files..."
files=(
    "docker/prometheus.yml"
    "docker/prometheus-alerts.yml"
    "docker/grafana/provisioning/datasources/prometheus.yml"
    "docker/grafana/provisioning/dashboards/dashboards.yml"
    "docker/grafana/dashboards/gpu-monitoring.json"
    "docker/grafana/dashboards/queue-monitoring.json"
    "docker/grafana/dashboards/request-processing.json"
)

for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✅ $file"
    else
        echo "  ❌ $file (missing)"
        exit 1
    fi
done

echo ""
echo "📊 Validating dashboard JSON files..."
for dashboard in docker/grafana/dashboards/*.json; do
    if python3 -m json.tool "$dashboard" > /dev/null 2>&1; then
        echo "  ✅ $(basename $dashboard) - valid JSON"
    else
        echo "  ❌ $(basename $dashboard) - invalid JSON"
        exit 1
    fi
done

echo ""
echo "🔧 Checking Prometheus configuration..."
if grep -q "rule_files:" docker/prometheus.yml; then
    echo "  ✅ Alert rules configured"
else
    echo "  ❌ Alert rules not configured"
    exit 1
fi

if grep -q "glm-ocr-service" docker/prometheus.yml; then
    echo "  ✅ GLM-OCR service scrape configured"
else
    echo "  ❌ GLM-OCR service scrape not configured"
    exit 1
fi

echo ""
echo "🎯 Checking Grafana provisioning..."
if grep -q "Prometheus" docker/grafana/provisioning/datasources/prometheus.yml; then
    echo "  ✅ Prometheus datasource configured"
else
    echo "  ❌ Prometheus datasource not configured"
    exit 1
fi

echo ""
echo "✅ All monitoring configuration files are valid!"
echo ""
echo "📝 Next steps:"
echo "  1. Start services: docker-compose up -d"
echo "  2. Access Grafana: http://localhost:3000 (admin/idep-admin)"
echo "  3. Access Prometheus: http://localhost:9090"
echo "  4. Access Jaeger: http://localhost:16686"
echo ""
echo "📚 See docker/MONITORING.md for detailed documentation"
