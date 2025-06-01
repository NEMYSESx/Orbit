from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

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

class TopicDetectionInfo(BaseModel):
    identified_topic: str
    confidence: float

class QueryRequest(BaseModel):
    query: str
    gemini_api_key: str
    similarity_threshold: Optional[float] = 0.7
    collections_to_search: Optional[List[str]] = None
    auto_detect_topic: Optional[bool] = True

class QueryResponse(BaseModel):
    question: str
    answer: str
    source: str 
    confidence: float
    supporting_documents: Optional[List[Document]] = None
    collections_searched: List[str]
    topic_detection: Optional[List[TopicDetectionInfo]] = None 

@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    try:
        rag_service = RAGService(gemini_api_key=request.gemini_api_key)
        
        if not rag_service.initialize_gemini_model():
            return {
                "question": request.query,
                "answer": "Invalid Gemini API key. Please check it.",
                "source": "error",
                "confidence": 0.0,
                "supporting_documents": None,
                "collections_searched": [],
                "topic_detection": None
            }
        
        topic_info = []
        collections = request.collections_to_search or []
        
        if request.auto_detect_topic and not collections:
            try:
                relevant_collections = rag_service.search_service._identify_relevant_collections(request.query)
                
                if relevant_collections:
                    collections = []
                    for collection, confidence in relevant_collections:
                        if confidence >= request.similarity_threshold:
                            collections.append(collection)
                            topic_info.append(TopicDetectionInfo(
                                identified_topic=collection,
                                confidence=confidence
                            ))
                
                if not collections:
                    collections = rag_service.search_service._get_available_collections()
                    
            except Exception as e:
                print(f"Error in topic detection: {str(e)}")
                collections = rag_service.search_service._get_available_collections()
        elif not collections:
            collections = rag_service.search_service._get_available_collections()
        
        if not collections:
            return {
                "question": request.query,
                "answer": "No collections available to search. Please index some documents first.",
                "source": "error",
                "confidence": 0.0,
                "supporting_documents": None,
                "collections_searched": [],
                "topic_detection": topic_info
            }
        
        result = rag_service.process_query(request.query, collections)
        
        supporting_docs = None
        if result.get("supporting_documents"):
            supporting_docs = [
                Document(
                    id=doc["id"],
                    text=doc["text"],
                    score=doc["score"],
                    metadata=doc["metadata"]
                ) for doc in result["supporting_documents"]
            ]
        
        confidence = 0.9 if result["source"] == "documents" else 0.7
        
        return {
            "question": request.query,
            "answer": result["answer"],
            "source": result["source"],
            "confidence": confidence,
            "supporting_documents": supporting_docs,
            "collections_searched": result["collections_searched"],
            "topic_detection": topic_info
        }
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")