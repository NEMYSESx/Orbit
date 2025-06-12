package service

import (
	"context"
	"fmt"
	"log"
	"net"

	"log-ingester/config"
	"log-ingester/kafka"
	pb "log-ingester/proto"

	"google.golang.org/grpc"
)

type LogService struct {
	pb.UnimplementedLogIngesterServer
	producer *kafka.Producer
	config   *config.Config
}

func NewLogService(cfg *config.Config) (*LogService, error) {
	producer, err := kafka.NewProducer(&cfg.Kafka)
	if err != nil {
		return nil, err
	}

	return &LogService{
		producer: producer,
		config:   cfg,
	}, nil
}

func (s *LogService) SendLogs(ctx context.Context, req *pb.LogBatch) (*pb.LogResponse, error) {
	logMessages := make([]*kafka.LogMessage, len(req.Logs))
	
	for i, logEntry := range req.Logs {
		logMessages[i] = &kafka.LogMessage{
			Timestamp:   logEntry.Timestamp,
			Level:       logEntry.Level,
			Type:        logEntry.Type,
			Message:     logEntry.Message,
			Source:      logEntry.Source,
			Hostname:    logEntry.Hostname,
			Environment: logEntry.Environment,
			Facility:    logEntry.Facility,
			Category:    logEntry.Category,
			Priority:    logEntry.Priority,
			Metadata:    logEntry.Metadata,
		}
	}

	err := s.producer.SendLogs(logMessages)
	if err != nil {
		log.Printf("Failed to send logs to Kafka: %v", err)
		return &pb.LogResponse{
			Success:        false,
			Message:        fmt.Sprintf("Failed to send logs: %v", err),
			ProcessedCount: 0,
		}, nil
	}

	return &pb.LogResponse{
		Success:        true,
		Message:        "Logs sent successfully",
		ProcessedCount: int32(len(req.Logs)),
	}, nil
}

func (s *LogService) SendLogStream(stream pb.LogIngester_SendLogStreamServer) error {
	count := 0
	for {
		logEntry, err := stream.Recv()
		if err != nil {
			break
		}

		logMessage := &kafka.LogMessage{
			Timestamp:   logEntry.Timestamp,
			Level:       logEntry.Level,
			Type:        logEntry.Type,
			Message:     logEntry.Message,
			Source:      logEntry.Source,
			Hostname:    logEntry.Hostname,
			Environment: logEntry.Environment,
			Facility:    logEntry.Facility,
			Category:    logEntry.Category,
			Priority:    logEntry.Priority,
			Metadata:    logEntry.Metadata,
		}

		err = s.producer.SendLog(logMessage)
		if err != nil {
			log.Printf("Failed to send log to Kafka: %v", err)
			return stream.SendAndClose(&pb.LogResponse{
				Success:        false,
				Message:        fmt.Sprintf("Failed to send log: %v", err),
				ProcessedCount: int32(count),
			})
		}
		count++
	}

	return stream.SendAndClose(&pb.LogResponse{
		Success:        true,
		Message:        "Stream processed successfully",
		ProcessedCount: int32(count),
	})
}

func (s *LogService) Start() error {
	lis, err := net.Listen("tcp", fmt.Sprintf("%s:%d", s.config.Server.Host, s.config.Server.Port))
	if err != nil {
		return err
	}

	grpcServer := grpc.NewServer()
	pb.RegisterLogIngesterServer(grpcServer, s)

	log.Printf("gRPC server starting on %s:%d", s.config.Server.Host, s.config.Server.Port)
	return grpcServer.Serve(lis)
}

func (s *LogService) Close() error {
	return s.producer.Close()
}