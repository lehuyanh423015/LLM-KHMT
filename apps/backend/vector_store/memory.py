"""
Memory and Continual Learning placeholder module.

This module will eventually handle:
- Embedding past conversations.
- Storing facts about the user.
- Retrieving relevant context for the current query.
"""

from vector_store.client import get_chroma_client
from core.database import SessionLocal

def add_to_memory(text: str):
    """
    Placeholder: Embed the text and save it to ChromaDB.
    """
    pass

def retrieve_context(query: str, limit: int = 3) -> list[str]:
    """
    Placeholder: Search ChromaDB for relevant past context.
    """
    return []
