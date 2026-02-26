package app

import (
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
			InitialInterval:    5 * time.Second,
			BackoffCoefficient: 2.0,
			MaximumInterval:    2 * time.Minute,
			MaximumAttempts:    10,
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
	var preprocessOutput PreprocessOutput
	err := workflow.ExecuteActivity(preprocessCtx, activities.Preprocess, input).Get(ctx, &preprocessOutput)
	if err != nil {
		logger.Error("❌ Preprocessing failed", "error", err)
		return nil, err
	}
	logger.Info("✅ Preprocessing complete", "pages", preprocessOutput.PageCount)

	// Step 2: GLM-OCR Extraction via Triton
	// PreprocessOutput carries Options through, including output_formats + prompt
	logger.Info("🧠 Step 2: AI Extraction", "formats", preprocessOutput.Options.OutputFormats)
	extractionCtx := workflow.WithActivityOptions(ctx, extractionOpts)
	var extractionOutput ExtractionOutput
	err = workflow.ExecuteActivity(extractionCtx, activities.CallTriton, &preprocessOutput).Get(ctx, &extractionOutput)
	if err != nil {
		logger.Error("❌ Extraction failed", "error", err)
		return nil, err
	}
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
