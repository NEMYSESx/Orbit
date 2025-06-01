package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"time"

	"github.com/NEMYSESx/Orbit/apps/ingestion-pipeline/internal/config"
	"github.com/NEMYSESx/Orbit/apps/ingestion-pipeline/internal/processor"
)

type APIResponse struct {
	Success bool   `json:"success"`
	Message string `json:"message"`
	Data    any    `json:"data,omitempty"`
	Error   string `json:"error,omitempty"`
}

type ProcessingResponse struct {
	FileName       string `json:"fileName"`
	ProcessingTime string `json:"processingTime"`
	Data           any    `json:"data"`
}

func main() {
	cfg, err := config.Load("config.json")
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	docProcessor, err := processor.New(cfg)
	if err != nil {
		log.Fatalf("Failed to create document processor: %v", err)
	}

	http.HandleFunc("/receive", handleReceiveDocument(docProcessor, cfg))

	port := "3001"
	log.Printf("Starting server on port %s", port)
	log.Printf("Document upload endpoint: http://localhost:%s/receive", port)
	log.Printf("Max file size: %d MB", cfg.Processing.MaxFileSize)

	if err := http.ListenAndServe(":"+port, nil); err != nil {
		log.Fatalf("Server failed to start: %v", err)
	}
}

func handleReceiveDocument(docProcessor *processor.DocumentProcessor, cfg *config.Config) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")

		if r.Method == "OPTIONS" {
			w.WriteHeader(http.StatusOK)
			return
		}

		if r.Method != "POST" {
			sendErrorResponse(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		startTime := time.Now()

		// Add file size validation
		err := r.ParseMultipartForm(int64(cfg.Processing.MaxFileSize) << 20) // Convert MB to bytes
		if err != nil {
			log.Printf("Failed to parse multipart form: %v", err)
			sendErrorResponse(w, "File too large or invalid form data", http.StatusBadRequest)
			return
		}

		file, header, err := r.FormFile("document")
		if err != nil {
			log.Printf("Failed to get file from form: %v", err)
			sendErrorResponse(w, "No document file found in request", http.StatusBadRequest)
			return
		}
		defer file.Close()

		result, err := docProcessor.ProcessDocument(r.Context(), file, header)
		if err != nil {
			log.Printf("Failed to process document: %v", err)
			sendErrorResponse(w, fmt.Sprintf("Failed to process document: %v", err), http.StatusInternalServerError)
			return
		}

		processingResponse := ProcessingResponse{
			FileName:       header.Filename,
			ProcessingTime: time.Since(startTime).String(),
			Data:           result,
		}

		log.Printf("Successfully processed document: %s", header.Filename)

		sendSuccessResponse(w, "Document processed successfully", processingResponse)
	}
}

func sendSuccessResponse(w http.ResponseWriter, message string, data any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)

	response := APIResponse{
		Success: true,
		Message: message,
		Data:    data,
	}

	if err := json.NewEncoder(w).Encode(response); err != nil {
		log.Printf("Failed to encode success response: %v", err)
	}
}

func sendErrorResponse(w http.ResponseWriter, message string, statusCode int) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)

	response := APIResponse{
		Success: false,
		Error:   message,
	}

	if err := json.NewEncoder(w).Encode(response); err != nil {
		log.Printf("Failed to encode error response: %v", err)
	}
}
