package storage

import (
	"context"
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
)

// LocalStorageClient stores files on the local filesystem,
// mirroring the MinioClient API for Docker-free development.
type LocalStorageClient struct {
	root   string // e.g. ".local/data/storage"
	bucket string // virtual bucket name used as a sub-directory
}

// NewLocalStorageClient creates a local-filesystem storage backend.
func NewLocalStorageClient(rootDir, bucket string) (*LocalStorageClient, error) {
	bucketDir := filepath.Join(rootDir, bucket)
	if err := os.MkdirAll(bucketDir, 0o755); err != nil {
		return nil, fmt.Errorf("failed to create local storage directory %s: %w", bucketDir, err)
	}
	log.Printf("✅ Local storage initialized at %s", bucketDir)
	return &LocalStorageClient{root: rootDir, bucket: bucket}, nil
}

// UploadFile writes the content to a local file and returns the storage path.
func (l *LocalStorageClient) UploadFile(ctx context.Context, objectName string, reader io.Reader, fileSize int64, contentType string) (string, error) {
	fullPath := filepath.Join(l.root, l.bucket, filepath.FromSlash(objectName))

	if err := os.MkdirAll(filepath.Dir(fullPath), 0o755); err != nil {
		return "", fmt.Errorf("failed to create directories for %s: %w", fullPath, err)
	}

	f, err := os.Create(fullPath)
	if err != nil {
		return "", fmt.Errorf("failed to create local file %s: %w", fullPath, err)
	}
	defer f.Close()

	n, err := io.Copy(f, reader)
	if err != nil {
		return "", fmt.Errorf("failed to write local file %s: %w", fullPath, err)
	}

	storagePath := fmt.Sprintf("%s/%s", l.bucket, objectName)
	log.Printf("Uploaded %s (%d bytes) to local: %s", objectName, n, fullPath)
	return storagePath, nil
}

// DownloadFile returns an io.ReadCloser for a locally stored object.
func (l *LocalStorageClient) DownloadFile(ctx context.Context, objectName string) (io.ReadCloser, error) {
	// objectName may include the bucket prefix – strip it.
	clean := objectName
	if len(l.bucket) > 0 {
		prefix := l.bucket + "/"
		if len(clean) > len(prefix) && clean[:len(prefix)] == prefix {
			clean = clean[len(prefix):]
		}
	}

	fullPath := filepath.Join(l.root, l.bucket, filepath.FromSlash(clean))
	f, err := os.Open(fullPath)
	if err != nil {
		return nil, fmt.Errorf("failed to open local file %s: %w", fullPath, err)
	}
	return f, nil
}
