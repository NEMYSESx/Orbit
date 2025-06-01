import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from models.embeddings import EmbeddingModel
from models.qdrant_client import QdrantClientWrapper
from config import settings

class SearchService:
    
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
        try:
            if not collection_name:
                relevant_collections = self._identify_relevant_collections(query_text)
                if not relevant_collections:
                    print("No relevant collections found for the query")
                    return []
                
                all_results = []
                for collection, confidence in relevant_collections:
                    try:
                        collection_results = self._search_single_collection(
                            collection,
                            query_text,
                            limit,
                            filter_conditions
                        )
                        for result in collection_results:
                            result.score *= confidence
                        all_results.extend(collection_results)
                    except Exception as e:
                        print(f"Error searching collection {collection}: {str(e)}")
                        continue
                
                all_results.sort(key=lambda x: x.score, reverse=True)
                results = all_results[:limit]
                
            else:
                results = self._search_single_collection(
                    collection_name,
                    query_text,
                    limit,
                    filter_conditions
                )
            
            if not results:
                print("No results found")
                return []
            
            results = self._apply_time_prioritization(results, time_priority)
            return results[:limit]
            
        except Exception as e:
            print(f"Search error: {str(e)}")
            return []
    
    def _search_single_collection(
        self,
        collection_name: str,
        query_text: str,
        limit: int,
        filter_conditions: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        query_vector = self.embedding_model.encode(query_text).tolist()
        
        return self.qdrant_client.search(
            collection_name,
            query_vector,
            limit=limit,
            filter_conditions=filter_conditions
        )
    
    def _identify_relevant_collections(self, query_text: str) -> List[Tuple[str, float]]:
        collections = self._get_available_collections()
        if not collections:
            return []
        
        if len(collections) == 1:
            return [(collections[0], 1.0)]
        
        try:
            query_vector = self.embedding_model.encode(query_text).tolist()
            collection_scores = []
            
            for collection in collections:
                collection_desc = f"Documents about {collection}"
                collection_embedding = self.embedding_model.encode(collection_desc).tolist()
                score = self._vector_similarity(query_vector, collection_embedding)
                
                if score >= settings.COLLECTION_SIMILARITY_THRESHOLD:
                    collection_scores.append((collection, score))
            
            collection_scores.sort(key=lambda x: x[1], reverse=True)
            return collection_scores
            
        except Exception as e:
            print(f"Error in collection selection: {str(e)}")
            return []
    
    def _vector_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
    
    def _get_available_collections(self) -> List[str]:
        try:
            return self.qdrant_client.list_collections()
        except Exception as e:
            print(f"Error retrieving collections: {str(e)}")
            return []
    
    def _apply_time_prioritization(
        self,
        results: List[Any],
        time_priority: float
    ) -> List[Any]:
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