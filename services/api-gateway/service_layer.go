package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"mime/multipart"
	"net/http"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/user/idep/api-gateway/cache"
	"github.com/user/idep/api-gateway/middleware"
	"github.com/user/idep/api-gateway/models"
	"github.com/user/idep/api-gateway/queue"
	"github.com/user/idep/api-gateway/storage"
	"go.temporal.io/sdk/client"
	"gorm.io/gorm"
)

const (
	maxUploadDocumentSizeBytes = 10 * 1024 * 1024
	defaultOutputFormats       = "text"
	defaultPrompt              = ""
	defaultLanguage            = "auto"
	defaultGranularity         = "block"
	defaultMaxPages            = "0"
	defaultTemperature         = "0.0"
	defaultMaxTokens           = "4096"
	defaultPrecisionMode       = "high"
	defaultMinConfidence       = "0.5"
	defaultMaxParallelRegions  = "5"
	defaultWaitTimeoutSeconds  = 1200
	defaultPollIntervalMS      = 1000
	minPollIntervalMS          = 200
	maxPollIntervalMS          = 5000
	minWaitTimeoutSeconds      = 10
	maxWaitTimeoutSeconds      = 7200
)

var validOutputFormats = map[string]bool{
	"text":       true,
	"json":       true,
	"markdown":   true,
	"table":      true,
	"key_value":  true,
	"structured": true,
}

type HealthService struct {
	DB      *gorm.DB
	Cache   *cache.RedisCache
	Queue   queue.RequestQueue
	GLMURL  string
	Service string
}

func (h *HealthService) Check(c *gin.Context) {
	ctx := c.Request.Context()
	components := make(map[string]interface{})
	overallStatus := "healthy"

	tritonEndpoint := h.GLMURL
	if !strings.HasPrefix(strings.ToLower(tritonEndpoint), "grpc://") {
		tritonEndpoint = tritonEndpoint + "/health"
	}
	tritonStatus := checkServiceHealth(tritonEndpoint)
	components["triton"] = tritonStatus
	if !isHealthyStatus(tritonStatus) {
		overallStatus = "degraded"
	}

	glmEndpoint := h.GLMURL
	if !strings.HasPrefix(strings.ToLower(glmEndpoint), "grpc://") {
		glmEndpoint = glmEndpoint + "/health"
	}
	glmOCRStatus := checkServiceHealth(glmEndpoint)
	components["glm_ocr_service"] = glmOCRStatus
	if !isHealthyStatus(glmOCRStatus) {
		overallStatus = "degraded"
	}

	if h.Queue != nil {
		queueStatus, ok := h.queueHealth(ctx)
		components["request_queue"] = queueStatus
		if !ok {
			overallStatus = "degraded"
		}
	} else {
		components["request_queue"] = gin.H{"status": "unavailable"}
		overallStatus = "degraded"
	}

	dbStatus, ok := h.dbHealth()
	components["database"] = dbStatus
	if !ok {
		overallStatus = "unhealthy"
	}

	redisStatus, ok := h.redisHealth(ctx)
	components["redis"] = redisStatus
	if !ok {
		overallStatus = "degraded"
	}

	statusCode := http.StatusOK
	if overallStatus == "unhealthy" {
		statusCode = http.StatusServiceUnavailable
	}

	c.JSON(statusCode, gin.H{
		"status":     overallStatus,
		"timestamp":  time.Now().Format(time.RFC3339),
		"service":    h.Service,
		"components": components,
	})
}

func (h *HealthService) queueHealth(ctx context.Context) (gin.H, bool) {
	queueLength, err := h.Queue.GetQueueLength(ctx)
	estimatedWait, _ := h.Queue.GetEstimatedWaitTime(ctx)
	status := gin.H{"status": "healthy"}
	if err != nil {
		status["status"] = "unhealthy"
		status["error"] = err.Error()
		return status, false
	}
	status["queue_length"] = queueLength
	status["estimated_wait_time_seconds"] = int(estimatedWait.Seconds())
	return status, true
}

func (h *HealthService) dbHealth() (gin.H, bool) {
	sqlDB, err := h.DB.DB()
	status := gin.H{"status": "healthy"}
	if err != nil || sqlDB.Ping() != nil {
		status["status"] = "unhealthy"
		if err != nil {
			status["error"] = err.Error()
		}
		return status, false
	}
	stats := sqlDB.Stats()
	status["connection_pool_available"] = stats.MaxOpenConnections - stats.InUse
	return status, true
}

func (h *HealthService) redisHealth(ctx context.Context) (gin.H, bool) {
	if h.Cache == nil {
		return gin.H{"status": "unavailable"}, false
	}
	status := gin.H{"status": "healthy"}
	if h.Cache.GetCacheStats(ctx) == nil {
		status["status"] = "unhealthy"
		return status, false
	}
	return status, true
}

type DocumentService struct {
	DB          *gorm.DB
	Storage     storage.StorageClient
	Cache       *cache.RedisCache
	Queue       queue.RequestQueue
	Temporal    client.Client
	TaskQueue   string
	UploadLimit int64
}

func (d *DocumentService) Upload(c *gin.Context) {
	file, header, err := c.Request.FormFile("document")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "No document provided"})
		return
	}
	defer file.Close()

	if !d.validateSize(c, header) {
		return
	}

	buffer, contentHash, err := readUploadPayload(file)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Failed to read document payload"})
		return
	}

	if d.tryServeDuplicate(c, contentHash, header.Filename) {
		return
	}

	jobID := uuid.New().String()
	objectName := fmt.Sprintf("raw/%s/%s", jobID, header.Filename)
	storagePath, err := d.Storage.UploadFile(
		context.Background(),
		objectName,
		io.NopCloser(bytes.NewReader(buffer.Bytes())),
		header.Size,
		header.Header.Get("Content-Type"),
	)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to upload document"})
		log.Printf("Upload error: %v", err)
		return
	}

	if d.Cache != nil && contentHash != "" {
		d.Cache.MarkProcessed(context.Background(), contentHash, jobID)
	}

	uploadOptions, err := parseUploadOptions(c)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error(), "valid_formats": sortedFormats()})
		return
	}

	job := models.Job{
		ID:            jobID,
		Filename:      header.Filename,
		FileSize:      header.Size,
		ContentType:   header.Header.Get("Content-Type"),
		StoragePath:   storagePath,
		Status:        models.StatusUploaded,
		OutputFormats: uploadOptions.OutputFormats,
	}
	if err := d.DB.Create(&job).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create job record"})
		return
	}
	middleware.RecordJobCreated()

	queuedJob := buildQueuedJob(jobID, header.Size, uploadOptions)
	queueLength, estimatedWait, queued := d.tryEnqueue(c, queuedJob, &job)
	if !queued {
		return
	}

	if d.Temporal == nil {
		c.JSON(http.StatusAccepted, queuedResponse(jobID, header.Filename, "", uploadOptions.OutputFormats, queueLength, estimatedWait, "Document uploaded and queued. Temporal is currently unavailable, it will be processed shortly."))
		return
	}

	workflowOptions := client.StartWorkflowOptions{
		ID:        fmt.Sprintf("doc-processing-%s", jobID),
		TaskQueue: d.TaskQueue,
	}
	workflowInput := buildWorkflowInput(jobID, header, storagePath, uploadOptions)

	we, err := d.Temporal.ExecuteWorkflow(context.Background(), workflowOptions, "DocumentProcessingWorkflow", workflowInput)
	if err != nil {
		log.Printf("⚠️ Failed to start workflow for job %s: %v. Job remains queued.", jobID, err)
		c.JSON(http.StatusAccepted, gin.H{
			"error":          "Failed to immediately start processing workflow, but job is queued",
			"job_id":         jobID,
			"status":         "QUEUED",
			"queue_position": queueLength,
		})
		return
	}

	d.DB.Model(&job).Updates(map[string]interface{}{
		"workflow_id": we.GetID(),
		"run_id":      we.GetRunID(),
		"status":      models.StatusProcessing,
	})

	c.JSON(http.StatusAccepted, successUploadResponse(jobID, header.Filename, we.GetID(), queueLength, estimatedWait, uploadOptions))
}

// Extract processes a document end-to-end in one API call and returns final output.
// It accepts the same multipart payload/options as /jobs/upload plus:
// - wait_timeout_seconds (default: 1200)
// - poll_interval_ms (default: 1000)
func (d *DocumentService) Extract(c *gin.Context) {
	file, header, err := c.Request.FormFile("document")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "No document provided"})
		return
	}
	defer file.Close()

	if !d.validateSize(c, header) {
		return
	}

	uploadOptions, err := parseUploadOptions(c)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error(), "valid_formats": sortedFormats()})
		return
	}

	waitTimeoutSeconds := parseIntFormWithBounds(c, "wait_timeout_seconds", defaultWaitTimeoutSeconds, minWaitTimeoutSeconds, maxWaitTimeoutSeconds)
	pollIntervalMS := parseIntFormWithBounds(c, "poll_interval_ms", defaultPollIntervalMS, minPollIntervalMS, maxPollIntervalMS)
	waitTimeout := time.Duration(waitTimeoutSeconds) * time.Second
	pollInterval := time.Duration(pollIntervalMS) * time.Millisecond

	buffer, contentHash, err := readUploadPayload(file)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Failed to read document payload"})
		return
	}

	if d.Cache != nil && contentHash != "" {
		existingJobID, found := d.Cache.CheckDuplicate(context.Background(), contentHash)
		if found {
			var existingJob models.Job
			if d.DB.First(&existingJob, "id = ?", existingJobID).Error == nil {
				if existingJob.Status == models.StatusFailed {
					log.Printf("♻️ Cache hit for FAILED job %s - evicting, will reprocess %s", existingJobID, header.Filename)
					d.Cache.Evict(context.Background(), contentHash)
				} else {
					resultPayload, resultErr := d.waitForAndLoadResult(c.Request.Context(), existingJob.ID, waitTimeout, pollInterval)
					if resultErr == nil {
						c.JSON(http.StatusOK, d.successExtractResponse(&existingJob, uploadOptions, resultPayload, true))
						return
					}
					if resultErr == context.DeadlineExceeded {
						c.JSON(http.StatusAccepted, gin.H{
							"job_id":          existingJob.ID,
							"filename":        existingJob.Filename,
							"status":          existingJob.Status,
							"cached":          true,
							"status_url":      fmt.Sprintf("/jobs/%s", existingJob.ID),
							"result_url":      fmt.Sprintf("/jobs/%s/result", existingJob.ID),
							"message":         "Document is already submitted and still processing. Poll the status/result URLs.",
							"wait_timeout_ms": waitTimeout.Milliseconds(),
						})
						return
					}

					c.JSON(http.StatusInternalServerError, gin.H{
						"error":  "Failed to fetch cached job result",
						"job_id": existingJob.ID,
					})
					return
				}
			}
		}
	}

	jobID := uuid.New().String()
	objectName := fmt.Sprintf("raw/%s/%s", jobID, header.Filename)
	storagePath, err := d.Storage.UploadFile(
		context.Background(),
		objectName,
		io.NopCloser(bytes.NewReader(buffer.Bytes())),
		header.Size,
		header.Header.Get("Content-Type"),
	)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to upload document"})
		log.Printf("Upload error: %v", err)
		return
	}

	if d.Cache != nil && contentHash != "" {
		d.Cache.MarkProcessed(context.Background(), contentHash, jobID)
	}

	job := models.Job{
		ID:            jobID,
		Filename:      header.Filename,
		FileSize:      header.Size,
		ContentType:   header.Header.Get("Content-Type"),
		StoragePath:   storagePath,
		Status:        models.StatusUploaded,
		OutputFormats: uploadOptions.OutputFormats,
	}
	if err := d.DB.Create(&job).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create job record"})
		return
	}
	middleware.RecordJobCreated()

	queuedJob := buildQueuedJob(jobID, header.Size, uploadOptions)
	queueLength, estimatedWait, queued := d.tryEnqueue(c, queuedJob, &job)
	if !queued {
		return
	}

	if d.Temporal == nil {
		c.JSON(http.StatusAccepted, queuedResponse(jobID, header.Filename, "", uploadOptions.OutputFormats, queueLength, estimatedWait, "Document uploaded and queued. Temporal is currently unavailable, it will be processed shortly."))
		return
	}

	workflowOptions := client.StartWorkflowOptions{
		ID:        fmt.Sprintf("doc-processing-%s", jobID),
		TaskQueue: d.TaskQueue,
	}
	workflowInput := buildWorkflowInput(jobID, header, storagePath, uploadOptions)

	we, err := d.Temporal.ExecuteWorkflow(context.Background(), workflowOptions, "DocumentProcessingWorkflow", workflowInput)
	if err != nil {
		log.Printf("⚠️ Failed to start workflow for job %s: %v. Job remains queued.", jobID, err)
		c.JSON(http.StatusAccepted, gin.H{
			"error":          "Failed to immediately start processing workflow, but job is queued",
			"job_id":         jobID,
			"status":         "QUEUED",
			"queue_position": queueLength,
		})
		return
	}

	d.DB.Model(&job).Updates(map[string]interface{}{
		"workflow_id": we.GetID(),
		"run_id":      we.GetRunID(),
		"status":      models.StatusProcessing,
	})
	job.WorkflowID = we.GetID()
	job.RunID = we.GetRunID()
	job.Status = models.StatusProcessing

	resultPayload, resultErr := d.waitForAndLoadResult(c.Request.Context(), jobID, waitTimeout, pollInterval)
	if resultErr == context.DeadlineExceeded {
		c.JSON(http.StatusAccepted, gin.H{
			"job_id":               jobID,
			"filename":             header.Filename,
			"status":               models.StatusProcessing,
			"workflow_id":          we.GetID(),
			"queue_position":       queueLength,
			"output_formats":       uploadOptions.OutputFormats,
			"options":              buildOptionsMap(uploadOptions),
			"status_url":           fmt.Sprintf("/jobs/%s", jobID),
			"result_url":           fmt.Sprintf("/jobs/%s/result", jobID),
			"message":              "Processing started but did not finish before wait timeout. Poll status/result URLs.",
			"wait_timeout_seconds": waitTimeoutSeconds,
		})
		return
	}

	if resultErr != nil {
		var currentJob models.Job
		if d.DB.First(&currentJob, "id = ?", jobID).Error == nil && currentJob.Status == models.StatusFailed {
			c.JSON(http.StatusUnprocessableEntity, gin.H{
				"job_id":  jobID,
				"status":  currentJob.Status,
				"error":   "Document processing failed",
				"details": currentJob.ErrorMessage,
			})
			return
		}

		c.JSON(http.StatusInternalServerError, gin.H{
			"job_id": jobID,
			"error":  "Failed to load extraction result",
		})
		return
	}

	_ = d.DB.First(&job, "id = ?", jobID)
	c.JSON(http.StatusOK, d.successExtractResponse(&job, uploadOptions, resultPayload, false))
}

func (d *DocumentService) waitForAndLoadResult(parentCtx context.Context, jobID string, waitTimeout time.Duration, pollInterval time.Duration) (interface{}, error) {
	ctx, cancel := context.WithTimeout(parentCtx, waitTimeout)
	defer cancel()

	ticker := time.NewTicker(pollInterval)
	defer ticker.Stop()

	var lastJob models.Job

	for {
		if err := d.DB.First(&lastJob, "id = ?", jobID).Error; err != nil {
			return nil, err
		}

		syncJobWithWorkflowStatus(ctx, &lastJob)

		switch lastJob.Status {
		case models.StatusCompleted:
			if lastJob.ResultPath == "" {
				return nil, fmt.Errorf("job completed but result path is empty")
			}
			return d.loadResultPayload(ctx, lastJob.ResultPath)
		case models.StatusFailed:
			return nil, fmt.Errorf("job failed: %s", lastJob.ErrorMessage)
		}

		select {
		case <-ctx.Done():
			if ctx.Err() == context.DeadlineExceeded {
				return nil, context.DeadlineExceeded
			}
			return nil, ctx.Err()
		case <-ticker.C:
		}
	}
}

func (d *DocumentService) loadResultPayload(ctx context.Context, resultPath string) (interface{}, error) {
	reader, err := d.Storage.DownloadFile(ctx, resultPath)
	if err != nil {
		return nil, err
	}
	defer reader.Close()

	body, err := io.ReadAll(reader)
	if err != nil {
		return nil, err
	}

	var parsed interface{}
	if err := json.Unmarshal(body, &parsed); err == nil {
		return parsed, nil
	}

	return string(body), nil
}

func (d *DocumentService) successExtractResponse(job *models.Job, opts *UploadOptions, resultPayload interface{}, cached bool) gin.H {
	response := gin.H{
		"job_id":         job.ID,
		"filename":       job.Filename,
		"status":         job.Status,
		"workflow_id":    job.WorkflowID,
		"output_formats": opts.OutputFormats,
		"options":        buildOptionsMap(opts),
		"page_count":     job.PageCount,
		"confidence":     job.Confidence,
		"result":         resultPayload,
		"cached":         cached,
	}

	return response
}

func parseIntFormWithBounds(c *gin.Context, key string, defaultValue, minValue, maxValue int) int {
	raw := strings.TrimSpace(c.DefaultPostForm(key, strconv.Itoa(defaultValue)))
	value, err := strconv.Atoi(raw)
	if err != nil {
		return defaultValue
	}
	if value < minValue {
		return minValue
	}
	if value > maxValue {
		return maxValue
	}
	return value
}

func (d *DocumentService) validateSize(c *gin.Context, header *multipart.FileHeader) bool {
	maxSize := d.UploadLimit
	if maxSize <= 0 {
		maxSize = maxUploadDocumentSizeBytes
	}
	if header.Size <= maxSize {
		return true
	}

	maxSizeMB := float64(maxSize) / (1024 * 1024)
	providedSizeMB := float64(header.Size) / (1024 * 1024)
	log.Printf("❌ Document too large: %s (%.2fMB) exceeds maximum of %.2fMB", header.Filename, providedSizeMB, maxSizeMB)
	c.JSON(http.StatusRequestEntityTooLarge, gin.H{
		"error":            "Document too large",
		"max_size_mb":      maxSizeMB,
		"provided_size_mb": providedSizeMB,
		"message":          fmt.Sprintf("Document size (%.2fMB) exceeds maximum allowed size of %.2fMB", providedSizeMB, maxSizeMB),
	})
	return false
}

func (d *DocumentService) tryServeDuplicate(c *gin.Context, contentHash, filename string) bool {
	if d.Cache == nil || contentHash == "" {
		return false
	}

	existingJobID, found := d.Cache.CheckDuplicate(context.Background(), contentHash)
	if !found {
		return false
	}

	var existingJob models.Job
	if d.DB.First(&existingJob, "id = ?", existingJobID).Error != nil {
		return false
	}

	if existingJob.Status == models.StatusFailed {
		log.Printf("♻️ Cache hit for FAILED job %s - evicting, will reprocess %s", existingJobID, filename)
		d.Cache.Evict(context.Background(), contentHash)
		return false
	}

	log.Printf("♻️ Cache hit: %s -> existing job %s (status=%s)", filename, existingJobID, existingJob.Status)
	c.JSON(http.StatusOK, gin.H{
		"job_id":   existingJobID,
		"filename": filename,
		"status":   existingJob.Status,
		"cached":   true,
		"message":  "Identical document already processed",
	})
	return true
}

func (d *DocumentService) tryEnqueue(c *gin.Context, queuedJob *queue.QueuedJob, job *models.Job) (int64, time.Duration, bool) {
	var queueLength int64
	var estimatedWait time.Duration
	if d.Queue == nil {
		return queueLength, estimatedWait, true
	}

	if err := d.Queue.Enqueue(c.Request.Context(), queuedJob); err != nil {
		estimatedWait, _ = d.Queue.GetEstimatedWaitTime(c.Request.Context())
		retryAfterSeconds := int(estimatedWait.Seconds())
		if retryAfterSeconds < 60 {
			retryAfterSeconds = 60
		}
		c.Header("Retry-After", fmt.Sprintf("%d", retryAfterSeconds))
		c.JSON(http.StatusTooManyRequests, gin.H{
			"error":                       "Queue is full, please retry later",
			"retry_after_seconds":         retryAfterSeconds,
			"estimated_wait_time_seconds": int(estimatedWait.Seconds()),
		})
		d.DB.Delete(job)
		return 0, estimatedWait, false
	}

	queueLength, _ = d.Queue.GetQueueLength(c.Request.Context())
	estimatedWait, _ = d.Queue.GetEstimatedWaitTime(c.Request.Context())
	return queueLength, estimatedWait, true
}

type UploadOptions struct {
	OutputFormats            string
	Prompt                   string
	IncludeCoordinates       bool
	FastMode                 bool
	IncludeWordConfidence    bool
	IncludeLineConfidence    bool
	IncludePageLayout        bool
	Language                 string
	Granularity              string
	RedactPII                bool
	Enhance                  bool
	Deskew                   bool
	MaxPages                 string
	Temperature              string
	MaxTokens                string
	PrecisionMode            string
	ExtractFields            []string
	EnableLayoutDetection    bool
	MinConfidence            string
	DetectTables             bool
	DetectFormulas           bool
	ParallelRegionProcessing bool
	MaxParallelRegions       string
	CacheLayoutResults       bool
}

func parseUploadOptions(c *gin.Context) (*UploadOptions, error) {
	opts := &UploadOptions{
		OutputFormats:            c.DefaultPostForm("output_formats", defaultOutputFormats),
		Prompt:                   c.DefaultPostForm("prompt", defaultPrompt),
		IncludeCoordinates:       parseBoolForm(c, "include_coordinates", false),
		FastMode:                 parseBoolForm(c, "fast_mode", false),
		IncludeWordConfidence:    parseBoolForm(c, "include_word_confidence", false),
		IncludeLineConfidence:    parseBoolForm(c, "include_line_confidence", false),
		IncludePageLayout:        parseBoolForm(c, "include_page_layout", false),
		Language:                 c.DefaultPostForm("language", defaultLanguage),
		Granularity:              c.DefaultPostForm("granularity", defaultGranularity),
		RedactPII:                parseBoolForm(c, "redact_pii", false),
		Enhance:                  parseBoolForm(c, "enhance", true),
		Deskew:                   parseBoolForm(c, "deskew", true),
		MaxPages:                 c.DefaultPostForm("max_pages", defaultMaxPages),
		Temperature:              c.DefaultPostForm("temperature", defaultTemperature),
		MaxTokens:                c.DefaultPostForm("max_tokens", defaultMaxTokens),
		PrecisionMode:            c.DefaultPostForm("precision_mode", defaultPrecisionMode),
		EnableLayoutDetection:    parseBoolForm(c, "enable_layout_detection", false),
		MinConfidence:            c.DefaultPostForm("min_confidence", defaultMinConfidence),
		DetectTables:             parseBoolForm(c, "detect_tables", true),
		DetectFormulas:           parseBoolForm(c, "detect_formulas", true),
		ParallelRegionProcessing: parseBoolForm(c, "parallel_region_processing", true),
		MaxParallelRegions:       c.DefaultPostForm("max_parallel_regions", defaultMaxParallelRegions),
		CacheLayoutResults:       parseBoolForm(c, "cache_layout_results", true),
	}

	extractFieldsRaw := strings.TrimSpace(c.DefaultPostForm("extract_fields", ""))
	if extractFieldsRaw != "" {
		for _, field := range strings.Split(extractFieldsRaw, ",") {
			field = strings.TrimSpace(field)
			if field != "" {
				opts.ExtractFields = append(opts.ExtractFields, field)
			}
		}
	}

	if opts.Prompt == "" {
		for _, f := range strings.Split(opts.OutputFormats, ",") {
			clean := strings.TrimSpace(f)
			if clean != "" && !validOutputFormats[clean] {
				return nil, fmt.Errorf("invalid output format: '%s'", clean)
			}
		}
	}

	return opts, nil
}

func parseBoolForm(c *gin.Context, key string, defaultValue bool) bool {
	defaultRaw := "false"
	if defaultValue {
		defaultRaw = "true"
	}
	return strings.EqualFold(c.DefaultPostForm(key, defaultRaw), "true")
}

func readUploadPayload(file multipart.File) (*bytes.Buffer, string, error) {
	var buf bytes.Buffer
	tee := io.TeeReader(file, &buf)
	hash, err := cache.HashContent(tee)
	if err != nil {
		return nil, "", err
	}
	return &buf, hash, nil
}

func buildQueuedJob(jobID string, size int64, opts *UploadOptions) *queue.QueuedJob {
	return &queue.QueuedJob{
		JobID:        jobID,
		Priority:     0,
		EnqueuedAt:   time.Now(),
		DocumentSize: size,
		Options:      buildOptionsMap(opts),
	}
}

func buildOptionsMap(opts *UploadOptions) map[string]interface{} {
	return map[string]interface{}{
		"prompt":                     opts.Prompt,
		"fast_mode":                  opts.FastMode,
		"include_coordinates":        opts.IncludeCoordinates,
		"include_word_confidence":    opts.IncludeWordConfidence,
		"include_line_confidence":    opts.IncludeLineConfidence,
		"include_page_layout":        opts.IncludePageLayout,
		"language":                   opts.Language,
		"granularity":                opts.Granularity,
		"redact_pii":                 opts.RedactPII,
		"enhance":                    opts.Enhance,
		"deskew":                     opts.Deskew,
		"max_pages":                  opts.MaxPages,
		"temperature":                opts.Temperature,
		"max_tokens":                 opts.MaxTokens,
		"precision_mode":             opts.PrecisionMode,
		"extract_fields":             opts.ExtractFields,
		"enable_layout_detection":    opts.EnableLayoutDetection,
		"parallel_region_processing": opts.ParallelRegionProcessing,
		"layout_detection_options": map[string]interface{}{
			"min_confidence":       opts.MinConfidence,
			"detect_tables":        opts.DetectTables,
			"detect_formulas":      opts.DetectFormulas,
			"max_parallel_regions": opts.MaxParallelRegions,
			"cache_layout_results": opts.CacheLayoutResults,
		},
	}
}

func buildWorkflowInput(jobID string, header *multipart.FileHeader, storagePath string, opts *UploadOptions) map[string]interface{} {
	return map[string]interface{}{
		"job_id":         jobID,
		"filename":       header.Filename,
		"storage_path":   storagePath,
		"content_type":   header.Header.Get("Content-Type"),
		"file_ext":       filepath.Ext(header.Filename),
		"output_formats": opts.OutputFormats,
		"options":        buildOptionsMap(opts),
	}
}

func queuedResponse(jobID, filename, workflowID, outputFormats string, queueLength int64, estimatedWait time.Duration, message string) gin.H {
	return gin.H{
		"job_id":                      jobID,
		"filename":                    filename,
		"status":                      "QUEUED",
		"workflow_id":                 workflowID,
		"output_formats":              outputFormats,
		"queue_position":              queueLength,
		"estimated_wait_time_seconds": int(estimatedWait.Seconds()),
		"message":                     message,
	}
}

func successUploadResponse(jobID, filename, workflowID string, queueLength int64, estimatedWait time.Duration, opts *UploadOptions) gin.H {
	return gin.H{
		"job_id":                      jobID,
		"filename":                    filename,
		"status":                      "QUEUED",
		"workflow_id":                 workflowID,
		"output_formats":              opts.OutputFormats,
		"queue_position":              queueLength,
		"estimated_wait_time_seconds": int(estimatedWait.Seconds()),
		"options":                     buildOptionsMap(opts),
		"result_url":                  fmt.Sprintf("/jobs/%s/result", jobID),
		"status_url":                  fmt.Sprintf("/jobs/%s", jobID),
	}
}

func sortedFormats() []string {
	return []string{"text", "json", "markdown", "table", "key_value", "structured"}
}

func isHealthyStatus(status gin.H) bool {
	health, ok := status["status"].(string)
	return ok && health == "healthy"
}
