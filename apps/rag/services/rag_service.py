from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import concurrent.futures
from rag.services.search_service import SearchService, SearchResult


@dataclass
class RAGResponse:
    answer: str
    used_context: bool
    context_sources: List[Dict[str, Any]]

class RAGService:
    def __init__(self, collection_name: str):
        self.search_service = SearchService()
        self.collection_name = collection_name
    
    def _extract_text_from_response(self, response) -> str:
        try:
            if hasattr(response, '__iter__') and not isinstance(response, str):
                return ''.join(str(chunk) for chunk in response)
            else:
                return str(response)
        except Exception as e:
            print(f"Error extracting text from response: {e}")
            return ""
    
    def create_relevance_check_prompt(self, query: str, contexts: List[SearchResult]) -> str:
        contexts_text = ""
        for i, context in enumerate(contexts, 1):
            text_sample = context.text[:800] if len(context.text) > 800 else context.text
            contexts_text += f"Context {i}:\n{text_sample}...\n\n"
        
        return f"""
Analyze if the provided contexts are relevant to answer the user's query.

User Query: "{query}"

Retrieved Contexts:
{contexts_text}

Determine if these contexts contain information that can help answer the user's query.

Respond with only "RELEVANT" or "NOT_RELEVANT" followed by a brief explanation.

Example responses:
- "RELEVANT - The contexts contain specific information about the query topic"
- "NOT_RELEVANT - The contexts discuss unrelated topics that don't address the query"
"""
    
    def create_conflict_detection_prompt(self, contexts: List[SearchResult]) -> str:
        contexts_text = ""
        for i, context in enumerate(contexts, 1):
            timestamp = context.payload.get('timestamp', 'Unknown')
            contexts_text += f"Context {i} (Timestamp: {timestamp}):\n{context.text[:500]}...\n\n"
        
        return f"""
Analyze if the provided contexts contain conflicting information.

Contexts:
{contexts_text}

Look for contradictory statements, opposing viewpoints, or conflicting facts between the contexts.

Respond with only "CONFLICT" or "NO_CONFLICT" followed by a brief explanation.

If CONFLICT is detected, identify which contexts conflict with each other.
"""
    
    def create_answer_generation_prompt(self, query: str, contexts: List[SearchResult]) -> str:
        contexts_text = ""
        for i, context in enumerate(contexts, 1):
            contexts_text += f"Context {i}:\n{context.text}\n\n"
        
        return f"""
Using the provided contexts, answer the user's query comprehensively and accurately.

User Query: "{query}"

Available Contexts:
{contexts_text}

Instructions:
- Base your answer primarily on the provided contexts
- If contexts don't fully address the query, clearly indicate what information is missing
- Maintain factual accuracy and cite relevant parts of the contexts
- Provide a clear, well-structured response
- Don't write things like "I'm using context 1 or context 2", be more professional

Answer:"""
    
    def check_context_relevance(self, query: str, contexts: List[SearchResult]) -> bool:
        if not contexts:
            return False
        
        try:
            prompt = self.create_relevance_check_prompt(query, contexts)
            response = self.search_service.gemini_client.generate_text(prompt, temperature=0.1)
            
            response_text = self._extract_text_from_response(response)
            
            is_relevant = response_text.strip().upper().startswith("RELEVANT")
            print(f"Context relevance check: {'RELEVANT' if is_relevant else 'NOT_RELEVANT'}")
            return is_relevant
            
        except Exception as e:
            print(f"Error in relevance check: {e}")
            return False
    
    def detect_conflicts(self, contexts: List[SearchResult]) -> str:
        if len(contexts) <= 1:
            return "NO_CONFLICT"
        
        try:
            prompt = self.create_conflict_detection_prompt(contexts)
            response = self.search_service.gemini_client.generate_text(prompt, temperature=0.1)
            
            response_text = self._extract_text_from_response(response)
            
            has_conflict = response_text.strip().upper().startswith("CONFLICT")
            print(f"Conflict detection: {'CONFLICT DETECTED' if has_conflict else 'NO CONFLICT'}")
            return response_text
            
        except Exception as e:
            print(f"Error in conflict detection: {e}")
            return "NO_CONFLICT"
    
    def resolve_conflicts(self, contexts: List[SearchResult]) -> List[SearchResult]:
        try:
            print("Resolving conflicts using timestamps...")
            
            contexts_with_time = []
            for context in contexts:
                timestamp_str = context.payload.get('timestamp', '')
                try:
                    if timestamp_str:
                        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    else:
                        timestamp = datetime.min  
                    
                    contexts_with_time.append((context, timestamp))
                except Exception:
                    contexts_with_time.append((context, datetime.min))
            
            contexts_with_time.sort(key=lambda x: x[1], reverse=True)
            
            latest_timestamp = contexts_with_time[0][1]
            resolved_contexts = []
            
            for context, timestamp in contexts_with_time:
                if abs((latest_timestamp - timestamp).days) <= 1:
                    resolved_contexts.append(context)
            
            print(f"Conflict resolved: Using {len(resolved_contexts)} most recent contexts")
            return resolved_contexts
            
        except Exception as e:
            print(f"Error in conflict resolution: {e}")
            return contexts
    
    def check_relevance_and_conflicts_concurrent(self, query: str, contexts: List[SearchResult]) -> Tuple[bool, Optional[str]]:
        is_relevant = False
        conflict_response = None
        
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                relevance_future = executor.submit(self.check_context_relevance, query, contexts)
                conflict_future = executor.submit(self.detect_conflicts, contexts)
                
                concurrent.futures.wait([relevance_future, conflict_future])
                
                is_relevant = relevance_future.result()
                conflict_response = conflict_future.result()
                
        except Exception as e:
            print(f"Error in concurrent processing: {e}")
            is_relevant = self.check_context_relevance(query, contexts)
            if is_relevant:
                conflict_response = self.detect_conflicts(contexts)
        
        if not is_relevant:
            conflict_response = None
            
        return is_relevant, conflict_response
    
    def generate_direct_answer(self, query: str) -> str:
        prompt = f"""
Answer the following question based on your knowledge:

Question: "{query}"

Provide a helpful, accurate, and comprehensive answer. If you're uncertain about specific details, clearly indicate this in your response.

Answer:"""
        
        try:
            response = self.search_service.gemini_client.generate_text(prompt, temperature=0.7)
            response_text = self._extract_text_from_response(response)
            return response_text.strip() if response_text else "I apologize, but I'm unable to provide an answer at this time."
        except Exception as e:
            print(f"Error generating direct answer: {e}")
            return "I apologize, but I'm unable to provide an answer at this time due to a technical issue."
    
    def generate_context_based_answer(self, query: str, contexts: List[SearchResult]) -> str:
        try:
            prompt = self.create_answer_generation_prompt(query, contexts)
            response = self.search_service.gemini_client.generate_text(prompt, temperature=0.3)
            response_text = self._extract_text_from_response(response)
            return response_text.strip() if response_text else self.generate_direct_answer(query)
        except Exception as e:
            print(f"Error generating context-based answer: {e}")
            return self.generate_direct_answer(query)
    
    def _clean_search_filters(self, search_results) -> List[SearchResult]:
        return search_results  
    
    def query(
        self, 
        user_query: str,
        search_limit: int = 5,
        score_threshold: float = 0.6 
    ) -> RAGResponse:
        print(f"Starting RAG Service for query: '{user_query}'")
        
        try:
            print("Step 1: Searching vector database...")
            search_results = self.search_service.search(
                query=user_query,
                collection_name=self.collection_name,
                limit=search_limit,
            )
            
            print(f"Found {len(search_results)} potential contexts")
            
            if not search_results:
                print("No contexts found, using direct LLM response")
                answer = self.generate_direct_answer(user_query)
                return RAGResponse(
                    answer=answer,
                    used_context=False,
                    context_sources=[{"reason": "no_contexts_found"}]
                )
            
            print("Step 2: Checking context relevance and conflicts concurrently...")
            high_score_results = [r for r in search_results if r.score >= score_threshold]
            print(f"Results with score >= {score_threshold}: {len(high_score_results)}")
            is_relevant, conflict_response = self.check_relevance_and_conflicts_concurrent(user_query, search_results)
        
            if not is_relevant and high_score_results:
                print(f"Relevance check said NOT_RELEVANT, but found {len(high_score_results)} high-scoring results. Using score-based fallback.")
                is_relevant = True
                search_results = high_score_results
        
            if not is_relevant:
                print("Contexts not relevant and no high-scoring fallback, using direct LLM response")
                answer = self.generate_direct_answer(user_query)
                return RAGResponse(
                    answer=answer,
                    used_context=False,
                    context_sources=[{"reason": "contexts_not_relevant"}]
                )
            
            resolved_contexts = search_results
            if conflict_response and conflict_response.strip().upper().startswith("CONFLICT"):
                print("Step 3: Resolving detected conflicts...")
                resolved_contexts = self.resolve_conflicts(search_results)
            
            print("Step 4: Generating context-based answer...")
            answer = self.generate_context_based_answer(user_query, resolved_contexts)
            
            context_sources = []
            for context in resolved_contexts:
                context_sources.append({
                    "text": context.text[:200] + "...",
                    "score": context.score,
                    "timestamp": context.payload.get('timestamp', 'Unknown'),
                    "topic": context.payload.get('topic', 'Unknown'),
                    "document_title": context.payload.get('document_title', 'Unknown')
                })
            
            print("RAG process completed successfully")
            
            return RAGResponse(
                answer=answer,
                used_context=True,
                context_sources=context_sources
            )
            
        except Exception as e:
            print(f"Error in RAG query process: {e}")
            answer = self.generate_direct_answer(user_query)
            return RAGResponse(
                answer=answer,
                used_context=False,
                context_sources=[{"reason": f"error_occurred: {str(e)}"}]
            )