package models

import (
	"time"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

// JobStatus enum
type JobStatus string

const (
	StatusPending    JobStatus = "PENDING"
	StatusUploaded   JobStatus = "UPLOADED"
	StatusProcessing JobStatus = "PROCESSING"
	StatusCompleted  JobStatus = "COMPLETED"
	StatusFailed     JobStatus = "FAILED"
)

// Job represents a document extraction job persisted in PostgreSQL
type Job struct {
	ID            string    `json:"id" gorm:"primaryKey;type:varchar(36)"`
	Filename      string    `json:"filename" gorm:"type:varchar(512);not null"`
	FileSize      int64     `json:"file_size"`
	ContentType   string    `json:"content_type" gorm:"type:varchar(128)"`
	StoragePath   string    `json:"storage_path" gorm:"type:varchar(1024)"`
	Status        JobStatus `json:"status" gorm:"type:varchar(32);default:'PENDING'"`
	WorkflowID    string    `json:"workflow_id" gorm:"type:varchar(256)"`
	RunID         string    `json:"run_id" gorm:"type:varchar(256)"`
	BatchID       string    `json:"batch_id" gorm:"type:varchar(36);index"`
	ResultPath    string    `json:"result_path" gorm:"type:varchar(1024)"`
	ErrorMessage  string    `json:"error_message" gorm:"type:text"`
	PageCount     int       `json:"page_count"`
	Confidence    float64   `json:"confidence"`
	OutputFormats string    `json:"output_formats" gorm:"type:varchar(256);default:'text'"`
	CreatedAt     time.Time `json:"created_at"`
	UpdatedAt     time.Time `json:"updated_at"`
}

// BeforeCreate hook to auto-generate UUID
func (j *Job) BeforeCreate(tx *gorm.DB) error {
	if j.ID == "" {
		j.ID = uuid.New().String()
	}
	j.CreatedAt = time.Now()
	j.UpdatedAt = time.Now()
	return nil
}
