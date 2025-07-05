import requests
import time
import threading
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/fluent", tags=["fluent-control"])

FLUENT_BIT_URL = "http://fluent-bit:9880"

class FluentControlRequest(BaseModel):
    enabled: bool

logging_enabled = False
ingesting = False

@router.post("/toggle")
async def toggle_logging(request: FluentControlRequest):
    global logging_enabled, ingesting

    try:
        if request.enabled:
            control_data = {
                "action": "enable",
                "timestamp": time.time(),
                "message": "Logging enabled from frontend",
                "max_logs": 10 
            }

            response = requests.post(
                FLUENT_BIT_URL,
                json=control_data,
                timeout=5,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code in [200, 201]:
                logging_enabled = True
                ingesting = True
                print("✅ Logging enabled")

                def auto_disable():
                    time.sleep(20)  
                    print("Ingestion complete, disabling logging")
                    global logging_enabled, ingesting
                    logging_enabled = False
                    ingesting = False

                threading.Thread(target=auto_disable, daemon=True).start()

            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"Fluent Bit returned {response.status_code}: {response.text}"
                )

        else:
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

            if response.status_code in [200, 201]:
                logging_enabled = False
                ingesting = False
                print("Logging disabled")
            else:
                raise HTTPException(status_code=500, detail="Failed to disable logging")

        return {
            "success": True,
            "enabled": request.enabled
        }

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_logging_status():
    return {
        "enabled": logging_enabled,
        "ingesting": ingesting,
        "status": "ingesting" if ingesting else "idle"
    }
