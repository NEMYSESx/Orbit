package storage

import (
	"compress/gzip"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/NEMYSESx/orbit/apps/ingestion-pipeline/internal/config"
	"github.com/NEMYSESx/orbit/apps/ingestion-pipeline/internal/models"
)

type Manager struct {
	config *config.StorageConfig
}

func NewManager(cfg *config.StorageConfig) *Manager {
	return &Manager{
		config: cfg,
	}
}

func (sm *Manager) Save(content *models.ExtractedContent) (string, error) {
	outputFilename := sm.generateOutputFilename(content.Metadata)
	outputPath := filepath.Join(sm.config.OutputDir, outputFilename)

	if err := os.MkdirAll(filepath.Dir(outputPath), 0755); err != nil {
		return "", fmt.Errorf("failed to create output directory: %w", err)
	}

	if sm.config.CompressOutput {
		return sm.saveCompressed(content, outputPath)
	}
	
	return sm.saveUncompressed(content, outputPath)
}

func (sm *Manager) saveUncompressed(content *models.ExtractedContent, outputPath string) (string, error) {
	file, err := os.Create(outputPath)
	if err != nil {
		return "", fmt.Errorf("failed to create output file: %w", err)
	}
	defer file.Close()

	encoder := json.NewEncoder(file)
	encoder.SetIndent("", "  ")
	
	if err := encoder.Encode(content); err != nil {
		return "", fmt.Errorf("failed to encode content to JSON: %w", err)
	}

	return outputPath, nil
}

func (sm *Manager) saveCompressed(content *models.ExtractedContent, outputPath string) (string, error) {
	compressedPath := outputPath + ".gz"
	
	file, err := os.Create(compressedPath)
	if err != nil {
		return "", fmt.Errorf("failed to create compressed output file: %w", err)
	}
	defer file.Close()

	gzipWriter := gzip.NewWriter(file)
	defer gzipWriter.Close()

	encoder := json.NewEncoder(gzipWriter)
	encoder.SetIndent("", "  ")
	
	if err := encoder.Encode(content); err != nil {
		return "", fmt.Errorf("failed to encode content to compressed JSON: %w", err)
	}

	return compressedPath, nil
}

func (sm *Manager) generateOutputFilename(metadata models.DocumentMetadata) string {
	timestamp := metadata.ProcessedAt.Format("20060102_150405")
	
	safeID := sm.sanitizeFilename(metadata.ID)
	
	filename := fmt.Sprintf("%s_%s.json", safeID, timestamp)
	return filename
}

func (sm *Manager) sanitizeFilename(filename string) string {
	unsafe := []string{"/", "\\", ":", "*", "?", "\"", "<", ">", "|", " "}
	safe := filename
	
	for _, char := range unsafe {
		safe = strings.ReplaceAll(safe, char, "_")
	}
	
	for strings.Contains(safe, "__") {
		safe = strings.ReplaceAll(safe, "__", "_")
	}
	
	safe = strings.Trim(safe, "_")
	
	if safe == "" {
		safe = "document"
	}
	
	if len(safe) > 100 {
		safe = safe[:100]
	}
	
	return safe
}

func (sm *Manager) Load(filePath string) (*models.ExtractedContent, error) {
	file, err := os.Open(filePath)
	if err != nil {
		return nil, fmt.Errorf("failed to open file: %w", err)
	}
	defer file.Close()

	var content models.ExtractedContent

	if strings.HasSuffix(filePath, ".gz") {
		gzipReader, err := gzip.NewReader(file)
		if err != nil {
			return nil, fmt.Errorf("failed to create gzip reader: %w", err)
		}
		defer gzipReader.Close()

		decoder := json.NewDecoder(gzipReader)
		if err := decoder.Decode(&content); err != nil {
			return nil, fmt.Errorf("failed to decode compressed JSON: %w", err)
		}
	} else {
		decoder := json.NewDecoder(file)
		if err := decoder.Decode(&content); err != nil {
			return nil, fmt.Errorf("failed to decode JSON: %w", err)
		}
	}

	return &content, nil
}

func (sm *Manager) SaveBatch(contents []*models.ExtractedContent) ([]string, error) {
	var outputPaths []string
	var errors []error

	for _, content := range contents {
		outputPath, err := sm.Save(content)
		if err != nil {
			errors = append(errors, fmt.Errorf("failed to save document %s: %w", 
				content.Metadata.ID, err))
			continue
		}
		outputPaths = append(outputPaths, outputPath)
	}

	if len(errors) > 0 {
		var errorMsgs []string
		for _, err := range errors {
			errorMsgs = append(errorMsgs, err.Error())
		}
		return outputPaths, fmt.Errorf("batch save completed with %d errors: %s", 
			len(errors), strings.Join(errorMsgs, "; "))
	}

	return outputPaths, nil
}

func (sm *Manager) CreateTempFile(prefix string) (*os.File, error) {
	if err := os.MkdirAll(sm.config.TempDir, 0755); err != nil {
		return nil, fmt.Errorf("failed to create temp directory: %w", err)
	}

	tempFile, err := os.CreateTemp(sm.config.TempDir, prefix+"_*.tmp")
	if err != nil {
		return nil, fmt.Errorf("failed to create temp file: %w", err)
	}

	return tempFile, nil
}

func (sm *Manager) CleanupTempFiles() error {
	cutoff := time.Now().Add(-24 * time.Hour)
	
	err := filepath.Walk(sm.config.TempDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		
		if !info.IsDir() && info.ModTime().Before(cutoff) {
			if removeErr := os.Remove(path); removeErr != nil {
				fmt.Printf("Warning: failed to remove temp file %s: %v\n", path, removeErr)
			}
		}
		
		return nil
	})

	return err
}

func (sm *Manager) GetStorageStats() (*StorageStats, error) {
	stats := &StorageStats{
		OutputDir: sm.config.OutputDir,
		TempDir:   sm.config.TempDir,
	}

	err := filepath.Walk(sm.config.OutputDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		
		if !info.IsDir() {
			stats.TotalFiles++
			stats.TotalSize += info.Size()
			
			if strings.HasSuffix(path, ".json") {
				stats.JsonFiles++
			} else if strings.HasSuffix(path, ".json.gz") {
				stats.CompressedFiles++
			}
		}
		
		return nil
	})

	if err != nil {
		return nil, fmt.Errorf("failed to calculate storage stats: %w", err)
	}

	return stats, nil
}

func (sm *Manager) ListProcessedDocuments() ([]string, error) {
	var documents []string

	err := filepath.Walk(sm.config.OutputDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		
		if !info.IsDir() && (strings.HasSuffix(path, ".json") || strings.HasSuffix(path, ".json.gz")) {
			documents = append(documents, path)
		}
		
		return nil
	})

	if err != nil {
		return nil, fmt.Errorf("failed to list processed documents: %w", err)
	}

	return documents, nil
}

func (sm *Manager) DeleteDocument(documentPath string) error {
	absOutputDir, err := filepath.Abs(sm.config.OutputDir)
	if err != nil {
		return fmt.Errorf("failed to get absolute output directory path: %w", err)
	}

	absDocPath, err := filepath.Abs(documentPath)
	if err != nil {
		return fmt.Errorf("failed to get absolute document path: %w", err)
	}

	if !strings.HasPrefix(absDocPath, absOutputDir) {
		return fmt.Errorf("document path is outside output directory")
	}

	if err := os.Remove(documentPath); err != nil {
		return fmt.Errorf("failed to delete document: %w", err)
	}

	return nil
}

type StorageStats struct {
	OutputDir       string `json:"output_dir"`
	TempDir         string `json:"temp_dir"`
	TotalFiles      int    `json:"total_files"`
	JsonFiles       int    `json:"json_files"`
	CompressedFiles int    `json:"compressed_files"`
	TotalSize       int64  `json:"total_size_bytes"`
}