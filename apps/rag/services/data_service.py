import os
import sys
import time
from typing import List, Dict, Any, Optional
from tqdm import tqdm

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from models.chunker import AgenticChunker
from models.embeddings import EmbeddingModel
from models.qdrant_client import QdrantClientWrapper
from qdrant_client.http import models
from config import settings

class DataService:
    
    def __init__(
        self,
        qdrant_client: QdrantClientWrapper = None,
        embedding_model: EmbeddingModel = None,
        chunker: AgenticChunker = None
    ):
        self.qdrant_client = qdrant_client or QdrantClientWrapper()
        self.embedding_model = embedding_model or EmbeddingModel()
        self.chunker = chunker
        
    def initialize_chunker(self, gemini_api_key: Optional[str] = None) -> AgenticChunker:
        """Initialize the document chunker if not already initialized."""
        if self.chunker is None:
            self.chunker = AgenticChunker(gemini_api_key=gemini_api_key)
        return self.chunker
    
    def push_data(
        self,
        data: List[Dict[str, Any]],
        collection_name: str,
        use_chunking: bool = True,
        gemini_api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Push data to Qdrant with timestamp support."""
        if use_chunking:
            self.initialize_chunker(gemini_api_key)
        
        vector_size = self.embedding_model.get_vector_size()
        print(f"Using model '{self.embedding_model.model_name}' with vector size: {vector_size}")
        
        if self.qdrant_client.collection_exists(collection_name):
            print(f"Collection '{collection_name}' already exists.")
        else:
            print(f"Creating collection '{collection_name}' with vector size {vector_size}...")
            self.qdrant_client.create_collection(collection_name, vector_size)
            print(f"Collection '{collection_name}' created successfully.")
        
        print(f"Preparing embeddings for {len(data)} items...")
        points = []
        
        for item_idx, item in enumerate(tqdm(data)):
            timestamp = int(time.time())
            
            text = item.get("text", "")
            if not text.strip():
                print(f"Skipping item {item_idx} - empty text")
                continue
            
            metadata = item.get("metadata", {}).copy()
            metadata["timestamp"] = timestamp
            
            processed_items = []
            if use_chunking and self.chunker and len(text) > settings.DEFAULT_CHUNK_SIZE:
                chunks = self.chunker.chunk_text(text, metadata)
                for i, chunk in enumerate(chunks):
                    original_id = item.get('id', item_idx)
                    if isinstance(original_id, str) and original_id.isdigit():
                        original_id = int(original_id)
        
                    chunk_id = int(f"{original_id}{i:03d}")
                    
                    chunk_metadata = {
                        **chunk["metadata"],
                        "parent_id": original_id,
                        "chunk_index": i,
                        "original_text_length": len(text)
                    }
        
                    chunk_item = {
                        "id": chunk_id,
                        "text": chunk["text"],
                        "metadata": chunk_metadata
                    }
                    processed_items.append(chunk_item)
            else:
                item_id = item.get("id", item_idx)
                if isinstance(item_id, str) and item_id.isdigit():
                    item_id = int(item_id)
    
                processed_items.append({
                    "id": item_id,
                    "text": text,
                    "metadata": metadata  
                })
            
            for proc_item in processed_items:
                item_text = proc_item["text"]
                embedding = self.embedding_model.encode(item_text)
                
                point_id = proc_item["id"]
                if isinstance(point_id, str) and point_id.isdigit():
                    point_id = int(point_id)
                
                point = models.PointStruct(
                    id=point_id,
                    vector=embedding.tolist(),
                    payload={
                        "text": item_text,
                        **proc_item.get("metadata", {})
                    }
                )
                points.append(point)
        
        print(f"Uploading {len(points)} points to collection '{collection_name}'...")
        
        points_uploaded = self.qdrant_client.upsert_points(collection_name, points)
        
        print(f"Successfully uploaded {points_uploaded} points to '{collection_name}'")
        return {"status": "success", "points_uploaded": points_uploaded}