package clients

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// PaddleOCRClient handles communication with the PaddleOCR service
type PaddleOCRClient struct {
	baseURL        string
	httpClient     *http.Client
	retryAttempts  int
	circuitBreaker *CircuitBreaker
}

// Region represents a detected document region
type Region struct {
	Index      int       `json:"index"`
	Type       string    `json:"type"`
	Bbox       []float64 `json:"bbox"`
	Confidence float64   `json:"confidence"`
}

// PageDimensions represents page dimensions
type PageDimensions struct {
	Width  int `json:"width"`
	Height int `json:"height"`
}

// DetectLayoutRequest represents the request to PaddleOCR service
type DetectLayoutRequest struct {
	Image   string                 `json:"image"`
	Options map[string]interface{} `json:"options,omitempty"`
}

// DetectLayoutResponse represents the response from PaddleOCR service
type DetectLayoutResponse struct {
	Regions          []Region        `json:"regions"`
	PageDimensions   *PageDimensions `json:"page_dimensions,omitempty"`
	ProcessingTimeMs float64         `json:"processing_time_ms"`
	ModelVersion     string          `json:"model_version"`
}

// NewPaddleOCRClient creates a new PaddleOCR service client
func NewPaddleOCRClient(baseURL string, timeout int, retryAttempts int, cbThreshold int, cbTimeout int) *PaddleOCRClient {
	return &PaddleOCRClient{
		baseURL: baseURL,
		httpClient: &http.Client{
			Timeout: time.Duration(timeout) * time.Second,
		},
		retryAttempts:  retryAttempts,
		circuitBreaker: NewCircuitBreaker(cbThreshold, time.Duration(cbTimeout)*time.Second),
	}
}

// DetectLayout calls the PaddleOCR service to detect document layout
func (c *PaddleOCRClient) DetectLayout(ctx context.Context, imageBase64 string, options map[string]interface{}) (*DetectLayoutResponse, error) {
	// Check circuit breaker
	if !c.circuitBreaker.CanExecute() {
		return nil, fmt.Errorf("circuit breaker open for PaddleOCR service")
	}

	request := DetectLayoutRequest{
		Image:   imageBase64,
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

// makeRequest performs the actual HTTP request
func (c *PaddleOCRClient) makeRequest(ctx context.Context, request DetectLayoutRequest) (*DetectLayoutResponse, error) {
	jsonData, err := json.Marshal(request)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, "POST", c.baseURL+"/detect-layout", bytes.NewBuffer(jsonData))
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
		return nil, fmt.Errorf("PaddleOCR service returned status %d: %s", resp.StatusCode, string(body))
	}

	var response DetectLayoutResponse
	if err := json.Unmarshal(body, &response); err != nil {
		return nil, fmt.Errorf("failed to unmarshal response: %w", err)
	}

	return &response, nil
}

// HealthCheck checks if the PaddleOCR service is healthy
func (c *PaddleOCRClient) HealthCheck(ctx context.Context) error {
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
