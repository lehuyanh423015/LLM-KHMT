from core.config import settings
from services.llm.base import BaseLLMProvider
from services.llm.ollama_provider import OllamaProvider

def get_llm_provider() -> BaseLLMProvider:
    """
    Factory method to retrieve the correct LLM provider instance
    based on the application configuration.
    """
    provider_name = settings.LLM_PROVIDER.lower()
    
    if provider_name == "ollama":
        return OllamaProvider()
    else:
        # Fallback or extension point for other providers
        raise ValueError(f"Unsupported LLM provider: {provider_name}")
