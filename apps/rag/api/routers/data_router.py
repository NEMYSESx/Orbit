import os
import sys

parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, parent_dir)

from fastapi import APIRouter, Depends, HTTPException, Body
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from services.data_service import DataService
from config import settings

router = APIRouter(
    prefix="/data",
    tags=["data"],
    responses={404: {"description": "Not found"}},
)

class DocumentItem(BaseModel):
    id: Optional[Any] = None
    text: str
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

class PushDataRequest(BaseModel):
    collection_name: Optional[str] = settings.DEFAULT_COLLECTION_NAME
    data: List[DocumentItem]
    recreate_collection: Optional[bool] = False
    use_chunking: Optional[bool] = True
    gemini_api_key: Optional[str] = None

class PushDataResponse(BaseModel):
    status: str
    points_uploaded: int
    collection_name: str

@router.post("/push", response_model=PushDataResponse)
async def push_data(
    request: PushDataRequest,
    data_service: DataService = Depends(lambda: DataService())
):
    """
    Push data to the vector database.
    """
    data = []
    for i, item in enumerate(request.data):
        entry = {
            "id": item.id if item.id is not None else i,
            "text": item.text,
            "metadata": item.metadata
        }
    data.append(entry)
    result = data_service.push_data(
        data=data,
        collection_name=request.collection_name,
        recreate_collection=request.recreate_collection,
        use_chunking=request.use_chunking,
        gemini_api_key=request.gemini_api_key
    )
    
    if result is None or "status" not in result:
        raise HTTPException(status_code=500, detail="Failed to push data")
    
    return {
        **result, 
        "collection_name": request.collection_name
    }