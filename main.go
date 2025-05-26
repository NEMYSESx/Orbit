package main

import (
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/NEMYSESx/orbit/apps/data/logs"
	tika_extractor "github.com/NEMYSESx/orbit/apps/ingestion-pipeline/cmd/tika-extractor"
)

func main() {
	config := logs.DefaultLogConfig()
	
	config.OutputDir = "./data/synthetic_logs"
	config.LogsPerMinute = map[string]int{
		"system":  20,  
		"network": 10,  
		"cluster": 5,   
		"slurm":   15,  
	}
	config.RotationInterval = 1 * time.Hour  
	
	
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
	
	go logs.LogsWithConfig(config)
	
	fmt.Println("Log generator started. Press Ctrl+C to stop.")
	
	<-sigChan
	fmt.Println("\nShutting down log generator...")

	tika_extractor.TikaExtractor()
}