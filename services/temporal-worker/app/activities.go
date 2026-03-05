package app

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
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
	InferenceBackend   string
	GLMOCRServiceURL   string
	PreprocessingHost  string
	PostprocessingHost string
	TritonHost         string
	TritonGRPCPort     string
	TritonHTTPPort     string
	MinioEndpoint      string
	MinioAccessKey     string
	MinioSecretKey     string
	MinioBucket        string
	StorageDriver      string // "minio" (default) or "local"
	LocalStorageRoot   string // root dir for local storage
}

// ─── Data Transfer Objects ───

// ExtractionOptions carries all user-configurable parameters through the pipeline
type ExtractionOptions struct {
	OutputFormats         string `json:"output_formats"`
	Prompt                string `json:"prompt"`
	FastMode              bool   `json:"fast_mode"`
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
	// PrecisionMode controls GLM-OCR inference quality: "normal" (faster) or "high"
	// (word-level bbox enrichment). Defaults to "normal".
	PrecisionMode string `json:"precision_mode"`
	// ExtractFields limits extraction to the listed field names (e.g. ["date", "amount"]).
	// When empty, all detected content is returned.  Values are case-insensitive.
	ExtractFields []string `json:"extract_fields"`
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
	JobID          string            `json:"job_id"`
	RawContent     string            `json:"raw_content"`
	Confidence     float64           `json:"confidence"`
	PageCount      int               `json:"page_count"`
	ExtractionTime float64           `json:"extraction_time"`
	Options        ExtractionOptions `json:"options"`
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
		ExtractFields: []string{},
	}

	if v, ok := input["output_formats"].(string); ok {
		opts.OutputFormats = v
	}

	if optMap, ok := input["options"].(map[string]interface{}); ok {
		if v, ok := optMap["prompt"].(string); ok {
			opts.Prompt = v
		}
		if v, ok := optMap["fast_mode"].(bool); ok {
			opts.FastMode = v
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
		if v, ok := optMap["precision_mode"].(string); ok {
			opts.PrecisionMode = v
		}
		// extract_fields: accept []string or []interface{}
		switch ef := optMap["extract_fields"].(type) {
		case []string:
			opts.ExtractFields = ef
		case []interface{}:
			for _, item := range ef {
				if s, ok := item.(string); ok {
					opts.ExtractFields = append(opts.ExtractFields, s)
				}
			}
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

	// Stage source document from MinIO to shared temp volume so downstream
	// preprocessing tools always receive a local filesystem path.
	localSourcePath, err := a.downloadSourceFromMinIO(ctx, storagePath, jobID)
	if err != nil {
		return nil, fmt.Errorf("failed to prepare source from storage: %w", err)
	}

	// Fast path for image uploads: download original file from MinIO into shared temp dir.
	// This bypasses local placeholder protobuf stubs that return simulated paths.
	ext := strings.ToLower(filepath.Ext(localSourcePath))
	if ext == ".png" || ext == ".jpg" || ext == ".jpeg" || ext == ".bmp" || ext == ".webp" || ext == ".tif" || ext == ".tiff" {
		return &PreprocessOutput{
			JobID:      jobID,
			ImagePaths: []string{localSourcePath},
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
		FilePath: localSourcePath,
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
	// ── Local storage mode ─────────────────────────────────────────────────
	if strings.EqualFold(a.StorageDriver, "local") {
		objectPath := strings.TrimPrefix(storagePath, a.MinioBucket+"/")
		objectPath = strings.TrimPrefix(objectPath, "/")
		localPath := filepath.Join(a.LocalStorageRoot, a.MinioBucket, filepath.FromSlash(objectPath))
		if _, err := os.Stat(localPath); err != nil {
			return "", fmt.Errorf("local file not found at %s: %w", localPath, err)
		}
		log.Printf("📁 [Local] Source file: %s", localPath)
		return localPath, nil
	}

	// ── MinIO mode (default) ────────────────────────────────────────────
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

// PageProcessingInput contains input for processing a single page
type PageProcessingInput struct {
	JobID         string `json:"job_id"`
	PageNumber    int    `json:"page_number"`
	ImagePath     string `json:"image_path"`
	Prompt        string `json:"prompt"`
	OptionsJSON   string `json:"options_json"`
	PrecisionMode string `json:"precision_mode"`
}

// PageProcessingOutput contains the result of processing a single page
type PageProcessingOutput struct {
	PageNumber int     `json:"page_number"`
	Content    string  `json:"content"`
	Confidence float64 `json:"confidence"`
	Error      string  `json:"error,omitempty"`
}

// ProcessSinglePage processes a single page through Triton
func (a *Activities) ProcessSinglePage(ctx context.Context, input *PageProcessingInput) (*PageProcessingOutput, error) {
	log.Printf("🧠 [ProcessSinglePage] job=%s page=%d", input.JobID, input.PageNumber)

	imgPath := resolveLocalImagePath(input.ImagePath)

	pageJSON, pageConf, err := a.callTritonHTTP(ctx, imgPath, input.Prompt, input.OptionsJSON, input.PrecisionMode)
	if err != nil {
		return &PageProcessingOutput{
			PageNumber: input.PageNumber,
			Error:      err.Error(),
		}, fmt.Errorf("triton inference failed for page %d: %w", input.PageNumber, err)
	}

	log.Printf("✅ [ProcessSinglePage] job=%s page=%d confidence=%.2f", input.JobID, input.PageNumber, pageConf)

	return &PageProcessingOutput{
		PageNumber: input.PageNumber,
		Content:    pageJSON,
		Confidence: pageConf,
	}, nil
}

// buildPrompt returns the official GLM-OCR task prompt for the requested output format.
// Reference: https://github.com/zai-org/GLM-OCR — prompts are fixed task prefixes, not
// free-form instructions. The model's output structure is controlled via the options JSON.
func buildPrompt(opts ExtractionOptions) string {
	// Custom prompt takes priority (advanced users may override the task prefix)
	if opts.Prompt != "" {
		return opts.Prompt
	}

	// When the caller requests specific fields, produce a focused extraction prompt.
	// The Python backend will additionally filter the result to those fields, but
	// giving the model an explicit list significantly improves precision.
	if len(opts.ExtractFields) > 0 {
		return fmt.Sprintf(
			"Text Recognition: Extract only the following fields from this document: %s. "+
				"Return a flat JSON object where each key is one of the requested field names.",
			strings.Join(opts.ExtractFields, ", "),
		)
	}

	// Map output formats to official GLM-OCR task prompts
	formats := strings.Split(opts.OutputFormats, ",")
	primary := strings.TrimSpace(strings.ToLower(formats[0]))

	switch primary {
	case "table":
		return "Table Recognition:"
	case "formula":
		return "Formula Recognition:"
	default:
		// text, json, markdown, key_value, structured — all start with text recognition;
		// output structure is controlled by the options JSON passed to Triton.
		return "Text Recognition:"
	}
}

func (a *Activities) CallTriton(ctx context.Context, input *PreprocessOutput) (*ExtractionOutput, error) {
	log.Printf("🧠 [Triton] job=%s pages=%d formats=%s precision=%s",
		input.JobID, input.PageCount, input.Options.OutputFormats, input.Options.PrecisionMode)

	// Build the official GLM-OCR task prompt
	prompt := buildPrompt(input.Options)

	// Build options JSON for Triton — controls output structure inside the Python backend
	optionsJSON, _ := json.Marshal(map[string]interface{}{
		"fast_mode":               input.Options.FastMode,
		"include_coordinates":     input.Options.IncludeCoordinates,
		"include_word_confidence": input.Options.IncludeWordConfidence,
		"include_line_confidence": input.Options.IncludeLineConfidence,
		"include_page_layout":     input.Options.IncludePageLayout,
		"language":                input.Options.Language,
		"granularity":             input.Options.Granularity,
		"temperature":             parseFloatOrDefault(input.Options.Temperature, 0.0),
		"max_tokens":              parseIntOrDefault(input.Options.MaxTokens, 4096),
		"output_format":           strings.TrimSpace(strings.Split(input.Options.OutputFormats, ",")[0]),
		"extract_fields":          input.Options.ExtractFields,
	})

	log.Printf("   Prompt: %q  Options: %s", prompt, string(optionsJSON))

	// ── Per-page inference ──────────────────────────────────────────────────
	type pageEntry struct {
		Page   int         `json:"page"`
		Result interface{} `json:"result"`
	}
	var pageEntries []pageEntry
	var markdownParts []string
	var totalConfidence float64
	successCount := 0

	start := time.Now()

	for i, imgPath := range input.ImagePaths {
		imgPath = resolveLocalImagePath(imgPath)
		pageJSON, pageConf, err := a.callTritonHTTP(ctx, imgPath, prompt, string(optionsJSON), input.Options.PrecisionMode)
		if err != nil {
			return nil, fmt.Errorf("triton inference failed for page %d (%s): %w", i+1, imgPath, err)
		}

		// Hoist per-page markdown into aggregated list
		var pageData map[string]json.RawMessage
		if json.Unmarshal([]byte(pageJSON), &pageData) == nil {
			if mdRaw, ok := pageData["markdown"]; ok {
				var md string
				if json.Unmarshal(mdRaw, &md) == nil && md != "" {
					markdownParts = append(markdownParts, md)
				}
			}
		}

		var parsedResult interface{}
		if json.Unmarshal([]byte(pageJSON), &parsedResult) != nil {
			parsedResult = pageJSON
		}
		pageEntries = append(pageEntries, pageEntry{Page: i + 1, Result: parsedResult})
		totalConfidence += pageConf
		successCount++
	}

	extractionTime := time.Since(start).Seconds()
	avgConfidence := 0.0
	if successCount > 0 {
		avgConfidence = totalConfidence / float64(successCount)
	}

	// ── Aggregate pages into canonical output ───────────────────────────────
	aggregated := map[string]interface{}{
		"job_id":     input.JobID,
		"model":      "zai-org/GLM-OCR",
		"precision":  input.Options.PrecisionMode,
		"pages":      pageEntries,
		"markdown":   strings.Join(markdownParts, "\n\n---\n\n"),
		"page_count": input.PageCount,
		"confidence": avgConfidence,
	}
	allContentBytes, _ := json.Marshal(aggregated)

	log.Printf("✅ [Triton] job=%s confidence=%.2f time=%.2fs", input.JobID, avgConfidence, extractionTime)

	return &ExtractionOutput{
		JobID:          input.JobID,
		RawContent:     string(allContentBytes),
		Confidence:     avgConfidence,
		PageCount:      input.PageCount,
		ExtractionTime: extractionTime,
		Options:        input.Options,
	}, nil
}

// resolveLocalImagePath normalizes page paths produced by preprocessing or MinIO staging.
// On Windows, paths like "\\tmp\\idep\\..." are rooted but filepath.IsAbs may not always
// classify incoming variants consistently, so we treat rooted tmp paths as already resolved.
func resolveLocalImagePath(path string) string {
	if strings.TrimSpace(path) == "" {
		return path
	}

	cleaned := filepath.Clean(filepath.FromSlash(path))
	if filepath.IsAbs(cleaned) || strings.HasPrefix(cleaned, string(os.PathSeparator)) {
		return cleaned
	}

	trimmed := strings.TrimLeft(cleaned, `/\\`)
	tmpRoot := filepath.Join("tmp", "idep")
	tmpRootPrefix := tmpRoot + string(os.PathSeparator)
	if strings.HasPrefix(strings.ToLower(trimmed), strings.ToLower(tmpRootPrefix)) || strings.EqualFold(trimmed, tmpRoot) {
		return string(os.PathSeparator) + trimmed
	}

	return filepath.Join("/tmp/idep", cleaned)
}

func parseIntOrDefault(raw string, fallback int) int {
	if v, err := strconv.Atoi(strings.TrimSpace(raw)); err == nil {
		return v
	}
	return fallback
}

func parseFloatOrDefault(raw string, fallback float64) float64 {
	if v, err := strconv.ParseFloat(strings.TrimSpace(raw), 64); err == nil {
		return v
	}
	return fallback
}

// stringToUint8Tensor encodes a Go string as a UINT8 tensor for Triton.
// This is a workaround for the Triton Python Backend 2.42.0 BYTES bug.
func stringToUint8Tensor(name, value string) map[string]interface{} {
	b := []byte(value)
	data := make([]int, len(b))
	for i, c := range b {
		data[i] = int(c)
	}
	return map[string]interface{}{
		"name":     name,
		"shape":    []int{len(b)},
		"datatype": "UINT8",
		"data":     data,
	}
}

// callTritonHTTP sends one image to Triton's HTTP inference endpoint and returns the
// raw JSON result string plus the top-level confidence score.
func (a *Activities) callTritonHTTP(ctx context.Context, imagePath, prompt, options, precisionMode string) (string, float64, error) {
	if strings.EqualFold(a.InferenceBackend, "glm_service") {
		return a.callGLMOCRHTTP(ctx, imagePath, prompt, options, precisionMode)
	}

	tritonURL := fmt.Sprintf("http://%s:%s/v2/models/glm_ocr/infer", a.TritonHost, a.TritonHTTPPort)

	// WORKAROUND: pass dynamic strings via request-level parameters to avoid
	// Python backend IPC corruption for variable-length string tensors.
	// Keep a minimal required input tensor for Triton request validation.
	inputs := []map[string]interface{}{
		stringToUint8Tensor("images", "x"),
	}

	params := map[string]interface{}{
		"image_ref":    imagePath,
		"prompt":       prompt,
		"options_json": options,
	}
	if precisionMode != "" {
		params["precision_mode"] = precisionMode
	}

	payload := map[string]interface{}{
		"inputs":     inputs,
		"parameters": params,
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

	httpClient := &http.Client{Timeout: 30 * time.Minute}
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
			var bytesArr []int
			if err := json.Unmarshal(out.Data, &bytesArr); err == nil && len(bytesArr) > 0 {
				buf := make([]byte, len(bytesArr))
				for i, v := range bytesArr {
					if v < 0 {
						v = 0
					}
					if v > 255 {
						v = 255
					}
					buf[i] = byte(v)
				}
				generatedText = string(bytes.TrimRight(buf, "\x00"))
				break
			}

			// Backward-compatible fallback if backend still returns TYPE_STRING
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

	// Confidence comes from the Triton output tensor; if absent (0), try the JSON payload.
	// The new GLM-OCR backend embeds "confidence" inside the generated_text JSON as well.
	if confidence == 0 {
		var result map[string]interface{}
		if json.Unmarshal([]byte(generatedText), &result) == nil {
			if c, ok := result["confidence"].(float64); ok && c > 0 {
				confidence = c
			}
		}
	}

	return generatedText, confidence, nil
}

func (a *Activities) callGLMOCRHTTP(ctx context.Context, imagePath, prompt, options, precisionMode string) (string, float64, error) {
	glmURL := strings.TrimRight(a.GLMOCRServiceURL, "/") + "/extract-region"
	if strings.TrimSpace(a.GLMOCRServiceURL) == "" {
		glmURL = "http://localhost:8002/extract-region"
	}

	imgBytes, err := os.ReadFile(imagePath)
	if err != nil {
		return "", 0, fmt.Errorf("failed to read image for glm service: %w", err)
	}

	optionsMap := map[string]interface{}{}
	if strings.TrimSpace(options) != "" {
		if err := json.Unmarshal([]byte(options), &optionsMap); err != nil {
			return "", 0, fmt.Errorf("invalid options json for glm service: %w", err)
		}
	}
	if precisionMode != "" {
		optionsMap["precision_mode"] = precisionMode
	}

	payload := map[string]interface{}{
		"image":       base64.StdEncoding.EncodeToString(imgBytes),
		"region_type": "text",
		"prompt":      prompt,
		"options":     optionsMap,
	}

	bodyBytes, err := json.Marshal(payload)
	if err != nil {
		return "", 0, err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, glmURL, bytes.NewReader(bodyBytes))
	if err != nil {
		return "", 0, err
	}
	req.Header.Set("Content-Type", "application/json")

	httpClient := &http.Client{Timeout: 30 * time.Minute}
	resp, err := httpClient.Do(req)
	if err != nil {
		return "", 0, err
	}
	defer resp.Body.Close()

	respBody, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 300 {
		return "", 0, fmt.Errorf("glm-ocr http %d: %s", resp.StatusCode, string(respBody))
	}

	var extractResp struct {
		Content    string  `json:"content"`
		Confidence float64 `json:"confidence"`
	}
	if err := json.Unmarshal(respBody, &extractResp); err != nil {
		return "", 0, err
	}

	if strings.TrimSpace(extractResp.Content) == "" {
		return "", 0, fmt.Errorf("missing content in glm-ocr response")
	}

	return extractResp.Content, extractResp.Confidence, nil
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

	// Build the final result envelope — includes all fields from the new GLM-OCR schema
	// so downstream consumers can access pages[].elements[].bbox_2d directly.
	resultPath := fmt.Sprintf("results/%s/extraction.json", input.JobID)

	// Attempt to unmarshal the aggregated pipeline result for inline embedding
	var inlineResult interface{}
	if err := json.Unmarshal([]byte(input.RawContent), &inlineResult); err != nil {
		// Fallback: treat as opaque string
		inlineResult = input.RawContent
	}

	envelope := map[string]interface{}{
		"job_id":              input.JobID,
		"model":               "zai-org/GLM-OCR",
		"document_confidence": resp.ConfidenceScore,
		"page_count":          input.PageCount,
		"extraction_time":     input.ExtractionTime,
		"output_formats":      input.Options.OutputFormats,
		"precision_mode":      input.Options.PrecisionMode,
		"result":              resp.StructuredContent,
		"raw_pages":           inlineResult,
		"timestamp":           time.Now().Format(time.RFC3339),
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
	// ── Local storage mode ─────────────────────────────────────────────────
	if strings.EqualFold(a.StorageDriver, "local") {
		fullPath := filepath.Join(a.LocalStorageRoot, a.MinioBucket, filepath.FromSlash(objectPath))
		if err := os.MkdirAll(filepath.Dir(fullPath), 0o755); err != nil {
			return fmt.Errorf("failed to create result directory: %w", err)
		}
		if err := os.WriteFile(fullPath, content, 0o644); err != nil {
			return fmt.Errorf("failed to write result file: %w", err)
		}
		log.Printf("📁 [Local] Result saved: %s", fullPath)
		return nil
	}

	// ── MinIO mode (default) ────────────────────────────────────────────
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
