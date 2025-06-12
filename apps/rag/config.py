from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    QDRANT_URL : str 
    QDRANT_API_KEY : str
    
    COLLECTION_SIMILARITY_THRESHOLD : float 
    CREATE_COLLECTIONS_DYNAMICALLY : bool
    
    EMBEDDING_MODEL : str 
    EMBEDDING_DIMENSIONALITY : int
    
    LLM_MODEL : str
    GEMINI_API_KEY : str
    CONNECTION_TIMEOUT : int

settings = Settings()