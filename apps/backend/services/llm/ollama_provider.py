import httpx
from core.config import settings
from services.llm.base import BaseLLMProvider

class OllamaProvider(BaseLLMProvider):
    """LLM Provider for calling local Ollama instance via HTTP API."""

    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")

    async def generate_response(self, user_message: str, memory_context: str = "", recent_messages: list = None) -> str:
        """
        Calls Ollama's /api/chat endpoint to get a response.
        Appends the shopping assistant persona and any memory context.
        """
        current_model = settings.active_model
        
        system_content = (
            "Bạn là một trợ lý ảo tư vấn mua sắm chuyên nghiệp và nhiệt tình. "
            "Nhiệm vụ của bạn là đưa ra các lời khuyên mua sắm hữu ích, rõ ràng và mạch lạc. "
            "Nếu bạn không có dữ liệu giá chính xác trên thị trường hiện tại, hãy ước lượng một cách hợp lý và nói rõ đó là mức giá tham khảo. "
            "Đừng từ chối trả lời quá nhanh; hãy cố gắng gợi ý các lựa chọn thay thế. "
            "Hãy chủ động hỏi thêm về nhu cầu, sở thích hoặc ngân sách của khách hàng để thu hẹp phạm vi tìm kiếm."
        )
        
        if settings.ENABLE_MEMORY and memory_context:
            system_content += f"\n\n{memory_context}\n\nLƯU Ý QUAN TRỌNG: Hãy sử dụng NHỮNG SỞ THÍCH VÀ RÀNG BUỘC CỦA KHÁCH HÀNG Ở TRÊN để cá nhân hóa câu trả lời một cách tự nhiên nhất. KHÔNG gợi ý những thứ khách hàng ghét."
            
        # Build multi-turn contextual history
        payload_messages = [{"role": "system", "content": system_content}]
        if settings.ENABLE_RECENT_CONTEXT and recent_messages:
            payload_messages.extend(recent_messages)
        payload_messages.append({"role": "user", "content": user_message})
            
        try:
            # Increased timeout to 300 seconds for slow local CPU inference
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": current_model,
                        "messages": payload_messages,
                        "stream": False
                    }
                )
                response.raise_for_status()
                data = response.json()
                return data.get("message", {}).get("content", "Sorry, I couldn't generate a response.")
        except httpx.ConnectError:
            return "Error: Could not connect to Ollama. Please ensure Ollama is running locally."
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return f"Error: Model '{current_model}' not found in Ollama. Please pull it first using 'ollama run {current_model}'."
            return f"Error from Ollama API: {e.response.text}"
        except Exception as e:
            print(f"[Ollama Provider Error] {e}")
            return f"An unexpected error occurred while calling Ollama: {str(e)}"
