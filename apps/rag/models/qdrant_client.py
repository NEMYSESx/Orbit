from qdrant_client import QdrantClient as QdrantClientSDK
from qdrant_client.http import models
from typing import List, Dict, Any, Optional
from rag.config import settings


class MyQdrantClient:
    def __init__(
        self,
        url: str = settings.QDRANT_URL,
        api_key: str = settings.QDRANT_API_KEY,
        timeout: float = 60.0
    ):
        self.client = QdrantClientSDK(
            url=url,
            api_key=api_key,
            timeout=timeout
        )
    
    def search(
        self,
        collection_name: str,
        query_vector: List[float],
        limit: int = 10,
        filter_conditions: Optional[Dict[str, Any]] = None,
        hnsw_ef: int = 256,
        exact: bool = False,
        indexed_only: bool = True
    ) -> List[Any]:
        query_filter = None
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
            
            query_filter = models.Filter(must=must_conditions)
        
        search_params = models.SearchParams(
            hnsw_ef=hnsw_ef,
            exact=exact,
            indexed_only=indexed_only
        )
        
        return self.client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            query_filter=query_filter,
            search_params=search_params,
            limit=limit,
            with_payload=True,
            with_vectors=False
        )