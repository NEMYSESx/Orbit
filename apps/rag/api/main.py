import uvicorn
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from rag.api.routers.rag_router import rag_router



app = FastAPI(
    title="RAG API",
    description="API for Retrieval-Augmented Generation Application",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rag_router)

@app.get("/")
async def root():
    return {
        "name": "RAG API",
        "version": "0.1.0",
        "description": "API for Retrieval-Augmented Generation Application",
        "endpoints": {
            "rag": "/rag/query"
        }
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":    
    uvicorn.run("main:app", host="0.0.0.0", port=8000)