package clients

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"sync"
	"time"
)

// GLMOCRClient handles communication with the GLM-OCR service
type GLMOCRClient struct {
	baseURL        string
	httpClient     *http.Client
	retryAttempts  int
	circuitBreaker *CircuitBreaker
}

// RegionExtractionRequest represents a single region extraction request
type RegionExtractionRequest struct {
	RegionID   string                 `json:"region_id"`
	Image      string                 `json:"image"`
	RegionType string                 `json:"region_type"`
	Prompt     string                 `json:"prompt"`
	Options    map[string]interface{} `json:"options,omitempty"`
}

// BatchRegionExtractionRequest represents a batch region extraction request
type BatchRegionExtractionRequest struct {
	Regions []RegionExtractionRequest `json:"regions"`
	Options map[string]interface{}    `json:"options,omitempty"`
}

// RegionExtractionResult represents the result of a single region extraction
type RegionExtractionResult struct {
	RegionID         string  `json:"region_id"`
	Content          string  `json:"content"`
	Confidence       float64 `json:"confidence"`
	ProcessingTimeMs float64 `json:"processing_time_ms,omitempty"`
	Error            string  `json:"error,omitempty"`
}

// BatchRegionExtractionResponse represents the response from batch extraction
type BatchRegionExtractionResponse struct {
	Results              []RegionExtractionResult `json:"results"`
	TotalProcessingTimeMs float64                  `json:"total_processing_time_ms"`
}

// NewGLMOCRClient creates a new GLM-OCR service client
func NewGLMOCRClient(baseURL string, timeout int, retryAttempts int, cbThreshold int, cbTimeout int) *GLMOCRClient {
	return &GLMOCRClient{
		baseURL: baseURL,
		httpClient: &http.Client{
			Timeout: time.Duration(timeout) * time.Second,
		},
		retryAttempts:  retryAttempts,
		circuitBreaker: NewCircuitBreaker(cbThreshold, time.Duration(cbTimeout)*time.Second),
	}
}

// ExtractRegionsBatch calls the GLM-OCR service to extract content from multiple regions
func (c *GLMOCRClient) ExtractRegionsBatch(ctx context.Context, regions []RegionExtractionRequest, options map[string]interface{}) (*BatchRegionExtractionResponse, error) {
	// Check circuit breaker
	if !c.circuitBreaker.CanExecute() {
		return nil, fmt.Errorf("circuit breaker open for GLM-OCR service")
	}

	request := BatchRegionExtractionRequest{
		Regions: regions,
		Options: options,
	}

	var lastErr error
	for attempt := 0; attempt < c.retryAttempts; attempt++ {
		if attempt > 0 {
			// Exponential backoff
			backoff := time.Duration(1<<uint(attempt-1)) * time.Second
			select {
			case <-ctx.Done():
				return nil, ctx.Err()
			case <-time.After(backoff):
			}
		}

		response, err := c.makeRequest(ctx, request)
		if err == nil {
			c.circuitBreaker.RecordSuccess()
			return response, nil
		}

		lastErr = err
	}

	c.circuitBreaker.RecordFailure()
	return nil, fmt.Errorf("failed after %d attempts: %w", c.retryAttempts, lastErr)
}

// ExtractRegionsParallel extracts content from regions in parallel batches
func (c *GLMOCRClient) ExtractRegionsParallel(ctx context.Context, regions []RegionExtractionRequest, options map[string]interface{}, maxParallel int) (*BatchRegionExtractionResponse, error) {
	if len(regions) == 0 {
		return &BatchRegionExtractionResponse{
			Results:              []RegionExtractionResult{},
			TotalProcessingTimeMs: 0,
		}, nil
	}

	// If regions fit in one batch, use regular batch extraction
	if len(regions) <= maxParallel {
		return c.ExtractRegionsBatch(ctx, regions, options)
	}

	// Split into batches and process in parallel
	var wg sync.WaitGroup
	resultsChan := make(chan []RegionExtractionResult, (len(regions)+maxParallel-1)/maxParallel)
	errorsChan := make(chan error, (len(regions)+maxParallel-1)/maxParallel)

	startTime := time.Now()

	for i := 0; i < len(regions); i += maxParallel {
		end := i + maxParallel
		if end > len(regions) {
			end = len(regions)
		}

		batch := regions[i:end]
		wg.Add(1)

		go func(batchRegions []RegionExtractionRequest) {
			defer wg.Done()

			response, err := c.ExtractRegionsBatch(ctx, batchRegions, options)
			if err != nil {
				errorsChan <- err
				return
			}

			resultsChan <- response.Results
		}(batch)
	}

	wg.Wait()
	close(resultsChan)
	close(errorsChan)

	// Check for errors
	if len(errorsChan) > 0 {
		return nil, <-errorsChan
	}

	// Combine results
	var allResults []RegionExtractionResult
	for results := range resultsChan {
		allResults = append(allResults, results...)
	}

	totalTime := time.Since(startTime).Milliseconds()

	return &BatchRegionExtractionResponse{
		Results:              allResults,
		TotalProcessingTimeMs: float64(totalTime),
	}, nil
}

// makeRequest performs the actual HTTP request
func (c *GLMOCRClient) makeRequest(ctx context.Context, request BatchRegionExtractionRequest) (*BatchRegionExtractionResponse, error) {
	jsonData, err := json.Marshal(request)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, "POST", c.baseURL+"/extract-regions-batch", bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("GLM-OCR service returned status %d: %s", resp.StatusCode, string(body))
	}

	var response BatchRegionExtractionResponse
	if err := json.Unmarshal(body, &response); err != nil {
		return nil, fmt.Errorf("failed to unmarshal response: %w", err)
	}

	return &response, nil
}

// HealthCheck checks if the GLM-OCR service is healthy
func (c *GLMOCRClient) HealthCheck(ctx context.Context) error {
	req, err := http.NewRequestWithContext(ctx, "GET", c.baseURL+"/health", nil)
	if err != nil {
		return fmt.Errorf("failed to create health check request: %w", err)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("health check failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("health check returned status %d", resp.StatusCode)
	}

	return nil
}

// GetPromptForRegionType returns the appropriate prompt for a region type
func GetPromptForRegionType(regionType string, customPrompt string) string {
	if customPrompt != "" {
		return customPrompt
	}

	promptMap := map[string]string{
		"text":    "Text Recognition:",
		"table":   "Table Recognition:",
		"formula": "Formula Recognition:",
		"title":   "Title Recognition:",
		"figure":  "Figure Recognition:",
	}

	if prompt, ok := promptMap[regionType]; ok {
		return prompt
	}

	return "Text Recognition:"
}
