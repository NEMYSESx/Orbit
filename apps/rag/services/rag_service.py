from services.search_service import SearchService
from config import settings

import logging
import json
from typing import List, Dict, Any, Optional

from services.search_service import SearchService
from config import settings
from models.embeddings import EmbeddingModel
from models.qdrant_client import QdrantClientWrapper

logger = logging.getLogger(__name__)

class RAGService:
    """Simplified RAG service that follows a clear search -> validate -> answer flow."""
    
    def __init__(
        self,
        search_service: SearchService = None,
        gemini_api_key: Optional[str] = None
    ):
        self.gemini_api_key = gemini_api_key
        self.gemini_model = None

        if search_service:
            self.search_service = search_service
        else:
            qdrant_client = QdrantClientWrapper()
            embedding_model = EmbeddingModel()
            self.search_service = SearchService(
                qdrant_client=qdrant_client, 
                embedding_model=embedding_model
            )
    
    def initialize_gemini_model(self, api_key: Optional[str] = None):
        """Initialize the Gemini model with the provided API key."""
        import google.generativeai as genai
        
        try:
            key_to_use = api_key or self.gemini_api_key
            
            if not key_to_use:
                logger.error("No Gemini API key provided")
                return False
            
            genai.configure(api_key=key_to_use)
            
            try:
                self.gemini_model = genai.GenerativeModel('gemini-2.5-pro-preview-05-06')
            except Exception:
                self.gemini_model = genai.GenerativeModel('gemini-2.5-flash-preview-04-17')
            
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Gemini model: {str(e)}")
            return False
    
    def process_query(self, query_text: str, collections: List[str] = None) -> Dict[str, Any]:
        """
        Main entry point for processing a query through the RAG pipeline.
    
        Flow:
        1. Search for relevant documents
        2. Check if context is relevant using Gemini
        3. If relevant, use context with priority to recent documents
        4. If not relevant, let Gemini answer directly
        """
        if not collections:
            collections = [settings.DEFAULT_COLLECTION_NAME]
    
        all_documents = []
        for collection in collections:
            try:
                results = self.search_service.search(
                    query_text,
                    collection_name=collection,
                    limit=5,
                    time_priority=0.3
                )
            
                for doc in results:
                    timestamp = None
                    
                    if "timestamp" in doc.payload:
                        timestamp = doc.payload.get("timestamp")
                    elif "metadata" in doc.payload and "timestamp" in doc.payload["metadata"]:
                        timestamp = doc.payload["metadata"].get("timestamp")
                    
                    logger.debug(f"Extracted timestamp: {timestamp}, type: {type(timestamp)}")
                    
                    if isinstance(timestamp, str):
                        try:
                            timestamp = int(timestamp)
                        except (ValueError, TypeError):
                            timestamp = 0
                    
                    if timestamp is None:
                        timestamp = 0
                            
                    all_documents.append({
                        "id": doc.id,
                        "text": doc.payload.get("text", ""),
                        "score": doc.score,
                        "metadata": {k: v for k, v in doc.payload.items() if k != "text"},
                        "collection": collection,
                        "timestamp": timestamp  
                    })
            except Exception as e:
                logger.error(f"Search failed in collection {collection}: {e}")
                continue
    
        all_documents.sort(key=lambda d: d["score"], reverse=True)
    
        all_documents.sort(key=lambda d: 0 if d["timestamp"] is None else -int(d["timestamp"]))
    
        top_documents = all_documents[:5]
    
        context = ""
        if top_documents:
            context_parts = []
            for i, doc in enumerate(top_documents):
                timestamp_display = "N/A"
                if doc["timestamp"] is not None and doc["timestamp"] > 0:
                    try:
                        from datetime import datetime
                        timestamp_display = f"{doc['timestamp']} ({datetime.fromtimestamp(doc['timestamp']).strftime('%Y-%m-%d %H:%M:%S')})"
                    except (ValueError, TypeError, OverflowError):
                        timestamp_display = str(doc["timestamp"])
                        
                context_parts.append(f"Document {i+1} (Score: {doc['score']:.2f}, Timestamp: {timestamp_display}):\n{doc['text']}")
            
            context = "\n\n".join(context_parts)
    
        has_relevant_context = False
        if top_documents:
            if top_documents[0]["score"] > 0.85:
                has_relevant_context = True
            else:
                relevance_check = self._check_context_relevance(query_text, top_documents)
                has_relevant_context = relevance_check.get("is_relevant", False)
    
        if has_relevant_context:
            answer = self._generate_answer_from_context(query_text, context)
            source = "documents"
        else:
            answer = self._generate_answer_from_knowledge(query_text)
            source = "gemini_knowledge"
    
        return {
            "question": query_text,
            "answer": answer,
            "source": source,
            "supporting_documents": top_documents if has_relevant_context else None,
            "collections_searched": collections
        }
    
    def _check_context_relevance(self, query_text: str, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Check if the retrieved documents are relevant to the query.
        
        Args:
            query_text: User's question
            documents: Retrieved documents
            
        Returns:
            Dictionary with relevance assessment
        """
        if not self.gemini_model and not self.initialize_gemini_model():
            return {"is_relevant": documents and documents[0]["score"] > 0.7}
        
        try:
            context_parts = []
            for i, doc in enumerate(documents[:3]):  
                context_parts.append(f"Document {i+1} (Score: {doc['score']:.2f}):\n{doc['text']}\n")
            
            context = "\n".join(context_parts)
            
            prompt = f"""
            Analyze whether the following retrieved documents are relevant to answering the user's query.
            
            User query: "{query_text}"
            
            Retrieved documents:
            {context}
            
            Respond with a JSON object containing:
            {{
                "is_relevant": true/false,
                "explanation": "brief explanation of your assessment"
            }}
            """
            
            response = self.gemini_model.generate_content(prompt)
            response_text = response.text.strip()
            
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            
            return {"is_relevant": documents and documents[0]["score"] > 0.7}
        except Exception as e:
            logger.error(f"Error in context relevance check: {e}")
            return {"is_relevant": documents and documents[0]["score"] > 0.7}
    
    def _generate_answer_from_context(self, query_text: str, context: str) -> str:
        """
        Generate an answer using the retrieved context and Gemini's knowledge.

        Args:
            query_text: User's question
            context: Retrieved context from documents

        Returns:
            Generated answer
        """
        if not self.gemini_model and not self.initialize_gemini_model():
            return "I couldn't process your query due to configuration issues."

        try:
            prompt = f"""
            You are an AI assistant designed to answer questions comprehensively.
            Use the provided context from documents as your primary source for specific details, facts, and recent information.
            Supplement your answer with your general knowledge where necessary to provide a complete and helpful response.

            Question: {query_text}

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

            response = self.gemini_model.generate_content(prompt)
            if response and response.text:
                return response.text.strip()
            else:
                logger.warning(f"Gemini returned no text content for query: {query_text}")
                return "I couldn't generate a text answer based on the provided context."
        except Exception as e:
            logger.error(f"Error generating answer from context: {e}")
            return "I encountered an error while processing your question."
    
    def _generate_answer_from_knowledge(self, query_text: str) -> str:
        """
        Generate an answer using Gemini's knowledge.
        
        Args:
            query_text: User's question
            
        Returns:
            Generated answer
        """
        if not self.gemini_model and not self.initialize_gemini_model():
            return "I couldn't process your query due to configuration issues."
        
        try:
            prompt = f"""
            The user has asked: "{query_text}"
            
            Please provide a helpful, accurate, and concise answer based on your knowledge.
            """
            
            response = self.gemini_model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Error generating answer from knowledge: {e}")
            return "I encountered an error while processing your question."