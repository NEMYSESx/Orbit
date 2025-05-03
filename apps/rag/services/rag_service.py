import os
import sys
import google.generativeai as genai
from typing import Dict, Any, Optional, List, Tuple

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from models.qdrant_client import QdrantClientWrapper
from models.embeddings import EmbeddingModel
from .search_service import SearchService

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)
from config import settings


class RAGService:
    """Service for Retrieval-Augmented Generation with improved accuracy and fallbacks."""

    def __init__(
        self,
        search_service: SearchService = None,
        qdrant_client: QdrantClientWrapper = None,
        embedding_model: EmbeddingModel = None
    ):
        """
        Initialize the RAG service.
        """
        if search_service:
            self.search_service = search_service
        else:
            qdrant_client = qdrant_client or QdrantClientWrapper()
            embedding_model = embedding_model or EmbeddingModel()
            self.search_service = SearchService(qdrant_client, embedding_model)

    def _configure_gemini(self, api_key: Optional[str] = None):
        """Configure Gemini API with provided key or from environment."""
        if api_key:
            genai.configure(api_key=api_key)
        elif "GOOGLE_API_KEY" in os.environ:
            genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

    def assess_query_needs_retrieval(self, query_text: str, gemini_api_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Use Gemini to assess if query needs retrieval or is general knowledge/personal.
        
        Args:
            query_text: User's question
            gemini_api_key: Optional API key for Gemini
            
        Returns:
            Dictionary with assessment results and reasoning
        """
        self._configure_gemini(gemini_api_key)
        model = genai.GenerativeModel('gemini-2.5-pro-preview-03-25')
        
        prompt = f"""
        Analyze the following user query and determine whether it requires retrieval from a knowledge base 
        or if it can be answered with general knowledge or is a personal question.
        
        User query: "{query_text}"
        
        Respond in JSON format with the following fields:
        - "needs_retrieval": true/false (whether specialized knowledge is needed)
        - "reason": "domain_specific" or "general_knowledge" or "personal_question"
        - "explanation": brief explanation of your reasoning
        
        Rules for classification:
        - "domain_specific" - needs specialized information not in general knowledge
        - "general_knowledge" - can be answered with common knowledge
        - "personal_question" - asks about user identity or personal info ("Who am I?", "What's my name?")
        
        JSON response:
        """
        
        try:
            response = model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Extract JSON portion
            import json
            import re
            
            # Look for JSON pattern
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                assessment = json.loads(json_match.group(0))
                return assessment
            else:
                # Fallback if JSON parsing fails
                needs_retrieval = False
                reason = "general_knowledge"
                
                if any(term in query_text.lower() for term in ["who am i", "my name", "myself", "my profile"]):
                    reason = "personal_question"
                elif any(term in query_text.lower() for term in ["specific", "document", "context", "database"]):
                    needs_retrieval = True
                    reason = "domain_specific"
                
                return {
                    "needs_retrieval": needs_retrieval,
                    "reason": reason,
                    "explanation": "Fallback classification based on keyword matching"
                }
        except Exception as e:
            # Default fallback on error
            print(f"Error in query assessment: {e}")
            return {
                "needs_retrieval": True,  # Default to retrieval on error
                "reason": "assessment_error",
                "explanation": f"Error occurred during assessment: {str(e)}"
            }

    def handle_personal_query(self, query_text: str, gemini_api_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Handle queries about personal identity.
        
        Args:
            query_text: User question
            gemini_api_key: API key for Gemini
            
        Returns:
            Response object with appropriate messaging
        """
        self._configure_gemini(gemini_api_key)
        model = genai.GenerativeModel('gemini-2.5-pro-preview-03-25')
        
        # Identity-specific response template
        response_text = "I don't have information about your personal identity. " \
                       "I'm an AI assistant that can help answer questions based on " \
                       "available knowledge, but I don't have access to who you are personally."
        
        return {
            "question": query_text,
            "answer": response_text,
            "retrieved_documents": [],
            "used_model_knowledge": False,
            "performed_retrieval": False,
            "process_mode": "personal_question"
        }

    def retrieve_with_similarity_threshold(
        self,
        query_text: str,
        collection_name: str,
        gemini_api_key: Optional[str] = None,
        k: int = 5,  # Increased from 3 to 5 for better coverage
        similarity_threshold: float = 0.7,
        filter_conditions: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[Any], bool]:
        """
        Retrieve documents but only return them if they meet a minimum similarity threshold.
        
        Args:
            query_text: User question
            collection_name: Name of the collection to search
            gemini_api_key: API key for Gemini
            k: Number of documents to retrieve
            similarity_threshold: Minimum similarity score to consider retrieval successful
            filter_conditions: Optional filter conditions for search
            
        Returns:
            Tuple of (search_results, retrieval_successful)
        """
        search_results = self.search_service.search(
            query_text,
            collection_name=collection_name,
            limit=k,
            gemini_api_key=gemini_api_key,
            rerank=True,
            filter_conditions=filter_conditions
        )
        
        # Enhanced threshold logic - check for multiple reasonably good results
        retrieval_successful = False
        if search_results:
            # Primary check: top result meets threshold
            if search_results[0].score >= similarity_threshold:
                retrieval_successful = True
                print(f"Top result score {search_results[0].score} meets threshold {similarity_threshold}")
            
            # Secondary check: Multiple results with decent scores (aggregate evidence)
            elif len(search_results) >= 3:
                # Check if we have at least 3 results with scores above a lower threshold
                lower_threshold = similarity_threshold - 0.1  # More lenient threshold
                good_results = [r for r in search_results if r.score >= lower_threshold]
                
                if len(good_results) >= 2:
                    # If we have multiple slightly-below-threshold results, they might collectively be useful
                    retrieval_successful = True
                    print(f"Multiple results above lower threshold {lower_threshold}. " 
                          f"Using {len(good_results)} documents.")
                else:
                    print(f"Insufficient results above lower threshold {lower_threshold}.")
            else:
                print(f"Top result score {search_results[0].score} below threshold {similarity_threshold}")
        
        return search_results, retrieval_successful

    def hybrid_assess_and_retrieve(
        self,
        query_text: str,
        collection_name: str = settings.DEFAULT_COLLECTION_NAME,
        gemini_api_key: Optional[str] = None,
        k: int = 5,  # Increased from 3 to 5
        similarity_threshold: float = 0.7,
        filter_conditions: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        First assess if query is personal/general knowledge, then retrieve documents 
        with similarity threshold if needed.
        
        Args:
            query_text: User question
            collection_name: Name of the collection
            gemini_api_key: API key for Gemini
            k: Number of documents to retrieve
            similarity_threshold: Minimum similarity score threshold
            filter_conditions: Optional filter conditions for search
            
        Returns:
            Dictionary with assessment results and retrieved documents if appropriate
        """
        # 1. First do LLM-based assessment
        assessment = self.assess_query_needs_retrieval(query_text, gemini_api_key)
        print(f"LLM assessment: {assessment}")
        
        # 2. Always retrieve but with threshold to catch edge cases
        search_results, retrieval_successful = self.retrieve_with_similarity_threshold(
            query_text=query_text,
            collection_name=collection_name,
            gemini_api_key=gemini_api_key,
            k=k,
            similarity_threshold=similarity_threshold,
            filter_conditions=filter_conditions
        )
        
        # 3. Apply keyword-based check for better identification of personal queries
        contains_personal_terms = any(term in query_text.lower() for term in 
                                     ["who am i", "my name", "myself", "my profile", "my account", "my mentor"])
        
        if contains_personal_terms and assessment["reason"] != "personal_question":
            # Override LLM assessment for personal queries
            assessment["reason"] = "personal_question"
            assessment["explanation"] = "Query contains personal identity terms"
            print("Overriding assessment: Query detected as personal question by keyword check")
        
        # 4. Determine the final decision based on both approaches
        documents = []
        if search_results and retrieval_successful:
            # Filter results by threshold and process documents if retrieval was successful
            filtered_results = [r for r in search_results if r.score >= similarity_threshold]
            
            for i, result in enumerate(filtered_results):
                doc_text = result.payload.get('text', '')
                documents.append({
                    "id": result.id,
                    "text": doc_text,
                    "score": result.score,
                    "metadata": {k: v for k, v in result.payload.items() if k != 'text'}
                })
        
        # Return comprehensive assessment results
        return {
            "llm_assessment": assessment,
            "retrieval_successful": retrieval_successful,
            "similarity_threshold": similarity_threshold,
            "top_score": search_results[0].score if search_results else None,
            "retrieved_documents": documents,
            "use_retrieval": retrieval_successful,  # Final decision
            "contains_personal_terms": contains_personal_terms
        }

    def improved_hybrid_assess_and_retrieve(
        self,
        query_text: str,
        collection_name: str = settings.DEFAULT_COLLECTION_NAME,
        gemini_api_key: Optional[str] = None,
        k: int = 5,
        similarity_threshold: float = 0.7,
        filter_conditions: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Enhanced assessment that properly handles personal queries with good document matches.
        """
        # First perform the existing hybrid assessment
        hybrid_results = self.hybrid_assess_and_retrieve(
            query_text=query_text,
            collection_name=collection_name,
            gemini_api_key=gemini_api_key,
            k=k,
            similarity_threshold=similarity_threshold,
            filter_conditions=filter_conditions
        )
        
        # Get the key elements from the results
        llm_assessment = hybrid_results["llm_assessment"]
        retrieval_successful = hybrid_results["retrieval_successful"]
        top_score = hybrid_results.get("top_score", 0)
        contains_personal_terms = hybrid_results.get("contains_personal_terms", False)
        
        # CRITICAL FIX: For personal questions with high-scoring matches (>0.75), 
        # we should trust the retrieval rather than Gemini's decision
        if (llm_assessment.get("reason") == "personal_question" or contains_personal_terms) and retrieval_successful:
            if top_score > 0.75:  # High confidence threshold for personal questions
                hybrid_results["use_retrieval"] = True
                hybrid_results["override_reason"] = "high_confidence_personal_match"
                print(f"Overriding decision for personal query with high confidence match (score: {top_score})")
        
        return hybrid_results

    def let_gemini_decide(
        self,
        query_text: str,
        retrieved_documents: List[Dict[str, Any]],
        gemini_api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Let Gemini decide whether to use retrieved documents or answer from its knowledge.
        
        Args:
            query_text: User question
            retrieved_documents: List of retrieved documents
            gemini_api_key: API key for Gemini
            
        Returns:
            Dictionary with Gemini's decision
        """
        self._configure_gemini(gemini_api_key)
        model = genai.GenerativeModel('gemini-2.5-pro-preview-03-25')
        
        # Build context from retrieved documents
        context = ""
        for i, doc in enumerate(retrieved_documents):
            context += f"Document {i+1} (score: {doc['score']:.2f}):\n{doc['text']}\n\n"
        
        decision_prompt = f"""
        I need your help deciding how to answer a user's question. I have retrieved some documents 
        that might be relevant, but I need you to determine if they actually contain the answer
        or if you should answer using your general knowledge instead.
        
        User's question: "{query_text}"
        
        Retrieved documents:
        {context}
        
        Please analyze whether these documents contain specific information that answers the user's 
        question. Consider both relevance AND correctness/completeness. Even if documents are related 
        to the query topic, if they don't directly address the specific question or provide outdated/
        incomplete information, you should use your knowledge instead.
        
        If they contain information that directly answers the question, respond with:
        USE_DOCUMENTS: <brief explanation why>
        
        If the documents don't contain specific information to answer the question, or if the 
        information is too generic and you can provide a better answer with your knowledge, respond with:
        USE_KNOWLEDGE: <brief explanation why>
        
        If you think a combination approach is best (using document info but supplementing with your knowledge):
        USE_HYBRID: <brief explanation why>
        
        IMPORTANT: For personal questions about identity, preferences, or user-specific information,
        if the documents contain a relevant answer, you MUST use the documents. Personal information
        in our documents is authoritative and should override your general knowledge.
        """
        
        try:
            response = model.generate_content(decision_prompt)
            response_text = response.text.strip()
            
            # Modified logic for handling personal queries
            is_personal_query = any(term in query_text.lower() for term in 
                                   ["who am i", "my name", "myself", "my profile", "my account", "my mentor"])
            
            if is_personal_query and context and any(doc["score"] > 0.75 for doc in retrieved_documents):
                return {
                    "decision": "use_documents",
                    "explanation": "Document contains authoritative information about personal query",
                    "confidence": "high",
                    "overridden_for_personal_query": True
                }
            
            if "USE_DOCUMENTS:" in response_text:
                return {
                    "decision": "use_documents",
                    "explanation": response_text.split("USE_DOCUMENTS:")[1].strip(),
                    "confidence": "high" if "specific" in response_text.lower() and "directly" in response_text.lower() else "medium"
                }
            elif "USE_KNOWLEDGE:" in response_text:
                return {
                    "decision": "use_knowledge", 
                    "explanation": response_text.split("USE_KNOWLEDGE:")[1].strip(),
                    "confidence": "high" if "don't contain" in response_text.lower() or "doesn't address" in response_text.lower() else "medium"
                }
            elif "USE_HYBRID:" in response_text:
                return {
                    "decision": "use_hybrid",
                    "explanation": response_text.split("USE_HYBRID:")[1].strip(),
                    "confidence": "high"
                }
            else:
                # Default if format not followed
                use_docs = "relevant" in response_text.lower() and "specific" in response_text.lower()
                return {
                    "decision": "use_documents" if use_docs else "use_knowledge",
                    "explanation": "Decision based on relevance analysis",
                    "confidence": "low"
                }
        except Exception as e:
            print(f"Error in Gemini decision: {e}")
            # Default to using documents if we retrieved them
            return {
                "decision": "use_documents" if retrieved_documents else "use_knowledge",
                "explanation": f"Default decision due to error: {str(e)}",
                "confidence": "very_low"
            }

    def retrieve_and_answer(
        self,
        query_text: str,
        collection_name: str = settings.DEFAULT_COLLECTION_NAME,
        gemini_api_key: Optional[str] = None,
        k: int = 5,  # Increased from 3 to 5
        expand_with_model_knowledge: bool = True,
        filter_conditions: Optional[Dict[str, Any]] = None,
        force_retrieval: bool = False,
        auto_assess_retrieval_need: bool = True,
        similarity_threshold: float = 0.7,
        three_phase_approach: bool = True
    ) -> Dict[str, Any]:
        """
        Advanced retrieval-augmented generation with multiple strategies.
        """
        self._configure_gemini(gemini_api_key)
        model = genai.GenerativeModel('gemini-2.5-pro-preview-03-25')

        if force_retrieval:
            print("Force retrieval is enabled. Skipping assessment.")
            search_results = self.search_service.search(
                query_text,
                collection_name=collection_name,
                limit=k,
                gemini_api_key=gemini_api_key,
                rerank=True,
                filter_conditions=filter_conditions
            )
            process_mode = "force_retrieval"

        elif three_phase_approach and auto_assess_retrieval_need:
            hybrid_results = self.improved_hybrid_assess_and_retrieve(
                query_text=query_text,
                collection_name=collection_name,
                gemini_api_key=gemini_api_key,
                k=k,
                similarity_threshold=similarity_threshold,
                filter_conditions=filter_conditions
            )

            llm_assessment = hybrid_results["llm_assessment"]
            retrieval_successful = hybrid_results["retrieval_successful"]
            contains_personal_terms = hybrid_results.get("contains_personal_terms", False)
            override_reason = hybrid_results.get("override_reason", None)
            
            # Get search results to work with
            search_results = self.search_service.search(
                query_text,
                collection_name=collection_name,
                limit=k,
                gemini_api_key=gemini_api_key,
                rerank=True,
                filter_conditions=filter_conditions
            ) if retrieval_successful else []
            
            filtered_results = [
                result for result in search_results if result.score >= similarity_threshold
            ] if search_results else []

            # Handle the override for personal queries with high confidence matches
            if override_reason == "high_confidence_personal_match":
                process_mode = "use_retrieval"
                print("Using retrieval for personal query due to high confidence match.")
            elif not retrieval_successful or not filtered_results:
                process_mode = "model_knowledge_only"
                print(f"No retrieval results above threshold ({similarity_threshold}). Using model knowledge.")
            elif llm_assessment.get("reason") == "personal_question" or contains_personal_terms:
                if not retrieval_successful:
                    process_mode = "personal_question"
                    print("Query assessed as personal question with no good document matches.")
                else:
                    # If we have good matches despite personal question nature, use retrieval
                    process_mode = "use_retrieval"
                    print("Personal query with good document matches. Using retrieval.")
            elif llm_assessment.get("needs_retrieval") and retrieval_successful:
                process_mode = "use_retrieval"
                print("Domain-specific query with good document matches. Using retrieval.")
            elif not llm_assessment.get("needs_retrieval") and retrieval_successful:
                process_mode = "gemini_decision"
                print("General knowledge query BUT has good document matches. Letting Gemini decide.")
            else:
                process_mode = "gemini_decision"
                print("Unclear assessment. Letting Gemini decide.")

        else:
            if auto_assess_retrieval_need:
                assessment = self.assess_query_needs_retrieval(query_text, gemini_api_key)
                needs_retrieval = assessment["needs_retrieval"]

                if needs_retrieval:
                    search_results = self.search_service.search(
                        query_text,
                        collection_name=collection_name,
                        limit=k,
                        gemini_api_key=gemini_api_key,
                        rerank=True,
                        filter_conditions=filter_conditions
                    )
                    # Check if we have results that meet the threshold
                    filtered_results = [r for r in search_results if r.score >= similarity_threshold]
                    process_mode = "use_retrieval" if filtered_results else "model_knowledge_only"
                else:
                    search_results = []
                    process_mode = "personal_question" if assessment.get("reason") == "personal_question" else "model_knowledge_only"
            else:
                search_results = self.search_service.search(
                    query_text,
                    collection_name=collection_name,
                    limit=k,
                    gemini_api_key=gemini_api_key,
                    rerank=True,
                    filter_conditions=filter_conditions
                )
                # Check if we have results that meet the threshold
                filtered_results = [r for r in search_results if r.score >= similarity_threshold]
                process_mode = "use_retrieval" if filtered_results else "model_knowledge_only"

        if process_mode == "personal_question":
            # Check for personal questions that might have answers in our knowledge base
            personal_search_results = self.search_service.search(
                query_text,
                collection_name=collection_name,
                limit=3,  # Just check top 3 for personal questions
                gemini_api_key=gemini_api_key,
                rerank=True,
                filter_conditions=filter_conditions
            )
            
            # If we have a high confidence match for the personal query, use it
            if personal_search_results and personal_search_results[0].score > 0.75:
                print(f"Found high confidence match ({personal_search_results[0].score}) for personal query. Using retrieval.")
                search_results = personal_search_results
                process_mode = "use_retrieval"
            else:
                return self.handle_personal_query(query_text, gemini_api_key)

        elif process_mode == "model_knowledge_only":
            if not expand_with_model_knowledge:
                return {
                    "question": query_text,
                    "answer": "I couldn't find relevant information to answer your question in our knowledge base, and I'm not permitted to use my general knowledge.",
                    "retrieved_documents": [],
                    "used_model_knowledge": False,
                    "performed_retrieval": True,
                    "process_mode": process_mode
                }

            prompt = f"""
            Please answer the following question using your general knowledge:

            Question: {query_text}

            Provide a clear, concise, and accurate response. If you don't know the answer,
            please state that clearly rather than making up information.
            """
            response = model.generate_content(prompt)
            return {
                "question": query_text,
                "answer": response.text,
                "retrieved_documents": [],
                "used_model_knowledge": True,
                "performed_retrieval": True,
                "process_mode": process_mode
            }

        elif process_mode == "gemini_decision":
            # Filter results by threshold
            filtered_results = [r for r in search_results if r.score >= similarity_threshold]
            
            documents = []
            for result in filtered_results:
                doc_text = result.payload.get('text', '')
                documents.append({
                    "id": result.id,
                    "text": doc_text,
                    "score": result.score,
                    "metadata": {k: v for k, v in result.payload.items() if k != 'text'}
                })

            decision = self.let_gemini_decide(query_text, documents, gemini_api_key)
            print(f"Gemini decision: {decision['decision']} ({decision['confidence']})")

            if decision['decision'] == "use_knowledge" and expand_with_model_knowledge:
                prompt = f"""
                Please answer the following question using your general knowledge:

                Question: {query_text}

                Provide a clear, concise, and accurate response. If you don't know the answer,
                please state that clearly rather than making up information.
                """
                response = model.generate_content(prompt)
                return {
                    "question": query_text,
                    "answer": response.text,
                    "retrieved_documents": documents,
                    "used_model_knowledge": True,
                    "performed_retrieval": True,
                    "process_mode": "gemini_decided_knowledge",
                    "gemini_decision": decision
                }
            elif decision['decision'] == "use_hybrid":
                # Use hybrid approach - combine retrieved info and model knowledge
                context = ""
                for i, doc in enumerate(documents):
                    context += f"Document {i + 1}:\n{doc['text']}\n\n"
                
                hybrid_prompt = f"""
                Answer the following question using BOTH the provided information AND your own knowledge.
                The provided context contains relevant information related to the question, but you should
                expand on it with additional relevant details, examples, or explanations from your knowledge.
                
                Question: {query_text}
                
                Context from knowledge base:
                {context}
                
                Provide a complete answer that combines the specific information from the context with your
                broader understanding of the topic. Make it clear when you're drawing from the context versus
                your own knowledge.
                """
                response = model.generate_content(hybrid_prompt)
                return {
                    "question": query_text,
                    "answer": response.text,
                    "retrieved_documents": documents,
                    "used_model_knowledge": True,
                    "performed_retrieval": True,
                    "process_mode": "hybrid_approach",
                    "gemini_decision": decision
                }
            else:
                process_mode = "use_retrieval"

        if process_mode in ["force_retrieval", "use_retrieval"]:
            # Filter results by threshold
            filtered_results = [r for r in search_results if r.score >= similarity_threshold]
            
            documents = []
            context = ""
            for i, result in enumerate(filtered_results):
                doc_text = result.payload.get('text', '')
                context += f"Document {i + 1}:\n{doc_text}\n\n"
                documents.append({
                    "id": result.id,
                    "text": doc_text,
                    "score": result.score,
                    "metadata": {k: v for k, v in result.payload.items() if k != 'text'}
                })

            if not documents:
                if expand_with_model_knowledge:
                    prompt = f"""
                    Please answer this question using your general knowledge:
                    
                    Question: {query_text}
                    
                    If you don't have sufficient information to answer accurately, please be honest
                    about the limitations of your knowledge rather than making up information.
                    """
                    response = model.generate_content(prompt)
                    return {
                        "question": query_text,
                        "answer": response.text,
                        "retrieved_documents": [],
                        "used_model_knowledge": True,
                        "performed_retrieval": True,
                        "process_mode": process_mode
                    }
                else:
                    return {
                        "question": query_text,
                        "answer": "I couldn't find any relevant information to answer your question.",
                        "retrieved_documents": [],
                        "used_model_knowledge": False,
                        "performed_retrieval": True,
                        "process_mode": process_mode
                    }

            # Improved prompt with explicit guidance about how to use the context
            prompt = f"""
            Answer the following question using the provided context information.
            If the context fully answers the question, rely primarily on that information.
            If the context only partially answers the question, you may supplement with your
            general knowledge, but clearly distinguish between facts from the context and your
            additional knowledge.
            
            Question: {query_text}
            
            Context from knowledge base:
            {context}
            
            When using information from the context, be precise and faithful to what it actually says.
            Do not make up or hallucinate information that's not in the context or your general knowledge.
            If you're uncertain about something, acknowledge that uncertainty.
            """
            response = model.generate_content(prompt)
            return {
                "question": query_text,
                "answer": response.text,
                "retrieved_documents": documents,
                "used_model_knowledge": True,
                "performed_retrieval": True,
                "process_mode": process_mode
            }