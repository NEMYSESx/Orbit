from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    QDRANT_URL: str = "https://00819855-01e9-4396-a2b5-5a856fe32d73.eu-central-1-0.aws.cloud.qdrant.io:6333"
    QDRANT_API_KEY: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.I_YX0wNGh_QrZ9A8gjGs8tCgA1a-AKvQ1vyXVJ_QVrs"
    
    COLLECTION_SIMILARITY_THRESHOLD: float = 0.7  
    CREATE_COLLECTIONS_DYNAMICALLY: bool = True  
    
    EMBEDDING_MODEL: str = "models/text-embedding-004"  
    EMBEDDING_DIMENSIONALITY: int = 768  
    
    LLM_MODEL: str = "gemini-2.5-pro-preview-03-25"
    GEMINI_API_KEY: str = "AIzaSyCHrXPFGHX565uVzOVECqjsN6m77_VN9n0"
    CONNECTION_TIMEOUT: int = 15
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    MAX_CHUNK_SIZE: int = 2000

settings = Settings()