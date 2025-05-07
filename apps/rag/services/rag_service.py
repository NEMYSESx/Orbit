import logging
from typing import Dict, Any, Optional, List, Tuple
import google.generativeai as genai
import json
import re

from models.qdrant_client import QdrantClientWrapper
from models.embeddings import EmbeddingModel
from services.search_service import SearchService


logger = logging.getLogger(__name__)

class RAGService:
    """Service for smart searching across collections and generating answers."""
    
    def __init__(
        self,
        search_service: SearchService = None,
        qdrant_client: QdrantClientWrapper = None,
        embedding_model: EmbeddingModel = None,
        gemini_api_key: Optional[str] = None
    ):
        self.gemini_api_key = gemini_api_key
        print(gemini_api_key,"yooooo")
        self.gemini_model = None

        if search_service:
            self.search_service = search_service
        else:
            qdrant_client = qdrant_client or QdrantClientWrapper()
            embedding_model = embedding_model or EmbeddingModel()
            self.search_service = SearchService(
                qdrant_client=qdrant_client, 
                embedding_model=embedding_model,
                gemini_api_key=self.gemini_api_key
            )
    
    def initialize_gemini_model(self, api_key: Optional[str] = None):
        """Initialize the Gemini model with the appropriate API key."""
        import google.generativeai as genai
        
        try:
            key_to_use = api_key or self.gemini_api_key
            
            if not key_to_use:
                raise ValueError("No Gemini API key provided - cannot initialize model")
            
            genai.configure(api_key=key_to_use)
            
            try:
                self.gemini_model = genai.GenerativeModel('gemini-2.5-pro-preview-05-06')
            except Exception as e:
                self.gemini_model = genai.GenerativeModel('gemini-2.5-flash-preview-04-17')
            
            return True
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise ValueError(f"Failed to initialize Gemini model: {str(e)}")
    
    def _ensure_gemini_model(self):
        """Ensure Gemini model is initialized."""
        if not self.gemini_model:
            try:
                self.initialize_gemini_model()
            except ValueError as e:
                logger.error(f"Failed to initialize Gemini model: {str(e)}")
                return False
        return True
    
    def assess_query_type(self, query_text: str) -> Dict[str, Any]:
        """
        Assess if query is personal, domain-specific, or general knowledge.
        
        Args:
            query_text: User's question
            
        Returns:
            Dictionary with assessment results
        """
        if not self._ensure_gemini_model():
            return {
                "type": "domain_specific", 
                "confidence": "low",
                "explanation": "Unable to assess query due to missing Gemini model",
                "reason": "domain_specific_query"
            }
        
        try:
            prompt = f"""
            Analyze the following user query and determine whether it is:
            1. A personal question (asking about user identity, preferences, or personal information)
            2. A domain-specific question (requires specialized knowledge)
            3. A general knowledge question (can be answered with common knowledge)
            
            User query: "{query_text}"
            
            Respond in JSON format with the following fields:
            - "type": "personal" or "domain_specific" or "general_knowledge"
            - "confidence": "high", "medium", or "low"
            - "explanation": brief explanation of your reasoning
            - "reason": "personal_question" if personal, "domain_specific_query" if domain-specific, "general_knowledge_query" if general knowledge
            
            JSON response:
            """
            
            response = self.gemini_model.generate_content(prompt)
            response_text = response.text.strip()
            
            import json
            import re
            
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                assessment = json.loads(json_match.group(0))
                
                if "reason" not in assessment:
                    if assessment.get("type") == "personal":
                        assessment["reason"] = "personal_question"
                    elif assessment.get("type") == "domain_specific":
                        assessment["reason"] = "domain_specific_query"
                    else:
                        assessment["reason"] = "general_knowledge_query"
                
                return assessment
            else:
                query_lower = query_text.lower()
                if any(term in query_lower for term in ["who am i", "my name", "myself", "my profile"]):
                    return {
                        "type": "personal",
                        "confidence": "medium",
                        "explanation": "Query appears to ask about personal identity",
                        "reason": "personal_question"
                    }
                elif any(term in query_lower for term in ["specific", "document", "context", "database"]):
                    return {
                        "type": "domain_specific",
                        "confidence": "medium",
                        "explanation": "Query appears to ask about specific information",
                        "reason": "domain_specific_query"
                    }
                else:
                    return {
                        "type": "general_knowledge",
                        "confidence": "low",
                        "explanation": "Fallback classification based on simple pattern matching",
                        "reason": "general_knowledge_query"
                    }
        except Exception as e:
            logger.error(f"Error in query assessment: {e}")
            return {
                "type": "domain_specific",  
                "confidence": "low",
                "explanation": f"Error occurred during assessment: {str(e)}",
                "reason": "domain_specific_query"
            }
    
    def generate_answer_from_context(self, query_text: str, context: str) -> str:
        """
        Generate an answer from the retrieved context using Gemini.
        
        Args:
            query_text: User's question
            context: Retrieved context from documents
            
        Returns:
            Generated answer
        """
        if not self._ensure_gemini_model():
            return "I'm unable to process your query due to configuration issues."
        
        try:
            prompt = f"""
            Answer the following question using the provided context. If the context fully answers 
            the question, rely on that information. If the context only partially answers the 
            question, you may supplement with your general knowledge, but clearly distinguish 
            between facts from the context and your additional knowledge.
            
            Question: {query_text}
            
            Context:
            {context}
            
            When using information from the context, be precise and faithful to what it actually says.
            Do not make up or hallucinate information that's not in the context or your general knowledge.
            If you're uncertain about something, acknowledge that uncertainty.
            """
            
            response = self.gemini_model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Error generating answer from context: {e}")
            return "I'm sorry, I encountered an error while processing your question."
    
    def generate_answer_from_knowledge(
        self,
        query_text: str,
        gemini_api_key: Optional[str] = None,
        preamble: Optional[str] = None
    ) -> str:
        """
        Generate an answer using Gemini's general knowledge, with support for intent detection 
        and optional preamble-based prompting.
    
        Args:
            query_text: User's question
            gemini_api_key: Optional API key for Gemini (used for lazy init)
            preamble: Optional preamble to prepend to the prompt
    
        Returns:
            A generated answer as a string
        """
        try:
            self.initialize_gemini_model(gemini_api_key)
            if not self._ensure_gemini_model():
                return "I'm unable to process your query due to configuration issues."

            query_lower = query_text.lower().strip("?!.,")

            greeting_patterns = [
                "hi", "hello", "hey", "greetings", "good morning", "good afternoon", 
                "good evening", "howdy", "hola", "hii", "sup", "what's up", "yo"
            ]
            is_greeting = query_lower in greeting_patterns or (
                len(query_lower.split()) <= 2 and any(pattern in query_lower for pattern in greeting_patterns)
            )

            if preamble:
                prompt = f"""
                {preamble.strip()}
            
                Question: {query_text}
            
                Please provide a helpful, accurate, and concise answer.
                """
            elif is_greeting:
                prompt = f"""
                The user has sent: "{query_text}"
            
                This appears to be a greeting or conversation starter. Respond in a friendly, 
                conversational manner as if starting a helpful dialogue.
                """
            else:
                prompt = f"""
                The user has asked: "{query_text}"
            
                Respond naturally to this query using your knowledge and capabilities.
                If this is a conversational message, respond conversationally.
                If this is a knowledge question, provide helpful information.
                If this is a request, respond appropriately to the request.
            
                Be helpful, accurate, and concise. If you don't know something, say so clearly.
                """

            response = self.gemini_model.generate_content(prompt)
            return response.text.strip()
    
        except Exception as e:
            logger.error(f"Error generating answer from knowledge: {e}")
            return "I'm sorry, I encountered an error while processing your question."

    def let_gemini_decide(
        self,
        query_text: str,
        retrieved_documents: List[Dict[str, Any]],
        gemini_api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Let Gemini decide if the documents are relevant.
        
        Args:
            query_text: User's question
            retrieved_documents: List of retrieved documents
            gemini_api_key: Optional API key for Gemini
            
        Returns:
            Dictionary with decision
        """
        if gemini_api_key:
            self.initialize_gemini_model(gemini_api_key)
        
        if not self._ensure_gemini_model():
            return {"decision": "use_documents", "confidence": "low", "explanation": "No Gemini model available"}
        
        try:
            context_parts = []
            for i, doc in enumerate(retrieved_documents):
                context_parts.append(f"Document {i+1} (Score: {doc['score']:.2f}):\n{doc['text']}\n")
            
            context = "\n".join(context_parts)
            
            prompt = f"""
            Analyze whether the following retrieved documents are relevant and helpful for answering the user's query.
            
            User query: "{query_text}"
            
            Retrieved documents:
            {context}
            
            Respond in JSON format with the following fields:
            - "decision": "use_documents" if documents are relevant, "use_hybrid" if partially relevant, "use_llm" if not relevant
            - "confidence": "high", "medium", or "low"
            - "explanation": brief explanation of your reasoning
            
            JSON response:
            """
            
            response = self.gemini_model.generate_content(prompt)
            response_text = response.text.strip()
            
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                decision = json.loads(json_match.group(0))
                return decision
            else:
                top_score = retrieved_documents[0]["score"] if retrieved_documents else 0
                
                if top_score > 0.8:
                    decision = "use_documents"
                elif top_score > 0.7:
                    decision = "use_hybrid"
                else:
                    decision = "use_llm"
                
                return {
                    "decision": decision,
                    "confidence": "low",
                    "explanation": f"Fallback assessment based on top score ({top_score:.2f})"
                }
        except Exception as e:
            logger.error(f"Error in document relevance assessment: {e}")
            return {"decision": "use_documents", "confidence": "low", "explanation": f"Error in assessment: {str(e)}"}
    
    