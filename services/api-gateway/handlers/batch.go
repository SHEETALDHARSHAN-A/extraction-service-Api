package handlers

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"path/filepath"
	"sync"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/user/idep/api-gateway/models"
	"github.com/user/idep/api-gateway/storage"
	"go.temporal.io/sdk/client"
	"gorm.io/gorm"
)

// BatchUploadHandler handles multi-document batch uploads (FR-1.3)
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

	batchID := uuid.New().String()
	log.Printf("📦 Batch upload started: %s (%d files)", batchID, len(files))

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
				Status: models.StatusUploaded, BatchID: batchID,
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
					"job_id": jobID, "batch_id": batchID, "filename": hdr.Filename,
					"storage_path": storagePath, "content_type": hdr.Header.Get("Content-Type"),
					"file_ext": filepath.Ext(hdr.Filename),
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
		"batch_id": batchID, "total": len(files),
		"succeeded": succeeded, "failed": failed, "jobs": results,
	})
}
