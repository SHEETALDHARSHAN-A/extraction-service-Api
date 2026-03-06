package clients

import (
	"bytes"
	"compress/gzip"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
)

const gzipRequestThresholdBytes = 32 * 1024

func doJSONRequest(ctx context.Context, httpClient *http.Client, method, url, serviceName string, requestPayload interface{}, responsePayload interface{}) error {
	jsonData, err := json.Marshal(requestPayload)
	if err != nil {
		return fmt.Errorf("failed to marshal request: %w", err)
	}

	requestBody := io.Reader(bytes.NewReader(jsonData))
	isCompressed := len(jsonData) >= gzipRequestThresholdBytes
	if isCompressed {
		compressed, err := gzipCompress(jsonData)
		if err != nil {
			return fmt.Errorf("failed to gzip request: %w", err)
		}
		requestBody = bytes.NewReader(compressed)
	}

	req, err := http.NewRequestWithContext(ctx, method, url, requestBody)
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept-Encoding", "gzip")
	if isCompressed {
		req.Header.Set("Content-Encoding", "gzip")
	}

	resp, err := httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	body, err := readResponseBody(resp)
	if err != nil {
		return fmt.Errorf("failed to read response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("%s returned status %d: %s", serviceName, resp.StatusCode, string(body))
	}

	if err := json.Unmarshal(body, responsePayload); err != nil {
		return fmt.Errorf("failed to unmarshal response: %w", err)
	}

	return nil
}

func readResponseBody(resp *http.Response) ([]byte, error) {
	reader := io.Reader(resp.Body)
	if strings.Contains(strings.ToLower(resp.Header.Get("Content-Encoding")), "gzip") {
		gzipReader, err := gzip.NewReader(resp.Body)
		if err != nil {
			return nil, err
		}
		defer gzipReader.Close()
		reader = gzipReader
	}
	return io.ReadAll(reader)
}

func gzipCompress(content []byte) ([]byte, error) {
	var buf bytes.Buffer
	writer := gzip.NewWriter(&buf)
	if _, err := writer.Write(content); err != nil {
		writer.Close()
		return nil, err
	}
	if err := writer.Close(); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}
