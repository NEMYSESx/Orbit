package chunking

import (
	"context"
	"crypto/md5"
	"fmt"
	"log"
	"regexp"
	"strings"
	"sync"
	"time"
	"unicode/utf8"

	"github.com/NEMYSESx/orbit/apps/ingestion-pipeline/internal/models"
	"golang.org/x/time/rate"
)

type AgenticChunker struct {
	config      *Config
	geminiClient *GeminiClient
	rateLimiter *rate.Limiter
	semaphore   chan struct{}
}

func NewAgenticChunker(config *Config) *AgenticChunker {
	return &AgenticChunker{
		config:       config,
		geminiClient: NewGeminiClient(config.GeminiAPIKey, config.GeminiModel, config.RequestTimeout),
		rateLimiter:  rate.NewLimiter(rate.Limit(config.RateLimitRPS), config.RateLimitRPS),
		semaphore:    make(chan struct{}, config.MaxConcurrentRequests),
	}
}

func (ac *AgenticChunker) ProcessDocument(ctx context.Context, document *models.ExtractedContent) (*ChunkedDocument, error) {
	startTime := time.Now()
	
	log.Printf("Starting agentic chunking for document: %s", document.Metadata.ID)

	chunks, err := ac.performSemanticChunking(document.CleanText)
	if err != nil {
		return nil, fmt.Errorf("semantic chunking failed: %w", err)
	}

	analyzedChunks, err := ac.analyzeChunksWithAI(ctx, chunks, document)
	if err != nil {
		return nil, fmt.Errorf("AI analysis failed: %w", err)
	}

	qdrantPoints, err := ac.generateQdrantPoints(analyzedChunks, document)
	if err != nil {
		return nil, fmt.Errorf("point generation failed: %w", err)
	}

	processingDuration := time.Since(startTime)
	summary := ac.calculateProcessingSummary(qdrantPoints, processingDuration)

	result := &ChunkedDocument{
		OriginalDocument:  *document,
		Chunks:           qdrantPoints,
		ProcessingSummary: summary,
	}

	log.Printf("Successfully processed document %s: %d chunks in %v", 
		document.Metadata.ID, len(qdrantPoints), processingDuration)

	return result, nil
}

func (ac *AgenticChunker) performSemanticChunking(text string) ([]string, error) {
	paragraphs := ac.splitByParagraphs(text)
	
	var chunks []string
	var currentChunk strings.Builder
	currentTokens := 0

	for _, paragraph := range paragraphs {
		sentences := ac.splitBySentences(paragraph)
		
		for _, sentence := range sentences {
			sentenceTokens := ac.estimateTokenCount(sentence)
			
			if currentTokens+sentenceTokens > ac.config.MaxChunkSize && currentChunk.Len() > 0 {
				if currentTokens >= ac.config.MinChunkSize {
					chunks = append(chunks, strings.TrimSpace(currentChunk.String()))
				}
				
				currentChunk.Reset()
				currentTokens = 0
			}
			
			if currentChunk.Len() > 0 {
				currentChunk.WriteString(" ")
			}
			currentChunk.WriteString(sentence)
			currentTokens += sentenceTokens
		}
	}

	if currentChunk.Len() > 0 && currentTokens >= ac.config.MinChunkSize {
		chunks = append(chunks, strings.TrimSpace(currentChunk.String()))
	}

	return ac.applyOverlap(chunks), nil
}

func (ac *AgenticChunker) splitByParagraphs(text string) []string {
	paragraphs := regexp.MustCompile(`\n\s*\n`).Split(text, -1)
	var result []string
	for _, p := range paragraphs {
		if trimmed := strings.TrimSpace(p); trimmed != "" {
			result = append(result, trimmed)
		}
	}
	return result
}

func (ac *AgenticChunker) splitBySentences(text string) []string {
	sentences := regexp.MustCompile(`(?<=[.!?])\s+`).Split(text, -1)
	var result []string
	for _, s := range sentences {
		if trimmed := strings.TrimSpace(s); trimmed != "" {
			result = append(result, trimmed)
		}
	}
	return result
}

func (ac *AgenticChunker) estimateTokenCount(text string) int {
	return utf8.RuneCountInString(text) / 4
}

func (ac *AgenticChunker) applyOverlap(chunks []string) []string {
	if len(chunks) <= 1 {
		return chunks
	}

	var overlappedChunks []string
	overlappedChunks = append(overlappedChunks, chunks[0])

	for i := 1; i < len(chunks); i++ {
		prevChunk := chunks[i-1]
		currentChunk := chunks[i]

		prevSentences := ac.splitBySentences(prevChunk)
		overlapSentences := prevSentences
		if len(prevSentences) > 2 {
			overlapSentences = prevSentences[len(prevSentences)-2:]
		}

		overlapText := strings.Join(overlapSentences, " ")
		overlappedChunk := fmt.Sprintf("%s %s", overlapText, currentChunk)

		if ac.estimateTokenCount(overlappedChunk) <= ac.config.MaxChunkSize {
			overlappedChunks = append(overlappedChunks, overlappedChunk)
		} else {
			overlappedChunks = append(overlappedChunks, currentChunk)
		}
	}

	return overlappedChunks
}

func (ac *AgenticChunker) analyzeChunksWithAI(ctx context.Context, chunks []string, document *models.ExtractedContent) ([]ChunkPayload, error) {
	var wg sync.WaitGroup
	var mu sync.Mutex
	var analyzedChunks []ChunkPayload
	var errors []error

	systemPrompt := `You are an expert document analysis agent. Analyze the given text chunk and provide structured metadata.

Your task is to:
1. Classify the chunk's role/purpose
2. Extract key entities and concepts
3. Identify main topics/themes
4. Assess level of detail
5. Provide context summary
6. Rate your confidence

Respond with valid JSON only, no additional text.`

	for i, chunk := range chunks {
		wg.Add(1)
		go func(index int, chunkText string) {
			defer wg.Done()

			ac.semaphore <- struct{}{}
			defer func() { <-ac.semaphore }()

			if err := ac.rateLimiter.Wait(ctx); err != nil {
				mu.Lock()
				errors = append(errors, fmt.Errorf("rate limit error for chunk %d: %w", index, err))
				mu.Unlock()
				return
			}

			userPrompt := fmt.Sprintf(`
Document Title: %s
Document Type: %s
Chunk %d of %d

Chunk Text:
"%s"

Analyze this chunk and respond with JSON in this exact format:
{
    "chunk_role": "one of: definition, procedure, example, summary, background, step, figure_caption, table_data, code_snippet, heading, paragraph",
    "key_entities": ["entity1", "entity2", "entity3"],
    "topics": ["topic1", "topic2"],
    "original_context_summary": "brief summary of the broader context",
    "level_of_detail": "one of: high-level, detailed, step-by-step, overview, specific",
    "agent_confidence": 0.0-1.0
}`, document.Metadata.Title, document.Metadata.SourceType, index+1, len(chunks), chunkText)

			var analysis *ChunkAnalysis
			var err error

			for attempt := 0; attempt < ac.config.MaxRetries; attempt++ {
				analysis, err = ac.geminiClient.AnalyzeChunk(ctx, systemPrompt, userPrompt)
				if err == nil {
					break
				}
				time.Sleep(time.Duration(attempt+1) * time.Second)
			}

			if err != nil {
				log.Printf("Failed to analyze chunk %d after %d attempts: %v", index, ac.config.MaxRetries, err)
				analysis = ac.createDefaultAnalysis(chunkText)
			}

			analysis = ac.validateAnalysis(analysis, chunkText)

			chunkPayload := ChunkPayload{
				Text:             chunkText,
				SourceID:         document.Metadata.SourceID,
				SourceType:       document.Metadata.SourceType,
				Title:            document.Metadata.Title,
				Filepath:         document.Metadata.Filepath,
				LastModifiedDate: document.Metadata.LastModifiedDate,
				SourceLocation: SourceLocation{
					ChunkIndex: &index,
				},
				Analysis: *analysis,
				ProcessingMetadata: ProcessingMetadata{
					ChunkID:           ac.generateChunkID(document.Metadata.ID, index),
					ProcessedAt:       time.Now(),
					ProcessingVersion: "1.0",
					TokenCount:        ac.estimateTokenCount(chunkText),
				},
			}

			mu.Lock()
			analyzedChunks = append(analyzedChunks, chunkPayload)
			mu.Unlock()
		}(i, chunk)
	}

	wg.Wait()

	if len(errors) > 0 {
		log.Printf("Encountered %d errors during chunk analysis", len(errors))
	}

	return analyzedChunks, nil
}

func (ac *AgenticChunker) validateAnalysis(analysis *ChunkAnalysis, chunkText string) *ChunkAnalysis {
	validRoles := map[string]bool{
		"definition": true, "procedure": true, "example": true, "summary": true,
		"background": true, "step": true, "figure_caption": true, "table_data": true,
		"code_snippet": true, "heading": true, "paragraph": true,
	}

	validLevels := map[string]bool{
		"high-level": true, "detailed": true, "step-by-step": true,
		"overview": true, "specific": true,
	}

	if !validRoles[analysis.ChunkRole] {
		analysis.ChunkRole = "paragraph"
	}

	if !validLevels[analysis.LevelOfDetail] {
		analysis.LevelOfDetail = "detailed"
	}

	if len(analysis.KeyEntities) > 10 {
		analysis.KeyEntities = analysis.KeyEntities[:10]
	}

	if len(analysis.Topics) > 5 {
		analysis.Topics = analysis.Topics[:5]
	}

	if analysis.AgentConfidence < 0 || analysis.AgentConfidence > 1 {
		analysis.AgentConfidence = 0.5
	}

	if analysis.OriginalContextSummary == "" {
		if len(chunkText) > 200 {
			analysis.OriginalContextSummary = chunkText[:200] + "..."
		} else {
			analysis.OriginalContextSummary = chunkText
		}
	}

	return analysis
}

func (ac *AgenticChunker) createDefaultAnalysis(chunkText string) *ChunkAnalysis {
	return &ChunkAnalysis{
		ChunkRole:              "paragraph",
		KeyEntities:           ac.extractSimpleEntities(chunkText),
		Topics:                []string{"general"},
		OriginalContextSummary: chunkText[:min(200, len(chunkText))],
		LevelOfDetail:         "detailed",
		AgentConfidence:       0.3,
		ProcessingTimestamp:   time.Now(),
	}
}

func (ac *AgenticChunker) extractSimpleEntities(text string) []string {
	re := regexp.MustCompile(`\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b`)
	matches := re.FindAllString(text, 5)
	return matches
}

func (ac *AgenticChunker) generateQdrantPoints(chunks []ChunkPayload, document *models.ExtractedContent) ([]QdrantPoint, error) {
	var points []QdrantPoint

	for i, chunk := range chunks {
		vector := make([]float64, 384)
		for j := range vector {
			vector[j] = float64(i) / float64(len(chunks)) 
		}

		point := QdrantPoint{
			ID:      chunk.ProcessingMetadata.ChunkID,
			Vector:  vector,
			Payload: chunk,
		}

		points = append(points, point)
	}

	return points, nil
}

func (ac *AgenticChunker) generateChunkID(documentID string, chunkIndex int) string {
	return fmt.Sprintf("%x", md5.Sum([]byte(fmt.Sprintf("%s_%d", documentID, chunkIndex))))
}

func (ac *AgenticChunker) calculateProcessingSummary(points []QdrantPoint, duration time.Duration) ProcessingSummary {
	totalConfidence := 0.0
	failedChunks := 0

	for _, point := range points {
		totalConfidence += point.Payload.Analysis.AgentConfidence
		if point.Payload.Analysis.AgentConfidence < ac.config.ConfidenceThreshold {
			failedChunks++
		}
	}

	averageConfidence := 0.0
	if len(points) > 0 {
		averageConfidence = totalConfidence / float64(len(points))
	}

	return ProcessingSummary{
		TotalChunks:        len(points),
		ProcessingDuration: duration,
		AverageConfidence:  averageConfidence,
		FailedChunks:       failedChunks,
		ProcessedAt:        time.Now(),
	}
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
