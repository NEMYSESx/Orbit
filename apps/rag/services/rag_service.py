from services.search_service import SearchService
from config import settings

import logging
import json
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAI

from services.search_service import SearchService
from config import settings
from models.embeddings import EmbeddingModel
from models.qdrant_client import QdrantClientWrapper

logger = logging.getLogger(__name__)


class QdrantVectorStoreWrapper(VectorStore):
    
    def __init__(self, search_service: SearchService):
        self.search_service = search_service
    
    @classmethod
    def from_texts(
        cls,
        texts: List[str],
        embedding: Embeddings,
        metadatas: Optional[List[dict]] = None,
        **kwargs: Any
    ) -> "QdrantVectorStoreWrapper":
        """Create a Qdrant vector store from texts."""
        search_service = kwargs.get('search_service')
        if not search_service:
            raise ValueError("search_service must be provided")
        
        return cls(search_service)
    
    def similarity_search(
        self, 
        query: str, 
        k: int = 5, 
        collection_name: str = None,
        **kwargs
    ) -> List[Document]:
        try:
            results = self.search_service.search(
                query_text=query,
                collection_name=collection_name,
                limit=k,
                time_priority=kwargs.get('time_priority', 0.3)
            )
            
            documents = []
            for doc in results:
                timestamp = None
                if "timestamp" in doc.payload:
                    timestamp = doc.payload.get("timestamp")
                elif "metadata" in doc.payload and "timestamp" in doc.payload["metadata"]:
                    timestamp = doc.payload["metadata"].get("timestamp")
                
                if isinstance(timestamp, str):
                    try:
                        timestamp = int(timestamp)
                    except (ValueError, TypeError):
                        timestamp = 0
                
                if timestamp is None:
                    timestamp = 0
                
                metadata = {k: v for k, v in doc.payload.items() if k != "text"}
                metadata.update({
                    "id": doc.id,
                    "score": doc.score,
                    "timestamp": timestamp,
                    "collection": collection_name or settings.DEFAULT_COLLECTION_NAME
                })
                
                documents.append(Document(
                    page_content=doc.payload.get("text", ""),
                    metadata=metadata
                ))
            
            return documents
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

class RAGService:    
    def __init__(
        self,
        search_service: SearchService = None,
        gemini_api_key: Optional[str] = None
    ):
        self.gemini_api_key = gemini_api_key
        self.search_service = None
        
        if search_service:
            self.search_service = search_service
        else:
            qdrant_client = QdrantClientWrapper()
            embedding_model = EmbeddingModel(
                model_name=settings.EMBEDDING_MODEL,
                output_dimensionality=settings.EMBEDDING_DIMENSIONALITY
            )
            self.search_service = SearchService(
                qdrant_client=qdrant_client, 
                embedding_model=embedding_model
            )
        
        self.vector_store = None
        self.llm = None
        self.context_answer_prompt = None
        self.json_parser = None
        
        self._setup_langchain_components()
    
    def _setup_langchain_components(self):
        """Initialize LangChain components"""
        try:
            self.llm = GoogleGenerativeAI(
                model="gemini-2.5-pro-preview-05-06",
                google_api_key=self.gemini_api_key,
                temperature=0.1
            ) if self.gemini_api_key else None
            
            self.vector_store = QdrantVectorStoreWrapper(self.search_service)
            
            self.context_answer_prompt = PromptTemplate(
                input_variables=["query", "context"],
                template="""
                You are an AI assistant designed to answer questions comprehensively.
                Use the provided context from documents as your primary source for specific details, facts, and recent information.
                Supplement your answer with your general knowledge where necessary to provide a complete and helpful response.

                Question: {query}

                Context from Documents:
                {context}

                IMPORTANT INSTRUCTIONS:
                1. Use information from the 'Context from Documents' first, especially for specific details directly related to the question.
                2. If the context doesn't fully answer the question or provides only partial information, use your general knowledge to complete the answer.
                3. Do not invent information and present it as coming from the 'Context from Documents' if it is not there.
                4. Documents within the context are sorted by most recent timestamp first.
                5. ALWAYS prioritize information from documents with the most recent timestamps when information differs within the provided context.
                6. The most recent information (highest timestamp value) within the context should be considered the most accurate for details from the documents.
                7. Aim for a helpful and informative answer, combining the specific details from the context with relevant general knowledge.
                """
            )
            
            self.knowledge_answer_prompt = PromptTemplate(
                input_variables=["query"],
                template="""
                The user has asked: "{query}"
                
                Please provide a helpful, accurate, and concise answer based on your knowledge.
                """
            )
            
            self.relevance_check_prompt = PromptTemplate(
                input_variables=["query", "context"],
                template="""
                Analyze whether the following retrieved documents are relevant to answering the user's query.
                
                User query: "{query}"
                
                Retrieved documents:
                {context}
                
                Respond with a JSON object containing:
                {{
                    "is_relevant": true/false,
                    "explanation": "brief explanation of your assessment"
                }}
                """
            )
            
            self.json_parser = JsonOutputParser()
            
            self._setup_chains()
            
        except Exception as e:
            logger.error(f"Failed to setup LangChain components: {e}")
            self.llm = None
    
    def _setup_chains(self):
        """Setup LangChain chains"""
        if not self.llm:
            return
        
        self.context_chain = (
            self.context_answer_prompt 
            | self.llm
        )
        
        self.knowledge_chain = (
            self.knowledge_answer_prompt 
            | self.llm
        )
        
        self.relevance_chain = (
            self.relevance_check_prompt 
            | self.llm
        )
    
    def initialize_gemini_model(self, api_key: Optional[str] = None):
        try:
            key_to_use = api_key or self.gemini_api_key
            
            if not key_to_use:
                logger.error("No Gemini API key provided")
                return False
            
            try:
                self.llm = GoogleGenerativeAI(
                    model="gemini-2.5-pro-preview-05-06",
                    google_api_key=key_to_use,
                    temperature=0.1
                )
            except Exception:
                self.llm = GoogleGenerativeAI(
                    model="gemini-2.5-flash-preview-04-17",
                    google_api_key=key_to_use,
                    temperature=0.1
                )
            
            self._setup_chains()
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Gemini model: {str(e)}")
            return False
    
    def process_query(self, query_text: str, collections: List[str] = None) -> Dict[str, Any]:
        if not collections:
            collections = [settings.DEFAULT_COLLECTION_NAME]
    
        all_documents = []
        for collection in collections:
            try:
                docs = self.vector_store.similarity_search(
                    query_text,
                    k=5,
                    collection_name=collection,
                    time_priority=0.3
                )
                
                for doc in docs:
                    all_documents.append({
                        "id": doc.metadata.get("id"),
                        "text": doc.page_content,
                        "score": doc.metadata.get("score", 0),
                        "metadata": {k: v for k, v in doc.metadata.items() 
                                   if k not in ["id", "score", "timestamp", "collection"]},
                        "collection": doc.metadata.get("collection", collection),
                        "timestamp": doc.metadata.get("timestamp", 0)
                    })
                    
            except Exception as e:
                logger.error(f"Search failed in collection {collection}: {e}")
                continue
    
        all_documents.sort(key=lambda d: d["score"], reverse=True)
        all_documents.sort(key=lambda d: 0 if d["timestamp"] is None else -int(d["timestamp"]))
        top_documents = all_documents[:5]
    
        context = self._format_context(top_documents)
    
        has_relevant_context = self._check_context_relevance_langchain(query_text, top_documents)
    
        if has_relevant_context:
            answer = self._generate_answer_from_context_langchain(query_text, context)
            source = "documents"
        else:
            answer = self._generate_answer_from_knowledge_langchain(query_text)
            source = "gemini_knowledge"
    
        return {
            "question": query_text,
            "answer": answer,
            "source": source,
            "supporting_documents": top_documents if has_relevant_context else None,
            "collections_searched": collections
        }
    
    def _format_context(self, documents: List[Dict[str, Any]]) -> str:
        """Format documents into context string"""
        if not documents:
            return ""
        
        context_parts = []
        for i, doc in enumerate(documents):
            timestamp_display = "N/A"
            if doc["timestamp"] is not None and doc["timestamp"] > 0:
                try:
                    timestamp_display = f"{doc['timestamp']} ({datetime.fromtimestamp(doc['timestamp']).strftime('%Y-%m-%d %H:%M:%S')})"
                except (ValueError, TypeError, OverflowError):
                    timestamp_display = str(doc["timestamp"])
                    
            context_parts.append(
                f"Document {i+1} (Score: {doc['score']:.2f}, Timestamp: {timestamp_display}):\n{doc['text']}"
            )
        
        return "\n\n".join(context_parts)
    
    def _check_context_relevance_langchain(self, query_text: str, documents: List[Dict[str, Any]]) -> bool:
        if not self.llm or not hasattr(self, 'relevance_chain'):
            return documents and documents[0]["score"] > 0.7
        
        try:
            context_parts = []
            for i, doc in enumerate(documents[:3]):
                context_parts.append(f"Document {i+1} (Score: {doc['score']:.2f}):\n{doc['text']}\n")
            
            context = "\n".join(context_parts)
            
            response = self.relevance_chain.invoke({
                "query": query_text,
                "context": context
            })
            
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))
                return result.get("is_relevant", False)
            
            return documents and documents[0]["score"] > 0.7
            
        except Exception as e:
            logger.error(f"Error in LangChain context relevance check: {e}")
            return documents and documents[0]["score"] > 0.7
    
    def _generate_answer_from_context_langchain(self, query_text: str, context: str) -> str:
        if not self.llm or not hasattr(self, 'context_chain'):
            return "I couldn't process your query due to configuration issues."

        try:
            response = self.context_chain.invoke({
                "query": query_text,
                "context": context
            })
            return response.strip() if response else "I couldn't generate a text answer based on the provided context."
            
        except Exception as e:
            logger.error(f"Error generating answer from context with LangChain: {e}")
            return "I encountered an error while processing your question."
    
    def _generate_answer_from_knowledge_langchain(self, query_text: str) -> str:
        if not self.llm or not hasattr(self, 'knowledge_chain'):
            return "I couldn't process your query due to configuration issues."
        
        try:
            response = self.knowledge_chain.invoke({"query": query_text})
            return response.strip() if response else "I couldn't generate an answer."
            
        except Exception as e:
            logger.error(f"Error generating answer from knowledge with LangChain: {e}")
            return "I encountered an error while processing your question."
    
    def _check_context_relevance(self, query_text: str, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        is_relevant = self._check_context_relevance_langchain(query_text, documents)
        return {"is_relevant": is_relevant, "explanation": "Processed with LangChain"}
    
    def _generate_answer_from_context(self, query_text: str, context: str) -> str:
        return self._generate_answer_from_context_langchain(query_text, context)
    
    def _generate_answer_from_knowledge(self, query_text: str) -> str:
        return self._generate_answer_from_knowledge_langchain(query_text)