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
	"github.com/google/uuid"
)

type QdrantClient struct {
	baseURL    string
	apiKey     string
	client     *http.Client
	collection string

	buffer        []QdrantPoint
	bufferMu      sync.Mutex
	bufferSize    int
	flushTimer    *time.Timer
	flushInterval time.Duration
}

type EmbeddedData struct {
	ID        string                 `json:"id,omitempty"`       
	Embedding []float32              `json:"embedding"`           
	Payload   map[string]interface{} `json:"payload"`            
}

func NewQdrantClient(cfg config.QdrantConfig, collectionName string) (*QdrantClient, error) {
	client := &QdrantClient{
		baseURL:       cfg.URL,
		apiKey:        cfg.APIKey,
		collection:    collectionName,
		bufferSize:    50,
		flushInterval: 5 * time.Second,
		client: &http.Client{
			Timeout: 30 * time.Second,
		},
	}

	err := client.createCollectionIfNotExists(cfg.VectorSize)
	if err != nil {
		return nil, fmt.Errorf("failed to create collection %s: %w", collectionName, err)
	}

	return client, nil
}

func (c *QdrantClient) createCollectionIfNotExists(vectorSize int) error {
	req, err := http.NewRequest("GET", fmt.Sprintf("%s/collections/%s", c.baseURL, c.collection), nil)
	if err != nil {
		return err
	}

	if c.apiKey != "" {
		req.Header.Set("api-key", c.apiKey)
	}

	resp, err := c.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusOK {
		fmt.Printf("Collection '%s' already exists\n", c.collection)
		return nil
	}

	if resp.StatusCode != http.StatusNotFound {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("unexpected status checking collection %s: %d, %s", c.collection, resp.StatusCode, string(body))
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

	req, err = http.NewRequest("PUT", fmt.Sprintf("%s/collections/%s", c.baseURL, c.collection), bytes.NewBuffer(jsonData))
	if err != nil {
		return err
	}

	req.Header.Set("Content-Type", "application/json")
	if c.apiKey != "" {
		req.Header.Set("api-key", c.apiKey)
	}

	resp, err = c.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("failed to create collection %s (status %d): %s", c.collection, resp.StatusCode, string(body))
	}

	fmt.Printf("Successfully created collection '%s' with vector size %d\n", c.collection, vectorSize)
	return nil
}

func (c *QdrantClient) Store(data EmbeddedData) error {
	return c.addToBuffer(data)
}

func (c *QdrantClient) StoreBatch(dataPoints []EmbeddedData) error {
	if len(dataPoints) == 0 {
		return nil
	}

	var points []QdrantPoint
	for _, data := range dataPoints {
		point := c.createPoint(data)
		points = append(points, point)
	}

	return c.upsertPoints(points)
}

func (c *QdrantClient) addToBuffer(data EmbeddedData) error {
	c.bufferMu.Lock()
	defer c.bufferMu.Unlock()

	point := c.createPoint(data)
	c.buffer = append(c.buffer, point)

	if c.flushTimer != nil {
		c.flushTimer.Stop()
	}
	c.flushTimer = time.AfterFunc(c.flushInterval, func() {
		if err := c.flushBuffer(); err != nil {
			fmt.Printf("Error flushing buffer: %v\n", err)
		}
	})

	if len(c.buffer) >= c.bufferSize {
		return c.flushBufferLocked()
	}

	return nil
}

func (c *QdrantClient) FlushBuffer() error {
	c.bufferMu.Lock()
	defer c.bufferMu.Unlock()
	return c.flushBufferLocked()
}

func (c *QdrantClient) flushBuffer() error {
	c.bufferMu.Lock()
	defer c.bufferMu.Unlock()
	return c.flushBufferLocked()
}

func (c *QdrantClient) flushBufferLocked() error {
	if len(c.buffer) == 0 {
		return nil
	}

	points := make([]QdrantPoint, len(c.buffer))
	copy(points, c.buffer)
	c.buffer = c.buffer[:0]

	if c.flushTimer != nil {
		c.flushTimer.Stop()
	}

	return c.upsertPoints(points)
}

func (c *QdrantClient) createPoint(data EmbeddedData) QdrantPoint {
	id := data.ID
	if id == "" {
		id = uuid.New().String()
	}

	return QdrantPoint{
		ID:      id,
		Vector:  data.Embedding,
		Payload: data.Payload,
	}
}

func (c *QdrantClient) upsertPoints(points []QdrantPoint) error {
	upsertReq := QdrantUpsertRequest{
		Points: points,
	}

	jsonData, err := json.Marshal(upsertReq)
	if err != nil {
		return fmt.Errorf("error marshaling upsert request: %w", err)
	}

	url := fmt.Sprintf("%s/collections/%s/points", c.baseURL, c.collection)
	req, err := http.NewRequest("PUT", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return fmt.Errorf("error creating request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	if c.apiKey != "" {
		req.Header.Set("api-key", c.apiKey)
	}

	resp, err := c.client.Do(req)
	if err != nil {
		return fmt.Errorf("error sending request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("failed to store points in collection %s (status %d): %s", c.collection, resp.StatusCode, string(body))
	}

	fmt.Printf("Successfully stored %d points in collection '%s'\n", len(points), c.collection)
	return nil
}

func (c *QdrantClient) CreatePayloadIndexes(fields []string) error {
	fmt.Printf("Creating payload indexes for collection '%s'\n", c.collection)

	for _, field := range fields {
		url := fmt.Sprintf("%s/collections/%s/index", c.baseURL, c.collection)

		payload := map[string]interface{}{
			"field_name": field,
			"field_schema": map[string]interface{}{
				"type": "keyword",
			},
		}

		jsonData, err := json.Marshal(payload)
		if err != nil {
			return fmt.Errorf("failed to marshal payload index request for field %s: %w", field, err)
		}

		req, err := http.NewRequest("PUT", url, bytes.NewBuffer(jsonData))
		if err != nil {
			return fmt.Errorf("failed to create payload index request for field %s: %w", field, err)
		}

		req.Header.Set("Content-Type", "application/json")
		if c.apiKey != "" {
			req.Header.Set("api-key", c.apiKey)
		}

		resp, err := c.client.Do(req)
		if err != nil {
			return fmt.Errorf("failed to send payload index request for field %s: %w", field, err)
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			body, _ := io.ReadAll(resp.Body)
			return fmt.Errorf("failed to create index for field %s (status %d): %s", field, resp.StatusCode, string(body))
		}
	}

	fmt.Printf("All payload indexes created successfully for collection '%s'\n", c.collection)
	return nil
}