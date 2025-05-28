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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import data_router, search_router, rag_router

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

app.include_router(data_router.router)
app.include_router(search_router.router)
app.include_router(rag_router.router)

@app.get("/")
async def root():
    return {
        "name": "RAG API",
        "version": "0.1.0",
        "description": "API for Retrieval-Augmented Generation Application",
        "endpoints": {
            "data": "/data/push",
            "search": "/search",
            "rag": "/rag/query"
        }
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":    
    uvicorn.run("main:app", host="0.0.0.0", port=8000,reload=True)