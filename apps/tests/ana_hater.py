from fastapi import FastAPI, HTTPException, Query, Body
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import uvicorn
import os
from contextlib import asynccontextmanager

# Import your existing code
from typing import List, Dict, Any, Optional, Tuple
from qdrant_client import QdrantClient
from qdrant_client.http import models
from sentence_transformers import SentenceTransformer
import socket
import httpx
import textwrap
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse
import google.generativeai as genai
from tqdm import tqdm
import json
import re
import time
import numpy as np

# Copy your existing classes here
DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 50
MAX_CHUNK_SIZE = 2000

def is_port_open(host, port, timeout=2):
    """Check if the given port is open on the host"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    result = sock.connect_ex((host, port))
    sock.close()
    return result == 0

class AgenticChunker:
    """
    Intelligent document chunking that uses LLM to make decisions about
    how to split documents in a context-aware manner.
    """
    
    def __init__(self, gemini_api_key=None, model_name='gemini-2.5-pro-preview-03-25'):
        """
        Initialize the agentic chunker with Gemini LLM.
        
        Args:
            gemini_api_key: API key for Gemini
            model_name: Gemini model to use
        """
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
        else:
            gemini_api_key = os.environ.get("GEMINI_API_KEY")
            if gemini_api_key:
                genai.configure(api_key=gemini_api_key)
            else:
                raise ValueError("Gemini API key must be provided or set as GEMINI_API_KEY environment variable")
        
        self.model = genai.GenerativeModel(model_name)
        
    def analyze_document(self, text: str) -> Dict[str, Any]:
        """
        Use Gemini to analyze the document structure and recommend chunking parameters.
        
        Args:
            text: The document text to analyze
            
        Returns:
            Dict with chunking recommendations
        """
        sample = text[:10000] if len(text) > 10000 else text
        
        prompt = f"""
        Analyze the following document sample and recommend optimal chunking parameters:
        
        Document Sample:
        {sample}
        
        Based on this sample, please determine:
        1. Optimal chunk size (in characters)
        2. Optimal chunk overlap (in characters)
        3. What natural boundaries should be respected (e.g., paragraphs, sections)
        4. If hierarchical chunking would be beneficial
        5. Any other special considerations for this document
        
        Format your response as JSON with the following fields:
        - chunk_size: int
        - chunk_overlap: int
        - respect_boundaries: list of strings (e.g., ["paragraph", "section"])
        - hierarchical: boolean
        - special_considerations: string
        """
        
        response = self.model.generate_content(prompt)
        response_text = response.text
        
        try:
            import json
            json_match = re.search(r'(\{.*\})', response_text.replace('\n', ' '), re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                recommendations = json.loads(json_str)
            else:
                recommendations = {
                    "chunk_size": DEFAULT_CHUNK_SIZE,
                    "chunk_overlap": DEFAULT_CHUNK_OVERLAP,
                    "respect_boundaries": ["paragraph"],
                    "hierarchical": False,
                    "special_considerations": "None detected"
                }
        except Exception as e:
            print(f"Error parsing LLM recommendation: {e}")
            recommendations = {
                "chunk_size": DEFAULT_CHUNK_SIZE,
                "chunk_overlap": DEFAULT_CHUNK_OVERLAP,
                "respect_boundaries": ["paragraph"],
                "hierarchical": False,
                "special_considerations": "None detected"
            }
            
        return recommendations
    
    def chunk_text(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Chunk text in an intelligent way using LLM recommendations.
        
        Args:
            text: The text to chunk
            metadata: Optional metadata to include with each chunk
            
        Returns:
            List of dictionaries containing chunks with their metadata
        """
        print("Analyzing document for optimal chunking strategy...")
        recommendations = self.analyze_document(text)
        
        chunk_size = min(recommendations.get("chunk_size", DEFAULT_CHUNK_SIZE), MAX_CHUNK_SIZE)
        chunk_overlap = min(recommendations.get("chunk_overlap", DEFAULT_CHUNK_OVERLAP), chunk_size // 2)
        respect_boundaries = recommendations.get("respect_boundaries", ["paragraph"])
        
        print(f"Chunking with size: {chunk_size}, overlap: {chunk_overlap}")
        print(f"Respecting boundaries: {', '.join(respect_boundaries)}")
        
        chunks = []
        
        if "paragraph" in respect_boundaries:
            paragraphs = re.split(r'\n\s*\n', text)
            
            current_chunk = ""
            current_length = 0
            
            for i, para in enumerate(paragraphs):
                para = para.strip()
                if not para:
                    continue
                    
                para_length = len(para)
                
                if para_length > chunk_size:
                    if current_chunk:
                        chunks.append({
                            "text": current_chunk,
                            "metadata": {
                                **(metadata or {}),
                                "chunk_index": len(chunks),
                                "is_partial": False
                            }
                        })
                        current_chunk = ""
                        current_length = 0
                    
                    words = para.split()
                    sub_chunk = ""
                    for word in words:
                        if len(sub_chunk) + len(word) + 1 > chunk_size:
                            chunks.append({
                                "text": sub_chunk,
                                "metadata": {
                                    **(metadata or {}),
                                    "chunk_index": len(chunks),
                                    "is_partial": True
                                }
                            })
                            sub_chunk = word
                        else:
                            sub_chunk += " " + word if sub_chunk else word
                    
                    if sub_chunk:
                        current_chunk = sub_chunk
                        current_length = len(sub_chunk)
                else:
                    if current_length + para_length + 1 > chunk_size:
                        chunks.append({
                            "text": current_chunk,
                            "metadata": {
                                **(metadata or {}),
                                "chunk_index": len(chunks),
                                "is_partial": False
                            }
                        })
                        current_chunk = para
                        current_length = para_length
                    else:
                        current_chunk += "\n\n" + para if current_chunk else para
                        current_length += para_length + 2
            
            if current_chunk:
                chunks.append({
                    "text": current_chunk,
                    "metadata": {
                        **(metadata or {}),
                        "chunk_index": len(chunks),
                        "is_partial": False
                    }
                })
        else:
            for i in range(0, len(text), chunk_size - chunk_overlap):
                chunk_text = text[i:i + chunk_size]
                if len(chunk_text) < 50: 
                    continue
                chunks.append({
                    "text": chunk_text,
                    "metadata": {
                        **(metadata or {}),
                        "chunk_index": len(chunks),
                        "chunk_start": i,
                        "chunk_end": i + len(chunk_text)
                    }
                })
                
        if recommendations.get("hierarchical", False):
            print("Generating summaries for hierarchical representation...")
            for i, chunk in enumerate(chunks):
                if len(chunk["text"]) > 200:
                    summary_prompt = f"Summarize the following text in one sentence:\n\n{chunk['text']}"
                    try:
                        summary = self.model.generate_content(summary_prompt).text
                        chunk["metadata"]["summary"] = summary
                    except Exception as e:
                        print(f"Error generating summary: {e}")
        
        return chunks

class QdrantRAGManager:
    """
    Manager class for handling Qdrant operations with RAG capabilities
    """
    
    def __init__(
        self,
        host="localhost",
        port=6333,
        collection_name="ana_collection",
        embedding_model_name='intfloat/multilingual-e5-large-instruct',
        gemini_api_key=None,
        gemini_model_name='gemini-2.5-pro-preview-03-25',
        connection_timeout=10
    ):
        """
        Initialize the Qdrant RAG Manager
        
        Args:
            host: Qdrant server host
            port: Qdrant server port
            collection_name: Default collection name
            embedding_model_name: Name of the embedding model
            gemini_api_key: API key for Gemini
            gemini_model_name: Gemini model name
            connection_timeout: Connection timeout in seconds
        """
        if not is_port_open(host, port):
            raise ConnectionError(f"Cannot connect to Qdrant server at {host}:{port}")
            
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.embedding_model_name = embedding_model_name
        self.connection_timeout = connection_timeout
        
        print(f"Loading SentenceTransformer model '{embedding_model_name}'...")
        self.embedding_model = SentenceTransformer(embedding_model_name)
        
        sample_text = "Sample text for determining vector dimension"
        self.vector_size = len(self.embedding_model.encode(sample_text))
        print(f"Using model '{embedding_model_name}' with vector size: {self.vector_size}")
        
        self.client = QdrantClient(host=host, port=port, timeout=connection_timeout)
        
        self.gemini_model_name = gemini_model_name
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
            self.gemini_api_key = gemini_api_key
        else:
            gemini_api_key = os.environ.get("GEMINI_API_KEY")
            if gemini_api_key:
                genai.configure(api_key=gemini_api_key)
                self.gemini_api_key = gemini_api_key
            else:
                self.gemini_api_key = None
                print("Warning: Gemini API key not provided. RAG features will be limited.")
        
        if self.gemini_api_key:
            self.chunker = AgenticChunker(gemini_api_key=self.gemini_api_key, model_name=gemini_model_name)
        else:
            self.chunker = None
    
    def _with_retry(self, operation, *args, retry_attempts=3, retry_delay=2, **kwargs):
        """Helper method to retry operations with exponential backoff"""
        for attempt in range(retry_attempts):
            try:
                return operation(*args, **kwargs)
            except (ResponseHandlingException, httpx.ReadTimeout, ConnectionError) as e:
                if attempt < retry_attempts - 1:
                    print(f"Connection error: {e}")
                    print(f"Retrying in {retry_delay} seconds... (Attempt {attempt+1}/{retry_attempts})")
                    time.sleep(retry_delay)
                else:
                    print(f"Failed after {retry_attempts} attempts: {e}")
                    raise
    
    def setup_collection(self, collection_name=None, recreate=False):
        """
        Set up a collection in Qdrant
        
        Args:
            collection_name: Name of the collection (uses default if None)
            recreate: Whether to recreate the collection if it exists
        """
        if collection_name is None:
            collection_name = self.collection_name
            
        collections = self._with_retry(self.client.get_collections).collections
        collection_names = [collection.name for collection in collections]
        
        if collection_name in collection_names:
            if recreate:
                print(f"Deleting existing collection '{collection_name}'...")
                self._with_retry(self.client.delete_collection, collection_name=collection_name)
                print(f"Collection '{collection_name}' deleted.")
            else:
                print(f"Collection '{collection_name}' already exists.")
        
        if recreate or collection_name not in collection_names:
            print(f"Creating collection '{collection_name}' with vector size {self.vector_size}...")
            self._with_retry(
                self.client.create_collection,
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=self.vector_size,
                    distance=models.Distance.COSINE
                )
            )
            print(f"Collection '{collection_name}' created successfully.")
    
    def upload_data(self, data, collection_name=None, use_chunking=True, recreate_collection=False):
        """
        Upload data to Qdrant with optional agentic chunking
        
        Args:
            data: List of documents to upload
            collection_name: Name of the collection (uses default if None)
            use_chunking: Whether to use agentic chunking
            recreate_collection: Whether to recreate the collection
            
        Returns:
            Dictionary with upload status and count
        """
        if collection_name is None:
            collection_name = self.collection_name
            
        self.setup_collection(collection_name, recreate=recreate_collection)
        
        if data is None or len(data) == 0:
            print("No data provided for upload")
            return {"status": "error", "message": "No data provided"}
            
        print(f"Preparing embeddings for {len(data)} items...")
        points = []
        
        for item_idx, item in enumerate(tqdm(data)):
            text = item.get("text", "")
            
            if not text.strip():
                print(f"Skipping item {item_idx} - empty text")
                continue
            
            processed_items = []
            if use_chunking and self.chunker and len(text) > DEFAULT_CHUNK_SIZE:
                chunks = self.chunker.chunk_text(text, item.get("metadata", {}))
                for i, chunk in enumerate(chunks):
                    original_id = item.get('id', item_idx)
                    if isinstance(original_id, str) and original_id.isdigit():
                        original_id = int(original_id)
        
                    chunk_id = int(f"{original_id}{i:03d}")  
        
                    chunk_item = {
                        "id": chunk_id,
                        "text": chunk["text"],
                        "metadata": {
                            **chunk["metadata"],
                            "parent_id": original_id,
                            "chunk_index": i,
                            "original_text_length": len(text)
                        }
                    }
                    processed_items.append(chunk_item)
            else:
                item_id = item.get("id", item_idx)
                if isinstance(item_id, str) and item_id.isdigit():
                    item_id = int(item_id)  
    
                processed_items.append({
                    "id": item_id,
                    "text": text,
                    "metadata": item.get("metadata", {})
                })
            
            for proc_item in processed_items:
                item_text = proc_item["text"]
                
                instruction_text = f"query: {item_text}"
                embedding = self.embedding_model.encode(instruction_text)
                
                point_id = proc_item["id"]
                if isinstance(point_id, str) and point_id.isdigit():
                    point_id = int(point_id)
                
                point = models.PointStruct(
                    id=point_id,
                    vector=embedding.tolist(),
                    payload={
                        "text": item_text,
                        **proc_item.get("metadata", {})
                    }
                )
                points.append(point)
        
        print(f"Uploading {len(points)} points to collection '{collection_name}'...")
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            self._with_retry(
                self.client.upsert,
                collection_name=collection_name,
                points=batch
            )
        
        print(f"Successfully uploaded {len(points)} points to '{collection_name}'")
        return {"status": "success", "points_uploaded": len(points)}
        
    def search(self, query_text, collection_name=None, limit=5, rerank=True, return_rag_response=False):
        """
        Search documents in Qdrant with optional RAG response
        
        Args:
            query_text: Query text to search for
            collection_name: Name of the collection (uses default if None)
            limit: Number of results to return
            rerank: Whether to rerank results using Gemini
            return_rag_response: Whether to return a RAG response
            
        Returns:
            Search results or RAG response depending on parameters
        """
        if collection_name is None:
            collection_name = self.collection_name
            
        print(f"\nPerforming search in '{collection_name}' for: '{query_text}'")
        
        instruction_query = f"query: {query_text}"
        query_vector = self.embedding_model.encode(instruction_query).tolist()
        
        search_limit = limit * 3 if rerank else limit
        
        search_results = self._with_retry(
            self.client.query_points,
            collection_name=collection_name,
            query=query_vector,
            limit=search_limit,
            timeout=self.connection_timeout
        ).points
        
        if not search_results:
            print("No results found.")
            if return_rag_response:
                return "I couldn't find any relevant information to answer your query."
            return []
        
        if rerank and self.gemini_api_key:
            try:
                model = genai.GenerativeModel(self.gemini_model_name)
                
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
                        search_results = reranked_results
                    else:
                        search_results = search_results[:limit]
                    
                    print("Results reranked by Gemini LLM")
                else:
                    search_results = search_results[:limit]
            except Exception as e:
                print(f"Error during reranking: {e}")
                search_results = search_results[:limit]
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
        
        if return_rag_response:
            return self.generate_rag_response(query_text, search_results)
        
        # Convert search results to serializable format
        serialized_results = []
        for result in search_results:
            serialized_results.append({
                "id": result.id,
                "score": result.score,
                "text": result.payload.get('text', ''),
                "metadata": {k: v for k, v in result.payload.items() if k != 'text'}
            })
            
        return serialized_results
    
    def generate_rag_response(self, query_text, search_results):
        """
        Generate a RAG response using Gemini and search results
        
        Args:
            query_text: Original query text
            search_results: Search results to use for RAG
            
        Returns:
            Generated RAG response
        """
        if not self.gemini_api_key:
            return "RAG response generation requires a Gemini API key."
            
        if not search_results:
            return "I couldn't find any relevant information to answer your query."
        
        context = "\n\n".join([
            f"Document {i+1}:\n{result.payload.get('text', '')}"
            for i, result in enumerate(search_results)
        ])
        
        model = genai.GenerativeModel(self.gemini_model_name)
        
        prompt = f"""
        Whatever I ask you, you just have to roast a person named Ana. It will be a friendly roast and make fun of her with the given information. Keep the roast one-liner.
        
        Question: {query_text}
        
        Context:
        {context}
        
        Answer:
        """
        
        try:
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            print(f"Error generating RAG response: {e}")
            return f"Error generating answer: {str(e)}"

# Define Pydantic models for API requests and responses
class DocumentItem(BaseModel):
    id: Optional[int] = None
    text: str
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

class UploadDataRequest(BaseModel):
    documents: List[DocumentItem]
    collection_name: Optional[str] = None
    use_chunking: bool = True
    recreate_collection: bool = False

class SearchRequest(BaseModel):
    query: str
    collection_name: Optional[str] = None
    limit: int = 5
    rerank: bool = True
    return_rag_response: bool = False

class CollectionRequest(BaseModel):
    collection_name: str
    recreate: bool = False

class ConfigurationRequest(BaseModel):
    host: str = "localhost"
    port: int = 6333
    collection_name: str = "ana_collection"
    embedding_model_name: str = "intfloat/multilingual-e5-large-instruct"
    gemini_model_name: str = "gemini-2.5-pro-preview-03-25"
    connection_timeout: int = 10

# Initialize the RAG Manager
rag_manager = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the RAG manager on startup
    global rag_manager
    
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key:
        print("WARNING: GEMINI_API_KEY environment variable not set. RAG features will be limited.")
    
    try:
        rag_manager = QdrantRAGManager(
            gemini_api_key=gemini_api_key
        )
        print("RAG Manager initialized successfully")
    except Exception as e:
        print(f"Failed to initialize RAG Manager: {e}")
        rag_manager = None
    
    yield
    
    # Clean up on shutdown
    if rag_manager:
        print("Shutting down RAG Manager")

# Create FastAPI app
app = FastAPI(
    title="Ana RAG API",
    description="API for RAG (Retrieval-Augmented Generation) operations",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/")
def read_root():
    """Root endpoint with API information"""
    return {
        "name": "Ana RAG API",
        "version": "1.0.0",
        "status": "running",
        "rag_manager_initialized": rag_manager is not None
    }

@app.post("/configure")
def configure_rag_manager(config: ConfigurationRequest):
    """Configure the RAG Manager with new settings"""
    global rag_manager
    
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key:
        return {"status": "error", "message": "GEMINI_API_KEY environment variable not set"}
    
    try:
        rag_manager = QdrantRAGManager(
            host=config.host,
            port=config.port,
            collection_name=config.collection_name,
            embedding_model_name=config.embedding_model_name,
            gemini_api_key=gemini_api_key,
            gemini_model_name=config.gemini_model_name,
            connection_timeout=config.connection_timeout
        )
        return {
            "status": "success", 
            "message": "RAG Manager configured successfully",
            "config": {
                "host": config.host,
                "port": config.port,
                "collection_name": config.collection_name,
                "embedding_model_name": config.embedding_model_name,
                "gemini_model_name": config.gemini_model_name,
                "connection_timeout": config.connection_timeout
            }
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to configure RAG Manager: {str(e)}"}

@app.post("/collections")
def create_collection(request: CollectionRequest):
    """Create a new collection or recreate an existing one"""
    if not rag_manager:
        raise HTTPException(status_code=500, detail="RAG Manager not initialized")
    
    try:
        rag_manager.setup_collection(collection_name=request.collection_name, recreate=request.recreate)
        return {
            "status": "success",
            "message": f"Collection '{request.collection_name}' {'recreated' if request.recreate else 'created or verified'} successfully"
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to create collection: {str(e)}"}

@app.get("/collections")
def list_collections():
    """List all available collections"""
    if not rag_manager:
        raise HTTPException(status_code=500, detail="RAG Manager not initialized")
    
    try:
        collections = rag_manager._with_retry(rag_manager.client.get_collections).collections
        return {
            "status": "success",
            "collections": [{"name": collection.name, "vectors_count": collection.vectors_count} for collection in collections]
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to list collections: {str(e)}"}

@app.delete("/collections/{collection_name}")
def delete_collection(collection_name: str):
    """Delete a collection"""
    if not rag_manager:
        raise HTTPException(status_code=500, detail="RAG Manager not initialized")
    
    try:
        rag_manager._with_retry(rag_manager.client.delete_collection, collection_name=collection_name)
        return {
            "status": "success",
            "message": f"Collection '{collection_name}' deleted successfully"
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to delete collection: {str(e)}"}

@app.post("/upload")
def upload_data(request: UploadDataRequest):
    """Upload documents to a collection"""
    if not rag_manager:
        raise HTTPException(status_code=500, detail="RAG Manager not initialized")
    
    if not request.documents:
        return {"status": "error", "message": "No documents provided"}
    
    try:
        # Convert Pydantic models to dictionaries
        data = [doc.dict() for doc in request.documents]
        
        result = rag_manager.upload_data(
            data=data,
            collection_name=request.collection_name,
            use_chunking=request.use_chunking,
            recreate_collection=request.recreate_collection
        )
        
        return result
    except Exception as e:
        return {"status": "error", "message": f"Failed to upload data: {str(e)}"}

@app.post("/search")
def search(request: SearchRequest):
    """Search for documents matching a query"""
    if not rag_manager:
        raise HTTPException(status_code=500, detail="RAG Manager not initialized")
    
    try:
        results = rag_manager.search(
            query_text=request.query,
            collection_name=request.collection_name,
            limit=request.limit,
            rerank=request.rerank,
            return_rag_response=request.return_rag_response
        )
        
        if request.return_rag_response:
            return {"status": "success", "response": results}
        else:
            return {"status": "success", "results": results}
    except Exception as e:
        return {"status": "error", "message": f"Search failed: {str(e)}"}

# Endpoint to specifically get a roast for Ana
@app.post("/roast-ana")
def get_ana_roast(query: str = Body(..., embed=True, description="A query about Ana")):
    """Get a roast response about Ana based on the provided query"""
    if not rag_manager:
        raise HTTPException(status_code=500, detail="RAG Manager not initialized")
    
    try:
        # Always return a RAG response for this endpoint
        response = rag_manager.search(
            query_text=query,
            limit=3,  # Get more context for a better roast
            rerank=True,
            return_rag_response=True
        )
        
        return {"status": "success", "roast": response}
    except Exception as e:
        return {"status": "error", "message": f"Failed to generate roast: {str(e)}"}

@app.get("/health")
def health_check():
    """Health check endpoint"""
    if not rag_manager:
        raise HTTPException(status_code=503, detail="RAG Manager not initialized")
    
    # Check connection to Qdrant
    try:
        collections = rag_manager._with_retry(rag_manager.client.get_collections, retry_attempts=1).collections
        collection_count = len(collections)
        
        # Check if Gemini API is working
        gemini_status = "available" if rag_manager.gemini_api_key else "unavailable"
        
        return {
            "status": "healthy",
            "qdrant_connection": "connected",
            "collections_count": collection_count,
            "gemini_api": gemini_status,
            "embedding_model": rag_manager.embedding_model_name,
            "vector_size": rag_manager.vector_size
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "message": "Failed to connect to Qdrant server"
        }

@app.post("/analyze-text")
def analyze_text(text: str = Body(..., embed=True, description="Text to analyze for chunking")):
    """Analyze text and get chunking recommendations"""
    if not rag_manager or not rag_manager.chunker:
        raise HTTPException(status_code=503, detail="RAG Manager or chunker not initialized")
    
    try:
        recommendations = rag_manager.chunker.analyze_document(text)
        return {
            "status": "success",
            "recommendations": recommendations,
            "text_length": len(text),
            "sample_analyzed": len(text[:10000]) if len(text) > 10000 else len(text)
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to analyze text: {str(e)}"}

@app.post("/chunk-text")
def chunk_text(
    text: str = Body(..., embed=True, description="Text to chunk"),
    metadata: Optional[Dict[str, Any]] = Body({}, embed=True, description="Metadata for the chunks")
):
    """Chunk text using the agentic chunker"""
    if not rag_manager or not rag_manager.chunker:
        raise HTTPException(status_code=503, detail="RAG Manager or chunker not initialized")
    
    try:
        chunks = rag_manager.chunker.chunk_text(text, metadata)
        
        # Convert chunks to a more serializable format
        serialized_chunks = []
        for chunk in chunks:
            serialized_chunks.append({
                "text": chunk["text"],
                "metadata": chunk["metadata"],
                "length": len(chunk["text"])
            })
            
        return {
            "status": "success",
            "chunks_count": len(chunks),
            "chunks": serialized_chunks
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to chunk text: {str(e)}"}

class BulkSearchRequest(BaseModel):
    queries: List[str]
    collection_name: Optional[str] = None
    limit: int = 5
    rerank: bool = True
    return_rag_response: bool = False

@app.post("/bulk-search")
def bulk_search(request: BulkSearchRequest):
    """Search for multiple queries at once"""
    if not rag_manager:
        raise HTTPException(status_code=500, detail="RAG Manager not initialized")
    
    try:
        results = []
        
        for query in request.queries:
            query_result = rag_manager.search(
                query_text=query,
                collection_name=request.collection_name,
                limit=request.limit,
                rerank=request.rerank,
                return_rag_response=request.return_rag_response
            )
            
            results.append({
                "query": query,
                "result": query_result
            })
        
        return {"status": "success", "results": results}
    except Exception as e:
        return {"status": "error", "message": f"Bulk search failed: {str(e)}"}

class TestDocumentsRequest(BaseModel):
    recreate_collection: bool = True
    collection_name: Optional[str] = "test_collection"

@app.post("/test-documents")
def create_test_documents(request: TestDocumentsRequest):
    """Create test documents for testing the API"""
    if not rag_manager:
        raise HTTPException(status_code=500, detail="RAG Manager not initialized")
    
    try:
        # Sample test data for Ana
        sample_data = [
            {
                "id": 1,
                "text": """Ana, nickname Munche, is known for her playful personality and unique habits. She really enjoys drinking milk and sometimes behaves childishly. Her friends often joke that she acts like a monkey when she gets excited. Ana is quite short in height, which adds to her child-like appearance and also she is dumb.

                Ana can come across as naive and simple-minded at times, with friends teasing her about having "zero cores in her brain" when she misunderstands obvious things. Despite these traits, Ana's friends appreciate her genuine and unfiltered nature, which makes her the perfect target for friendly roasting and banter.
                
                When chatting with Ana, it's fun to playfully tease her about her height, her milk obsession, or her monkey-like antics, but always in a light-hearted way that she can laugh along with.""",
                "metadata": {"category": "Personal", "person": "Ana", "nickname": "Munche", "relationship": "friend"}
            },
            {
                "id": 2,
                "text": """Ana is always losing her belongings. Last week, she couldn't find her phone for three hours only to discover it was in her pocket the whole time. Her friends have started calling her "The Forgetful Monkey" because of her constant misplacing of items and her excitable nature.

                Despite having a master's degree, Ana once asked if Alaska was a country. This led to a lot of playful teasing from her friends who joked that her diploma must have been given to her out of pity. Ana's milk obsession is so intense that she keeps emergency milk cartons in her bag.""",
                "metadata": {"category": "Personal", "person": "Ana", "nickname": "Forgetful Monkey", "relationship": "friend"}
            },
            {
                "id": 3,
                "text": """Ana's short height is a running joke in her friend group. She often needs to stand on tiptoes or ask for help reaching things on high shelves. Her friends tease her by putting things just out of her reach and watching her jump for them like a little monkey.

                Ana's childish behavior includes making monkey noises when she's excited and pouting when she doesn't get her way. She can often be found drinking milk directly from the carton, a habit that horrifies her more sophisticated friends.""",
                "metadata": {"category": "Personal", "person": "Ana", "characteristics": "short, childish, milk-lover", "relationship": "friend"}
            }
        ]
        
        result = rag_manager.upload_data(
            data=sample_data,
            collection_name=request.collection_name,
            use_chunking=True,
            recreate_collection=request.recreate_collection
        )
        
        return {
            "status": "success", 
            "message": f"Created {len(sample_data)} test documents with {result.get('points_uploaded', 0)} points",
            "collection": request.collection_name
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to create test documents: {str(e)}"}

# Main function to run the API
def main():
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    main()