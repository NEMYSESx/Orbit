package models

import (
	"time"
)

type DocumentMetadata struct {
	ID               string                 `json:"id"`
	SourceID         string                 `json:"source_id"`
	SourceType       string                 `json:"source_type"`
	Title            string                 `json:"title"`
	Filepath         string                 `json:"filepath"`
	LastModifiedDate time.Time              `json:"last_modified_date"`
	FileSize         int64                  `json:"file_size"`
	Author           string                 `json:"author,omitempty"`
	CreationDate     *time.Time             `json:"creation_date,omitempty"`
	Language         string                 `json:"language,omitempty"`
	ContentType      string                 `json:"content_type"`
	Checksum         string                 `json:"checksum"`
	ProcessedAt      time.Time              `json:"processed_at"`
	ProcessorVersion string                 `json:"processor_version"`
	ExtraMetadata    map[string]interface{} `json:"extra_metadata,omitempty"`
}

type ExtractedContent struct {
	Metadata  DocumentMetadata `json:"metadata"`
	RawText   string           `json:"raw_text"`
	CleanText string           `json:"clean_text"`
	WordCount int              `json:"word_count"`
	PageCount int              `json:"page_count,omitempty"`
}

type TikaResponse struct {
	Content  string                 `json:"content"`
	Metadata map[string]interface{} `json:"metadata"`
}

type ProcessingResult struct {
	Success     bool                 `json:"success"`
	Document    *ExtractedContent    `json:"document,omitempty"`
	Error       string               `json:"error,omitempty"`
	ProcessTime time.Duration        `json:"process_time"`
	OutputPath  string               `json:"output_path,omitempty"`
}

type BatchProcessingResult struct {
	TotalFiles     int                `json:"total_files"`
	SuccessCount   int                `json:"success_count"`
	ErrorCount     int                `json:"error_count"`
	Results        []ProcessingResult `json:"results"`
	TotalTime      time.Duration      `json:"total_time"`
	ErrorDetails   []string           `json:"error_details,omitempty"`
}