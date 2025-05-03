import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings."""
    QDRANT_URL: str = "https://00819855-01e9-4396-a2b5-5a856fe32d73.eu-central-1-0.aws.cloud.qdrant.io:6333"
    QDRANT_API_KEY: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.I_YX0wNGh_QrZ9A8gjGs8tCgA1a-AKvQ1vyXVJ_QVrs"
    DEFAULT_COLLECTION_NAME: str = "documents"
    DEFAULT_EMBEDDING_MODEL: str = "intfloat/multilingual-e5-large-instruct"
    DEFAULT_LLM_MODEL: str = "gemini-2.5-pro-preview-03-25"
    GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
    CONNECTION_TIMEOUT: int = 15
    DEFAULT_CHUNK_SIZE: int = 500
    DEFAULT_CHUNK_OVERLAP: int = 50
    MAX_CHUNK_SIZE: int = 2000
    
    class Config:
        env_prefix = "RAG_"
        env_file = ".env"

settings = Settings()