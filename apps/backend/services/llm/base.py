"""
Base LLM Provider Interface

=== LLM PROVIDER LAYER (Developer A) ===

Defines the stable interface that all LLM providers must implement.

STABLE INTERFACE:
    generate_response(
        user_message: str,
        memory_context: str = "",
        product_context: str = "",
        recent_messages: list = None
    ) -> str

This interface separates context injection from LLM calling logic.

Type Contracts:
- user_message: str (the current user input)
- memory_context: str (customer profile info, can be empty)
- product_context: str (product knowledge/search results, can be empty)
- recent_messages: List[Dict[str, str]] with keys "role" and "content"

Provider implementations should:
1. Accept these parameters
2. Build final prompt internally
3. Call LLM
4. Return assistant response as string

Provider should NOT modify orchestrator or routes.
Provider should only focus on LLM calling logic.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate_response(
        self,
        user_message: str,
        memory_context: str = "",
        product_context: str = "",
        recent_messages: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        STABLE INTERFACE - All providers must implement this.
        
        Generate a response from the LLM given a user message and context.
        
        Args:
            user_message: The user's current input message
            memory_context: Customer profile context (budget, preferences, etc.)
                           Empty string if no memory or memory disabled
            product_context: Product knowledge context (search results, recommendations)
                            Empty string if no knowledge or search disabled
            recent_messages: Recent conversation history for multi-turn context
                            List of {"role": "user"|"assistant", "content": "..."} dicts
                            None or empty list if no history
                            
        Returns:
            str: The assistant's response message
                 
        Implementation Note:
        Provider should build the final prompt by combining all contexts,
        then call the underlying LLM. The order should be:
        1. System prompt
        2. Memory context
        3. Product context
        4. Recent messages
        5. Current message
        
        See prompt_builder.py for reference implementation.
        """
        pass
