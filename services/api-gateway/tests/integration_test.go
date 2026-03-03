package tests

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"image"
	"image/color"
	"image/png"
	"io"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
	"github.com/user/idep/api-gateway/clients"
	"github.com/user/idep/api-gateway/orchestrator"
)

// Helper function to create a test image
func createTestImage() []byte {
	img := image.NewRGBA(image.Rect(0, 0, 800, 600))
	// Fill with white
	for y := 0; y < 600; y++ {
		for x := 0; x < 800; x++ {
			img.Set(x, y, color.White)
		}
	}

	var buf bytes.Buffer
	png.Encode(&buf, img)
	return buf.Bytes()
}

// MockPaddleOCRServer creates a mock PaddleOCR service
func MockPaddleOCRServer() *httptest.Server {
	router := gin.Default()

	router.POST("/detect-layout", func(c *gin.Context) {
		var request struct {
			Image   string                 `json:"image"`
			Options map[string]interface{} `json:"options"`
		}

		if err := c.BindJSON(&request); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		// Return mock layout detection response
		c.JSON(http.StatusOK, gin.H{
			"regions": []gin.H{
				{
					"index":      0,
					"type":       "text",
					"bbox":       []float64{100, 100, 400, 200},
					"confidence": 0.9,
				},
				{
					"index":      1,
					"type":       "table",
					"bbox":       []float64{100, 250, 700, 500},
					"confidence": 0.85,
				},
			},
			"page_dimensions": gin.H{
				"width":  800,
				"height": 600,
			},
			"processing_time_ms": 150,
			"model_version":      "PPStructureV3",
		})
	})

	router.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "healthy"})
	})

	return httptest.NewServer(router)
}

// MockGLMOCRServer creates a mock GLM-OCR service
func MockGLMOCRServer() *httptest.Server {
	router := gin.Default()

	router.POST("/extract-regions-batch", func(c *gin.Context) {
		var request struct {
			Regions []struct {
				RegionID   string `json:"region_id"`
				Image      string `json:"image"`
				RegionType string `json:"region_type"`
				Prompt     string `json:"prompt"`
			} `json:"regions"`
			Options map[string]interface{} `json:"options"`
		}

		if err := c.BindJSON(&request); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		// Return mock extraction results
		results := []gin.H{}
		for _, region := range request.Regions {
			results = append(results, gin.H{
				"region_id":   region.RegionID,
				"content":     "Extracted content for " + region.RegionType,
				"confidence":  0.92,
			})
		}

		c.JSON(http.StatusOK, gin.H{
			"results":                  results,
			"total_processing_time_ms": 2500,
		})
	})

	router.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "healthy"})
	})

	return httptest.NewServer(router)
}

func TestIntegration_TwoStagePipeline(t *testing.T) {
	// Start mock servers
	paddleOCRServer := MockPaddleOCRServer()
	defer paddleOCRServer.Close()

	glmOCRServer := MockGLMOCRServer()
	defer glmOCRServer.Close()

	// Create clients
	paddleOCRClient := clients.NewPaddleOCRClient(paddleOCRServer.URL, 30, 3, 5, 60)
	glmOCRClient := clients.NewGLMOCRClient(glmOCRServer.URL, 30, 3, 5, 60)

	// Create orchestrator
	orch := orchestrator.NewOrchestrator(
		paddleOCRClient,
		glmOCRClient,
		nil,
		&orchestrator.OrchestratorConfig{
			EnableLayoutDetection: true,
			CacheLayoutResults:    false,
			MaxParallelRegions:    5,
			ParallelProcessing:    false,
		},
	)

	// Create test image
	imageBytes := createTestImage()
	imageBase64 := base64.StdEncoding.EncodeToString(imageBytes)

	// Process document
	result, err := orch.ProcessDocument(context.Background(), imageBase64, map[string]interface{}{
		"enable_layout_detection": true,
	})

	// Assertions
	assert.NoError(t, err)
	assert.NotNil(t, result)
	assert.Equal(t, "two-stage", result.Mode)
	assert.Equal(t, 1, len(result.Pages))
	assert.Equal(t, 2, len(result.Pages[0].Elements))
	assert.Greater(t, result.Usage.LayoutDetectionMs, 0.0)
	assert.Greater(t, result.Usage.ContentExtractionMs, 0.0)
	assert.Equal(t, 2, result.Usage.RegionsProcessed)
}

func TestIntegration_FallbackMode(t *testing.T) {
	// Start only GLM-OCR server (PaddleOCR unavailable)
	glmOCRServer := MockGLMOCRServer()
	defer glmOCRServer.Close()

	// Create clients (PaddleOCR will fail)
	paddleOCRClient := clients.NewPaddleOCRClient("http://invalid-url:9999", 1, 1, 5, 60)
	glmOCRClient := clients.NewGLMOCRClient(glmOCRServer.URL, 30, 3, 5, 60)

	// Create orchestrator
	orch := orchestrator.NewOrchestrator(
		paddleOCRClient,
		glmOCRClient,
		nil,
		&orchestrator.OrchestratorConfig{
			EnableLayoutDetection: true,
			CacheLayoutResults:    false,
			MaxParallelRegions:    5,
			ParallelProcessing:    false,
		},
	)

	// Create test image
	imageBytes := createTestImage()
	imageBase64 := base64.StdEncoding.EncodeToString(imageBytes)

	// Process document (should fallback to full-page mode)
	result, err := orch.ProcessDocument(context.Background(), imageBase64, map[string]interface{}{
		"enable_layout_detection": true,
	})

	// Assertions
	assert.NoError(t, err)
	assert.NotNil(t, result)
	assert.Equal(t, "full-page", result.Mode)
	assert.Equal(t, 1, len(result.Pages))
	assert.Equal(t, 1, len(result.Pages[0].Elements))
	assert.Equal(t, 0.0, result.Usage.LayoutDetectionMs)
	assert.Greater(t, result.Usage.ContentExtractionMs, 0.0)
}

func TestIntegration_HealthChecks(t *testing.T) {
	// Start mock servers
	paddleOCRServer := MockPaddleOCRServer()
	defer paddleOCRServer.Close()

	glmOCRServer := MockGLMOCRServer()
	defer glmOCRServer.Close()

	// Create clients
	paddleOCRClient := clients.NewPaddleOCRClient(paddleOCRServer.URL, 30, 3, 5, 60)
	glmOCRClient := clients.NewGLMOCRClient(glmOCRServer.URL, 30, 3, 5, 60)

	// Test health checks
	err := paddleOCRClient.HealthCheck(context.Background())
	assert.NoError(t, err)

	err = glmOCRClient.HealthCheck(context.Background())
	assert.NoError(t, err)
}

func TestIntegration_CircuitBreaker(t *testing.T) {
	// Create client with low threshold
	paddleOCRClient := clients.NewPaddleOCRClient("http://invalid-url:9999", 1, 1, 2, 1)

	// First request should fail
	_, err := paddleOCRClient.DetectLayout(context.Background(), "test", map[string]interface{}{})
	assert.Error(t, err)

	// Second request should fail
	_, err = paddleOCRClient.DetectLayout(context.Background(), "test", map[string]interface{}{})
	assert.Error(t, err)

	// Third request should fail with circuit breaker open
	_, err = paddleOCRClient.DetectLayout(context.Background(), "test", map[string]interface{}{})
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "circuit breaker open")
}

func TestIntegration_MultipartUpload(t *testing.T) {
	// This test simulates the actual API Gateway upload endpoint
	router := gin.Default()

	// Mock upload handler
	router.POST("/jobs/upload", func(c *gin.Context) {
		file, header, err := c.Request.FormFile("document")
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "No document provided"})
			return
		}
		defer file.Close()

		// Read file
		fileBytes, err := io.ReadAll(file)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to read file"})
			return
		}

		// Parse options
		enableLayoutDetection := c.DefaultPostForm("enable_layout_detection", "false") == "true"

		c.JSON(http.StatusAccepted, gin.H{
			"job_id":                  "test-job-id",
			"filename":                header.Filename,
			"status":                  "PROCESSING",
			"file_size":               len(fileBytes),
			"enable_layout_detection": enableLayoutDetection,
		})
	})

	// Create test server
	server := httptest.NewServer(router)
	defer server.Close()

	// Create multipart form
	var buf bytes.Buffer
	writer := multipart.NewWriter(&buf)

	// Add file
	part, err := writer.CreateFormFile("document", "test.png")
	assert.NoError(t, err)
	_, err = part.Write(createTestImage())
	assert.NoError(t, err)

	// Add options
	writer.WriteField("enable_layout_detection", "true")
	writer.WriteField("min_confidence", "0.5")

	writer.Close()

	// Make request
	req, err := http.NewRequest("POST", server.URL+"/jobs/upload", &buf)
	assert.NoError(t, err)
	req.Header.Set("Content-Type", writer.FormDataContentType())

	client := &http.Client{}
	resp, err := client.Do(req)
	assert.NoError(t, err)
	defer resp.Body.Close()

	// Check response
	assert.Equal(t, http.StatusAccepted, resp.StatusCode)

	var result map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&result)
	assert.NoError(t, err)
	assert.Equal(t, "test-job-id", result["job_id"])
	assert.Equal(t, true, result["enable_layout_detection"])
}
