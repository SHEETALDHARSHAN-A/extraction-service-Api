package app

import (
	"time"

	"go.temporal.io/sdk/temporal"
	"go.temporal.io/sdk/workflow"
)

func DocumentProcessingWorkflow(ctx workflow.Context, input map[string]interface{}) (map[string]interface{}, error) {
	logger := workflow.GetLogger(ctx)
	logger.Info("🚀 DocumentProcessingWorkflow started",
		"job_id", input["job_id"],
		"filename", input["filename"],
	)

	// Activity options with retry policies per step
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
			InitialInterval:    2 * time.Second,
			BackoffCoefficient: 2.0,
			MaximumInterval:    10 * time.Minute,
			MaximumAttempts:    5,
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

	// Step 1: Preprocess
	logger.Info("📄 Step 1: Preprocessing document")
	preprocessCtx := workflow.WithActivityOptions(ctx, preprocessOpts)
	var preprocessOutput PreprocessOutput
	err := workflow.ExecuteActivity(preprocessCtx, activities.Preprocess, input).Get(ctx, &preprocessOutput)
	if err != nil {
		logger.Error("❌ Preprocessing failed", "error", err)
		return nil, err
	}
	logger.Info("✅ Preprocessing complete", "pages", preprocessOutput.PageCount)

	// Step 2: AI Extraction via Triton
	logger.Info("🧠 Step 2: AI Extraction via Triton")
	extractionCtx := workflow.WithActivityOptions(ctx, extractionOpts)
	var extractionOutput ExtractionOutput
	err = workflow.ExecuteActivity(extractionCtx, activities.CallTriton, &preprocessOutput).Get(ctx, &extractionOutput)
	if err != nil {
		logger.Error("❌ Extraction failed", "error", err)
		return nil, err
	}
	logger.Info("✅ Extraction complete", "confidence", extractionOutput.Confidence)

	// Step 3: Post-processing (PII redaction, validation)
	logger.Info("🔍 Step 3: Post-processing")
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
	}

	logger.Info("🎉 Workflow completed successfully", "job_id", finalOutput.JobID)
	return result, nil
}
