package chunking

import (
	"time"
)

type Config struct {
	MaxChunkSize     int     `json:"max_chunk_size"`
	MinChunkSize     int     `json:"min_chunk_size"`
	OverlapSize      int     `json:"overlap_size"`
	
	GeminiAPIKey     string  `json:"gemini_api_key"`
	GeminiModel      string  `json:"gemini_model"`
	
	ConfidenceThreshold float64 `json:"confidence_threshold"`
	BatchSize          int     `json:"batch_size"`
	MaxRetries         int     `json:"max_retries"`
	RequestTimeout     time.Duration `json:"request_timeout"`
	
	QdrantURL          string `json:"qdrant_url"`
	QdrantCollection   string `json:"qdrant_collection"`
	
	MaxConcurrentRequests int `json:"max_concurrent_requests"`
	RateLimitRPS         int `json:"rate_limit_rps"`
}

func DefaultConfig() *Config {
	return &Config{
		MaxChunkSize:          1000,
		MinChunkSize:          100,
		OverlapSize:           50,
		GeminiModel:          "gemini-1.5-pro",
		ConfidenceThreshold:  0.7,
		BatchSize:            10,
		MaxRetries:           3,
		RequestTimeout:       30 * time.Second,
		QdrantCollection:     "document_chunks",
		QdrantURL:           "http://localhost:6333",
		MaxConcurrentRequests: 5,
		RateLimitRPS:        10,
	}
}
