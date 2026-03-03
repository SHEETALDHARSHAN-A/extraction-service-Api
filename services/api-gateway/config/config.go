package config

import (
	"os"
	"strconv"
)

type Config struct {
	Port                    string
	DatabaseURL             string
	RedisURL                string
	MinioEndpoint           string
	MinioAccessKey          string
	MinioSecretKey          string
	MinioBucket             string
	MinioUseSSL             bool
	TemporalHost            string
	TemporalNamespace       string
	TemporalTaskQueue       string
	PaddleOCRServiceURL     string
	GLMOCRServiceURL        string
	EnableLayoutDetection   bool
	CacheLayoutResults      bool
	MaxParallelRegions      int
	ServiceRequestTimeout   int
	ServiceRetryAttempts    int
	CircuitBreakerThreshold int
	CircuitBreakerTimeout   int
}

func Load() *Config {
	return &Config{
		Port:                    getEnv("API_PORT", "8000"),
		DatabaseURL:             getEnv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/idep"),
		RedisURL:                getEnv("REDIS_URL", "redis://redis:6379/0"),
		MinioEndpoint:           getEnv("MINIO_ENDPOINT", "localhost:9000"),
		MinioAccessKey:          getEnv("MINIO_ACCESS_KEY", "minioadmin"),
		MinioSecretKey:          getEnv("MINIO_SECRET_KEY", "minioadmin"),
		MinioBucket:             getEnv("MINIO_BUCKET", "idep-documents"),
		MinioUseSSL:             getEnv("MINIO_USE_SSL", "false") == "true",
		TemporalHost:            getEnv("TEMPORAL_HOST", "localhost:7233"),
		TemporalNamespace:       getEnv("TEMPORAL_NAMESPACE", "default"),
		TemporalTaskQueue:       getEnv("TEMPORAL_TASK_QUEUE", "document-processing-task-queue"),
		PaddleOCRServiceURL:     getEnv("PADDLEOCR_SERVICE_URL", "http://paddleocr-service:8001"),
		GLMOCRServiceURL:        getEnv("GLM_OCR_SERVICE_URL", "http://glm-ocr-service:8002"),
		EnableLayoutDetection:   getEnv("ENABLE_LAYOUT_DETECTION", "false") == "true",
		CacheLayoutResults:      getEnv("CACHE_LAYOUT_RESULTS", "true") == "true",
		MaxParallelRegions:      getEnvInt("MAX_PARALLEL_REGIONS", 5),
		ServiceRequestTimeout:   getEnvInt("SERVICE_REQUEST_TIMEOUT", 30),
		ServiceRetryAttempts:    getEnvInt("SERVICE_RETRY_ATTEMPTS", 3),
		CircuitBreakerThreshold: getEnvInt("CIRCUIT_BREAKER_THRESHOLD", 5),
		CircuitBreakerTimeout:   getEnvInt("CIRCUIT_BREAKER_TIMEOUT", 60),
	}
}

func getEnv(key, fallback string) string {
	if value, ok := os.LookupEnv(key); ok {
		return value
	}
	return fallback
}

func getEnvInt(key string, fallback int) int {
	if value, ok := os.LookupEnv(key); ok {
		if intVal, err := strconv.Atoi(value); err == nil {
			return intVal
		}
	}
	return fallback
}
