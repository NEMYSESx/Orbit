package main

import (
	"flag"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/NEMYSESx/Orbit/apps/embedding-pipeline/internal/config"
	"github.com/NEMYSESx/Orbit/apps/embedding-pipeline/internal/consumer"
	"github.com/NEMYSESx/Orbit/apps/embedding-pipeline/internal/embedders"
	"github.com/NEMYSESx/Orbit/apps/embedding-pipeline/internal/storage"
)

func main() {
	configPath := flag.String("config", "config.json", "Path to configuration file")
	flag.Parse()

	cfg, err := config.LoadConfig(*configPath)
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	logConsumer, err := consumer.NewLogKafkaConsumer(cfg.Kafka)
	if err != nil {
		log.Fatalf("Failed to create log Kafka consumer: %v", err)
	}
	defer logConsumer.Close()

	chunkConsumer, err := consumer.NewChunkKafkaConsumer(cfg.Kafka)
	if err != nil {
		log.Fatalf("Failed to create chunk Kafka consumer: %v", err)
	}
	defer chunkConsumer.Close()

	embedder, err := embedders.NewGeminiEmbedderWithConfig(cfg.Gemini)
	if err != nil {
		log.Fatalf("Failed to create Gemini embedder: %v", err)
	}

	logClient, err := storage.NewQdrantClient(cfg.Qdrant, "logs")
	if err != nil {
		log.Fatalf("Failed to create log Qdrant client: %v", err)
	}

	documentClient, err := storage.NewQdrantClient(cfg.Qdrant, "documents")
	if err != nil {
		log.Fatalf("Failed to create document Qdrant client: %v", err)
	}

	logFields := []string{"level", "type", "source", "collector", "kafka_topic"}
	if err := logClient.CreatePayloadIndexes(logFields); err != nil {
		log.Fatalf("Failed to create log payload indexes: %v", err)
	}

	documentFields := []string{"document_title", "document_type", "chunk_index", "kafka_topic"}
	if err := documentClient.CreatePayloadIndexes(documentFields); err != nil {
		log.Fatalf("Failed to create document payload indexes: %v", err)
	}

	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	log.Println("Starting embedding pipeline...")

	go func() {
		for {
			logChunk, err := logConsumer.ConsumeLogMessage()
			if err != nil {
				log.Printf("Error consuming log message: %v", err)
				continue
			}
			processLogMessage(*logChunk, embedder, logClient)
		}
	}()

	go func() {
		for {
			chunk, topic, err := chunkConsumer.ConsumeChunk()
			if err != nil {
				log.Printf("Error consuming structured chunk: %v", err)
				continue
			}
			processDocumentChunk(*chunk, topic, embedder, documentClient)
		}
	}()

	<-sigChan
	log.Println("Shutting down embedding pipeline...")

	if err := logClient.FlushBuffer(); err != nil {
		log.Printf("Error flushing log buffer: %v", err)
	}
	if err := documentClient.FlushBuffer(); err != nil {
		log.Printf("Error flushing document buffer: %v", err)
	}
}

func processDocumentChunk(chunk consumer.ChunkOutput, topic string, embedder *embedders.GoogleEmbedder, client *storage.QdrantClient) {
	embedding, err := embedder.GenerateEmbedding(chunk.Text)
	if err != nil {
		log.Printf("Embedding error (document: %s): %v", chunk.Source.DocumentTitle, err)
		return
	}

	payload := map[string]interface{}{
		"text":           chunk.Text,
		"document_title": chunk.Source.DocumentTitle,
		"document_type":  chunk.Source.DocumentType,
		"chunk_index":    chunk.ChunkMetadata.ChunkIndex,
		"word_count":     chunk.ChunkMetadata.WordCount,
		"kafka_topic":    topic,
		"timestamp":      time.Now().Format(time.RFC3339),
	}

	data := storage.EmbeddedData{
		Embedding: embedding,
		Payload:   payload,
	}

	if err := client.Store(data); err != nil {
		log.Printf("Error storing document chunk: %v", err)
		return
	}

	log.Printf("✅ Stored document chunk: '%s' (%d words)", 
		chunk.Source.DocumentTitle, chunk.ChunkMetadata.WordCount)
}

func processLogMessage(logChunk consumer.LogChunk, embedder *embedders.GoogleEmbedder, client *storage.QdrantClient) {
	embedding, err := embedder.GenerateEmbedding(logChunk.Message)
	if err != nil {
		log.Printf("Embedding error: %v", err)
		return
	}

	collector := "unknown"
	if collectorValue, exists := logChunk.Details["collector"]; exists {
		if collectorStr, ok := collectorValue.(string); ok {
			collector = collectorStr
		}
	}

	payload := map[string]interface{}{
		"message":     logChunk.Message,
		"timestamp":   logChunk.Timestamp.Format(time.RFC3339),
		"level":       logChunk.Level,
		"type":        logChunk.Type,
		"source":      logChunk.Source,
		"collector":   collector,
		"kafka_topic": "logs",
	}

	if len(logChunk.Details) > 0 {
		payload["details"] = logChunk.Details
	}

	data := storage.EmbeddedData{
		Embedding: embedding,
		Payload:   payload,
	}

	if err := client.Store(data); err != nil {
		log.Printf("Error storing log message: %v", err)
		return
	}

	log.Printf("✅ Stored log: %s/%s - %s", 
		logChunk.Type, logChunk.Level, logChunk.Source)
}