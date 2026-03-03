package orchestrator

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"image"
	"image/jpeg"
	"image/png"
	"log"
	"strings"
	"time"

	"bytes"

	"github.com/user/idep/api-gateway/cache"
	"github.com/user/idep/api-gateway/clients"
)

// Orchestrator handles the two-stage document processing pipeline
type Orchestrator struct {
	paddleOCRClient clients.PaddleOCRClientInterface
	glmOCRClient    clients.GLMOCRClientInterface
	redisCache      *cache.RedisCache
	config          *OrchestratorConfig
}

// OrchestratorConfig holds configuration for the orchestrator
type OrchestratorConfig struct {
	EnableLayoutDetection bool
	CacheLayoutResults    bool
	MaxParallelRegions    int
	ParallelProcessing    bool
}

// ProcessingResult represents the final result of document processing
type ProcessingResult struct {
	Pages      []PageResult       `json:"pages"`
	Markdown   string             `json:"markdown"`
	Model      string             `json:"model"`
	Mode       string             `json:"mode"`
	Confidence float64            `json:"confidence"`
	Usage      ProcessingUsage    `json:"usage"`
	Metadata   map[string]interface{} `json:"metadata,omitempty"`
}

// PageResult represents the result for a single page
type PageResult struct {
	Page     int           `json:"page"`
	Width    int           `json:"width"`
	Height   int           `json:"height"`
	Elements []PageElement `json:"elements"`
}

// PageElement represents a single element on a page
type PageElement struct {
	Index      int       `json:"index"`
	Label      string    `json:"label"`
	Content    string    `json:"content"`
	Bbox2D     []float64 `json:"bbox_2d"`
	Confidence float64   `json:"confidence"`
}

// ProcessingUsage tracks processing time for each stage
type ProcessingUsage struct {
	LayoutDetectionMs    float64 `json:"layout_detection_ms"`
	ContentExtractionMs  float64 `json:"content_extraction_ms"`
	TotalMs              float64 `json:"total_ms"`
	RegionsProcessed     int     `json:"regions_processed"`
	CacheHit             bool    `json:"cache_hit,omitempty"`
}

// NewOrchestrator creates a new orchestrator
func NewOrchestrator(
	paddleOCRClient clients.PaddleOCRClientInterface,
	glmOCRClient clients.GLMOCRClientInterface,
	redisCache *cache.RedisCache,
	config *OrchestratorConfig,
) *Orchestrator {
	return &Orchestrator{
		paddleOCRClient: paddleOCRClient,
		glmOCRClient:    glmOCRClient,
		redisCache:      redisCache,
		config:          config,
	}
}

// ProcessDocument orchestrates the two-stage pipeline
func (o *Orchestrator) ProcessDocument(
	ctx context.Context,
	imageBase64 string,
	options map[string]interface{},
) (*ProcessingResult, error) {
	startTime := time.Now()

	// Check if layout detection is enabled
	enableLayoutDetection := o.config.EnableLayoutDetection
	if val, ok := options["enable_layout_detection"].(bool); ok {
		enableLayoutDetection = val
	}

	if !enableLayoutDetection {
		// Fallback to full-page mode
		return o.processFallbackMode(ctx, imageBase64, options)
	}

	// Stage 1: Layout Detection
	layoutStartTime := time.Now()
	layoutResponse, err := o.detectLayout(ctx, imageBase64, options)
	layoutDuration := time.Since(layoutStartTime).Milliseconds()

	if err != nil {
		log.Printf("Layout detection failed: %v, falling back to full-page mode", err)
		return o.processFallbackMode(ctx, imageBase64, options)
	}

	if len(layoutResponse.Regions) == 0 {
		log.Printf("No regions detected, falling back to full-page mode")
		return o.processFallbackMode(ctx, imageBase64, options)
	}

	// Stage 2: Crop regions
	croppedRegions, err := o.cropRegions(imageBase64, layoutResponse.Regions, layoutResponse.PageDimensions)
	if err != nil {
		log.Printf("Failed to crop regions: %v, falling back to full-page mode", err)
		return o.processFallbackMode(ctx, imageBase64, options)
	}

	// Stage 3: Extract content from regions
	extractionStartTime := time.Now()
	extractionResults, err := o.extractRegionsContent(ctx, croppedRegions, options)
	extractionDuration := time.Since(extractionStartTime).Milliseconds()

	if err != nil {
		log.Printf("Content extraction failed: %v, returning layout only", err)
		// Return layout detection results only
		return o.assembleLayoutOnlyResult(layoutResponse, float64(layoutDuration), 0)
	}

	// Stage 4: Assemble final result
	result := o.assembleResult(layoutResponse, extractionResults, float64(layoutDuration), float64(extractionDuration))
	result.Usage.TotalMs = float64(time.Since(startTime).Milliseconds())

	return result, nil
}

// detectLayout performs layout detection with caching
func (o *Orchestrator) detectLayout(
	ctx context.Context,
	imageBase64 string,
	options map[string]interface{},
) (*clients.DetectLayoutResponse, error) {
	// Check cache if enabled
	if o.config.CacheLayoutResults && o.redisCache != nil {
		cacheKey := o.generateLayoutCacheKey(imageBase64, options)
		
		if cachedData, found := o.redisCache.Get(ctx, cacheKey); found {
			var response clients.DetectLayoutResponse
			if err := json.Unmarshal([]byte(cachedData), &response); err == nil {
				log.Printf("Layout detection cache hit")
				return &response, nil
			}
		}
	}

	// Prepare layout detection options
	layoutOptions := make(map[string]interface{})
	if layoutOpts, ok := options["layout_detection_options"].(map[string]interface{}); ok {
		layoutOptions = layoutOpts
	}

	// Set defaults
	if _, ok := layoutOptions["min_confidence"]; !ok {
		layoutOptions["min_confidence"] = 0.5
	}
	if _, ok := layoutOptions["detect_tables"]; !ok {
		layoutOptions["detect_tables"] = true
	}
	if _, ok := layoutOptions["detect_formulas"]; !ok {
		layoutOptions["detect_formulas"] = true
	}
	if _, ok := layoutOptions["return_image_dimensions"]; !ok {
		layoutOptions["return_image_dimensions"] = true
	}

	// Call PaddleOCR service
	response, err := o.paddleOCRClient.DetectLayout(ctx, imageBase64, layoutOptions)
	if err != nil {
		return nil, fmt.Errorf("layout detection failed: %w", err)
	}

	// Cache the result if enabled
	if o.config.CacheLayoutResults && o.redisCache != nil {
		cacheKey := o.generateLayoutCacheKey(imageBase64, options)
		if data, err := json.Marshal(response); err == nil {
			// Cache for 1 hour
			o.redisCache.Set(ctx, cacheKey, string(data), 3600)
		}
	}

	return response, nil
}

// generateLayoutCacheKey generates a cache key for layout detection
func (o *Orchestrator) generateLayoutCacheKey(imageBase64 string, options map[string]interface{}) string {
	// Hash image + options
	h := sha256.New()
	h.Write([]byte(imageBase64))
	
	if layoutOpts, ok := options["layout_detection_options"].(map[string]interface{}); ok {
		if data, err := json.Marshal(layoutOpts); err == nil {
			h.Write(data)
		}
	}
	
	return "layout:" + hex.EncodeToString(h.Sum(nil))
}

// cropRegions crops the image into regions based on bounding boxes
func (o *Orchestrator) cropRegions(
	imageBase64 string,
	regions []clients.Region,
	pageDims *clients.PageDimensions,
) ([]clients.RegionExtractionRequest, error) {
	// Decode base64 image
	imageData, err := base64.StdEncoding.DecodeString(imageBase64)
	if err != nil {
		return nil, fmt.Errorf("failed to decode image: %w", err)
	}

	// Decode image
	img, format, err := image.Decode(bytes.NewReader(imageData))
	if err != nil {
		return nil, fmt.Errorf("failed to decode image: %w", err)
	}

	var croppedRegions []clients.RegionExtractionRequest

	for _, region := range regions {
		// Extract bbox coordinates
		if len(region.Bbox) != 4 {
			log.Printf("Invalid bbox for region %d: %v", region.Index, region.Bbox)
			continue
		}

		x1, y1, x2, y2 := int(region.Bbox[0]), int(region.Bbox[1]), int(region.Bbox[2]), int(region.Bbox[3])

		// Validate bbox
		bounds := img.Bounds()
		if x1 < 0 {
			x1 = 0
		}
		if y1 < 0 {
			y1 = 0
		}
		if x2 > bounds.Max.X {
			x2 = bounds.Max.X
		}
		if y2 > bounds.Max.Y {
			y2 = bounds.Max.Y
		}

		// Crop image
		croppedImg := img.(interface {
			SubImage(r image.Rectangle) image.Image
		}).SubImage(image.Rect(x1, y1, x2, y2))

		// Encode cropped image to base64
		var buf bytes.Buffer
		switch format {
		case "jpeg", "jpg":
			if err := jpeg.Encode(&buf, croppedImg, &jpeg.Options{Quality: 95}); err != nil {
				log.Printf("Failed to encode region %d: %v", region.Index, err)
				continue
			}
		case "png":
			if err := png.Encode(&buf, croppedImg); err != nil {
				log.Printf("Failed to encode region %d: %v", region.Index, err)
				continue
			}
		default:
			// Default to PNG
			if err := png.Encode(&buf, croppedImg); err != nil {
				log.Printf("Failed to encode region %d: %v", region.Index, err)
				continue
			}
		}

		croppedBase64 := base64.StdEncoding.EncodeToString(buf.Bytes())

		// Get prompt for region type
		prompt := clients.GetPromptForRegionType(region.Type, "")

		croppedRegions = append(croppedRegions, clients.RegionExtractionRequest{
			RegionID:   fmt.Sprintf("region_%d", region.Index),
			Image:      croppedBase64,
			RegionType: region.Type,
			Prompt:     prompt,
		})
	}

	return croppedRegions, nil
}

// extractRegionsContent extracts content from cropped regions
func (o *Orchestrator) extractRegionsContent(
	ctx context.Context,
	regions []clients.RegionExtractionRequest,
	options map[string]interface{},
) (*clients.BatchRegionExtractionResponse, error) {
	// Prepare extraction options
	extractionOptions := make(map[string]interface{})
	
	// Copy relevant options
	if val, ok := options["output_format"]; ok {
		extractionOptions["output_format"] = val
	} else {
		extractionOptions["output_format"] = "json"
	}
	
	if val, ok := options["max_tokens"]; ok {
		extractionOptions["max_tokens"] = val
	}
	
	if val, ok := options["precision_mode"]; ok {
		extractionOptions["precision_mode"] = val
	}

	// Check if parallel processing is enabled
	parallelProcessing := o.config.ParallelProcessing
	if val, ok := options["parallel_region_processing"].(bool); ok {
		parallelProcessing = val
	}

	if parallelProcessing {
		return o.glmOCRClient.ExtractRegionsParallel(ctx, regions, extractionOptions, o.config.MaxParallelRegions)
	}

	return o.glmOCRClient.ExtractRegionsBatch(ctx, regions, extractionOptions)
}

// assembleResult assembles the final result from layout and extraction
func (o *Orchestrator) assembleResult(
	layoutResponse *clients.DetectLayoutResponse,
	extractionResponse *clients.BatchRegionExtractionResponse,
	layoutDuration float64,
	extractionDuration float64,
) *ProcessingResult {
	// Create result map for quick lookup
	resultMap := make(map[string]*clients.RegionExtractionResult)
	for i := range extractionResponse.Results {
		resultMap[extractionResponse.Results[i].RegionID] = &extractionResponse.Results[i]
	}

	// Build page elements
	var elements []PageElement
	var markdownParts []string
	totalConfidence := 0.0
	confidenceCount := 0

	for _, region := range layoutResponse.Regions {
		regionID := fmt.Sprintf("region_%d", region.Index)
		result, ok := resultMap[regionID]
		
		content := ""
		confidence := region.Confidence
		
		if ok && result.Error == "" {
			content = result.Content
			if result.Confidence > 0 {
				confidence = (region.Confidence + result.Confidence) / 2
			}
		}

		element := PageElement{
			Index:      region.Index,
			Label:      region.Type,
			Content:    content,
			Bbox2D:     region.Bbox,
			Confidence: confidence,
		}
		elements = append(elements, element)

		// Build markdown
		if content != "" {
			markdownParts = append(markdownParts, content)
		}

		totalConfidence += confidence
		confidenceCount++
	}

	// Calculate average confidence
	avgConfidence := 0.0
	if confidenceCount > 0 {
		avgConfidence = totalConfidence / float64(confidenceCount)
	}

	// Build page result
	width := 0
	height := 0
	if layoutResponse.PageDimensions != nil {
		width = layoutResponse.PageDimensions.Width
		height = layoutResponse.PageDimensions.Height
	}

	page := PageResult{
		Page:     1,
		Width:    width,
		Height:   height,
		Elements: elements,
	}

	return &ProcessingResult{
		Pages:      []PageResult{page},
		Markdown:   strings.Join(markdownParts, "\n\n"),
		Model:      "zai-org/GLM-OCR",
		Mode:       "two-stage",
		Confidence: avgConfidence,
		Usage: ProcessingUsage{
			LayoutDetectionMs:   layoutDuration,
			ContentExtractionMs: extractionDuration,
			RegionsProcessed:    len(layoutResponse.Regions),
		},
	}
}

// assembleLayoutOnlyResult assembles result with layout detection only
func (o *Orchestrator) assembleLayoutOnlyResult(
	layoutResponse *clients.DetectLayoutResponse,
	layoutDuration float64,
	extractionDuration float64,
) (*ProcessingResult, error) {
	var elements []PageElement
	totalConfidence := 0.0

	for _, region := range layoutResponse.Regions {
		element := PageElement{
			Index:      region.Index,
			Label:      region.Type,
			Content:    "", // No content extracted
			Bbox2D:     region.Bbox,
			Confidence: region.Confidence,
		}
		elements = append(elements, element)
		totalConfidence += region.Confidence
	}

	avgConfidence := 0.0
	if len(layoutResponse.Regions) > 0 {
		avgConfidence = totalConfidence / float64(len(layoutResponse.Regions))
	}

	width := 0
	height := 0
	if layoutResponse.PageDimensions != nil {
		width = layoutResponse.PageDimensions.Width
		height = layoutResponse.PageDimensions.Height
	}

	page := PageResult{
		Page:     1,
		Width:    width,
		Height:   height,
		Elements: elements,
	}

	return &ProcessingResult{
		Pages:      []PageResult{page},
		Markdown:   "",
		Model:      "PaddleOCR-only",
		Mode:       "layout-only",
		Confidence: avgConfidence,
		Usage: ProcessingUsage{
			LayoutDetectionMs:   layoutDuration,
			ContentExtractionMs: extractionDuration,
			RegionsProcessed:    len(layoutResponse.Regions),
		},
		Metadata: map[string]interface{}{
			"warning": "Content extraction failed, returning layout detection only",
		},
	}, nil
}

// processFallbackMode processes document in full-page mode (no layout detection)
func (o *Orchestrator) processFallbackMode(
	ctx context.Context,
	imageBase64 string,
	options map[string]interface{},
) (*ProcessingResult, error) {
	log.Printf("Processing in fallback mode (full-page)")

	// Get image dimensions
	imageData, err := base64.StdEncoding.DecodeString(imageBase64)
	if err != nil {
		return nil, fmt.Errorf("failed to decode image: %w", err)
	}

	img, _, err := image.Decode(bytes.NewReader(imageData))
	if err != nil {
		return nil, fmt.Errorf("failed to decode image: %w", err)
	}

	bounds := img.Bounds()
	width := bounds.Max.X
	height := bounds.Max.Y

	// Create single full-page region
	regions := []clients.RegionExtractionRequest{
		{
			RegionID:   "region_0",
			Image:      imageBase64,
			RegionType: "text",
			Prompt:     "Text Recognition:",
		},
	}

	// Extract content
	startTime := time.Now()
	extractionResponse, err := o.glmOCRClient.ExtractRegionsBatch(ctx, regions, options)
	extractionDuration := time.Since(startTime).Milliseconds()

	if err != nil {
		return nil, fmt.Errorf("content extraction failed: %w", err)
	}

	// Build result
	content := ""
	confidence := 0.0
	if len(extractionResponse.Results) > 0 {
		content = extractionResponse.Results[0].Content
		confidence = extractionResponse.Results[0].Confidence
	}

	element := PageElement{
		Index:      0,
		Label:      "text",
		Content:    content,
		Bbox2D:     []float64{0, 0, float64(width), float64(height)},
		Confidence: confidence,
	}

	page := PageResult{
		Page:     1,
		Width:    width,
		Height:   height,
		Elements: []PageElement{element},
	}

	return &ProcessingResult{
		Pages:      []PageResult{page},
		Markdown:   content,
		Model:      "zai-org/GLM-OCR",
		Mode:       "full-page",
		Confidence: confidence,
		Usage: ProcessingUsage{
			LayoutDetectionMs:   0,
			ContentExtractionMs: float64(extractionDuration),
			TotalMs:             float64(extractionDuration),
			RegionsProcessed:    1,
		},
		Metadata: map[string]interface{}{
			"fallback": "Layout detection disabled or failed",
		},
	}, nil
}
