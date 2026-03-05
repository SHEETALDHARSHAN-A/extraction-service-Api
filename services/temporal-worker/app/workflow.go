package app

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"go.temporal.io/sdk/temporal"
	"go.temporal.io/sdk/workflow"
)

// DocumentProcessingWorkflow orchestrates the 3-step extraction pipeline.
// Input comes from the API Gateway and includes output_formats + options.
func DocumentProcessingWorkflow(ctx workflow.Context, input map[string]interface{}) (map[string]interface{}, error) {
	logger := workflow.GetLogger(ctx)
	logger.Info("🚀 DocumentProcessingWorkflow started",
		"job_id", input["job_id"],
		"filename", input["filename"],
		"output_formats", input["output_formats"],
	)

	jobID := input["job_id"].(string)
	workflowStartTime := workflow.Now(ctx)

	// Track partial results for timeout handling
	var partialPageResults []*PageProcessingOutput
	var preprocessOutput PreprocessOutput

	// Mark queue status as PROCESSING at workflow start.
	// NOTE: There is no standalone queue consumer currently calling Dequeue(),
	// so waiting for PROCESSING can block forever while status remains QUEUED.
	logger.Info("🔄 Marking queued job as PROCESSING", "job_id", jobID)
	queueCheckOpts := workflow.ActivityOptions{
		StartToCloseTimeout: 30 * time.Second,
		RetryPolicy: &temporal.RetryPolicy{
			InitialInterval:    time.Second,
			BackoffCoefficient: 2.0,
			MaximumInterval:    5 * time.Second,
			MaximumAttempts:    5,
		},
	}

	var queueActivities *QueueActivities
	queueCheckCtx := workflow.WithActivityOptions(ctx, queueCheckOpts)

	err := workflow.ExecuteActivity(queueCheckCtx, queueActivities.MarkJobProcessing, jobID).Get(ctx, nil)
	if err != nil {
		logger.Error("❌ Failed to mark queue status as PROCESSING", "error", err)
		return nil, err
	}

	logger.Info("✅ Job ready for processing", "job_id", jobID)

	// Acquire GPU lock before processing
	logger.Info("🔒 Acquiring GPU lock", "job_id", jobID)
	lockOpts := workflow.ActivityOptions{
		StartToCloseTimeout: 10 * time.Second,
		RetryPolicy: &temporal.RetryPolicy{
			InitialInterval:    time.Second,
			BackoffCoefficient: 2.0,
			MaximumInterval:    30 * time.Second,
			MaximumAttempts:    5,
		},
	}

	lockCtx := workflow.WithActivityOptions(ctx, lockOpts)
	var lockAcquired bool
	err = workflow.ExecuteActivity(lockCtx, queueActivities.AcquireGPULock, jobID).Get(ctx, &lockAcquired)
	if err != nil {
		logger.Error("❌ Failed to acquire GPU lock", "error", err)
		return nil, fmt.Errorf("failed to acquire GPU lock: %w", err)
	}

	if !lockAcquired {
		logger.Error("❌ GPU lock not available", "job_id", jobID)
		return nil, fmt.Errorf("GPU lock not available for job %s", jobID)
	}

	logger.Info("✅ GPU lock acquired", "job_id", jobID)

	// Ensure GPU lock is released when workflow completes (success or failure)
	defer func() {
		// Use a new context for cleanup to ensure it runs even if workflow context is cancelled
		cleanupCtx, cancel := workflow.NewDisconnectedContext(ctx)
		defer cancel()

		cleanupCtx = workflow.WithActivityOptions(cleanupCtx, lockOpts)
		releaseErr := workflow.ExecuteActivity(cleanupCtx, queueActivities.ReleaseGPULock, jobID).Get(cleanupCtx, nil)
		if releaseErr != nil {
			logger.Error("⚠️ Failed to release GPU lock in defer", "error", releaseErr)
		} else {
			logger.Info("✅ GPU lock released in defer", "job_id", jobID)
		}
	}()

	// Check document size and determine if chunking is needed
	documentSize := int64(0)
	if size, ok := input["document_size"].(int64); ok {
		documentSize = size
	} else if size, ok := input["document_size"].(float64); ok {
		documentSize = int64(size)
	}

	const maxDocumentSize = 5 * 1024 * 1024 // 5MB
	needsChunking := documentSize > maxDocumentSize

	if needsChunking {
		logger.Info("📦 Document requires chunking", "size_mb", float64(documentSize)/(1024*1024))
		// For large documents, we'll process in chunks
		// This is handled by splitting pages into batches during parallel processing
	}

	preprocessOpts := workflow.ActivityOptions{
		StartToCloseTimeout: 10 * time.Minute,
		RetryPolicy: &temporal.RetryPolicy{
			InitialInterval:    time.Second,
			BackoffCoefficient: 2.0,
			MaximumInterval:    time.Minute,
			MaximumAttempts:    3,
		},
	}
	extractionOpts := workflow.ActivityOptions{
		StartToCloseTimeout: 30 * time.Minute,
		RetryPolicy: &temporal.RetryPolicy{
			InitialInterval:    time.Second,
			BackoffCoefficient: 2.0,         // Exponential backoff: 1s, 2s, 4s, ...
			MaximumInterval:    time.Minute, // Cap at 1 minute
			MaximumAttempts:    3,           // Limit to 3 attempts as per requirements
			// Note: Temporal automatically adds jitter (±10%) to prevent thundering herd
		},
	}
	postprocessOpts := workflow.ActivityOptions{
		StartToCloseTimeout: 5 * time.Minute,
		RetryPolicy: &temporal.RetryPolicy{
			InitialInterval:    time.Second,
			BackoffCoefficient: 2.0,
			MaximumInterval:    time.Minute,
			MaximumAttempts:    3,
		},
	}

	var activities *Activities

	// Step 1: Preprocess — converts documents to images, enhances quality
	// Receives full input map so it can parse output_formats + options
	logger.Info("📄 Step 1: Preprocessing")
	preprocessCtx := workflow.WithActivityOptions(ctx, preprocessOpts)
	err = workflow.ExecuteActivity(preprocessCtx, activities.Preprocess, input).Get(ctx, &preprocessOutput)
	if err != nil {
		logger.Error("❌ Preprocessing failed", "error", err)
		return nil, err
	}
	logger.Info("✅ Preprocessing complete", "pages", preprocessOutput.PageCount)

	// Step 2: GLM-OCR Extraction via Triton with parallel page processing
	logger.Info("🧠 Step 2: AI Extraction (parallel)", "formats", preprocessOutput.Options.OutputFormats, "pages", preprocessOutput.PageCount)

	// Build prompt and options for Triton
	prompt := buildPromptForWorkflow(preprocessOutput.Options)
	optionsJSON := buildOptionsJSONForWorkflow(preprocessOutput.Options)

	// Process pages in parallel (max 3 concurrent)
	pageResults, err := processPagesConcurrently(ctx, extractionOpts, &preprocessOutput, prompt, optionsJSON, activities)
	if err != nil {
		logger.Error("❌ Parallel extraction failed", "error", err)

		// Check if this is a timeout error
		if temporal.IsTimeoutError(err) {
			logger.Error("⏱️ Workflow timeout occurred", "error", err)

			// Store partial results
			processingTime := workflow.Now(ctx).Sub(workflowStartTime)
			partialResults := map[string]interface{}{
				"pages_completed": len(partialPageResults),
				"total_pages":     preprocessOutput.PageCount,
			}
			processingMetadata := map[string]interface{}{
				"pages_completed":         len(partialPageResults),
				"total_pages":             preprocessOutput.PageCount,
				"processing_time_seconds": int(processingTime.Seconds()),
				"timeout_type":            "workflow_timeout",
			}

			// Store partial results using activity
			storeOpts := workflow.ActivityOptions{
				StartToCloseTimeout: 30 * time.Second,
				RetryPolicy: &temporal.RetryPolicy{
					InitialInterval:    time.Second,
					BackoffCoefficient: 2.0,
					MaximumInterval:    10 * time.Second,
					MaximumAttempts:    3,
				},
			}
			storeCtx := workflow.WithActivityOptions(ctx, storeOpts)

			storeErr := workflow.ExecuteActivity(storeCtx, queueActivities.StorePartialResults, jobID, partialResults, processingMetadata).Get(ctx, nil)
			if storeErr != nil {
				logger.Error("⚠️ Failed to store partial results", "error", storeErr)
			} else {
				logger.Info("✅ Partial results stored", "pages_completed", len(partialPageResults), "total_pages", preprocessOutput.PageCount)
			}

			return nil, fmt.Errorf("workflow timeout after %d seconds: completed %d of %d pages",
				int(processingTime.Seconds()), len(partialPageResults), preprocessOutput.PageCount)
		}

		// Store failure details for non-timeout errors
		failureOpts := workflow.ActivityOptions{
			StartToCloseTimeout: 30 * time.Second,
			RetryPolicy: &temporal.RetryPolicy{
				InitialInterval:    time.Second,
				BackoffCoefficient: 2.0,
				MaximumInterval:    10 * time.Second,
				MaximumAttempts:    3,
			},
		}
		failureCtx := workflow.WithActivityOptions(ctx, failureOpts)

		// Get retry count from workflow info
		info := workflow.GetInfo(ctx)
		retryCount := int(info.Attempt)

		storeErr := workflow.ExecuteActivity(failureCtx, queueActivities.StoreFailureDetails, jobID, err.Error(), retryCount).Get(ctx, nil)
		if storeErr != nil {
			logger.Error("⚠️ Failed to store failure details", "error", storeErr)
		}

		return nil, err
	}

	// Store page results for potential timeout handling
	partialPageResults = pageResults

	// Aggregate results
	extractionOutput := aggregatePageResults(preprocessOutput.JobID, pageResults, preprocessOutput.PageCount, preprocessOutput.Options)
	logger.Info("✅ Extraction complete", "confidence", extractionOutput.Confidence)

	// Step 3: Post-processing (PII redaction, validation, result envelope)
	// ExtractionOutput carries Options through, including redact_pii
	logger.Info("🔍 Step 3: Post-processing", "redact_pii", extractionOutput.Options.RedactPII)
	postprocessCtx := workflow.WithActivityOptions(ctx, postprocessOpts)
	var finalOutput FinalOutput
	err = workflow.ExecuteActivity(postprocessCtx, activities.PostProcess, &extractionOutput).Get(ctx, &finalOutput)
	if err != nil {
		logger.Error("❌ Post-processing failed", "error", err)
		return nil, err
	}
	logger.Info("✅ Post-processing complete", "result_path", finalOutput.ResultPath)

	result := map[string]interface{}{
		"job_id":      finalOutput.JobID,
		"status":      "COMPLETED",
		"result_path": finalOutput.ResultPath,
		"confidence":  finalOutput.Confidence,
		"page_count":  finalOutput.PageCount,
	}

	logger.Info("🎉 Workflow completed", "job_id", finalOutput.JobID)
	return result, nil
}

// processPagesConcurrently processes pages in parallel with max 3 concurrent workers
// For large documents (>5MB), pages are processed in chunks to manage memory
func processPagesConcurrently(
	ctx workflow.Context,
	activityOpts workflow.ActivityOptions,
	preprocessOutput *PreprocessOutput,
	prompt string,
	optionsJSON string,
	activities *Activities,
) ([]*PageProcessingOutput, error) {
	logger := workflow.GetLogger(ctx)
	pageCount := len(preprocessOutput.ImagePaths)

	// Determine chunk size based on document size
	// For large documents, process in smaller batches to avoid memory issues
	chunkSize := pageCount
	const maxPagesPerChunk = 10 // Process max 10 pages per chunk for large documents

	// Check if we need chunking (document > 5MB or > 10 pages)
	if pageCount > 10 {
		chunkSize = maxPagesPerChunk
		logger.Info("📦 Processing document in chunks", "total_pages", pageCount, "chunk_size", chunkSize)
	}

	// Process pages in chunks
	allResults := make([]*PageProcessingOutput, 0, pageCount)

	for chunkStart := 0; chunkStart < pageCount; chunkStart += chunkSize {
		chunkEnd := chunkStart + chunkSize
		if chunkEnd > pageCount {
			chunkEnd = pageCount
		}

		logger.Info("🔄 Processing chunk", "pages", fmt.Sprintf("%d-%d", chunkStart+1, chunkEnd))

		chunkResults, err := processPageChunk(ctx, activityOpts, preprocessOutput, prompt, optionsJSON, activities, chunkStart, chunkEnd)
		if err != nil {
			return nil, fmt.Errorf("failed to process chunk %d-%d: %w", chunkStart+1, chunkEnd, err)
		}

		allResults = append(allResults, chunkResults...)
		logger.Info("✅ Chunk processed", "pages", fmt.Sprintf("%d-%d", chunkStart+1, chunkEnd))
	}

	return allResults, nil
}

// processPageChunk processes a chunk of pages with max 3 concurrent workers
func processPageChunk(
	ctx workflow.Context,
	activityOpts workflow.ActivityOptions,
	preprocessOutput *PreprocessOutput,
	prompt string,
	optionsJSON string,
	activities *Activities,
	startIdx int,
	endIdx int,
) ([]*PageProcessingOutput, error) {
	logger := workflow.GetLogger(ctx)
	chunkSize := endIdx - startIdx

	// Create channels for coordination
	type pageTask struct {
		index int
		path  string
	}

	// Use workflow.Go for concurrent execution with semaphore
	results := make([]*PageProcessingOutput, chunkSize)
	errors := make([]error, chunkSize)

	// Create a selector for managing concurrent goroutines
	selector := workflow.NewSelector(ctx)
	pendingTasks := 0
	maxConcurrent := 1
	currentIndex := startIdx

	// Function to start a page processing task
	startTask := func(globalIndex int, imagePath string) {
		localIndex := globalIndex - startIdx

		pageInput := &PageProcessingInput{
			JobID:         preprocessOutput.JobID,
			PageNumber:    globalIndex + 1,
			ImagePath:     imagePath,
			Prompt:        prompt,
			OptionsJSON:   optionsJSON,
			PrecisionMode: preprocessOutput.Options.PrecisionMode,
		}

		activityCtx := workflow.WithActivityOptions(ctx, activityOpts)
		future := workflow.ExecuteActivity(activityCtx, activities.ProcessSinglePage, pageInput)

		selector.AddFuture(future, func(f workflow.Future) {
			var result PageProcessingOutput
			err := f.Get(ctx, &result)
			results[localIndex] = &result
			errors[localIndex] = err
			pendingTasks--

			if err != nil {
				logger.Error("❌ Page processing failed", "page", globalIndex+1, "error", err)

				// Check if this is a timeout error
				if temporal.IsTimeoutError(err) {
					logger.Error("⏱️ Page processing timeout", "page", globalIndex+1, "error", err)
				}
			} else {
				logger.Info("✅ Page processed", "page", globalIndex+1, "confidence", result.Confidence)
			}
		})

		pendingTasks++
	}

	// Start initial batch of tasks (up to maxConcurrent)
	for currentIndex < endIdx && pendingTasks < maxConcurrent {
		startTask(currentIndex, preprocessOutput.ImagePaths[currentIndex])
		currentIndex++
	}

	// Process remaining tasks as slots become available
	for currentIndex < endIdx || pendingTasks > 0 {
		selector.Select(ctx)

		// Start new tasks if we have capacity and remaining pages
		for currentIndex < endIdx && pendingTasks < maxConcurrent {
			startTask(currentIndex, preprocessOutput.ImagePaths[currentIndex])
			currentIndex++
		}
	}

	// Check for errors
	var firstError error
	for i, err := range errors {
		if err != nil {
			logger.Error("Page processing error", "page", i+1, "error", err)
			if firstError == nil {
				firstError = err
			}
		}
	}

	if firstError != nil {
		return nil, firstError
	}

	return results, nil
}

// aggregatePageResults combines individual page results into a single extraction output
func aggregatePageResults(jobID string, pageResults []*PageProcessingOutput, pageCount int, options ExtractionOptions) ExtractionOutput {
	type pageEntry struct {
		Page   int         `json:"page"`
		Result interface{} `json:"result"`
	}

	var pageEntries []pageEntry
	var markdownParts []string
	var totalConfidence float64
	successCount := 0

	for _, result := range pageResults {
		if result.Error != "" {
			continue
		}

		// Hoist per-page markdown into aggregated list
		var pageData map[string]json.RawMessage
		if json.Unmarshal([]byte(result.Content), &pageData) == nil {
			if mdRaw, ok := pageData["markdown"]; ok {
				var md string
				if json.Unmarshal(mdRaw, &md) == nil && md != "" {
					markdownParts = append(markdownParts, md)
				}
			}
		}

		var parsedResult interface{}
		if json.Unmarshal([]byte(result.Content), &parsedResult) != nil {
			// Preserve plain text/markdown content without breaking JSON marshaling.
			parsedResult = result.Content
		}

		pageEntries = append(pageEntries, pageEntry{
			Page:   result.PageNumber,
			Result: parsedResult,
		})
		totalConfidence += result.Confidence
		successCount++
	}

	avgConfidence := 0.0
	if successCount > 0 {
		avgConfidence = totalConfidence / float64(successCount)
	}

	// Aggregate pages into canonical output
	aggregated := map[string]interface{}{
		"job_id":     jobID,
		"model":      "zai-org/GLM-OCR",
		"precision":  options.PrecisionMode,
		"pages":      pageEntries,
		"markdown":   strings.Join(markdownParts, "\n\n---\n\n"),
		"page_count": pageCount,
		"confidence": avgConfidence,
	}
	allContentBytes, _ := json.Marshal(aggregated)

	return ExtractionOutput{
		JobID:      jobID,
		RawContent: string(allContentBytes),
		Confidence: avgConfidence,
		PageCount:  pageCount,
		Options:    options,
	}
}

// buildPromptForWorkflow builds the prompt for Triton inference
func buildPromptForWorkflow(opts ExtractionOptions) string {
	// Custom prompt takes priority
	if opts.Prompt != "" {
		return opts.Prompt
	}

	// When the caller requests specific fields, produce a focused extraction prompt
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
		return "Text Recognition:"
	}
}

// buildOptionsJSONForWorkflow builds the options JSON for Triton
func buildOptionsJSONForWorkflow(opts ExtractionOptions) string {
	optionsMap := map[string]interface{}{
		"include_coordinates":     opts.IncludeCoordinates,
		"include_word_confidence": opts.IncludeWordConfidence,
		"include_line_confidence": opts.IncludeLineConfidence,
		"include_page_layout":     opts.IncludePageLayout,
		"language":                opts.Language,
		"granularity":             opts.Granularity,
		"temperature":             opts.Temperature,
		"max_tokens":              opts.MaxTokens,
		"output_format":           strings.TrimSpace(strings.Split(opts.OutputFormats, ",")[0]),
		"extract_fields":          opts.ExtractFields,
	}
	optionsJSON, _ := json.Marshal(optionsMap)
	return string(optionsJSON)
}
