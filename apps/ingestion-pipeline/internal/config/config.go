package config

import (
	"encoding/json"
	"fmt"
	"os"
	"time"
)

type Config struct {
	Tika     TikaConfig     `json:"tika"`
	Storage  StorageConfig  `json:"storage"`
	Services ServicesConfig `json:"services"`
	Processing ProcessingConfig `json:"processing"`
}

type TikaConfig struct {
	ServerURL     string        `json:"server_url"`
	Timeout       time.Duration `json:"timeout"`
	RetryAttempts int           `json:"retry_attempts"`
	RetryDelay    time.Duration `json:"retry_delay"`
}

type StorageConfig struct {
	OutputDir        string `json:"output_dir"`
	TempDir          string `json:"temp_dir"`
	KeepOriginals    bool   `json:"keep_originals"`
	CompressOutput   bool   `json:"compress_output"`
}

type ServicesConfig struct {
	ChunkingService ChunkingServiceConfig `json:"chunking_service"`
}

type ChunkingServiceConfig struct {
	URL     string        `json:"url"`
	Enabled bool          `json:"enabled"`
	Timeout time.Duration `json:"timeout"`
}

type ProcessingConfig struct {
	MaxFileSize      int64    `json:"max_file_size_mb"`
	SupportedFormats []string `json:"supported_formats"`
	BatchSize        int      `json:"batch_size"`
	MaxConcurrency   int      `json:"max_concurrency"`
	EnableTextClean  bool     `json:"enable_text_cleaning"`
}

func Load(configPath string) (*Config, error) {
	cfg := &Config{
		Tika: TikaConfig{
			ServerURL:     "http://localhost:9998",
			Timeout:       10 * time.Minute,
			RetryAttempts: 3,
			RetryDelay:    5 * time.Second,
		},
		Storage: StorageConfig{
			OutputDir:      "./processed_documents",
			TempDir:        "/tmp/doc-processor",
			KeepOriginals:  true,
			CompressOutput: false,
		},
		Services: ServicesConfig{
			ChunkingService: ChunkingServiceConfig{
				URL:     "http://localhost:8080",
				Enabled: false,
				Timeout: 30 * time.Second,
			},
		},
		Processing: ProcessingConfig{
			MaxFileSize:      100, 
			SupportedFormats: []string{"pdf", "docx", "doc", "txt", "html", "rtf", "odt"},
			BatchSize:        5,
			MaxConcurrency:   10,
			EnableTextClean:  true,
		},
	}

	if configPath != "" {
		if err := cfg.loadFromFile(configPath); err != nil {
			return nil, fmt.Errorf("failed to load config from file: %w", err)
		}
	}

	if err := cfg.validate(); err != nil {
		return nil, fmt.Errorf("invalid configuration: %w", err)
	}

	return cfg, nil
}

func (c *Config) loadFromFile(path string) error {
	file, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil 
		}
		return err
	}
	defer file.Close()

	return json.NewDecoder(file).Decode(c)
}

func (c *Config) validate() error {
	if c.Tika.ServerURL == "" {
		return fmt.Errorf("tika server URL cannot be empty")
	}
	if c.Storage.OutputDir == "" {
		return fmt.Errorf("output directory cannot be empty")
	}
	if c.Processing.MaxFileSize <= 0 {
		return fmt.Errorf("max file size must be positive")
	}
	if c.Processing.BatchSize <= 0 {
		c.Processing.BatchSize = 1
	}
	if c.Processing.MaxConcurrency <= 0 {
		c.Processing.MaxConcurrency = 1
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