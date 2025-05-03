import re
import json
import textwrap
import os
import sys
import google.generativeai as genai
from typing import List, Dict, Any, Optional
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from models.embeddings import EmbeddingModel  
from models.qdrant_client import QdrantClientWrapper

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)
from config import settings

class SearchService:
    """Service for searching data in Qdrant."""
    
    def __init__(
        self,
        qdrant_client: QdrantClientWrapper = None,
        embedding_model: EmbeddingModel = None
    ):
        """
        Initialize the search service.
        
        Args:
            qdrant_client: Qdrant client wrapper
            embedding_model: Embedding model
        """
        self.qdrant_client = qdrant_client or QdrantClientWrapper()
        self.embedding_model = embedding_model or EmbeddingModel()
    
    def search(
        self, 
        query_text: str,
        collection_name: str = settings.DEFAULT_COLLECTION_NAME,
        limit: int = 5,
        gemini_api_key: Optional[str] = None,
        rerank: bool = True,
        filter_conditions: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        """
        Search for documents in Qdrant and optionally rerank with Gemini.
        
        Args:
            query_text: Query text
            collection_name: Name of the collection to search
            limit: Maximum number of results to return
            gemini_api_key: API key for Gemini
            rerank: Whether to use Gemini to rerank results
            filter_conditions: Optional filter conditions for search
            
        Returns:
            List of search results
        """
        try:
            print(f"\nPerforming search in '{collection_name}' for: '{query_text}'")
            
            query_vector = self.embedding_model.encode(query_text).tolist()
            
            search_limit = limit * 3 if rerank else limit
            
            search_results = self.qdrant_client.search(
                collection_name,
                query_vector,
                limit=search_limit,
                filter_conditions=filter_conditions
            )
            
            if not search_results:
                print("No results found.")
                return []
            
            if rerank:
                search_results = self._rerank_with_gemini(
                    search_results,
                    query_text,
                    limit,
                    gemini_api_key
                )
            else:
                search_results = search_results[:limit]
                
            print(f"Search results:")
            for idx, result in enumerate(search_results[:limit]):
                print(f"Result #{idx+1}")
                print(f"ID: {result.id}, Score: {result.score:.4f}")
                print(f"Text: {textwrap.shorten(result.payload.get('text', ''), width=200, placeholder='...')}")
                metadata = {k: v for k, v in result.payload.items() if k != 'text'}
                if metadata:
                    print(f"Metadata: {', '.join([f'{k}: {v}' for k, v in metadata.items()])}")
                print()
                
            return search_results
                
        except Exception as e:
            print(f"Search error: {str(e)}")
            return []
    
    def _rerank_with_gemini(
        self, 
        search_results: List[Any], 
        query_text: str, 
        limit: int,
        gemini_api_key: Optional[str] = None
    ) -> List[Any]:
        """
        Rerank search results using Gemini.
        
        Args:
            search_results: List of search results
            query_text: Original query text
            limit: Maximum number of results to return
            gemini_api_key: API key for Gemini
            
        Returns:
            Reranked search results
        """
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
        else:
            gemini_api_key = os.environ.get("GEMINI_API_KEY", settings.GEMINI_API_KEY)
            if gemini_api_key:
                genai.configure(api_key=gemini_api_key)
            else:
                print("Warning: Gemini API key not provided. Skipping reranking.")
                return search_results[:limit]
        
        model = genai.GenerativeModel('gemini-2.5-pro-preview-03-25')
        
        context_list = []
        for idx, result in enumerate(search_results):
            text = result.payload.get('text', '')
            score = result.score
            context_list.append({
                "id": result.id,
                "text": text,
                "original_score": score,
                "original_rank": idx
            })
        
        rerank_prompt = f"""
        I need help reranking search results for the query: "{query_text}"
        
        Here are the search results, already sorted by vector similarity:
        
        {json.dumps(context_list, indent=2)}
        
        Please rerank these results based on relevance to the query. Consider:
        1. How well the content addresses the query
        2. The depth and quality of information
        3. The specificity to the query topic
        
        Return a JSON array with the IDs of the top {limit} results in order of relevance.
        Format: [id1, id2, id3, ...]
        """
        
        try:
            rerank_response = model.generate_content(rerank_prompt)
            response_text = rerank_response.text
            
            id_match = re.search(r'(\[.*\])', response_text.replace('\n', ' '), re.DOTALL)
            if id_match:
                reranked_ids = json.loads(id_match.group(1))
                
                id_to_result = {str(result.id): result for result in search_results}
                reranked_results = []
                
                for result_id in reranked_ids:
                    result_id_str = str(result_id)
                    if result_id_str in id_to_result:
                        reranked_results.append(id_to_result[result_id_str])
                        if len(reranked_results) >= limit:
                            break
                
                if reranked_results and len(reranked_results) >= limit / 2:
                    print("Results reranked by Gemini LLM")
                    return reranked_results
            
            return search_results[:limit]
        except Exception as e:
            print(f"Error during reranking: {e}")
            return search_results[:limit]
