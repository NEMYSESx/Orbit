package validator

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/NEMYSESx/orbit/apps/ingestion-pipeline/internal/config"
)

type FileValidator struct {
	config *config.ProcessingConfig
}

func NewFileValidator(cfg *config.ProcessingConfig) *FileValidator {
	return &FileValidator{
		config: cfg,
	}
}

func (fv *FileValidator) Validate(filePath string) error {
	fileInfo, err := os.Stat(filePath)
	if err != nil {
		if os.IsNotExist(err) {
			return fmt.Errorf("file does not exist: %s", filePath)
		}
		return fmt.Errorf("cannot access file: %w", err)
	}

	if fileInfo.IsDir() {
		return fmt.Errorf("path is a directory, not a file: %s", filePath)
	}

	maxSizeBytes := fv.config.MaxFileSize * 1024 * 1024 
	if fileInfo.Size() > maxSizeBytes {
		return fmt.Errorf("file size (%d bytes) exceeds maximum allowed size (%d MB)", 
			fileInfo.Size(), fv.config.MaxFileSize)
	}

	if !fv.IsSupported(filePath) {
		return fmt.Errorf("unsupported file format: %s", filepath.Ext(filePath))
	}

	file, err := os.Open(filePath)
	if err != nil {
		return fmt.Errorf("cannot open file for reading: %w", err)
	}
	file.Close()

	return nil
}

func (fv *FileValidator) IsSupported(filePath string) bool {
	ext := strings.ToLower(filepath.Ext(filePath))
	if ext != "" && ext[0] == '.' {
		ext = ext[1:] 
	}

	for _, supportedFormat := range fv.config.SupportedFormats {
		if strings.ToLower(supportedFormat) == ext {
			return true
		}
	}

	return false
}

func (fv *FileValidator) GetSupportedFormats() []string {
	return fv.config.SupportedFormats
}

func (fv *FileValidator) ValidateDirectory(dirPath string) error {
	fileInfo, err := os.Stat(dirPath)
	if err != nil {
		if os.IsNotExist(err) {
			return fmt.Errorf("directory does not exist: %s", dirPath)
		}
		return fmt.Errorf("cannot access directory: %w", err)
	}

	if !fileInfo.IsDir() {
		return fmt.Errorf("path is not a directory: %s", dirPath)
	}

	dir, err := os.Open(dirPath)
	if err != nil {
		return fmt.Errorf("cannot open directory for reading: %w", err)
	}
	dir.Close()

	return nil
}