from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from rag.services.rag_service import RAGService, RAGResponse
import os

rag_router = APIRouter()

rag_service = RAGService(
    collection_name="documents",
    redis_host=os.getenv('REDIS_HOST', 'redis'),
    redis_port=int(os.getenv('REDIS_PORT', 6379)),
    redis_password=os.getenv('REDIS_PASSWORD')
)

class QueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    limit: Optional[int] = 5
    score_threshold: Optional[float] = 0.6
    conversation_history_limit: Optional[int] = None  

@rag_router.post("/rag/query", response_model=RAGResponse)
async def query_rag_service(request: QueryRequest):
    try:
        result = rag_service.query(
            user_query=request.query,
            session_id=request.session_id,
            search_limit=request.limit,
            score_threshold=request.score_threshold,
            conversation_history_limit=request.conversation_history_limit
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error during RAG query processing: {str(e)}"
        )
