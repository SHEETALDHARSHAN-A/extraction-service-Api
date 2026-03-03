package orchestrator

import (
	"context"
	"encoding/base64"
	"image"
	"image/color"
	"image/png"
	"bytes"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/user/idep/api-gateway/clients"
)

// MockPaddleOCRClient is a mock implementation of PaddleOCR client
type MockPaddleOCRClient struct {
	mock.Mock
}

func (m *MockPaddleOCRClient) DetectLayout(ctx context.Context, imageBase64 string, options map[string]interface{}) (*clients.DetectLayoutResponse, error) {
	args := m.Called(ctx, imageBase64, options)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*clients.DetectLayoutResponse), args.Error(1)
}

func (m *MockPaddleOCRClient) HealthCheck(ctx context.Context) error {
	args := m.Called(ctx)
	return args.Error(0)
}

// MockGLMOCRClient is a mock implementation of GLM-OCR client
type MockGLMOCRClient struct {
	mock.Mock
}

func (m *MockGLMOCRClient) ExtractRegionsBatch(ctx context.Context, regions []clients.RegionExtractionRequest, options map[string]interface{}) (*clients.BatchRegionExtractionResponse, error) {
	args := m.Called(ctx, regions, options)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*clients.BatchRegionExtractionResponse), args.Error(1)
}

func (m *MockGLMOCRClient) ExtractRegionsParallel(ctx context.Context, regions []clients.RegionExtractionRequest, options map[string]interface{}, maxParallel int) (*clients.BatchRegionExtractionResponse, error) {
	args := m.Called(ctx, regions, options, maxParallel)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*clients.BatchRegionExtractionResponse), args.Error(1)
}

func (m *MockGLMOCRClient) HealthCheck(ctx context.Context) error {
	args := m.Called(ctx)
	return args.Error(0)
}

// Helper function to create a test image
func createTestImage() string {
	img := image.NewRGBA(image.Rect(0, 0, 800, 600))
	// Fill with white
	for y := 0; y < 600; y++ {
		for x := 0; x < 800; x++ {
			img.Set(x, y, color.White)
		}
	}

	var buf bytes.Buffer
	png.Encode(&buf, img)
	return base64.StdEncoding.EncodeToString(buf.Bytes())
}

func TestProcessDocument_LayoutDetectionDisabled(t *testing.T) {
	mockPaddleOCR := new(MockPaddleOCRClient)
	mockGLMOCR := new(MockGLMOCRClient)

	orchestrator := NewOrchestrator(
		mockPaddleOCR,
		mockGLMOCR,
		nil,
		&OrchestratorConfig{
			EnableLayoutDetection: false,
			ParallelProcessing:    false,
		},
	)

	imageBase64 := createTestImage()
	options := map[string]interface{}{
		"enable_layout_detection": false,
	}

	// Mock GLM-OCR batch extraction
	mockGLMOCR.On("ExtractRegionsBatch", mock.Anything, mock.Anything, mock.Anything).Return(
		&clients.BatchRegionExtractionResponse{
			Results: []clients.RegionExtractionResult{
				{
					RegionID:   "region_0",
					Content:    "Test content",
					Confidence: 0.95,
				},
			},
			TotalProcessingTimeMs: 100,
		},
		nil,
	)

	result, err := orchestrator.ProcessDocument(context.Background(), imageBase64, options)

	assert.NoError(t, err)
	assert.NotNil(t, result)
	assert.Equal(t, "full-page", result.Mode)
	assert.Equal(t, 1, len(result.Pages))
	assert.Equal(t, 1, len(result.Pages[0].Elements))
	assert.Equal(t, "Test content", result.Pages[0].Elements[0].Content)

	mockGLMOCR.AssertExpectations(t)
}

func TestProcessDocument_LayoutDetectionEnabled(t *testing.T) {
	mockPaddleOCR := new(MockPaddleOCRClient)
	mockGLMOCR := new(MockGLMOCRClient)

	orchestrator := NewOrchestrator(
		mockPaddleOCR,
		mockGLMOCR,
		nil,
		&OrchestratorConfig{
			EnableLayoutDetection: true,
			ParallelProcessing:    false,
		},
	)

	imageBase64 := createTestImage()
	options := map[string]interface{}{
		"enable_layout_detection": true,
	}

	// Mock PaddleOCR layout detection
	mockPaddleOCR.On("DetectLayout", mock.Anything, mock.Anything, mock.Anything).Return(
		&clients.DetectLayoutResponse{
			Regions: []clients.Region{
				{
					Index:      0,
					Type:       "text",
					Bbox:       []float64{100, 100, 400, 200},
					Confidence: 0.9,
				},
				{
					Index:      1,
					Type:       "table",
					Bbox:       []float64{100, 250, 700, 500},
					Confidence: 0.85,
				},
			},
			PageDimensions: &clients.PageDimensions{
				Width:  800,
				Height: 600,
			},
			ProcessingTimeMs: 150,
		},
		nil,
	)

	// Mock GLM-OCR batch extraction
	mockGLMOCR.On("ExtractRegionsBatch", mock.Anything, mock.Anything, mock.Anything).Return(
		&clients.BatchRegionExtractionResponse{
			Results: []clients.RegionExtractionResult{
				{
					RegionID:   "region_0",
					Content:    "Text content",
					Confidence: 0.92,
				},
				{
					RegionID:   "region_1",
					Content:    "Table content",
					Confidence: 0.88,
				},
			},
			TotalProcessingTimeMs: 2500,
		},
		nil,
	)

	result, err := orchestrator.ProcessDocument(context.Background(), imageBase64, options)

	assert.NoError(t, err)
	assert.NotNil(t, result)
	assert.Equal(t, "two-stage", result.Mode)
	assert.Equal(t, 1, len(result.Pages))
	assert.Equal(t, 2, len(result.Pages[0].Elements))
	assert.Equal(t, "Text content", result.Pages[0].Elements[0].Content)
	assert.Equal(t, "Table content", result.Pages[0].Elements[1].Content)
	assert.GreaterOrEqual(t, result.Usage.LayoutDetectionMs, 0.0)
	assert.GreaterOrEqual(t, result.Usage.ContentExtractionMs, 0.0)

	mockPaddleOCR.AssertExpectations(t)
	mockGLMOCR.AssertExpectations(t)
}

func TestProcessDocument_LayoutDetectionFallback(t *testing.T) {
	mockPaddleOCR := new(MockPaddleOCRClient)
	mockGLMOCR := new(MockGLMOCRClient)

	orchestrator := NewOrchestrator(
		mockPaddleOCR,
		mockGLMOCR,
		nil,
		&OrchestratorConfig{
			EnableLayoutDetection: true,
			ParallelProcessing:    false,
		},
	)

	imageBase64 := createTestImage()
	options := map[string]interface{}{
		"enable_layout_detection": true,
	}

	// Mock PaddleOCR layout detection failure
	mockPaddleOCR.On("DetectLayout", mock.Anything, mock.Anything, mock.Anything).Return(
		nil,
		assert.AnError,
	)

	// Mock GLM-OCR batch extraction (fallback mode)
	mockGLMOCR.On("ExtractRegionsBatch", mock.Anything, mock.Anything, mock.Anything).Return(
		&clients.BatchRegionExtractionResponse{
			Results: []clients.RegionExtractionResult{
				{
					RegionID:   "region_0",
					Content:    "Fallback content",
					Confidence: 0.90,
				},
			},
			TotalProcessingTimeMs: 1500,
		},
		nil,
	)

	result, err := orchestrator.ProcessDocument(context.Background(), imageBase64, options)

	assert.NoError(t, err)
	assert.NotNil(t, result)
	assert.Equal(t, "full-page", result.Mode)
	assert.Equal(t, 1, len(result.Pages))
	assert.Equal(t, 1, len(result.Pages[0].Elements))

	mockPaddleOCR.AssertExpectations(t)
	mockGLMOCR.AssertExpectations(t)
}

func TestCropRegions(t *testing.T) {
	orchestrator := NewOrchestrator(nil, nil, nil, &OrchestratorConfig{})

	imageBase64 := createTestImage()

	regions := []clients.Region{
		{
			Index:      0,
			Type:       "text",
			Bbox:       []float64{100, 100, 400, 200},
			Confidence: 0.9,
		},
	}

	croppedRegions, err := orchestrator.cropRegions(imageBase64, regions, nil)

	assert.NoError(t, err)
	assert.Equal(t, 1, len(croppedRegions))
	assert.Equal(t, "region_0", croppedRegions[0].RegionID)
	assert.Equal(t, "text", croppedRegions[0].RegionType)
	assert.NotEmpty(t, croppedRegions[0].Image)
}

func TestCropRegions_InvalidBbox(t *testing.T) {
	orchestrator := NewOrchestrator(nil, nil, nil, &OrchestratorConfig{})

	imageBase64 := createTestImage()

	regions := []clients.Region{
		{
			Index:      0,
			Type:       "text",
			Bbox:       []float64{100, 100}, // Invalid bbox (only 2 values)
			Confidence: 0.9,
		},
	}

	croppedRegions, err := orchestrator.cropRegions(imageBase64, regions, nil)

	assert.NoError(t, err)
	assert.Equal(t, 0, len(croppedRegions)) // Invalid bbox should be skipped
}

func TestCropRegions_BboxOutsideImage(t *testing.T) {
	orchestrator := NewOrchestrator(nil, nil, nil, &OrchestratorConfig{})

	imageBase64 := createTestImage()

	regions := []clients.Region{
		{
			Index:      0,
			Type:       "text",
			Bbox:       []float64{-50, -50, 900, 700}, // Bbox outside image bounds
			Confidence: 0.9,
		},
	}

	croppedRegions, err := orchestrator.cropRegions(imageBase64, regions, nil)

	assert.NoError(t, err)
	assert.Equal(t, 1, len(croppedRegions))
	// Should be clamped to image bounds
}
