import os
import sys
from pathlib import Path

current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import chat, suggestions, conversation, upload, fluent_control
from dotenv import load_dotenv

from database import Base, engine

load_dotenv()
frontendURL = os.getenv("FRONTEND_URL")

app = FastAPI()

origins = [
    frontendURL,
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

app.include_router(chat.router)
app.include_router(suggestions.router)
app.include_router(conversation.router)
app.include_router(upload.router)
app.include_router(fluent_control.router)  

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080)