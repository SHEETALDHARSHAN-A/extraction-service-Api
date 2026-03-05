package main

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"log"
	"net/http"
	"path/filepath"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
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
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

var (
	db              *gorm.DB
	minioStore      *storage.MinioClient
	temporalClient  client.Client
	redisCache      *cache.RedisCache
	requestQueue    queue.RequestQueue
	cfg             *config.Config
	paddleOCRClient *clients.PaddleOCRClient
	glmOCRClient    *clients.GLMOCRClient
	docOrchestrator *orchestrator.Orchestrator
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
		log.Println("✅ Jaeger tracer initialized")
	}
	_ = tracer // Tracer is set globally

	// --- Initialize PostgreSQL ---
	db, err = gorm.Open(postgres.Open(cfg.DatabaseURL), &gorm.Config{})
	if err != nil {
		log.Fatalf("Failed to connect to database: %v", err)
	}
	if err := db.AutoMigrate(&models.Job{}); err != nil {
		log.Fatalf("Failed to auto-migrate: %v", err)
	}
	log.Println("✅ PostgreSQL connected and migrated")

	// --- Initialize MinIO ---
	minioStore, err = storage.NewMinioClient(
		cfg.MinioEndpoint, cfg.MinioAccessKey, cfg.MinioSecretKey,
		cfg.MinioBucket, cfg.MinioUseSSL,
	)
	if err != nil {
		log.Fatalf("Failed to connect to MinIO: %v", err)
	}
	log.Println("✅ MinIO connected")

	// --- Initialize Temporal Client ---
	temporalClient, err = client.Dial(client.Options{
		HostPort:  cfg.TemporalHost,
		Namespace: cfg.TemporalNamespace,
	})
	if err != nil {
		log.Fatalf("Failed to connect to Temporal: %v", err)
	}
	defer temporalClient.Close()
	log.Println("✅ Temporal connected")

	// --- Initialize Redis Cache ---
	redisCache, err = cache.New(cfg.RedisURL)
	if err != nil {
		log.Printf("⚠️ Redis cache unavailable (non-fatal): %v", err)
	}

	// --- Initialize Redis Request Queue ---
	redisClient := redis.NewClient(&redis.Options{
		Addr: cfg.RedisURL,
	})
	requestQueue = queue.NewRedisQueue(redisClient)
	log.Println("✅ Redis request queue initialized")

	// Start queue metrics emission goroutine
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
			log.Printf(`{"timestamp":"%s","level":"INFO","service":"idep-api-gateway","message":"Queue metrics","context":{"queue_length":%d,"processing_count":%d,"avg_wait_time_seconds":%.2f,"avg_processing_time_seconds":%.2f,"throughput_per_hour":%.2f}}`,
				metrics.Timestamp,
				metrics.QueueLength,
				metrics.ProcessingCount,
				metrics.AvgWaitTimeSeconds,
				metrics.AvgProcessingTime,
				metrics.ThroughputPerHour,
			)
		}
	}()

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

	// --- Gin Router ---
	r := gin.Default()

	// Global middleware
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
	}

	log.Printf("🚀 API Gateway starting on :%s", cfg.Port)
	r.Run(":" + cfg.Port)
}

func batchHandler() *handlers.BatchUploadHandler {
	return &handlers.BatchUploadHandler{
		DB:             db,
		MinioStore:     minioStore,
		TemporalClient: temporalClient,
		TaskQueue:      cfg.TemporalTaskQueue,
	}
}

// --- Handlers ---

func healthCheck(c *gin.Context) {
	ctx := c.Request.Context()
	components := make(map[string]interface{})
	overallStatus := "healthy"

	// Check Triton (via GLM-OCR service health endpoint)
	tritonStatus := checkServiceHealth(cfg.GLMOCRServiceURL + "/health")
	components["triton"] = tritonStatus
	if status, ok := tritonStatus["status"].(string); !ok || status != "healthy" {
		overallStatus = "degraded"
	}

	// Check GLM-OCR service
	glmOCRStatus := checkServiceHealth(cfg.GLMOCRServiceURL + "/health")
	components["glm_ocr_service"] = glmOCRStatus
	if status, ok := glmOCRStatus["status"].(string); !ok || status != "healthy" {
		overallStatus = "degraded"
	}

	// Check Redis queue
	if requestQueue != nil {
		queueLength, err := requestQueue.GetQueueLength(ctx)
		estimatedWait, _ := requestQueue.GetEstimatedWaitTime(ctx)

		queueStatus := gin.H{
			"status": "healthy",
		}

		if err != nil {
			queueStatus["status"] = "unhealthy"
			queueStatus["error"] = err.Error()
			overallStatus = "degraded"
		} else {
			queueStatus["queue_length"] = queueLength
			queueStatus["estimated_wait_time_seconds"] = int(estimatedWait.Seconds())
		}

		components["request_queue"] = queueStatus
	} else {
		components["request_queue"] = gin.H{
			"status": "unavailable",
		}
		overallStatus = "degraded"
	}

	// Check database
	sqlDB, err := db.DB()
	dbStatus := gin.H{
		"status": "healthy",
	}
	if err != nil || sqlDB.Ping() != nil {
		dbStatus["status"] = "unhealthy"
		if err != nil {
			dbStatus["error"] = err.Error()
		}
		overallStatus = "unhealthy"
	} else {
		stats := sqlDB.Stats()
		dbStatus["connection_pool_available"] = stats.MaxOpenConnections - stats.InUse
	}
	components["database"] = dbStatus

	// Check Redis cache
	if redisCache != nil {
		redisStatus := gin.H{
			"status": "healthy",
		}
		// Try a simple ping
		stats := redisCache.GetCacheStats(ctx)
		if stats == nil {
			redisStatus["status"] = "unhealthy"
			overallStatus = "degraded"
		}
		components["redis"] = redisStatus
	} else {
		components["redis"] = gin.H{
			"status": "unavailable",
		}
	}

	statusCode := http.StatusOK
	if overallStatus == "unhealthy" {
		statusCode = http.StatusServiceUnavailable
	} else if overallStatus == "degraded" {
		statusCode = http.StatusOK // Still return 200 for degraded
	}

	c.JSON(statusCode, gin.H{
		"status":     overallStatus,
		"timestamp":  time.Now().Format(time.RFC3339),
		"service":    "idep-api-gateway",
		"components": components,
	})
}

// checkServiceHealth performs a simple HTTP GET to a service health endpoint
func checkServiceHealth(url string) gin.H {
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
	file, header, err := c.Request.FormFile("document")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "No document provided"})
		return
	}
	defer file.Close()

	// Document size validation - max 10MB
	const maxDocumentSize = 10 * 1024 * 1024 // 10MB in bytes
	if header.Size > maxDocumentSize {
		maxSizeMB := float64(maxDocumentSize) / (1024 * 1024)
		providedSizeMB := float64(header.Size) / (1024 * 1024)

		log.Printf("❌ Document too large: %s (%.2fMB) exceeds maximum of %.2fMB",
			header.Filename, providedSizeMB, maxSizeMB)

		c.JSON(http.StatusRequestEntityTooLarge, gin.H{
			"error":            "Document too large",
			"max_size_mb":      maxSizeMB,
			"provided_size_mb": providedSizeMB,
			"message":          fmt.Sprintf("Document size (%.2fMB) exceeds maximum allowed size of %.2fMB", providedSizeMB, maxSizeMB),
		})
		return
	}

	// --- Cache Dedup: Hash content to detect duplicates ---
	var buf bytes.Buffer
	tee := io.TeeReader(file, &buf) // Read into buf while hashing
	contentHash, _ := cache.HashContent(tee)

	if redisCache != nil && contentHash != "" {
		if existingJobID, found := redisCache.CheckDuplicate(context.Background(), contentHash); found {
			var existingJob models.Job
			if db.First(&existingJob, "id = ?", existingJobID).Error == nil {
				// Only return cached result for COMPLETED or PROCESSING jobs.
				// If the previous job FAILED, evict the cache entry and allow
				// the document to be re-submitted for processing.
				if existingJob.Status == models.StatusFailed {
					log.Printf("♻️ Cache hit for FAILED job %s – evicting, will reprocess %s",
						existingJobID, header.Filename)
					redisCache.Evict(context.Background(), contentHash)
				} else {
					log.Printf("♻️ Cache hit: %s → existing job %s (status=%s)",
						header.Filename, existingJobID, existingJob.Status)
					c.JSON(http.StatusOK, gin.H{
						"job_id":   existingJobID,
						"filename": header.Filename,
						"status":   existingJob.Status,
						"cached":   true,
						"message":  "Identical document already processed",
					})
					return
				}
			}
		}
	}

	jobID := uuid.New().String()
	objectName := fmt.Sprintf("raw/%s/%s", jobID, header.Filename)

	// Upload from buffer (already read for hashing)
	reader := io.NopCloser(&buf)
	storagePath, err := minioStore.UploadFile(
		context.Background(), objectName, reader, header.Size,
		header.Header.Get("Content-Type"),
	)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to upload document"})
		log.Printf("Upload error: %v", err)
		return
	}

	// Store content hash → job ID mapping in cache
	if redisCache != nil && contentHash != "" {
		redisCache.MarkProcessed(context.Background(), contentHash, jobID)
	}

	// --- Output Formats & Options ---
	outputFormats := c.DefaultPostForm("output_formats", "text")
	customPrompt := c.DefaultPostForm("prompt", "")
	includeCoordinates := c.DefaultPostForm("include_coordinates", "false") == "true"
	includeWordConfidence := c.DefaultPostForm("include_word_confidence", "false") == "true"
	includeLineConfidence := c.DefaultPostForm("include_line_confidence", "false") == "true"
	includePageLayout := c.DefaultPostForm("include_page_layout", "false") == "true"
	language := c.DefaultPostForm("language", "auto")
	granularity := c.DefaultPostForm("granularity", "block")
	redactPII := c.DefaultPostForm("redact_pii", "false") == "true"
	enhance := c.DefaultPostForm("enhance", "true") == "true"
	deskew := c.DefaultPostForm("deskew", "true") == "true"
	maxPages := c.DefaultPostForm("max_pages", "0")
	temperature := c.DefaultPostForm("temperature", "0.0")
	maxTokens := c.DefaultPostForm("max_tokens", "4096")
	precisionMode := c.DefaultPostForm("precision_mode", "normal")
	extractFieldsRaw := strings.TrimSpace(c.DefaultPostForm("extract_fields", ""))

	// Layout detection options
	enableLayoutDetection := c.DefaultPostForm("enable_layout_detection", "false") == "true"
	minConfidence := c.DefaultPostForm("min_confidence", "0.5")
	detectTables := c.DefaultPostForm("detect_tables", "true") == "true"
	detectFormulas := c.DefaultPostForm("detect_formulas", "true") == "true"
	parallelRegionProcessing := c.DefaultPostForm("parallel_region_processing", "true") == "true"
	maxParallelRegions := c.DefaultPostForm("max_parallel_regions", "5")
	cacheLayoutResults := c.DefaultPostForm("cache_layout_results", "true") == "true"

	extractFields := []string{}
	if extractFieldsRaw != "" {
		for _, f := range strings.Split(extractFieldsRaw, ",") {
			f = strings.TrimSpace(f)
			if f != "" {
				extractFields = append(extractFields, f)
			}
		}
	}

	// Validate formats (skip if custom prompt provided)
	if customPrompt == "" {
		validFormats := map[string]bool{
			"text": true, "json": true, "markdown": true,
			"table": true, "key_value": true, "structured": true,
		}
		for _, f := range strings.Split(outputFormats, ",") {
			f = strings.TrimSpace(f)
			if f != "" && !validFormats[f] {
				c.JSON(http.StatusBadRequest, gin.H{
					"error":         fmt.Sprintf("Invalid output format: '%s'", f),
					"valid_formats": []string{"text", "json", "markdown", "table", "key_value", "structured"},
					"usage":         "Comma-separated, e.g. 'text,table,json'. Or use 'prompt' for custom instructions.",
				})
				return
			}
		}
	}

	job := models.Job{
		ID:            jobID,
		Filename:      header.Filename,
		FileSize:      header.Size,
		ContentType:   header.Header.Get("Content-Type"),
		StoragePath:   storagePath,
		Status:        models.StatusUploaded,
		OutputFormats: outputFormats,
	}
	if err := db.Create(&job).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create job record"})
		return
	}
	middleware.RecordJobCreated()

	// --- Enqueue job to Redis queue ---
	queuedJob := &queue.QueuedJob{
		JobID:        jobID,
		Priority:     0, // Default priority (normal)
		EnqueuedAt:   time.Now(),
		DocumentSize: header.Size,
		Options: map[string]interface{}{
			"prompt":                     customPrompt,
			"include_coordinates":        includeCoordinates,
			"include_word_confidence":    includeWordConfidence,
			"include_line_confidence":    includeLineConfidence,
			"include_page_layout":        includePageLayout,
			"language":                   language,
			"granularity":                granularity,
			"redact_pii":                 redactPII,
			"enhance":                    enhance,
			"deskew":                     deskew,
			"max_pages":                  maxPages,
			"temperature":                temperature,
			"max_tokens":                 maxTokens,
			"precision_mode":             precisionMode,
			"extract_fields":             extractFields,
			"enable_layout_detection":    enableLayoutDetection,
			"parallel_region_processing": parallelRegionProcessing,
			"layout_detection_options": map[string]interface{}{
				"min_confidence":       minConfidence,
				"detect_tables":        detectTables,
				"detect_formulas":      detectFormulas,
				"max_parallel_regions": maxParallelRegions,
				"cache_layout_results": cacheLayoutResults,
			},
		},
	}

	if err := requestQueue.Enqueue(c.Request.Context(), queuedJob); err != nil {
		// Queue is full - return HTTP 429 with retry-after header
		estimatedWait, _ := requestQueue.GetEstimatedWaitTime(c.Request.Context())
		retryAfterSeconds := int(estimatedWait.Seconds())
		if retryAfterSeconds < 60 {
			retryAfterSeconds = 60 // Minimum 1 minute retry
		}

		c.Header("Retry-After", fmt.Sprintf("%d", retryAfterSeconds))
		c.JSON(http.StatusTooManyRequests, gin.H{
			"error":                       "Queue is full, please retry later",
			"retry_after_seconds":         retryAfterSeconds,
			"estimated_wait_time_seconds": int(estimatedWait.Seconds()),
		})

		// Clean up the job record since we couldn't enqueue
		db.Delete(&job)
		return
	}

	queueLength, _ := requestQueue.GetQueueLength(c.Request.Context())
	estimatedWait, _ := requestQueue.GetEstimatedWaitTime(c.Request.Context())

	workflowOptions := client.StartWorkflowOptions{
		ID:        fmt.Sprintf("doc-processing-%s", jobID),
		TaskQueue: cfg.TemporalTaskQueue,
	}
	workflowInput := map[string]interface{}{
		"job_id":         jobID,
		"filename":       header.Filename,
		"storage_path":   storagePath,
		"content_type":   header.Header.Get("Content-Type"),
		"file_ext":       filepath.Ext(header.Filename),
		"output_formats": outputFormats,
		"options": map[string]interface{}{
			"prompt":                     customPrompt,
			"include_coordinates":        includeCoordinates,
			"include_word_confidence":    includeWordConfidence,
			"include_line_confidence":    includeLineConfidence,
			"include_page_layout":        includePageLayout,
			"language":                   language,
			"granularity":                granularity,
			"redact_pii":                 redactPII,
			"enhance":                    enhance,
			"deskew":                     deskew,
			"max_pages":                  maxPages,
			"temperature":                temperature,
			"max_tokens":                 maxTokens,
			"precision_mode":             precisionMode,
			"extract_fields":             extractFields,
			"enable_layout_detection":    enableLayoutDetection,
			"parallel_region_processing": parallelRegionProcessing,
			"layout_detection_options": map[string]interface{}{
				"min_confidence":       minConfidence,
				"detect_tables":        detectTables,
				"detect_formulas":      detectFormulas,
				"max_parallel_regions": maxParallelRegions,
				"cache_layout_results": cacheLayoutResults,
			},
		},
	}

	we, err := temporalClient.ExecuteWorkflow(context.Background(), workflowOptions, "DocumentProcessingWorkflow", workflowInput)
	if err != nil {
		log.Printf("Failed to start workflow for job %s: %v", jobID, err)
		if requestQueue != nil {
			if qErr := requestQueue.CancelJob(c.Request.Context(), jobID); qErr != nil {
				log.Printf("⚠️ Failed to remove failed-start job from queue %s: %v", jobID, qErr)
			}
		}
		db.Model(&job).Updates(map[string]interface{}{
			"status":        models.StatusFailed,
			"error_message": fmt.Sprintf("Failed to start workflow: %v", err),
		})
		middleware.RecordJobFailed()
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to start processing workflow"})
		return
	}

	db.Model(&job).Updates(map[string]interface{}{
		"workflow_id": we.GetID(),
		"run_id":      we.GetRunID(),
		"status":      models.StatusProcessing,
	})

	c.JSON(http.StatusAccepted, gin.H{
		"job_id":                      jobID,
		"filename":                    header.Filename,
		"status":                      "QUEUED",
		"workflow_id":                 we.GetID(),
		"output_formats":              outputFormats,
		"queue_position":              queueLength,
		"estimated_wait_time_seconds": int(estimatedWait.Seconds()),
		"options": gin.H{
			"prompt":                     customPrompt,
			"include_coordinates":        includeCoordinates,
			"include_word_confidence":    includeWordConfidence,
			"include_line_confidence":    includeLineConfidence,
			"include_page_layout":        includePageLayout,
			"language":                   language,
			"granularity":                granularity,
			"redact_pii":                 redactPII,
			"enhance":                    enhance,
			"deskew":                     deskew,
			"max_pages":                  maxPages,
			"temperature":                temperature,
			"max_tokens":                 maxTokens,
			"precision_mode":             precisionMode,
			"extract_fields":             extractFields,
			"enable_layout_detection":    enableLayoutDetection,
			"parallel_region_processing": parallelRegionProcessing,
			"layout_detection_options": gin.H{
				"min_confidence":       minConfidence,
				"detect_tables":        detectTables,
				"detect_formulas":      detectFormulas,
				"max_parallel_regions": maxParallelRegions,
				"cache_layout_results": cacheLayoutResults,
			},
		},
		"result_url": fmt.Sprintf("/jobs/%s/result", jobID),
		"status_url": fmt.Sprintf("/jobs/%s", jobID),
	})
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

	reader, err := minioStore.DownloadFile(context.Background(), job.ResultPath)
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
	result := db.Order("created_at desc").Limit(100).Find(&jobs)
	if result.Error != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to list jobs"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"jobs": jobs, "count": len(jobs)})
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
		"timestamp":                   time.Now().Format(time.RFC3339),
	})
}
