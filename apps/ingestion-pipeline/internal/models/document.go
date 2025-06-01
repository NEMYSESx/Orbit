package models

import (
	"context"
	"time"
)

type DocumentMetadata struct {
	Title            string                 `json:"title"`
	Filepath         string                 `json:"filepath"`
	FileSize         int64                  `json:"file_size"`
	Author           string                 `json:"author,omitempty"`
	CreationDate     *time.Time             `json:"creation_date,omitempty"`
	LastModifiedDate string                 `json:"last_modified_date,omitempty"`
	Language         string                 `json:"language,omitempty"`
	ContentType      string                 `json:"content_type"`
	SourceType       string                 `json:"source_type"`
	Checksum         string                 `json:"checksum"`
	ProcessedAt      time.Time              `json:"processed_at"`
	ExtraMetadata    map[string]interface{} `json:"extra_metadata,omitempty"`
}

type ExtractedContent struct {
	Metadata  DocumentMetadata `json:"metadata"`
	CleanText string           `json:"clean_text"`
	WordCount int              `json:"word_count"`
	PageCount int              `json:"page_count,omitempty"`
}

type TikaResponse struct {
	Content  string                 `json:"content"`
	Metadata map[string]interface{} `json:"metadata"`
}

type ProcessingResult struct {
	Success     bool              `json:"success"`
	Document    *ExtractedContent `json:"document,omitempty"`
	Error       string            `json:"error,omitempty"`
	ProcessTime time.Duration     `json:"process_time"`
	OutputPath  string            `json:"output_path,omitempty"`
}

type BatchProcessingResult struct {
	TotalFiles   int                `json:"total_files"`
	SuccessCount int                `json:"success_count"`
	ErrorCount   int                `json:"error_count"`
	Results      []ProcessingResult `json:"results"`
	TotalTime    time.Duration      `json:"total_time"`
	ErrorDetails []string           `json:"error_details,omitempty"`
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

type Chunk struct {
	ID       string        `json:"id"`
	Content  string        `json:"content"`
	Metadata ChunkMetadata `json:"metadata"`
	Vector   []float32     `json:"vector,omitempty"`
}

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

type ChunkingConfig struct {
	GeminiAPIKey   string
	GeminiModel    string
	MaxRetries     int
	MaxConcurrency int
	RateLimitRPS   int
	RequestTimeout time.Duration
}

type ChunkerResult struct {
	Chunks      []Chunk `json:"chunks"`
	TotalCount  int     `json:"total_count"`
	ProcessedAt string  `json:"processed_at"`
}

type ProcessResult struct {
	ExtractedContent *ExtractedContent `json:"extracted_content"`
	Chunks           []ChunkOutput     `json:"chunks,omitempty"`
}

type GeminiRequest struct {
	Contents []Content `json:"contents"`
}

type Content struct {
	Parts []Part `json:"parts"`
}

type Part struct {
	Text string `json:"text"`
}

type GeminiResponse struct {
	Candidates []Candidate `json:"candidates"`
}

type Candidate struct {
	Content Content `json:"content"`
}

type GeminiChunkerResponse struct {
	Chunks []struct {
		Content    string   `json:"content"`
		Topic      string   `json:"topic"`
		Keywords   []string `json:"keywords"`
		Entities   []string `json:"entities"`
		Summary    string   `json:"summary"`
		Category   string   `json:"category"`
		Sentiment  string   `json:"sentiment"`
		Complexity string   `json:"complexity"`
		Language   string   `json:"language"`
	} `json:"chunks"`
}

type TextChunker interface {
	ChunkTextWithSource(ctx context.Context, text string, sourceInfo SourceInfo) ([]ChunkOutput, error)
}

type AgenticChunker interface {
	ChunkText(ctx context.Context, text string) (*ChunkerResult, error)
}

func (cr *ChunkerResult) ToQdrantPayload() []map[string]interface{} {
	payload := make([]map[string]interface{}, len(cr.Chunks))
	
	for i, chunk := range cr.Chunks {
		payload[i] = map[string]interface{}{
			"id": chunk.ID,
			"payload": map[string]interface{}{
				"content":     chunk.Content,
				"topic":       chunk.Metadata.Topic,
				"keywords":    chunk.Metadata.Keywords,
				"entities":    chunk.Metadata.Entities,
				"summary":     chunk.Metadata.Summary,
				"category":    chunk.Metadata.Category,
				"sentiment":   chunk.Metadata.Sentiment,
				"complexity":  chunk.Metadata.Complexity,
				"language":    chunk.Metadata.Language,
				"word_count":  chunk.Metadata.WordCount,
				"chunk_index": chunk.Metadata.ChunkIndex,
				"timestamp":   chunk.Metadata.Timestamp,
			},
		}
		
		if len(chunk.Vector) > 0 {
			payload[i]["vector"] = chunk.Vector
		}
	}
	
	return payload
}

func (cr *ChunkerResult) FilterChunksByCategory(category string) []Chunk {
	var filtered []Chunk
	for _, chunk := range cr.Chunks {
		if chunk.Metadata.Category == category {
			filtered = append(filtered, chunk)
		}
	}
	return filtered
}

func (cr *ChunkerResult) GetChunksByKeyword(keyword string) []Chunk {
	var matches []Chunk
	
	for _, chunk := range cr.Chunks {
		for _, kw := range chunk.Metadata.Keywords {
			if kw == keyword {
				matches = append(matches, chunk)
				break
			}
		}
	}
	
	return matches
}

func (cr *ChunkerResult) GetStatistics() map[string]interface{} {
	totalWords := 0
	categories := make(map[string]int)
	sentiments := make(map[string]int)
	complexities := make(map[string]int)
	languages := make(map[string]int)
	
	for _, chunk := range cr.Chunks {
		totalWords += chunk.Metadata.WordCount
		categories[chunk.Metadata.Category]++
		sentiments[chunk.Metadata.Sentiment]++
		complexities[chunk.Metadata.Complexity]++
		languages[chunk.Metadata.Language]++
	}
	
	avgWords := 0.0
	if cr.TotalCount > 0 {
		avgWords = float64(totalWords) / float64(cr.TotalCount)
	}
	
	return map[string]interface{}{
		"total_chunks":              cr.TotalCount,
		"total_words":               totalWords,
		"average_words_per_chunk":   avgWords,
		"categories":                categories,
		"sentiments":                sentiments,
		"complexities":              complexities,
		"languages":                 languages,
		"processed_at":              cr.ProcessedAt,
	}
}