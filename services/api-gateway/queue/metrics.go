package queue

import (
	"context"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	// Queue length gauge
	queueLengthGauge = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "queue_length",
		Help: "Current number of jobs in the queue",
	})

	// Average wait time gauge
	avgWaitTimeGauge = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "queue_avg_wait_time_seconds",
		Help: "Average wait time for jobs in the queue",
	})

	// Throughput gauge (jobs per hour)
	throughputGauge = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "queue_throughput_per_hour",
		Help: "Number of jobs processed per hour",
	})

	// Processing count gauge
	processingCountGauge = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "queue_processing_count",
		Help: "Number of jobs currently being processed",
	})

	// Total enqueued counter
	totalEnqueuedCounter = promauto.NewCounter(prometheus.CounterOpts{
		Name: "queue_total_enqueued",
		Help: "Total number of jobs enqueued",
	})

	// Total completed counter
	totalCompletedCounter = promauto.NewCounter(prometheus.CounterOpts{
		Name: "queue_total_completed",
		Help: "Total number of jobs completed",
	})

	// Average processing time gauge
	avgProcessingTimeGauge = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "queue_avg_processing_time_seconds",
		Help: "Average processing time for jobs",
	})
)

// QueueMetrics holds queue metrics data
type QueueMetrics struct {
	QueueLength        int64   `json:"queue_length"`
	ProcessingCount    int64   `json:"processing_count"`
	AvgWaitTimeSeconds float64 `json:"avg_wait_time_seconds"`
	AvgProcessingTime  float64 `json:"avg_processing_time_seconds"`
	ThroughputPerHour  float64 `json:"throughput_per_hour"`
	Timestamp          string  `json:"timestamp"`
}

// UpdateQueueMetrics updates Prometheus metrics for the queue
func (q *RedisQueue) UpdateQueueMetrics(ctx context.Context) (*QueueMetrics, error) {
	// Get queue length
	queueLength, err := q.GetQueueLength(ctx)
	if err != nil {
		return nil, err
	}
	queueLengthGauge.Set(float64(queueLength))

	// Get processing count
	processingCount, err := q.client.HLen(ctx, q.processingKey).Result()
	if err != nil {
		processingCount = 0
	}
	processingCountGauge.Set(float64(processingCount))

	// Get average wait time
	estimatedWait, err := q.GetEstimatedWaitTime(ctx)
	if err != nil {
		estimatedWait = 0
	}
	avgWaitTimeSeconds := estimatedWait.Seconds()
	avgWaitTimeGauge.Set(avgWaitTimeSeconds)

	// Get total completed and processing time
	totalCompleted, err := q.client.HGet(ctx, q.metricsKey, "total_completed").Int64()
	if err != nil {
		totalCompleted = 0
	}
	totalCompletedCounter.Add(0) // Initialize if not set

	totalProcessingTimeMs, err := q.client.HGet(ctx, q.metricsKey, "total_processing_time_ms").Int64()
	if err != nil {
		totalProcessingTimeMs = 0
	}

	// Calculate average processing time
	avgProcessingTimeSeconds := 0.0
	if totalCompleted > 0 && totalProcessingTimeMs > 0 {
		avgProcessingTimeSeconds = float64(totalProcessingTimeMs) / float64(totalCompleted) / 1000.0
		avgProcessingTimeGauge.Set(avgProcessingTimeSeconds)
	}

	// Calculate throughput (jobs per hour)
	// Use a sliding window approach: completed jobs in last hour
	throughputPerHour := 0.0
	if avgProcessingTimeSeconds > 0 {
		// Estimate: 3600 seconds / avg_processing_time
		throughputPerHour = 3600.0 / avgProcessingTimeSeconds
	}
	throughputGauge.Set(throughputPerHour)

	// Get total enqueued
	totalEnqueued, err := q.client.HGet(ctx, q.metricsKey, "total_enqueued").Int64()
	if err != nil {
		totalEnqueued = 0
	}
	_ = totalEnqueued
	totalEnqueuedCounter.Add(0) // Initialize if not set

	return &QueueMetrics{
		QueueLength:        queueLength,
		ProcessingCount:    processingCount,
		AvgWaitTimeSeconds: avgWaitTimeSeconds,
		AvgProcessingTime:  avgProcessingTimeSeconds,
		ThroughputPerHour:  throughputPerHour,
		Timestamp:          time.Now().UTC().Format(time.RFC3339),
	}, nil
}
