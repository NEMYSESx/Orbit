from fastapi import APIRouter, Depends, Query, HTTPException, Body
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from services.search_service import SearchService
from config import settings

router = APIRouter(
    prefix="/search",
    tags=["search"],
    responses={404: {"description": "Not found"}},
)

class SearchResult(BaseModel):
    id: Any
    score: float
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class TopicDetectionInfo(BaseModel):
    identified_topic: str
    confidence: float

class SearchRequest(BaseModel):
    query: str
    collection_name: Optional[str] = None
    limit: Optional[int] = 5
    gemini_api_key: Optional[str] = None
    rerank: Optional[bool] = True
    filter_conditions: Optional[Dict[str, Any]] = None
    auto_detect_topic: Optional[bool] = True

class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]
    count: int
    topic_detection: Optional[TopicDetectionInfo] = None

class SmartSearchRequest(BaseModel):
    query: str
    limit: Optional[int] = 5
    rerank: Optional[bool] = True
    gemini_api_key: Optional[str] = None

@router.post("/", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    search_service: SearchService = Depends(lambda: SearchService())
):
    """
    Search for documents in the vector database.
    
    Optionally auto-detects the most relevant collection based on the query.
    """
    topic_info = None
    
    if request.gemini_api_key:
        search_service.gemini_api_key = request.gemini_api_key
    
    try:
        if request.auto_detect_topic and not request.collection_name:
            collection_name, confidence = search_service._identify_topic_collection(request.query)
            topic_info = TopicDetectionInfo(
                identified_topic=collection_name,
                confidence=confidence
            )
            
            if confidence >= 0.4:  
                request.collection_name = collection_name
            else:
                request.collection_name = settings.DEFAULT_COLLECTION_NAME
    except Exception as e:
        print(f"Topic detection failed: {str(e)}")
        request.collection_name = settings.DEFAULT_COLLECTION_NAME
        topic_info = None
    
    results = search_service.search(
        query_text=request.query,
        collection_name=request.collection_name,
        limit=request.limit,
        rerank=request.rerank,
        filter_conditions=request.filter_conditions,
        auto_detect_topic=False  
    )
    
    formatted_results = []
    for result in results:
        metadata = {k: v for k, v in result.payload.items() if k != 'text'}
        formatted_results.append(
            SearchResult(
                id=result.id,
                score=result.score,
                text=result.payload.get('text', ''),
                metadata=metadata
            )
        )
    
    return {
        "query": request.query,
        "results": formatted_results,
        "count": len(formatted_results),
        "topic_detection": topic_info
    }

@router.post("/smart", response_model=SearchResponse)
async def smart_search(
    request: SmartSearchRequest,
    search_service: SearchService = Depends(lambda: SearchService())
):
    """
    Perform an intelligent search that automatically identifies the relevant topic/collection
    and performs a focused search within that collection.
    """
    if request.gemini_api_key:
        search_service.gemini_api_key = request.gemini_api_key
    
    try:
        smart_results = search_service.smart_search(
            user_query=request.query,
            limit=request.limit,
            rerank=request.rerank
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Smart search failed: {str(e)}")
    
    formatted_results = []
    for result in smart_results["results"]:
        metadata = {k: v for k, v in result.payload.items() if k != 'text'}
        formatted_results.append(
            SearchResult(
                id=result.id,
                score=result.score,
                text=result.payload.get('text', ''),
                metadata=metadata
            )
        )
    
    topic_info = TopicDetectionInfo(
        identified_topic=smart_results["identified_topic"],
        confidence=smart_results["topic_confidence"]
    )
    
    return {
        "query": request.query,
        "results": formatted_results,
        "count": len(formatted_results),
        "topic_detection": topic_info
    }

@router.get("/collections", response_model=List[str])
async def list_collections(
    search_service: SearchService = Depends(lambda: SearchService())
):
    """
    List all available document collections in the vector database.
    """
    try:
        collections = search_service._get_available_collections()
        return collections
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve collections: {str(e)}")