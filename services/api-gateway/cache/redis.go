package cache

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"time"

	"github.com/redis/go-redis/v9"
)

// RedisCache provides document-level and result-level caching
//
// Cache Strategy:
//   - Document Dedup:  SHA-256(file content) → existing job_id
//     Avoids reprocessing identical documents entirely
//   - Result Cache:    job_id → extraction result JSON
//     Fast retrieval without hitting MinIO
//   - Rate State:      Used by rate limiter (already in auth.go, can migrate here)
type RedisCache struct {
	client *redis.Client
	prefix string
}

type CachedResult struct {
	JobID      string  `json:"job_id"`
	Status     string  `json:"status"`
	ResultPath string  `json:"result_path"`
	Confidence float64 `json:"confidence"`
	PageCount  int     `json:"page_count"`
	CachedAt   string  `json:"cached_at"`
}

// New creates a Redis cache client
func New(redisURL string) (*RedisCache, error) {
	opts, err := redis.ParseURL(redisURL)
	if err != nil {
		// Fallback: treat as host:port
		opts = &redis.Options{Addr: redisURL, DB: 0}
	}

	client := redis.NewClient(opts)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := client.Ping(ctx).Err(); err != nil {
		return nil, fmt.Errorf("redis connection failed: %w", err)
	}

	log.Println("✅ Redis cache connected")
	return &RedisCache{client: client, prefix: "idep:"}, nil
}

// ─── Document Dedup ───

// HashContent computes SHA-256 of a reader (file content)
func HashContent(r io.Reader) (string, error) {
	h := sha256.New()
	if _, err := io.Copy(h, r); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

// CheckDuplicate returns the existing job ID if this content was already processed
func (c *RedisCache) CheckDuplicate(ctx context.Context, contentHash string) (string, bool) {
	key := c.prefix + "dedup:" + contentHash
	jobID, err := c.client.Get(ctx, key).Result()
	if err == redis.Nil {
		return "", false
	}
	if err != nil {
		log.Printf("⚠️ Redis dedup check error: %v", err)
		return "", false
	}
	return jobID, true
}

// MarkProcessed stores the content hash → job ID mapping
// TTL: 24 hours (documents don't change, but we don't cache forever)
func (c *RedisCache) MarkProcessed(ctx context.Context, contentHash, jobID string) {
	key := c.prefix + "dedup:" + contentHash
	if err := c.client.Set(ctx, key, jobID, 24*time.Hour).Err(); err != nil {
		log.Printf("⚠️ Redis dedup set error: %v", err)
	}
}

// ─── Result Cache ───

// GetResult retrieves a cached extraction result
func (c *RedisCache) GetResult(ctx context.Context, jobID string) (*CachedResult, bool) {
	key := c.prefix + "result:" + jobID
	data, err := c.client.Get(ctx, key).Result()
	if err == redis.Nil {
		return nil, false
	}
	if err != nil {
		log.Printf("⚠️ Redis result get error: %v", err)
		return nil, false
	}

	var result CachedResult
	if err := json.Unmarshal([]byte(data), &result); err != nil {
		return nil, false
	}
	return &result, true
}

// SetResult caches an extraction result (TTL: 1 hour)
func (c *RedisCache) SetResult(ctx context.Context, jobID string, result *CachedResult) {
	key := c.prefix + "result:" + jobID
	data, err := json.Marshal(result)
	if err != nil {
		return
	}
	if err := c.client.Set(ctx, key, data, 1*time.Hour).Err(); err != nil {
		log.Printf("⚠️ Redis result set error: %v", err)
	}
}

// InvalidateResult removes a cached result (e.g., on reprocessing)
func (c *RedisCache) InvalidateResult(ctx context.Context, jobID string) {
	key := c.prefix + "result:" + jobID
	c.client.Del(ctx, key)
}

// ─── Job Status Cache ───

// CacheJobStatus stores job status for fast polling (TTL: 5 min)
func (c *RedisCache) CacheJobStatus(ctx context.Context, jobID, status string) {
	key := c.prefix + "status:" + jobID
	c.client.Set(ctx, key, status, 5*time.Minute)
}

// GetJobStatus returns cached status or empty string
func (c *RedisCache) GetJobStatus(ctx context.Context, jobID string) string {
	key := c.prefix + "status:" + jobID
	val, err := c.client.Get(ctx, key).Result()
	if err != nil {
		return ""
	}
	return val
}

// ─── Stats ───

// GetCacheStats returns cache hit/miss counts
func (c *RedisCache) GetCacheStats(ctx context.Context) map[string]int64 {
	info := c.client.Info(ctx, "stats").Val()
	_ = info // Could parse hit/miss from INFO stats

	// Count keys by pattern
	dedupCount, _ := c.countKeys(ctx, c.prefix+"dedup:*")
	resultCount, _ := c.countKeys(ctx, c.prefix+"result:*")
	statusCount, _ := c.countKeys(ctx, c.prefix+"status:*")

	return map[string]int64{
		"dedup_entries":  dedupCount,
		"result_entries": resultCount,
		"status_entries": statusCount,
	}
}

func (c *RedisCache) countKeys(ctx context.Context, pattern string) (int64, error) {
	var cursor uint64
	var count int64
	for {
		keys, nextCursor, err := c.client.Scan(ctx, cursor, pattern, 100).Result()
		if err != nil {
			return 0, err
		}
		count += int64(len(keys))
		cursor = nextCursor
		if cursor == 0 {
			break
		}
	}
	return count, nil
}
