from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from rag.models.gemini_client import GeminiClient
from rag.models.qdrant_client import MyQdrantClient
import re,json

@dataclass
class SearchResult:
    score: float
    payload: Dict[str, Any]
    text: str

class SearchService:
    def __init__(self):
        self.gemini_client = GeminiClient()
        self.qdrant_client = MyQdrantClient()
        
    def metadata_extraction_prompt(self, query: str) -> str:
        return f"""
You are a metadata extraction expert. Analyze this user query and create the most useful metadata structure for search and filtering.

User Query: "{query}"

Extract metadata based on this schema:
- category: What domain/category does this belong to? (choose most relevant)
- complexity: What's the complexity level? (infer from query sophistication)
- document_type: if query mentions specific file types
- language: language of the query
- sentiment: overall tone of the query
- topic: main topic/subject area as a string
- entities: list of specific names, tools, technologies, people mentioned
- keywords: list of 3-5 key terms for search

Also provide an "enhanced_query" - a semantically improved version that:
1. Expands abbreviated terms or unclear references
2. Adds relevant synonyms for better matching
3. Optimizes for embedding-based search

Return your response as valid JSON in this format:
{{
    "metadata": {{
        "category": "value_or_null",
        "complexity": "value_or_null", 
        "document_type": "value_or_null",
        "language": "value_or_null",
        "sentiment": "value_or_null",
        "topic": "value_or_null",
        "entities": ["entity1", "entity2"] or null,
        "keywords": ["keyword1", "keyword2", "keyword3"] or null
    }},
    "enhanced_query": "enhanced version of the query"
}}

Only include metadata fields that are clearly identifiable. Use null for uncertain fields.
"""
    
    def extract_metadata_and_enhance_query(self, query: str) -> Tuple[Dict[str, Any], str]:
        try:
            prompt = self.metadata_extraction_prompt(query)
            response_generator = self.gemini_client.generate_text(prompt, temperature=0.3)
            
            response = ""
            for chunk in response_generator:
                response += chunk
        
            if not response.strip():
                print("Warning: Empty response from LLM")
                return {}, query
            
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                metadata = result.get("metadata", {})
                enhanced_query = result.get("enhanced_query", query)
                
                return metadata, enhanced_query
            else:
                print("Warning: Could not extract JSON from LLM response")
                return {}, query
                
        except Exception as e:
            print(f"Error in metadata extraction: {e}")
            return {}, query
    
    def search(
        self, 
        query: str, 
        collection_name: str,
        limit: int = 10,
        min_score: float = 0.5
    ) -> List[SearchResult]:
        print(f"Processing query: '{query}'")
        
        metadata, enhanced_query = self.extract_metadata_and_enhance_query(query)
        print(f"Enhanced query: '{enhanced_query}'")
        
        try:
            query_vector = self.gemini_client.generate_embedding(enhanced_query)
        except Exception as e:
            print(f"Error generating embedding: {e}")
            return []
        
        if metadata:
            if metadata:
                print(f"Trying search with filters: {metadata}")
                results = self.execute_search(collection_name, query_vector, metadata, limit)
                if results and any(result.score >= min_score for result in results):
                    return results
        
        print("Falling back to search without filters")
        return self.execute_search(collection_name, query_vector, None, limit)
    
    def execute_search(
        self, 
        collection_name: str, 
        query_vector: List[float], 
        filters: Optional[Dict[str, Any]], 
        limit: int
    ) -> List[SearchResult]:
        try:
            search_results = self.qdrant_client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
                filter_conditions=filters,
                hnsw_ef=256,         
                exact=False,         
                indexed_only=True    
            )
        
            formatted_results = []
            for result in search_results:
                formatted_results.append(SearchResult(
                    score=result.score,
                    payload=result.payload,
                    text=result.payload.get('text', '')
                ))
        
            return formatted_results
        
        except Exception as e:
            print(f"Error in vector search: {e}")
            return []