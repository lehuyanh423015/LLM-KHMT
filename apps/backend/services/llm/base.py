from abc import ABC, abstractmethod

class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate_response(self, user_message: str, memory_context: str = "", recent_messages: list = None) -> str:
        """
        Generate a response from the LLM given a user message and optional context.
        """
        pass
