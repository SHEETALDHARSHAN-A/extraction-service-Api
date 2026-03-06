package config

import (
	"os"
	"strconv"
	"strings"
)

type Config struct {
	Port                       string
	UploadMaxDocumentSizeBytes int64
	DatabaseDriver             string
	DatabaseURL                string
	RedisURL                   string
	StorageDriver              string // "minio" (default) or "local"
	LocalStorageRoot           string // root dir for local storage (default: .local/data/storage)
	MinioEndpoint              string
	MinioAccessKey             string
	MinioSecretKey             string
	MinioBucket                string
	MinioUseSSL                bool
	TemporalHost               string
	TemporalNamespace          string
	TemporalTaskQueue          string
	PaddleOCRServiceURL        string
	GLMOCRServiceURL           string
	EnableLayoutDetection      bool
	CacheLayoutResults         bool
	MaxParallelRegions         int
	ServiceRequestTimeout      int
	ServiceRetryAttempts       int
	CircuitBreakerThreshold    int
	CircuitBreakerTimeout      int
	JaegerEndpoint             string
}

const (
	defaultPort                    = "8000"
	defaultUploadMaxDocumentSizeMB = 10
	defaultDatabaseDriver          = "postgres"
	defaultDatabaseURL             = "postgresql://postgres:postgres@localhost:5432/idep"
	defaultRedisURL                = "redis://localhost:6379/0"
	defaultStorageDriver           = "minio"
	defaultLocalStorageRoot        = ".local/data/storage"
	defaultMinioEndpoint           = "localhost:9000"
	defaultMinioAccessKey          = "minioadmin"
	defaultMinioSecretKey          = "minioadmin"
	defaultMinioBucket             = "idep-documents"
	defaultTemporalHost            = "localhost:7233"
	defaultTemporalNamespace       = "default"
	defaultTemporalTaskQueue       = "document-processing-task-queue"
	defaultPaddleOCRServiceURL     = "grpc://paddleocr-service:50061"
	defaultGLMOCRServiceURL        = "grpc://glm-ocr-service:50062"
	defaultMaxParallelRegions      = 5
	defaultServiceRequestTimeout   = 30
	defaultServiceRetryAttempts    = 3
	defaultCircuitBreakerThreshold = 5
	defaultCircuitBreakerTimeout   = 60
	defaultJaegerAgentEndpoint     = "localhost:6831"
)

func Load() *Config {
	return &Config{
		Port:                       getEnv("API_PORT", defaultPort),
		UploadMaxDocumentSizeBytes: int64(getEnvInt("UPLOAD_MAX_DOCUMENT_SIZE_MB", defaultUploadMaxDocumentSizeMB)) * 1024 * 1024,
		DatabaseDriver:             getEnv("DATABASE_DRIVER", defaultDatabaseDriver),
		DatabaseURL:                getEnv("DATABASE_URL", defaultDatabaseURL),
		RedisURL:                   getEnv("REDIS_URL", defaultRedisURL),
		StorageDriver:              getEnv("STORAGE_DRIVER", defaultStorageDriver),
		LocalStorageRoot:           getEnv("LOCAL_STORAGE_ROOT", defaultLocalStorageRoot),
		MinioEndpoint:              getEnv("MINIO_ENDPOINT", defaultMinioEndpoint),
		MinioAccessKey:             getEnv("MINIO_ACCESS_KEY", defaultMinioAccessKey),
		MinioSecretKey:             getEnv("MINIO_SECRET_KEY", defaultMinioSecretKey),
		MinioBucket:                getEnv("MINIO_BUCKET", defaultMinioBucket),
		MinioUseSSL:                getEnvBool("MINIO_USE_SSL", false),
		TemporalHost:               getEnv("TEMPORAL_HOST", defaultTemporalHost),
		TemporalNamespace:          getEnv("TEMPORAL_NAMESPACE", defaultTemporalNamespace),
		TemporalTaskQueue:          getEnv("TEMPORAL_TASK_QUEUE", defaultTemporalTaskQueue),
		PaddleOCRServiceURL:        getEnv("PADDLEOCR_SERVICE_URL", defaultPaddleOCRServiceURL),
		GLMOCRServiceURL:           getEnv("GLM_OCR_SERVICE_URL", defaultGLMOCRServiceURL),
		EnableLayoutDetection:      getEnvBool("ENABLE_LAYOUT_DETECTION", false),
		CacheLayoutResults:         getEnvBool("CACHE_LAYOUT_RESULTS", true),
		MaxParallelRegions:         getEnvInt("MAX_PARALLEL_REGIONS", defaultMaxParallelRegions),
		ServiceRequestTimeout:      getEnvIntAny([]string{"SERVICE_REQUEST_TIMEOUT", "SERVICE_TIMEOUT_SECONDS"}, defaultServiceRequestTimeout),
		ServiceRetryAttempts:       getEnvInt("SERVICE_RETRY_ATTEMPTS", defaultServiceRetryAttempts),
		CircuitBreakerThreshold:    getEnvInt("CIRCUIT_BREAKER_THRESHOLD", defaultCircuitBreakerThreshold),
		CircuitBreakerTimeout:      getEnvIntAny([]string{"CIRCUIT_BREAKER_TIMEOUT", "CIRCUIT_BREAKER_TIMEOUT_SECONDS"}, defaultCircuitBreakerTimeout),
		JaegerEndpoint:             getEnv("JAEGER_AGENT_ENDPOINT", defaultJaegerAgentEndpoint),
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

func getEnvIntAny(keys []string, fallback int) int {
	for _, key := range keys {
		if value, ok := os.LookupEnv(key); ok {
			if intVal, err := strconv.Atoi(value); err == nil {
				return intVal
			}
		}
	}
	return fallback
}

func getEnvBool(key string, fallback bool) bool {
	if value, ok := os.LookupEnv(key); ok {
		return strings.EqualFold(value, "true")
	}
	return fallback
}
