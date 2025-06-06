from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from rag.services.search_service import MetadataSearchService, SearchResult


@dataclass
class RAGResponse:
    answer: str
    used_context: bool
    context_sources: List[Dict[str, Any]]
    conflict_resolution_applied: bool

class RAGService:
    def __init__(self, collection_name: str):
        self.search_service = MetadataSearchService()
        self.collection_name = collection_name
    
    def _create_relevance_check_prompt(self, query: str, contexts: List[SearchResult]) -> str:
        contexts_text = ""
        for i, context in enumerate(contexts, 1):
            contexts_text += f"Context {i}:\n{context.text[:500]}...\n\n"
        
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
    
    def _create_conflict_detection_prompt(self, contexts: List[SearchResult]) -> str:
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
    
    def _create_answer_generation_prompt(self, query: str, contexts: List[SearchResult]) -> str:
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

Answer:"""
    
    def _check_context_relevance(self, query: str, contexts: List[SearchResult]) -> bool:
        if not contexts:
            return False
        
        try:
            prompt = self._create_relevance_check_prompt(query, contexts)
            response = self.search_service.gemini_client.generate_text(prompt, temperature=0.1)
            
            is_relevant = response.strip().upper().startswith("RELEVANT")
            print(f"Context relevance check: {'RELEVANT' if is_relevant else 'NOT_RELEVANT'}")
            return is_relevant
            
        except Exception as e:
            print(f"Error in relevance check: {e}")
            return False
    
    def _detect_and_resolve_conflicts(self, contexts: List[SearchResult]) -> List[SearchResult]:
        if len(contexts) <= 1:
            return contexts
        
        try:
            prompt = self._create_conflict_detection_prompt(contexts)
            response = self.search_service.gemini_client.generate_text(prompt, temperature=0.1)
            
            has_conflict = response.strip().upper().startswith("CONFLICT")
            print(f"Conflict detection: {'CONFLICT DETECTED' if has_conflict else 'NO CONFLICT'}")
            
            if not has_conflict:
                return contexts
            
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
    
    def _generate_direct_answer(self, query: str) -> str:
        prompt = f"""
Answer the following question based on your knowledge:

Question: "{query}"

Provide a helpful, accurate, and comprehensive answer. If you're uncertain about specific details, clearly indicate this in your response.

Answer:"""
        
        try:
            response = self.search_service.gemini_client.generate_text(prompt, temperature=0.7)
            return response.strip()
        except Exception as e:
            print(f"Error generating direct answer: {e}")
            return "I apologize, but I'm unable to provide an answer at this time due to a technical issue."
    
    def _generate_context_based_answer(self, query: str, contexts: List[SearchResult]) -> str:
        try:
            prompt = self._create_answer_generation_prompt(query, contexts)
            response = self.search_service.gemini_client.generate_text(prompt, temperature=0.3)
            return response.strip()
        except Exception as e:
            print(f"Error generating context-based answer: {e}")
            return self._generate_direct_answer(query)
    
    def query(
        self, 
        user_query: str, 
        search_limit: int = 5,
        fallback_strategy: str = "progressive"
    ) -> RAGResponse:
        print(f"Starting RAG pipeline for query: '{user_query}'")
        
        print("Step 1: Searching vector database...")
        search_results = self.search_service.search(
            query=user_query,
            collection_name=self.collection_name,
            limit=search_limit,
            fallback_strategy=fallback_strategy
        )
        
        if not search_results:
            print("No contexts found, using direct LLM response")
            answer = self._generate_direct_answer(user_query)
            return RAGResponse(
                answer=answer,
                used_context=False,
                context_sources=[],
                conflict_resolution_applied=False
            )
        
        print(f"Found {len(search_results)} potential contexts")
        
        print("Step 2: Checking context relevance...")
        is_relevant = self._check_context_relevance(user_query, search_results)
        
        if not is_relevant:
            print("Contexts not relevant, using direct LLM response")
            answer = self._generate_direct_answer(user_query)
            return RAGResponse(
                answer=answer,
                used_context=False,
                context_sources=[{"reason": "contexts_not_relevant"}],
                conflict_resolution_applied=False
            )
        
        print("Step 3: Checking for conflicts...")
        resolved_contexts = self._detect_and_resolve_conflicts(search_results)
        conflict_resolved = len(resolved_contexts) < len(search_results)
        
        print("Step 4: Generating context-based answer...")
        answer = self._generate_context_based_answer(user_query, resolved_contexts)
        
        context_sources = []
        for context in resolved_contexts:
            context_sources.append({
                "text": context.text[:200] + "...",
                "score": context.score,
                "timestamp": context.payload.get('timestamp', 'Unknown'),
                "topic": context.payload.get('topic', 'Unknown'),
                "document_title": context.payload.get('document_title', 'Unknown')
            })
        
        print("RAG pipeline completed successfully")
        
        return RAGResponse(
            answer=answer,
            used_context=True,
            context_sources=context_sources,
            conflict_resolution_applied=conflict_resolved
        )
