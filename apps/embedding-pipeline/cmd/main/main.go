package main

import (
	"flag"
	"log"
	"os"
	"os/signal"
	"sync"
	"syscall"

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

	kafkaConsumer, err := consumer.NewKafkaConsumerWithConfig(cfg.Kafka)
	if err != nil {
		log.Fatalf("Failed to create Kafka consumer: %v", err)
	}
	defer kafkaConsumer.Close()

	embedder, err := embedders.NewGeminiEmbedderWithConfig(cfg.Gemini)
	if err != nil {
		log.Fatalf("Failed to create Gemini embedder: %v", err)
	}

	qdrantClient, err := storage.NewQdrantClientWithConfig(cfg.Qdrant)
	if err != nil {
		log.Fatalf("Failed to create Qdrant client: %v", err)
	}

	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	log.Println("Starting embedding pipeline...")
	
	go func() {
		for {
			chunks, err := kafkaConsumer.ConsumeChunks()
			if err != nil {
				log.Printf("Error consuming chunks: %v", err)
				continue
			}

			log.Printf("Received %d chunks to process", len(chunks))

			var wg sync.WaitGroup
			errorCount := 0
			var errorMutex sync.Mutex

			for i, chunk := range chunks {
				wg.Add(1)
				go func(idx int, c consumer.ChunkOutput) {
					defer wg.Done()

					embedding, err := embedder.GenerateEmbedding(c.Text)
					if err != nil {
						log.Printf("Error generating embedding for chunk %d (document: %s): %v", 
							idx, c.Source.DocumentTitle, err)
						errorMutex.Lock()
						errorCount++
						errorMutex.Unlock()
						return
					}

					enrichedChunk := consumer.EnrichedChunk{
						ChunkOutput: c,
						Embedding:   embedding,
					}

					err = qdrantClient.AddToBuffer(enrichedChunk)
					if err != nil {
						log.Printf("Error adding chunk to buffer: %v", err)
						errorMutex.Lock()
						errorCount++
						errorMutex.Unlock()
						return
					}

					log.Printf("Generated embedding for chunk %d: document='%s', chunk_index=%d, words=%d", 
						idx, c.Source.DocumentTitle, c.ChunkMetadata.ChunkIndex, c.ChunkMetadata.WordCount)
				}(i, chunk)
			}

			wg.Wait()

			if errorCount > 0 {
				log.Printf("Encountered %d errors during processing", errorCount)
			}

			log.Printf("Successfully processed %d chunks", len(chunks)-errorCount)
		}
	}()

	<-sigChan
	log.Println("Shutting down embedding pipeline...")
	
	err = qdrantClient.FlushBuffer()
	if err != nil {
		log.Printf("Error flushing buffer during shutdown: %v", err)
	}
}