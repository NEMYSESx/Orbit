import re
import json
import textwrap
import os
import sys
import google.generativeai as genai
from typing import List, Dict, Any, Optional, Tuple
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from models.embeddings import EmbeddingModel  
from models.qdrant_client import QdrantClientWrapper

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)
from config import settings

class SearchService:
    """Service for searching data in Qdrant with intelligent topic selection."""
    
    def __init__(
        self,
        qdrant_client: QdrantClientWrapper = None,
        embedding_model: EmbeddingModel = None,
        gemini_api_key: Optional[str] = None
    ):
        """
        Initialize the search service.
        
        Args:
            qdrant_client: Qdrant client wrapper
            embedding_model: Embedding model
            gemini_api_key: API key for Gemini
        """
        self.qdrant_client = qdrant_client or QdrantClientWrapper()
        self.embedding_model = embedding_model or EmbeddingModel()
        
        self.gemini_api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY", settings.GEMINI_API_KEY)
        self.gemini_model = None
        self._initialize_gemini()
    
    def _initialize_gemini(self):
        """Initialize Gemini model if API key is available."""
        if self.gemini_api_key:
            try:
                genai.configure(api_key=self.gemini_api_key)
                self.gemini_model = genai.GenerativeModel('gemini-2.5-pro-preview-03-25')
                print("Initialized Gemini model successfully.")
            except Exception as e:
                print(f"Failed to initialize Gemini model: {str(e)}")
                self.gemini_model = None
        else:
            self.gemini_model = None
            print("Warning: Gemini API key not provided. Topic classification may be limited.")
            
    @property
    def gemini_api_key(self):
        return self._gemini_api_key
        
    @gemini_api_key.setter
    def gemini_api_key(self, value):
        """Set the Gemini API key and reinitialize the model if needed."""
        self._gemini_api_key = value
        self._initialize_gemini()
    
    def _get_available_collections(self) -> List[str]:
        """
        Get a list of available collections in Qdrant.
        
        Returns:
            List of collection names
        """
        try:
            collections = self.qdrant_client.list_collections()
            return collections
        except Exception as e:
            print(f"Error retrieving collections: {str(e)}")
            return [settings.DEFAULT_COLLECTION_NAME]
    
    def _identify_topic_collection(self, query_text: str) -> tuple[str, float]:
        """
        Identify the most relevant collection/topic for the given query.
        
        Args:
            query_text: User query text
            
        Returns:
            Tuple of (collection_name, confidence_score)
        """
        collections = self._get_available_collections()
        
        if hasattr(self, 'gemini_model') and self.gemini_model:
            try:
                collection_prompt = f"""
                Given the user query: "{query_text}"
                
                Determine which of these document collections would be most relevant:
                {', '.join(collections)}
                
                Return your answer in JSON format like this:
                {{
                    "collection": "most_relevant_collection_name",
                    "confidence": 0.95  # Between 0.0 and 1.0
                }}
                """
                
                response = self.gemini_model.generate_content(collection_prompt)
                response_text = response.text
                
                json_match = re.search(r'({.*})', response_text.replace('\n', ' '), re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group(1))
                    collection = result.get("collection")
                    confidence = result.get("confidence", 0.0)
                    
                    if collection in collections:
                        print(f"Topic classifier identified collection: '{collection}' with confidence: {confidence:.2f}")
                        return collection, confidence
            
            except Exception as e:
                print(f"Error during topic classification: {str(e)}")
        
        try:
            if not hasattr(self, 'embedding_model') or self.embedding_model is None:
                print("Warning: Embedding model not initialized. Using default collection.")
                return settings.DEFAULT_COLLECTION_NAME, 0.0
                
            query_vector = self.embedding_model.encode(query_text).tolist()
            
            collection_scores = []
            for collection in collections:
                collection_embedding = self.embedding_model.encode(f"Documents about {collection}").tolist()
                similarity = self._calculate_similarity(query_vector, collection_embedding)
                collection_scores.append((collection, similarity))
            
            collection_scores.sort(key=lambda x: x[1], reverse=True)
            best_collection, score = collection_scores[0]
            
            print(f"Vector similarity identified collection: '{best_collection}' with score: {score:.2f}")
            return best_collection, score
            
        except Exception as e:
            print(f"Error during vector-based topic classification: {str(e)}")
            return settings.DEFAULT_COLLECTION_NAME, 0.0
    
    def _calculate_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Calculate cosine similarity between two vectors.
        
        Args:
            vec1: First vector
            vec2: Second vector
            
        Returns:
            Similarity score (0.0 to 1.0)
        """
        import numpy as np
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
    
    def search(
        self, 
        query_text: str,
        collection_name: Optional[str] = None,
        limit: int = 5,
        rerank: bool = True,
        filter_conditions: Optional[Dict[str, Any]] = None,
        auto_detect_topic: bool = True,
        time_priority: float = 0.0,
        time_field: str = "created_at"
    ) -> List[Any]:
        """
        Intelligently search for documents in Qdrant with topic detection and time prioritization.
    
        Args:
            query_text: Query text
            collection_name: Name of the collection to search (overrides auto detection)
            limit: Maximum number of results to return
            rerank: Whether to use Gemini to rerank results
            filter_conditions: Optional filter conditions for search
            auto_detect_topic: Whether to automatically detect the topic/collection
            time_priority: Weight for time prioritization (0-1)
            time_field: Field name containing timestamp
        
        Returns:
            List of search results
        """
        try:
            if not collection_name and auto_detect_topic:
                collection_name, confidence = self._identify_topic_collection(query_text)
            
                if confidence < 0.4:
                    print(f"Low confidence in topic detection ({confidence:.2f}). Using default collection.")
                    collection_name = settings.DEFAULT_COLLECTION_NAME
        
            collection_name = collection_name or settings.DEFAULT_COLLECTION_NAME
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
        
            if time_priority > 0:
                search_results = self._apply_time_prioritization(
                    search_results,
                    time_priority,
                    time_field
                )
        
            if rerank:
                search_results = self._rerank_with_gemini(
                    search_results,
                    query_text,
                    limit
                )
            
                if time_priority > 0:
                    search_results = self._apply_time_prioritization(
                        search_results,
                        time_priority * 0.5,  
                        time_field
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
        limit: int
    ) -> List[Any]:
        """
        Rerank search results using Gemini.
        
        Args:
            search_results: List of search results
            query_text: Original query text
            limit: Maximum number of results to return
            
        Returns:
            Reranked search results
        """
        if not self.gemini_model:
            print("Warning: Gemini model not configured. Skipping reranking.")
            return search_results[:limit]
        
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
            rerank_response = self.gemini_model.generate_content(rerank_prompt)
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
    
    def smart_search(
        self,
        user_query: str,
        limit: int = 5,
        rerank: bool = True,
        time_priority: float = 0.0,
        time_field: str = "created_at"
    ) -> Dict[str, Any]:
        """
        Perform a smart search including topic identification, focused search, and time prioritization.
    
        Args:
            user_query: User query text
            limit: Maximum number of results to return
            rerank: Whether to use Gemini to rerank results
            time_priority: Weight for time prioritization (0-1)
            time_field: Field name containing timestamp
        
        Returns:
            Dictionary with search results and metadata
        """
        collection_name, confidence = self._identify_topic_collection(user_query)
    
        results = self.search(
            query_text=user_query,
            collection_name=collection_name,
            limit=limit,
            rerank=rerank,
            auto_detect_topic=False,
            time_priority=time_priority,
            time_field=time_field
        )
    
        response = {
            "query": user_query,
            "identified_topic": collection_name,
            "topic_confidence": confidence,
            "results": results,
            "result_count": len(results),
            "time_prioritized": time_priority > 0
        }
    
        return response
    
    
    
    def _apply_time_prioritization(
        self,
        results: List[Any],
        time_priority: float,
        time_field: str
    ) -> List[Any]:
        """
        Apply time-based prioritization to search results.
    
        Args:
            results: Original search results
            time_priority: Weight for time prioritization (0-1)
            time_field: Field name containing timestamp
        
        Returns:
            Reranked results with time priority applied
        """
        if not results or time_priority <= 0:
            return results
    
        time_priority = max(0.0, min(1.0, time_priority))
    
        import datetime
        from dateutil import parser
        import numpy as np
    
        now = datetime.datetime.now()
    
        scored_results = []
        valid_timestamps = []
    
        for result in results:
            if time_field in result.payload:
                try:
                    timestamp_value = result.payload[time_field]
                    if isinstance(timestamp_value, str):
                        timestamp = parser.parse(timestamp_value)
                    elif isinstance(timestamp_value, (int, float)):
                        timestamp = datetime.datetime.fromtimestamp(timestamp_value)
                    elif isinstance(timestamp_value, datetime.datetime):
                        timestamp = timestamp_value
                    else:
                        print(f"Invalid timestamp format for result {result.id}")
                        scored_results.append((result, result.score, None))
                        continue
                
                    valid_timestamps.append(timestamp)
                    scored_results.append((result, result.score, timestamp))
                except Exception as e:
                    print(f"Error parsing timestamp for result {result.id}: {e}")
                    scored_results.append((result, result.score, None))
            else:
                scored_results.append((result, result.score, None))
    
        if not valid_timestamps:
            print("No valid timestamps found in results, skipping time prioritization")
            return results
    
        max_age = max([(now - ts).total_seconds() for ts in valid_timestamps])
        if max_age <= 0:
            return results
    
        rescored_results = []
        for result, original_score, timestamp in scored_results:
            if timestamp is not None:
                age_seconds = (now - timestamp).total_seconds()
                recency_score = 1.0 - (age_seconds / max_age)
            
                combined_score = (1 - time_priority) * original_score + time_priority * recency_score
            else:
                combined_score = original_score
        
            rescored_results.append((result, combined_score))
    
        rescored_results.sort(key=lambda x: x[1], reverse=True)
    
        final_results = []
        for result, combined_score in rescored_results:
            result.score = combined_score
            final_results.append(result)
    
        return final_results