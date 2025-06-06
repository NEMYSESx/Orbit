import json
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from rag.models.gemini_client import GeminiClient
from rag.models.qdrant_client import SimpleQdrantClient

@dataclass
class SearchResult:
    score: float
    payload: Dict[str, Any]
    text: str

class MetadataSearchService:
    def __init__(self):
        self.gemini_client = GeminiClient()
        self.qdrant_client = SimpleQdrantClient()
        
        self.metadata_schema = {
            "category": ["technical", "business", "general", "academic"],
            "complexity": ["basic", "moderate", "advanced", "expert"],
            "document_type": ["application/pdf", "text/plain", "application/json", "text/html"],
            "language": ["en", "es", "fr", "de", "zh", "ja"],
            "sentiment": ["positive", "negative", "neutral"],
            "topic": "string",  
            "entities": "list",  
            "keywords": "list" 
        }
    
    def _create_metadata_extraction_prompt(self, query: str) -> str:
        return f"""
Analyze the following user query and extract relevant metadata that could be used for filtering search results.

User Query: "{query}"

Extract metadata based on this schema:
- category: {self.metadata_schema['category']} (choose most relevant)
- complexity: {self.metadata_schema['complexity']} (infer from query sophistication)
- document_type: {self.metadata_schema['document_type']} (if query mentions specific file types)
- language: {self.metadata_schema['language']} (language of the query)
- sentiment: {self.metadata_schema['sentiment']} (overall tone of the query)
- topic: (main topic/subject area as a string)
- entities: (list of specific names, tools, technologies, people mentioned)
- keywords: (list of 3-5 key terms for search)

Also provide an "enhanced_query" - a semantically improved version of the original query, stripped of metadata phrases and optimized for embedding-based search.

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
    "enhanced_query": "semantically enhanced version of the query"
}}

Only include metadata fields that are clearly identifiable from the query. Use null for uncertain fields.
"""
    
    def _extract_metadata_and_enhance_query(self, query: str) -> Tuple[Dict[str, Any], str]:
        try:
            prompt = self._create_metadata_extraction_prompt(query)
            response = self.gemini_client.generate_text(prompt, temperature=0.3)
            
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                metadata = result.get("metadata", {})
                enhanced_query = result.get("enhanced_query", query)
                
                cleaned_metadata = self._validate_and_clean_metadata(metadata)
                
                return cleaned_metadata, enhanced_query
            else:
                print("Warning: Could not extract JSON from LLM response")
                return {}, query
                
        except Exception as e:
            print(f"Error in metadata extraction: {e}")
            return {}, query
    
    def _validate_and_clean_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = {}
        
        for key, value in metadata.items():
            if value is None or value == "":
                continue
                
            if key in self.metadata_schema:
                schema_type = self.metadata_schema[key]
                
                if isinstance(schema_type, list):
                    if value in schema_type:
                        cleaned[key] = value
                    else:
                        print(f"Warning: Invalid value '{value}' for {key}, skipping")
                elif schema_type == "string":
                    if isinstance(value, str) and len(value.strip()) > 0:
                        cleaned[key] = value.strip()
                elif schema_type == "list":
                    if isinstance(value, list) and len(value) > 0:
                        clean_list = [item.strip() for item in value if isinstance(item, str) and len(item.strip()) > 0]
                        if clean_list:
                            cleaned[key] = clean_list
            else:
                print(f"Warning: Unknown metadata key '{key}', skipping")
        
        return cleaned
    
    def search(
        self, 
        query: str, 
        collection_name: str,
        limit: int = 10,
        additional_filters: Optional[Dict[str, Any]] = None,
        fallback_strategy: str = "progressive"
    ) -> List[SearchResult]:
        print(f"Processing query: '{query}'")
        
        metadata, enhanced_query = self._extract_metadata_and_enhance_query(query)        
        try:
            query_vector = self.gemini_client.generate_embedding(enhanced_query)
        except Exception as e:
            print(f"Error generating embedding: {e}")
            return []
        
        results = self._search_with_fallback(
            collection_name, query_vector, metadata, additional_filters, 
            limit, fallback_strategy
        )
        
        return results
    
    def _search_with_fallback(
        self,
        collection_name: str,
        query_vector: List[float],
        metadata: Dict[str, Any],
        additional_filters: Optional[Dict[str, Any]],
        limit: int,
        strategy: str
    ) -> List[SearchResult]:
        all_filters = {}
        if metadata:
            all_filters.update(metadata)
        if additional_filters:
            all_filters.update(additional_filters)
        
        if strategy == "progressive":
            return self._progressive_search(collection_name, query_vector, all_filters, limit)
        elif strategy == "strict":
            return self._strict_search(collection_name, query_vector, all_filters, limit)
        else:  
            return self._open_search(collection_name, query_vector, limit)
    
    def _progressive_search(
        self, 
        collection_name: str, 
        query_vector: List[float], 
        filters: Dict[str, Any], 
        limit: int
    ) -> List[SearchResult]:
        if not filters:
            return self._execute_search(collection_name, query_vector, None, limit)
        
        print(f"Trying search with all filters: {filters}")
        results = self._execute_search(collection_name, query_vector, filters, limit)
        
        if results:
            return results
        
        fallback_order = ["document_type", "sentiment", "complexity", "category"]
        current_filters = filters.copy()
        
        for filter_to_remove in fallback_order:
            if filter_to_remove in current_filters:
                current_filters.pop(filter_to_remove)
                
                results = self._execute_search(collection_name, query_vector, current_filters, limit)
                if results:
                    return results
        
        return self._execute_search(collection_name, query_vector, None, limit)
    
    def _strict_search(
        self, 
        collection_name: str, 
        query_vector: List[float], 
        filters: Dict[str, Any], 
        limit: int
    ) -> List[SearchResult]:
        if not filters:
            return []
        
        return self._execute_search(collection_name, query_vector, filters, limit)
    
    def _open_search(
        self, 
        collection_name: str, 
        query_vector: List[float], 
        limit: int
    ) -> List[SearchResult]:
        return self._execute_search(collection_name, query_vector, None, limit)
    
    def _execute_search(
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
                filter_conditions=filters
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
    
    def explain_search(self, query: str) -> Dict[str, Any]:
        metadata, enhanced_query = self._extract_metadata_and_enhance_query(query)
        
        return {
            "original_query": query,
            "extracted_metadata": metadata,
            "enhanced_query": enhanced_query,
            "would_filter_by": list(metadata.keys()) if metadata else "No filters",
            "search_strategy": "Semantic similarity search with metadata filtering"
        }

