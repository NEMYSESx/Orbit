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
    timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class TopicInfo(BaseModel):
    collection: str
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
    selected_collection: Optional[TopicInfo] = None

@router.post("/", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    search_service: SearchService = Depends(lambda: SearchService())
):
    """
    Search for documents with automatic collection selection and time prioritization.
    
    - If collection_name is not provided, the most relevant collection is automatically selected
    - time_priority (0.0-1.0) controls the balance between relevance and recency
    - When multiple documents have similar relevance, more recent ones are prioritized using the 'timestamp' field
    """
    selected_collection = None
    collection_name = request.collection_name
    
    if not collection_name:
        collection_name, confidence = search_service._identify_collection(request.query)
        selected_collection = TopicInfo(
            collection=collection_name, 
            confidence=confidence
        )
    
    try:
        results = search_service.search(
            query_text=request.query,
            collection_name=collection_name,
            limit=request.limit,
            filter_conditions=request.filter_conditions,
            time_priority=request.time_priority
        )
        
        formatted_results = []
        for result in results:
            metadata = {k: v for k, v in result.payload.items() 
                    if k != 'text' and k != 'timestamp'}
            
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
                    timestamp=timestamp,
                    metadata=metadata
                )
            )
        
        return SearchResponse(
            query=request.query,
            results=formatted_results,
            count=len(formatted_results),
            selected_collection=selected_collection
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")