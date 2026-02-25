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
	"github.com/golang-jwt/jwt/v5"
)

// --- JWT Authentication Middleware (§2.6) ---

var jwtSecret = []byte(getEnvDefault("JWT_SECRET", "idep-dev-secret-change-in-production"))

type Claims struct {
	UserID string `json:"user_id"`
	Role   string `json:"role"` // admin, operator, viewer
	jwt.RegisteredClaims
}

func JWTAuth() gin.HandlerFunc {
	return func(c *gin.Context) {
		authHeader := c.GetHeader("Authorization")
		if authHeader == "" {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "Missing Authorization header"})
			return
		}

		parts := strings.SplitN(authHeader, " ", 2)
		if len(parts) != 2 || strings.ToLower(parts[0]) != "bearer" {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "Invalid Authorization format. Use: Bearer <token>"})
			return
		}

		token, err := jwt.ParseWithClaims(parts[1], &Claims{}, func(token *jwt.Token) (interface{}, error) {
			return jwtSecret, nil
		})
		if err != nil || !token.Valid {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "Invalid or expired token"})
			return
		}

		claims, ok := token.Claims.(*Claims)
		if !ok {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "Invalid token claims"})
			return
		}

		// Set user context
		c.Set("user_id", claims.UserID)
		c.Set("role", claims.Role)
		c.Next()
	}
}

// GenerateToken creates a JWT token (for testing/dev login)
func GenerateToken(userID, role string) (string, error) {
	claims := &Claims{
		UserID: userID,
		Role:   role,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(15 * time.Minute)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
			Issuer:    "idep-api-gateway",
		},
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString(jwtSecret)
}

// --- API Key Authentication ---

var validAPIKeys = loadAPIKeys()

func APIKeyAuth() gin.HandlerFunc {
	return func(c *gin.Context) {
		apiKey := c.GetHeader("X-API-Key")
		if apiKey == "" {
			apiKey = c.Query("api_key")
		}
		if apiKey == "" {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "Missing API key"})
			return
		}

		role, ok := validAPIKeys[apiKey]
		if !ok {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "Invalid API key"})
			return
		}

		c.Set("user_id", "api-key-user")
		c.Set("role", role)
		c.Next()
	}
}

func loadAPIKeys() map[string]string {
	keys := make(map[string]string)
	// Load from environment (comma-separated key:role pairs)
	raw := getEnvDefault("API_KEYS", "dev-key-123:admin")
	for _, pair := range strings.Split(raw, ",") {
		parts := strings.SplitN(strings.TrimSpace(pair), ":", 2)
		if len(parts) == 2 {
			keys[parts[0]] = parts[1]
		}
	}
	return keys
}

// --- Combined Auth: Accept JWT OR API Key ---

func Auth() gin.HandlerFunc {
	return func(c *gin.Context) {
		// Try JWT first
		if authHeader := c.GetHeader("Authorization"); authHeader != "" {
			JWTAuth()(c)
			return
		}
		// Fall back to API Key
		if apiKey := c.GetHeader("X-API-Key"); apiKey != "" {
			APIKeyAuth()(c)
			return
		}
		if apiKey := c.Query("api_key"); apiKey != "" {
			APIKeyAuth()(c)
			return
		}

		c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{
			"error": "Authentication required. Provide Bearer token or X-API-Key header.",
		})
	}
}

// --- RBAC Middleware ---

func RequireRole(roles ...string) gin.HandlerFunc {
	return func(c *gin.Context) {
		userRole, exists := c.Get("role")
		if !exists {
			c.AbortWithStatusJSON(http.StatusForbidden, gin.H{"error": "No role assigned"})
			return
		}

		for _, r := range roles {
			if subtle.ConstantTimeCompare([]byte(userRole.(string)), []byte(r)) == 1 {
				c.Next()
				return
			}
		}

		c.AbortWithStatusJSON(http.StatusForbidden, gin.H{
			"error":          "Insufficient permissions",
			"required_roles": roles,
		})
	}
}

// --- Rate Limiting Middleware (§2.6: 100 req/min per key) ---

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
		key := c.ClientIP()
		if apiKey := c.GetHeader("X-API-Key"); apiKey != "" {
			key = apiKey
		}

		limiter.mu.Lock()
		now := time.Now()

		// Clean old entries
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
				"error":       "Rate limit exceeded",
				"limit":       limiter.limit,
				"window":      limiter.window.String(),
				"retry_after": limiter.window.Seconds(),
			})
			return
		}

		limiter.requests[key] = append(limiter.requests[key], now)
		limiter.mu.Unlock()

		c.Header("X-RateLimit-Limit", "100")
		c.Header("X-RateLimit-Remaining", fmt.Sprintf("%d", limiter.limit-len(valid)-1))
		c.Next()
	}
}

func getEnvDefault(key, fallback string) string {
	if v, ok := os.LookupEnv(key); ok {
		return v
	}
	return fallback
}
