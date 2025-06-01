package config

import (
	"encoding/json"
	"fmt"
	"os"
)

type Config struct {
	Kafka  KafkaConfig  `json:"kafka"`
	Qdrant QdrantConfig `json:"qdrant"`
	Gemini GeminiConfig `json:"gemini"`
}

type KafkaConfig struct {
	BootstrapServers string `json:"bootstrap_servers"`
	GroupID          string `json:"group_id"`
	Topic            string `json:"topic"`
	AutoOffsetReset  string `json:"auto_offset_reset"`
}

type QdrantConfig struct {
	URL        string `json:"url"`
	APIKey     string `json:"api_key"`
	Collection string `json:"collection"`
	VectorSize int    `json:"vector_size"`
}

type GeminiConfig struct {
	APIKey string `json:"api_key"`
	Model  string `json:"model"`
}

// LoadConfig reads configuration from a JSON file
func LoadConfig(configPath string) (*Config, error) {
	file, err := os.Open(configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to open config file: %w", err)
	}
	defer file.Close()

	var config Config
	decoder := json.NewDecoder(file)
	err = decoder.Decode(&config)
	if err != nil {
		return nil, fmt.Errorf("failed to decode config: %w", err)
	}

	// Set defaults if not provided
	if config.Kafka.BootstrapServers == "" {
		config.Kafka.BootstrapServers = "localhost:9092"
	}
	if config.Kafka.GroupID == "" {
		config.Kafka.GroupID = "embedding-pipeline-group"
	}
	if config.Kafka.Topic == "" {
		config.Kafka.Topic = "document"
	}
	if config.Kafka.AutoOffsetReset == "" {
		config.Kafka.AutoOffsetReset = "earliest"
	}

	if config.Qdrant.URL == "" {
		config.Qdrant.URL = "http://localhost:6333"
	}
	if config.Qdrant.Collection == "" {
		config.Qdrant.Collection = "documents"
	}
	if config.Qdrant.VectorSize == 0 {
		config.Qdrant.VectorSize = 768
	}

	if config.Gemini.Model == "" {
		config.Gemini.Model = "models/text-embedding-004"
	}

	// Validate required fields
	if config.Gemini.APIKey == "" {
		return nil, fmt.Errorf("gemini api_key is required")
	}

	return &config, nil
}

// GetConfig returns a default configuration (for backward compatibility)
func GetConfig() *Config {
	return &Config{
		Kafka: KafkaConfig{
			BootstrapServers: "localhost:9092",
			GroupID:          "embedding-pipeline-group",
			Topic:            "document",
			AutoOffsetReset:  "earliest",
		},
		Qdrant: QdrantConfig{
			URL:        "http://localhost:6333",
			Collection: "documents",
			VectorSize: 768,
		},
		Gemini: GeminiConfig{
			Model: "models/text-embedding-004",
		},
	}
}