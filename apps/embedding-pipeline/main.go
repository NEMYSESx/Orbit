package main

import (
	"fmt"
	"os"
	"os/signal"

	"github.com/confluentinc/confluent-kafka-go/kafka"
)

func main(){
	c,err := kafka.NewConsumer(&kafka.ConfigMap{
		"bootstrap.servers": "localhost:9092",
		"group.id":          "my-group",
		"auto.offset.reset": "earliest",
	})

	if err != nil{
		fmt.Printf("getting error in consuming the data %v",err)
	}

	c.SubscribeTopics([]string{"documents"},nil)

	fmt.Printf("kafka consumer started...")

	sigchan := make(chan os.Signal, 1)
	signal.Notify(sigchan, os.Interrupt)

runLoop:
	for {
		select {
		case <-sigchan:
			fmt.Println("\n🛑 Interrupt received, exiting...")
			break runLoop

		default:
			// Wait for new message
			msg, err := c.ReadMessage(-1) // -1 = no timeout
			if err == nil {
				fmt.Printf("📥 Message received: %s\n", string(msg.Value))
			} else {
				fmt.Printf("⚠️ Error while reading message: %v\n", err)
			}
		}
	}
}