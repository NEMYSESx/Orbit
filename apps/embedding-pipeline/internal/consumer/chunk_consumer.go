package consumer

import (
	"encoding/json"
	"fmt"
	"log"
	"strings"

	"github.com/NEMYSESx/Orbit/apps/embedding-pipeline/internal/config"
	"github.com/confluentinc/confluent-kafka-go/kafka"
)

type ChunkKafkaConsumer struct {
	consumer *kafka.Consumer
	topics   []string
}

func NewChunkKafkaConsumer(cfg config.KafkaConfig) (*ChunkKafkaConsumer, error) {
	c, err := kafka.NewConsumer(&kafka.ConfigMap{
		"bootstrap.servers": cfg.BootstrapServers,
		"group.id":          cfg.GroupID + "-chunks",
		"auto.offset.reset": cfg.AutoOffsetReset,
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create consumer: %w", err)
	}

	var chunkTopics []string
	for _, topic := range cfg.Topic {
		if topic != "logs" {
			chunkTopics = append(chunkTopics, topic)
		}
	}

	if len(chunkTopics) == 0 {
		return nil, fmt.Errorf("no valid chunk topics found (excluding 'logs')")
	}

	if err := c.SubscribeTopics(chunkTopics, nil); err != nil {
		c.Close()
		return nil, fmt.Errorf("failed to subscribe to topics: %w", err)
	}

	log.Printf("Chunk consumer started for topics: %s", strings.Join(chunkTopics, ", "))
	return &ChunkKafkaConsumer{consumer: c, topics: chunkTopics}, nil
}

func (cc *ChunkKafkaConsumer) ConsumeChunk() (*ChunkOutput, string, error) {
	msg, err := cc.consumer.ReadMessage(-1)
	if err != nil {
		return nil, "", fmt.Errorf("read error: %w", err)
	}

	if len(msg.Value) == 0 {
		return nil, "", fmt.Errorf("empty message")
	}

	var chunk ChunkOutput
	if err := json.Unmarshal(msg.Value, &chunk); err != nil {
		return nil, "", fmt.Errorf("unmarshal error: %w", err)
	}

	topic := ""
	if msg.TopicPartition.Topic != nil {
		topic = *msg.TopicPartition.Topic
	}

	return &chunk, topic, nil
}

func (cc *ChunkKafkaConsumer) Close() error {
	if cc.consumer != nil {
		return cc.consumer.Close()
	}
	return nil
}