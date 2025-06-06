package consumer

import (
	"encoding/json"
	"fmt"
	"log"
	"os"

	"github.com/NEMYSESx/Orbit/apps/embedding-pipeline/internal/config"
	"github.com/confluentinc/confluent-kafka-go/kafka"
)

type ChunkOutput struct {
	Text          string        `json:"text"`
	Source        SourceInfo    `json:"source"`
	ChunkMetadata ChunkMetadata `json:"chunk_metadata"`
}

type SourceInfo struct {
	DocumentTitle string `json:"document_title"`
	DocumentType  string `json:"document_type"`
	Section       string `json:"section,omitempty"`
	PageNumber    *int   `json:"page_number,omitempty"`
	LastModified  string `json:"last_modified,omitempty"`
}

type ChunkMetadata struct {
	Topic      string   `json:"topic"`
	Keywords   []string `json:"keywords"`
	Entities   []string `json:"entities"`
	Summary    string   `json:"summary"`
	Category   string   `json:"category"`
	Sentiment  string   `json:"sentiment"`
	Complexity string   `json:"complexity"`
	Language   string   `json:"language"`
	WordCount  int      `json:"word_count"`
	ChunkIndex int      `json:"chunk_index"`
	Timestamp  string   `json:"timestamp"`
}

type EnrichedChunk struct {
	ChunkOutput
	Embedding []float32 `json:"embedding"`
}

type KafkaConsumer struct {
	consumer *kafka.Consumer
	topic    string
}

func NewKafkaConsumerWithConfig(cfg config.KafkaConfig) (*KafkaConsumer, error) {
	c, err := kafka.NewConsumer(&kafka.ConfigMap{
		"bootstrap.servers": cfg.BootstrapServers,
		"group.id":          cfg.GroupID,
		"auto.offset.reset": cfg.AutoOffsetReset,
	})

	if err != nil {
		return nil, fmt.Errorf("failed to create consumer: %w", err)
	}

	err = c.SubscribeTopics([]string{cfg.Topic}, nil)
	if err != nil {
		c.Close()
		return nil, fmt.Errorf("failed to subscribe to topic %s: %w", cfg.Topic, err)
	}

	log.Printf("Kafka consumer started for topic: %s", cfg.Topic)

	return &KafkaConsumer{
		consumer: c,
		topic:    cfg.Topic,
	}, nil
}

func (kc *KafkaConsumer) ConsumeChunks() ([]ChunkOutput, error) {
	msg, err := kc.consumer.ReadMessage(-1)
	if err != nil {
		return nil, fmt.Errorf("error reading message: %w", err)
	}

	if len(msg.Value) == 0 {
		return nil, fmt.Errorf("received empty message")
	}

	log.Printf("Raw message: %s", string(msg.Value))

	var singleChunk ChunkOutput
	if err := json.Unmarshal(msg.Value, &singleChunk); err != nil {
		return nil, fmt.Errorf("failed to parse chunk: %w", err)
	}
	
	chunks := []ChunkOutput{singleChunk}

	if len(chunks) == 0 {
		return nil, fmt.Errorf("no chunks found in message")
	}

	log.Printf("Successfully consumed %d chunks", len(chunks))
	return chunks, nil
}

func (kc *KafkaConsumer) Close() error {
	if kc.consumer != nil {
		return kc.consumer.Close()
	}
	return nil
}

func getEnvOrDefault(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}