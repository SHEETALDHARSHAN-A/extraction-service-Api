package main

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"log"
	"net/http"
	"path/filepath"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/user/idep/api-gateway/cache"
	"github.com/user/idep/api-gateway/config"
	"github.com/user/idep/api-gateway/handlers"
	"github.com/user/idep/api-gateway/middleware"
	"github.com/user/idep/api-gateway/models"
	"github.com/user/idep/api-gateway/storage"
	"go.temporal.io/sdk/client"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

var (
	db             *gorm.DB
	minioStore     *storage.MinioClient
	temporalClient client.Client
	redisCache     *cache.RedisCache
	cfg            *config.Config
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

	// --- Gin Router ---
	r := gin.Default()

	// Global middleware
	r.Use(middleware.PrometheusMiddleware())
	r.Use(middleware.RateLimit())

	// Public endpoints
	r.GET("/health", healthCheck)
	r.GET("/metrics", middleware.PrometheusHandler())
	r.POST("/auth/token", issueToken) // Dev-only login

	// Protected API routes
	api := r.Group("/jobs")
	api.Use(middleware.Auth())
	{
		api.POST("/upload", uploadDocument)
		api.POST("/batch", batchHandler().Handle)
		api.GET("/:id", getJobStatus)
		api.GET("/:id/result", getJobResult)
		api.GET("", listJobs)
		api.GET("/batch/:batch_id", getBatchStatus)
	}

	// Admin routes (require admin role)
	admin := r.Group("/admin")
	admin.Use(middleware.Auth(), middleware.RequireRole("admin"))
	{
		admin.GET("/stats", getSystemStats)
		admin.GET("/cache", getCacheStats)
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

func issueToken(c *gin.Context) {
	var req struct {
		UserID string `json:"user_id" binding:"required"`
		Role   string `json:"role" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	token, err := middleware.GenerateToken(req.UserID, req.Role)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Token generation failed"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"token": token, "expires_in": 900})
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
				log.Printf("♻️ Cache hit: %s → existing job %s", header.Filename, existingJobID)
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

	job := models.Job{
		ID:          jobID,
		Filename:    header.Filename,
		FileSize:    header.Size,
		ContentType: header.Header.Get("Content-Type"),
		StoragePath: storagePath,
		Status:      models.StatusUploaded,
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
		"job_id":       jobID,
		"filename":     header.Filename,
		"storage_path": storagePath,
		"content_type": header.Header.Get("Content-Type"),
		"file_ext":     filepath.Ext(header.Filename),
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
		"job_id":      jobID,
		"filename":    header.Filename,
		"status":      "PROCESSING",
		"workflow_id": we.GetID(),
	})
}

func getJobStatus(c *gin.Context) {
	jobID := c.Param("id")
	var job models.Job
	if err := db.First(&job, "id = ?", jobID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Job not found"})
		return
	}
	c.JSON(http.StatusOK, job)
}

func getJobResult(c *gin.Context) {
	jobID := c.Param("id")
	var job models.Job
	if err := db.First(&job, "id = ?", jobID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Job not found"})
		return
	}
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
	var jobs []models.Job
	db.Where("batch_id = ?", batchID).Find(&jobs)

	completed, failed, processing := 0, 0, 0
	for _, j := range jobs {
		switch j.Status {
		case models.StatusCompleted:
			completed++
		case models.StatusFailed:
			failed++
		default:
			processing++
		}
	}

	c.JSON(http.StatusOK, gin.H{
		"batch_id":   batchID,
		"total":      len(jobs),
		"completed":  completed,
		"failed":     failed,
		"processing": processing,
		"jobs":       jobs,
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
