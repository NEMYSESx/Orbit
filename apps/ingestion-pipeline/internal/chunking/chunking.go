package chunking

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/NEMYSESx/Orbit/apps/ingestion-pipeline/internal/models"
)

type AgenticChunker struct {
	apiKey     string
	baseURL    string
	client     *http.Client
	maxRetries int
	config     models.ChunkingConfig
}

func NewAgenticChunker(apiKey string) *AgenticChunker {
	return &AgenticChunker{
		apiKey:  apiKey,
		baseURL: "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent",
		client: &http.Client{
			Timeout: 60 * time.Second,
		},
		maxRetries: 3,
	}
}

func NewAgenticChunkerWithConfig(config models.ChunkingConfig) *AgenticChunker {
	timeout := config.RequestTimeout
	if timeout == 0 {
		timeout = 60 * time.Second
	}
	
	maxRetries := config.MaxRetries
	if maxRetries == 0 {
		maxRetries = 3
	}

	return &AgenticChunker{
		apiKey:  config.GeminiAPIKey,
		baseURL: "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent",
		client: &http.Client{
			Timeout: timeout,
		},
		maxRetries: maxRetries,
		config:     config,
	}
}

func (ac *AgenticChunker) ChunkText(ctx context.Context, text string) (*models.ChunkerResult, error) {
	if strings.TrimSpace(text) == "" {
		return nil, fmt.Errorf("input text cannot be empty")
	}

	prompt := ac.buildChunkingPrompt(text)
	
	geminiResponse, err := ac.callGeminiAPI(ctx, prompt)
	if err != nil {
		return nil, fmt.Errorf("failed to call Gemini API: %w", err)
	}

	chunks, err := ac.parseGeminiResponse(geminiResponse)
	if err != nil {
		return nil, fmt.Errorf("failed to parse Gemini response: %w", err)
	}

	result := &models.ChunkerResult{
		Chunks:      chunks,
		TotalCount:  len(chunks),
		ProcessedAt: time.Now().UTC().Format(time.RFC3339),
	}

	return result, nil
}

func (ac *AgenticChunker) ChunkTextWithSource(ctx context.Context, text string, sourceInfo models.SourceInfo) ([]models.ChunkOutput, error) {
	result, err := ac.ChunkText(ctx, text)
	if err != nil {
		return nil, err
	}
	
	return ac.ConvertToChunkOutput(result, sourceInfo), nil
}

func (ac *AgenticChunker) buildChunkingPrompt(text string) string {
	return fmt.Sprintf(`You are an expert text analyst. Please analyze the following text and break it into semantically meaningful chunks. Each chunk should represent a complete thought, concept, or topic.

For each chunk, provide:
1. The actual text content
2. A descriptive topic/title
3. Key keywords (3-8 words)
4. Named entities (people, places, organizations, etc.)
5. A brief summary (1-2 sentences)
6. A category (e.g., "technical", "narrative", "instructional", "analytical", etc.)
7. Sentiment (positive, negative, neutral, mixed)
8. Complexity level (simple, moderate, complex)
9. Language (detected language)

Guidelines:
- Each chunk should be 100-500 words ideally
- Maintain semantic coherence within each chunk
- Avoid breaking sentences in the middle
- Ensure chunks have clear topical boundaries
- Include transitional context when necessary

Please respond with a JSON object in exactly this format:
{
  "chunks": [
    {
      "content": "actual chunk text here",
      "topic": "descriptive topic",
      "keywords": ["keyword1", "keyword2", "keyword3"],
      "entities": ["entity1", "entity2"],
      "summary": "brief summary",
      "category": "category name",
      "sentiment": "sentiment",
      "complexity": "complexity level",
      "language": "language"
    }
  ]
}

Text to analyze:
%s`, text)
}

func (ac *AgenticChunker) callGeminiAPI(ctx context.Context, prompt string) (string, error) {
	reqBody := models.GeminiRequest{
		Contents: []models.Content{
			{
				Parts: []models.Part{
					{Text: prompt},
				},
			},
		},
	}

	jsonData, err := json.Marshal(reqBody)
	if err != nil {
		return "", fmt.Errorf("failed to marshal request: %w", err)
	}

	url := fmt.Sprintf("%s?key=%s", ac.baseURL, ac.apiKey)
	
	var lastErr error
	for attempt := 0; attempt <= ac.maxRetries; attempt++ {
		if attempt > 0 {
			backoffDuration := time.Duration(attempt*attempt) * time.Second
			fmt.Printf("Retrying Gemini API call (attempt %d) after %v\n", attempt+1, backoffDuration)
			time.Sleep(backoffDuration)
		}

		req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer(jsonData))
		if err != nil {
			lastErr = fmt.Errorf("failed to create request: %w", err)
			continue
		}

		req.Header.Set("Content-Type", "application/json")

		resp, err := ac.client.Do(req)
		if err != nil {
			lastErr = fmt.Errorf("failed to make request: %w", err)
			continue
		}

		if resp.StatusCode == http.StatusTooManyRequests {
			resp.Body.Close()
			lastErr = fmt.Errorf("rate limit exceeded")
			continue
		}

		if resp.StatusCode != http.StatusOK {
			body, _ := io.ReadAll(resp.Body)
			resp.Body.Close()
			lastErr = fmt.Errorf("API request failed with status %d: %s", resp.StatusCode, string(body))
			continue
		}

		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			lastErr = fmt.Errorf("failed to read response body: %w", err)
			continue
		}
		fmt.Println("Raw Gemini response:", resp.Body)


		var geminiResp models.GeminiResponse
		if err := json.Unmarshal(body, &geminiResp); err != nil {
			lastErr = fmt.Errorf("failed to unmarshal response: %w", err)
			continue
		}

		if len(geminiResp.Candidates) == 0 || len(geminiResp.Candidates[0].Content.Parts) == 0 {
			lastErr = fmt.Errorf("no content in Gemini response")
			continue
		}

		return geminiResp.Candidates[0].Content.Parts[0].Text, nil
	}

	return "", fmt.Errorf("failed after %d retries: %w", ac.maxRetries, lastErr)
}

func (ac *AgenticChunker) parseGeminiResponse(response string) ([]models.Chunk, error) {
	response = strings.TrimSpace(response)
	
	if strings.HasPrefix(response, "```json") {
		response = strings.TrimPrefix(response, "```json")
		response = strings.TrimSuffix(response, "```")
	} else if strings.HasPrefix(response, "```") {
		response = strings.TrimPrefix(response, "```")
		response = strings.TrimSuffix(response, "```")
	}
	
	response = strings.TrimSpace(response)

	var geminiResp models.GeminiChunkerResponse
	if err := json.Unmarshal([]byte(response), &geminiResp); err != nil {
		return nil, fmt.Errorf("failed to parse Gemini JSON response: %w", err)
	}

	chunks := make([]models.Chunk, 0, len(geminiResp.Chunks))
	timestamp := time.Now().UTC().Format(time.RFC3339)

	for i, geminiChunk := range geminiResp.Chunks {
		chunk := models.Chunk{
			ID:      fmt.Sprintf("chunk_%d_%d", time.Now().Unix(), i),
			Content: geminiChunk.Content,
			Metadata: models.ChunkMetadata{
				Topic:       geminiChunk.Topic,
				Keywords:    geminiChunk.Keywords,
				Entities:    geminiChunk.Entities,
				Summary:     geminiChunk.Summary,
				Category:    geminiChunk.Category,
				Sentiment:   geminiChunk.Sentiment,
				Complexity:  geminiChunk.Complexity,
				Language:    geminiChunk.Language,
				WordCount:   len(strings.Fields(geminiChunk.Content)),
				ChunkIndex:  i,
				Timestamp:   timestamp,
			},
		}
		chunks = append(chunks, chunk)
	}

	return chunks, nil
}

func (ac *AgenticChunker) ConvertToChunkOutput(result *models.ChunkerResult, sourceInfo models.SourceInfo) []models.ChunkOutput {
	chunkOutputs := make([]models.ChunkOutput, len(result.Chunks))
	
	for i, chunk := range result.Chunks {
		chunkOutputs[i] = models.ChunkOutput{
			Text:   chunk.Content,
			Source: sourceInfo,
			ChunkMetadata: chunk.Metadata,
		}
	}
	
	return chunkOutputs
}

func NewChunker(config models.ChunkingConfig) *AgenticChunker {
	return NewAgenticChunker(config.GeminiAPIKey)
}