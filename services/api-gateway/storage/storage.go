package storage

import (
	"context"
	"io"
)

// StorageClient is the common interface implemented by both MinioClient and
// LocalStorageClient. The api-gateway and temporal-worker use this interface
// so that the storage backend can be swapped based on the STORAGE_DRIVER env.
type StorageClient interface {
	UploadFile(ctx context.Context, objectName string, reader io.Reader, fileSize int64, contentType string) (string, error)
	DownloadFile(ctx context.Context, objectName string) (io.ReadCloser, error)
}
