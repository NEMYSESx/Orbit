from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import concurrent.futures
from rag.services.search_service import SearchService, SearchResult
from rag.services.conv_manager import ConversationManager
@dataclass
class RAGResponse:
    answer: str
    used_context: bool
    context_sources: List[Dict[str, Any]]

class RAGService:
    def __init__(self, collection_name: str, redis_host: str = None, redis_port: int = None, redis_password: str = None):
        self.search_service = SearchService()
        self.collection_name = collection_name
        self.conversation_manager = ConversationManager(
            redis_host=redis_host,
            redis_port=redis_port,
            redis_password=redis_password
        )
        self.default_history_limit = 3  
        
    def get_limited_conversation_context(self, session_data: Dict[str, Any], history_limit: int = None) -> str:
        """
        Extract limited conversation context based on history_limit
        
        Args:
            session_data: Session data from conversation manager
            history_limit: Number of previous Q&A pairs to include (None uses default)
        
        Returns:
            Formatted conversation context string
        """
        if not session_data or not session_data.get('messages'):
            return ""
        
        limit = history_limit if history_limit is not None else self.default_history_limit
        
        messages = session_data['messages']
        limited_messages = messages[-limit:] if limit > 0 else []
        
        conversation_parts = []
        for msg_pair in limited_messages:
            query_content = msg_pair.get('query', {}).get('content', '')
            answer_content = msg_pair.get('answer', {}).get('content', '')
            count = msg_pair.get('count', 0)
            
            conversation_parts.append(f"Q{count}: {query_content}")
            conversation_parts.append(f"A{count}: {answer_content}")
        
        return "\n".join(conversation_parts)
    
    def create_relevance_check_prompt(self, query: str, contexts: List[SearchResult], conversation_context: str = "") -> str:
        contexts_text = ""
        for i, context in enumerate(contexts, 1):
            text_sample = context.text[:800] if len(context.text) > 800 else context.text
            contexts_text += f"Context {i}:\n{text_sample}...\n\n"
        
        context_section = ""
        if conversation_context:
            context_section = f"\nConversation History:\n{conversation_context}\n"
        
        return f"""
Analyze if the provided contexts are relevant to answer the user's query.

User Query: "{query}"{context_section}

Retrieved Contexts:
{contexts_text}

Determine if these contexts contain information that can help answer the user's query, considering the conversation history if provided.

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
    
    def create_answer_generation_prompt(self, query: str, contexts: List[SearchResult], conversation_context: str = "") -> str:
        contexts_text = ""
        for i, context in enumerate(contexts, 1):
            contexts_text += f"Context {i}:\n{context.text}\n\n"
        
        context_section = ""
        if conversation_context:
            context_section = f"\nConversation History:\n{conversation_context}\n"
        
        return f"""
You are having a conversation with a user. Use the provided contexts and conversation history to answer the user's current query.

Current User Query: "{query}"{context_section}

Available Knowledge Contexts:
{contexts_text}

Instructions:
- Use the conversation history to understand the full context of the current question
- If the user refers to "my previous query" or similar references, look at the conversation history
- Answer based on both the retrieved contexts and the conversation flow
- If the query is asking about previous conversation, reference the conversation history directly
- Be conversational and acknowledge the ongoing discussion
- Don't mention "Context 1" or "Context 2" - be natural in your response
- If asking about previous queries, be specific about what they asked before

Answer:"""
    
    def check_context_relevance(self, query: str, contexts: List[SearchResult], conversation_context: str = "") -> bool:
        if not contexts:
            return False
        
        try:
            prompt = self.create_relevance_check_prompt(query, contexts, conversation_context)
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
    
    def check_relevance_and_conflicts_concurrent(self, query: str, contexts: List[SearchResult], conversation_context: str = "") -> Tuple[bool, Optional[str]]:
        is_relevant = False
        conflict_response = None
        
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                relevance_future = executor.submit(self.check_context_relevance, query, contexts, conversation_context)
                conflict_future = executor.submit(self.detect_conflicts, contexts)
                
                concurrent.futures.wait([relevance_future, conflict_future])
                
                is_relevant = relevance_future.result()
                conflict_response = conflict_future.result()
                
        except Exception as e:
            print(f"Error in concurrent processing: {e}")
            is_relevant = self.check_context_relevance(query, contexts, conversation_context)
            if is_relevant:
                conflict_response = self.detect_conflicts(contexts)
        
        if not is_relevant:
            conflict_response = None
            
        return is_relevant, conflict_response
    
    def generate_direct_answer(self, query: str, conversation_context: str = "") -> Tuple[str, str]:
        context_section = ""
        if conversation_context:
            context_section = f"\n\nConversation History:\n{conversation_context}"
        
        prompt = f"""
    You are having a conversation with a user. Answer their current question using the conversation history for context.

    Current Question: "{query}"{context_section}

    Instructions:
    - If the user asks about their previous question/query (using words like "previous", "earlier", "before", "last", "what did I ask", "my last question", etc.):
    * If there IS conversation history: Look at it and tell them specifically what they asked before
    * If there is NO conversation history: Tell them this is their first question in the conversation
    - If they reference something from our previous conversation, use the conversation history to provide context
    - Be conversational and natural in your response
    - If there's no relevant conversation history for their question, answer the question directly
    - Always prioritize answering based on the conversation context when the user is clearly referencing previous interactions

    Provide your response in this format:
    Answer: [Your detailed answer here]
    Summary: [A brief 1-2 sentence summary of the answer]
    """
        
        try:
            response = self.search_service.gemini_client.generate_text(prompt, temperature=0.7)
            response_text = self._extract_text_from_response(response)
            
            if response_text:
                lines = response_text.strip().split('\n')
                answer = ""
                summary = ""
                
                for line in lines:
                    if line.startswith("Answer:"):
                        answer = line.replace("Answer:", "").strip()
                    elif line.startswith("Summary:"):
                        summary = line.replace("Summary:", "").strip()
                
                if not answer:
                    answer = response_text.strip()
                    summary = answer[:100] + "..." if len(answer) > 100 else answer
                
                return answer, summary
            else:
                default_answer = "I apologize, but I'm unable to provide an answer at this time."
                return default_answer, default_answer
        except Exception as e:
            print(f"Error generating direct answer: {e}")
            default_answer = "I apologize, but I'm unable to provide an answer at this time due to a technical issue."
            return default_answer, default_answer

    def generate_context_based_answer(self, query: str, contexts: List[SearchResult], conversation_context: str = "") -> Tuple[str, str]:
        try:
            contexts_text = ""
            for i, context in enumerate(contexts, 1):
                contexts_text += f"Context {i}:\n{context.text}\n\n"
            
            context_section = ""
            if conversation_context:
                context_section = f"\nConversation History:\n{conversation_context}\n"
            
            prompt = f"""
    You are having a conversation with a user. Use the provided contexts and conversation history to answer the user's current query.

    Current User Query: "{query}"{context_section}

    Available Knowledge Contexts:
    {contexts_text}

    Instructions:
    - PRIORITY: If the user is asking about their previous question/query (using words like "previous", "earlier", "before", "last", "what did I ask", "my last question", etc.), use the conversation history to tell them specifically what they asked before
    - Use the conversation history to understand the full context of the current question
    - If the user refers to something from our previous conversation, reference the conversation history directly
    - Answer based on both the retrieved contexts and the conversation flow
    - Be conversational and acknowledge the ongoing discussion
    - Don't mention "Context 1" or "Context 2" - be natural in your response
    - Always prioritize conversation context when the user is clearly referencing previous interactions

    Provide your response in this format:
    Answer: [Your detailed answer here]
    Summary: [A brief 1-2 sentence summary of the answer]
    """
            
            response = self.search_service.gemini_client.generate_text(prompt, temperature=0.3)
            response_text = self._extract_text_from_response(response)
            
            if response_text:
                lines = response_text.strip().split('\n')
                answer = ""
                summary = ""
                
                for line in lines:
                    if line.startswith("Answer:"):
                        answer = line.replace("Answer:", "").strip()
                    elif line.startswith("Summary:"):
                        summary = line.replace("Summary:", "").strip()
                
                if not answer:
                    answer = response_text.strip()
                    summary = answer[:100] + "..." if len(answer) > 100 else answer
                
                return answer, summary
            else:
                return self.generate_direct_answer(query, conversation_context)
        except Exception as e:
            print(f"Error generating context-based answer: {e}")
            return self.generate_direct_answer(query, conversation_context)
        
    def _extract_text_from_response(self, response) -> str:
        try:
            if hasattr(response, '__iter__') and not isinstance(response, str):
                return ''.join(str(chunk) for chunk in response)
            else:
                return str(response)
        except Exception as e:
            print(f"Error extracting text from response: {e}")
            return ""
    
    def clean_search_filters(self, search_results) -> List[SearchResult]:
        return search_results  
    
    def set_default_history_limit(self, limit: int):
        self.default_history_limit = limit
        print(f"Default conversation history limit set to: {limit}")

        # Updated query method - Remove the problematic first query checks
    def query(
        self, 
        user_query: str,
        session_id: str,
        search_limit: int = 5,
        score_threshold: float = 0.6,
        conversation_history_limit: int = 3
    ) -> RAGResponse:   
        metadata, enhanced_query = self.search_service.extract_metadata_and_enhance_query(user_query)

        try:
            if not session_id:
                session_data = self.conversation_manager.create_session()
                session_id = session_data['session_id']
                print(f"Created new session: {session_id}")
            elif not self.conversation_manager.session_exists(session_id):
                print(f"Session {session_id} doesn't exist, creating new one")
                session_data = self.conversation_manager.create_session()
                session_id = session_data['session_id']
            else:
                print(f"Using existing session: {session_id}")
        
            history_limit = conversation_history_limit if conversation_history_limit is not None else self.default_history_limit
            print(f"Using conversation history limit: {history_limit}")
        
            print(f"Starting RAG Service for query: '{user_query}' (session: {session_id})")

            print("Step 1: Searching vector database...")
            search_results = self.search_service.search(
                query=enhanced_query,
                collection_name=self.collection_name,
                limit=search_limit, 
            )

            print(f"Found {len(search_results)} potential contexts")

            # Get session data once at the beginning
            get_session = self.conversation_manager.get_session(session_id)
            conversation_context = self.get_limited_conversation_context(get_session, history_limit) if get_session and get_session.get('messages') else ""

            if not search_results:
                print("No contexts found, using direct LLM response")
                answer, summary = self.generate_direct_answer(user_query, conversation_context)
        
                print(f"Storing assistant response in session {session_id}")
                self.conversation_manager.add_message(session_id, enhanced_query, answer, metadata, summary)
            
                return RAGResponse(
                    answer=answer,
                    used_context=False,
                    context_sources=[{"reason": "no_contexts_found"}]
                )

            print("Step 2: Checking context relevance and conflicts concurrently...")
            high_score_results = [r for r in search_results if r.score >= score_threshold]
            print(f"Results with score >= {score_threshold}: {len(high_score_results)}")
        
            is_relevant, conflict_response = self.check_relevance_and_conflicts_concurrent(
                user_query, search_results, conversation_context
            )

            if not is_relevant and high_score_results:
                print(f"Relevance check said NOT_RELEVANT, but found {len(high_score_results)} high-scoring results. Using score-based fallback.")
                is_relevant = True
                search_results = high_score_results

            if not is_relevant:
                print("Contexts not relevant, using direct LLM response")
                answer, summary = self.generate_direct_answer(user_query, conversation_context)
            
                self.conversation_manager.add_message(session_id, enhanced_query, answer, metadata, summary)
        
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
            answer, summary = self.generate_context_based_answer(user_query, resolved_contexts, conversation_context)
        
            self.conversation_manager.add_message(session_id, enhanced_query, answer, metadata, summary)

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
            import traceback
            traceback.print_exc()
        
            return RAGResponse(
                answer="I apologize, but I'm unable to provide an answer at this time due to a technical issue.",
                used_context=False,
                context_sources=[{"reason": f"error_occurred: {str(e)}"}]
            )