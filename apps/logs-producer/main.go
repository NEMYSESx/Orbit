package main

import (
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func main() {
	fmt.Println("Starting synthetic log generator with default settings...")
	
	go func() {
		Logs() 
	}()
	
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
	
	fmt.Println("Log generator is running... Press Ctrl+C to stop")
	fmt.Println("Logs will be generated in JSON format in the ./synthetic_logs directory")
	fmt.Println("Log types: system, network, cluster, slurm")
	
	<-sigChan
	fmt.Println("\nShutting down log generator...")
	
	time.Sleep(2 * time.Second)
	fmt.Println("Log generator stopped")
}