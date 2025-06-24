package consumer

type ChunkOutput struct {
	Text          string        `json:"text"`
	Source        SourceInfo    `json:"source"`
	ChunkMetadata ChunkMetadata `json:"chunk_metadata"`
}

type SourceInfo struct {
	DocumentTitle string `json:"document_title"`
	DocumentType  string `json:"document_type"`
	Section       string `json:"section"`
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
	Embedding  []float32 `json:"embedding"`
	KafkaTopic string    `json:"kafka_topic"`
}

type LogMessage struct {
	Timestamp string                 `json:"timestamp"`
	Level     string                 `json:"level"`
	Type      string                 `json:"type"`
	Message   string                 `json:"message"`
	Source    string                 `json:"source"`
	Details   map[string]interface{} `json:"details,omitempty"`

	Log      string                 `json:"log,omitempty"`
	Stream   string                 `json:"stream,omitempty"`
	Time     string                 `json:"time,omitempty"`
	Tag      string                 `json:"tag,omitempty"`
	Metadata map[string]interface{} `json:"metadata,omitempty"`
}
