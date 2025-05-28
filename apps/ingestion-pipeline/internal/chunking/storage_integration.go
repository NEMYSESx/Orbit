package chunking

import (
	"fmt"
	"time"

	"github.com/NEMYSESx/orbit/apps/ingestion-pipeline/internal/models"
	"github.com/NEMYSESx/orbit/apps/ingestion-pipeline/internal/storage"
)

type ChunkingStorageManager struct {
	storageManager *storage.Manager
	config         *Config
}

func NewChunkingStorageManager(storageManager *storage.Manager, config *Config) *ChunkingStorageManager {
	return &ChunkingStorageManager{
		storageManager: storageManager,
		config:         config,
	}
}

func (csm *ChunkingStorageManager) SaveChunkedDocument(chunkedDoc *ChunkedDocument) (string, error) {
	// Create a new ExtractedContent for the chunked document
	chunkedContent := &models.ExtractedContent{
		Metadata: models.DocumentMetadata{
			ID:               chunkedDoc.OriginalDocument.Metadata.ID + "_chunked",
			SourceID:         chunkedDoc.OriginalDocument.Metadata.SourceID,
			SourceType:       "chunked_" + chunkedDoc.OriginalDocument.Metadata.SourceType,
			Title:            chunkedDoc.OriginalDocument.Metadata.Title + " (Chunked)",
			Filepath:         chunkedDoc.OriginalDocument.Metadata.Filepath,
			LastModifiedDate: chunkedDoc.OriginalDocument.Metadata.LastModifiedDate,
			FileSize:         chunkedDoc.OriginalDocument.Metadata.FileSize,
			Author:           chunkedDoc.OriginalDocument.Metadata.Author,
			CreationDate:     chunkedDoc.OriginalDocument.Metadata.CreationDate,
			Language:         chunkedDoc.OriginalDocument.Metadata.Language,
			ContentType:      "application/json",
			Checksum:         chunkedDoc.OriginalDocument.Metadata.Checksum,
			ProcessedAt:      time.Now(),
		},
		RawText:   chunkedDoc.OriginalDocument.RawText,
		CleanText: csm.generateChunkedSummary(chunkedDoc),
	}

	return csm.storageManager.Save(chunkedContent)
}

func (csm *ChunkingStorageManager) SaveChunksAsIndividualFiles(chunkedDoc *ChunkedDocument) ([]string, error) {
	var savedPaths []string

	for i, chunk := range chunkedDoc.Chunks {
		chunkContent := &models.ExtractedContent{
			Metadata: models.DocumentMetadata{
				ID:               fmt.Sprintf("%s_chunk_%d", chunkedDoc.OriginalDocument.Metadata.ID, i),
				SourceID:         chunk.Payload.SourceID,
				SourceType:       "chunk",
				Title:            fmt.Sprintf("%s - Chunk %d", chunk.Payload.Title, i+1),
				Filepath:         chunk.Payload.Filepath,
				LastModifiedDate: chunk.Payload.LastModifiedDate,
				FileSize:         int64(len(chunk.Payload.Text)),
				ContentType:      "text/plain",
				ProcessedAt:      time.Now(),
			},
			RawText:   chunk.Payload.Text,
			CleanText: chunk.Payload.Text,
		}

		savedPath, err := csm.storageManager.Save(chunkContent)
		if err != nil {
			return savedPaths, fmt.Errorf("failed to save chunk %d: %w", i, err)
		}
		savedPaths = append(savedPaths, savedPath)
	}

	return savedPaths, nil
}

func (csm *ChunkingStorageManager) generateChunkedSummary(chunkedDoc *ChunkedDocument) string {
	summary := fmt.Sprintf("Document processed into %d chunks\n\n", len(chunkedDoc.Chunks))
	summary += fmt.Sprintf("Processing Summary:\n")
	summary += fmt.Sprintf("- Total Chunks: %d\n", chunkedDoc.ProcessingSummary.TotalChunks)
	summary += fmt.Sprintf("- Processing Duration: %v\n", chunkedDoc.ProcessingSummary.ProcessingDuration)
	summary += fmt.Sprintf("- Average Confidence: %.2f\n", chunkedDoc.ProcessingSummary.AverageConfidence)
	summary += fmt.Sprintf("- Failed Chunks: %d\n\n", chunkedDoc.ProcessingSummary.FailedChunks)

	for i, chunk := range chunkedDoc.Chunks {
		summary += fmt.Sprintf("Chunk %d:\n", i+1)
		summary += fmt.Sprintf("Role: %s\n", chunk.Payload.Analysis.ChunkRole)
		summary += fmt.Sprintf("Topics: %v\n", chunk.Payload.Analysis.Topics)
		summary += fmt.Sprintf("Confidence: %.2f\n", chunk.Payload.Analysis.AgentConfidence)
		summary += fmt.Sprintf("Text Preview: %s...\n\n", 
			chunk.Payload.Text[:min(100, len(chunk.Payload.Text))])
	}

	return summary
}
