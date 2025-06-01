package embedders

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"

	"github.com/NEMYSESx/Orbit/apps/embedding-pipeline/internal/config"
)

type GoogleEmbedder struct {
	apiKey string
	model  string
	client *http.Client
}

// NewGeminiEmbedderWithConfig creates embedder using config
func NewGeminiEmbedderWithConfig(cfg config.GeminiConfig) (*GoogleEmbedder, error) {
	return &GoogleEmbedder{
		apiKey: cfg.APIKey,
		model:  cfg.Model,
		client: &http.Client{},
	}, nil
}

// GenerateEmbedding converts only the text content into embeddings using Google AI Studio API
func (ge *GoogleEmbedder) GenerateEmbedding(text string) ([]float32, error) {
	if text == "" {
		return nil, fmt.Errorf("input text cannot be empty")
	}

	// Google AI Studio Embedding API endpoint for text-embedding-004
	apiURL := fmt.Sprintf("https://generativelanguage.googleapis.com/v1beta/models/%s:embedContent?key=%s",
		ge.model, ge.apiKey)

	// Request body structure for Google AI Studio embedContent API
	reqBody := map[string]interface{}{
		"content": map[string]interface{}{
			"parts": []map[string]interface{}{
				{
					"text": text,
				},
			},
		},
		// Optional: specify task type for better embeddings
		"taskType": "RETRIEVAL_DOCUMENT",
	}

	jsonData, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("error marshaling request: %w", err)
	}

	req, err := http.NewRequest("POST", apiURL, bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("error creating request: %w", err)
	}

	// Set proper headers for Google AI Studio API
	req.Header.Set("Content-Type", "application/json")

	resp, err := ge.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("error sending request: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("error reading response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("API request failed with status %d: %s", resp.StatusCode, string(body))
	}

	// Response structure for embedContent API
	var response struct {
		Embedding struct {
			Values []float32 `json:"values"`
		} `json:"embedding"`
	}

	err = json.Unmarshal(body, &response)
	if err != nil {
		return nil, fmt.Errorf("error unmarshaling response: %w", err)
	}

	if len(response.Embedding.Values) == 0 {
		return nil, fmt.Errorf("empty embedding returned")
	}

	return response.Embedding.Values, nil
}