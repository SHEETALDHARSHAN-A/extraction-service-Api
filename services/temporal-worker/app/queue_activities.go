package app

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/redis/go-redis/v9"
	"github.com/user/idep/services/api-gateway/queue"
)

// QueueActivities holds queue-related activities
type QueueActivities struct {
	Queue queue.RequestQueue
}

// NewQueueActivities creates a new QueueActivities instance
func NewQueueActivities(redisClient *redis.Client) *QueueActivities {
	return &QueueActivities{
		Queue: queue.NewRedisQueue(redisClient),
	}
}

// CheckQueueStatus checks if a job is ready for processing
func (qa *QueueActivities) CheckQueueStatus(ctx context.Context, jobID string) (string, error) {
	log.Printf("🔍 [CheckQueueStatus] Checking status for job %s", jobID)

	job, err := qa.Queue.GetStatus(ctx, jobID)
	if err != nil {
		return "", fmt.Errorf("failed to get job status: %w", err)
	}

	log.Printf("✅ [CheckQueueStatus] Job %s status: %s", jobID, job.Status)
	return string(job.Status), nil
}

// AcquireGPULock attempts to acquire exclusive GPU access for a job
func (qa *QueueActivities) AcquireGPULock(ctx context.Context, jobID string) (bool, error) {
	log.Printf("🔒 [AcquireGPULock] Attempting to acquire GPU lock for job %s", jobID)

	// Set TTL to 1 hour (should be more than enough for any job)
	ttl := 1 * time.Hour
	acquired, err := qa.Queue.AcquireGPULock(ctx, jobID, ttl)
	if err != nil {
		return false, fmt.Errorf("failed to acquire GPU lock: %w", err)
	}

	if acquired {
		log.Printf("✅ [AcquireGPULock] GPU lock acquired for job %s", jobID)
	} else {
		log.Printf("⏳ [AcquireGPULock] GPU lock not available for job %s", jobID)
	}

	return acquired, nil
}

// ReleaseGPULock releases the GPU lock for a job
func (qa *QueueActivities) ReleaseGPULock(ctx context.Context, jobID string) error {
	log.Printf("🔓 [ReleaseGPULock] Releasing GPU lock for job %s", jobID)

	err := qa.Queue.ReleaseGPULock(ctx, jobID)
	if err != nil {
		return fmt.Errorf("failed to release GPU lock: %w", err)
	}

	log.Printf("✅ [ReleaseGPULock] GPU lock released for job %s", jobID)
	return nil
}

// StoreFailureDetails stores failure information for a job
func (qa *QueueActivities) StoreFailureDetails(ctx context.Context, jobID string, errorMessage string, retryCount int) error {
	log.Printf("💾 [StoreFailureDetails] Storing failure for job %s (retry %d)", jobID, retryCount)

	// Get current job status
	job, err := qa.Queue.GetStatus(ctx, jobID)
	if err != nil {
		return fmt.Errorf("failed to get job status: %w", err)
	}

	// Update job with error details
	job.ErrorMessage = errorMessage
	job.RetryCount = retryCount
	job.Status = "FAILED"

	// Update in queue
	err = qa.Queue.UpdateStatus(ctx, jobID, "FAILED")
	if err != nil {
		return fmt.Errorf("failed to update job status: %w", err)
	}

	log.Printf("✅ [StoreFailureDetails] Failure details stored for job %s", jobID)
	return nil
}

// StorePartialResults stores partial results when a job times out
func (qa *QueueActivities) StorePartialResults(ctx context.Context, jobID string, partialResults map[string]interface{}, processingMetadata map[string]interface{}) error {
	log.Printf("💾 [StorePartialResults] Storing partial results for job %s", jobID)

	// Get current job status
	job, err := qa.Queue.GetStatus(ctx, jobID)
	if err != nil {
		return fmt.Errorf("failed to get job status: %w", err)
	}

	// Store partial results in job options
	if job.Options == nil {
		job.Options = make(map[string]interface{})
	}
	job.Options["partial_results"] = partialResults
	job.Options["processing_metadata"] = processingMetadata
	job.Options["timeout_occurred"] = true

	// Update error message
	pagesCompleted := 0
	totalPages := 0
	if metadata, ok := processingMetadata["pages_completed"].(int); ok {
		pagesCompleted = metadata
	}
	if metadata, ok := processingMetadata["total_pages"].(int); ok {
		totalPages = metadata
	}
	processingTime := 0
	if metadata, ok := processingMetadata["processing_time_seconds"].(int); ok {
		processingTime = metadata
	}

	job.ErrorMessage = fmt.Sprintf(
		"Processing timeout after %d seconds. Completed %d of %d pages.",
		processingTime, pagesCompleted, totalPages,
	)
	job.Status = "FAILED"

	// Update in queue
	err = qa.Queue.UpdateStatus(ctx, jobID, "FAILED")
	if err != nil {
		return fmt.Errorf("failed to update job status: %w", err)
	}

	log.Printf("✅ [StorePartialResults] Partial results stored for job %s: %d/%d pages completed",
		jobID, pagesCompleted, totalPages)
	return nil
}

