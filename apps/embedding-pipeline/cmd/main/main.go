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
	// Parse command line flags
	configPath := flag.String("config", "config.json", "Path to configuration file")
	flag.Parse()

	// Load configuration
	cfg, err := config.LoadConfig(*configPath)
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	// Create Kafka consumer with config
	kafkaConsumer, err := consumer.NewKafkaConsumerWithConfig(cfg.Kafka)
	if err != nil {
		log.Fatalf("Failed to create Kafka consumer: %v", err)
	}
	defer kafkaConsumer.Close()

	// Create Gemini embedder with config
	embedder, err := embedders.NewGeminiEmbedderWithConfig(cfg.Gemini)
	if err != nil {
		log.Fatalf("Failed to create Gemini embedder: %v", err)
	}

	// Create Qdrant client with config
	qdrantClient, err := storage.NewQdrantClientWithConfig(cfg.Qdrant)
	if err != nil {
		log.Fatalf("Failed to create Qdrant client: %v", err)
	}

	// Setup graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	// Start processing
	log.Println("Starting embedding pipeline...")
	
	go func() {
		for {
			// Consume multiple chunks from a single Kafka message
			chunks, err := kafkaConsumer.ConsumeChunks()
			if err != nil {
				log.Printf("Error consuming chunks: %v", err)
				continue
			}

			log.Printf("Received %d chunks to process", len(chunks))

			// Process chunks concurrently for better performance
			var enrichedChunks []consumer.EnrichedChunk
			var wg sync.WaitGroup
			var mutex sync.Mutex
			errorCount := 0

			for i, chunk := range chunks {
				wg.Add(1)
				go func(idx int, c consumer.ChunkOutput) {
					defer wg.Done()

					// Generate embedding for the text content only
					embedding, err := embedder.GenerateEmbedding(c.Text)
					if err != nil {
						log.Printf("Error generating embedding for chunk %d (document: %s): %v", 
							idx, c.Source.DocumentTitle, err)
						mutex.Lock()
						errorCount++
						mutex.Unlock()
						return
					}

					// Create enriched chunk
					enrichedChunk := consumer.EnrichedChunk{
						ChunkOutput: c,
						Embedding:   embedding,
					}

					// Thread-safe append to results
					mutex.Lock()
					enrichedChunks = append(enrichedChunks, enrichedChunk)
					mutex.Unlock()

					log.Printf("Generated embedding for chunk %d: document='%s', chunk_index=%d, words=%d", 
						idx, c.Source.DocumentTitle, c.ChunkMetadata.ChunkIndex, c.ChunkMetadata.WordCount)
				}(i, chunk)
			}

			// Wait for all embeddings to complete
			wg.Wait()

			// Check results
			if errorCount > 0 {
				log.Printf("Encountered %d errors during embedding generation", errorCount)
			}

			if len(enrichedChunks) == 0 {
				log.Println("No successful embeddings generated, skipping batch")
				continue
			}

			log.Printf("Successfully generated %d embeddings out of %d chunks", len(enrichedChunks), len(chunks))

			// Store all enriched chunks as separate points in Qdrant
			err = qdrantClient.StoreEmbeddings(enrichedChunks)
			if err != nil {
				log.Printf("Error storing enriched chunks to Qdrant: %v", err)
				continue
			}

			log.Printf("Successfully processed and stored %d chunks as separate points", len(enrichedChunks))
		}
	}()

	// Wait for shutdown signal
	<-sigChan
	log.Println("Shutting down embedding pipeline...")
}