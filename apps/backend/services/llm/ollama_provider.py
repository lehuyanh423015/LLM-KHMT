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

    async def rewrite_grounded_answer(
        self,
        user_message: str,
        grounded_draft: str,
        memory_context: str = "",
    ) -> str:
        """
        Fast, narrow LLM pass for turning grounded product notes into a natural answer.

        This intentionally avoids the full prompt/context path because comparison
        rewrites should be short and must not invent extra product facts.
        """
        system_prompt = (
            "You are a Vietnamese shopping assistant. /no_think\n"
            "Rewrite grounded product notes into a natural Vietnamese answer with full diacritics.\n"
            "Use only facts in the grounded notes and customer memory. Do not add products, prices, specs, links, or claims.\n"
            "For comparisons, start with 'Kết luận:' and state which product is better for which need.\n"
            "For one named product, focus only on that product unless alternatives are requested.\n"
            "Keep the answer practical and concise."
        )
        user_prompt = (
            f"CUSTOMER MEMORY:\n{memory_context or 'Không có.'}\n\n"
            f"USER QUESTION:\n{user_message}\n\n"
            f"GROUNDED NOTES:\n{grounded_draft}\n\n"
            "Write the final answer in natural Vietnamese. /no_think"
        )
        try:
            async with httpx.AsyncClient(timeout=min(settings.OLLAMA_TIMEOUT_SECONDS, 45.0)) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": settings.OLLAMA_REWRITE_MODEL or settings.active_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "stream": False,
                        "options": {
                            "num_predict": min(settings.OLLAMA_NUM_PREDICT, 420),
                            "temperature": min(settings.OLLAMA_TEMPERATURE, 0.2),
                        },
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data.get("message", {}).get("content", "")
        except Exception as e:
            print(f"[Ollama Grounded Rewrite Error] {e}")
            return ""

    async def generate_general_response(
        self,
        user_message: str,
        recent_messages: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Answer normal conversation that is not a product-shopping request."""
        system_prompt = (
            "Bạn là trợ lý trò chuyện bằng tiếng Việt. /no_think\n"
            "Trả lời tự nhiên, ngắn gọn và đúng trọng tâm.\n"
            "Không tự gợi ý sản phẩm, không mở catalog, không đưa checklist mua hàng "
            "trừ khi người dùng hỏi rõ về mua sắm hoặc sản phẩm.\n"
            "Nếu người dùng hỏi về khả năng của bạn, hãy nói bạn có thể trò chuyện, "
            "giải thích và hỗ trợ tư vấn mua sắm khi họ cần."
        )
        system_prompt += (
            "\nTone rules: reply in natural Vietnamese with full diacritics. "
            "Use 'mình' for yourself and 'bạn' for the user. "
            "For light tiredness or stress, give brief empathy and a simple next step; "
            "do not refuse and do not suggest medical help unless there is danger, self-harm, or severe symptoms."
        )
        messages = [{"role": "system", "content": system_prompt}]
        for message in (recent_messages or [])[-4:]:
            role = message.get("role")
            content = message.get("content")
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": f"{user_message}\n/no_think"})

        try:
            async with httpx.AsyncClient(timeout=min(settings.OLLAMA_TIMEOUT_SECONDS, settings.OLLAMA_CASUAL_TIMEOUT_SECONDS)) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": settings.OLLAMA_CASUAL_MODEL or settings.active_model,
                        "messages": messages,
                        "stream": False,
                        "options": {
                            "num_predict": min(settings.OLLAMA_NUM_PREDICT, 220),
                            "temperature": min(max(settings.OLLAMA_TEMPERATURE, 0.2), 0.5),
                        },
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data.get("message", {}).get("content", "")
        except Exception as e:
            print(f"[Ollama General Chat Error] {e}")
            return ""

    async def generate_clarification_response(
        self,
        user_message: str,
        fallback_question: str,
        recent_messages: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        Rewrite a missing-information question in a natural Vietnamese tone.

        The orchestrator validates this output and falls back to fallback_question
        if the model starts recommending products or returns an error.
        """
        system_prompt = (
            "Bạn là trợ lý tư vấn mua sắm tiếng Việt. /no_think\n"
            "Người dùng mới nêu nhu cầu mua hàng nhưng còn thiếu thông tin.\n"
            "Hãy hỏi lại tự nhiên bằng tiếng Việt có dấu, thân thiện nhưng ngắn gọn.\n"
            "Luôn xưng 'mình' và gọi người dùng là 'bạn'. Không dùng 'tôi'.\n"
            "Không dịch máy móc, không viết câu lạ như 'tìm một cho mình'.\n"
            "Không gợi ý sản phẩm, không nêu tên model, không đưa checklist dài.\n"
            "Nên hỏi 2-3 ý quan trọng như ngân sách, mục đích dùng, sở thích/hãng muốn tránh.\n"
            "Có thể đưa 1 ví dụ câu trả lời mẫu nếu hữu ích."
        )
        messages = [{"role": "system", "content": system_prompt}]
        for message in (recent_messages or [])[-4:]:
            role = message.get("role")
            content = message.get("content")
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Người dùng vừa nói: {user_message}\n\n"
                    f"Câu hỏi fallback cần giữ ý chính:\n{fallback_question}\n\n"
                    "Hãy viết lại tự nhiên hơn, vẫn chỉ hỏi thêm thông tin. /no_think"
                ),
            }
        )

        try:
            async with httpx.AsyncClient(timeout=min(settings.OLLAMA_TIMEOUT_SECONDS, 25.0)) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": settings.active_model,
                        "messages": messages,
                        "stream": False,
                        "options": {
                            "num_predict": min(settings.OLLAMA_NUM_PREDICT, 180),
                            "temperature": min(max(settings.OLLAMA_TEMPERATURE, 0.25), 0.45),
                        },
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data.get("message", {}).get("content", "")
        except Exception as e:
            print(f"[Ollama Clarification Error] {e}")
            return ""
