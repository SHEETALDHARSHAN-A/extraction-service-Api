package tracing

import (
	"context"
	"fmt"
	"io"
	"log"

	"github.com/opentracing/opentracing-go"
	"github.com/opentracing/opentracing-go/ext"
	"github.com/uber/jaeger-client-go"
	"github.com/uber/jaeger-client-go/config"
)

// InitJaeger initializes Jaeger tracer
func InitJaeger(serviceName, jaegerEndpoint string) (opentracing.Tracer, io.Closer, error) {
	cfg := &config.Configuration{
		ServiceName: serviceName,
		Sampler: &config.SamplerConfig{
			Type:  jaeger.SamplerTypeConst,
			Param: 1, // Sample all traces
		},
		Reporter: &config.ReporterConfig{
			LogSpans:           true,
			LocalAgentHostPort: jaegerEndpoint,
		},
	}

	tracer, closer, err := cfg.NewTracer(
		config.Logger(jaeger.StdLogger),
	)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to initialize Jaeger tracer: %w", err)
	}

	opentracing.SetGlobalTracer(tracer)
	log.Printf("✅ Jaeger tracer initialized for service: %s", serviceName)

	return tracer, closer, nil
}

// StartSpanFromContext starts a new span from context
func StartSpanFromContext(ctx context.Context, operationName string) (opentracing.Span, context.Context) {
	span, ctx := opentracing.StartSpanFromContext(ctx, operationName)
	return span, ctx
}

// InjectTraceID injects trace ID into context for logging
func InjectTraceID(ctx context.Context) string {
	span := opentracing.SpanFromContext(ctx)
	if span == nil {
		return ""
	}

	if sc, ok := span.Context().(jaeger.SpanContext); ok {
		return sc.TraceID().String()
	}

	return ""
}

// LogError logs an error to the span
func LogError(span opentracing.Span, err error) {
	if span == nil || err == nil {
		return
	}

	ext.Error.Set(span, true)
	span.LogKV("event", "error", "message", err.Error())
}

// SetSpanTag sets a tag on the span
func SetSpanTag(span opentracing.Span, key string, value interface{}) {
	if span == nil {
		return
	}
	span.SetTag(key, value)
}
