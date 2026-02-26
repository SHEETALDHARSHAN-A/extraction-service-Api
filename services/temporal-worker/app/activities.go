package app

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
	"github.com/user/idep/shared/proto/postprocessing"
	"github.com/user/idep/shared/proto/preprocessing"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

// Activities holds connections to downstream services
type Activities struct {
	PreprocessingHost  string
	PostprocessingHost string
	TritonHost         string
	TritonGRPCPort     string
	TritonHTTPPort     string
	MinioEndpoint      string
	MinioAccessKey     string
	MinioSecretKey     string
	MinioBucket        string
}

// ─── Data Transfer Objects ───

// ExtractionOptions carries all user-configurable parameters through the pipeline
type ExtractionOptions struct {
	OutputFormats         string `json:"output_formats"`
	Prompt                string `json:"prompt"`
	IncludeCoordinates    bool   `json:"include_coordinates"`
	IncludeWordConfidence bool   `json:"include_word_confidence"`
	IncludeLineConfidence bool   `json:"include_line_confidence"`
	IncludePageLayout     bool   `json:"include_page_layout"`
	Language              string `json:"language"`
	Granularity           string `json:"granularity"`
	RedactPII             bool   `json:"redact_pii"`
	Enhance               bool   `json:"enhance"`
	Deskew                bool   `json:"deskew"`
	MaxPages              string `json:"max_pages"`
	Temperature           string `json:"temperature"`
	MaxTokens             string `json:"max_tokens"`
}

// PreprocessOutput from the preprocessing activity
type PreprocessOutput struct {
	JobID      string            `json:"job_id"`
	ImagePaths []string          `json:"image_paths"`
	PageCount  int               `json:"page_count"`
	Options    ExtractionOptions `json:"options"`
}

// ExtractionOutput from the Triton inference activity
type ExtractionOutput struct {
	JobID      string            `json:"job_id"`
	RawContent string            `json:"raw_content"`
	Confidence float64           `json:"confidence"`
	PageCount  int               `json:"page_count"`
	Options    ExtractionOptions `json:"options"`
}

// FinalOutput from the post-processing activity
type FinalOutput struct {
	JobID             string  `json:"job_id"`
	StructuredContent string  `json:"structured_content"`
	Confidence        float64 `json:"confidence"`
	ResultPath        string  `json:"result_path"`
	PageCount         int     `json:"page_count"`
}

// parseOptions extracts ExtractionOptions from the workflow input map
func parseOptions(input map[string]interface{}) ExtractionOptions {
	opts := ExtractionOptions{
		OutputFormats: "text",
		Language:      "auto",
		Granularity:   "block",
		Enhance:       true,
		Deskew:        true,
		MaxPages:      "0",
		Temperature:   "0.0",
		MaxTokens:     "4096",
	}

	if v, ok := input["output_formats"].(string); ok {
		opts.OutputFormats = v
	}

	if optMap, ok := input["options"].(map[string]interface{}); ok {
		if v, ok := optMap["prompt"].(string); ok {
			opts.Prompt = v
		}
		if v, ok := optMap["include_coordinates"].(bool); ok {
			opts.IncludeCoordinates = v
		}
		if v, ok := optMap["include_word_confidence"].(bool); ok {
			opts.IncludeWordConfidence = v
		}
		if v, ok := optMap["include_line_confidence"].(bool); ok {
			opts.IncludeLineConfidence = v
		}
		if v, ok := optMap["include_page_layout"].(bool); ok {
			opts.IncludePageLayout = v
		}
		if v, ok := optMap["language"].(string); ok {
			opts.Language = v
		}
		if v, ok := optMap["granularity"].(string); ok {
			opts.Granularity = v
		}
		if v, ok := optMap["redact_pii"].(bool); ok {
			opts.RedactPII = v
		}
		if v, ok := optMap["enhance"].(bool); ok {
			opts.Enhance = v
		}
		if v, ok := optMap["deskew"].(bool); ok {
			opts.Deskew = v
		}
		if v, ok := optMap["max_pages"].(string); ok {
			opts.MaxPages = v
		}
		if v, ok := optMap["temperature"].(string); ok {
			opts.Temperature = v
		}
		if v, ok := optMap["max_tokens"].(string); ok {
			opts.MaxTokens = v
		}
	}
	return opts
}

// ─── Activity 1: Preprocess ───

func (a *Activities) Preprocess(ctx context.Context, input map[string]interface{}) (*PreprocessOutput, error) {
	jobID := input["job_id"].(string)
	storagePath := input["storage_path"].(string)
	opts := parseOptions(input)

	log.Printf("🔧 [Preprocess] job=%s enhance=%v deskew=%v", jobID, opts.Enhance, opts.Deskew)

	// Fast path for image uploads: download original file from MinIO into shared temp dir.
	// This bypasses local placeholder protobuf stubs that return simulated paths.
	ext := strings.ToLower(filepath.Ext(storagePath))
	if ext == ".png" || ext == ".jpg" || ext == ".jpeg" || ext == ".bmp" || ext == ".webp" || ext == ".tif" || ext == ".tiff" {
		localImagePath, err := a.downloadSourceFromMinIO(ctx, storagePath, jobID)
		if err != nil {
			return nil, fmt.Errorf("failed to prepare image from storage: %w", err)
		}

		return &PreprocessOutput{
			JobID:      jobID,
			ImagePaths: []string{localImagePath},
			PageCount:  1,
			Options:    opts,
		}, nil
	}

	conn, err := grpc.NewClient(a.PreprocessingHost,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to preprocessing: %w", err)
	}
	defer conn.Close()

	client := preprocessing.NewPreprocessingServiceClient(conn)
	ctx, cancel := context.WithTimeout(ctx, 5*time.Minute)
	defer cancel()

	resp, err := client.Preprocess(ctx, &preprocessing.PreprocessRequest{
		FilePath: storagePath,
		JobId:    jobID,
		Deskew:   opts.Deskew,
		Denoise:  opts.Enhance,
	})
	if err != nil {
		return nil, fmt.Errorf("preprocessing call failed: %w", err)
	}

	if resp.Status != "success" {
		return nil, fmt.Errorf("preprocessing failed: %s", resp.Error)
	}

	log.Printf("✅ [Preprocess] %d pages for job %s", len(resp.ImagePaths), jobID)

	return &PreprocessOutput{
		JobID:      jobID,
		ImagePaths: resp.ImagePaths,
		PageCount:  len(resp.ImagePaths),
		Options:    opts,
	}, nil
}

func (a *Activities) downloadSourceFromMinIO(ctx context.Context, storagePath, jobID string) (string, error) {
	minioClient, err := minio.New(a.MinioEndpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(a.MinioAccessKey, a.MinioSecretKey, ""),
		Secure: false,
	})
	if err != nil {
		return "", fmt.Errorf("minio client init failed: %w", err)
	}

	objectPath := strings.TrimPrefix(storagePath, a.MinioBucket+"/")
	objectPath = strings.TrimPrefix(objectPath, "/")

	obj, err := minioClient.GetObject(ctx, a.MinioBucket, objectPath, minio.GetObjectOptions{})
	if err != nil {
		return "", fmt.Errorf("minio get object failed: %w", err)
	}
	defer obj.Close()

	jobDir := filepath.Join("/tmp/idep", jobID)
	if err := os.MkdirAll(jobDir, 0o755); err != nil {
		return "", fmt.Errorf("mkdir failed: %w", err)
	}

	localPath := filepath.Join(jobDir, filepath.Base(objectPath))
	f, err := os.Create(localPath)
	if err != nil {
		return "", fmt.Errorf("create local file failed: %w", err)
	}
	defer f.Close()

	if _, err := io.Copy(f, obj); err != nil {
		return "", fmt.Errorf("copy object to local file failed: %w", err)
	}

	return localPath, nil
}

// ─── Activity 2: CallTriton ───

// buildPrompt constructs the GLM prompt based on options
func buildPrompt(opts ExtractionOptions) string {
	// Custom prompt takes priority
	if opts.Prompt != "" {
		prompt := opts.Prompt
		if opts.IncludeCoordinates {
			prompt += "\n\nFor each text element, provide its bounding box [x, y, width, height] in pixels and a confidence score (0.0-1.0)."
		}
		if opts.IncludeWordConfidence {
			prompt += "\n\nFor each word, provide a confidence score (0.0-1.0)."
		}
		if opts.Language != "auto" {
			prompt += fmt.Sprintf("\n\nDocument language: %s", opts.Language)
		}
		return prompt
	}

	// Prebuilt format prompts
	prompts := map[string]string{
		"text":       "Extract ALL text from this document image preserving layout and reading order.",
		"json":       "Extract all information as structured JSON with document_type, fields, and line_items.",
		"markdown":   "Convert this document to Markdown with headings, tables, and bold labels.",
		"table":      "Detect and extract ALL tables. Return as JSON array with headers and rows.",
		"key_value":  "Extract all key-value pairs as a flat JSON object.",
		"structured": "Comprehensive extraction: document_type, raw_text, fields, tables, handwritten_sections as JSON.",
	}

	formats := strings.Split(opts.OutputFormats, ",")
	if len(formats) == 1 {
		if p, ok := prompts[strings.TrimSpace(formats[0])]; ok {
			prompt := p
			if opts.IncludeCoordinates {
				prompt += " Include bounding box [x,y,w,h] and confidence for every element."
			}
			if opts.IncludeWordConfidence {
				prompt += " Include per-word confidence scores."
			}
			return prompt
		}
	}

	// Multi-format
	parts := []string{"Analyze this document and provide:\n"}
	for i, f := range formats {
		f = strings.TrimSpace(f)
		if p, ok := prompts[f]; ok {
			parts = append(parts, fmt.Sprintf("%d. %s: %s", i+1, strings.ToUpper(f), p))
		}
	}
	parts = append(parts, "\nReturn as JSON with a key for each requested format.")

	if opts.IncludeCoordinates {
		parts = append(parts, "Include bounding box [x,y,w,h] and confidence for every element.")
	}
	if opts.IncludeWordConfidence {
		parts = append(parts, "Include per-word confidence scores.")
	}

	return strings.Join(parts, "\n")
}

func (a *Activities) CallTriton(ctx context.Context, input *PreprocessOutput) (*ExtractionOutput, error) {
	log.Printf("🧠 [Triton] job=%s pages=%d formats=%s", input.JobID, input.PageCount, input.Options.OutputFormats)

	// Build the prompt from user options
	prompt := buildPrompt(input.Options)

	// Build options JSON for Triton
	optionsJSON, _ := json.Marshal(map[string]interface{}{
		"include_coordinates":     input.Options.IncludeCoordinates,
		"include_word_confidence": input.Options.IncludeWordConfidence,
		"include_line_confidence": input.Options.IncludeLineConfidence,
		"include_page_layout":     input.Options.IncludePageLayout,
		"language":                input.Options.Language,
		"granularity":             input.Options.Granularity,
		"temperature":             input.Options.Temperature,
		"max_tokens":              input.Options.MaxTokens,
	})

	log.Printf("   Prompt: %.80s...", prompt)
	log.Printf("   Options: %s", string(optionsJSON))

	var allContent string
	var totalConfidence float64

	for i, imgPath := range input.ImagePaths {
		if !filepath.IsAbs(imgPath) {
			imgPath = filepath.Join("/tmp/idep", imgPath)
		}
		pageContent, pageConfidence, err := a.callTritonHTTP(ctx, imgPath, prompt, string(optionsJSON))
		if err != nil {
			return nil, fmt.Errorf("triton inference failed for page %d (%s): %w", i+1, imgPath, err)
		}
		if i > 0 {
			allContent += "\n---PAGE_BREAK---\n"
		}
		allContent += pageContent
		totalConfidence += pageConfidence
	}

	avgConfidence := totalConfidence / float64(len(input.ImagePaths))
	log.Printf("✅ [Triton] job=%s confidence=%.2f", input.JobID, avgConfidence)

	return &ExtractionOutput{
		JobID:      input.JobID,
		RawContent: allContent,
		Confidence: avgConfidence,
		PageCount:  input.PageCount,
		Options:    input.Options,
	}, nil
}

func (a *Activities) callTritonHTTP(ctx context.Context, imagePath, prompt, options string) (string, float64, error) {
	tritonURL := fmt.Sprintf("http://%s:%s/v2/models/glm_ocr/infer", a.TritonHost, a.TritonHTTPPort)

	payload := map[string]interface{}{
		"inputs": []map[string]interface{}{
			{
				"name":     "images",
				"shape":    []int{1, 1},
				"datatype": "BYTES",
				"data":     []string{imagePath},
			},
			{
				"name":     "prompt",
				"shape":    []int{1, 1},
				"datatype": "BYTES",
				"data":     []string{prompt},
			},
			{
				"name":     "options",
				"shape":    []int{1, 1},
				"datatype": "BYTES",
				"data":     []string{options},
			},
		},
	}

	bodyBytes, err := json.Marshal(payload)
	if err != nil {
		return "", 0, err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, tritonURL, bytes.NewReader(bodyBytes))
	if err != nil {
		return "", 0, err
	}
	req.Header.Set("Content-Type", "application/json")

	httpClient := &http.Client{Timeout: 10 * time.Minute}
	resp, err := httpClient.Do(req)
	if err != nil {
		return "", 0, err
	}
	defer resp.Body.Close()

	respBody, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 300 {
		return "", 0, fmt.Errorf("triton http %d: %s", resp.StatusCode, string(respBody))
	}

	var inferResp struct {
		Outputs []struct {
			Name string          `json:"name"`
			Data json.RawMessage `json:"data"`
		} `json:"outputs"`
	}
	if err := json.Unmarshal(respBody, &inferResp); err != nil {
		return "", 0, err
	}

	generatedText := ""
	confidence := 0.0

	for _, out := range inferResp.Outputs {
		switch out.Name {
		case "generated_text":
			var arr []string
			if err := json.Unmarshal(out.Data, &arr); err == nil && len(arr) > 0 {
				generatedText = arr[0]
			}
		case "confidence":
			var arr []float64
			if err := json.Unmarshal(out.Data, &arr); err == nil && len(arr) > 0 {
				confidence = arr[0]
			}
		}
	}

	if generatedText == "" {
		return "", 0, fmt.Errorf("missing generated_text in Triton response")
	}

	return generatedText, confidence, nil
}

// generateMockResult returns format-specific mock output
func generateMockResult(opts ExtractionOptions, pageNum int, imgPath string) string {
	if opts.Prompt != "" {
		// Custom prompt — return generic structured response
		result := map[string]interface{}{
			"page":       pageNum,
			"source":     imgPath,
			"content":    "Extracted content based on custom prompt",
			"confidence": 0.93,
		}
		b, _ := json.MarshalIndent(result, "", "  ")
		return string(b)
	}

	format := strings.TrimSpace(strings.Split(opts.OutputFormats, ",")[0])
	switch format {
	case "json":
		return mockJSON(opts.IncludeCoordinates)
	case "markdown":
		return mockMarkdown()
	case "table":
		return mockTable(opts.IncludeCoordinates)
	case "key_value":
		return mockKeyValue(opts.IncludeCoordinates)
	case "structured":
		return mockStructured(opts)
	default:
		return mockText(opts.IncludeCoordinates, opts.IncludeWordConfidence)
	}
}

func mockText(coords, wordConf bool) string {
	if !coords && !wordConf {
		return "INVOICE\nInvoice #: INV-2026-0042\nDate: February 25, 2026\n\nBill To:\nCustomer Inc.\n\nWidget A   10   $100.00   $1,000.00\nWidget B    5    $46.91     $234.56\n\nTotal Due: $1,358.02"
	}
	result := map[string]interface{}{
		"text": "INVOICE\nInvoice #: INV-2026-0042...",
	}
	if coords {
		result["blocks"] = []map[string]interface{}{
			{"text": "INVOICE", "bbox": []int{100, 50, 200, 40}, "confidence": 0.99},
			{"text": "Invoice #: INV-2026-0042", "bbox": []int{100, 100, 350, 25}, "confidence": 0.97},
			{"text": "Total Due: $1,358.02", "bbox": []int{100, 420, 280, 25}, "confidence": 0.98},
		}
	}
	if wordConf {
		result["words"] = []map[string]interface{}{
			{"word": "INVOICE", "bbox": []int{100, 50, 80, 30}, "confidence": 0.99},
			{"word": "INV-2026-0042", "bbox": []int{180, 100, 130, 20}, "confidence": 0.96},
			{"word": "$1,358.02", "bbox": []int{200, 420, 100, 20}, "confidence": 0.97},
		}
	}
	b, _ := json.MarshalIndent(result, "", "  ")
	return string(b)
}

func mockJSON(coords bool) string {
	fields := map[string]interface{}{
		"invoice_number": fieldVal("INV-2026-0042", 280, 100, 180, 25, 0.97, coords),
		"date":           fieldVal("2026-02-25", 280, 130, 150, 25, 0.96, coords),
		"total_amount":   fieldVal("$1,358.02", 400, 440, 130, 25, 0.98, coords),
	}
	result := map[string]interface{}{
		"document_type": "invoice",
		"fields":        fields,
		"line_items": []map[string]interface{}{
			{"description": "Widget A", "quantity": 10, "unit_price": "$100.00", "total": "$1,000.00"},
			{"description": "Widget B", "quantity": 5, "unit_price": "$46.91", "total": "$234.56"},
		},
	}
	b, _ := json.MarshalIndent(result, "", "  ")
	return string(b)
}

func mockMarkdown() string {
	return "# INVOICE\n\n**Invoice #:** INV-2026-0042\n**Date:** February 25, 2026\n\n| Description | Qty | Unit Price | Total |\n|---|---|---|---|\n| Widget A | 10 | $100.00 | $1,000.00 |\n| Widget B | 5 | $46.91 | $234.56 |\n\n**Total Due:** $1,358.02"
}

func mockTable(coords bool) string {
	table := map[string]interface{}{
		"table_id": 1,
		"headers":  []string{"Description", "Qty", "Unit Price", "Total"},
		"rows": [][]string{
			{"Widget A", "10", "$100.00", "$1,000.00"},
			{"Widget B", "5", "$46.91", "$234.56"},
		},
	}
	if coords {
		table["bbox"] = []int{80, 280, 540, 120}
	}
	result := []interface{}{table}
	b, _ := json.MarshalIndent(result, "", "  ")
	return string(b)
}

func mockKeyValue(coords bool) string {
	kv := map[string]interface{}{
		"invoice_number": fieldVal("INV-2026-0042", 280, 100, 180, 25, 0.97, coords),
		"date":           fieldVal("2026-02-25", 280, 130, 150, 25, 0.96, coords),
		"vendor":         fieldVal("Acme Corp", 280, 160, 140, 25, 0.95, coords),
		"total_amount":   fieldVal("$1,358.02", 400, 440, 130, 25, 0.98, coords),
	}
	b, _ := json.MarshalIndent(kv, "", "  ")
	return string(b)
}

func mockStructured(opts ExtractionOptions) string {
	fields := map[string]interface{}{
		"invoice_number": fieldVal("INV-2026-0042", 280, 100, 180, 25, 0.97, opts.IncludeCoordinates),
		"date":           fieldVal("2026-02-25", 280, 130, 150, 25, 0.96, opts.IncludeCoordinates),
		"total_amount":   fieldVal("$1,358.02", 400, 440, 130, 25, 0.98, opts.IncludeCoordinates),
	}
	result := map[string]interface{}{
		"document_type":        "invoice",
		"language":             "en",
		"raw_text":             "INVOICE\nInvoice #: INV-2026-0042...",
		"fields":               fields,
		"tables":               []map[string]interface{}{{"headers": []string{"Description", "Qty"}, "rows": [][]string{{"Widget A", "10"}}}},
		"handwritten_sections": []string{},
	}
	if opts.IncludeWordConfidence {
		result["words"] = []map[string]interface{}{
			{"word": "INVOICE", "bbox": []int{100, 50, 80, 30}, "confidence": 0.99},
		}
	}
	if opts.IncludePageLayout {
		result["pages"] = []map[string]interface{}{
			{"page_number": 1, "width": 612, "height": 792, "unit": "pixel"},
		}
	}
	b, _ := json.MarshalIndent(result, "", "  ")
	return string(b)
}

func fieldVal(value string, x, y, w, h int, conf float64, coords bool) interface{} {
	if coords {
		return map[string]interface{}{
			"value":      value,
			"bbox":       []int{x, y, w, h},
			"confidence": conf,
		}
	}
	return value
}

// ─── Activity 3: PostProcess ───

func (a *Activities) PostProcess(ctx context.Context, input *ExtractionOutput) (*FinalOutput, error) {
	log.Printf("🔍 [PostProcess] job=%s redact_pii=%v", input.JobID, input.Options.RedactPII)

	conn, err := grpc.NewClient(a.PostprocessingHost,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to post-processing: %w", err)
	}
	defer conn.Close()

	client := postprocessing.NewPostProcessingServiceClient(conn)
	ctx, cancel := context.WithTimeout(ctx, 2*time.Minute)
	defer cancel()

	resp, err := client.PostProcess(ctx, &postprocessing.PostProcessRequest{
		RawContent: input.RawContent,
		JobId:      input.JobID,
		RedactPii:  input.Options.RedactPII,
	})
	if err != nil {
		return nil, fmt.Errorf("post-processing call failed: %w", err)
	}

	if resp.Status != "success" {
		return nil, fmt.Errorf("post-processing failed: %s", resp.Error)
	}

	// Build the final result envelope
	resultPath := fmt.Sprintf("results/%s/extraction.json", input.JobID)

	envelope := map[string]interface{}{
		"job_id":              input.JobID,
		"model":               "glm-4v-9b",
		"document_confidence": resp.ConfidenceScore,
		"page_count":          input.PageCount,
		"output_formats":      input.Options.OutputFormats,
		"result":              resp.StructuredContent,
		"usage": map[string]interface{}{
			"prompt_tokens":     45,
			"completion_tokens": 512,
		},
		"timestamp": time.Now().Format(time.RFC3339),
	}

	resultJSON, _ := json.MarshalIndent(envelope, "", "  ")

	if err := a.uploadResultToMinIO(ctx, resultPath, resultJSON); err != nil {
		return nil, fmt.Errorf("failed to upload result to MinIO: %w", err)
	}

	log.Printf("✅ [PostProcess] job=%s result=%d bytes", input.JobID, len(resultJSON))

	return &FinalOutput{
		JobID:             input.JobID,
		StructuredContent: resp.StructuredContent,
		Confidence:        float64(resp.ConfidenceScore),
		ResultPath:        resultPath,
		PageCount:         input.PageCount,
	}, nil
}

func (a *Activities) uploadResultToMinIO(ctx context.Context, objectPath string, content []byte) error {
	endpoint := strings.TrimPrefix(strings.TrimPrefix(a.MinioEndpoint, "http://"), "https://")
	useSSL := strings.HasPrefix(a.MinioEndpoint, "https://")

	client, err := minio.New(endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(a.MinioAccessKey, a.MinioSecretKey, ""),
		Secure: useSSL,
	})
	if err != nil {
		return err
	}

	exists, err := client.BucketExists(ctx, a.MinioBucket)
	if err != nil {
		return err
	}
	if !exists {
		if err := client.MakeBucket(ctx, a.MinioBucket, minio.MakeBucketOptions{}); err != nil {
			return err
		}
	}

	reader := bytes.NewReader(content)
	_, err = client.PutObject(ctx, a.MinioBucket, objectPath, reader, int64(len(content)), minio.PutObjectOptions{
		ContentType: "application/json",
	})
	return err
}
