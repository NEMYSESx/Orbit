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

type JSONMetadata struct {
	KeyCount     int                    `json:"keyCount"`
	MaxDepth     int                    `json:"maxDepth"`
	ArrayCount   int                    `json:"arrayCount"`
	ObjectCount  int                    `json:"objectCount"`
	DataTypes    map[string]int         `json:"dataTypes"`
	TopLevelKeys []string               `json:"topLevelKeys"`
	Structure    map[string]interface{} `json:"structure"`
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
	if header != nil && strings.ToLower(filepath.Ext(header.Filename)) == ".json" {
		return c.extractJSONContent(ctx, file, header)
	}

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

func (c *Client) extractJSONContent(ctx context.Context, file multipart.File, header *multipart.FileHeader) (*models.ExtractedContent, error) {
	file.Seek(0, 0)

	fileContent, err := io.ReadAll(file)
	if err != nil {
		return nil, fmt.Errorf("failed to read JSON file content: %w", err)
	}

	var jsonData interface{}
	if err := json.Unmarshal(fileContent, &jsonData); err != nil {
		return nil, fmt.Errorf("failed to parse JSON content: %w", err)
	}

	jsonMeta := c.analyzeJSON(jsonData)
	
	cleanText := c.jsonToText(jsonData, 0)
	wordCount := c.cleaner.CountWords(cleanText)
	checksum := generateChecksum(fileContent)

	title := ""
	author := ""
	language := "json"
	
	if obj, ok := jsonData.(map[string]interface{}); ok {
		if titleVal, exists := obj["title"]; exists {
			if titleStr, ok := titleVal.(string); ok {
				title = titleStr
			}
		}
		if authorVal, exists := obj["author"]; exists {
			if authorStr, ok := authorVal.(string); ok {
				author = authorStr
			}
		}
	}

	filename := ""
	filepath := ""
	if header != nil && header.Filename != "" {
		filename = header.Filename
		filepath = filename
		if title == "" {
			title = strings.TrimSuffix(filename, ".json")
		}
	}

	metadata := map[string]interface{}{
		"content-type":     "application/json",
		"json-key-count":   jsonMeta.KeyCount,
		"json-max-depth":   jsonMeta.MaxDepth,
		"json-array-count": jsonMeta.ArrayCount,
		"json-object-count": jsonMeta.ObjectCount,
		"json-data-types":  jsonMeta.DataTypes,
		"json-top-keys":    jsonMeta.TopLevelKeys,
		"json-structure":   jsonMeta.Structure,
	}

	return &models.ExtractedContent{
		Metadata: models.DocumentMetadata{
			Title:         title,
			Filepath:      filepath,
			FileSize:      int64(len(fileContent)),
			Author:        author,
			CreationDate:  nil, 
			Language:      language,
			ContentType:   "application/json",
			Checksum:      checksum,
			ProcessedAt:   time.Now(),
			ExtraMetadata: metadata,
		},
		CleanText: cleanText,
		WordCount: wordCount,
		PageCount: 1, 
	}, nil
}

func (c *Client) analyzeJSON(data interface{}) *JSONMetadata {
	meta := &JSONMetadata{
		DataTypes: make(map[string]int),
		Structure: make(map[string]interface{}),
	}

	c.analyzeJSONRecursive(data, meta, 0, "")
	return meta
}

func (c *Client) analyzeJSONRecursive(data interface{}, meta *JSONMetadata, depth int, path string) {
	if depth > meta.MaxDepth {
		meta.MaxDepth = depth
	}

	switch v := data.(type) {
	case map[string]interface{}:
		meta.ObjectCount++
		meta.DataTypes["object"]++
		
		if depth == 0 {
			for key := range v {
				meta.TopLevelKeys = append(meta.TopLevelKeys, key)
				meta.KeyCount++
			}
		}

		if depth <= 2 {
			structObj := make(map[string]interface{})
			for key, value := range v {
				structObj[key] = c.getValueType(value)
			}
			if path == "" {
				meta.Structure = structObj
			}
		}

		for key, value := range v {
			newPath := key
			if path != "" {
				newPath = path + "." + key
			}
			c.analyzeJSONRecursive(value, meta, depth+1, newPath)
		}

	case []interface{}:
		meta.ArrayCount++
		meta.DataTypes["array"]++
		
		for i, item := range v {
			newPath := fmt.Sprintf("%s[%d]", path, i)
			c.analyzeJSONRecursive(item, meta, depth+1, newPath)
		}

	case string:
		meta.DataTypes["string"]++
	case float64:
		meta.DataTypes["number"]++
	case bool:
		meta.DataTypes["boolean"]++
	case nil:
		meta.DataTypes["null"]++
	}
}

func (c *Client) getValueType(value interface{}) string {
	switch value.(type) {
	case map[string]interface{}:
		return "object"
	case []interface{}:
		return "array"
	case string:
		return "string"
	case float64:
		return "number"
	case bool:
		return "boolean"
	case nil:
		return "null"
	default:
		return "unknown"
	}
}

func (c *Client) jsonToText(data interface{}, depth int) string {
	var builder strings.Builder
	c.jsonToTextRecursive(data, &builder, depth, "")
	return c.cleaner.Clean(builder.String())
}

func (c *Client) jsonToTextRecursive(data interface{}, builder *strings.Builder, depth int, prefix string) {
	indent := strings.Repeat("  ", depth)
	
	switch v := data.(type) {
	case map[string]interface{}:
		for key, value := range v {
			builder.WriteString(fmt.Sprintf("%s%s%s: ", indent, prefix, key))
			
			switch val := value.(type) {
			case string:
				builder.WriteString(fmt.Sprintf("%s\n", val))
			case float64:
				builder.WriteString(fmt.Sprintf("%.2f\n", val))
			case bool:
				builder.WriteString(fmt.Sprintf("%t\n", val))
			case nil:
				builder.WriteString("null\n")
			case map[string]interface{}, []interface{}:
				builder.WriteString("\n")
				c.jsonToTextRecursive(value, builder, depth+1, "")
			default:
				builder.WriteString(fmt.Sprintf("%v\n", val))
			}
		}
		
	case []interface{}:
		for i, item := range v {
			c.jsonToTextRecursive(item, builder, depth, fmt.Sprintf("[%d] ", i))
		}
		
	case string:
		builder.WriteString(fmt.Sprintf("%s%s%s\n", indent, prefix, v))
	case float64:
		builder.WriteString(fmt.Sprintf("%s%s%.2f\n", indent, prefix, v))
	case bool:
		builder.WriteString(fmt.Sprintf("%s%s%t\n", indent, prefix, v))
	case nil:
		builder.WriteString(fmt.Sprintf("%s%snull\n", indent, prefix))
	default:
		builder.WriteString(fmt.Sprintf("%s%s%v\n", indent, prefix, v))
	}
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
		case ".json":
			contentType = "application/json"
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