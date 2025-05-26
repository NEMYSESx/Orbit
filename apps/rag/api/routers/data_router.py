import os
import sys
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, parent_dir)

from fastapi import APIRouter, Depends, HTTPException, Body
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from services.data_service import DataService

router = APIRouter(
    prefix="/data",
    tags=["data"],
    responses={404: {"description": "Not found"}},
)

class DocumentItem(BaseModel):
    id: Optional[Any] = None
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        extra = "allow"

class PushDataRequest(BaseModel):
    collection_name: str
    data: List[DocumentItem]
    recreate_collection: Optional[bool] = False
    use_chunking: Optional[bool] = True
    gemini_api_key: Optional[str] = None
    
    class Config:
        extra = "allow"

class PushDataResponse(BaseModel):
    status: str
    points_uploaded: int
    collection_name: str

@router.post("/push", response_model=PushDataResponse)
async def push_data(
    request: PushDataRequest,
    data_service: DataService = Depends(lambda: DataService())
):
    data = []
    
    for i, item in enumerate(request.data):
        entry = {
            "id": item.id if item.id is not None else i,
            "text": item.text,
            "metadata": dict(item.metadata)
        }
        data.append(entry)
    
    print(f"Pushing {len(data)} items to collection '{request.collection_name}'")
    
    result = data_service.push_data(
        data=data,
        collection_name=request.collection_name,
        use_chunking=request.use_chunking,
        gemini_api_key=request.gemini_api_key,
    )
    
    if result is None or "status" not in result:
        raise HTTPException(status_code=500, detail="Failed to push data")
    
    return {
        **result,
        "collection_name": request.collection_name
    }