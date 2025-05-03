from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from services.rag_service import RAGService
from config import settings

router = APIRouter(
    prefix="/rag",
    tags=["rag"],
    responses={404: {"description": "Not found"}},
)

class Document(BaseModel):
    id: Any
    text: str
    score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)

class RAGRequest(BaseModel):
    query: str
    collection_name: Optional[str] = settings.DEFAULT_COLLECTION_NAME
    gemini_api_key: Optional[str] = None
    k: Optional[int] = 3
    expand_with_model_knowledge: Optional[bool] = True
    filter_conditions: Optional[Dict[str, Any]] = None

class RAGResponse(BaseModel):
    question: str
    answer: str
    retrieved_documents: List[Document]
    used_model_knowledge: bool
    error: Optional[str] = None

@router.post("/answer", response_model=RAGResponse)
async def retrieve_and_answer(
    request: RAGRequest,
    rag_service: RAGService = Depends(lambda: RAGService())
):
    """
    Perform retrieval-augmented generation to answer a question.
    """
    try:
        result = rag_service.retrieve_and_answer(
            query_text=request.query,
            collection_name=request.collection_name,
            gemini_api_key=request.gemini_api_key,
            k=request.k,
            expand_with_model_knowledge=request.expand_with_model_knowledge,
            filter_conditions=request.filter_conditions
        )
        documents = []
        retrieved_documents = result.get("retrieved_documents", [])
        for doc in retrieved_documents:
            document = Document(
            id=doc["id"],
            text=doc["text"],
            score=doc["score"],
            metadata=doc["metadata"]
        )
        documents.append(document)
            
        return {
            "question": result["question"],
            "answer": result["answer"],
            "retrieved_documents": documents,
            "used_model_knowledge": result["used_model_knowledge"],
            "error": result.get("error")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))