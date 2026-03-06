package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/glebarez/sqlite"
	"github.com/google/uuid"
	"github.com/opentracing/opentracing-go"
	"github.com/redis/go-redis/v9"
	"github.com/user/idep/api-gateway/cache"
	"github.com/user/idep/api-gateway/clients"
	"github.com/user/idep/api-gateway/config"
	"github.com/user/idep/api-gateway/handlers"
	"github.com/user/idep/api-gateway/middleware"
	"github.com/user/idep/api-gateway/models"
	"github.com/user/idep/api-gateway/orchestrator"
	"github.com/user/idep/api-gateway/queue"
	"github.com/user/idep/api-gateway/storage"
	"github.com/user/idep/api-gateway/tracing"
	enumspb "go.temporal.io/api/enums/v1"
	"go.temporal.io/sdk/client"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	grpc_health_v1 "google.golang.org/grpc/health/grpc_health_v1"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

var (
	db              *gorm.DB
	storageClient   storage.StorageClient
	temporalClient  client.Client
	redisCache      *cache.RedisCache
	requestQueue    queue.RequestQueue
	cfg             *config.Config
	paddleOCRClient *clients.PaddleOCRClient
	glmOCRClient    *clients.GLMOCRClient
	docOrchestrator *orchestrator.Orchestrator
	healthService   *HealthService
	documentService *DocumentService
)

func main() {
	cfg = config.Load()

	// --- Initialize Jaeger Tracer ---
	jaegerEndpoint := "localhost:6831" // Default Jaeger agent endpoint
	if endpoint := cfg.JaegerEndpoint; endpoint != "" {
		jaegerEndpoint = endpoint
	}

	tracer, closer, err := tracing.InitJaeger("idep-api-gateway", jaegerEndpoint)
	if err != nil {
		log.Printf("⚠️ Failed to initialize Jaeger tracer (non-fatal): %v", err)
	} else {
		defer closer.Close()
		opentracing.SetGlobalTracer(tracer)
		log.Println("✅ Jaeger tracer initialized and set globally")
	}

	// --- Initialize Database ---
	switch strings.ToLower(cfg.DatabaseDriver) {
	case "sqlite":
		db, err = gorm.Open(sqlite.Open(cfg.DatabaseURL), &gorm.Config{})
	default:
		db, err = gorm.Open(postgres.Open(cfg.DatabaseURL), &gorm.Config{})
	}
	if err != nil {
		log.Fatalf("Failed to connect to database: %v", err)
	}
	if err := db.AutoMigrate(&models.Job{}); err != nil {
		log.Fatalf("Failed to auto-migrate: %v", err)
	}
	log.Printf("✅ Database connected and migrated (driver=%s)", cfg.DatabaseDriver)

	// --- Initialize Storage Backend ---
	switch strings.ToLower(cfg.StorageDriver) {
	case "local":
		storageClient, err = storage.NewLocalStorageClient(cfg.LocalStorageRoot, cfg.MinioBucket)
		if err != nil {
			log.Fatalf("Failed to initialize local storage: %v", err)
		}
		log.Println("✅ Local filesystem storage connected")
	default:
		storageClient, err = storage.NewMinioClient(
			cfg.MinioEndpoint, cfg.MinioAccessKey, cfg.MinioSecretKey,
			cfg.MinioBucket, cfg.MinioUseSSL,
		)
		if err != nil {
			log.Fatalf("Failed to connect to MinIO: %v", err)
		}
		log.Println("✅ MinIO connected")
	}

	// --- Initialize Temporal Client ---
	temporalClient, err = client.Dial(client.Options{
		HostPort:  cfg.TemporalHost,
		Namespace: cfg.TemporalNamespace,
	})
	if err != nil {
		log.Printf("⚠️ Failed to connect to Temporal (non-fatal): %v", err)
		log.Println("   Workflows will not start. Install Temporal CLI and run: temporal server start-dev")
	} else {
		defer temporalClient.Close()
		log.Println("✅ Temporal connected")
	}

	// --- Initialize Redis Cache ---
	redisCache, err = cache.New(cfg.RedisURL)
	if err != nil {
		log.Printf("⚠️ Redis cache unavailable (non-fatal): %v", err)
	}

	// --- Initialize Redis Request Queue ---
	redisOpts, err := redis.ParseURL(cfg.RedisURL)
	if err != nil {
		redisOpts = &redis.Options{Addr: cfg.RedisURL, DB: 0}
	}
	redisClient := redis.NewClient(redisOpts)
	if _, pingErr := redisClient.Ping(context.Background()).Result(); pingErr != nil {
		log.Printf("⚠️ Redis queue and rate limiting unavailable (non-fatal): %v", pingErr)
		middleware.InitRateLimiter(nil) // Use local memory fallback
	} else {
		requestQueue = queue.NewRedisQueue(redisClient)
		middleware.InitRateLimiter(redisClient) // Use Redis for rate limiting
		log.Println("✅ Redis request queue and rate limiter initialized")
	}

	// Start queue metrics emission goroutine only if queue is initialized
	if requestQueue != nil {
		// Start background job to submit queued jobs to Temporal
		go startTemporalSubmitter()

		go func() {
			ticker := time.NewTicker(30 * time.Second) // Emit metrics every 30 seconds
			defer ticker.Stop()

			for range ticker.C {
				metrics, err := requestQueue.UpdateQueueMetrics(context.Background())
				if err != nil {
					log.Printf("⚠️ Failed to update queue metrics: %v", err)
					continue
				}

				// Log queue metrics with structured logging
				log.Printf(`{"timestamp":"%s","level":"INFO","service":"idep-api-gateway","message":"Queue metrics","context":{"queue_length":%d,"processing_count":%d,"avg_wait_time_seconds":%.2f,"avg_processing_time_seconds":%.2f}}`,
					metrics.Timestamp,
					metrics.QueueLength,
					metrics.ProcessingCount,
					metrics.AvgWaitTimeSeconds,
					metrics.AvgProcessingTime,
				)
			}
		}()
	}

	// --- Initialize Service Clients ---
	paddleOCRClient = clients.NewPaddleOCRClient(
		cfg.PaddleOCRServiceURL,
		cfg.ServiceRequestTimeout,
		cfg.ServiceRetryAttempts,
		cfg.CircuitBreakerThreshold,
		cfg.CircuitBreakerTimeout,
	)
	log.Println("✅ PaddleOCR client initialized")

	glmOCRClient = clients.NewGLMOCRClient(
		cfg.GLMOCRServiceURL,
		cfg.ServiceRequestTimeout,
		cfg.ServiceRetryAttempts,
		cfg.CircuitBreakerThreshold,
		cfg.CircuitBreakerTimeout,
	)
	log.Println("✅ GLM-OCR client initialized")

	// --- Initialize Orchestrator ---
	docOrchestrator = orchestrator.NewOrchestrator(
		paddleOCRClient,
		glmOCRClient,
		redisCache,
		&orchestrator.OrchestratorConfig{
			EnableLayoutDetection: cfg.EnableLayoutDetection,
			CacheLayoutResults:    cfg.CacheLayoutResults,
			MaxParallelRegions:    cfg.MaxParallelRegions,
			ParallelProcessing:    true,
		},
	)
	log.Println("✅ Document orchestrator initialized")

	healthService = &HealthService{
		DB:      db,
		Cache:   redisCache,
		Queue:   requestQueue,
		GLMURL:  cfg.GLMOCRServiceURL,
		Service: "idep-api-gateway",
	}

	documentService = &DocumentService{
		DB:          db,
		Storage:     storageClient,
		Cache:       redisCache,
		Queue:       requestQueue,
		Temporal:    temporalClient,
		TaskQueue:   cfg.TemporalTaskQueue,
		UploadLimit: cfg.UploadMaxDocumentSizeBytes,
	}

	// --- Gin Router ---
	r := gin.Default()

	// Global middleware
	r.Use(RequestIDMiddleware())
	r.Use(middleware.TracingMiddleware())
	r.Use(middleware.PrometheusMiddleware())
	r.Use(middleware.RateLimit())

	// Public endpoints
	r.GET("/health", healthCheck)
	r.GET("/metrics", middleware.PrometheusHandler())

	// Authenticated API routes (Bearer API key)
	api := r.Group("/")
	api.Use(middleware.Auth())
	{
		// Document processing
		api.POST("/jobs/upload", uploadDocument)
		api.POST("/jobs/extract", extractDocument)
		api.POST("/jobs/batch", batchHandler().Handle)
		api.GET("/jobs", listJobs)
		api.GET("/jobs/:id", getJobStatus)
		api.GET("/jobs/:id/result", getJobResult)
		api.GET("/jobs/batch/:batch_id", getBatchStatus)

		// Queue management
		api.GET("/queue/status", getQueueStatus)

		// Platform
		api.GET("/admin/stats", getSystemStats)
		api.GET("/admin/cache", getCacheStats)
		api.POST("/admin/reload-keys", reloadKeys)
	}

	log.Printf("🚀 API Gateway starting on :%s", cfg.Port)
	r.Run(":" + cfg.Port)
}

func batchHandler() *handlers.BatchUploadHandler {
	return &handlers.BatchUploadHandler{
		DB:             db,
		MinioStore:     storageClient,
		TemporalClient: temporalClient,
		TaskQueue:      cfg.TemporalTaskQueue,
	}
}

// --- Handlers & Middleware ---

func RequestIDMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		reqID := c.GetHeader("X-Request-ID")
		if reqID == "" {
			reqID = uuid.New().String()
		}
		c.Set("RequestID", reqID)
		c.Header("X-Request-ID", reqID)

		// Also add it to passing context for traced spans/logger context if needed
		ctx := context.WithValue(c.Request.Context(), "request_id", reqID)
		c.Request = c.Request.WithContext(ctx)

		c.Next()
	}
}

func reloadKeys(c *gin.Context) {
	middleware.ReloadAPIKeys()
	c.JSON(http.StatusOK, gin.H{
		"status":  "success",
		"message": "API keys reloaded successfully from environment",
	})
}

func healthCheck(c *gin.Context) {
	healthService.Check(c)
}

// checkServiceHealth performs a simple HTTP GET to a service health endpoint
func checkServiceHealth(url string) gin.H {
	if strings.HasPrefix(strings.ToLower(url), "grpc://") {
		target := strings.TrimPrefix(url, "grpc://")
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()

		conn, err := grpc.NewClient(target, grpc.WithTransportCredentials(insecure.NewCredentials()))
		if err != nil {
			return gin.H{
				"status":            "unhealthy",
				"error":             err.Error(),
				"last_health_check": time.Now().Format(time.RFC3339),
			}
		}
		defer conn.Close()

		healthClient := grpc_health_v1.NewHealthClient(conn)
		healthResp, err := healthClient.Check(ctx, &grpc_health_v1.HealthCheckRequest{})
		if err != nil {
			return gin.H{
				"status":            "unhealthy",
				"transport":         "grpc",
				"error":             err.Error(),
				"last_health_check": time.Now().Format(time.RFC3339),
			}
		}

		if healthResp.GetStatus() != grpc_health_v1.HealthCheckResponse_SERVING {
			return gin.H{
				"status":            "unhealthy",
				"transport":         "grpc",
				"health_status":     healthResp.GetStatus().String(),
				"last_health_check": time.Now().Format(time.RFC3339),
			}
		}

		return gin.H{
			"status":            "healthy",
			"transport":         "grpc",
			"health_status":     healthResp.GetStatus().String(),
			"last_health_check": time.Now().Format(time.RFC3339),
		}
	}

	client := &http.Client{
		Timeout: 5 * time.Second,
	}

	resp, err := client.Get(url)
	if err != nil {
		return gin.H{
			"status":            "unhealthy",
			"error":             err.Error(),
			"last_health_check": time.Now().Format(time.RFC3339),
		}
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return gin.H{
			"status":            "unhealthy",
			"response_code":     resp.StatusCode,
			"last_health_check": time.Now().Format(time.RFC3339),
		}
	}

	return gin.H{
		"status":            "healthy",
		"response_time_ms":  0, // Could measure this if needed
		"last_health_check": time.Now().Format(time.RFC3339),
	}
}

func uploadDocument(c *gin.Context) {
	documentService.Upload(c)
}

func extractDocument(c *gin.Context) {
	documentService.Extract(c)
}

func getJobStatus(c *gin.Context) {
	jobID := c.Param("id")
	var job models.Job
	if err := db.First(&job, "id = ?", jobID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Job not found"})
		return
	}
	syncJobWithWorkflowStatus(c.Request.Context(), &job)
	c.JSON(http.StatusOK, job)
}

func getJobResult(c *gin.Context) {
	jobID := c.Param("id")
	var job models.Job
	if err := db.First(&job, "id = ?", jobID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Job not found"})
		return
	}
	syncJobWithWorkflowStatus(c.Request.Context(), &job)
	if job.Status != models.StatusCompleted {
		c.JSON(http.StatusConflict, gin.H{"error": "Job not yet completed", "status": job.Status})
		return
	}
	if job.ResultPath == "" {
		c.JSON(http.StatusNotFound, gin.H{"error": "No result available"})
		return
	}

	reader, err := storageClient.DownloadFile(context.Background(), job.ResultPath)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to retrieve result"})
		return
	}
	defer reader.Close()

	c.Header("Content-Disposition", fmt.Sprintf(`attachment; filename="%s_result.json"`, job.Filename))
	c.Header("Content-Type", "application/json")
	c.DataFromReader(http.StatusOK, -1, "application/json", reader, nil)
}

func syncJobWithWorkflowStatus(ctx context.Context, job *models.Job) {
	if temporalClient == nil || job.WorkflowID == "" {
		return
	}

	desc, err := temporalClient.DescribeWorkflowExecution(ctx, job.WorkflowID, job.RunID)
	if err != nil || desc == nil || desc.WorkflowExecutionInfo == nil {
		return
	}

	status := desc.WorkflowExecutionInfo.GetStatus()
	if status == enumspb.WORKFLOW_EXECUTION_STATUS_COMPLETED {
		if job.Status == models.StatusCompleted && job.ResultPath != "" {
			return
		}

		wfRun := temporalClient.GetWorkflow(ctx, job.WorkflowID, job.RunID)
		var workflowResult map[string]interface{}
		if err := wfRun.Get(ctx, &workflowResult); err != nil {
			return
		}

		updates := map[string]interface{}{
			"status": models.StatusCompleted,
		}

		if resultPath, ok := workflowResult["result_path"].(string); ok {
			updates["result_path"] = resultPath
			job.ResultPath = resultPath
		}
		if confidence, ok := workflowResult["confidence"].(float64); ok {
			updates["confidence"] = confidence
			job.Confidence = confidence
		}
		if pageCount, ok := workflowResult["page_count"].(float64); ok {
			updates["page_count"] = int(pageCount)
			job.PageCount = int(pageCount)
		}

		db.Model(job).Updates(updates)
		job.Status = models.StatusCompleted
		job.ErrorMessage = ""
		return
	}

	if status == enumspb.WORKFLOW_EXECUTION_STATUS_FAILED ||
		status == enumspb.WORKFLOW_EXECUTION_STATUS_CANCELED ||
		status == enumspb.WORKFLOW_EXECUTION_STATUS_TERMINATED ||
		status == enumspb.WORKFLOW_EXECUTION_STATUS_TIMED_OUT {
		if job.Status != models.StatusFailed {
			db.Model(job).Updates(map[string]interface{}{
				"status":        models.StatusFailed,
				"error_message": fmt.Sprintf("Workflow ended with status: %s", status.String()),
			})
			job.Status = models.StatusFailed
			job.ErrorMessage = fmt.Sprintf("Workflow ended with status: %s", status.String())
		}
	}
}

func listJobs(c *gin.Context) {
	var jobs []models.Job

	// Default pagination
	limit := 50
	offset := 0

	// Parse query params
	if limitParam := c.Query("limit"); limitParam != "" {
		if parsedLimit, err := strconv.Atoi(limitParam); err == nil && parsedLimit > 0 {
			if parsedLimit > 100 {
				limit = 100 // Cap at 100
			} else {
				limit = parsedLimit
			}
		}
	}

	if offsetParam := c.Query("offset"); offsetParam != "" {
		if parsedOffset, err := strconv.Atoi(offsetParam); err == nil && parsedOffset >= 0 {
			offset = parsedOffset
		}
	}

	// Get total count
	var totalCount int64
	db.Model(&models.Job{}).Count(&totalCount)

	result := db.Order("created_at desc").Limit(limit).Offset(offset).Find(&jobs)
	if result.Error != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to list jobs"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"jobs":   jobs,
		"count":  len(jobs),
		"total":  totalCount,
		"limit":  limit,
		"offset": offset,
	})
}

func getBatchStatus(c *gin.Context) {
	batchID := c.Param("batch_id")
	statusFilter := c.Query("status") // Optional: ?status=COMPLETED or ?status=FAILED

	var jobs []models.Job
	query := db.Where("batch_id = ?", batchID).Order("created_at asc")
	if statusFilter != "" {
		query = query.Where("status = ?", statusFilter)
	}
	query.Find(&jobs)

	if len(jobs) == 0 {
		c.JSON(http.StatusNotFound, gin.H{
			"error": map[string]interface{}{
				"message": "Batch not found",
				"type":    "invalid_request_error",
				"code":    "batch_not_found",
			},
		})
		return
	}

	// Count by status (always from full batch, not filtered)
	var allJobs []models.Job
	if statusFilter != "" {
		db.Where("batch_id = ?", batchID).Find(&allJobs)
	} else {
		allJobs = jobs
	}

	completed, failed, processing, uploaded := 0, 0, 0, 0
	for _, j := range allJobs {
		switch j.Status {
		case models.StatusCompleted:
			completed++
		case models.StatusFailed:
			failed++
		case models.StatusProcessing:
			processing++
		default:
			uploaded++
		}
	}
	total := len(allJobs)
	finished := completed + failed
	progress := 0.0
	if total > 0 {
		progress = float64(finished) / float64(total) * 100
	}

	// Determine overall batch status
	batchStatus := "PROCESSING"
	if finished == total {
		if failed == 0 {
			batchStatus = "COMPLETED"
		} else if completed == 0 {
			batchStatus = "FAILED"
		} else {
			batchStatus = "COMPLETED_WITH_ERRORS"
		}
	}

	// Build per-file detail
	type fileStatus struct {
		JobID      string  `json:"job_id"`
		Filename   string  `json:"filename"`
		Status     string  `json:"status"`
		Confidence float64 `json:"confidence,omitempty"`
		PageCount  int     `json:"page_count,omitempty"`
		Error      string  `json:"error,omitempty"`
		ResultURL  string  `json:"result_url,omitempty"`
		CreatedAt  string  `json:"created_at"`
		UpdatedAt  string  `json:"updated_at"`
	}

	fileStatuses := make([]fileStatus, len(jobs))
	for i, j := range jobs {
		fs := fileStatus{
			JobID:     j.ID,
			Filename:  j.Filename,
			Status:    string(j.Status),
			CreatedAt: j.CreatedAt.Format("2006-01-02T15:04:05Z"),
			UpdatedAt: j.UpdatedAt.Format("2006-01-02T15:04:05Z"),
		}
		if j.Status == models.StatusCompleted {
			fs.Confidence = j.Confidence
			fs.PageCount = j.PageCount
			fs.ResultURL = fmt.Sprintf("/jobs/%s/result", j.ID)
		}
		if j.Status == models.StatusFailed {
			fs.Error = j.ErrorMessage
		}
		fileStatuses[i] = fs
	}

	c.JSON(http.StatusOK, gin.H{
		"batch_id":   batchID,
		"status":     batchStatus,
		"progress":   fmt.Sprintf("%.1f%%", progress),
		"total":      total,
		"completed":  completed,
		"failed":     failed,
		"processing": processing,
		"uploaded":   uploaded,
		"files":      fileStatuses,
	})
}

func getSystemStats(c *gin.Context) {
	var totalJobs, processingJobs, completedJobs, failedJobs int64
	db.Model(&models.Job{}).Count(&totalJobs)
	db.Model(&models.Job{}).Where("status = ?", models.StatusProcessing).Count(&processingJobs)
	db.Model(&models.Job{}).Where("status = ?", models.StatusCompleted).Count(&completedJobs)
	db.Model(&models.Job{}).Where("status = ?", models.StatusFailed).Count(&failedJobs)

	c.JSON(http.StatusOK, gin.H{
		"total_jobs":      totalJobs,
		"processing_jobs": processingJobs,
		"completed_jobs":  completedJobs,
		"failed_jobs":     failedJobs,
	})
}

func getCacheStats(c *gin.Context) {
	if redisCache == nil {
		c.JSON(http.StatusOK, gin.H{"status": "cache_unavailable"})
		return
	}
	stats := redisCache.GetCacheStats(context.Background())
	c.JSON(http.StatusOK, gin.H{
		"status": "connected",
		"stats":  stats,
	})
}

func getQueueStatus(c *gin.Context) {
	if requestQueue == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{
			"error": "Queue service unavailable",
		})
		return
	}

	queueLength, err := requestQueue.GetQueueLength(c.Request.Context())
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": "Failed to get queue length",
		})
		return
	}

	estimatedWait, err := requestQueue.GetEstimatedWaitTime(c.Request.Context())
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": "Failed to get estimated wait time",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"queue_length":                queueLength,
		"estimated_wait_time_seconds": int(estimatedWait.Seconds()),
	})
}

// startTemporalSubmitter runs in the background to retry submitting jobs
// to Temporal if they failed to submit previously.
func startTemporalSubmitter() {
	if requestQueue == nil {
		return
	}

	ticker := time.NewTicker(10 * time.Second)
	defer ticker.Stop()

	for range ticker.C {
		if temporalClient == nil {
			continue // Still no temporal, skip this tick
		}

		// Limit the number of retries per tick to avoid flooding Temporal when it comes back
		for i := 0; i < 10; i++ {
			// Try to get a job
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			queuedJob, err := requestQueue.Dequeue(ctx)
			cancel()

			if err != nil {
				log.Printf("⚠️ Background submitter failed to dequeue: %v", err)
				break
			}

			if queuedJob == nil {
				break // Queue is empty
			}

			// We have a job! Submit it to Temporal
			log.Printf("🔄 Background submitter retrying job %s", queuedJob.JobID)

			var job models.Job
			if err := db.First(&job, "id = ?", queuedJob.JobID).Error; err != nil {
				log.Printf("⚠️ Unknown job %s dequeued", queuedJob.JobID)
				requestQueue.UpdateStatus(context.Background(), queuedJob.JobID, queue.StatusFailed)
				continue
			}

			workflowOptions := client.StartWorkflowOptions{
				ID:        fmt.Sprintf("doc-processing-%s", job.ID),
				TaskQueue: cfg.TemporalTaskQueue,
			}

			workflowInput := map[string]interface{}{
				"job_id":         job.ID,
				"filename":       job.Filename,
				"storage_path":   job.StoragePath,
				"content_type":   job.ContentType,
				"output_formats": job.OutputFormats,
				"options":        queuedJob.Options,
			}

			we, err := temporalClient.ExecuteWorkflow(context.Background(), workflowOptions, "DocumentProcessingWorkflow", workflowInput)
			if err != nil {
				log.Printf("⚠️ Background submitter failed again for job %s: %v", job.ID, err)
				queuedJob.RetryCount++
				if queuedJob.RetryCount > 5 {
					log.Printf("❌ Job %s exceeded retries. Marking failed.", job.ID)
					requestQueue.UpdateStatus(context.Background(), queuedJob.JobID, queue.StatusFailed)
					db.Model(&job).Updates(map[string]interface{}{
						"status":        models.StatusFailed,
						"error_message": "Exceeded retries when submitting to processing workflow",
					})
				} else {
					log.Printf("🔄 Requeuing job %s (attempt %d)", job.ID, queuedJob.RetryCount)
					requestQueue.CancelJob(context.Background(), queuedJob.JobID)
					requestQueue.Enqueue(context.Background(), queuedJob)
				}
				continue
			}

			// Success!
			log.Printf("✅ Background submitter successfully started workflow %s for job %s", we.GetID(), job.ID)
			db.Model(&job).Updates(map[string]interface{}{
				"workflow_id": we.GetID(),
				"run_id":      we.GetRunID(),
				"status":      models.StatusProcessing,
			})
		}
	}
}
