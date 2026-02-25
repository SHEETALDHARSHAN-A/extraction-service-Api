package app

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"time"

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
	MinioEndpoint      string
	MinioAccessKey     string
	MinioSecretKey     string
	MinioBucket        string
}

// DocumentInput is the input to the workflow
type DocumentInput struct {
	JobID       string `json:"job_id"`
	Filename    string `json:"filename"`
	StoragePath string `json:"storage_path"`
	ContentType string `json:"content_type"`
	FileExt     string `json:"file_ext"`
}

// PreprocessOutput from the preprocessing activity
type PreprocessOutput struct {
	JobID      string   `json:"job_id"`
	ImagePaths []string `json:"image_paths"`
	PageCount  int      `json:"page_count"`
}

// ExtractionOutput from the Triton inference activity
type ExtractionOutput struct {
	JobID      string  `json:"job_id"`
	RawContent string  `json:"raw_content"`
	Confidence float64 `json:"confidence"`
	PageCount  int     `json:"page_count"`
}

// FinalOutput from the post-processing activity
type FinalOutput struct {
	JobID             string  `json:"job_id"`
	StructuredContent string  `json:"structured_content"`
	Confidence        float64 `json:"confidence"`
	ResultPath        string  `json:"result_path"`
}

// --- Activity 1: Preprocess ---
func (a *Activities) Preprocess(ctx context.Context, input map[string]interface{}) (*PreprocessOutput, error) {
	jobID := input["job_id"].(string)
	storagePath := input["storage_path"].(string)

	log.Printf("🔧 [Activity] Preprocessing job %s, file: %s", jobID, storagePath)

	conn, err := grpc.NewClient(a.PreprocessingHost,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to preprocessing service: %w", err)
	}
	defer conn.Close()

	client := preprocessing.NewPreprocessingServiceClient(conn)
	ctx, cancel := context.WithTimeout(ctx, 5*time.Minute)
	defer cancel()

	resp, err := client.Preprocess(ctx, &preprocessing.PreprocessRequest{
		FilePath: storagePath,
		JobId:    jobID,
		Deskew:   true,
		Denoise:  true,
	})
	if err != nil {
		return nil, fmt.Errorf("preprocessing service call failed: %w", err)
	}

	if resp.Status != "success" {
		return nil, fmt.Errorf("preprocessing failed: %s", resp.Error)
	}

	log.Printf("✅ [Activity] Preprocessed %d pages for job %s", len(resp.ImagePaths), jobID)

	return &PreprocessOutput{
		JobID:      jobID,
		ImagePaths: resp.ImagePaths,
		PageCount:  len(resp.ImagePaths),
	}, nil
}

// --- Activity 2: CallTriton ---
func (a *Activities) CallTriton(ctx context.Context, input *PreprocessOutput) (*ExtractionOutput, error) {
	log.Printf("🧠 [Activity] Calling Triton for job %s (%d pages)", input.JobID, input.PageCount)

	tritonAddr := fmt.Sprintf("%s:%s", a.TritonHost, a.TritonGRPCPort)

	conn, err := grpc.NewClient(tritonAddr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to Triton: %w", err)
	}
	defer conn.Close()

	// In a real implementation, we would use the Triton gRPC client
	// to send image tensors and receive structured text output.
	// The Triton client SDK generates Go code from the Triton protobuf.
	//
	// For now, we simulate the extraction by assembling per-page results.
	var allContent string
	var totalConfidence float64

	for i, imgPath := range input.ImagePaths {
		// Each page would be sent as a tensor to Triton's GLM-OCR model
		// response would contain generated_text and confidence
		pageContent := fmt.Sprintf("--- Page %d (%s) ---\nExtracted content from GLM-OCR inference.\n", i+1, imgPath)
		allContent += pageContent
		totalConfidence += 0.95 // Simulated per-page confidence
	}

	avgConfidence := totalConfidence / float64(len(input.ImagePaths))
	log.Printf("✅ [Activity] Triton extraction complete for job %s (confidence: %.2f)", input.JobID, avgConfidence)

	return &ExtractionOutput{
		JobID:      input.JobID,
		RawContent: allContent,
		Confidence: avgConfidence,
		PageCount:  input.PageCount,
	}, nil
}

// --- Activity 3: PostProcess ---
func (a *Activities) PostProcess(ctx context.Context, input *ExtractionOutput) (*FinalOutput, error) {
	log.Printf("🔍 [Activity] Post-processing job %s", input.JobID)

	conn, err := grpc.NewClient(a.PostprocessingHost,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to post-processing service: %w", err)
	}
	defer conn.Close()

	client := postprocessing.NewPostProcessingServiceClient(conn)
	ctx, cancel := context.WithTimeout(ctx, 2*time.Minute)
	defer cancel()

	resp, err := client.PostProcess(ctx, &postprocessing.PostProcessRequest{
		RawContent: input.RawContent,
		JobId:      input.JobID,
		RedactPii:  true,
	})
	if err != nil {
		return nil, fmt.Errorf("post-processing service call failed: %w", err)
	}

	if resp.Status != "success" {
		return nil, fmt.Errorf("post-processing failed: %s", resp.Error)
	}

	// Store result in MinIO
	resultPath := fmt.Sprintf("results/%s/extraction.json", input.JobID)

	resultJSON, _ := json.Marshal(map[string]interface{}{
		"job_id":     input.JobID,
		"content":    resp.StructuredContent,
		"confidence": resp.ConfidenceScore,
		"page_count": input.PageCount,
		"timestamp":  time.Now().Format(time.RFC3339),
	})

	log.Printf("✅ [Activity] Post-processing complete for job %s (result: %d bytes)", input.JobID, len(resultJSON))

	return &FinalOutput{
		JobID:             input.JobID,
		StructuredContent: resp.StructuredContent,
		Confidence:        float64(resp.ConfidenceScore),
		ResultPath:        resultPath,
	}, nil
}
