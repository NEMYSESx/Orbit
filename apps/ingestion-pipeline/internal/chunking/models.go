package chunking

import (
	"time"

	"github.com/NEMYSESx/orbit/apps/ingestion-pipeline/internal/models"
)

type SourceLocation struct {
	PageNumber *int `json:"page_number,omitempty"`
	StartChar  *int `json:"start_char,omitempty"`
	EndChar    *int `json:"end_char,omitempty"`
	ChunkIndex *int `json:"chunk_index,omitempty"`
}

type ChunkAnalysis struct {
	ChunkRole              string    `json:"chunk_role"`
	KeyEntities           []string  `json:"key_entities"`
	Topics                []string  `json:"topics"`
	OriginalContextSummary string   `json:"original_context_summary"`
	LevelOfDetail         string    `json:"level_of_detail"`
	AgentConfidence       float64   `json:"agent_confidence"`
	ProcessingTimestamp   time.Time `json:"processing_timestamp"`
}

type ChunkPayload struct {
	Text                   string         `json:"text"`
	SourceID              string         `json:"source_id"`
	SourceType            string         `json:"source_type"`
	Title                 string         `json:"title"`
	Filepath              string         `json:"filepath"`
	LastModifiedDate      time.Time      `json:"last_modified_date"`
	SourceLocation        SourceLocation `json:"source_location"`
	Analysis              ChunkAnalysis  `json:"analysis"`
	RelatedChunks         []string       `json:"related_chunks"`
	ProcessingMetadata    ProcessingMetadata `json:"processing_metadata"`
}

type ProcessingMetadata struct {
	ChunkID           string    `json:"chunk_id"`
	ProcessedAt       time.Time `json:"processed_at"`
	ProcessingVersion string    `json:"processing_version"`
	TokenCount        int       `json:"token_count"`
	ProcessingTimeMs  int64     `json:"processing_time_ms"`
}

type QdrantPoint struct {
	ID      string       `json:"id"`
	Vector  []float64    `json:"vector"`
	Payload ChunkPayload `json:"payload"`
}

type ChunkedDocument struct {
	OriginalDocument models.ExtractedContent `json:"original_document"`
	Chunks          []QdrantPoint           `json:"chunks"`
	ProcessingSummary ProcessingSummary      `json:"processing_summary"`
}

type ProcessingSummary struct {
	TotalChunks        int           `json:"total_chunks"`
	ProcessingDuration time.Duration `json:"processing_duration"`
	AverageConfidence  float64       `json:"average_confidence"`
	FailedChunks       int           `json:"failed_chunks"`
	ProcessedAt        time.Time     `json:"processed_at"`
}