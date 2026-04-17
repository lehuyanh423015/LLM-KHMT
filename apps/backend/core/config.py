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
    
    # Model Operation Modes Configuration
    LLM_MODE: str = os.getenv("LLM_MODE", "fast")
    OLLAMA_FAST_MODEL: str = os.getenv("OLLAMA_FAST_MODEL", "qwen2.5:0.5b")
    OLLAMA_QUALITY_MODEL: str = os.getenv("OLLAMA_QUALITY_MODEL", "qwen3:4b")
    
    # Feature / Experimentation Toggles
    ENABLE_MEMORY: bool = os.getenv("ENABLE_MEMORY", "true").lower() == "true"
    ENABLE_RECENT_CONTEXT: bool = os.getenv("ENABLE_RECENT_CONTEXT", "true").lower() == "true"
    RECENT_CONTEXT_LIMIT: int = int(os.getenv("RECENT_CONTEXT_LIMIT", "6"))
    
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")

    @property
    def active_model(self) -> str:
        """Resolves the current active Ollama model based on LLM_MODE."""
        # Fallback to fast mode safely against invalid env entries.
        if self.LLM_MODE.strip().lower() == "quality":
            return self.OLLAMA_QUALITY_MODEL
        return self.OLLAMA_FAST_MODEL


settings = Settings()
