from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from rag.services.conv_manager import ConversationManager
import os

class SessionResponse(BaseModel):
    session_id: str
    messages: list
    count: int
    created_at: str
    status: str = "created"
    
session_router = APIRouter()

conversation_manager = ConversationManager()

@session_router.post("/sessions/create", response_model=SessionResponse)
async def create_session():
    try:
        session_data = conversation_manager.create_session()
        return SessionResponse(
            session_id=session_data["session_id"],
            messages=session_data["messages"],
            count=session_data["count"],
            created_at=session_data["created_at"],
            status="created"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")