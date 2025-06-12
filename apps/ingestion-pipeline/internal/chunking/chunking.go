package chunking

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/NEMYSESx/Orbit/apps/ingestion-pipeline/internal/models"
	"github.com/confluentinc/confluent-kafka-go/kafka"
)

type AgenticChunker struct {
	apiKey             string
	baseURL            string
	client             *http.Client
	maxRetries         int
	sectionSize        int
	maxCharsPerSection int
	kafkaProducer      *kafka.Producer
	kafkaTopic         string
}

type sectionJob struct {
	index      int
	text       string
	sourceInfo models.SourceInfo
}

type sectionResult struct {
	chunks []models.Chunk
	err    error
	index  int
}

func NewAgenticChunker(config models.ChunkingConfig) *AgenticChunker {
	return &AgenticChunker{
		apiKey:  config.GeminiAPIKey,
		baseURL: "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent",
		client: &http.Client{
			Timeout: 60 * time.Second,
		},
		maxRetries:         3,
		maxCharsPerSection: 12000,
	}
}

func (ac *AgenticChunker) InitializeKafkaStreaming(bootstrapServers, topic string) error {
	producer, err := kafka.NewProducer(&kafka.ConfigMap{
		"bootstrap.servers": bootstrapServers,
		"acks":              "all",
		"retries":           "3",
		"batch.size":        "16384",
		"linger.ms":         "1",
		"compression.type":  "snappy",
	})
	if err != nil {
		return fmt.Errorf("failed to create Kafka producer: %w", err)
	}

	ac.kafkaProducer = producer
	ac.kafkaTopic = topic
	return nil
}

func (ac *AgenticChunker) Close() {
	if ac.kafkaProducer != nil {
		ac.kafkaProducer.Flush(30 * 1000)
		ac.kafkaProducer.Close()
	}
}

func (ac *AgenticChunker) ChunkTextStreaming(ctx context.Context, text string, sourceInfo models.SourceInfo) error {
	if strings.TrimSpace(text) == "" {
		return fmt.Errorf("input text cannot be empty")
	}

	if ac.kafkaProducer == nil {
		return fmt.Errorf("kafka producer not initialized - call InitializeKafkaStreaming first")
	}

	ac.sectionSize = ac.calculateOptimalSectionSize(len(text))
	sections := ac.divideIntoSections(text)

	fmt.Printf("Processing %d sections with streaming to Kafka\n", len(sections))

	maxWorkers := min(12, len(sections))
	jobs := make(chan sectionJob, len(sections))
	results := make(chan sectionResult, len(sections))

	var processingErrors []error
	var errorsMutex sync.Mutex

	var wg sync.WaitGroup
	for i := 0; i < maxWorkers; i++ {
		wg.Add(1)
		go ac.worker(ctx, jobs, results, sourceInfo, &wg)
	}

	go func() {
		defer close(jobs)
		for i, section := range sections {
			jobs <- sectionJob{
				index:      i,
				text:       section,
				sourceInfo: sourceInfo,
			}
		}
	}()

	go func() {
		defer close(results)
		wg.Wait()
	}()

	processedSections := 0
	for result := range results {
		processedSections++
		if result.err != nil {
			errorsMutex.Lock()
			processingErrors = append(processingErrors, fmt.Errorf("section %d: %w", result.index, result.err))
			errorsMutex.Unlock()
		}
	}

	if len(processingErrors) > 0 {
		return fmt.Errorf("failed to process %d/%d sections: %v", len(processingErrors), processedSections, processingErrors[0])
	}

	fmt.Printf("Successfully processed and streamed %d sections\n", processedSections)
	return nil
}


func (ac *AgenticChunker) streamChunkToKafka(chunk models.ChunkOutput) error {
	chunkJSON, err := json.Marshal(chunk)
	if err != nil {
		return fmt.Errorf("failed to marshal chunk: %w", err)
	}

	deliveryChan := make(chan kafka.Event, 1)

	err = ac.kafkaProducer.Produce(&kafka.Message{
		TopicPartition: kafka.TopicPartition{
			Topic:     &ac.kafkaTopic,
			Partition: kafka.PartitionAny,
		},
		Value: chunkJSON,
		Headers: []kafka.Header{
			{Key: "chunk_id", Value: []byte(chunk.ChunkMetadata.Topic)},
			{Key: "document_type", Value: []byte(chunk.Source.DocumentType)},
			{Key: "timestamp", Value: []byte(chunk.ChunkMetadata.Timestamp)},
		},
	}, deliveryChan)

	if err != nil {
		return fmt.Errorf("failed to produce message: %w", err)
	}

	select {
	case e := <-deliveryChan:
		if msg, ok := e.(*kafka.Message); ok {
			if msg.TopicPartition.Error != nil {
				return fmt.Errorf("delivery failed: %w", msg.TopicPartition.Error)
			}
		}
	case <-time.After(5 * time.Second):
		return fmt.Errorf("delivery confirmation timeout")
	}

	return nil
}

func (ac *AgenticChunker) calculateOptimalSectionSize(textLength int) int {
	if textLength > 100000 {
		return 1800
	} else if textLength > 50000 {
		return 3000
	}

	targetConcurrency := 10
	estimatedWords := textLength / 5
	optimalSectionSize := estimatedWords / targetConcurrency

	minSectionSize := 1200
	maxSectionSize := 3600

	if optimalSectionSize < minSectionSize {
		return minSectionSize
	} else if optimalSectionSize > maxSectionSize {
		return maxSectionSize
	}

	return optimalSectionSize
}

func (ac *AgenticChunker) divideIntoSections(text string) []string {
	words := strings.Fields(text)
	var sections []string

	currentSection := strings.Builder{}
	wordCount := 0

	for _, word := range words {
		willExceedWordLimit := wordCount >= ac.sectionSize
		willExceedCharLimit := currentSection.Len() > 0 && currentSection.Len()+len(word)+1 > ac.maxCharsPerSection

		if willExceedWordLimit || willExceedCharLimit {
			if currentSection.Len() > 0 {
				sections = append(sections, strings.TrimSpace(currentSection.String()))
				currentSection.Reset()
				wordCount = 0
			}
		}

		if currentSection.Len() > 0 {
			currentSection.WriteString(" ")
		}
		currentSection.WriteString(word)
		wordCount++
	}

	if currentSection.Len() > 0 {
		sections = append(sections, strings.TrimSpace(currentSection.String()))
	}

	return sections
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
- Each chunk should be 50-300 words ideally (smaller chunks for better processing)
- Maintain semantic coherence within each chunk
- Avoid breaking sentences in the middle
- Ensure chunks have clear topical boundaries
- Include transitional context when necessary
- For shorter input text, create 2-4 chunks maximum

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

Text to analyze (length: %d characters):
%s`, len(text), text)
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
			lastErr = fmt.Errorf("api request failed with status %d: %s", resp.StatusCode, string(body))
			continue
		}

		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			lastErr = fmt.Errorf("failed to read response body: %w", err)
			continue
		}

		var geminiResp models.GeminiResponse
		if err := json.Unmarshal(body, &geminiResp); err != nil {
			lastErr = fmt.Errorf("failed to unmarshal response: %w", err)
			continue
		}

		if len(geminiResp.Candidates) == 0 || len(geminiResp.Candidates[0].Content.Parts) == 0 {
			lastErr = fmt.Errorf("no content in gemini response")
			continue
		}

		return geminiResp.Candidates[0].Content.Parts[0].Text, nil
	}

	return "", fmt.Errorf("failed after %d retries: %w", ac.maxRetries, lastErr)
}

func (ac *AgenticChunker) parseGeminiResponse(response string, sectionIndex int) ([]models.Chunk, error) {
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
		return nil, fmt.Errorf("failed to parse gemini json response: %w", err)
	}

	chunks := make([]models.Chunk, 0, len(geminiResp.Chunks))
	timestamp := time.Now().UTC().Format(time.RFC3339)

	for i, geminiChunk := range geminiResp.Chunks {
		chunk := models.Chunk{
			ID:      fmt.Sprintf("chunk_%d_%d_%d", time.Now().Unix(), sectionIndex, i),
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

func (ac *AgenticChunker) processSubSection(ctx context.Context, sectionText string, sectionIndex, subIndex int) ([]models.Chunk, error) {
	prompt := ac.buildChunkingPrompt(sectionText)

	geminiResponse, err := ac.callGeminiAPI(ctx, prompt)
	if err != nil {
		return nil, fmt.Errorf("failed to call Gemini API for section %d-%d: %w", sectionIndex, subIndex, err)
	}

	chunks, err := ac.parseGeminiResponse(geminiResponse, sectionIndex*1000+subIndex)
	if err != nil {
		return nil, fmt.Errorf("failed to parse Gemini response for section %d-%d: %w", sectionIndex, subIndex, err)
	}

	return chunks, nil
}

func (ac *AgenticChunker) splitLargeSection(text string) []string {
	words := strings.Fields(text)
	var sections []string
	maxWordsPerSubSection := ac.maxCharsPerSection / 6

	for i := 0; i < len(words); i += maxWordsPerSubSection {
		end := i + maxWordsPerSubSection
		if end > len(words) {
			end = len(words)
		}

		section := strings.Join(words[i:end], " ")
		sections = append(sections, section)
	}

	return sections
}

func (ac *AgenticChunker) processSectionConcurrently(ctx context.Context, sectionText string, sectionIndex int) ([]models.Chunk, error) {
	if len(sectionText) > ac.maxCharsPerSection {
		subSections := ac.splitLargeSection(sectionText)
		var allChunks []models.Chunk

		for i, subSection := range subSections {
			chunks, err := ac.processSubSection(ctx, subSection, sectionIndex, i)
			if err != nil {
				return nil, fmt.Errorf("failed to process subsection %d: %w", i, err)
			}
			allChunks = append(allChunks, chunks...)
		}
		return allChunks, nil
	}

	return ac.processSubSection(ctx, sectionText, sectionIndex, 0)
}

func (ac *AgenticChunker) worker(ctx context.Context, jobs <-chan sectionJob, results chan<- sectionResult, sourceInfo models.SourceInfo, wg *sync.WaitGroup) {
	defer wg.Done()

	for job := range jobs {
		chunks, err := ac.processSectionConcurrently(ctx, job.text, job.index)

		if err != nil {
			results <- sectionResult{chunks: nil, err: err, index: job.index}
			continue
		}

		for _, chunk := range chunks {
			chunkOutput := models.ChunkOutput{
				Text:          chunk.Content,
				Source:        sourceInfo,
				ChunkMetadata: chunk.Metadata,
			}

			if streamErr := ac.streamChunkToKafka(chunkOutput); streamErr != nil {
				fmt.Printf("Failed to stream chunk to Kafka: %v\n", streamErr)
				results <- sectionResult{chunks: nil, err: streamErr, index: job.index}
				continue
			} else {
				fmt.Printf("Streamed chunk %s to Kafka\n", chunkOutput.ChunkMetadata.Topic)
			}
		}

		results <- sectionResult{chunks: chunks, err: nil, index: job.index}
	}
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}