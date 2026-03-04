package logger

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"time"
)

// LogLevel represents the severity of a log entry
type LogLevel string

const (
	LevelDebug LogLevel = "DEBUG"
	LevelInfo  LogLevel = "INFO"
	LevelWarn  LogLevel = "WARN"
	LevelError LogLevel = "ERROR"
)

// StructuredLogger provides JSON-formatted logging
type StructuredLogger struct {
	serviceName string
	logger      *log.Logger
}

// LogEntry represents a structured log entry
type LogEntry struct {
	Timestamp  string                 `json:"timestamp"`
	Level      string                 `json:"level"`
	Service    string                 `json:"service"`
	RequestID  string                 `json:"request_id,omitempty"`
	Message    string                 `json:"message"`
	Context    map[string]interface{} `json:"context,omitempty"`
	Error      string                 `json:"error,omitempty"`
	StackTrace string                 `json:"stack_trace,omitempty"`
}

// NewStructuredLogger creates a new structured logger
func NewStructuredLogger(serviceName string) *StructuredLogger {
	return &StructuredLogger{
		serviceName: serviceName,
		logger:      log.New(os.Stdout, "", 0),
	}
}

// log writes a structured log entry
func (sl *StructuredLogger) log(level LogLevel, requestID, message string, context map[string]interface{}, err error) {
	entry := LogEntry{
		Timestamp: time.Now().UTC().Format(time.RFC3339),
		Level:     string(level),
		Service:   sl.serviceName,
		RequestID: requestID,
		Message:   message,
		Context:   context,
	}

	if err != nil {
		entry.Error = err.Error()
	}

	jsonBytes, marshalErr := json.Marshal(entry)
	if marshalErr != nil {
		// Fallback to plain text if JSON marshaling fails
		sl.logger.Printf("ERROR: Failed to marshal log entry: %v", marshalErr)
		return
	}

	sl.logger.Println(string(jsonBytes))
}

// Debug logs a debug message
func (sl *StructuredLogger) Debug(message string, context map[string]interface{}) {
	sl.log(LevelDebug, "", message, context, nil)
}

// DebugWithRequest logs a debug message with request ID
func (sl *StructuredLogger) DebugWithRequest(requestID, message string, context map[string]interface{}) {
	sl.log(LevelDebug, requestID, message, context, nil)
}

// Info logs an info message
func (sl *StructuredLogger) Info(message string, context map[string]interface{}) {
	sl.log(LevelInfo, "", message, context, nil)
}

// InfoWithRequest logs an info message with request ID
func (sl *StructuredLogger) InfoWithRequest(requestID, message string, context map[string]interface{}) {
	sl.log(LevelInfo, requestID, message, context, nil)
}

// Warn logs a warning message
func (sl *StructuredLogger) Warn(message string, context map[string]interface{}) {
	sl.log(LevelWarn, "", message, context, nil)
}

// WarnWithRequest logs a warning message with request ID
func (sl *StructuredLogger) WarnWithRequest(requestID, message string, context map[string]interface{}) {
	sl.log(LevelWarn, requestID, message, context, nil)
}

// Error logs an error message
func (sl *StructuredLogger) Error(message string, err error, context map[string]interface{}) {
	sl.log(LevelError, "", message, context, err)
}

// ErrorWithRequest logs an error message with request ID
func (sl *StructuredLogger) ErrorWithRequest(requestID, message string, err error, context map[string]interface{}) {
	sl.log(LevelError, requestID, message, context, err)
}

// LogExtractionRequest logs an extraction request with standard fields
func (sl *StructuredLogger) LogExtractionRequest(requestID, status string, documentSize int64, processingTimeMs int64, context map[string]interface{}) {
	if context == nil {
		context = make(map[string]interface{})
	}
	context["document_size"] = documentSize
	context["processing_time_ms"] = processingTimeMs
	context["status"] = status

	message := fmt.Sprintf("Extraction request %s", status)
	sl.log(LevelInfo, requestID, message, context, nil)
}

// LogHealthCheck logs a health check event
func (sl *StructuredLogger) LogHealthCheck(status string, context map[string]interface{}) {
	if context == nil {
		context = make(map[string]interface{})
	}
	context["health_status"] = status

	message := fmt.Sprintf("Health check: %s", status)
	sl.log(LevelInfo, "", message, context, nil)
}

// LogQueueMetrics logs queue metrics
func (sl *StructuredLogger) LogQueueMetrics(queueLength int64, avgWaitTime float64, throughput float64, context map[string]interface{}) {
	if context == nil {
		context = make(map[string]interface{})
	}
	context["queue_length"] = queueLength
	context["avg_wait_time_seconds"] = avgWaitTime
	context["throughput_per_hour"] = throughput

	message := "Queue metrics"
	sl.log(LevelInfo, "", message, context, nil)
}
