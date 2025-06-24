package consumer

import (
	"encoding/json"
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/NEMYSESx/Orbit/apps/embedding-pipeline/internal/config"
	"github.com/confluentinc/confluent-kafka-go/kafka"
)

type LogChunk struct {
	Message   string                 `json:"message"`
	Timestamp time.Time              `json:"timestamp"`
	Level     string                 `json:"level"`
	Type      string                 `json:"type"`
	Source    string                 `json:"source"`
	Details   map[string]interface{} `json:"details,omitempty"`
}

type LogKafkaConsumer struct {
	consumer *kafka.Consumer
	topic    string
}

func NewLogKafkaConsumer(cfg config.KafkaConfig) (*LogKafkaConsumer, error) {
	c, err := kafka.NewConsumer(&kafka.ConfigMap{
		"bootstrap.servers": cfg.BootstrapServers,
		"group.id":          cfg.GroupID + "-logs",
		"auto.offset.reset": cfg.AutoOffsetReset,
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create log consumer: %w", err)
	}

	if err := c.SubscribeTopics([]string{"logs"}, nil); err != nil {
		c.Close()
		return nil, fmt.Errorf("failed to subscribe to logs topic: %w", err)
	}

	log.Println("Log consumer started for topic: logs")
	return &LogKafkaConsumer{consumer: c, topic: "logs"}, nil
}

func (l *LogKafkaConsumer) ConsumeLogMessage() (*LogChunk, error) {
	for {
		msg, err := l.consumer.ReadMessage(-1)
		if err != nil {
			log.Printf("Error reading log message: %v", err)
			continue
		}

		if len(msg.Value) == 0 {
			continue
		}

		var fluentBitLog map[string]interface{}
		if err := json.Unmarshal(msg.Value, &fluentBitLog); err != nil {
			log.Printf("Error parsing JSON: %v", err)
			continue
		}

		var message string
		var messageFound bool

		if msgValue, ok := fluentBitLog["message"]; ok {
			if msgStr, isString := msgValue.(string); isString && strings.TrimSpace(msgStr) != "" {
				message = strings.TrimSpace(msgStr)
				messageFound = true
			}
		}

		if !messageFound {
			if logValue, ok := fluentBitLog["log"]; ok {
				if logStr, isString := logValue.(string); isString {
					logStr = strings.TrimSpace(logStr)
					if logStr != "" && logStr != "{" && logStr != "}" && logStr != "[" && logStr != "]" {
						if strings.Contains(logStr, "service") && strings.Contains(logStr, ":") {
							parts := strings.Split(logStr, ":")
							if len(parts) >= 2 {
								serviceName := strings.Trim(strings.TrimSpace(parts[1]), `"`)
								if serviceName != "" {
									message = fmt.Sprintf("Service event: %s", serviceName)
									messageFound = true
								}
							}
						} else {
							message = logStr
							messageFound = true
						}
					}
				}
			}
		}

		if !messageFound || message == "" {
			continue
		}

		level, _ := fluentBitLog["level"].(string)
		if level == "" {
			level = "INFO"
		}

		logType, _ := fluentBitLog["type"].(string)
		if logType == "" {
			logType = "system"
		}

		source, _ := fluentBitLog["source"].(string)
		if source == "" {
			source = "unknown"
		}

		timestamp := time.Now()
		if originalTimestamp, ok := fluentBitLog["original_timestamp"].(string); ok {
			if parsedTime, err := time.Parse("2006-01-02T15:04:05.000Z", originalTimestamp); err == nil {
				timestamp = parsedTime
			} else if parsedTime, err := time.Parse(time.RFC3339, originalTimestamp); err == nil {
				timestamp = parsedTime
			}
		} else if tsValue, ok := fluentBitLog["@timestamp"]; ok {
			switch ts := tsValue.(type) {
			case float64:
				timestamp = time.Unix(int64(ts), int64((ts-float64(int64(ts)))*1e9))
			case int64:
				timestamp = time.Unix(ts, 0)
			}
		}

		details := make(map[string]interface{})
		for key, value := range fluentBitLog {
			if strings.HasPrefix(key, "detail_") {
				detailKey := strings.TrimPrefix(key, "detail_")
				details[detailKey] = value
			}
		}

		if collector, ok := fluentBitLog["collector"].(string); ok {
			details["collector"] = collector
		}
		if logFilePath, ok := fluentBitLog["log_file_path"].(string); ok {
			details["log_file_path"] = logFilePath
		}

		return &LogChunk{
			Message:   message,
			Timestamp: timestamp,
			Level:     level,
			Type:      logType,
			Source:    source,
			Details:   details,
		}, nil
	}
}

func (l *LogKafkaConsumer) Close() error {
	if l.consumer != nil {
		return l.consumer.Close()
	}
	return nil
}