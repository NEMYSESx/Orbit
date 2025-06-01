from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from services.search_service import SearchService

router = APIRouter(
    prefix="/search",
    tags=["search"],
    responses={404: {"description": "Not found"}}
)

class SearchResult(BaseModel):
    id: Any
    score: float
    text: str
    collection: str  
    timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class CollectionInfo(BaseModel):
    name: str
    confidence: float

class SearchRequest(BaseModel):
    query: str
    collection_name: Optional[str] = None  
    limit: Optional[int] = 5
    filter_conditions: Optional[Dict[str, Any]] = None
    time_priority: Optional[float] = 0.5  

class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]
    count: int
    relevant_collections: List[CollectionInfo]  

@router.post("/", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    search_service: SearchService = Depends(lambda: SearchService())
):
    try:
        relevant_collections = []
        if not request.collection_name:
            collection_scores = search_service._identify_relevant_collections(request.query)
            relevant_collections = [
                CollectionInfo(name=name, confidence=score)
                for name, score in collection_scores
            ]
        
        results = search_service.search(
            query_text=request.query,
            collection_name=request.collection_name,
            limit=request.limit,
            filter_conditions=request.filter_conditions,
            time_priority=request.time_priority
        )
        
        formatted_results = []
        for result in results:
            metadata = {k: v for k, v in result.payload.items() 
                    if k not in ['text', 'timestamp', 'collection']}
            
            timestamp = None
            if "timestamp" in result.payload:
                timestamp_value = result.payload["timestamp"]
                if isinstance(timestamp_value, (int, float)):
                    timestamp = datetime.fromtimestamp(timestamp_value)
            
            formatted_results.append(
                SearchResult(
                    id=result.id,
                    score=result.score,
                    text=result.payload.get('text', ''),
                    collection=result.payload.get('collection', request.collection_name or 'unknown'),
                    timestamp=timestamp,
                    metadata=metadata
                )
            )
        
        return SearchResponse(
            query=request.query,
            results=formatted_results,
            count=len(formatted_results),
            relevant_collections=relevant_collections
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@router.get("/collections")
async def list_collections(
    search_service: SearchService = Depends(lambda: SearchService())
):
    """List all available collections."""
    try:
        collections = search_service._get_available_collections()
        return {"collections": collections}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list collections: {str(e)}")