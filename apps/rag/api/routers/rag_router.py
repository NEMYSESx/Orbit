from fastapi import APIRouter, Depends, HTTPException, Body
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import logging

from services.rag_service import RAGService
from services.search_service import SearchService
from config import settings

logger = logging.getLogger(__name__)

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
    topic_detection: Optional[TopicDetectionInfo] = None

@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """
    New flow:
    1. Search documents for every query
    2. Let Gemini decide if the context is relevant
    3. Generate an answer from context, hybrid, or fallback to LLM
    4. Use assess_query_type() optionally to tune tone or detect personal queries
    """
    try:
        gemini_api_key = request.gemini_api_key
        rag_service = RAGService(gemini_api_key=gemini_api_key)

        if gemini_api_key:
            logger.info("Initializing Gemini model with provided API key")
            if not rag_service.initialize_gemini_model(api_key=gemini_api_key):
                logger.warning("Invalid Gemini API key")
                return {
                    "question": request.query,
                    "answer": "Invalid Gemini API key. Please check it.",
                    "source": "error",
                    "confidence": 0.0,
                    "supporting_documents": None,
                    "collections_searched": [],
                    "topic_detection": None
                }

        topic_info = None
        collections = request.collections_to_search or []
        search_service = SearchService(gemini_api_key=gemini_api_key) 
        if request.auto_detect_topic and not collections:
            try:
                topic, confidence = search_service._identify_topic_collection(request.query)
                topic_info = TopicDetectionInfo(identified_topic=topic, confidence=confidence)
                collections = [topic] if confidence >= 0.4 else [settings.DEFAULT_COLLECTION_NAME]
            except Exception as e:
                logger.error(f"Topic detection failed: {str(e)}")
                collections = [settings.DEFAULT_COLLECTION_NAME]
        elif not collections:
            collections = [settings.DEFAULT_COLLECTION_NAME]

        logger.info(f"Searching in collections: {collections}")
        all_documents = []
        for collection in collections:
            try:
                results = search_service.search(
                    request.query,
                    collection_name=collection,
                    limit=10,
                    rerank=bool(gemini_api_key)
                )
                for doc in results:
                    if doc.score >= request.similarity_threshold:
                        all_documents.append({
                            "id": doc.id,
                            "text": doc.payload.get("text", ""),
                            "score": doc.score,
                            "metadata": {k: v for k, v in doc.payload.items() if k != "text"},
                            "collection": collection
                        })
            except Exception as e:
                logger.error(f"Search failed in collection {collection}: {e}")
                continue

        all_documents.sort(key=lambda d: d["score"], reverse=True)
        logger.info(f"Total relevant documents found: {len(all_documents)}")

        context = ""
        if all_documents:
            context = "\n\n".join(
                [f"Document {i+1} (Score: {doc['score']:.2f}):\n{doc['text']}" for i, doc in enumerate(all_documents[:5])]
            )

        if rag_service.gemini_model:
            decision = rag_service.let_gemini_decide(
                query_text=request.query,
                retrieved_documents=all_documents[:5]
            )
            logger.info(f"Gemini decision: {decision}")
        else:
            decision = {
                "decision": "use_documents" if all_documents and all_documents[0]["score"] > 0.8 else "use_hybrid",
                "confidence": "medium",
                "explanation": "Fallback decision"
            }

        if rag_service.gemini_model:
            if decision["decision"] == "use_documents":
                answer = rag_service.generate_answer_from_context(
                    query_text=request.query,
                    context=context
                )
            elif decision["decision"] == "use_hybrid":
                answer = rag_service.generate_answer_from_context(
                    query_text=request.query,
                    context=context
                )
            else:
                answer = rag_service.generate_answer_from_knowledge(
                    query_text=request.query
                )

        else:
            if all_documents:
                answer = f"Here is some relevant information I found:\n\n{all_documents[0]['text']}"
            else:
                answer = "I couldn't find any relevant information, and Gemini is not available."

        assessment = rag_service.assess_query_type(request.query)
        logger.info(f"Query assessment: {assessment}")

        return {
            "question": request.query,
            "answer": answer,
            "source": decision["decision"],
            "confidence": 0.9 if decision.get("confidence") == "high" else 0.8,
            "supporting_documents": [
                Document(
                    id=doc["id"],
                    text=doc["text"],
                    score=doc["score"],
                    metadata=doc["metadata"]
                ) for doc in all_documents[:5]
            ] if all_documents else None,
            "collections_searched": collections,
            "topic_detection": topic_info
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@router.get("/collections", response_model=List[str])
async def list_rag_collections(
    rag_service: RAGService = Depends(lambda: RAGService())
):
    """
    List all available document collections for RAG.
    """
    try:
        collections = rag_service._get_available_collections()
        return collections
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve collections: {str(e)}")

@router.post("/smart-search", response_model=Dict[str, Any])
async def smart_search(
    request: QueryRequest,
    rag_service: RAGService = Depends(lambda: RAGService())
):
    """
    Perform a smart search across collections using topic detection
    and return the results with the detected topic.
    """
    try:
        if request.gemini_api_key:
            rag_service.gemini_api_key = request.gemini_api_key
            rag_service.initialize_gemini_model(api_key=request.gemini_api_key)
        
        result = rag_service.smart_search_and_answer(
            query_text=request.query,
            similarity_threshold=request.similarity_threshold or 0.7,
            max_results=5
        )
        
        response = {
            "question": request.query,
            "answer": result["answer"],
            "source": "documents" if result.get("used_retrieval") else "llm_knowledge",
            "confidence": 0.8 if result.get("used_retrieval") else 0.7,
            "supporting_documents": [
                Document(
                    id=doc["id"],
                    text=doc["text"],
                    score=doc["score"],
                    metadata=doc["metadata"]
                ) for doc in result.get("results", [])
            ] if result.get("results") else None,
            "collections_searched": [result.get("identified_topic", settings.DEFAULT_COLLECTION_NAME)],
            "topic_detection": TopicDetectionInfo(
                identified_topic=result.get("identified_topic", "unknown"),
                confidence=result.get("topic_confidence", 0.0)
            ) if "identified_topic" in result else None
        }
        
        return response
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Smart search failed: {str(e)}")