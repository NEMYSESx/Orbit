import requests
import time
import threading
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/fluent", tags=["fluent-control"])

# Fluent Bit HTTP endpoint - remove /control path
FLUENT_BIT_URL = "http://fluent-bit:9880"

class FluentControlRequest(BaseModel):
    enabled: bool

# Global state to track if logging is enabled
logging_enabled = False

@router.post("/toggle")
async def toggle_logging(request: FluentControlRequest):
    """Enable/Disable Fluent Bit ingestion using HTTP control."""
    global logging_enabled
    
    try:
        if request.enabled:
            # Enable ingestion by sending enable signal
            control_data = {
                "action": "enable",
                "timestamp": time.time(),
                "message": "Logging enabled from frontend",
                "max_logs": 100  # Add max_logs parameter
            }
            
            # Send directly to HTTP input (no /control path)
            response = requests.post(
                FLUENT_BIT_URL,
                json=control_data,
                timeout=5,
                headers={"Content-Type": "application/json"}
            )
            
            print(f"Enable request sent. Status: {response.status_code}")
            print(f"Response: {response.text}")
            
            if response.status_code == 200 or response.status_code == 201:
                logging_enabled = True
                print("✅ Fluent logging enabled successfully.")
            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"Fluent Bit returned status {response.status_code}: {response.text}"
                )
                
        else:
            # Disable ingestion immediately
            control_data = {
                "action": "disable",
                "timestamp": time.time(),
                "message": "Logging disabled from frontend"
            }
            
            response = requests.post(
                FLUENT_BIT_URL,
                json=control_data,
                timeout=5,
                headers={"Content-Type": "application/json"}
            )
            
            print(f"Disable request sent. Status: {response.status_code}")
            
            if response.status_code == 200 or response.status_code == 201:
                logging_enabled = False
                print("✅ Fluent logging disabled successfully.")
            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"Fluent Bit returned status {response.status_code}: {response.text}"
                )
        
        return {
            "success": True,
            "enabled": request.enabled,
            "message": f"Logging {'enabled' if request.enabled else 'disabled'} successfully."
        }
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Request error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to communicate with Fluent Bit: {str(e)}"
        )
    except Exception as e:
        print(f"❌ Internal error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e)}"
        )

@router.get("/status")
async def get_logging_status():
    """Get current logging status."""
    return {
        "enabled": logging_enabled,
        "status": "active" if logging_enabled else "inactive"
    }