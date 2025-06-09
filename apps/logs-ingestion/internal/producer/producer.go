package producer

import (
	"encoding/json"
	"log"
	"time"

	"log-ingester/config"

	"github.com/IBM/sarama"
)

type Producer struct {
	producer sarama.SyncProducer
	config   *config.KafkaConfig
}

type LogMessage struct {
	Timestamp   string            `json:"timestamp"`
	Level       string            `json:"level"`
	Type        string            `json:"type"`
	Message     string            `json:"message"`
	Source      string            `json:"source"`
	Hostname    string            `json:"hostname"`
	Environment string            `json:"environment"`
	Facility    string            `json:"facility"`
	Category    string            `json:"category"`
	Priority    string            `json:"priority"`
	Metadata    map[string]string `json:"metadata"`
}

func NewProducer(cfg *config.KafkaConfig) (*Producer, error) {
	saramaConfig := sarama.NewConfig()
	saramaConfig.Producer.RequiredAcks = sarama.WaitForAll
	saramaConfig.Producer.Retry.Max = cfg.Retries
	saramaConfig.Producer.Return.Successes = true
	saramaConfig.Producer.Timeout = time.Duration(cfg.Timeout) * time.Second
	saramaConfig.Producer.Flush.Frequency = time.Duration(cfg.FlushInterval) * time.Millisecond
	saramaConfig.Producer.Flush.Messages = cfg.BatchSize

	producer, err := sarama.NewSyncProducer(cfg.Brokers, saramaConfig)
	if err != nil {
		return nil, err
	}

	return &Producer{
		producer: producer,
		config:   cfg,
	}, nil
}

func (p *Producer) SendLog(logMsg *LogMessage) error {
	data, err := json.Marshal(logMsg)
	if err != nil {
		return err
	}

	msg := &sarama.ProducerMessage{
		Topic:     p.config.Topic,
		Partition: p.config.Partition,
		Value:     sarama.StringEncoder(data),
		Timestamp: time.Now(),
	}

	_, _, err = p.producer.SendMessage(msg)
	if err != nil {
		log.Printf("Failed to send message to Kafka: %v", err)
		return err
	}

	return nil
}

func (p *Producer) SendLogs(logMsgs []*LogMessage) error {
	for _, logMsg := range logMsgs {
		if err := p.SendLog(logMsg); err != nil {
			return err
		}
	}
	return nil
}

func (p *Producer) Close() error {
	return p.producer.Close()
}