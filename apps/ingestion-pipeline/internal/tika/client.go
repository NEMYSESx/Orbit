// internal/tika/client.go
package tika

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"github.com/NEMYSESx/orbit/apps/ingestion-pipeline/internal/config"
	"github.com/NEMYSESx/orbit/apps/ingestion-pipeline/internal/models"
)

type Client struct {
	config     *config.TikaConfig
	httpClient *http.Client
}

func NewClient(cfg *config.TikaConfig) *Client {
	return &Client{
		config: cfg,
		httpClient: &http.Client{
			Timeout: cfg.Timeout,
		},
	}
}

func (c *Client) ExtractWithMetadata(ctx context.Context, filePath string) (*models.ExtractedContent, error) {
	var lastErr error
	
	for attempt := 0; attempt <= c.config.RetryAttempts; attempt++ {
		if attempt > 0 {
			select {
			case <-ctx.Done():
				return nil, ctx.Err()
			case <-time.After(c.config.RetryDelay):
			}
		}

		result, err := c.extractWithMetadataAttempt(ctx, filePath)
		if err == nil {
			return result, nil
		}
		
		lastErr = err
	}

	return nil, fmt.Errorf("failed after %d attempts: %w", c.config.RetryAttempts+1, lastErr)
}

func (c *Client) extractWithMetadataAttempt(ctx context.Context, filePath string) (*models.ExtractedContent, error) {
	file, err := os.Open(filePath)
	if err != nil {
		return nil, fmt.Errorf("failed to open file: %w", err)
	}
	defer file.Close()

	var body bytes.Buffer
	writer := multipart.NewWriter(&body)

	part, err := writer.CreateFormFile("file", filepath.Base(filePath))
	if err != nil {
		return nil, fmt.Errorf("failed to create form file: %w", err)
	}

	if _, err := io.Copy(part, file); err != nil {
		return nil, fmt.Errorf("failed to copy file content: %w", err)
	}

	writer.Close()

	tikaURL := fmt.Sprintf("%s/rmeta/json", c.config.ServerURL)
	req, err := http.NewRequestWithContext(ctx, "POST", tikaURL, &body)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", writer.FormDataContentType())

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to execute tika request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("tika server returned status %d: %s", resp.StatusCode, string(bodyBytes))
	}

	var tikaResponses []map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&tikaResponses); err != nil {
		return nil, fmt.Errorf("failed to decode tika response: %w", err)
	}

	if len(tikaResponses) == 0 {
		return nil, fmt.Errorf("no content extracted from document")
	}

	content := ""
	if contentField, exists := tikaResponses[0]["X-TIKA:content"]; exists {
		if contentStr, ok := contentField.(string); ok {
			content = contentStr
		}
	}

	return &models.ExtractedContent{
		RawText: content,
	}, nil
}

func (c *Client) HealthCheck(ctx context.Context) error {
	req, err := http.NewRequestWithContext(ctx, "GET", c.config.ServerURL+"/version", nil)
	if err != nil {
		return err
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("tika server unreachable: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("tika server returned status: %d", resp.StatusCode)
	}

	return nil
}