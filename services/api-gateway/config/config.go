package config

import "os"

type Config struct {
	Port              string
	DatabaseURL       string
	RedisURL          string
	MinioEndpoint     string
	MinioAccessKey    string
	MinioSecretKey    string
	MinioBucket       string
	MinioUseSSL       bool
	TemporalHost      string
	TemporalNamespace string
	TemporalTaskQueue string
}

func Load() *Config {
	return &Config{
		Port:              getEnv("API_PORT", "8000"),
		DatabaseURL:       getEnv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/idep"),
		RedisURL:          getEnv("REDIS_URL", "redis://redis:6379/0"),
		MinioEndpoint:     getEnv("MINIO_ENDPOINT", "localhost:9000"),
		MinioAccessKey:    getEnv("MINIO_ACCESS_KEY", "minioadmin"),
		MinioSecretKey:    getEnv("MINIO_SECRET_KEY", "minioadmin"),
		MinioBucket:       getEnv("MINIO_BUCKET", "idep-documents"),
		MinioUseSSL:       getEnv("MINIO_USE_SSL", "false") == "true",
		TemporalHost:      getEnv("TEMPORAL_HOST", "localhost:7233"),
		TemporalNamespace: getEnv("TEMPORAL_NAMESPACE", "default"),
		TemporalTaskQueue: getEnv("TEMPORAL_TASK_QUEUE", "document-processing-task-queue"),
	}
}

func getEnv(key, fallback string) string {
	if value, ok := os.LookupEnv(key); ok {
		return value
	}
	return fallback
}
