import os
import sys
import json
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from models.embeddings import EmbeddingModel
from models.qdrant_client import QdrantClientWrapper
from config import settings

class SearchService:
    """Simplified service for searching data with automatic collection selection and time prioritization."""
    
    def __init__(
        self,
        qdrant_client: Optional[QdrantClientWrapper] = None,
        embedding_model: Optional[EmbeddingModel] = None
    ):
        self.qdrant_client = qdrant_client or QdrantClientWrapper()
        self.embedding_model = embedding_model or EmbeddingModel()
    
    def search(
        self, 
        query_text: str,
        collection_name: Optional[str] = None,
        limit: int = 5,
        filter_conditions: Optional[Dict[str, Any]] = None,
        time_priority: float = 0.5
    ) -> List[Any]:
        """
        Search for documents with automatic collection selection and time prioritization.
        
        Args:
            query_text: Query text
            collection_name: Optional collection name (auto-selected if None)
            limit: Maximum number of results to return
            filter_conditions: Optional filter conditions
            time_priority: Weight for time prioritization (0-1)
            
        Returns:
            List of search results
        """
        try:
            if not collection_name:
                collection_name, confidence = self._identify_collection(query_text)
                print(f"Auto-selected collection '{collection_name}' with confidence {confidence:.2f}")
            
            query_vector = self.embedding_model.encode(query_text).tolist()
            
            search_limit = limit * 2
            
            results = self.qdrant_client.search(
                collection_name,
                query_vector,
                limit=search_limit,
                filter_conditions=filter_conditions
            )
            
            if not results:
                print("No results found")
                return []
            
            results = self._apply_time_prioritization(results, time_priority)
            
            return results[:limit]
            
        except Exception as e:
            print(f"Search error: {str(e)}")
            return []
    
    def _identify_collection(self, query_text: str) -> Tuple[str, float]:
        """
        Identify the most relevant collection for the query.
        
        Args:
            query_text: User query text
            
        Returns:
            Tuple of (collection_name, confidence_score)
        """
        collections = self._get_available_collections()
        
        if len(collections) == 1:
            return collections[0], 1.0
        
        try:
            query_vector = self.embedding_model.encode(query_text).tolist()
            best_score = -1
            best_collection = settings.DEFAULT_COLLECTION_NAME
            
            for collection in collections:
                collection_embedding = self.embedding_model.encode(f"Documents about {collection}").tolist()
                score = self._vector_similarity(query_vector, collection_embedding)
                
                if score > best_score:
                    best_score = score
                    best_collection = collection
            
            return best_collection, best_score
        except Exception as e:
            print(f"Error in collection selection: {str(e)}")
            return settings.DEFAULT_COLLECTION_NAME, 0.0
    
    def _vector_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
    
    def _get_available_collections(self) -> List[str]:
        """Get list of available collections."""
        try:
            return self.qdrant_client.list_collections()
        except Exception as e:
            print(f"Error retrieving collections: {str(e)}")
            return [settings.DEFAULT_COLLECTION_NAME]
    
    def _apply_time_prioritization(
        self,
        results: List[Any],
        time_priority: float
    ) -> List[Any]:
        """
        Apply time-based prioritization to search results using "timestamp" field.
        
        Args:
            results: Original search results
            time_priority: Weight for time priority (0-1)
            
        Returns:
            Time-prioritized results
        """
        if not results or time_priority <= 0:
            return results
            
        time_priority = max(0.0, min(1.0, time_priority))
        
        now_timestamp = int(datetime.now().timestamp())
        
        valid_timestamps = []
        for result in results:
            if "timestamp" in result.payload and isinstance(result.payload["timestamp"], (int, float)):
                valid_timestamps.append(int(result.payload["timestamp"]))
        
        if not valid_timestamps:
            return results
            
        oldest_timestamp = min(valid_timestamps)
        time_range = max(1, now_timestamp - oldest_timestamp)  
        
        rescored_results = []
        for result in results:
            recency_score = 0
            
            if "timestamp" in result.payload and isinstance(result.payload["timestamp"], (int, float)):
                timestamp = int(result.payload["timestamp"])
                recency_score = (timestamp - oldest_timestamp) / time_range
            
            combined_score = (1 - time_priority) * result.score + time_priority * recency_score
            
            result.score = combined_score
            rescored_results.append(result)
        
        rescored_results.sort(key=lambda x: x.score, reverse=True)
        return rescored_results