package middleware

import (
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

// --- Prometheus Metrics (§2.7) ---

var (
	httpRequestsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "idep_http_requests_total",
			Help: "Total number of HTTP requests",
		},
		[]string{"method", "path", "status"},
	)

	httpRequestDuration = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "idep_http_request_duration_seconds",
			Help:    "HTTP request duration in seconds",
			Buckets: []float64{0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0},
		},
		[]string{"method", "path"},
	)

	httpRequestSize = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "idep_http_request_size_bytes",
			Help:    "HTTP request size in bytes",
			Buckets: prometheus.ExponentialBuckets(100, 10, 7), // 100B to 100MB
		},
		[]string{"method", "path"},
	)

	activeJobs = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "idep_active_jobs",
		Help: "Number of currently processing jobs",
	})

	jobsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "idep_jobs_total",
			Help: "Total number of jobs by status",
		},
		[]string{"status"},
	)

	documentPages = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "idep_document_pages",
		Help:    "Number of pages per document",
		Buckets: []float64{1, 5, 10, 25, 50, 100, 250, 500, 1000},
	})

	extractionConfidence = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "idep_extraction_confidence",
		Help:    "Extraction confidence scores",
		Buckets: []float64{0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99},
	})
)

// PrometheusMiddleware records HTTP metrics for every request
func PrometheusMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()
		path := c.FullPath()
		if path == "" {
			path = c.Request.URL.Path
		}

		c.Next()

		duration := time.Since(start).Seconds()
		status := strconv.Itoa(c.Writer.Status())

		httpRequestsTotal.WithLabelValues(c.Request.Method, path, status).Inc()
		httpRequestDuration.WithLabelValues(c.Request.Method, path).Observe(duration)
		httpRequestSize.WithLabelValues(c.Request.Method, path).Observe(float64(c.Request.ContentLength))
	}
}

// PrometheusHandler returns the Prometheus metrics endpoint handler
func PrometheusHandler() gin.HandlerFunc {
	h := promhttp.Handler()
	return func(c *gin.Context) {
		h.ServeHTTP(c.Writer, c.Request)
	}
}

// --- Helper functions to record business metrics ---

func RecordJobCreated()                   { jobsTotal.WithLabelValues("created").Inc(); activeJobs.Inc() }
func RecordJobCompleted()                 { jobsTotal.WithLabelValues("completed").Inc(); activeJobs.Dec() }
func RecordJobFailed()                    { jobsTotal.WithLabelValues("failed").Inc(); activeJobs.Dec() }
func RecordPageCount(pages int)           { documentPages.Observe(float64(pages)) }
func RecordConfidence(confidence float64) { extractionConfidence.Observe(confidence) }
