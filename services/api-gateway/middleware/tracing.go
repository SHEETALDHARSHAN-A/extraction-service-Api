package middleware

import (
	"github.com/gin-gonic/gin"
	"github.com/opentracing/opentracing-go"
	"github.com/opentracing/opentracing-go/ext"
)

// TracingMiddleware adds distributed tracing to requests
func TracingMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		tracer := opentracing.GlobalTracer()

		// Extract span context from headers if present
		spanCtx, _ := tracer.Extract(
			opentracing.HTTPHeaders,
			opentracing.HTTPHeadersCarrier(c.Request.Header),
		)

		// Start a new span
		span := tracer.StartSpan(
			c.Request.URL.Path,
			ext.RPCServerOption(spanCtx),
		)
		defer span.Finish()

		// Set standard tags
		ext.HTTPMethod.Set(span, c.Request.Method)
		ext.HTTPUrl.Set(span, c.Request.URL.String())
		ext.Component.Set(span, "api-gateway")

		// Store span in context
		ctx := opentracing.ContextWithSpan(c.Request.Context(), span)
		c.Request = c.Request.WithContext(ctx)

		// Get trace ID for logging
		if sc, ok := span.Context().(interface{ TraceID() interface{ String() string } }); ok {
			traceID := sc.TraceID().String()
			c.Set("trace_id", traceID)
			c.Header("X-Trace-ID", traceID)
		}

		c.Next()

		// Set response status
		ext.HTTPStatusCode.Set(span, uint16(c.Writer.Status()))

		// Mark as error if status >= 400
		if c.Writer.Status() >= 400 {
			ext.Error.Set(span, true)
		}
	}
}
