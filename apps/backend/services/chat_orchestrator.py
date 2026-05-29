"""
Chat Orchestrator Service

Developer A owns this file. It is the only coordinator for the chat pipeline:
session handling, context loading, LLM call, persistence, and memory update.

Developer B plugs Knowledge + Memory logic behind the stable service functions:
- retrieval_service.get_customer_memory_context()
- product_retrieval_service.get_product_knowledge_context()
- memory_service.extract_and_update_customer_memory()
"""

from typing import Any, Dict, List

from sqlalchemy.orm import Session

from core.config import settings
from models.database_models import Conversation, Message
from models.schemas import ChatRequest, ChatResponse
from services.chat_context_service import get_recent_messages
from services.llm.provider_factory import get_llm_provider
from services.memory_service import extract_and_update_customer_memory
from services.product_retrieval_service import (
    get_grounded_product_answer,
    get_product_knowledge_context,
)
from services.retrieval_service import get_customer_memory_context


class ChatOrchestrator:
    """Main orchestration service for chat handling."""

    async def handle_chat(
        self,
        user_message: str,
        session_id: str,
        db: Session,
    ) -> Dict[str, Any]:
        """
        Coordinate one chat turn end-to-end.

        Context contracts:
        - recent_messages: list[dict] with role/content keys
        - memory_context: str
        - product_context: str
        """
        conversation = self._get_or_create_conversation(session_id, user_message, db)
        conversation_id = conversation.id

        recent_messages = self._load_recent_messages(conversation_id, db)
        memory_context = self._load_memory_context(session_id, db)
        product_context = self._load_product_context(user_message, session_id, db)

        self._save_user_message(conversation_id, user_message, db)

        grounded_answer_used = False
        if product_context and settings.ENABLE_GROUNDED_PRODUCT_ANSWER:
            assistant_answer = get_grounded_product_answer(
                user_message=user_message,
                session_id=session_id,
                db=db,
            )
            grounded_answer_used = bool(assistant_answer)
        else:
            assistant_answer = ""

        if not assistant_answer:
            try:
                provider = get_llm_provider()
                assistant_answer = await provider.generate_response(
                    user_message=user_message,
                    memory_context=memory_context,
                    product_context=product_context,
                    recent_messages=recent_messages,
                )
            except Exception as e:
                assistant_answer = f"Xin loi, da co loi xay ra: {str(e)}"

        if not assistant_answer.strip():
            assistant_answer = (
                "Xin loi, toi chua tao duoc cau tra loi. "
                "Ban co the thu lai o che do FAST hoac tat QUALITY neu may chay cham."
            )

        assistant_msg = self._save_assistant_message(conversation_id, assistant_answer, db)

        # Synchronous update keeps this student prototype DB-session safe.
        # Developer B can improve extraction internals without changing this call.
        extract_and_update_customer_memory(
            session_id=session_id,
            user_message=user_message,
            assistant_response=assistant_answer,
            db=db,
        )

        return {
            "answer": assistant_answer,
            "session_id": session_id,
            "conversation_id": conversation_id,
            "message_id": assistant_msg.id,
            "debug": self._build_debug_context(
                recent_messages=recent_messages,
                memory_context=memory_context,
                product_context=product_context,
                grounded_answer_used=grounded_answer_used,
            ),
        }

    def _load_recent_messages(self, conversation_id: int, db: Session) -> List[Dict[str, str]]:
        """Load recent role/content messages when the experiment flag is enabled."""
        if not settings.ENABLE_RECENT_CONTEXT:
            return []
        return get_recent_messages(
            conversation_id=conversation_id,
            db=db,
            limit=settings.RECENT_CONTEXT_LIMIT,
        )

    def _load_memory_context(self, session_id: str, db: Session) -> str:
        """Load formatted customer memory through Developer B's stable interface."""
        if not settings.ENABLE_MEMORY:
            return ""
        return get_customer_memory_context(session_id=session_id, db=db)

    def _load_product_context(self, user_message: str, session_id: str, db: Session) -> str:
        """Load formatted product knowledge through Developer B's stable interface."""
        if not settings.ENABLE_PRODUCT_CONTEXT:
            return ""
        return get_product_knowledge_context(
            user_message=user_message,
            session_id=session_id,
            db=db,
        )

    def _get_or_create_conversation(
        self,
        session_id: str,
        user_message: str,
        db: Session,
    ) -> Conversation:
        """Find existing conversation or create a new one."""
        conversation = (
            db.query(Conversation)
            .filter(Conversation.session_id == session_id)
            .first()
        )
        if conversation:
            return conversation

        conversation = Conversation(
            title=user_message[:50] if user_message else "New Conversation",
            session_id=session_id,
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        return conversation

    def _save_user_message(self, conversation_id: int, message: str, db: Session) -> Message:
        """Persist the user's message."""
        return self._save_message(conversation_id, "user", message, db)

    def _save_assistant_message(self, conversation_id: int, message: str, db: Session) -> Message:
        """Persist the assistant's response."""
        return self._save_message(conversation_id, "assistant", message, db)

    def _save_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        db: Session,
    ) -> Message:
        msg = Message(conversation_id=conversation_id, role=role, content=content)
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return msg

    def _build_debug_context(
        self,
        recent_messages: List[Dict[str, str]],
        memory_context: str,
        product_context: str,
        grounded_answer_used: bool,
    ) -> Dict[str, Any]:
        """Expose lightweight debug metadata for demos and experiments."""
        return {
            "llm_mode": settings.LLM_MODE,
            "active_model": settings.active_model,
            "memory_enabled": settings.ENABLE_MEMORY,
            "recent_context_enabled": settings.ENABLE_RECENT_CONTEXT,
            "product_context_enabled": settings.ENABLE_PRODUCT_CONTEXT,
            "recent_message_count": len(recent_messages or []),
            "memory_context_loaded": bool(memory_context.strip()),
            "product_context_loaded": bool(product_context.strip()),
            "grounded_answer_used": grounded_answer_used,
        }


_orchestrator_instance = None


def get_chat_orchestrator() -> ChatOrchestrator:
    """Get or create the orchestrator singleton."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = ChatOrchestrator()
    return _orchestrator_instance


async def handle_chat(request: ChatRequest, db: Session) -> ChatResponse:
    """
    Route-facing entry point.

    Keep routes/chat.py thin by delegating the full pipeline here.
    """
    session_id = request.session_id or "default-session"
    result = await get_chat_orchestrator().handle_chat(
        user_message=request.message,
        session_id=session_id,
        db=db,
    )
    return ChatResponse(
        answer=result["answer"],
        session_id=result["session_id"],
        debug=result["debug"],
    )
