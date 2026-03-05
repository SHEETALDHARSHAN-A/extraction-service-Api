package queue

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

// JobStatus represents the current status of a job
type JobStatus string

const (
	StatusQueued     JobStatus = "QUEUED"
	StatusProcessing JobStatus = "PROCESSING"
	StatusCompleted  JobStatus = "COMPLETED"
	StatusFailed     JobStatus = "FAILED"
)

// QueuedJob represents a job in the request queue
type QueuedJob struct {
	JobID        string                 `json:"job_id"`
	Priority     int                    `json:"priority"` // 0=normal, 1=high, 2=urgent
	EnqueuedAt   time.Time              `json:"enqueued_at"`
	StartedAt    *time.Time             `json:"started_at,omitempty"`
	CompletedAt  *time.Time             `json:"completed_at,omitempty"`
	DocumentSize int64                  `json:"document_size"`
	Status       JobStatus              `json:"status"`
	Options      map[string]interface{} `json:"options"`
	RetryCount   int                    `json:"retry_count"`
	ErrorMessage string                 `json:"error_message,omitempty"`
}

// RequestQueue defines the interface for managing extraction request queue
type RequestQueue interface {
	// Enqueue adds a job to the queue with priority
	Enqueue(ctx context.Context, job *QueuedJob) error

	// Dequeue retrieves the next job from the queue
	Dequeue(ctx context.Context) (*QueuedJob, error)

	// UpdateStatus updates job status in the queue
	UpdateStatus(ctx context.Context, jobID string, status JobStatus) error

	// GetStatus retrieves current job status
	GetStatus(ctx context.Context, jobID string) (*QueuedJob, error)

	// AcquireGPULock attempts to acquire exclusive GPU access
	AcquireGPULock(ctx context.Context, jobID string, ttl time.Duration) (bool, error)

	// ReleaseGPULock releases GPU lock
	ReleaseGPULock(ctx context.Context, jobID string) error

	// GetQueueLength returns current queue length
	GetQueueLength(ctx context.Context) (int64, error)

	// GetEstimatedWaitTime estimates wait time based on queue length
	GetEstimatedWaitTime(ctx context.Context) (time.Duration, error)

	// CancelJob removes a job from the queue
	CancelJob(ctx context.Context, jobID string) error

	// UpdateQueueMetrics updates Prometheus metrics for the queue
	UpdateQueueMetrics(ctx context.Context) (*QueueMetrics, error)
}

// RedisQueue implements RequestQueue using Redis
type RedisQueue struct {
	client            *redis.Client
	queueKey          string
	processingKey     string
	statusKeyPrefix   string
	gpuLockKey        string
	metricsKey        string
	avgProcessingTime time.Duration
	maxQueueLength    int64
}

// NewRedisQueue creates a new Redis-based request queue
func NewRedisQueue(client *redis.Client) *RedisQueue {
	return &RedisQueue{
		client:            client,
		queueKey:          "queue:pending",
		processingKey:     "queue:processing",
		statusKeyPrefix:   "queue:status:",
		gpuLockKey:        "lock:gpu",
		metricsKey:        "metrics:queue",
		avgProcessingTime: 30 * time.Second, // Default estimate
		maxQueueLength:    50,               // Maximum queue capacity
	}
}

// Enqueue adds a job to the priority queue
func (q *RedisQueue) Enqueue(ctx context.Context, job *QueuedJob) error {
	// Check queue capacity
	length, err := q.GetQueueLength(ctx)
	if err != nil {
		return fmt.Errorf("failed to check queue length: %w", err)
	}

	if length >= q.maxQueueLength {
		return fmt.Errorf("queue is full (max %d jobs)", q.maxQueueLength)
	}

	// Set initial status
	job.Status = StatusQueued
	job.EnqueuedAt = time.Now()

	// Calculate priority score (higher priority = lower score for ZADD)
	// Score = priority * 1000000 + timestamp (to maintain FIFO within same priority)
	score := float64(job.Priority)*1000000 + float64(job.EnqueuedAt.Unix())

	// Add to sorted set (priority queue)
	err = q.client.ZAdd(ctx, q.queueKey, redis.Z{
		Score:  score,
		Member: job.JobID,
	}).Err()
	if err != nil {
		return fmt.Errorf("failed to enqueue job: %w", err)
	}

	// Store job metadata
	jobData, err := json.Marshal(job)
	if err != nil {
		return fmt.Errorf("failed to marshal job: %w", err)
	}

	err = q.client.HSet(ctx, q.statusKeyPrefix+job.JobID, map[string]interface{}{
		"data":        string(jobData),
		"status":      string(job.Status),
		"enqueued_at": job.EnqueuedAt.Unix(),
	}).Err()
	if err != nil {
		return fmt.Errorf("failed to store job metadata: %w", err)
	}

	// Set TTL for job metadata (24 hours)
	q.client.Expire(ctx, q.statusKeyPrefix+job.JobID, 24*time.Hour)

	// Increment queue metrics
	q.client.HIncrBy(ctx, q.metricsKey, "total_enqueued", 1)

	return nil
}

// Dequeue retrieves the next job from the queue (highest priority, oldest first)
func (q *RedisQueue) Dequeue(ctx context.Context) (*QueuedJob, error) {
	// Get job with lowest score (highest priority, oldest)
	result, err := q.client.ZPopMin(ctx, q.queueKey, 1).Result()
	if err != nil {
		return nil, fmt.Errorf("failed to dequeue job: %w", err)
	}

	if len(result) == 0 {
		return nil, nil // Queue is empty
	}

	jobID := result[0].Member.(string)

	// Get job metadata
	job, err := q.GetStatus(ctx, jobID)
	if err != nil {
		return nil, fmt.Errorf("failed to get job metadata: %w", err)
	}

	// Update status to processing
	now := time.Now()
	job.Status = StatusProcessing
	job.StartedAt = &now

	// Move to processing set
	q.client.HSet(ctx, q.processingKey, jobID, now.Unix())

	// Update job metadata
	err = q.UpdateStatus(ctx, jobID, StatusProcessing)
	if err != nil {
		return nil, fmt.Errorf("failed to update job status: %w", err)
	}

	return job, nil
}

// UpdateStatus updates the status of a job
func (q *RedisQueue) UpdateStatus(ctx context.Context, jobID string, status JobStatus) error {
	// Get current job data
	job, err := q.GetStatus(ctx, jobID)
	if err != nil {
		return fmt.Errorf("failed to get current job status: %w", err)
	}

	// Update status
	job.Status = status

	// Any non-queued status must not remain in pending sorted-set,
	// otherwise queue length drifts and can saturate capacity.
	if status != StatusQueued {
		q.client.ZRem(ctx, q.queueKey, jobID)
	}

	// Mark processing metadata when transitioning to PROCESSING.
	if status == StatusProcessing {
		now := time.Now()
		if job.StartedAt == nil {
			job.StartedAt = &now
		}
		q.client.HSet(ctx, q.processingKey, jobID, now.Unix())
	}

	// Set completion time if completed or failed
	if status == StatusCompleted || status == StatusFailed {
		now := time.Now()
		job.CompletedAt = &now

		// Remove from processing set
		q.client.HDel(ctx, q.processingKey, jobID)

		// Update metrics
		if job.StartedAt != nil {
			processingTime := now.Sub(*job.StartedAt)
			q.client.HIncrBy(ctx, q.metricsKey, "total_completed", 1)
			q.client.HIncrBy(ctx, q.metricsKey, "total_processing_time_ms", processingTime.Milliseconds())
		}
	}

	// Marshal updated job
	jobData, err := json.Marshal(job)
	if err != nil {
		return fmt.Errorf("failed to marshal job: %w", err)
	}

	// Update in Redis
	err = q.client.HSet(ctx, q.statusKeyPrefix+jobID, map[string]interface{}{
		"data":   string(jobData),
		"status": string(status),
	}).Err()
	if err != nil {
		return fmt.Errorf("failed to update job status: %w", err)
	}

	return nil
}

// GetStatus retrieves the current status of a job
func (q *RedisQueue) GetStatus(ctx context.Context, jobID string) (*QueuedJob, error) {
	data, err := q.client.HGet(ctx, q.statusKeyPrefix+jobID, "data").Result()
	if err == redis.Nil {
		return nil, fmt.Errorf("job not found: %s", jobID)
	}
	if err != nil {
		return nil, fmt.Errorf("failed to get job status: %w", err)
	}

	var job QueuedJob
	err = json.Unmarshal([]byte(data), &job)
	if err != nil {
		return nil, fmt.Errorf("failed to unmarshal job: %w", err)
	}

	// Check if job is in queue and get position
	rank, err := q.client.ZRank(ctx, q.queueKey, jobID).Result()
	if err == nil {
		// Job is still in queue, calculate position
		job.Status = StatusQueued
	}
	_ = rank // Position can be used for estimated wait time

	return &job, nil
}

// AcquireGPULock attempts to acquire exclusive GPU access
func (q *RedisQueue) AcquireGPULock(ctx context.Context, jobID string, ttl time.Duration) (bool, error) {
	// Try to set lock with NX (only if not exists)
	success, err := q.client.SetNX(ctx, q.gpuLockKey, jobID, ttl).Result()
	if err != nil {
		return false, fmt.Errorf("failed to acquire GPU lock: %w", err)
	}

	return success, nil
}

// ReleaseGPULock releases the GPU lock
func (q *RedisQueue) ReleaseGPULock(ctx context.Context, jobID string) error {
	// Only delete if the lock is held by this job
	script := `
		if redis.call("get", KEYS[1]) == ARGV[1] then
			return redis.call("del", KEYS[1])
		else
			return 0
		end
	`

	err := q.client.Eval(ctx, script, []string{q.gpuLockKey}, jobID).Err()
	if err != nil {
		return fmt.Errorf("failed to release GPU lock: %w", err)
	}

	return nil
}

// GetQueueLength returns the current number of jobs in the queue
func (q *RedisQueue) GetQueueLength(ctx context.Context) (int64, error) {
	length, err := q.client.ZCard(ctx, q.queueKey).Result()
	if err != nil {
		return 0, fmt.Errorf("failed to get queue length: %w", err)
	}

	return length, nil
}

// GetEstimatedWaitTime estimates wait time based on queue length and average processing time
func (q *RedisQueue) GetEstimatedWaitTime(ctx context.Context) (time.Duration, error) {
	length, err := q.GetQueueLength(ctx)
	if err != nil {
		return 0, err
	}

	// Get average processing time from metrics
	totalCompleted, err := q.client.HGet(ctx, q.metricsKey, "total_completed").Int64()
	if err == nil && totalCompleted > 0 {
		totalTime, _ := q.client.HGet(ctx, q.metricsKey, "total_processing_time_ms").Int64()
		if totalTime > 0 {
			q.avgProcessingTime = time.Duration(totalTime/totalCompleted) * time.Millisecond
		}
	}

	// Estimate: queue_length * avg_processing_time
	estimatedWait := time.Duration(length) * q.avgProcessingTime

	return estimatedWait, nil
}

// CancelJob removes a job from the queue
func (q *RedisQueue) CancelJob(ctx context.Context, jobID string) error {
	// Remove from queue
	err := q.client.ZRem(ctx, q.queueKey, jobID).Err()
	if err != nil {
		return fmt.Errorf("failed to remove job from queue: %w", err)
	}

	// Ensure job is not left in processing set
	q.client.HDel(ctx, q.processingKey, jobID)

	// Update status to failed
	err = q.UpdateStatus(ctx, jobID, StatusFailed)
	if err != nil {
		return fmt.Errorf("failed to update job status: %w", err)
	}

	return nil
}
