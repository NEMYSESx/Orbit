from typing import List, Dict, Any, Optional,Tuple
from dataclasses import dataclass
from rag.models.gemini_client import GeminiClient
from rag.models.qdrant_client import MyQdrantClient
import json
from datetime import datetime, timedelta
import concurrent.futures
import threading

@dataclass
class SearchResult:
    score: float
    payload: Dict[str, Any]
    text: str
    source_collection: str
    
    def __str__(self):
        if 'message' in self.payload:  
            level = self.payload.get('level', '')
            message = self.payload.get('message', '')
            timestamp = self.payload.get('timestamp', '')
            return f"[{self.source_collection}] {level} | {timestamp} | {message}"
        else:  
            title = self.payload.get('document_title', '')
            topic = self.payload.get('topic', '')
            return f"[{self.source_collection}] {title} | {topic} | {self.text[:100]}..."

class SearchService:
    def __init__(self):
        self.gemini_client = GeminiClient()
        self.qdrant_client = MyQdrantClient()
        
        self.collection_filters = {
            'logs': {'level', 'source', 'type', 'time_range'},
            'documents': {'category', 'complexity', 'topic', 'time_range', 'document_type', 'language', 'sentiment'}
        }
    
    def extract_filters(self, query: str) -> Dict[str, Any]:
        prompt = f"""
Extract search filters from this query for a system with logs and documents.

Query: "{query}"

Extract only clear, specific filters. Return JSON with these fields (use null if not mentioned):

For LOGS:
- level: ERROR, WARN, INFO, DEBUG 
- source: system/service name (e.g., "network-generator")
- type: network, application, system

For DOCUMENTS:
- category: technical, business
- complexity: simple, moderate, complex
- topic: main subject area
- document_type: application/pdf, text/plain, etc.
- language: english, spanish, etc.
- sentiment: positive, negative, neutral

For BOTH:
- time_range: today, yesterday, last_week

JSON format:
{{"level": null, "source": null, "type": null, "category": null, "complexity": null, "topic": null, "document_type": null, "language": null, "sentiment": null, "time_range": null}}
"""
        
        try:
            response = ""
            for chunk in self.gemini_client.generate_text(prompt, temperature=0.1):
                response += chunk
            
            start = response.find('{')
            end = response.rfind('}') + 1
            if start != -1 and end != 0:
                filters = json.loads(response[start:end])
                return {k: v for k, v in filters.items() if v is not None}
        except Exception as e:
            print(f"Filter extraction error: {e}")
        
        return {}
    
    def get_available_filters(self, collection_name: str) -> Dict[str, List[str]]:
        filter_values = {
            'logs': {
                'level': ['ERROR', 'WARN', 'INFO', 'DEBUG'],
                'source': ['network-generator', 'app-server', 'database'],  
                'type': ['network', 'application', 'system'],
                'time_range': ['today', 'yesterday', 'last_week']
            },
            'documents': {
                'category': ['technical', 'business'],
                'complexity': ['simple', 'moderate', 'complex'],
                'topic': [],  
                'document_type': ['application/pdf', 'text/plain', 'text/html'],
                'language': ['english', 'spanish', 'french'],
                'sentiment': ['positive', 'negative', 'neutral'],
                'time_range': ['today', 'yesterday', 'last_week']
            }
        }
        return filter_values.get(collection_name, {})
    
    def filter_for_collection(self, filters: Dict[str, Any], collection_name: str) -> Dict[str, Any]:
        valid_filters = self.collection_filters.get(collection_name, set())
        return {k: v for k, v in filters.items() if k in valid_filters}
    
    def build_time_filter(self, time_range: str) -> Dict[str, str]:
        now = datetime.now()
        
        if time_range == "today":
            return {"gte": now.strftime("%Y-%m-%d") + "T00:00:00Z"}
        elif time_range == "yesterday":
            yesterday = now - timedelta(days=1)
            return {
                "gte": yesterday.strftime("%Y-%m-%d") + "T00:00:00Z",
                "lt": now.strftime("%Y-%m-%d") + "T00:00:00Z"
            }
        elif time_range == "last_week":
            return {"gte": (now - timedelta(days=7)).strftime("%Y-%m-%d") + "T00:00:00Z"}
        
        return {}
    
    def search_collection(
        self, 
        collection_name: str, 
        query_vector: List[float], 
        filters: Dict[str, Any], 
        limit: int
    ) -> List[SearchResult]:
        
        valid_filters = self.filter_for_collection(filters, collection_name)
        print(f"Filtered filters for {collection_name}: {valid_filters}")
        
        filter_conditions = {}
        for key, value in valid_filters.items():
            if key == "time_range":
                time_filter = self.build_time_filter(value)
                if time_filter:
                    filter_conditions["timestamp"] = time_filter
            else:
                filter_conditions[key] = value
        
        try:
            if filter_conditions:
                search_results = self.qdrant_client.search(
                    collection_name=collection_name,
                    query_vector=query_vector,
                    limit=limit,
                    filter_conditions=filter_conditions,
                    hnsw_ef=256,
                    exact=False,
                    indexed_only=True
                )
            else:
                search_results = self.qdrant_client.search(
                    collection_name=collection_name,
                    query_vector=query_vector,
                    limit=limit,
                    filter_conditions=None,
                    hnsw_ef=256,
                    exact=False,
                    indexed_only=True
                )
            
            results = []
            for result in search_results:
                if 'message' in result.payload:  
                    text = result.payload['message']
                elif 'text' in result.payload:  
                    text = result.payload['text']
                elif 'summary' in result.payload:  
                    text = result.payload['summary']
                else:
                    text = str(result.payload)
                
                results.append(SearchResult(
                    score=result.score,
                    payload=result.payload,
                    text=text,
                    source_collection=collection_name
                ))
            
            return results
            
        except Exception as e:
            print(f"Search error in {collection_name}: {e}")
            try:
                search_results = self.qdrant_client.search(
                    collection_name=collection_name,
                    query_vector=query_vector,
                    limit=limit,
                    filter_conditions=None,
                    hnsw_ef=256,
                    exact=False,
                    indexed_only=True
                )
                
                results = []
                for result in search_results:
                    if 'message' in result.payload:
                        text = result.payload['message']
                    elif 'text' in result.payload:
                        text = result.payload['text']
                    elif 'summary' in result.payload:
                        text = result.payload['summary']
                    else:
                        text = str(result.payload)
                    
                    results.append(SearchResult(
                        score=result.score,
                        payload=result.payload,
                        text=text,
                        source_collection=collection_name
                    ))
                
                return results
                
            except Exception as e:
                print(f"Fallback search failed for {collection_name}: {e}")
                return []
            
    def extract_metadata_and_enhance_query(self, query: str) -> Tuple[Dict[str, Any], str]:
    
        try:
            prompt = f"""
    Analyze this user query and extract metadata, then enhance it for better search.

    Original Query: "{query}"

    Extract the following metadata (use null if not present):
    - intent: question, request, complaint, information_seeking, troubleshooting
    - urgency: low, medium, high, critical
    - time_context: current, historical, future, specific_date
    - technical_complexity: basic, intermediate, advanced
    - domain: technical, business, general, logs, documentation

    Then enhance the query by:
    1. Adding relevant synonyms and related terms
    2. Expanding abbreviations
    3. Adding context keywords
    4. Making implicit concepts explicit

    Respond in this exact JSON format:
    {{
        "metadata": {{
            "intent": "...",
            "urgency": "...",
            "time_context": "...",
            "technical_complexity": "...",
            "domain": "..."
        }},
        "enhanced_query": "enhanced version of the query with additional relevant terms and context"
    }}
    """
            
            response = ""
            for chunk in self.gemini_client.generate_text(prompt, temperature=0.1):
                response += chunk
            
            # Extract JSON from response
            start = response.find('{')
            end = response.rfind('}') + 1
            if start != -1 and end != 0:
                result = json.loads(response[start:end])
                metadata = result.get('metadata', {})
                enhanced_query = result.get('enhanced_query', query)
                
                # Clean up metadata - remove null values
                metadata = {k: v for k, v in metadata.items() if v is not None and v != "null"}
                
                # Fallback to original query if enhancement is too similar or empty
                if not enhanced_query or enhanced_query.strip() == query.strip():
                    enhanced_query = query
                
                print(f"Original query: {query}")
                print(f"Enhanced query: {enhanced_query}")
                print(f"Extracted metadata: {metadata}")
                
                return metadata, enhanced_query
                
        except Exception as e:
            print(f"Query enhancement error: {e}")
            return {}, query
        
        return {}, query
    
    def search_concurrent(
        self, 
        query: str, 
        collection_names: List[str],
        limit: int = 10
    ) -> List[SearchResult]:
        
        print(f"Searching query: '{query}'")
        print(f"Searching collections: {collection_names}")
        
        filters = self.extract_filters(query)
        print(f"Extracted filters: {filters}")
        
        try:
            query_vector = self.gemini_client.generate_embedding(query)
        except Exception as e:
            print(f"Embedding generation error: {e}")
            return []
        
        results_lock = threading.Lock()
        all_results = []
        
        def search_single_collection(collection_name: str) -> None:
            try:
                collection_results = self.search_collection(
                    collection_name, 
                    query_vector, 
                    filters, 
                    limit
                )
                
                with results_lock:
                    all_results.extend(collection_results)
                    print(f"Found {len(collection_results)} results in {collection_name}")
                    
            except Exception as e:
                print(f"Error searching collection {collection_name}: {e}")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(collection_names)) as executor:
            future_to_collection = {
                executor.submit(search_single_collection, collection_name): collection_name
                for collection_name in collection_names
            }
            
            for future in concurrent.futures.as_completed(future_to_collection):
                collection_name = future_to_collection[future]
                try:
                    future.result()  
                except Exception as e:
                    print(f"Thread execution error for {collection_name}: {e}")
        
        print(f"Total results found: {len(all_results)}")
        
        all_results.sort(key=lambda x: x.score, reverse=True)
        
        return all_results[:limit]
    
    def search_logs_only(
        self, 
        query: str, 
        collection_name: str, 
        level: Optional[str] = None,
        source: Optional[str] = None,
        log_type: Optional[str] = None,
        limit: int = 10
    ) -> List[SearchResult]:
        
        filters = self.extract_filters(query)
        
        if level:
            filters['level'] = level.upper()
        if source:
            filters['source'] = source
        if log_type:
            filters['type'] = log_type
        
        try:
            query_vector = self.gemini_client.generate_embedding(query)
        except Exception as e:
            print(f"Embedding generation error: {e}")
            return []
        
        return self.search_collection(collection_name, query_vector, filters, limit)
    
    def search_docs_only(
        self, 
        query: str, 
        collection_name: str, 
        category: Optional[str] = None,
        complexity: Optional[str] = None,
        topic: Optional[str] = None,
        limit: int = 10
    ) -> List[SearchResult]:
        
        filters = self.extract_filters(query)
        
        if category:
            filters['category'] = category
        if complexity:
            filters['complexity'] = complexity
        if topic:
            filters['topic'] = topic
        
        try:
            query_vector = self.gemini_client.generate_embedding(query)
        except Exception as e:
            print(f"Embedding generation error: {e}")
            return []
        
        return self.search_collection(collection_name, query_vector, filters, limit)
    
    def format_results(self, results: List[SearchResult]) -> str:
        if not results:
            return "No results found."
        
        output = [f"Found {len(results)} results:\n"]
        
        for i, result in enumerate(results, 1):
            output.append(f"{i}. {result}")
            output.append(f"   Score: {result.score:.3f}")
            
            if 'message' in result.payload:  
                if 'details' in result.payload:
                    output.append(f"   Details: {result.payload['details']}")
            else:  
                if 'category' in result.payload:
                    output.append(f"   Category: {result.payload['category']}")
                if 'complexity' in result.payload:
                    output.append(f"   Complexity: {result.payload['complexity']}")
            
            output.append("")  
        
        return "\n".join(output)