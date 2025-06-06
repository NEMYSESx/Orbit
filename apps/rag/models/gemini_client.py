import google.generativeai as genai
from typing import List, Dict, Any, Optional
from rag.config import settings

class GeminiClient:
    
    def __init__(self, api_key: str = settings.GEMINI_API_KEY):
        genai.configure(api_key=api_key)
        self.llm_model = genai.GenerativeModel(settings.LLM_MODEL)
        
    def generate_text(self, prompt: str, temperature: float = 0.7) -> str:
        try:
            response = self.llm_model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature
                )
            )
            return response.text
        except Exception as e:
            print(f"Error generating text: {e}")
            raise
    
    def generate_embedding(self, text: str) -> List[float]:
        try:
            result = genai.embed_content(
                model=settings.EMBEDDING_MODEL,
                content=text,
                task_type="retrieval_query"
            )
            return result['embedding']
        except Exception as e:
            print(f"Error generating embedding: {e}")
            raise