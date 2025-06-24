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

type DocumentQdrantClient struct {
	baseURL       string
	apiKey        string
	client        *http.Client
	collections   map[string]string 
	
	documentBuffer        []consumer.EnrichedChunk
	documentBufferMu      sync.Mutex
	documentBufferSize    int
	documentFlushTimer    *time.Timer
	documentFlushInterval time.Duration
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

func NewDocumentQdrantClientWithConfig(cfg config.QdrantConfig) (*DocumentQdrantClient, error) {
	client := &DocumentQdrantClient{
		baseURL:       cfg.URL,
		apiKey:        cfg.APIKey,
		collections:   cfg.Collections,
		documentBufferSize:    50, 
		documentFlushInterval: 5 * time.Second,
		client: &http.Client{
			Timeout: 30 * time.Second,
		},
	}

	for topic, collectionName := range cfg.Collections {
		if topic != "logs" {
			err := client.createCollectionIfNotExistsWithSize(collectionName, cfg.VectorSize)
			if err != nil {
				return nil, fmt.Errorf("failed to create collection %s for topic %s: %w", collectionName, topic, err)
			}
		}
	}

	return client, nil
}

func (dc *DocumentQdrantClient) createCollectionIfNotExistsWithSize(collectionName string, vectorSize int) error {
	req, err := http.NewRequest("GET", fmt.Sprintf("%s/collections/%s", dc.baseURL, collectionName), nil)
	if err != nil {
		return err
	}

	if dc.apiKey != "" {
		req.Header.Set("api-key", dc.apiKey)
	}

	resp, err := dc.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusOK {
		fmt.Printf("Collection '%s' already exists\n", collectionName)
		return nil 
	}
	
	if resp.StatusCode != http.StatusNotFound {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("unexpected status checking collection %s: %d, %s", collectionName, resp.StatusCode, string(body))
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

	req, err = http.NewRequest("PUT", fmt.Sprintf("%s/collections/%s", dc.baseURL, collectionName), bytes.NewBuffer(jsonData))
	if err != nil {
		return err
	}

	req.Header.Set("Content-Type", "application/json")
	if dc.apiKey != "" {
		req.Header.Set("api-key", dc.apiKey)
	}

	resp, err = dc.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("failed to create collection %s (status %d): %s", collectionName, resp.StatusCode, string(body))
	}
	
	fmt.Printf("Successfully created collection '%s' with vector size %d\n", collectionName, vectorSize)
	return nil
}

func (dc *DocumentQdrantClient) generateValidPointID() string {
	return uuid.New().String()
}

func (dc *DocumentQdrantClient) createDocumentPayload(enrichedChunk consumer.EnrichedChunk) map[string]interface{} {
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
		"kafka_topic":    enrichedChunk.KafkaTopic,
	}

	if enrichedChunk.Source.PageNumber != nil {
		payload["page_number"] = *enrichedChunk.Source.PageNumber
	}

	if enrichedChunk.Source.LastModified != "" {
		payload["last_modified"] = enrichedChunk.Source.LastModified
	}

	return payload
}

func (dc *DocumentQdrantClient) getCollectionForTopic(kafkaTopic string) string {
	if collectionName, exists := dc.collections[kafkaTopic]; exists {
		return collectionName
	}
	return kafkaTopic
}

func (dc *DocumentQdrantClient) AddDocumentToBuffer(enrichedChunk consumer.EnrichedChunk) error {
	dc.documentBufferMu.Lock()
	defer dc.documentBufferMu.Unlock()
	
	dc.documentBuffer = append(dc.documentBuffer, enrichedChunk)
	
	if dc.documentFlushTimer != nil {
		dc.documentFlushTimer.Stop()
	}
	dc.documentFlushTimer = time.AfterFunc(dc.documentFlushInterval, func() {
		if err := dc.flushDocumentBuffer(); err != nil {
			fmt.Printf("Error flushing document buffer: %v\n", err)
		}
	})
	
	if len(dc.documentBuffer) >= dc.documentBufferSize {
		return dc.flushDocumentBufferLocked()
	}
	
	return nil
}

func (dc *DocumentQdrantClient) flushDocumentBuffer() error {
	dc.documentBufferMu.Lock()
	defer dc.documentBufferMu.Unlock()
	return dc.flushDocumentBufferLocked()
}

func (dc *DocumentQdrantClient) flushDocumentBufferLocked() error {
	if len(dc.documentBuffer) == 0 {
		return nil
	}
	
	chunks := make([]consumer.EnrichedChunk, len(dc.documentBuffer))
	copy(chunks, dc.documentBuffer)
	dc.documentBuffer = dc.documentBuffer[:0]
	
	if dc.documentFlushTimer != nil {
		dc.documentFlushTimer.Stop()
	}
	
	return dc.storeDocumentsInternal(chunks)
}

func (dc *DocumentQdrantClient) storeDocumentsInternal(enrichedChunks []consumer.EnrichedChunk) error {
	if len(enrichedChunks) == 0 {
		return nil
	}

	collectionGroups := make(map[string][]consumer.EnrichedChunk)
	
	for _, chunk := range enrichedChunks {
		collectionName := dc.getCollectionForTopic(chunk.KafkaTopic)
		collectionGroups[collectionName] = append(collectionGroups[collectionName], chunk)
	}

	for collectionName, chunks := range collectionGroups {
		err := dc.storeDocumentChunksInCollection(collectionName, chunks)
		if err != nil {
			return fmt.Errorf("failed to store document chunks in collection %s: %w", collectionName, err)
		}
	}

	return nil
}

func (dc *DocumentQdrantClient) storeDocumentChunksInCollection(collectionName string, enrichedChunks []consumer.EnrichedChunk) error {
	var points []QdrantPoint

	for _, enrichedChunk := range enrichedChunks {
		pointID := dc.generateValidPointID()
		payload := dc.createDocumentPayload(enrichedChunk)

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

	url := fmt.Sprintf("%s/collections/%s/points", dc.baseURL, collectionName)
	req, err := http.NewRequest("PUT", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return fmt.Errorf("error creating batch request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	if dc.apiKey != "" {
		req.Header.Set("api-key", dc.apiKey)
	}

	resp, err := dc.client.Do(req)
	if err != nil {
		return fmt.Errorf("error sending batch request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("failed to store batch document embeddings in collection %s (status %d): %s", collectionName, resp.StatusCode, string(body))
	}

	fmt.Printf("Successfully stored %d document embeddings in collection '%s'\n", len(enrichedChunks), collectionName)
	return nil
}

func (dc *DocumentQdrantClient) StoreDocuments(enrichedChunks []consumer.EnrichedChunk) error {
	return dc.storeDocumentsInternal(enrichedChunks)
}

func (dc *DocumentQdrantClient) StoreDocument(enrichedChunk consumer.EnrichedChunk) error {
	return dc.AddDocumentToBuffer(enrichedChunk)
}

func (dc *DocumentQdrantClient) FlushDocumentBuffer() error {
	return dc.flushDocumentBuffer()
}

func (dc *DocumentQdrantClient) CreateDocumentPayloadIndexes() error {
	documentFields := []string{
		"category", "complexity", "document_type", "language",
		"sentiment", "topic", "entities", "keywords", "kafka_topic",
	}

	for topic, collectionName := range dc.collections {
		if topic != "logs" {
			fmt.Printf("Creating payload indexes for document collection '%s' (topic: %s)\n", collectionName, topic)
			
			for _, field := range documentFields {
				url := fmt.Sprintf("%s/collections/%s/index", dc.baseURL, collectionName)

				payload := map[string]interface{}{
					"field_name": field,
					"field_schema": map[string]interface{}{
						"type": "keyword",
					},
				}

				jsonData, err := json.Marshal(payload)
				if err != nil {
					return fmt.Errorf("failed to marshal payload index request for field %s in collection %s: %w", field, collectionName, err)
				}

				req, err := http.NewRequest("PUT", url, bytes.NewBuffer(jsonData))
				if err != nil {
					return fmt.Errorf("failed to create payload index request for field %s in collection %s: %w", field, collectionName, err)
				}

				req.Header.Set("Content-Type", "application/json")
				if dc.apiKey != "" {
					req.Header.Set("api-key", dc.apiKey)
				}

				resp, err := dc.client.Do(req)
				if err != nil {
					return fmt.Errorf("failed to send payload index request for field %s in collection %s: %w", field, collectionName, err)
				}
				defer resp.Body.Close()

				if resp.StatusCode != http.StatusOK {
					body, _ := io.ReadAll(resp.Body)
					return fmt.Errorf("failed to create index for field %s in collection %s (status %d): %s", field, collectionName, resp.StatusCode, string(body))
				}
			}
		}
	}

	fmt.Println("All document payload indexes created successfully.")
	return nil
}

func (dc *DocumentQdrantClient) AddToBuffer(enrichedChunk consumer.EnrichedChunk) error {
	return dc.AddDocumentToBuffer(enrichedChunk)
}

func (dc *DocumentQdrantClient) StoreEmbeddings(enrichedChunks []consumer.EnrichedChunk) error {
	return dc.StoreDocuments(enrichedChunks)
}

func (dc *DocumentQdrantClient) StoreEmbedding(enrichedChunk consumer.EnrichedChunk) error {
	return dc.StoreDocument(enrichedChunk)
}