# Monitoring Dashboard Setup

This document describes the monitoring infrastructure for the GPU extraction production-ready system.

## Overview

The monitoring stack consists of:
- **Prometheus**: Metrics collection and storage
- **Grafana**: Visualization and dashboards
- **Jaeger**: Distributed tracing

## Architecture

```
┌─────────────────┐
│   Services      │
│  (API Gateway,  │
│  GLM-OCR, etc.) │
└────────┬────────┘
         │ /metrics
         ▼
┌─────────────────┐
│   Prometheus    │
│   (Port 9090)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Grafana      │
│   (Port 3000)   │
└─────────────────┘
```

## Accessing the Dashboards

### Grafana
- **URL**: http://localhost:3000
- **Username**: admin
- **Password**: idep-admin

### Prometheus
- **URL**: http://localhost:9090

### Jaeger
- **URL**: http://localhost:16686

## Available Dashboards

### 1. GPU Monitoring Dashboard
**UID**: `gpu-monitoring`

Displays real-time GPU metrics:
- **GPU Memory Allocated**: Current GPU memory in use (gauge)
- **GPU Memory Free**: Available GPU memory (gauge)
- **GPU Memory Usage Over Time**: Historical memory usage (time series)
- **GPU Memory Utilization %**: Percentage of GPU memory in use (gauge)

**Alerts**:
- High GPU Memory Usage (>90% for 2 minutes)
- Critical GPU Memory Usage (>95% for 1 minute)
- Low GPU Memory Available (<0.5GB for 2 minutes)

### 2. Queue Monitoring Dashboard
**UID**: `queue-monitoring`

Displays request queue metrics:
- **Current Queue Length**: Number of jobs waiting (gauge)
- **Jobs Being Processed**: Number of active jobs (gauge)
- **Average Wait Time**: Time jobs spend in queue (gauge)
- **Queue Length Over Time**: Historical queue length (time series)
- **Average Wait and Processing Time**: Historical timing metrics (time series)
- **Throughput**: Jobs processed per hour (time series)
- **Queue Activity Rates**: Enqueue and completion rates (time series)

**Alerts**:
- High Queue Length (>40 for 5 minutes)
- Queue Near Capacity (>45 for 2 minutes)
- High Average Wait Time (>120s for 5 minutes)

### 3. Request Processing Dashboard
**UID**: `request-processing`

Displays extraction request metrics:
- **Request Success/Failure Rates**: Rate of successful vs failed requests (time series)
- **Success Rate %**: Percentage of successful requests (gauge)
- **Error Rate %**: Percentage of failed requests (gauge)
- **Processing Time Percentiles**: p50, p95, p99 latencies (time series)
- **Request Status Distribution**: Pie chart of request statuses
- **Requests by Endpoint**: Pie chart of requests per endpoint
- **Average Processing Time by Endpoint**: Historical processing times (time series)

**Alerts**:
- High Error Rate (>10% for 5 minutes)
- Critical Error Rate (>25% for 2 minutes)
- Slow Processing Time (p95 >30s for 5 minutes)

## Metrics Exposed

### GPU Metrics (GLM-OCR Service)
- `gpu_memory_allocated_gb`: GPU memory allocated in GB
- `gpu_memory_free_gb`: GPU memory free in GB

### Queue Metrics (API Gateway)
- `queue_length`: Current number of jobs in queue
- `queue_processing_count`: Number of jobs being processed
- `queue_avg_wait_time_seconds`: Average wait time in queue
- `queue_avg_processing_time_seconds`: Average processing time
- `queue_throughput_per_hour`: Jobs processed per hour
- `queue_total_enqueued`: Total jobs enqueued (counter)
- `queue_total_completed`: Total jobs completed (counter)

### Extraction Metrics (GLM-OCR Service)
- `extraction_requests_total`: Total extraction requests (counter with labels: endpoint, status)
- `extraction_duration_seconds`: Processing time histogram (with labels: endpoint)

## Configuration Files

### Prometheus Configuration
- **Main config**: `docker/prometheus.yml`
- **Alert rules**: `docker/prometheus-alerts.yml`

### Grafana Configuration
- **Datasource**: `docker/grafana/provisioning/datasources/prometheus.yml`
- **Dashboard provider**: `docker/grafana/provisioning/dashboards/dashboards.yml`
- **Dashboards**: `docker/grafana/dashboards/*.json`

## Customizing Dashboards

Dashboards can be customized through the Grafana UI:
1. Navigate to http://localhost:3000
2. Go to Dashboards → Browse
3. Select the dashboard to edit
4. Click the gear icon (⚙️) to edit
5. Save changes

Changes made in the UI will persist in the Grafana database volume.

## Alert Configuration

Alerts are configured in `docker/prometheus-alerts.yml`. To modify:
1. Edit the alert rules file
2. Restart Prometheus: `docker-compose restart prometheus`
3. View active alerts at http://localhost:9090/alerts

## Troubleshooting

### Dashboards not appearing
1. Check Grafana logs: `docker-compose logs grafana`
2. Verify provisioning files are mounted: `docker-compose exec grafana ls /etc/grafana/provisioning/dashboards`
3. Restart Grafana: `docker-compose restart grafana`

### Metrics not showing
1. Check if services are exposing metrics:
   - API Gateway: http://localhost:8000/metrics
   - GLM-OCR Service: http://localhost:8002/metrics
   - Triton: http://localhost:18002/metrics
2. Check Prometheus targets: http://localhost:9090/targets
3. Verify Prometheus is scraping: `docker-compose logs prometheus`

### Alerts not firing
1. Check alert rules are loaded: http://localhost:9090/rules
2. Verify alert conditions are met
3. Check Prometheus logs: `docker-compose logs prometheus`

## Metrics Retention

- **Prometheus**: 30 days (configurable in docker-compose.yml)
- **Grafana**: Unlimited (stored in Grafana database)

## Performance Considerations

- Prometheus scrapes metrics every 15 seconds
- Dashboards refresh every 5 seconds
- Adjust refresh rates in dashboard settings if needed
- Monitor Prometheus memory usage for high-cardinality metrics

## Adding New Metrics

To add new metrics to services:

### Python (GLM-OCR Service)
```python
from prometheus_client import Counter, Gauge, Histogram

my_metric = Counter('my_metric_total', 'Description')
my_metric.inc()
```

### Go (API Gateway)
```go
import "github.com/prometheus/client_golang/prometheus/promauto"

var myMetric = promauto.NewCounter(prometheus.CounterOpts{
    Name: "my_metric_total",
    Help: "Description",
})
myMetric.Inc()
```

After adding metrics:
1. Update Prometheus scrape config if needed
2. Create/update Grafana dashboards
3. Add alert rules if appropriate

## References

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Prometheus Client Libraries](https://prometheus.io/docs/instrumenting/clientlibs/)
