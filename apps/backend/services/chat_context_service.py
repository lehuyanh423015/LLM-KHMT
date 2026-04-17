"""
Service for retrieving conversational continuity parameters for LLM prompts.
"""
from typing import List, Dict
from sqlalchemy.orm import Session
from models.database_models import Message

def get_recent_messages(conversation_id: int, db: Session, limit: int = 6) -> List[Dict[str, str]]:
    """
    Fetches the most recent `limit` messages from a specific conversation.
    Returns them fully structured sequentially as a list of role/content dictionaries.
    """
    
    # Query explicit limits sequentially ordered backwards
    messages = db.query(Message)\
        .filter(Message.conversation_id == conversation_id)\
        .order_by(Message.id.desc())\
        .limit(limit)\
        .all()
    
    # Reverse the array chronologically for LLM array append
    messages.reverse()
    
    formatted_context = []
    for m in messages:
        formatted_context.append({
            "role": m.role,
            "content": m.content
        })
        
    return formatted_context
