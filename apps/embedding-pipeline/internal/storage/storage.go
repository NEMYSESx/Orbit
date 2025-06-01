package storage

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"

	"github.com/NEMYSESx/Orbit/apps/embedding-pipeline/internal/config"
	"github.com/NEMYSESx/Orbit/apps/embedding-pipeline/internal/consumer"
	"github.com/google/uuid"
)

type QdrantClient struct {
	baseURL    string
	apiKey     string
	client     *http.Client
	collection string
}

type QdrantPoint struct {
	ID      interface{}            `json:"id"` // Can be string (UUID) or uint64
	Vector  []float32              `json:"vector"`
	Payload map[string]interface{} `json:"payload"`
}

type QdrantUpsertRequest struct {
	Points []QdrantPoint `json:"points"`
}

type QdrantResponse struct {
	Result struct{} `json:"result"`
	Status string   `json:"status"`
	Time   float64  `json:"time"`
}

func NewQdrantClientWithConfig(cfg config.QdrantConfig) (*QdrantClient, error) {
	client := &QdrantClient{
		baseURL:    cfg.URL,
		apiKey:     cfg.APIKey,
		collection: cfg.Collection,
		client: &http.Client{
			Timeout: 30 * time.Second,
		},
	}

	// Create collection if it doesn't exist
	err := client.createCollectionIfNotExistsWithSize(cfg.VectorSize)
	if err != nil {
		return nil, fmt.Errorf("failed to create collection: %w", err)
	}

	return client, nil
}

func (qc *QdrantClient) createCollectionIfNotExistsWithSize(vectorSize int) error {
	// Check if collection exists
	req, err := http.NewRequest("GET", fmt.Sprintf("%s/collections/%s", qc.baseURL, qc.collection), nil)
	if err != nil {
		return err
	}

	if qc.apiKey != "" {
		req.Header.Set("api-key", qc.apiKey)
	}

	resp, err := qc.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusOK {
		return nil // Collection exists
	}

	// Create collection with configurable vector size
	createReq := map[string]interface{}{
		"vectors": map[string]interface{}{
			"size":     vectorSize,
			"distance": "Cosine",
		},
	}

	jsonData, err := json.Marshal(createReq)
	if err != nil {
		return err
	}

	req, err = http.NewRequest("PUT", fmt.Sprintf("%s/collections/%s", qc.baseURL, qc.collection), bytes.NewBuffer(jsonData))
	if err != nil {
		return err
	}

	req.Header.Set("Content-Type", "application/json")
	if qc.apiKey != "" {
		req.Header.Set("api-key", qc.apiKey)
	}

	resp, err = qc.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("failed to create collection: %s", string(body))
	}

	return nil
}

// generateValidPointID creates a valid Qdrant point ID from the chunk data
func (qc *QdrantClient) generateValidPointID(enrichedChunk consumer.EnrichedChunk) string {
	// Option 1: Generate UUID (recommended)
	return uuid.New().String()
	
	// Option 2: Generate deterministic ID based on content (uncomment if you prefer this)
	// data := fmt.Sprintf("%s_%d_%s", 
	//     enrichedChunk.Source.DocumentTitle,
	//     enrichedChunk.ChunkMetadata.ChunkIndex,
	//     enrichedChunk.ChunkMetadata.Timestamp)
	// hash := md5.Sum([]byte(data))
	// return fmt.Sprintf("%x", hash)
}

// createPayload creates payload from chunk metadata
func (qc *QdrantClient) createPayload(enrichedChunk consumer.EnrichedChunk) map[string]interface{} {
	payload := map[string]interface{}{
		"text":           enrichedChunk.Text,
		"document_title": enrichedChunk.Source.DocumentTitle,
		"document_type":  enrichedChunk.Source.DocumentType,
		"section":        enrichedChunk.Source.Section,
		"topic":          enrichedChunk.ChunkMetadata.Topic,
		"keywords":       enrichedChunk.ChunkMetadata.Keywords,
		"entities":       enrichedChunk.ChunkMetadata.Entities,
		"summary":        enrichedChunk.ChunkMetadata.Summary,
		"category":       enrichedChunk.ChunkMetadata.Category,
		"sentiment":      enrichedChunk.ChunkMetadata.Sentiment,
		"complexity":     enrichedChunk.ChunkMetadata.Complexity,
		"language":       enrichedChunk.ChunkMetadata.Language,
		"word_count":     enrichedChunk.ChunkMetadata.WordCount,
		"chunk_index":    enrichedChunk.ChunkMetadata.ChunkIndex,
		"timestamp":      enrichedChunk.ChunkMetadata.Timestamp,
	}

	if enrichedChunk.Source.PageNumber != nil {
		payload["page_number"] = *enrichedChunk.Source.PageNumber
	}

	if enrichedChunk.Source.LastModified != "" {
		payload["last_modified"] = enrichedChunk.Source.LastModified
	}

	return payload
}

// StoreEmbeddings stores multiple enriched chunks as separate points in batch
func (qc *QdrantClient) StoreEmbeddings(enrichedChunks []consumer.EnrichedChunk) error {
	if len(enrichedChunks) == 0 {
		return fmt.Errorf("no chunks to store")
	}

	var points []QdrantPoint

	// Create a point for each enriched chunk
	for _, enrichedChunk := range enrichedChunks {
		pointID := qc.generateValidPointID(enrichedChunk)
		payload := qc.createPayload(enrichedChunk)

		point := QdrantPoint{
			ID:      pointID,
			Vector:  enrichedChunk.Embedding,
			Payload: payload,
		}

		points = append(points, point)
	}

	// Create batch upsert request
	upsertReq := QdrantUpsertRequest{
		Points: points,
	}

	jsonData, err := json.Marshal(upsertReq)
	if err != nil {
		return fmt.Errorf("error marshaling batch upsert request: %w", err)
	}

	// Send batch request to Qdrant
	url := fmt.Sprintf("%s/collections/%s/points", qc.baseURL, qc.collection)
	req, err := http.NewRequest("PUT", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return fmt.Errorf("error creating batch request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	if qc.apiKey != "" {
		req.Header.Set("api-key", qc.apiKey)
	}

	resp, err := qc.client.Do(req)
	if err != nil {
		return fmt.Errorf("error sending batch request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("failed to store batch embeddings (status %d): %s", resp.StatusCode, string(body))
	}

	fmt.Printf("Successfully stored %d embeddings as separate points\n", len(enrichedChunks))
	
	// Log details about each stored chunk
	for i, chunk := range enrichedChunks {
		fmt.Printf("  Point %d: Document='%s', ChunkIndex=%d, WordCount=%d\n", 
			i+1, chunk.Source.DocumentTitle, chunk.ChunkMetadata.ChunkIndex, chunk.ChunkMetadata.WordCount)
	}
	
	return nil
}

// StoreEmbedding stores a single enriched chunk (backward compatibility)
func (qc *QdrantClient) StoreEmbedding(enrichedChunk consumer.EnrichedChunk) error {
	return qc.StoreEmbeddings([]consumer.EnrichedChunk{enrichedChunk})
}

func (qc *QdrantClient) SearchSimilar(query []float32, limit int) ([]QdrantPoint, error) {
	searchReq := map[string]interface{}{
		"vector": query,
		"limit":  limit,
		"with_payload": true,
	}

	jsonData, err := json.Marshal(searchReq)
	if err != nil {
		return nil, fmt.Errorf("error marshaling search request: %w", err)
	}

	url := fmt.Sprintf("%s/collections/%s/points/search", qc.baseURL, qc.collection)
	req, err := http.NewRequest("POST", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("error creating request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	if qc.apiKey != "" {
		req.Header.Set("api-key", qc.apiKey)
	}

	resp, err := qc.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("error sending request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("search failed (status %d): %s", resp.StatusCode, string(body))
	}

	var searchResp struct {
		Result []struct {
			ID      interface{}            `json:"id"` // Can be string or number
			Score   float64               `json:"score"`
			Payload map[string]interface{} `json:"payload"`
		} `json:"result"`
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("error reading response: %w", err)
	}

	err = json.Unmarshal(body, &searchResp)
	if err != nil {
		return nil, fmt.Errorf("error unmarshaling response: %w", err)
	}

	var points []QdrantPoint
	for _, result := range searchResp.Result {
		points = append(points, QdrantPoint{
			ID:      result.ID,
			Payload: result.Payload,
		})
	}

	return points, nil
}

func getEnvOrDefault(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}