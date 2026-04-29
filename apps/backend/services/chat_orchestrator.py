"""
Chat Orchestrator Service

=== ORCHESTRATION LAYER (Developer A) ===
This module coordinates the entire chat flow:
1. Session ID handling
2. Loading recent conversation context
3. Loading customer memory context (via memory_service)
4. Loading product knowledge context (via product_retrieval_service - stub for Developer B)
5. Calling the LLM provider
6. Saving conversation/messages to DB
7. Triggering memory update (via memory_service)

This is the MAIN integration point. All chat logic flows through here.
The orchestrator assembles contexts and delegates to specialized services.

Developer B should extend the context loaders (memory_service, product_retrieval_service)
without changing this orchestrator's flow.

Type Contracts (stable interfaces):
- recent_messages: List[Dict[str, str]] with keys: "role", "content"
- memory_context: str (empty string if no memory loaded)
- product_context: str (empty string if no knowledge loaded)
"""

from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from models.database_models import Conversation, Message
from services.chat_context_service import get_recent_messages
from services.retrieval_service import get_customer_memory_context
from services.product_retrieval_service import get_product_knowledge_context
from services.memory_service import extract_and_update_customer_memory
from services.prompt_builder import build_llm_prompt
from services.llm.provider_factory import get_llm_provider
from core.config import settings


class ChatOrchestrator:
    """
    Main orchestration service for chat handling.
    
    Responsibilities:
    - Coordinate data loading (recent messages, memory, knowledge)
    - Build final prompt for LLM
    - Call LLM provider
    - Persist conversation
    - Trigger background tasks
    """

    async def handle_chat(
        self,
        user_message: str,
        session_id: str,
        db: Session
    ) -> Dict[str, Any]:
        """
        Main entry point for handling a chat message.
        
        Args:
            user_message: The user's input message
            session_id: Unique identifier for this conversation session
            db: SQLAlchemy database session
            
        Returns:
            Dict with keys:
                - "answer": str, the LLM's response
                - "conversation_id": int, the database ID of the conversation
                - "message_id": int, the database ID of the assistant's message
                
        Raises:
            Exception: If critical operations fail (with detailed error message)
        """
        
        # Step 1: Ensure conversation exists
        conversation = self._get_or_create_conversation(session_id, user_message, db)
        conversation_id = conversation.id
        
        # Step 2: Load recent messages (stable interface: List[Dict])
        recent_messages = self._load_recent_messages(conversation_id, db)
        
        # Step 3: Load customer memory context (stable interface: str)
        memory_context = self._load_memory_context(session_id, db)
        
        # Step 4: Load product knowledge context (stable interface: str)
        # This is where Developer B plugs in enhanced product search
        product_context = self._load_product_context(user_message, session_id, db)
        
        # Step 5: Save the user's message
        user_msg = self._save_user_message(conversation_id, user_message, db)
        
        # Step 6: Build final LLM prompt (centralized, stable assembly)
        llm_prompt_parts = build_llm_prompt(
            memory_context=memory_context,
            product_context=product_context,
            recent_messages=recent_messages,
            current_message=user_message
        )
        
        # Step 7: Call LLM provider
        try:
            provider = get_llm_provider()
            assistant_answer = await provider.generate_response(
                user_message=user_message,
                memory_context=memory_context,
                product_context=product_context,
                recent_messages=recent_messages
            )
        except Exception as e:
            assistant_answer = f"Xin lỗi, đã có lỗi xảy ra: {str(e)}"
        
        # Step 8: Save assistant's response
        assistant_msg = self._save_assistant_message(conversation_id, assistant_answer, db)
        
        # Step 9: Queue memory update task (fires asynchronously in the background)
        # Developer B should implement the actual memory extraction logic
        extract_and_update_customer_memory(
            session_id=session_id,
            user_message=user_message,
            assistant_response=assistant_answer,
            db=db
        )
        
        return {
            "answer": assistant_answer,
            "conversation_id": conversation_id,
            "message_id": assistant_msg.id
        }

    # ========== CONTEXT LOADERS (Stable Interfaces) ==========
    # Developer B extends these methods by modifying the underlying services
    
    def _load_recent_messages(self, conversation_id: int, db: Session) -> List[Dict[str, str]]:
        """
        Load recent conversation messages.
        
        Returns:
            List of {"role": "user"|"assistant", "content": "..."} dicts
            Empty list if ENABLE_RECENT_CONTEXT is disabled or no history exists
        """
        if not settings.ENABLE_RECENT_CONTEXT:
            return []
        
        messages = get_recent_messages(
            conversation_id=conversation_id,
            db=db,
            limit=settings.RECENT_CONTEXT_LIMIT
        )
        return messages

    def _load_memory_context(self, session_id: str, db: Session) -> str:
        """
        Load customer memory context.
        
        Calls: services/retrieval_service.get_customer_memory_context()
        
        Returns:
            Formatted string with customer profile info (budget, preferences, etc.)
            Empty string if ENABLE_MEMORY is disabled or no profile exists
        """
        if not settings.ENABLE_MEMORY:
            return ""
        
        memory_context = get_customer_memory_context(
            session_id=session_id,
            db=db
        )
        return memory_context

    def _load_product_context(self, user_message: str, session_id: str, db: Session) -> str:
        """
        Load product knowledge context.
        
        Calls: services/product_retrieval_service.get_product_knowledge_context()
        
        This is a STABLE INTERFACE for Developer B to extend.
        Currently returns empty string (stub).
        
        Expected future implementation:
        - Vector search over product database
        - Web search for real-time pricing
        - Filtered by customer budget + preferences
        
        Returns:
            Formatted string with relevant products/knowledge
            Empty string if no context available
        """
        product_context = get_product_knowledge_context(
            user_message=user_message,
            session_id=session_id,
            db=db
        )
        return product_context

    # ========== HELPER METHODS (Internal) ==========
    
    def _get_or_create_conversation(
        self, 
        session_id: str, 
        user_message: str,
        db: Session
    ) -> Conversation:
        """Find existing conversation or create new one."""
        conversation = db.query(Conversation).filter(
            Conversation.session_id == session_id
        ).first()
        
        if conversation:
            return conversation
        
        # Create new conversation with title from first message
        title = user_message[:50] if user_message else "New Conversation"
        conversation = Conversation(title=title, session_id=session_id)
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        return conversation

    def _save_user_message(self, conversation_id: int, message: str, db: Session) -> Message:
        """Save user's message to database."""
        msg = Message(
            conversation_id=conversation_id,
            role="user",
            content=message
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return msg

    def _save_assistant_message(self, conversation_id: int, message: str, db: Session) -> Message:
        """Save assistant's response to database."""
        msg = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=message
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return msg


# Singleton instance
_orchestrator_instance = None


def get_chat_orchestrator() -> ChatOrchestrator:
    """Get or create the orchestrator singleton."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = ChatOrchestrator()
    return _orchestrator_instance
