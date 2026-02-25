package handlers

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"path/filepath"
	"strings"
	"sync"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/user/idep/api-gateway/models"
	"github.com/user/idep/api-gateway/storage"
	"go.temporal.io/sdk/client"
	"gorm.io/gorm"
)

// BatchUploadHandler handles multi-document batch uploads
type BatchUploadHandler struct {
	DB             *gorm.DB
	MinioStore     *storage.MinioClient
	TemporalClient client.Client
	TaskQueue      string
}

type batchResult struct {
	JobID      string `json:"job_id"`
	Filename   string `json:"filename"`
	Status     string `json:"status"`
	WorkflowID string `json:"workflow_id,omitempty"`
	Error      string `json:"error,omitempty"`
}

// Handle processes a batch of uploaded documents (up to 10,000)
// All user options (output_formats, prompt, coordinates, etc.) apply to every file.
func (h *BatchUploadHandler) Handle(c *gin.Context) {
	form, err := c.MultipartForm()
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid multipart form"})
		return
	}

	files := form.File["documents"]
	if len(files) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "No documents provided. Use field name 'documents'"})
		return
	}
	if len(files) > 10000 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Maximum 10,000 files per batch"})
		return
	}

	// Parse options from form (same params as single upload)
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
	webhookURL := c.DefaultPostForm("webhook_url", "")

	// Validate formats
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
				})
				return
			}
		}
	}

	batchID := uuid.New().String()
	log.Printf("📦 Batch %s: %d files, formats=%s", batchID, len(files), outputFormats)

	// Options map applied to every file in batch
	options := map[string]interface{}{
		"prompt":                  customPrompt,
		"include_coordinates":     includeCoordinates,
		"include_word_confidence": includeWordConfidence,
		"include_line_confidence": includeLineConfidence,
		"include_page_layout":     includePageLayout,
		"language":                language,
		"granularity":             granularity,
		"redact_pii":              redactPII,
		"enhance":                 enhance,
		"deskew":                  deskew,
		"max_pages":               maxPages,
		"temperature":             temperature,
		"max_tokens":              maxTokens,
		"webhook_url":             webhookURL,
	}

	results := make([]batchResult, len(files))
	var wg sync.WaitGroup
	semaphore := make(chan struct{}, 20) // Limit concurrent uploads

	for i := range files {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			semaphore <- struct{}{}
			defer func() { <-semaphore }()

			hdr := files[idx]
			file, err := hdr.Open()
			if err != nil {
				results[idx] = batchResult{Filename: hdr.Filename, Status: "FAILED", Error: "Failed to open file"}
				return
			}
			defer file.Close()

			jobID := uuid.New().String()
			objectName := fmt.Sprintf("raw/%s/%s/%s", batchID, jobID, hdr.Filename)

			storagePath, err := h.MinioStore.UploadFile(
				context.Background(), objectName, file, hdr.Size, hdr.Header.Get("Content-Type"),
			)
			if err != nil {
				results[idx] = batchResult{JobID: jobID, Filename: hdr.Filename, Status: "FAILED", Error: "Upload failed"}
				return
			}

			job := models.Job{
				ID: jobID, Filename: hdr.Filename, FileSize: hdr.Size,
				ContentType: hdr.Header.Get("Content-Type"), StoragePath: storagePath,
				Status: models.StatusUploaded, BatchID: batchID, OutputFormats: outputFormats,
			}
			if err := h.DB.Create(&job).Error; err != nil {
				results[idx] = batchResult{JobID: jobID, Filename: hdr.Filename, Status: "FAILED", Error: "DB insert failed"}
				return
			}

			we, err := h.TemporalClient.ExecuteWorkflow(
				context.Background(),
				client.StartWorkflowOptions{ID: fmt.Sprintf("doc-processing-%s", jobID), TaskQueue: h.TaskQueue},
				"DocumentProcessingWorkflow",
				map[string]interface{}{
					"job_id":         jobID,
					"batch_id":       batchID,
					"filename":       hdr.Filename,
					"storage_path":   storagePath,
					"content_type":   hdr.Header.Get("Content-Type"),
					"file_ext":       filepath.Ext(hdr.Filename),
					"output_formats": outputFormats,
					"options":        options,
				},
			)
			if err != nil {
				h.DB.Model(&job).Updates(map[string]interface{}{"status": models.StatusFailed, "error_message": err.Error()})
				results[idx] = batchResult{JobID: jobID, Filename: hdr.Filename, Status: "FAILED", Error: "Workflow start failed"}
				return
			}

			h.DB.Model(&job).Updates(map[string]interface{}{"workflow_id": we.GetID(), "run_id": we.GetRunID(), "status": models.StatusProcessing})
			results[idx] = batchResult{JobID: jobID, Filename: hdr.Filename, Status: "PROCESSING", WorkflowID: we.GetID()}
		}(i)
	}

	wg.Wait()

	succeeded, failed := 0, 0
	for _, r := range results {
		if r.Status == "PROCESSING" {
			succeeded++
		} else {
			failed++
		}
	}

	c.JSON(http.StatusAccepted, gin.H{
		"batch_id":       batchID,
		"total":          len(files),
		"succeeded":      succeeded,
		"failed":         failed,
		"output_formats": outputFormats,
		"status_url":     fmt.Sprintf("/jobs/batch/%s", batchID),
		"jobs":           results,
	})
}
