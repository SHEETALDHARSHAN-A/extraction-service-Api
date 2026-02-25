package storage

import (
	"context"
	"fmt"
	"io"
	"log"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

type MinioClient struct {
	client *minio.Client
	bucket string
}

func NewMinioClient(endpoint, accessKey, secretKey, bucket string, useSSL bool) (*MinioClient, error) {
	client, err := minio.New(endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(accessKey, secretKey, ""),
		Secure: useSSL,
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create minio client: %w", err)
	}

	// Ensure bucket exists
	ctx := context.Background()
	exists, err := client.BucketExists(ctx, bucket)
	if err != nil {
		return nil, fmt.Errorf("failed to check bucket existence: %w", err)
	}
	if !exists {
		err = client.MakeBucket(ctx, bucket, minio.MakeBucketOptions{})
		if err != nil {
			return nil, fmt.Errorf("failed to create bucket %s: %w", bucket, err)
		}
		log.Printf("Created MinIO bucket: %s", bucket)
	}

	return &MinioClient{client: client, bucket: bucket}, nil
}

// UploadFile uploads a file to MinIO and returns the object path
func (m *MinioClient) UploadFile(ctx context.Context, objectName string, reader io.Reader, fileSize int64, contentType string) (string, error) {
	info, err := m.client.PutObject(ctx, m.bucket, objectName, reader, fileSize, minio.PutObjectOptions{
		ContentType: contentType,
	})
	if err != nil {
		return "", fmt.Errorf("failed to upload to minio: %w", err)
	}
	log.Printf("Uploaded %s (%d bytes) to %s/%s", objectName, info.Size, m.bucket, objectName)
	return fmt.Sprintf("%s/%s", m.bucket, objectName), nil
}

// DownloadFile retrieves a file from MinIO
func (m *MinioClient) DownloadFile(ctx context.Context, objectName string) (io.ReadCloser, error) {
	obj, err := m.client.GetObject(ctx, m.bucket, objectName, minio.GetObjectOptions{})
	if err != nil {
		return nil, fmt.Errorf("failed to get object from minio: %w", err)
	}
	return obj, nil
}

// GetPresignedURL generates a presigned URL for downloading a result
func (m *MinioClient) GetPresignedURL(ctx context.Context, objectName string) (string, error) {
	url, err := m.client.PresignedGetObject(ctx, m.bucket, objectName, 3600*1e9, nil) // 1 hour
	if err != nil {
		return "", fmt.Errorf("failed to generate presigned URL: %w", err)
	}
	return url.String(), nil
}
