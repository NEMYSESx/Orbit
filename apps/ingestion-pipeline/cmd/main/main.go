package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"

	"github.com/NEMYSESx/orbit/apps/ingestion-pipeline/internal/chunking"
	"github.com/NEMYSESx/orbit/apps/ingestion-pipeline/internal/config"
	"github.com/NEMYSESx/orbit/apps/ingestion-pipeline/internal/models"
	"github.com/NEMYSESx/orbit/apps/ingestion-pipeline/internal/processor"
	"github.com/NEMYSESx/orbit/apps/ingestion-pipeline/internal/storage"
)

func main() {
	var (
		configPath     = flag.String("config", "config.json", "Path to configuration file")
		filePath       = flag.String("file", "", "Path to file to process")
		dirPath        = flag.String("dir", "", "Path to directory to process")
		batchSize      = flag.Int("batch", 5, "Batch size for concurrent processing")
		enableChunking = flag.Bool("chunk", false, "Enable agentic chunking")
	)
	flag.Parse()

	if *filePath == "" && *dirPath == "" {
		log.Fatal("Either -file or -dir must be specified")
	}

	cfg, err := config.Load(*configPath)
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	proc, err := processor.New(cfg)
	if err != nil {
		log.Fatalf("Failed to create processor: %v", err)
	}

	ctx := context.Background()

	var chunker *chunking.AgenticChunker
	var chunkingStorage *chunking.ChunkingStorageManager

	if *enableChunking {
		chunkingConfig := chunking.DefaultConfig()

		if apiKey := os.Getenv("GEMINI_API_KEY"); apiKey != "" {
			chunkingConfig.GeminiAPIKey = apiKey
		} else {
			log.Fatal("GEMINI_API_KEY environment variable is required for chunking")
		}

		chunker = chunking.NewAgenticChunker(chunkingConfig)

		storageManager := storage.NewManager(&cfg.Storage)
		chunkingStorage = chunking.NewChunkingStorageManager(storageManager, chunkingConfig)
	}

	if *filePath != "" {
		if err := processFile(ctx, proc, chunker, chunkingStorage, *filePath, *enableChunking); err != nil {
			log.Fatalf("Failed to process document: %v", err)
		}
		fmt.Println("Document processed successfully!")
	} else {
		if err := processDirectory(ctx, proc, chunker, chunkingStorage, *dirPath, *batchSize, *enableChunking); err != nil {
			log.Fatalf("Failed to process directory: %v", err)
		}
		fmt.Println("Directory processed successfully!")
	}
}

func processFile(ctx context.Context, proc *processor.DocumentProcessor, chunker *chunking.AgenticChunker,
	chunkingStorage *chunking.ChunkingStorageManager, filePath string, enableChunking bool) error {

	if err := proc.ProcessDocument(ctx, filePath); err != nil {
		return fmt.Errorf("failed to extract document: %w", err)
	}

	if !enableChunking {
		return nil
	}

	extractedContent, err := loadExtractedContent(filePath)
	if err != nil {
		return fmt.Errorf("failed to load extracted content: %w", err)
	}

	chunkedDoc, err := chunker.ProcessDocument(ctx, extractedContent)
	if err != nil {
		return fmt.Errorf("failed to chunk document: %w", err)
	}

	savedPath, err := chunkingStorage.SaveChunkedDocument(chunkedDoc)
	if err != nil {
		return fmt.Errorf("failed to save chunked document: %w", err)
	}

	log.Printf("Chunked document saved to: %s", savedPath)
	log.Printf("Processing summary: %d chunks, %.2f avg confidence, %v duration",
		chunkedDoc.ProcessingSummary.TotalChunks,
		chunkedDoc.ProcessingSummary.AverageConfidence,
		chunkedDoc.ProcessingSummary.ProcessingDuration)

	return nil
}

func processDirectory(ctx context.Context, proc *processor.DocumentProcessor, chunker *chunking.AgenticChunker,
	chunkingStorage *chunking.ChunkingStorageManager, dirPath string, batchSize int, enableChunking bool) error {

	if err := proc.ProcessDirectory(ctx, dirPath, batchSize); err != nil {
		return fmt.Errorf("failed to extract documents: %w", err)
	}

	if !enableChunking {
		return nil
	}

	// TODO: Implement batch chunking for directory processing
	// This would involve:
	// 1. Finding all extracted documents
	// 2. Processing them in batches
	// 3. Implementing concurrent chunking with proper resource management

	log.Println("Directory chunking not yet implemented - use individual file processing")
	return nil
}

func loadExtractedContent(originalFilePath string) (*models.ExtractedContent, error) {
	// This is a placeholder - you'll need to implement logic to find
	// the corresponding extracted content file based on your storage naming convention
	// For now, assume it follows a pattern like: original_file_extracted.json

	// Implementation would depend on your storage manager's naming convention
	return nil, fmt.Errorf("loadExtractedContent not implemented - integrate with your storage system")
}
