from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from rag.services.rag_service import RAGService, RAGResponse  

rag_router = APIRouter()

rag_service = RAGService(collection_name="documents")

class QueryRequest(BaseModel):
    query: str
    limit: Optional[int] = 5

@rag_router.post("/rag/query", response_model=RAGResponse)
async def query_rag_service(request: QueryRequest):
    try:
        result = rag_service.query(
            user_query=request.query,
            search_limit=request.limit
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during RAG query processing: {str(e)}")
