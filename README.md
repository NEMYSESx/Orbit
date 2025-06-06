# Orbit Setup Guide

## Architecture Overview
The application consists of the following services:

- **Apache Tika** – Document text extraction service  
- **Apache Kafka** – Message streaming platform  
- **Ingestion Pipeline** – Processes and ingests documents  
- **Embedding Pipeline** – Generates text embeddings  
- **RAG API** – Retrieval-Augmented Generation service  
- **Chat Backend** – Main application backend  
- **Chat Frontend** – React-based user interface  

## Setup

```bash
git clone https://github.com/NEMYSESx/Orbit
cd Orbit
```

## Build and Start Services

```bash
docker-compose up --build
docker-compose up -d
```

## Demo
 [Download or view the demo video](demo.mp4)

