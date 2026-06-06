"""Ollama LLM provider.

Developer A owns this file. Keep it focused on provider duties:
building Ollama-compatible messages from the central prompt builder, calling
Ollama, and using the single configured synthesis model.

Knowledge retrieval, web search, product search, and memory extraction belong
behind the stable service interfaces called by chat_orchestrator.py.
"""

from typing import Dict, List, Optional

import httpx

from core.config import settings
from services.llm.base import BaseLLMProvider
from services.prompt_builder import build_llm_prompt


class OllamaProvider(BaseLLMProvider):
    """LLM provider for a local Ollama instance."""

    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")

    async def generate_response(
        self,
        user_message: str,
        memory_context: str = "",
        product_context: str = "",
        recent_messages: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        Generate an assistant response using only contexts supplied by the orchestrator.
        """
        prompt_parts = build_llm_prompt(
            memory_context=memory_context,
            product_context=product_context,
            recent_messages=recent_messages or [],
            current_message=user_message,
        )

        payload_messages = [{"role": "system", "content": prompt_parts["system"]}]
        payload_messages.extend(prompt_parts["conversation_history"])
        payload_messages.append({"role": "user", "content": prompt_parts["current_message"]})

        try:
            async with httpx.AsyncClient(timeout=settings.OLLAMA_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": settings.active_model,
                        "messages": payload_messages,
                        "stream": False,
                        "options": {
                            "num_predict": settings.OLLAMA_NUM_PREDICT,
                            "temperature": settings.OLLAMA_TEMPERATURE,
                        },
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data.get("message", {}).get(
                    "content",
                    "Sorry, I couldn't generate a response.",
                )
        except httpx.ConnectError:
            return "Error: Could not connect to Ollama. Please ensure Ollama is running locally."
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return (
                    f"Error: Model '{settings.active_model}' not found in Ollama. "
                    f"Please pull it first using 'ollama run {settings.active_model}'."
                )
            return f"Error from Ollama API: {e.response.text}"
        except Exception as e:
            print(f"[Ollama Provider Error] {e}")
            return f"An unexpected error occurred while calling Ollama: {str(e)}"
