package validator

import (
	"fmt"
	"mime/multipart"
	"os"
	"path/filepath"
	"strings"

	"github.com/NEMYSESx/Orbit/apps/ingestion-pipeline/internal/config"
)

type FileValidator struct {
	config *config.ProcessingConfig
}

func NewFileValidator(cfg *config.ProcessingConfig) *FileValidator {
	return &FileValidator{
		config: cfg,
	}
}

func (fv *FileValidator) Validate(file multipart.File, header multipart.FileHeader) error {
	maxSizeBytes := fv.config.MaxFileSize * 1024 * 1024 

	if header.Size > maxSizeBytes {
		return fmt.Errorf("file size (%d bytes) exceeds maximum allowed size (%d MB)", 
			header.Size, fv.config.MaxFileSize)
	}

	if !fv.IsSupported(header.Filename) {
		return fmt.Errorf("unsupported file format: %s", filepath.Ext(header.Filename))
	}

	return nil
}

func (fv *FileValidator) IsSupported(filename string) bool {
	ext := strings.ToLower(filepath.Ext(filename))
	if ext != "" && ext[0] == '.' {
		ext = ext[1:]
	}

	for _, supported := range fv.config.SupportedFormats {
		if strings.ToLower(supported) == ext {
			return true
		}
	}
	return false
}

func (fv *FileValidator) GetSupportedFormats() []string {
	return fv.config.SupportedFormats
}

func (fv *FileValidator) ValidateDirectory(dirPath string) error {
	info, err := os.Stat(dirPath)
	if err != nil {
		if os.IsNotExist(err) {
			return fmt.Errorf("directory does not exist: %s", dirPath)
		}
		return fmt.Errorf("cannot access directory: %w", err)
	}

	if !info.IsDir() {
		return fmt.Errorf("path is not a directory: %s", dirPath)
	}

	return nil
}
