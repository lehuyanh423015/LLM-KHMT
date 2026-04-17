"""
Chat route — POST /chat

Receives a user message and returns an AI-generated response.
Also persists the conversation to the database.
"""

from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from models.schemas import ChatRequest, ChatResponse
from models.database_models import Conversation, Message
from services.llm.provider_factory import get_llm_provider
from services.retrieval_service import get_customer_context
from services.memory_service import extract_and_update_memory
from services.chat_context_service import get_recent_messages
from core.database import get_db

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Main chat endpoint.
    1. Fetches or creates Conversation tied to session_id.
    2. Saves the user's message to the database.
    3. Retrieves previously established Customer Memory.
    4. Retrieves Recent Conversational Context.
    5. Calls the LLM service to get a continuous response.
    6. Saves the assistant's response to the database.
    7. Triggers background task to extract metrics.
    """
    session_id = request.session_id or "default-session"
    
    # Fetch existing conversation for this session_id or create a new one
    conversation = db.query(Conversation).filter(Conversation.session_id == session_id).first()
    
    if not conversation:
        conversation = Conversation(title=request.message[:50], session_id=session_id)
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    from core.config import settings

    # Retrieve previous dialog to preserve conversational continuity BEFORE appending the current message
    recent_messages = []
    if settings.ENABLE_RECENT_CONTEXT:
        recent_messages = get_recent_messages(conversation.id, db, limit=settings.RECENT_CONTEXT_LIMIT)

    # Save the user's message
    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=request.message,
    )
    db.add(user_msg)
    db.commit()

    # Get formatting context memory
    memory_context = get_customer_context(session_id, db)

    # Get AI response
    try:
        provider = get_llm_provider()
        answer = await provider.generate_response(
            request.message, 
            memory_context=memory_context,
            recent_messages=recent_messages
        )
    except Exception as e:
        answer = f"Error: Could not retrieve response from LLM Provider - {str(e)}"

    # Save the assistant's response
    assistant_msg = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=answer,
    )
    db.add(assistant_msg)
    db.commit()

    # Trigger background parse 
    background_tasks.add_task(extract_and_update_memory, session_id, request.message, db)

    return ChatResponse(answer=answer)
