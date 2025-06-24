import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/fluent", tags=["fluent-control"])

class FluentControlRequest(BaseModel):
    enabled: bool  

@router.post("/toggle")
async def toggle_fluent_bit(request: FluentControlRequest):
    
    action = "start" if request.enabled else "stop"
    
    payload = {
        "action": action,
        "component": "all",
        "source": "ui-control"
    }
    
    try:
        response = requests.post(
            "http://localhost:9880",  
            json=payload,
            timeout=5
        )
        
        if response.status_code == 200:
            return {
                "success": True,
                "message": f"Fluent Bit {'enabled' if request.enabled else 'disabled'}",
                "enabled": request.enabled
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to control Fluent Bit")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")