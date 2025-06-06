package processor

import (
	"context"
	"encoding/json"
	"fmt"
	"mime/multipart"
	"time"

	"github.com/NEMYSESx/Orbit/apps/ingestion-pipeline/internal/chunking"
	"github.com/NEMYSESx/Orbit/apps/ingestion-pipeline/internal/config"
	"github.com/NEMYSESx/Orbit/apps/ingestion-pipeline/internal/models"
	"github.com/NEMYSESx/Orbit/apps/ingestion-pipeline/internal/text"
	"github.com/NEMYSESx/Orbit/apps/ingestion-pipeline/internal/tika"
	"github.com/NEMYSESx/Orbit/apps/ingestion-pipeline/internal/validator"
	"github.com/confluentinc/confluent-kafka-go/kafka"
)

type DocumentProcessor struct {
	config      *config.Config
	tikaClient  *tika.Client
	textCleaner *text.Cleaner
	validator   *validator.FileValidator
	chunker     *chunking.AgenticChunker
	producer    *kafka.Producer
}

func New(cfg *config.Config) (*DocumentProcessor, error) {
	chunkingConfig := models.ChunkingConfig{
		GeminiAPIKey:   cfg.Chunking.GeminiAPIKey,
		GeminiModel:    cfg.Chunking.GeminiModel,
		MaxRetries:     3,
		MaxConcurrency: 5,
		RateLimitRPS:   10,
		RequestTimeout: time.Second * 30,
	}

	producer, err := kafka.NewProducer(&kafka.ConfigMap{
		"bootstrap.servers": "kafka:29092",
		"acks":             "all",
		"retries":          "3",
		"batch.size":       "16384",
		"linger.ms":        "1",
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create Kafka producer: %w", err)
	}

	dp := &DocumentProcessor{
		config:      cfg,
		tikaClient:  tika.NewClient(&cfg.Tika),
		textCleaner: text.NewCleaner(cfg.Processing.EnableTextClean),
		validator:   validator.NewFileValidator(&cfg.Processing),
		chunker:     chunking.NewAgenticChunkerWithConfig(chunkingConfig),
		producer:    producer,
	}

	return dp, nil
}

func (dp *DocumentProcessor) ProcessDocument(ctx context.Context, file multipart.File, header *multipart.FileHeader) (*models.ProcessResult, error) {
	fmt.Printf("Starting processing for file: %s\n", header.Filename)

	if seeker, ok := file.(interface{ Seek(int64, int) (int64, error) }); ok {
		if _, err := seeker.Seek(0, 0); err != nil {
			return nil, fmt.Errorf("failed to reset file pointer: %w", err)
		}
	}

	if err := dp.validator.Validate(file, *header); err != nil {
		return nil, fmt.Errorf("file validation failed: %w", err)
	}

	if seeker, ok := file.(interface{ Seek(int64, int) (int64, error) }); ok {
		if _, err := seeker.Seek(0, 0); err != nil {
			return nil, fmt.Errorf("failed to reset file pointer: %w", err)
		}
	}

	extracted, err := dp.tikaClient.ExtractWithMetadata(ctx, file, header)
	if err != nil {
		return nil, fmt.Errorf("tika extraction failed: %w", err)
	}

	cleanText := extracted.CleanText
	if dp.config.Processing.EnableTextClean {
		cleanText = dp.textCleaner.Clean(extracted.CleanText)
	}

	var chunks []models.ChunkOutput
	if dp.config.Chunking.Enabled && dp.config.Chunking.GeminiAPIKey != "" {
		fmt.Printf("Starting agentic chunking for document: %s\n", header.Filename)
		
		sourceInfo := models.SourceInfo{
			DocumentTitle: extracted.Metadata.Title,
			DocumentType:  extracted.Metadata.ContentType,
			LastModified:  extracted.Metadata.LastModifiedDate,
		}

		chunkOutputs, err := dp.chunker.ChunkTextWithSource(ctx, cleanText, sourceInfo)
		if err != nil {
			fmt.Printf("Agentic chunking failed for %s: %v\n", header.Filename, err)
		} else {
			chunks = chunkOutputs
			kafkaProducer(chunks, "documents")
			fmt.Printf("Successfully created %d chunks for document: %s\n", len(chunks), header.Filename)
		}
	}

	fmt.Printf("Successfully processed document: %s\n", header.Filename)	
	result := &models.ProcessResult{
		ExtractedContent: extracted,
		Chunks:           chunks,
	}

	return result, nil
}

func (dp *DocumentProcessor) ProcessDocumentWithChunking(ctx context.Context, file multipart.File, header *multipart.FileHeader) (*models.ProcessResult, error) {
	originalEnabled := dp.config.Chunking.Enabled
	dp.config.Chunking.Enabled = true
	defer func() {
		dp.config.Chunking.Enabled = originalEnabled
	}()

	return dp.ProcessDocument(ctx, file, header)
}

func (dp *DocumentProcessor) GetChunkingStatistics(result *models.ProcessResult) map[string]interface{} {
	if len(result.Chunks) == 0 {
		return map[string]interface{}{
			"total_chunks": 0,
			"chunking_enabled": false,
		}
	}

	totalWords := 0
	categories := make(map[string]int)
	sentiments := make(map[string]int)
	complexities := make(map[string]int)

	for _, chunk := range result.Chunks {
		totalWords += chunk.ChunkMetadata.WordCount
		categories[chunk.ChunkMetadata.Category]++
		sentiments[chunk.ChunkMetadata.Sentiment]++
		complexities[chunk.ChunkMetadata.Complexity]++
	}

	avgWords := 0.0
	if len(result.Chunks) > 0 {
		avgWords = float64(totalWords) / float64(len(result.Chunks))
	}

	return map[string]interface{}{
		"total_chunks":              len(result.Chunks),
		"total_words":               totalWords,
		"average_words_per_chunk":   avgWords,
		"categories":                categories,
		"sentiments":                sentiments,
		"complexities":              complexities,
		"chunking_enabled":          true,
	}
}

func kafkaProducer(chunks []models.ChunkOutput, topic string) {
	p, err := kafka.NewProducer(&kafka.ConfigMap{"bootstrap.servers": "kafka:29092"})
	if err != nil {
		fmt.Printf("Failed to create producer: %v\n", err)
		return
	}
	defer p.Close()

	for i, chunk := range chunks {
		chunkJSON, err := json.Marshal(chunk)
		if err != nil {
			fmt.Printf("Failed to marshal chunk %d: %v\n", i, err)
			continue
		}

		err = p.Produce(&kafka.Message{
			TopicPartition: kafka.TopicPartition{Topic: &topic, Partition: kafka.PartitionAny},
			Value:          chunkJSON,
		}, nil)

		if err != nil {
			fmt.Printf("Failed to produce chunk %d: %v\n", i, err)
		}
	}

	p.Flush(15 * 1000)
}