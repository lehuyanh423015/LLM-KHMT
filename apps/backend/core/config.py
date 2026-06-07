"""
Application configuration — loads settings from .env file.
"""

import os
from dotenv import load_dotenv, find_dotenv

# Search for nearest .env file upwards from this directory
load_dotenv(find_dotenv(usecwd=True))


class Settings:
    """Central configuration for the application."""

    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    
    # Single-model configuration. Product knowledge comes from retrieval/memory;
    # the LLM is used for synthesis, explanation, and follow-up reasoning.
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen3:4b")
    OLLAMA_REWRITE_MODEL: str = os.getenv("OLLAMA_REWRITE_MODEL", "qwen2.5:0.5b")
    OLLAMA_CASUAL_MODEL: str = os.getenv("OLLAMA_CASUAL_MODEL", OLLAMA_REWRITE_MODEL)
    OLLAMA_NUM_PREDICT: int = int(os.getenv("OLLAMA_NUM_PREDICT", "768"))
    OLLAMA_TEMPERATURE: float = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
    OLLAMA_TIMEOUT_SECONDS: float = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "90"))
    OLLAMA_CASUAL_TIMEOUT_SECONDS: float = float(os.getenv("OLLAMA_CASUAL_TIMEOUT_SECONDS", "12"))
    
    # Feature / Experimentation Toggles
    ENABLE_MEMORY: bool = os.getenv("ENABLE_MEMORY", "true").lower() == "true"
    ENABLE_RECENT_CONTEXT: bool = os.getenv("ENABLE_RECENT_CONTEXT", "true").lower() == "true"
    ENABLE_PRODUCT_CONTEXT: bool = os.getenv("ENABLE_PRODUCT_CONTEXT", "true").lower() == "true"
    ENABLE_GROUNDED_PRODUCT_ANSWER: bool = os.getenv("ENABLE_GROUNDED_PRODUCT_ANSWER", "true").lower() == "true"
    ENABLE_LLM_GROUNDED_REWRITE: bool = os.getenv("ENABLE_LLM_GROUNDED_REWRITE", "true").lower() == "true"
    ENABLE_LLM_CLARIFICATION: bool = os.getenv("ENABLE_LLM_CLARIFICATION", "false").lower() == "true"
    ENABLE_LLM_CASUAL_CHAT: bool = os.getenv("ENABLE_LLM_CASUAL_CHAT", "true").lower() == "true"
    RECENT_CONTEXT_LIMIT: int = int(os.getenv("RECENT_CONTEXT_LIMIT", "6"))
    ENABLE_WEB_SEARCH: bool = os.getenv("ENABLE_WEB_SEARCH", "false").lower() == "true"
    WEB_SEARCH_RESULTS: int = int(os.getenv("WEB_SEARCH_RESULTS", "5"))
    ENABLE_EXTERNAL_PRODUCT_SEARCH: bool = os.getenv("ENABLE_EXTERNAL_PRODUCT_SEARCH", "false").lower() == "true"
    EXTERNAL_PRODUCT_SEARCH_RESULTS: int = int(os.getenv("EXTERNAL_PRODUCT_SEARCH_RESULTS", "3"))
    
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")

    @property
    def active_model(self) -> str:
        """Return the single Ollama model used for answer synthesis."""
        return self.OLLAMA_MODEL


settings = Settings()
