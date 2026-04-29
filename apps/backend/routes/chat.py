"""
Chat Route — POST /chat

=== THIN ROUTE LAYER (Developer A) ===

This route is now a thin wrapper that:
1. Validates request
2. Delegates to chat orchestrator
3. Returns response

The orchestrator handles ALL coordination logic.
This keeps routes simple and testable.

Route responsibilities:
- Parse and validate ChatRequest
- Extract session_id
- Call orchestrator.handle_chat()
- Return ChatResponse
- Handle errors gracefully

All business logic is in services/chat_orchestrator.py.
Routes should never do orchestration directly.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from models.schemas import ChatRequest, ChatResponse
from services.chat_orchestrator import get_chat_orchestrator
from core.database import get_db

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, db: Session = Depends(get_db)):
    """
    Main chat endpoint.
    
    Flow:
    1. Parse request
    2. Get orchestrator
    3. Delegate to orchestrator.handle_chat()
    4. Return response
    
    The orchestrator handles:
    - Session/conversation management
    - Loading context (memory, knowledge, recent messages)
    - Calling LLM
    - Saving to database
    - Triggering memory update
    
    Args:
        request: ChatRequest with message and optional session_id
        db: Database session
        
    Returns:
        ChatResponse with the assistant's answer
    """
    
    session_id = request.session_id or "default-session"
    orchestrator = get_chat_orchestrator()
    
    try:
        result = await orchestrator.handle_chat(
            user_message=request.message,
            session_id=session_id,
            db=db
        )
        return ChatResponse(answer=result["answer"])
    except Exception as e:
        print(f"[Chat Route Error] {e}")
        error_message = f"Xin lỗi, đã có lỗi xảy ra: {str(e)}"
        return ChatResponse(answer=error_message)

