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
	"github.com/redis/go-redis/v9"
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

type keyInfo struct {
	key    string
	isTest bool
}

type APIKeyStore struct {
	mu   sync.RWMutex
	keys []keyInfo
}

var globalKeyStore = &APIKeyStore{
	keys: loadAPIKeys(),
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

func (s *APIKeyStore) Reload() {
	newKeys := loadAPIKeys()
	s.mu.Lock()
	defer s.mu.Unlock()
	s.keys = newKeys
}

func (s *APIKeyStore) IsValid(provided string) (bool, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	for _, k := range s.keys {
		if subtle.ConstantTimeCompare([]byte(provided), []byte(k.key)) == 1 {
			return true, k.isTest
		}
	}
	return false, false
}

// ReloadAPIKeys triggers a reload of the API keys from the environment
func ReloadAPIKeys() {
	globalKeyStore.Reload()
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

		valid, isTest := globalKeyStore.IsValid(apiKey)
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

var (
	redisClient  *redis.Client
	localLimiter *rateLimiter
	limit        = 100
	window       = time.Minute
)

// InitRateLimiter initializes the rate limiter with a Redis client (can be nil for local only fallback)
func InitRateLimiter(rdb *redis.Client) {
	redisClient = rdb
	localLimiter = &rateLimiter{
		requests: make(map[string][]time.Time),
	}
}

type rateLimiter struct {
	mu       sync.Mutex
	requests map[string][]time.Time
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

		ctx := c.Request.Context()
		now := time.Now()
		var allowed = false
		var remaining = 0

		if redisClient != nil {
			// Distributed rate limiting with Redis
			redisKey := fmt.Sprintf("ratelimit:%s", key)

			pipe := redisClient.Pipeline()
			// Remove older requests
			pipe.ZRemRangeByScore(ctx, redisKey, "0", fmt.Sprintf("%d", now.Add(-window).UnixMilli()))
			// Add current request
			pipe.ZAdd(ctx, redisKey, redis.Z{Score: float64(now.UnixMilli()), Member: now.UnixNano()})
			// Count requests in window
			countCmd := pipe.ZCard(ctx, redisKey)
			// Expire key after window
			pipe.Expire(ctx, redisKey, window)

			_, err := pipe.Exec(ctx)
			if err == nil {
				requestCount := countCmd.Val()
				if requestCount <= int64(limit) {
					allowed = true
					remaining = limit - int(requestCount)
				}
			} else {
				// Fallback to true if Redis fails
				allowed = true
				remaining = 1
			}
		} else {
			// Memory-based local fallback
			localLimiter.mu.Lock()

			valid := make([]time.Time, 0)
			for _, t := range localLimiter.requests[key] {
				if now.Sub(t) < window {
					valid = append(valid, t)
				}
			}

			if len(valid) < limit {
				valid = append(valid, now)
				allowed = true
				remaining = limit - len(valid)
			}

			localLimiter.requests[key] = valid
			localLimiter.mu.Unlock()
		}

		if !allowed {
			c.AbortWithStatusJSON(http.StatusTooManyRequests, gin.H{
				"error": map[string]interface{}{
					"message": "Rate limit reached. Please slow down.",
					"type":    "rate_limit_error",
					"code":    "rate_limit_exceeded",
				},
			})
			return
		}

		c.Header("x-ratelimit-limit-requests", fmt.Sprintf("%d", limit))
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
