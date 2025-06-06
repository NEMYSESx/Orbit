from qdrant_client import QdrantClient
from qdrant_client.http import models
from typing import List, Dict, Any, Optional
from rag.config import settings

class SimpleQdrantClient:
    def __init__(
        self, 
        url: str = settings.QDRANT_URL, 
        api_key: str = settings.QDRANT_API_KEY
    ):
        self.client = QdrantClient(url=url, api_key=api_key)
    
    def search(
        self, 
        collection_name: str, 
        query_vector: List[float], 
        limit: int = 10,
        filter_conditions: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        search_params = {
            "collection_name": collection_name,
            "query_vector": query_vector,
            "limit": limit,
            "with_payload": True,
            "with_vectors": False
        }
        
        if filter_conditions:
            must_conditions = []
            for key, value in filter_conditions.items():
                if isinstance(value, list):
                    must_conditions.append(
                        models.FieldCondition(
                            key=key,
                            match=models.MatchAny(any=value)
                        )
                    )
                else:
                    must_conditions.append(
                        models.FieldCondition(
                            key=key,
                            match=models.MatchValue(value=value)
                        )
                    )
            
            search_params["query_filter"] = models.Filter(must=must_conditions)
        
        return self.client.search(**search_params)