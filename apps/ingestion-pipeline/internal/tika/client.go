package tika

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"path/filepath"
	"strings"
	"time"

	"github.com/NEMYSESx/Orbit/apps/ingestion-pipeline/internal/config"
	"github.com/NEMYSESx/Orbit/apps/ingestion-pipeline/internal/models"
	"github.com/NEMYSESx/Orbit/apps/ingestion-pipeline/internal/text"
)

type Client struct {
	config     *config.TikaConfig
	httpClient *http.Client
	cleaner    *text.Cleaner
}

func NewClient(cfg *config.TikaConfig) *Client {
	return &Client{
		config: cfg,
		httpClient: &http.Client{
			Timeout: cfg.Timeout.Duration,
		},
		cleaner: text.NewCleaner(true),
	}
}

func (c *Client) ExtractWithMetadata(ctx context.Context, file multipart.File, header *multipart.FileHeader) (*models.ExtractedContent, error) {
	var lastErr error

	for attempt := 0; attempt <= c.config.RetryAttempts; attempt++ {
		if attempt > 0 {
			select {
			case <-ctx.Done():
				return nil, ctx.Err()
			case <-time.After(c.config.RetryDelay.Duration):
			}
		}

		result, err := c.extractWithMetadataAttempt(ctx, file, header)
		if err == nil {
			return result, nil
		}

		lastErr = err
	}

	return nil, fmt.Errorf("failed after %d attempts: %w", c.config.RetryAttempts+1, lastErr)
}

func (c *Client) extractWithMetadataAttempt(ctx context.Context, file multipart.File, header *multipart.FileHeader) (*models.ExtractedContent, error) {
	file.Seek(0, 0)

	fileContent, err := io.ReadAll(file)
	if err != nil {
		return nil, fmt.Errorf("failed to read file content: %w", err)
	}

	tikaURL := fmt.Sprintf("%s/tika", c.config.ServerURL)
	req, err := http.NewRequestWithContext(ctx, "PUT", tikaURL, bytes.NewReader(fileContent))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	contentType := "application/octet-stream"
	if header != nil && header.Filename != "" {
		switch filepath.Ext(header.Filename) {
		case ".pdf":
			contentType = "application/pdf"
		case ".docx":
			contentType = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
		case ".doc":
			contentType = "application/msword"
		case ".txt":
			contentType = "text/plain"
		case ".html":
			contentType = "text/html"
		case ".rtf":
			contentType = "application/rtf"
		case ".odt":
			contentType = "application/vnd.oasis.opendocument.text"
		}
	}

	req.Header.Set("Content-Type", contentType)
	req.Header.Set("Accept", "text/plain")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to execute tika request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("tika server returned status %d: %s", resp.StatusCode, string(bodyBytes))
	}

	extractedText, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response body: %w", err)
	}

	metaURL := fmt.Sprintf("%s/meta", c.config.ServerURL)
	metaReq, err := http.NewRequestWithContext(ctx, "PUT", metaURL, bytes.NewReader(fileContent))
	if err != nil {
		return nil, fmt.Errorf("failed to create metadata request: %w", err)
	}
	metaReq.Header.Set("Content-Type", contentType)
	metaReq.Header.Set("Accept", "application/json")

	metaResp, err := c.httpClient.Do(metaReq)
	if err != nil {
		return nil, fmt.Errorf("failed to execute metadata request: %w", err)
	}
	defer metaResp.Body.Close()

	if metaResp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(metaResp.Body)
		return nil, fmt.Errorf("tika metadata request returned status %d: %s", metaResp.StatusCode, string(bodyBytes))
	}

	var metadata map[string]interface{}
	if err := json.NewDecoder(metaResp.Body).Decode(&metadata); err != nil {
		return nil, fmt.Errorf("failed to decode metadata response: %w", err)
	}

	rawText := string(extractedText)
	cleanText := c.cleaner.Clean(rawText)
	wordCount := c.cleaner.CountWords(cleanText)
	pageCount := extractPageCount(metadata)

	checksum := generateChecksum(fileContent)

	title := extractStringFromMetadata(metadata, []string{"dc:title", "title", "Title"})
	author := extractStringFromMetadata(metadata, []string{"dc:creator", "Author", "meta:author", "creator"})
	language := extractStringFromMetadata(metadata, []string{"dc:language", "language", "Content-Language"})

	creationDate := extractDateFromMetadata(metadata, []string{
		"dcterms:created", "meta:creation-date", "Creation-Date",
		"dc:created", "created", "dcterms:modified",
	})

	filename := ""
	filepath := ""
	if header != nil && header.Filename != "" {
		filename = header.Filename
		filepath = filename
	}

	return &models.ExtractedContent{
		Metadata: models.DocumentMetadata{
			Title:         title,
			Filepath:      filepath,
			FileSize:      int64(len(fileContent)),
			Author:        author,
			CreationDate:  creationDate,
			Language:      language,
			ContentType:   contentType,
			Checksum:      checksum,
			ProcessedAt:   time.Now(),
			ExtraMetadata: metadata,
		},
		CleanText: cleanText,
		WordCount: wordCount,
		PageCount: pageCount,
	}, nil
}

func generateChecksum(content []byte) string {
	hash := sha256.Sum256(content)
	return hex.EncodeToString(hash[:])
}

func extractStringFromMetadata(metadata map[string]interface{}, keys []string) string {
	if metadata == nil {
		return ""
	}

	for _, key := range keys {
		if value, exists := metadata[key]; exists {
			switch v := value.(type) {
			case string:
				return strings.TrimSpace(v)
			case []interface{}:
				if len(v) > 0 {
					if str, ok := v[0].(string); ok {
						return strings.TrimSpace(str)
					}
				}
			}
		}
	}
	return ""
}

func extractDateFromMetadata(metadata map[string]interface{}, keys []string) *time.Time {
	if metadata == nil {
		return nil
	}

	for _, key := range keys {
		if value, exists := metadata[key]; exists {
			switch v := value.(type) {
			case string:
				if date := parseDate(v); date != nil {
					return date
				}
			case []interface{}:
				if len(v) > 0 {
					if str, ok := v[0].(string); ok {
						if date := parseDate(str); date != nil {
							return date
						}
					}
				}
			}
		}
	}
	return nil
}

func parseDate(dateStr string) *time.Time {
	dateStr = strings.TrimSpace(dateStr)
	if dateStr == "" {
		return nil
	}

	formats := []string{
		time.RFC3339,
		time.RFC3339Nano,
		"2006-01-02T15:04:05Z",
		"2006-01-02T15:04:05",
		"2006-01-02 15:04:05",
		"2006-01-02",
		"2006/01/02",
		"01/02/2006",
		"02/01/2006",
		"2006-01-02T15:04:05.000Z",
	}

	for _, format := range formats {
		if parsed, err := time.Parse(format, dateStr); err == nil {
			return &parsed
		}
	}

	return nil
}

func extractPageCount(metadata map[string]interface{}) int {
	if metadata == nil {
		return 0
	}

	pageFields := []string{
		"xmpTPg:NPages",
		"meta:page-count",
		"Page-Count",
		"dc:pages",
		"pdf:Pages",
	}

	for _, field := range pageFields {
		if value, exists := metadata[field]; exists {
			switch v := value.(type) {
			case float64:
				return int(v)
			case int:
				return v
			case string:
				if parsed := parseInt(v); parsed > 0 {
					return parsed
				}
			}
		}
	}

	return 0
}

func parseInt(s string) int {
	s = strings.TrimSpace(s)
	if s == "" {
		return 0
	}

	var result int
	for _, char := range s {
		if char >= '0' && char <= '9' {
			result = result*10 + int(char-'0')
		} else {
			break
		}
	}
	return result
}
