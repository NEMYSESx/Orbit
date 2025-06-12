package main

import (
	"log"

	"github.com/NEMYSESx/Orbit/apps/logs-ingestion/internal/config"
)

func main() {
	

	cfg, err := config.Load("config.json")
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	logService, err := service.NewLogService(cfg)
	if err != nil {
		log.Fatalf("Failed to create log service: %v", err)
	}
	defer logService.Close()

	log.Printf("Starting log ingester service...")
	if err := logService.Start(); err != nil {
		log.Fatalf("Failed to start service: %v", err)
	}
}