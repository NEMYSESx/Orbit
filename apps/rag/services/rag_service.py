from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import concurrent.futures
import traceback
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class RAGResponse:
    answer: str
    used_context: bool
    context_sources: List[Dict[str, Any]]

class RAGService:
    def __init__(self, collection_names: List[str], redis_host: str = None, redis_port: int = None, redis_password: str = None):
        try:
            from rag.services.search_service import SearchService
            from rag.services.conv_manager import ConversationManager
            
            self.search_service = SearchService()
            self.collection_names = collection_names 
            self.conversation_manager = ConversationManager(
                redis_host=redis_host,
                redis_port=redis_port,
                redis_password=redis_password
            )
            self.default_history_limit = 3
            logger.info("RAG Service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize RAG Service: {e}")
            raise
        
    def search_multiple_collections(self, enhanced_query: str, search_limit: int = 5) -> List:
        try:
            if not self.search_service:
                logger.error("Search service not initialized")
                return []
                
            return self.search_service.search_concurrent(
                query=enhanced_query,
                collection_names=self.collection_names,
                limit=search_limit
            )
        except Exception as e:
            logger.error(f"Error in search_multiple_collections: {e}")
            return []
        
    def get_limited_conversation_context(self, session_data: Dict[str, Any], history_limit: int = None) -> str:
        try:
            if not session_data or not session_data.get('messages'):
                return ""
            
            limit = history_limit if history_limit is not None else self.default_history_limit
            
            messages = session_data.get('messages', [])
            if not isinstance(messages, list):
                logger.warning("Messages is not a list, returning empty context")
                return ""
                
            limited_messages = messages[-limit:] if limit > 0 else []
            
            conversation_parts = []
            for i, msg_pair in enumerate(limited_messages):
                if not isinstance(msg_pair, dict):
                    continue
                    
                query_content = msg_pair.get('query', {}).get('content', '') if isinstance(msg_pair.get('query'), dict) else ''
                answer_content = msg_pair.get('answer', {}).get('content', '') if isinstance(msg_pair.get('answer'), dict) else ''
                count = msg_pair.get('count', i + 1)
                
                if query_content:
                    conversation_parts.append(f"Q{count}: {query_content}")
                if answer_content:
                    conversation_parts.append(f"A{count}: {answer_content}")
            
            return "\n".join(conversation_parts)
            
        except Exception as e:
            logger.error(f"Error getting conversation context: {e}")
            return ""
    
    def create_relevance_check_prompt(self, query: str, contexts: List, conversation_context: str = "") -> str:
        """Improved relevance check that better understands log analysis context"""
        try:
            if not contexts:
                return ""
                
            contexts_text = ""
            for i, context in enumerate(contexts, 1):
                if hasattr(context, 'text'):
                    text_sample = str(context.text)[:500]  # Increased sample size for better analysis
                    score = getattr(context, 'score', 0.0)
                    contexts_text += f"Log Entry {i} (Score: {score:.3f}):\n{text_sample}...\n\n"
            
            context_section = ""
            if conversation_context:
                context_section = f"\nConversation History:\n{conversation_context}\n"
            
            return f"""
    You are analyzing whether log entries and system data are relevant to answer a user's technical query.

    User Query: "{query}"

    Retrieved Log Entries:
    {contexts_text}

    Previous Conversation:
    {context_section}

    ANALYSIS INSTRUCTIONS:
    - If the user is asking about network issues, errors, or problems with a specific server/system, check if the log entries contain error messages, failures, or issues related to that server/system
    - If the user mentions a specific server name (like "mgmt01"), look for that server name or related errors in the log entries
    - Log entries about DNS failures, connection timeouts, network errors, or system failures are HIGHLY RELEVANT to network troubleshooting queries
    - Even if the log entries don't contain the exact server name, they may still be relevant if they describe similar network/system issues
    - Consider the semantic meaning - error logs are relevant to troubleshooting queries even if they don't match exact keywords

    Respond with only one of these:
    - "RELEVANT - [specific reason why the logs help answer the query]"
    - "NOT_RELEVANT - [specific reason why the logs don't help]"

    Examples:
    - RELEVANT - Log entries contain DNS resolution failures and network errors relevant to the user's network troubleshooting query
    - RELEVANT - Error logs show connection timeouts and failures that relate to the reported server issues
    - NOT_RELEVANT - Log entries are about database performance, unrelated to the network connectivity question
    """
        except Exception as e:
            logger.error(f"Error creating relevance check prompt: {e}")
            return ""
    
    def create_conflict_detection_prompt(self, contexts: List) -> str:
        try:
            if not contexts or len(contexts) <= 1:
                return ""
                
            contexts_text = ""
            for i, context in enumerate(contexts, 1):
                if hasattr(context, 'text'):
                    text_sample = str(context.text)[:500]
                    timestamp = getattr(context, 'payload', {}).get('timestamp', 'Unknown') if hasattr(context, 'payload') else 'Unknown'
                    contexts_text += f"Context {i} (Timestamp: {timestamp}):\n{text_sample}...\n\n"
            
            return f"""
Analyze if the provided contexts contain conflicting information.

Contexts:
{contexts_text}

Look for contradictory statements, opposing viewpoints, or conflicting facts between the contexts.

Respond with only "CONFLICT" or "NO_CONFLICT" followed by a brief explanation.

If CONFLICT is detected, identify which contexts conflict with each other.
"""
        except Exception as e:
            logger.error(f"Error creating conflict detection prompt: {e}")
            return ""
    
    def check_context_relevance(self, query: str, contexts: List, conversation_context: str = "") -> bool:
        if not contexts:
            return False
        
        try:
            prompt = self.create_relevance_check_prompt(query, contexts, conversation_context)
            if not prompt:
                return False
                
            if not hasattr(self.search_service, 'gemini_client') or not self.search_service.gemini_client:
                logger.error("Gemini client not available")
                return False
                
            response = self.search_service.gemini_client.generate_text(prompt, temperature=0.1)
            response_text = self._extract_text_from_response(response)
            
            is_relevant = response_text.strip().upper().startswith("RELEVANT")
            logger.info(f"Context relevance check: {'RELEVANT' if is_relevant else 'NOT_RELEVANT'}")
            return is_relevant
            
        except Exception as e:
            logger.error(f"Error in relevance check: {e}")
            return False
    
    def detect_conflicts(self, contexts: List) -> str:
        if not contexts or len(contexts) <= 1:
            return "NO_CONFLICT"
        
        try:
            prompt = self.create_conflict_detection_prompt(contexts)
            if not prompt:
                return "NO_CONFLICT"
                
            if not hasattr(self.search_service, 'gemini_client') or not self.search_service.gemini_client:
                logger.error("Gemini client not available for conflict detection")
                return "NO_CONFLICT"
                
            response = self.search_service.gemini_client.generate_text(prompt, temperature=0.1)
            response_text = self._extract_text_from_response(response)
            
            has_conflict = response_text.strip().upper().startswith("CONFLICT")
            logger.info(f"Conflict detection: {'CONFLICT DETECTED' if has_conflict else 'NO CONFLICT'}")
            return response_text
            
        except Exception as e:
            logger.error(f"Error in conflict detection: {e}")
            return "NO_CONFLICT"
    
    def resolve_conflicts(self, contexts: List) -> List:
        try:
            logger.info("Resolving conflicts using timestamps...")
            
            contexts_with_time = []
            for context in contexts:
                timestamp_str = ""
                if hasattr(context, 'payload') and isinstance(context.payload, dict):
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
            
            logger.info(f"Conflict resolved: Using {len(resolved_contexts)} most recent contexts")
            return resolved_contexts
            
        except Exception as e:
            logger.error(f"Error in conflict resolution: {e}")
            return contexts
    
    def check_relevance_and_conflicts_concurrent(self, query: str, contexts: List, conversation_context: str = "") -> Tuple[bool, Optional[str]]:
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
            logger.error(f"Error in concurrent processing: {e}")
            is_relevant = self.check_context_relevance(query, contexts, conversation_context)
            if is_relevant:
                conflict_response = self.detect_conflicts(contexts)
        
        if not is_relevant:
            conflict_response = None
            
        return is_relevant, conflict_response
    
    def generate_direct_answer(self, query: str, conversation_context: str = "") -> Tuple[str, str]:
        try:
            if not hasattr(self.search_service, 'gemini_client') or not self.search_service.gemini_client:
                logger.error("Gemini client not available for direct answer")
                return self._get_fallback_answer(), "Unable to generate answer"
            
            # Handle previous query questions
            previous_query_keywords = ["previous", "earlier", "before", "last", "what did I ask", "my last question", "my previous question"]
            is_asking_about_previous = any(keyword in query.lower() for keyword in previous_query_keywords)
            
            if is_asking_about_previous:
                if conversation_context:
                    lines = conversation_context.strip().split('\n')
                    last_query = ""
                    for line in reversed(lines):
                        if line.startswith('Q'):
                            last_query = line.split(':', 1)[1].strip() if ':' in line else ""
                            break
                    
                    if last_query:
                        return f"Your previous question was: \"{last_query}\"", "Previous query information"
                    else:
                        return "I can see we've been talking, but I'm having trouble identifying your specific previous question.", "Previous query unclear"
                else:
                    return "This is actually your first question in our conversation.", "First question"
            
            # Classify query type for appropriate response length
            greeting_keywords = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "how are you", "what's up"]
            simple_yes_no = ["yes", "no", "ok", "okay", "thanks", "thank you"]
            
            is_greeting = any(keyword in query.lower() for keyword in greeting_keywords)
            is_simple_response = any(keyword.strip().lower() == query.strip().lower() for keyword in simple_yes_no)
            
            # Determine if this is a technical/complex question that needs detailed response
            technical_indicators = [
                "what is", "what are", "how does", "how do", "explain", "describe", 
                "difference between", "compare", "why", "when", "where", "which",
                "algorithm", "database", "system", "architecture", "implementation",
                "tree", "data structure", "performance", "optimization", "design"
            ]
            
            is_technical = any(indicator in query.lower() for indicator in technical_indicators)
            is_complex = len(query.split()) > 5  # Longer queries usually need detailed answers
            
            # Build appropriate prompt based on query type
            if is_greeting or is_simple_response:
                prompt = f"""
    You are a helpful AI assistant. The user has sent a greeting or simple response.

    User's Message: "{query}"

    Respond naturally and conversationally in 1-2 sentences.

    Answer: [Your brief, friendly response]
    Summary: [Brief summary]
    """
            elif is_technical or is_complex:
                prompt = f"""
    You are a knowledgeable AI assistant with expertise in technology, databases, systems, and technical concepts.

    User's Technical Question: "{query}"

    Previous conversation context (for reference): {conversation_context if conversation_context else "No previous conversation"}

    INSTRUCTIONS:
    - This is a technical question that requires a comprehensive, detailed explanation
    - Provide a thorough answer with multiple paragraphs covering different aspects
    - Include definitions, explanations, examples, and practical context
    - Aim for 200-400 words to ensure completeness
    - Structure your response logically with clear explanations
    - If applicable, mention use cases, advantages, disadvantages, or comparisons

    Answer: [Your detailed, comprehensive technical explanation - minimum 200 words]
    Summary: [A brief 1-2 sentence summary of the key points]
    """
            else:
                # General questions - moderate detail
                prompt = f"""
    You are a helpful AI assistant with broad knowledge.

    User's Question: "{query}"

    Previous conversation context (for reference): {conversation_context if conversation_context else "No previous conversation"}

    Provide a helpful, informative response that thoroughly addresses the user's question. 
    Be comprehensive but concise, aiming for 100-200 words.

    Answer: [Your informative response]
    Summary: [Brief summary]
    """
            
            response = self.search_service.gemini_client.generate_text(prompt, temperature=0.7)
            response_text = self._extract_text_from_response(response)
            
            if response_text:
                answer, summary = self._parse_answer_response(response_text)
                logger.info(f"Direct answer generated - Type: {'greeting' if is_greeting else 'technical' if is_technical else 'general'}")
                return answer, summary
            else:
                return self._get_fallback_answer(), "Unable to generate answer"
                
        except Exception as e:
            logger.error(f"Error generating direct answer: {e}")
            return self._get_fallback_answer(), "Error generating answer"

    def generate_context_based_answer(self, query: str, contexts: List, conversation_context: str = "") -> Tuple[str, str]:
        try:
            if not contexts:
                return self.generate_direct_answer(query, conversation_context)
                
            if not hasattr(self.search_service, 'gemini_client') or not self.search_service.gemini_client:
                logger.error("Gemini client not available for context-based answer")
                return self._get_fallback_answer(), "Unable to generate answer"
            
            # Handle previous query questions
            previous_query_keywords = ["previous", "earlier", "before", "last", "what did I ask", "my last question", "my previous question"]
            is_asking_about_previous = any(keyword in query.lower() for keyword in previous_query_keywords)
            
            if is_asking_about_previous:
                if conversation_context:
                    lines = conversation_context.strip().split('\n')
                    last_query = ""
                    for line in reversed(lines):
                        if line.startswith('Q'):
                            last_query = line.split(':', 1)[1].strip() if ':' in line else ""
                            break
                    
                    if last_query:
                        return f"Your previous question was: \"{last_query}\"", "Previous query information"
                    else:
                        return "I can see we've been talking, but I'm having trouble identifying your specific previous question.", "Previous query unclear"
                else:
                    return "This is actually your first question in our conversation.", "First question"
            
            # Build contexts with better formatting and metadata
            contexts_text = ""
            relevant_logs = []
            error_patterns = []
            
            for i, context in enumerate(contexts, 1):
                if hasattr(context, 'text'):
                    context_text = str(context.text)
                    score = getattr(context, 'score', 0.0)
                    source = getattr(context, 'source_collection', 'Unknown')
                    
                    # Extract timestamp and other metadata if available
                    metadata_info = ""
                    if hasattr(context, 'payload') and isinstance(context.payload, dict):
                        timestamp = context.payload.get('timestamp', 'Unknown')
                        topic = context.payload.get('topic', 'Unknown')
                        metadata_info = f" | Timestamp: {timestamp} | Topic: {topic}"
                    
                    contexts_text += f"=== LOG ENTRY {i} ===\n"
                    contexts_text += f"Source: {source} | Relevance Score: {score:.3f}{metadata_info}\n"
                    contexts_text += f"Content: {context_text}\n\n"
                    
                    # Collect specific error information for analysis
                    if any(keyword in context_text.lower() for keyword in ['error', 'failed', 'timeout', 'unable', 'denied', 'exception']):
                        relevant_logs.append(context_text)
                        # Extract error patterns
                        if 'dns resolution failed' in context_text.lower():
                            error_patterns.append('DNS Resolution Failure')
                        elif 'connection timeout' in context_text.lower():
                            error_patterns.append('Connection Timeout')
                        elif 'network unreachable' in context_text.lower():
                            error_patterns.append('Network Unreachable')
            
            # Enhanced prompt that forces the LLM to analyze the actual logs first
            prompt = f"""
You are a technical support specialist analyzing server logs, system behavior, and technical documentation to resolve specific issues. You will receive either or both of the following:

1. **Log entries** containing real-time server/system events, warnings, and errors.
2. **Documentation** excerpts that include official descriptions, configuration guidance, and expected system behavior.

CRITICAL INSTRUCTION: 
- Your analysis MUST be rooted **primarily in the actual log entries or documentation excerpts provided**.
- DO NOT provide generic troubleshooting advice unless **neither the logs nor the docs contain relevant information**.

USER QUERY: "{query}"

RETRIEVED CONTEXT (Log Entries and/or Documentation):
{contexts_text}

ANALYSIS REQUIREMENTS:
1. **First**, examine the log entries for any relevant warnings, errors, or failed operations that relate to the user's query.
2. **Second**, explain what those specific log entries mean and what their likely causes are.
3. **Third**, provide **targeted, actionable troubleshooting steps** based on those actual log entries.
4. If technical documentation is provided and relevant to the query, analyze it as well:
   - Extract and explain applicable rules, constraints, or expected behaviors from the documentation.
   - Use it to either validate or challenge what the logs indicate.
5. If **neither the logs nor the docs** are relevant to the issue, then (and only then) provide general troubleshooting advice.

RESPONSE FORMAT:
Answer: 
- Clearly state what specific errors or insights were found in the logs and/or documentation.
- Reference log lines or document excerpts directly.
- Explain what they mean and how they relate to the user's issue.
- Provide specific steps to fix or further investigate the problem.
- If the query mentions a specific host/server (e.g., "mgmt01"), tie the findings to that host explicitly.

Summary: 
- A brief summary of the root cause and main recommendation based on the logs/docs.

IMPORTANT:
- Use the logs or documentation **as the primary source of truth**.
- Be specific and technical—avoid assumptions not grounded in the context.
- Treat documentation analysis with the same weight as log analysis: reference it, interpret it, and apply it to the query.
- If both logs and docs are available, correlate them to provide a more accurate and comprehensive diagnosis.

Previous Conversation Context (for reference only):
{conversation_context if conversation_context else "No previous conversation"}
"""

            
            response = self.search_service.gemini_client.generate_text(prompt, temperature=0.2)  # Lower temperature for more focused responses
            response_text = self._extract_text_from_response(response)
            
            if response_text:
                answer, summary = self._parse_answer_response(response_text)
                logger.info(f"Context-based answer generated with {len(contexts)} log entries")
                return answer, summary
            else:
                logger.warning("Failed to generate context-based answer, falling back to direct answer")
                return self.generate_direct_answer(query, conversation_context)
                
        except Exception as e:
            logger.error(f"Error generating context-based answer: {e}")
            return self.generate_direct_answer(query, conversation_context)

    
    def _parse_answer_response(self, response_text: str) -> Tuple[str, str]:
        try:
            lines = response_text.strip().split('\n')
            answer = ""
            summary = ""
            
            for line in lines:
                line = line.strip()
                if line.startswith("Answer:"):
                    answer = line.replace("Answer:", "").strip()
                elif line.startswith("Summary:"):
                    summary = line.replace("Summary:", "").strip()
            
            if not answer:
                answer = response_text.strip()
            
            if not summary:
                summary = answer[:500] + "..." if len(answer) > 100 else answer
            
            return answer, summary
            
        except Exception as e:
            logger.error(f"Error parsing answer response: {e}")
            return response_text.strip(), "Generated response"
    
    def _get_fallback_answer(self) -> str:
        return "I apologize, but I'm unable to provide an answer at this time due to a technical issue."
        
    def _extract_text_from_response(self, response) -> str:
        try:
            if response is None:
                return ""
            
            if isinstance(response, str):
                return response
            
            if hasattr(response, '__iter__') and not isinstance(response, (str, bytes)):
                return ''.join(str(chunk) for chunk in response)
            
            return str(response)
            
        except Exception as e:
            logger.error(f"Error extracting text from response: {e}")
            return ""
    
    def set_default_history_limit(self, limit: int):
        try:
            if not isinstance(limit, int) or limit < 0:
                logger.warning("Invalid history limit, using default value 3")
                limit = 3
            
            self.default_history_limit = limit
            logger.info(f"Default conversation history limit set to: {limit}")
            
        except Exception as e:
            logger.error(f"Error setting history limit: {e}")

    def query(
        self, 
        user_query: str,
        session_id: str,
        search_limit: int = 5,
        score_threshold: float = 0.6,
        conversation_history_limit: int = 3
    ) -> RAGResponse:        
        if not user_query or not isinstance(user_query, str):
            logger.error("Invalid user query provided")
            return RAGResponse(
                answer="Invalid query provided",
                used_context=False,
                context_sources=[{"reason": "invalid_query"}]
            )
        
        try:
            try:
                if hasattr(self.search_service, 'extract_metadata_and_enhance_query'):
                    metadata, enhanced_query = self.search_service.extract_metadata_and_enhance_query(user_query)
                else:
                    metadata = {}
                    enhanced_query = user_query
            except Exception as e:
                logger.error(f"Error extracting metadata: {e}")
                metadata = {}
                enhanced_query = user_query

            try:
                if not session_id:
                    session_data = self.conversation_manager.create_session()
                    session_id = session_data.get('session_id', 'default')
                    logger.info(f"Created new session: {session_id}")
                elif not self.conversation_manager.session_exists(session_id):
                    logger.info(f"Session {session_id} doesn't exist, creating new one")
                    session_data = self.conversation_manager.create_session()
                    session_id = session_data.get('session_id', session_id)
                else:
                    logger.info(f"Using existing session: {session_id}")
            except Exception as e:
                logger.error(f"Session management error: {e}")
                session_id = 'fallback_session'
            
            history_limit = conversation_history_limit if conversation_history_limit is not None else self.default_history_limit
            
            logger.info(f"Starting RAG Service for query: '{user_query}' (session: {session_id})")

            logger.info("Step 1: Searching multiple collections...")
            search_results = self.search_multiple_collections(enhanced_query, search_limit)
            print("[DEBUG] Retrieved contexts from vector DB:")
            for idx, ctx in enumerate(search_results, 1):
                print(f"Context {idx}: Score={getattr(ctx, 'score', None)}, Source={getattr(ctx, 'source_collection', None)}, Text={str(getattr(ctx, 'text', ''))[:300]}...")
            logger.info(f"Found {len(search_results)} potential contexts across all collections")

            try:
                get_session = self.conversation_manager.get_session(session_id)
                conversation_context = self.get_limited_conversation_context(get_session, history_limit) if get_session and get_session.get('messages') else ""
            except Exception as e:
                logger.error(f"Error getting conversation context: {e}")
                conversation_context = ""

            if not search_results:
                logger.info("No contexts found, using direct LLM response")
                answer, summary = self.generate_direct_answer(user_query, conversation_context)
                
                try:
                    self.conversation_manager.add_message(session_id, user_query, answer, metadata, summary)
                except Exception as e:
                    logger.error(f"Error storing message: {e}")
                
                return RAGResponse(
                    answer=answer,
                    used_context=False,
                    context_sources=[{"reason": "no_contexts_found"}]
                )

            logger.info("Step 2: Checking context relevance and conflicts concurrently...")
            high_score_results = [r for r in search_results if hasattr(r, 'score') and r.score >= score_threshold]
            logger.info(f"Results with score >= {score_threshold}: {len(high_score_results)}")
            
            is_relevant, conflict_response = self.check_relevance_and_conflicts_concurrent(
                user_query, search_results, conversation_context
            )

            if not is_relevant and high_score_results:
                logger.info(f"Relevance check said NOT_RELEVANT, but found {len(high_score_results)} high-scoring results. Using score-based fallback.")
                is_relevant = True
                search_results = high_score_results

            if not is_relevant:
                logger.info("Contexts not relevant, using direct LLM response")
                answer, summary = self.generate_direct_answer(user_query, conversation_context)
                
                try:
                    self.conversation_manager.add_message(session_id, user_query, answer, metadata, summary)
                except Exception as e:
                    logger.error(f"Error storing message: {e}")
                
                return RAGResponse(
                    answer=answer,
                    used_context=False,
                    context_sources=[{"reason": "contexts_not_relevant"}]
                )

            resolved_contexts = search_results
            if conflict_response and conflict_response.strip().upper().startswith("CONFLICT"):
                logger.info("Step 3: Resolving detected conflicts...")
                resolved_contexts = self.resolve_conflicts(search_results)

            logger.info("Step 4: Generating context-based answer...")
            answer, summary = self.generate_context_based_answer(user_query, resolved_contexts, conversation_context)
            print("The answer is",answer)
            
            try:
                self.conversation_manager.add_message(session_id, enhanced_query, answer, metadata, summary)
            except Exception as e:
                logger.error(f"Error storing message: {e}")

            context_sources = []
            for context in resolved_contexts:
                try:
                    context_info = {
                        "text": str(getattr(context, 'text', ''))[:1000] + "...",
                        "score": getattr(context, 'score', 0.0),
                        "source_collection": getattr(context, 'source_collection', 'Unknown')
                    }
                    
                    if hasattr(context, 'payload') and isinstance(context.payload, dict):
                        context_info.update({
                            "timestamp": context.payload.get('timestamp', 'Unknown'),
                            "topic": context.payload.get('topic', 'Unknown'),
                            "document_title": context.payload.get('document_title', 'Unknown')
                        })
                    
                    context_sources.append(context_info)
                    
                except Exception as e:
                    logger.error(f"Error building context source: {e}")
                    continue

            logger.info("RAG process completed successfully")
            print("The response is",answer)
            return RAGResponse(
                answer=answer,
                used_context=True,
                context_sources=context_sources
            )

        except Exception as e:
            logger.error(f"Critical error in RAG query process: {e}")
            logger.error(traceback.format_exc())
            
            return RAGResponse(
                answer=self._get_fallback_answer(),
                used_context=False,
                context_sources=[{"reason": f"error_occurred: {str(e)}"}]
            )