package config

import (
	"encoding/json"
	"fmt"
	"os"
	"time"
)

type Duration struct {
	time.Duration
}

func (d *Duration) UnmarshalJSON(b []byte) error {
	var v interface{}
	if err := json.Unmarshal(b, &v); err != nil {
		return err
	}
	switch value := v.(type) {
	case string:
		var err error
		d.Duration, err = time.ParseDuration(value)
		if err != nil {
			return err
		}
		return nil
	default:
		return fmt.Errorf("invalid duration")
	}
}

func (d Duration) MarshalJSON() ([]byte, error) {
	return json.Marshal(d.String())
}

func (d Duration) String() string {
	return d.Duration.String()
}

type Config struct {
	Tika       TikaConfig       `json:"tika"`
	Storage    StorageConfig    `json:"storage"`
	Processing ProcessingConfig `json:"processing"`
	Chunking   ChunkingConfig   `json:"chunking"`
}

type TikaConfig struct {
	ServerURL     string   `json:"server_url"`
	Timeout       Duration `json:"timeout"`
	RetryAttempts int      `json:"retry_attempts"`
	RetryDelay    Duration `json:"retry_delay"`
}

type StorageConfig struct {
	OutputDir      string `json:"output_dir"`
	TempDir        string `json:"temp_dir"`
	KeepOriginals  bool   `json:"keep_originals"`
	CompressOutput bool   `json:"compress_output"`
}

type ChunkingConfig struct {
	Enabled      bool    `json:"enabled"`
	GeminiAPIKey string  `json:"gemini_api_key"`
	GeminiModel  string  `json:"gemini_model"`
	MaxTokens    int     `json:"max_tokens"`
	Temperature  float64 `json:"temperature"`
	SectionSize  int     `json:"sectionSize"`
}

type ProcessingConfig struct {
	MaxFileSize      int64    `json:"max_file_size_mb"`
	SupportedFormats []string `json:"supported_formats"`
	BatchSize        int      `json:"batch_size"`
	MaxConcurrency   int      `json:"max_concurrency"`
	EnableTextClean  bool     `json:"enable_text_cleaning"`
}

func Load(configPath string) (*Config, error) {
	if configPath == "" {
		return nil, fmt.Errorf("config path cannot be empty")
	}

	cfg := &Config{}

	if err := cfg.loadFromFile(configPath); err != nil {
		return nil, fmt.Errorf("failed to load config from file: %w", err)
	}

	if err := cfg.validate(); err != nil {
		return nil, fmt.Errorf("invalid configuration: %w", err)
	}

	return cfg, nil
}

func (c *Config) loadFromFile(path string) error {
	file, err := os.Open(path)
	if err != nil {
		return err
	}
	defer file.Close()

	return json.NewDecoder(file).Decode(c)
}

func (c *Config) validate() error {
	if c.Tika.ServerURL == "" {
		return fmt.Errorf("tika server URL cannot be empty")
	}
	if c.Processing.MaxFileSize <= 0 {
		return fmt.Errorf("max file size must be positive")
	}
	if c.Processing.BatchSize <= 0 {
		return fmt.Errorf("batch size must be positive")
	}
	if c.Processing.MaxConcurrency <= 0 {
		return fmt.Errorf("max concurrency must be positive")
	}
	
	if c.Chunking.Enabled {
		if c.Chunking.GeminiAPIKey == "" {
			return fmt.Errorf("gemini API key is required when chunking is enabled")
		}
		if c.Chunking.MaxTokens <= 0 {
			return fmt.Errorf("max tokens must be positive when chunking is enabled")
		}
		if c.Chunking.Temperature < 0 || c.Chunking.Temperature > 2 {
			return fmt.Errorf("temperature must be between 0 and 2")
		}
	}
	
	return nil
}

func (c *Config) Save(path string) error {
	file, err := os.Create(path)
	if err != nil {
		return err
	}
	defer file.Close()

	encoder := json.NewEncoder(file)
	encoder.SetIndent("", "  ")
	return encoder.Encode(c)
}