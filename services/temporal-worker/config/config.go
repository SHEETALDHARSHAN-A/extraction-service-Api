package config

import "os"

type WorkerConfig struct {
	TemporalHost       string
	TemporalNamespace  string
	TaskQueue          string
	TritonHost         string
	TritonGRPCPort     string
	PreprocessingHost  string
	PostprocessingHost string
	MinioEndpoint      string
	MinioAccessKey     string
	MinioSecretKey     string
	MinioBucket        string
}

func Load() *WorkerConfig {
	return &WorkerConfig{
		TemporalHost:       getEnv("TEMPORAL_HOST", "localhost:7233"),
		TemporalNamespace:  getEnv("TEMPORAL_NAMESPACE", "default"),
		TaskQueue:          getEnv("TEMPORAL_TASK_QUEUE", "document-processing-task-queue"),
		TritonHost:         getEnv("TRITON_HOST", "localhost"),
		TritonGRPCPort:     getEnv("TRITON_GRPC_PORT", "8001"),
		PreprocessingHost:  getEnv("PREPROCESSING_HOST", "localhost:50051"),
		PostprocessingHost: getEnv("POSTPROCESSING_HOST", "localhost:50052"),
		MinioEndpoint:      getEnv("MINIO_ENDPOINT", "localhost:9000"),
		MinioAccessKey:     getEnv("MINIO_ACCESS_KEY", "minioadmin"),
		MinioSecretKey:     getEnv("MINIO_SECRET_KEY", "minioadmin"),
		MinioBucket:        getEnv("MINIO_BUCKET", "idep-documents"),
	}
}

func getEnv(key, fallback string) string {
	if value, ok := os.LookupEnv(key); ok {
		return value
	}
	return fallback
}
