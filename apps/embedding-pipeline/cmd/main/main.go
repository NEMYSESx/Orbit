package main

import (
	"fmt"
	"log"

	"github.com/Orbit/apps/embedding-pipeline/internal/configs"
)


type APIStructResponse struct {
	Success bool   `json:"success"`
	Message string `json:"message"`
	Error bool     `json:"error,omitempty"`
}

func main() {
	cfg,err := configs.Load("config.json")
	if err != nil {
		log.Fatalf("Failed to load config %v", err)
	}

	getChunks,err := processor.New(&cfg)
}



