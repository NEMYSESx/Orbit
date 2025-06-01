
from google import genai
from google.genai import types
from typing import List, Union
import numpy as np
import sys
import os

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from config import settings

class EmbeddingModel:
    
    def __init__(self, model_name=None, output_dimensionality=None, api_key=None):
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self.output_dimensionality = output_dimensionality or settings.EMBEDDING_DIMENSIONALITY
        
        api_key_to_use = api_key or settings.GEMINI_API_KEY
        if not api_key_to_use:
            raise ValueError("No Google API key provided. Please provide api_key parameter or set GEMINI_API_KEY in settings.")
        
        self.client = genai.Client(api_key=api_key_to_use)
        self.vector_size = self.output_dimensionality
        
        self._validate_setup()
    
    def _validate_setup(self):
        try:
            config = types.EmbedContentConfig(output_dimensionality=self.output_dimensionality)
            
            test_result = self.client.models.embed_content(
                model=self.model_name,
                contents="test",
                config=config,
            )
            actual_size = len(test_result.embeddings[0].values)
            if actual_size != self.output_dimensionality:
                raise ValueError(
                    f"Embedding dimension mismatch. Expected {self.output_dimensionality}, "
                    f"but model returned {actual_size}. Please check your model and settings."
                )
            self.vector_size = actual_size
        except Exception as e:
            raise ConnectionError(f"Failed to initialize Google embedding model: {e}")
    
    def encode(self, text: Union[str, List[str]]) -> np.ndarray:
        try:
            config = types.EmbedContentConfig(output_dimensionality=self.output_dimensionality)
            
            if isinstance(text, str):
                result = self.client.models.embed_content(
                    model=self.model_name,
                    contents=text,
                    config=config,
                )
                return np.array(result.embeddings[0].values)
            
            elif isinstance(text, list):
                all_embeddings = []
                
                for single_text in text:
                    result = self.client.models.embed_content(
                        model=self.model_name,
                        contents=single_text,
                        config=config,
                    )
                    all_embeddings.append(result.embeddings[0].values)
                
                return np.array(all_embeddings)
            
            else:
                raise ValueError("Text must be a string or list of strings")
                
        except Exception as e:
            raise RuntimeError(f"Failed to generate embeddings: {e}")
    
    def get_vector_size(self) -> int:
        return self.vector_size