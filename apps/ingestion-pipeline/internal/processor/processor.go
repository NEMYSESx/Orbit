// internal/processor/processor.go
package processor

import (
	"context"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/NEMYSESx/orbit/apps/ingestion-pipeline/internal/config"
	"github.com/NEMYSESx/orbit/apps/ingestion-pipeline/internal/metadata"
	"github.com/NEMYSESx/orbit/apps/ingestion-pipeline/internal/storage"
	"github.com/NEMYSESx/orbit/apps/ingestion-pipeline/internal/text"
	"github.com/NEMYSESx/orbit/apps/ingestion-pipeline/internal/tika"
	"github.com/NEMYSESx/orbit/apps/ingestion-pipeline/internal/validator"
)

const ProcessorVersion = "1.0.0"

type DocumentProcessor struct {
	config        *config.Config
	tikaClient    *tika.Client
	metaBuilder   *metadata.Builder
	textCleaner   *text.Cleaner
	validator     *validator.FileValidator
	storage       *storage.Manager
	logger        *log.Logger
}

func New(cfg *config.Config) (*DocumentProcessor, error) {
	if err := os.MkdirAll(cfg.Storage.OutputDir, 0755); err != nil {
		return nil, fmt.Errorf("failed to create output directory: %w", err)
	}
	if err := os.MkdirAll(cfg.Storage.TempDir, 0755); err != nil {
		return nil, fmt.Errorf("failed to create temp directory: %w", err)
	}

	dp := &DocumentProcessor{
		config:      cfg,
		tikaClient:  tika.NewClient(&cfg.Tika),
		metaBuilder: metadata.NewBuilder(),
		textCleaner: text.NewCleaner(cfg.Processing.EnableTextClean),
		validator:   validator.NewFileValidator(&cfg.Processing),
		storage:     storage.NewManager(&cfg.Storage),
		logger:      log.New(os.Stdout, "[DOC_PROCESSOR] ", log.LstdFlags|log.Lshortfile),
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	
	if err := dp.tikaClient.HealthCheck(ctx); err != nil {
		return nil, fmt.Errorf("tika server health check failed: %w", err)
	}

	return dp, nil
}

func (dp *DocumentProcessor) ProcessDocument(ctx context.Context, filePath string) error {
	start := time.Now()
	dp.logger.Printf("Starting processing for file: %s", filePath)

	if err := dp.validator.Validate(filePath); err != nil {
		return fmt.Errorf("file validation failed: %w", err)
	}

	extracted, err := dp.tikaClient.ExtractWithMetadata(ctx, filePath)
	if err != nil {
		return fmt.Errorf("tika extraction failed: %w", err)
	}

	metadata, err := dp.metaBuilder.BuildFromFile(filePath, map[string]interface{}{})
	if err != nil {
		return fmt.Errorf("metadata building failed: %w", err)
	}
	metadata.ProcessedAt = time.Now()
	metadata.ProcessorVersion = ProcessorVersion
	extracted.Metadata = *metadata

	extracted.CleanText = dp.textCleaner.Clean(extracted.RawText)
	extracted.WordCount = dp.textCleaner.CountWords(extracted.CleanText)

	outputPath, err := dp.storage.Save(extracted)
	if err != nil {
		return fmt.Errorf("failed to save extracted content: %w", err)
	}

	processingTime := time.Since(start)
	dp.logger.Printf("Successfully processed document: %s -> %s (took %v)", 
		filePath, outputPath, processingTime)

	return nil
}

func (dp *DocumentProcessor) ProcessDirectory(ctx context.Context, dirPath string, batchSize int) error {
	files, err := dp.getSupportedFiles(dirPath)
	if err != nil {
		return fmt.Errorf("failed to get files: %w", err)
	}

	if len(files) == 0 {
		return fmt.Errorf("no supported files found in directory: %s", dirPath)
	}

	dp.logger.Printf("Found %d files to process", len(files))
	return dp.processBatch(ctx, files, batchSize)
}

func (dp *DocumentProcessor) getSupportedFiles(dirPath string) ([]string, error) {
	var files []string
	err := filepath.Walk(dirPath, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if !info.IsDir() && dp.validator.IsSupported(path) {
			files = append(files, path)
		}
		return nil
	})
	return files, err
}

func (dp *DocumentProcessor) processBatch(ctx context.Context, files []string, batchSize int) error {
	var wg sync.WaitGroup
	semaphore := make(chan struct{}, batchSize)
	
	successCount := 0
	errorCount := 0
	var mu sync.Mutex

	for _, file := range files {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case semaphore <- struct{}{}:
		}

		wg.Add(1)
		go func(filePath string) {
			defer wg.Done()
			defer func() { <-semaphore }()

			if err := dp.ProcessDocument(ctx, filePath); err != nil {
				mu.Lock()
				errorCount++
				mu.Unlock()
				dp.logger.Printf("Failed to process file %s: %v", filePath, err)
			} else {
				mu.Lock()
				successCount++
				mu.Unlock()
			}
		}(file)
	}

	wg.Wait()
	
	dp.logger.Printf("Batch processing complete: %d successful, %d failed out of %d total", 
		successCount, errorCount, len(files))

	if errorCount > 0 && successCount == 0 {
		return fmt.Errorf("all %d files failed to process", errorCount)
	}

	return nil
}