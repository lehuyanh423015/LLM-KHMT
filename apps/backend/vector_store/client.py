"""
Initializes and maintains the ChromaDB client for vector storage.
"""

try:
    import chromadb
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

from core.config import settings

# Initialize a persistent local Chroma client
if CHROMA_AVAILABLE:
    try:
        chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
    except Exception as e:
        print(f"Warning: ChromaDB failed to initialize: {e}")
        chroma_client = None
        CHROMA_AVAILABLE = False
else:
    print("Warning: chromadb package not found. Vector memory will be disabled.")
    chroma_client = None

def get_chroma_client():
    """Returns the configured ChromaDB client or None if unavailable."""
    return chroma_client
