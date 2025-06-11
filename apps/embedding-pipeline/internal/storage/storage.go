package storage

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"sync"
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
	
	buffer     []consumer.EnrichedChunk
	bufferMu   sync.Mutex
	bufferSize int
	flushTimer *time.Timer
	flushInterval time.Duration
}

type QdrantPoint struct {
	ID      interface{}            `json:"id"` 
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
		baseURL:       cfg.URL,
		apiKey:        cfg.APIKey,
		collection:    cfg.Collection,
		bufferSize:    50, 
		flushInterval: 5 * time.Second, 
		client: &http.Client{
			Timeout: 30 * time.Second,
		},
	}

	err := client.createCollectionIfNotExistsWithSize(cfg.VectorSize)
	if err != nil {
		return nil, fmt.Errorf("failed to create collection: %w", err)
	}

	return client, nil
}

func (qc *QdrantClient) createCollectionIfNotExistsWithSize(vectorSize int) error {
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
		return nil 
	}
	
	if resp.StatusCode != http.StatusNotFound {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("unexpected status checking collection: %d, %s", resp.StatusCode, string(body))
	}
	
	createReq := map[string]interface{}{
		"vectors": map[string]interface{}{
			"size":     vectorSize,
			"distance": "Cosine",
			"hnsw_config": map[string]interface{}{
				"m":            16,
				"ef_construct": 200,
			},
			"quantization_config": map[string]interface{}{
				"scalar": map[string]interface{}{
					"type":       "int8",
					"always_ram": true,
				},
			},
			"on_disk": true,
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

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("failed to create collection (status %d): %s", resp.StatusCode, string(body))
	}
	
	fmt.Printf("Successfully created collection '%s' with vector size %d\n", qc.collection, vectorSize)
	return nil
}

func (qc *QdrantClient) generateValidPointID() string {
	return uuid.New().String()
}

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

func (qc *QdrantClient) AddToBuffer(enrichedChunk consumer.EnrichedChunk) error {
	qc.bufferMu.Lock()
	defer qc.bufferMu.Unlock()
	
	qc.buffer = append(qc.buffer, enrichedChunk)
	
	if qc.flushTimer != nil {
		qc.flushTimer.Stop()
	}
	qc.flushTimer = time.AfterFunc(qc.flushInterval, func() {
		if err := qc.flushBuffer(); err != nil {
			fmt.Printf("Error flushing buffer: %v\n", err)
		}
	})
	
	if len(qc.buffer) >= qc.bufferSize {
		return qc.flushBufferLocked()
	}
	
	return nil
}

func (qc *QdrantClient) flushBuffer() error {
	qc.bufferMu.Lock()
	defer qc.bufferMu.Unlock()
	return qc.flushBufferLocked()
}

func (qc *QdrantClient) flushBufferLocked() error {
	if len(qc.buffer) == 0 {
		return nil
	}
	
	chunks := make([]consumer.EnrichedChunk, len(qc.buffer))
	copy(chunks, qc.buffer)
	qc.buffer = qc.buffer[:0]
	
	if qc.flushTimer != nil {
		qc.flushTimer.Stop()
	}
	
	return qc.storeEmbeddingsInternal(chunks)
}

func (qc *QdrantClient) FlushBuffer() error {
	return qc.flushBuffer()
}

func (qc *QdrantClient) storeEmbeddingsInternal(enrichedChunks []consumer.EnrichedChunk) error {
	if len(enrichedChunks) == 0 {
		return nil
	}

	var points []QdrantPoint

	for _, enrichedChunk := range enrichedChunks {
		pointID := qc.generateValidPointID()
		payload := qc.createPayload(enrichedChunk)

		point := QdrantPoint{
			ID:      pointID,
			Vector:  enrichedChunk.Embedding,
			Payload: payload,
		}

		points = append(points, point)
	}

	upsertReq := QdrantUpsertRequest{
		Points: points,
	}

	jsonData, err := json.Marshal(upsertReq)
	if err != nil {
		return fmt.Errorf("error marshaling batch upsert request: %w", err)
	}

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
	return nil
}

func (qc *QdrantClient) StoreEmbeddings(enrichedChunks []consumer.EnrichedChunk) error {
	return qc.storeEmbeddingsInternal(enrichedChunks)
}

func (qc *QdrantClient) StoreEmbedding(enrichedChunk consumer.EnrichedChunk) error {
	return qc.AddToBuffer(enrichedChunk)
}