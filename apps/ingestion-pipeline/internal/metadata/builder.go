// internal/metadata/builder.go
package metadata

import (
	"crypto/md5"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/NEMYSESx/orbit/apps/ingestion-pipeline/internal/models"
)

type Builder struct{}

func NewBuilder() *Builder {
	return &Builder{}
}

func (b *Builder) BuildFromFile(filePath string, extraMetadata map[string]interface{}) (*models.DocumentMetadata, error) {
	fileInfo, err := os.Stat(filePath)
	if err != nil {
		return nil, fmt.Errorf("failed to get file info: %w", err)
	}

	checksum, err := b.calculateChecksum(filePath)
	if err != nil {
		return nil, fmt.Errorf("failed to calculate checksum: %w", err)
	}

	id := b.generateID(filePath, checksum)

	title := b.extractTitle(filePath)

	contentType := b.determineContentType(filePath)

	modTime := fileInfo.ModTime()

	metadata := &models.DocumentMetadata{
		ID:               id,
		SourceID:         id, 
		SourceType:       "file",
		Title:            title,
		Filepath:         filePath,
		LastModifiedDate: modTime,
		FileSize:         fileInfo.Size(),
		ContentType:      contentType,
		Checksum:         checksum,
		ExtraMetadata:    extraMetadata,
	}

	b.enrichMetadata(metadata, filePath, fileInfo)

	return metadata, nil
}

func (b *Builder) BuildFromTikaMetadata(filePath string, tikaMetadata map[string]interface{}) (*models.DocumentMetadata, error) {
	metadata, err := b.BuildFromFile(filePath, nil)
	if err != nil {
		return nil, err
	}

	if title, ok := tikaMetadata["title"].(string); ok && title != "" {
		metadata.Title = title
	}

	if author, ok := tikaMetadata["author"].(string); ok && author != "" {
		metadata.Author = author
	}

	if creator, ok := tikaMetadata["creator"].(string); ok && creator != "" && metadata.Author == "" {
		metadata.Author = creator
	}

	if createdStr, ok := tikaMetadata["created"].(string); ok {
		if createdTime, err := b.parseTimeString(createdStr); err == nil {
			metadata.CreationDate = &createdTime
		}
	}

	if contentType, ok := tikaMetadata["Content-Type"].(string); ok && contentType != "" {
		metadata.ContentType = contentType
	}

	if language, ok := tikaMetadata["language"].(string); ok && language != "" {
		metadata.Language = language
	}

	metadata.ExtraMetadata = make(map[string]interface{})
	for key, value := range tikaMetadata {
		if !b.isStandardField(key) {
			metadata.ExtraMetadata[key] = value
		}
	}

	return metadata, nil
}

func (b *Builder) calculateChecksum(filePath string) (string, error) {
	file, err := os.Open(filePath)
	if err != nil {
		return "", err
	}
	defer file.Close()

	hash := md5.New()
	if _, err := io.Copy(hash, file); err != nil {
		return "", err
	}

	return fmt.Sprintf("%x", hash.Sum(nil)), nil
}

func (b *Builder) generateID(filePath, checksum string) string {
	base := filepath.Base(filePath)
	return fmt.Sprintf("%s_%s", 
		strings.ReplaceAll(base, " ", "_"), 
		checksum[:8]) 
}

func (b *Builder) extractTitle(filePath string) string {
	base := filepath.Base(filePath)
	ext := filepath.Ext(base)
	
	title := strings.TrimSuffix(base, ext)
	title = strings.ReplaceAll(title, "_", " ")
	title = strings.ReplaceAll(title, "-", " ")
	
	words := strings.Fields(title)
	for i, word := range words {
		if len(word) > 0 {
			words[i] = strings.ToUpper(string(word[0])) + strings.ToLower(word[1:])
		}
	}
	
	return strings.Join(words, " ")
}

func (b *Builder) determineContentType(filePath string) string {
	ext := strings.ToLower(filepath.Ext(filePath))
	
	contentTypes := map[string]string{
		".pdf":  "application/pdf",
		".doc":  "application/msword",
		".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
		".txt":  "text/plain",
		".html": "text/html",
		".htm":  "text/html",
		".rtf":  "application/rtf",
		".odt":  "application/vnd.oasis.opendocument.text",
		".xml":  "application/xml",
		".json": "application/json",
	}
	
	if contentType, exists := contentTypes[ext]; exists {
		return contentType
	}
	
	return "application/octet-stream"
}

func (b *Builder) enrichMetadata(metadata *models.DocumentMetadata, filePath string, fileInfo os.FileInfo) {
	if metadata.Language == "" {
		metadata.Language = b.detectLanguageFromPath(filePath)
	}
	
	if metadata.CreationDate == nil {
		creationTime := fileInfo.ModTime()
		metadata.CreationDate = &creationTime
	}
}

func (b *Builder) detectLanguageFromPath(filePath string) string {
	path := strings.ToLower(filePath)
	
	languageIndicators := map[string]string{
		"en":    "en",
		"eng":   "en",
		"english": "en",
		"fr":    "fr",
		"french": "fr",
		"de":    "de",
		"german": "de",
		"es":    "es",
		"spanish": "es",
		"it":    "it",
		"italian": "it",
	}
	
	for indicator, lang := range languageIndicators {
		if strings.Contains(path, indicator) {
			return lang
		}
	}
	
	return "en"
}

func (b *Builder) parseTimeString(timeStr string) (time.Time, error) {
	formats := []string{
		time.RFC3339,
		"2006-01-02T15:04:05Z",
		"2006-01-02 15:04:05",
		"2006-01-02",
		"01/02/2006",
		"01-02-2006",
		"2006/01/02",
	}
	
	for _, format := range formats {
		if t, err := time.Parse(format, timeStr); err == nil {
			return t, nil
		}
	}
	
	return time.Time{}, fmt.Errorf("unable to parse time string: %s", timeStr)
}

func (b *Builder) isStandardField(key string) bool {
	standardFields := map[string]bool{
		"title":        true,
		"author":       true,
		"creator":      true,
		"created":      true,
		"Content-Type": true,
		"content-type": true,
		"language":     true,
	}
	
	return standardFields[key]
}

func (b *Builder) ValidateMetadata(metadata *models.DocumentMetadata) error {
	if metadata.ID == "" {
		return fmt.Errorf("metadata ID cannot be empty")
	}
	
	if metadata.Filepath == "" {
		return fmt.Errorf("metadata filepath cannot be empty")
	}
	
	if metadata.FileSize < 0 {
		return fmt.Errorf("metadata file size cannot be negative")
	}
	
	if metadata.Checksum == "" {
		return fmt.Errorf("metadata checksum cannot be empty")
	}
	
	return nil
}

func (b *Builder) UpdateMetadata(metadata *models.DocumentMetadata, updates map[string]interface{}) {
	for key, value := range updates {
		switch key {
		case "title":
			if title, ok := value.(string); ok {
				metadata.Title = title
			}
		case "author":
			if author, ok := value.(string); ok {
				metadata.Author = author
			}
		case "language":
			if language, ok := value.(string); ok {
				metadata.Language = language
			}
		default:
			if metadata.ExtraMetadata == nil {
				metadata.ExtraMetadata = make(map[string]interface{})
			}
			metadata.ExtraMetadata[key] = value
		}
	}
}