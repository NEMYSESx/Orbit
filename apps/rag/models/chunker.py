import re
import json
import os
import sys
import google.generativeai as genai
from typing import Dict, Any, List, Optional


parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from config import settings



class AgenticChunker:
    """
    Intelligent document chunking that uses LLM to make decisions about
    how to split documents in a context-aware manner.
    """
    
    def __init__(self, gemini_api_key=None, model_name=settings.LLM_MODEL):
        """
        Initialize the agentic chunker with Gemini LLM.
        
        Args:
            gemini_api_key: API key for Gemini
            model_name: Gemini model to use
        """
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
        else:
            gemini_api_key = os.environ.get("GEMINI_API_KEY", settings.GEMINI_API_KEY)
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
            json_match = re.search(r'(\{.*\})', response_text.replace('\n', ' '), re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                recommendations = json.loads(json_str)
            else:
                recommendations = {
                    "chunk_size": settings.CHUNK_SIZE,
                    "chunk_overlap": settings.CHUNK_OVERLAP,
                    "respect_boundaries": ["paragraph"],
                    "hierarchical": False,
                    "special_considerations": "None detected"
                }
        except Exception as e:
            print(f"Error parsing LLM recommendation: {e}")
            recommendations = {
                "chunk_size": settings.DEFAULT_CHUNK_SIZE,
                "chunk_overlap": settings.CHUNK_OVERLAP,
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
        
        chunk_size = min(recommendations.get("chunk_size", settings.CHUNK_SIZE), settings.MAX_CHUNK_SIZE)
        chunk_overlap = min(recommendations.get("chunk_overlap", settings.CHUNK_OVERLAP), chunk_size // 2)
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