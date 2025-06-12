from fastapi import File, UploadFile, APIRouter
import requests,os
from typing import Dict

router = APIRouter(prefix="/upload", tags=["upload"])

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> Dict:
    try:
        ingestion_url = os.environ.get("INGESTION_URL", "http://localhost:3001")
        response = requests.post(
            f"{ingestion_url}/receive",
            files={"document": (file.filename, file.file, file.content_type)}
        )

        if response.status_code != 200:
            return {"status": "error", "message": "Go server failed"}

        return {
            "status": "success",
            "go_server_response": response.json()
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}
