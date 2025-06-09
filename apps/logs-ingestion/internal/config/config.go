package config

import (
	"encoding/json"
	"os"
)

type Config struct {
	Server ServerConfig `json:"server"`
	Kafka  KafkaConfig  `json:"kafka"`
	Log    LogConfig    `json:"logging"`
}

type ServerConfig struct {
	Host string `json:"host"`
	Port int    `json:"port"`
}

type KafkaConfig struct {
	Brokers       []string `json:"brokers"`
	Topic         string   `json:"topic"`
	Partition     int32    `json:"partition"`
	Timeout       int      `json:"timeout"`
	Retries       int      `json:"retries"`
	BatchSize     int      `json:"batch_size"`
	FlushInterval int      `json:"flush_interval"`
}

type LogConfig struct {
	Level         string `json:"level"`
	EnableConsole bool   `json:"enable_console"`
}

func Load(filename string) (*Config, error) {
	data, err := os.ReadFile(filename)
	if err != nil {
		return nil, err
	}

	var config Config
	err = json.Unmarshal(data, &config)
	if err != nil {
		return nil, err
	}

	return &config, nil
}