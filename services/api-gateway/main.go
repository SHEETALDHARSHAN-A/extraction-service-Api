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
	"github.com/user/idep/api-gateway/cache"
	"github.com/user/idep/api-gateway/clients"
	"github.com/user/idep/api-gateway/config"
	"github.com/user/idep/api-gateway/handlers"
	"github.com/user/idep/api-gateway/middleware"
	"github.com/user/idep/api-gateway/models"
	"github.com/user/idep/api-gateway/orchestrator"
	"github.com/user/idep/api-gateway/storage"
	enumspb "go.temporal.io/api/enums/v1"
	"go.temporal.io/sdk/client"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

var (
	db                *gorm.DB
	minioStore        *storage.MinioClient
	temporalClient    client.Client
	redisCache        *cache.RedisCache
	cfg               *config.Config
	paddleOCRClient   *clients.PaddleOCRClient
	glmOCRClient      *clients.GLMOCRClient
	docOrchestrator   *orchestrator.Orchestrator
)

func main() {
	cfg = config.Load()

	// --- Initialize PostgreSQL ---
	var err error
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
	c.JSON(http.StatusOK, gin.H{
		"status":  "healthy",
		"service": "idep-api-gateway",
		"time":    time.Now().Format(time.RFC3339),
	})
}

func uploadDocument(c *gin.Context) {
	file, header, err := c.Request.FormFile("document")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "No document provided"})
		return
	}
	defer file.Close()

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
				"min_confidence":   minConfidence,
				"detect_tables":    detectTables,
				"detect_formulas":  detectFormulas,
				"max_parallel_regions": maxParallelRegions,
				"cache_layout_results": cacheLayoutResults,
			},
		},
	}

	we, err := temporalClient.ExecuteWorkflow(context.Background(), workflowOptions, "DocumentProcessingWorkflow", workflowInput)
	if err != nil {
		log.Printf("Failed to start workflow for job %s: %v", jobID, err)
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
		"job_id":         jobID,
		"filename":       header.Filename,
		"status":         "PROCESSING",
		"workflow_id":    we.GetID(),
		"output_formats": outputFormats,
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
