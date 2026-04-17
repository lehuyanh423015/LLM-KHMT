"""
Initializes and maintains the ChromaDB client for vector storage.
"""

import chromadb
from core.config import settings

# Initialize a persistent local Chroma client
# This will save data to the path specified in .env
chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)

# Example: get or create a collection for document chunks
# collection = chroma_client.get_or_create_collection(name="documents")

def get_chroma_client():
    """Returns the configured ChromaDB client."""
    return chroma_client
