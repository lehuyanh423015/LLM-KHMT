"""
Chat route.

This file is intentionally thin. Developer A keeps orchestration in
services/chat_orchestrator.py, while Developer B implements Knowledge + Memory
behind stable service interfaces.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.database import get_db
from models.schemas import ChatRequest, ChatResponse
from services.chat_orchestrator import handle_chat

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, db: Session = Depends(get_db)):
    """Receive a chat request and delegate the full pipeline to the orchestrator."""
    try:
        return await handle_chat(request=request, db=db)
    except Exception as e:
        print(f"[Chat Route Error] {e}")
        return ChatResponse(
            answer=f"Xin loi, da co loi xay ra: {str(e)}",
            session_id=request.session_id or "default-session",
        )
