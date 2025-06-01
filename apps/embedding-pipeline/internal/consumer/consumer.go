package consumer

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strings"
	"time"

	"github.com/NEMYSESx/Orbit/apps/embedding-pipeline/internal/config"
	"github.com/confluentinc/confluent-kafka-go/kafka"
)

type ChunkOutput struct {
	Text          string        `json:"text"`
	Source        SourceInfo    `json:"source"`
	ChunkMetadata ChunkMetadata `json:"chunk_metadata"`
}

type SourceInfo struct {
	DocumentTitle string `json:"document_title"`
	DocumentType  string `json:"document_type"`
	Section       string `json:"section,omitempty"`
	PageNumber    *int   `json:"page_number,omitempty"`
	LastModified  string `json:"last_modified,omitempty"`
}

type ChunkMetadata struct {
	Topic      string   `json:"topic"`
	Keywords   []string `json:"keywords"`
	Entities   []string `json:"entities"`
	Summary    string   `json:"summary"`
	Category   string   `json:"category"`
	Sentiment  string   `json:"sentiment"`
	Complexity string   `json:"complexity"`
	Language   string   `json:"language"`
	WordCount  int      `json:"word_count"`
	ChunkIndex int      `json:"chunk_index"`
	Timestamp  string   `json:"timestamp"`
}

type EnrichedChunk struct {
	ChunkOutput
	Embedding []float32 `json:"embedding"`
}

type KafkaConsumer struct {
	consumer *kafka.Consumer
	topic    string
}

func NewKafkaConsumer(topic string) (*KafkaConsumer, error) {
	c, err := kafka.NewConsumer(&kafka.ConfigMap{
		"bootstrap.servers": getEnvOrDefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
		"group.id":          getEnvOrDefault("KAFKA_GROUP_ID", "embedding-pipeline-group"),
		"auto.offset.reset": "earliest",
	})

	if err != nil {
		return nil, fmt.Errorf("failed to create consumer: %w", err)
	}

	err = c.SubscribeTopics([]string{topic}, nil)
	if err != nil {
		c.Close()
		return nil, fmt.Errorf("failed to subscribe to topic %s: %w", topic, err)
	}

	log.Printf("Kafka consumer started for topic: %s", topic)

	return &KafkaConsumer{
		consumer: c,
		topic:    topic,
	}, nil
}

func NewKafkaConsumerWithConfig(cfg config.KafkaConfig) (*KafkaConsumer, error) {
	c, err := kafka.NewConsumer(&kafka.ConfigMap{
		"bootstrap.servers": cfg.BootstrapServers,
		"group.id":          cfg.GroupID,
		"auto.offset.reset": cfg.AutoOffsetReset,
	})

	if err != nil {
		return nil, fmt.Errorf("failed to create consumer: %w", err)
	}

	err = c.SubscribeTopics([]string{cfg.Topic}, nil)
	if err != nil {
		c.Close()
		return nil, fmt.Errorf("failed to subscribe to topic %s: %w", cfg.Topic, err)
	}

	log.Printf("Kafka consumer started for topic: %s", cfg.Topic)

	return &KafkaConsumer{
		consumer: c,
		topic:    cfg.Topic,
	}, nil
}

// ConsumeChunks extracts chunks from JSON array format
func (kc *KafkaConsumer) ConsumeChunks() ([]ChunkOutput, error) {
	msg, err := kc.consumer.ReadMessage(-1)
	if err != nil {
		return nil, fmt.Errorf("error reading message: %w", err)
	}

	rawMessage := string(msg.Value)
	
	// Check if message is empty
	if len(msg.Value) == 0 {
		return nil, fmt.Errorf("received empty message")
	}

	// Debug: Log the raw message (first 200 chars for safety)
	if len(rawMessage) > 200 {
		log.Printf("Raw message preview: %s...", rawMessage[:200])
	} else {
		log.Printf("Raw message: %s", rawMessage)
	}

	// Clean the message
	cleanedMessage := strings.TrimSpace(rawMessage)
	cleanedMessage = strings.TrimPrefix(cleanedMessage, "\ufeff") // Remove BOM if present

	// Extract chunks using the new function
	chunks, err := extractChunksFromMessage(cleanedMessage)
	if err != nil {
		return nil, fmt.Errorf("error extracting chunks: %w", err)
	}

	log.Printf("Successfully extracted %d chunks", len(chunks))
	return chunks, nil
}

// extractChunksFromMessage handles different JSON formats and extracts chunks
func extractChunksFromMessage(message string) ([]ChunkOutput, error) {
	// Clean up any potential formatting issues
	message = strings.TrimSpace(message)
	
	// Debug: Check if the message looks like valid JSON
	if !strings.HasPrefix(message, "[") && !strings.HasPrefix(message, "{") {
		return nil, fmt.Errorf("message doesn't start with [ or {: %s", message[:min(50, len(message))])
	}

	// Check if it's valid JSON first
	if !json.Valid([]byte(message)) {
		log.Printf("Invalid JSON detected, attempting to fix quasi-JSON format...")
		// Try to fix the quasi-JSON format (missing quotes)
		fixedMessage, err := fixQuasiJSON(message)
		if err != nil {
			return nil, fmt.Errorf("failed to fix quasi-JSON: %w", err)
		}
		message = fixedMessage
		log.Printf("Fixed quasi-JSON, new length: %d", len(message))
	}

	var chunks []ChunkOutput

	// Case 1: Direct array of chunks (like your example)
	// [{"text": "...", "source": {...}, "chunk_metadata": {...}}, ...]
	if strings.HasPrefix(message, "[") {
		var chunkArray []ChunkOutput
		if err := json.Unmarshal([]byte(message), &chunkArray); err != nil {
			return nil, fmt.Errorf("failed to parse chunk array: %w", err)
		}
		chunks = chunkArray
		log.Printf("Parsed as direct chunk array: %d chunks", len(chunks))
	} else if strings.HasPrefix(message, "{") {
		// Case 2: Object containing chunks array
		// {"chunks": [{"text": "...", "source": {...}, "chunk_metadata": {...}}]}
		var wrapper map[string]interface{}
		if err := json.Unmarshal([]byte(message), &wrapper); err != nil {
			return nil, fmt.Errorf("failed to parse JSON object: %w", err)
		}

		// Check if it has a chunks field
		if chunksField, exists := wrapper["chunks"]; exists {
			chunksBytes, err := json.Marshal(chunksField)
			if err != nil {
				return nil, fmt.Errorf("failed to marshal chunks field: %w", err)
			}
			
			var chunkArray []ChunkOutput
			if err := json.Unmarshal(chunksBytes, &chunkArray); err != nil {
				return nil, fmt.Errorf("failed to parse chunks array: %w", err)
			}
			chunks = chunkArray
			log.Printf("Parsed as wrapped chunk array: %d chunks", len(chunks))
		} else {
			// Case 3: Single chunk object
			// {"text": "...", "source": {...}, "chunk_metadata": {...}}
			var singleChunk ChunkOutput
			if err := json.Unmarshal([]byte(message), &singleChunk); err != nil {
				return nil, fmt.Errorf("failed to parse single chunk: %w", err)
			}
			chunks = []ChunkOutput{singleChunk}
			log.Printf("Parsed as single chunk")
		}
	} else {
		return nil, fmt.Errorf("unrecognized JSON format")
	}

	if len(chunks) == 0 {
		return nil, fmt.Errorf("no chunks found in message")
	}

	// Validate and fix chunks if needed
	chunks = validateAndFixChunks(chunks)
	
	return chunks, nil
}

// validateAndFixChunks ensures chunks have proper metadata
func validateAndFixChunks(chunks []ChunkOutput) []ChunkOutput {
	for i := range chunks {
		chunk := &chunks[i]
		
		// Validate required fields
		if chunk.Text == "" {
			log.Printf("Warning: chunk %d has empty text", i)
			continue
		}
		
		// Fix empty document title if needed
		if chunk.Source.DocumentTitle == "" {
			if len(chunk.Text) > 50 {
				chunk.Source.DocumentTitle = chunk.Text[:50] + "..."
			} else {
				chunk.Source.DocumentTitle = "Untitled Document"
			}
		}
		
		// Ensure document type is set
		if chunk.Source.DocumentType == "" {
			chunk.Source.DocumentType = "text"
		}
		
		// Fix word count if it's incorrect
		actualWordCount := len(strings.Fields(chunk.Text))
		if chunk.ChunkMetadata.WordCount != actualWordCount {
			log.Printf("Fixing word count for chunk %d: was %d, should be %d", 
				chunk.ChunkMetadata.ChunkIndex, chunk.ChunkMetadata.WordCount, actualWordCount)
			chunk.ChunkMetadata.WordCount = actualWordCount
		}
		
		// Set timestamp if missing
		if chunk.ChunkMetadata.Timestamp == "" {
			chunk.ChunkMetadata.Timestamp = time.Now().Format(time.RFC3339)
		}
		
		// Initialize empty slices to avoid null values
		if chunk.ChunkMetadata.Keywords == nil {
			chunk.ChunkMetadata.Keywords = []string{}
		}
		if chunk.ChunkMetadata.Entities == nil {
			chunk.ChunkMetadata.Entities = []string{}
		}
		
		// Set default values for missing metadata
		if chunk.ChunkMetadata.Category == "" {
			chunk.ChunkMetadata.Category = "general"
		}
		if chunk.ChunkMetadata.Sentiment == "" {
			chunk.ChunkMetadata.Sentiment = "neutral"
		}
		if chunk.ChunkMetadata.Complexity == "" {
			chunk.ChunkMetadata.Complexity = "moderate"
		}
		if chunk.ChunkMetadata.Language == "" {
			chunk.ChunkMetadata.Language = "english"
		}
		
		log.Printf("Validated chunk %d: '%s' (%d words)", 
			chunk.ChunkMetadata.ChunkIndex, 
			chunk.Source.DocumentTitle, 
			chunk.ChunkMetadata.WordCount)
	}
	
	return chunks
}

// Backward compatibility - returns single chunk (first one if multiple)
func (kc *KafkaConsumer) ConsumeChunk() (*ChunkOutput, error) {
	chunks, err := kc.ConsumeChunks()
	if err != nil {
		return nil, err
	}
	
	if len(chunks) == 0 {
		return nil, fmt.Errorf("no chunks received")
	}
	
	// If multiple chunks, log a warning
	if len(chunks) > 1 {
		log.Printf("Warning: ConsumeChunk() called but received %d chunks, returning only the first one", len(chunks))
	}
	
	return &chunks[0], nil
}

func (kc *KafkaConsumer) Close() error {
	if kc.consumer != nil {
		return kc.consumer.Close()
	}
	return nil
}

func getEnvOrDefault(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

// Helper function for Go versions that don't have built-in min
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

// fixQuasiJSON attempts to convert quasi-JSON (missing quotes) to valid JSON
func fixQuasiJSON(input string) (string, error) {
	log.Printf("Attempting to fix quasi-JSON format...")
	
	// This is a more robust approach using regex and string replacement
	// to add quotes around unquoted keys and string values
	
	result := input
	
	// Common patterns to fix:
	// 1. Unquoted keys: {text: -> {"text":
	// 2. Unquoted string values: "key": value -> "key": "value"
	
	// List of known string fields that need quotes
	stringFields := []string{
		"text", "document_title", "document_type", "section", "last_modified",
		"topic", "summary", "category", "sentiment", "complexity", "language", "timestamp",
	}
	
	// List of known array fields
	arrayFields := []string{"keywords", "entities"}
	
	// Fix unquoted keys first
	for _, field := range stringFields {
		// Pattern: field: -> "field":
		oldPattern := field + ":"
		newPattern := "\"" + field + "\":"
		result = strings.ReplaceAll(result, oldPattern, newPattern)
	}
	
	for _, field := range arrayFields {
		// Pattern: field: -> "field":
		oldPattern := field + ":"
		newPattern := "\"" + field + "\":"
		result = strings.ReplaceAll(result, oldPattern, newPattern)
	}
	
	// Fix numeric fields too
	numericFields := []string{"page_number", "word_count", "chunk_index"}
	for _, field := range numericFields {
		oldPattern := field + ":"
		newPattern := "\"" + field + "\":"
		result = strings.ReplaceAll(result, oldPattern, newPattern)
	}
	
	// Now we need to add quotes around string values
	// This is trickier - we'll use a more targeted approach
	
	// Simple approach: look for patterns like ": value," or ": value}" where value should be quoted
	// We'll do this for known string fields
	
	for _, field := range stringFields {
		quotedField := "\"" + field + "\":"
		// Find all occurrences of this field
		if strings.Contains(result, quotedField) {
			result = fixStringValues(result, quotedField)
		}
	}
	
	// Validate the result
	if json.Valid([]byte(result)) {
		log.Printf("Successfully fixed quasi-JSON")
		return result, nil
	}
	
	log.Printf("Failed to fix quasi-JSON, result still invalid")
	return "", fmt.Errorf("could not convert quasi-JSON to valid JSON")
}

// fixStringValues adds quotes around string values for a specific field
func fixStringValues(input, field string) string {
	result := input
	
	// Look for pattern: "field": unquoted_value
	// We'll search for the field and then find the value after it
	
	fieldIndex := 0
	for {
		fieldIndex = strings.Index(result[fieldIndex:], field)
		if fieldIndex == -1 {
			break
		}
		fieldIndex += len(field)
		
		// Skip whitespace
		for fieldIndex < len(result) && (result[fieldIndex] == ' ' || result[fieldIndex] == '\t') {
			fieldIndex++
		}
		
		if fieldIndex >= len(result) {
			break
		}
		
		// Check if the value is already quoted
		if result[fieldIndex] == '"' {
			// Already quoted, find the end of this field
			fieldIndex = findEndOfQuotedString(result, fieldIndex)
			continue
		}
		
		// Find the end of the unquoted value
		valueStart := fieldIndex
		valueEnd := findEndOfUnquotedValue(result, valueStart)
		
		if valueEnd > valueStart {
			// Extract the value
			value := strings.TrimSpace(result[valueStart:valueEnd])
			
			// Quote the value
			quotedValue := "\"" + value + "\""
			
			// Replace in result
			result = result[:valueStart] + quotedValue + result[valueEnd:]
			
			// Adjust index
			fieldIndex = valueStart + len(quotedValue)
		}
	}
	
	return result
}

// findEndOfQuotedString finds the end of a quoted string starting at index
func findEndOfQuotedString(input string, startIndex int) int {
	if startIndex >= len(input) || input[startIndex] != '"' {
		return startIndex
	}
	
	for i := startIndex + 1; i < len(input); i++ {
		if input[i] == '"' && (i == 0 || input[i-1] != '\\') {
			return i + 1
		}
	}
	return len(input)
}

// findEndOfUnquotedValue finds the end of an unquoted value
func findEndOfUnquotedValue(input string, startIndex int) int {
	for i := startIndex; i < len(input); i++ {
		char := input[i]
		if char == ',' || char == '}' || char == ']' || char == '\n' || char == '\r' {
			return i
		}
	}
	return len(input)
}