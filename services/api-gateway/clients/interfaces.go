package clients

import "context"

// PaddleOCRClientInterface defines the interface for PaddleOCR client
type PaddleOCRClientInterface interface {
	DetectLayout(ctx context.Context, imageBase64 string, options map[string]interface{}) (*DetectLayoutResponse, error)
	HealthCheck(ctx context.Context) error
}

// GLMOCRClientInterface defines the interface for GLM-OCR client
type GLMOCRClientInterface interface {
	ExtractRegionsBatch(ctx context.Context, regions []RegionExtractionRequest, options map[string]interface{}) (*BatchRegionExtractionResponse, error)
	ExtractRegionsParallel(ctx context.Context, regions []RegionExtractionRequest, options map[string]interface{}, maxParallel int) (*BatchRegionExtractionResponse, error)
	HealthCheck(ctx context.Context) error
}
