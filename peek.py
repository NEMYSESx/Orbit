from confluent_kafka import Consumer, KafkaError
import json

config = {
    'bootstrap.servers': 'localhost:9092',
    'group.id': 'json-data-checker',
    'auto.offset.reset': 'earliest'
}

consumer = Consumer(config)
consumer.subscribe(['documents'])

print("Checking for messages in topic: json-data...")

msg = consumer.poll(timeout=5.0)

if msg is None:
    print("No data in topic.")
elif msg.error():
    print(f"Kafka error: {msg.error()}")
else:
    print("Data found!")
    print("Message:", json.loads(msg.value()))

consumer.close()
