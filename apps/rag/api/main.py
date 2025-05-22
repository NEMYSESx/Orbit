import os
import sys
import uvicorn

current_dir = os.path.dirname(os.path.abspath(__file__))

router_dir = os.path.join(current_dir, 'routers')
if router_dir not in sys.path:
    sys.path.insert(0, router_dir)

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from routers import data_router, search_router, rag_router
from config import settings

app = FastAPI(
    title="RAG API",
    description="API for Retrieval-Augmented Generation with intelligent chunking",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(data_router.router)
app.include_router(search_router.router)
app.include_router(rag_router.router)

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "RAG API",
        "version": "0.1.0",
        "description": "API for Retrieval-Augmented Generation with intelligent chunking",
        "endpoints": {
            "data": "/data/push",
            "search": "/search",
            "rag": "/rag/answer"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}

if __name__ == "__main__":    
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)