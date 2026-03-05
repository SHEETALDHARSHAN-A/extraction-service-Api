package middleware

import (
	"crypto/subtle"
	"fmt"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
)

/*
API Key Authentication

Usage:
  Authorization: Bearer tp-proj-xxxxxxxxxxxx

Keys are loaded from IDEP_API_KEYS environment variable:
  IDEP_API_KEYS=tp-proj-abc123,tp-proj-def456,tp-test-xyz789

Key prefixes:
  tp-proj-*   Production keys (full access)
  tp-test-*   Test keys (full access, marked as test in logs)

No roles, no JWT, no tokens to manage.
*/

// ─── API Key Store ───

var apiKeys = loadAPIKeys()

type keyInfo struct {
	key    string
	isTest bool
}

func loadAPIKeys() []keyInfo {
	raw := getEnvAny([]string{"IDEP_API_KEYS", "API_KEYS"}, "tp-proj-dev-key-123")
	var keys []keyInfo
	for _, k := range strings.Split(raw, ",") {
		k = strings.TrimSpace(k)
		if k != "" {
			// Support legacy entries like "api-key:role" while using the key part only.
			if idx := strings.Index(k, ":"); idx > 0 {
				k = strings.TrimSpace(k[:idx])
			}
			keys = append(keys, keyInfo{
				key:    k,
				isTest: strings.HasPrefix(k, "tp-test-"),
			})
		}
	}
	return keys
}

func isValidKey(provided string) (bool, bool) {
	for _, k := range apiKeys {
		if subtle.ConstantTimeCompare([]byte(provided), []byte(k.key)) == 1 {
			return true, k.isTest
		}
	}
	return false, false
}

// ─── Auth Middleware ───

func Auth() gin.HandlerFunc {
	return func(c *gin.Context) {
		apiKey := extractAPIKey(c)
		if apiKey == "" {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{
				"error": map[string]interface{}{
					"message": "Invalid Authentication",
					"type":    "invalid_request_error",
					"code":    "invalid_api_key",
				},
			})
			return
		}

		valid, isTest := isValidKey(apiKey)
		if !valid {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{
				"error": map[string]interface{}{
					"message": "Incorrect API key provided. You can find your API key at the dashboard.",
					"type":    "invalid_request_error",
					"code":    "invalid_api_key",
				},
			})
			return
		}

		// Set context (no roles — just authenticated or not)
		c.Set("api_key", apiKey)
		c.Set("is_test", isTest)
		c.Next()
	}
}

func extractAPIKey(c *gin.Context) string {
	// 1. Authorization: Bearer sk-proj-...
	if auth := c.GetHeader("Authorization"); auth != "" {
		parts := strings.SplitN(auth, " ", 2)
		if len(parts) == 2 && strings.ToLower(parts[0]) == "bearer" {
			return strings.TrimSpace(parts[1])
		}
	}
	// 2. X-API-Key header (backwards compat)
	if key := c.GetHeader("X-API-Key"); key != "" {
		return key
	}
	return ""
}

// ─── Rate Limiting (per API key, 100 req/min) ───

type rateLimiter struct {
	mu       sync.Mutex
	requests map[string][]time.Time
	limit    int
	window   time.Duration
}

var limiter = &rateLimiter{
	requests: make(map[string][]time.Time),
	limit:    100,
	window:   time.Minute,
}

func RateLimit() gin.HandlerFunc {
	return func(c *gin.Context) {
		// Rate limit by API key or IP
		key := c.ClientIP()
		if auth := c.GetHeader("Authorization"); auth != "" {
			key = auth
		} else if apiKey := c.GetHeader("X-API-Key"); apiKey != "" {
			key = apiKey
		}

		limiter.mu.Lock()
		now := time.Now()

		valid := make([]time.Time, 0)
		for _, t := range limiter.requests[key] {
			if now.Sub(t) < limiter.window {
				valid = append(valid, t)
			}
		}
		limiter.requests[key] = valid

		if len(valid) >= limiter.limit {
			limiter.mu.Unlock()
			c.AbortWithStatusJSON(http.StatusTooManyRequests, gin.H{
				"error": map[string]interface{}{
					"message": "Rate limit reached. Please slow down.",
					"type":    "rate_limit_error",
					"code":    "rate_limit_exceeded",
				},
			})
			return
		}

		limiter.requests[key] = append(limiter.requests[key], now)
		remaining := limiter.limit - len(valid) - 1
		limiter.mu.Unlock()

		c.Header("x-ratelimit-limit-requests", "100")
		c.Header("x-ratelimit-remaining-requests", fmt.Sprintf("%d", remaining))
		c.Header("x-ratelimit-reset-requests", "60s")
		c.Next()
	}
}

// ─── Util ───

func getEnvDefault(key, fallback string) string {
	if v, ok := os.LookupEnv(key); ok {
		return v
	}
	return fallback
}

func getEnvAny(keys []string, fallback string) string {
	for _, key := range keys {
		if v, ok := os.LookupEnv(key); ok {
			return v
		}
	}
	return fallback
}
