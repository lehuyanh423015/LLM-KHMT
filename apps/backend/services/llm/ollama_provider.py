import httpx
from typing import Optional, Dict, Any
from core.config import settings
from services.llm.base import BaseLLMProvider
from services.web_search_service import get_enriched_context
from services.product_search_service import search_products_enhanced
import json

class OllamaProvider(BaseLLMProvider):
    """LLM Provider for calling local Ollama instance via HTTP API."""

    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")

    async def generate_response(
        self, 
        user_message: str, 
        memory_context: str = "", 
        product_context: str = "",
        recent_messages: list = None,
        orchestration_context=None,
        dialogue_state=None
    ) -> str:
        """
        Calls Ollama with orchestrated conversation management.
        
        Implements the stable interface from BaseLLMProvider.
        
        Args:
            user_message: Current user input
            memory_context: Customer profile context
            product_context: Product knowledge context (NEW - from stable interface)
            recent_messages: Recent conversation history
            orchestration_context: Legacy context from dialogue orchestrator (deprecated)
            dialogue_state: Legacy dialogue state (deprecated)
            
        Returns:
            str: The assistant's response
        """
        current_model = settings.active_model
        
        # Build system prompt from contexts
        system_content = self._build_system_prompt(memory_context, product_context)
        
        # Legacy: Support old orchestration-aware prompting for backward compatibility
        if orchestration_context or dialogue_state:
            system_content = self._build_orchestrated_system_prompt(
                memory_context,
                orchestration_context,
                dialogue_state
            )
        
        # Get enriched context - check if using product search with URLs
        enriched_context = ""
        
        # Check if orchestration context specifies product search
        if orchestration_context and orchestration_context.get("tool_type") == "product_search":
            # Use enhanced product search with validation + URLs
            try:
                search_params = orchestration_context.get("tool_query", "{}")
                if isinstance(search_params, str):
                    try:
                        search_params = json.loads(search_params)
                    except json.JSONDecodeError:
                        # Fallback for plain string queries
                        search_params = {"query": search_params}
                
                search_products = await search_products_enhanced(
                    query=search_params.get("query", user_message),
                    category=search_params.get("category", "electronics"),
                    budget_max=search_params.get("budget_max"),
                    excluded_brands=search_params.get("excluded_brands", []),
                    num_results=8
                )
                
                if search_products:
                    enriched_context = _format_product_results_with_urls(search_products)
            except Exception as e:
                print(f"[Product Search Error] {e}")
                enriched_context = ""
        else:
            # Use general web search
            enriched_context = await get_enriched_context(user_message, memory_context)
        
        if enriched_context:
            system_content += f"\n{'=' * 70}\n"
            system_content += f"📡 DỮ LIỆU HIỆN TẠI (MỚI NHẤT - ƯU TIÊN DÙNG):\n"
            system_content += f"{enriched_context}\n"
            system_content += f"{'=' * 70}\n"
        
        # Build multi-turn contextual history
        payload_messages = [{"role": "system", "content": system_content}]
        if settings.ENABLE_RECENT_CONTEXT and recent_messages:
            payload_messages.extend(recent_messages)
        payload_messages.append({"role": "user", "content": user_message})
        
        try:
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
    
    
    def _build_system_prompt(
        self,
        memory_context: str,
        product_context: str
    ) -> str:
        """
        Build system prompt from stable context interface.
        
        This is the NEW standard prompt builder (simplified from orchestrated version).
        Used by default when orchestration_context is not provided.
        
        Args:
            memory_context: Customer profile info
            product_context: Product knowledge/search results
            
        Returns:
            str: Complete system prompt for LLM
        """
        base_prompt = (
            "Bạn là một trợ lý ảo tư vấn mua sắm CHUYÊN NGHIỆP. Năm hiện tại là 2026.\n\n"
            "🔴 NGUYÊN TẮC VÀNG (PRIORITY RULES):\n"
            "    1. LUÔN LUÔN ưu tiên thông tin từ INTERNET (2025-2026) hơn kiến thức cũ\n"
            "    2. KHÔNG sử dụng dữ liệu từ trước năm 2024 nếu có thông tin mới\n"
            "    3. LUÔN nêu rõ năm/thời gian của thông tin bạn sử dụng\n"
            "    4. 🚫 TUYỆT ĐỐI TUÂN THỦ NGÂN SÁCH (BUDGET): KHÔNG gợi ý sản phẩm vượt quá ngân sách đã nêu\n"
            "    5. 🚫 CHỐNG HALLUCINATION: KHÔNG TỰ BIẾN TẤU SẢN PHẨM HOẶC GIÁ\n"
            "       - Nếu không có dữ liệu, GỬI LỜI TỪ CHỐI thay vì bịa ra\n"
            "       - LUÔN GHI NGUỒN khi đưa ra thông tin sản phẩm/giá\n\n"
        )
        
        # Inject memory context
        if memory_context.strip():
            base_prompt += f"💾 THÔNG TIN KHÁCH HÀNG (Memory):\n{memory_context}\n\n"
        
        # Inject product context
        if product_context.strip():
            base_prompt += f"📦 KIẾN THỨC SẢN PHẨM (Knowledge Base):\n{product_context}\n\n"
        
        # Final instructions
        base_prompt += (
            "📝 HƯỚNG DẪN PHẢN HỒI:\n"
            "    - Trả lời bằng Tiếng Việt, rõ ràng, tự nhiên\n"
            "    - Nếu người dùng hỏi về sản phẩm, tham khảo THÔNG TIN KHÁCH HÀNG + KIẾN THỨC SẢN PHẨM\n"
            "    - Luôn lấy ý kiến của khách hàng trước khi gợi ý\n"
            "    - Giải thích lý do tại sao sản phẩm phù hợp với nhu cầu họ\n"
            "    - Chỉ hỏi những thứ thực sự cần thiết để hiểu rõ hơn\n"
        )
        
        return base_prompt
    
    def _build_orchestrated_system_prompt(
        self,
        memory_context: str,
        orchestration_context: Optional[Dict],
        dialogue_state: Optional[Any]
    ) -> str:
        """Build system prompt incorporating orchestration intelligence."""
        
        base_prompt = (
            "Bạn là một trợ lý ảo tư vấn mua sắm CHUYÊN NGHIỆP. Năm hiện tại là 2026.\n"
            "🔴 QUYẾT TẮC ƯORDERTH TIÊN ('NGUYÊN TẮC VÀNG'):\n"
            "    1. LUÔN LUÔN ưu tiên thông tin từ INTERNET (2025-2026) hơn kiến thức cũ\n"
            "    2. KHÔNG sử dụng dữ liệu từ trước năm 2024 nếu có thông tin mới\n"
            "    3. LUÔN nêu rõ năm/thời gian của thông tin bạn sử dụng\n"
            "    4. KHÔNG lặp lại các gợi ý sai từ trước\n"
            "    5. Ưu tiên ý định hiện tại và ràng buộc mới nhất của người dùng\n"
            "    6. 🚫 TUYỆT ĐỐI TUÂN THỦ NGÂN SÁCH (BUDGET): KHÔNG gợi ý sản phẩm vượt quá ngân sách đã nêu\n"
            "    7. 🎮 ƯU TIÊN GAMING: Nếu người dùng cần chơi game, hãy ưu tiên các mẫu có cấu hình mạnh (Chip Snapdragon 8+, Screen 120Hz+, tản nhiệt tốt) từ dữ liệu search\n"
            "    8. 🚫 CHỐNG HALLUCINATION: KHÔNG TỰ BIẾN TẤU SẢN PHẨM HOẶC GIÁ\n"
            "       - Nếu không có dữ liệu web search, GỬI LỜI TỪ CHỐI thay vì bịa ra\n"
            "       - LUÔN GHI NGUỒN khi đưa ra thông tin sản phẩm/giá\n"
            "       - KIỂM TRA dữ liệu web search - nếu không có, thừa nhận không biết\n\n"
        )
        
        # Add orchestration context if available
        if orchestration_context:
            intent = orchestration_context.get("intent", "product_recommendation")
            response_strategy = orchestration_context.get("response_strategy", "direct_advice")
            
            base_prompt += f"📋 HIỂU BÀI HỌC HIỆN TẠI:\n"
            base_prompt += f"   - Ý định: {intent}\n"
            base_prompt += f"   - Chiến lược phản hồi: {response_strategy}\n"
            
            if orchestration_context.get("learning_signal", {}).get("negative_feedback_detected"):
                base_prompt += (
                    "   - ⚠️ PHÁT HIỆN: Phản hồi trước không hợp lý\n"
                    "   - HÀNH ĐỘNG: Thay đổi hướng tư vấn, làm rõ yêu cầu, tránh lặp lại\n"
                )
            
            base_prompt += "\n"
            
            # Add response format instructions based on strategy
            if response_strategy == "grouped_recommendation":
                base_prompt += (
                    "📦 ĐỊNH DẠNG PHẢN HỒI - GROUPED RECOMMENDATIONS:\n"
                    "   Chia các sản phẩm/sách thành các nhóm rõ ràng (theo giá, thể loại, use-case, v.v.)\n"
                    "   ⚠️ NGUYÊN TẮC KHÔNG HALLUCINATE:\n"
                    "      - CHỈ liệt kê sản phẩm CÓ TRONG web search results\n"
                    "      - ĐỪNG bịa ra sản phẩm hoặc giá nếu không chắc chắn\n"
                    "      - Nếu không tìm được kết quả, thừa nhận: 'Xin lỗi, tôi không tìm được dữ liệu đủ chi tiết...'\n"
                    "   Dạng: \n"
                    "   🏷️ **Nhóm 1 (e.g., Entry-level):**\n"
                    "      - Sản phẩm A - Giá: XXX (Nguồn: ngày YY/MM/2026)\n"
                    "      - Sản phẩm B - Giá: XXX\n"
                    "   🏷️ **Nhóm 2 (e.g., Mid-range):**\n"
                    "      - Sản phẩm C - Giá: XXX\n"
                    "      - Sản phẩm D - Giá: XXX\n"
                    "   📝 Sau đó, HỎI ĐẾ XƯ TIÊN DUY NHẤT: 'Nhóm nào hợp với bạn?'\n\n"
                )
            
            elif response_strategy == "compare_options":
                base_prompt += (
                    "📊 ĐỊNH DẠNG PHẢN HỒI - COMPARISON:\n"
                    "   Bảng so sánh rõ ràng các sản phẩm/sách đối lập:\n"
                    "   | Đặc điểm | Lựa chọn A | Lựa chọn B | Lựa chọn C |\n"
                    "   | --- | --- | --- | --- |\n"
                    "   Không cần hỏi theo sau khi so sánh - đủ dữ liệu để quyết định.\n\n"
                )
            
            elif response_strategy == "tool_augmented_recommendation":
                base_prompt += (
                    "🔍 ĐỊNH DẠNG PHẢN HỒI - TOOL-AUGMENTED:\n"
                    "   Bao gồm giá hiện tại, nơi mua, tình trạng hàng từ tìm kiếm web.\n"
                    "   Ưu tiên thông tin RỒI NHẤT (2025-2026).\n"
                    "   LUÔN GHI NGUỒN DỮ LIỆU (nơi, ngày cập nhật).\n"
                    "   ⚠️ KHÔNG được sáng tạo: Nếu web search không có data cụ thể, nói 'Dữ liệu không khả dụng'\n\n"
                )
        
            # Add one-follow-up enforcement
            base_prompt += (
                "🚨 QUY TẮC CHI HỎI:\n"
                "   - Chỉ HỎI TỐI ĐA MỘT CÂU FOLLOW-UP nếu thực sự cần\n"
                "   - Không hỏi những thứ có thể suy luận từ ngữ cảnh\n"
                "   - Không hỏi những tính năng sẽ chi tiết trong recommendations\n"
                "   - Không hỏi một cách thụ động - luôn TRẢ LỜI TRƯỚC\n\n"
            )
        
        # Add dialogue state constraints if available
        if dialogue_state:
            constraints = self._extract_state_constraints(dialogue_state)
            if constraints:
                base_prompt += f"📌 RÀNG BUỘC MỚI NHẤT:\n{constraints}\n"
            
            # CRITICAL: Inject excluded brands/items from dialog state
            if dialogue_state.excluded_categories and len(dialogue_state.excluded_categories) > 0:
                excluded_list = ", ".join(dialogue_state.excluded_categories)
                base_prompt += f"\n🚫 LOẠI TRỪ (từ các turn trước):\n   - Brand/Model: {excluded_list}\n   - KHÔNG được gợi ý những loại này dù bao nhiêu lần user hỏi\n"
        
        # Add memory context
        if memory_context:
            base_prompt += f"\n💾 KỸ NĂ KHÁCH HÀNG:\n{memory_context}\n"
        
        base_prompt += (
            "\n⚠️ NGUYÊN TẮC CẢI TIẾN:\n"
            "- Nếu câu hỏi thay đổi hướng, không bám vào gợi ý cũ\n"
            "- Chỉ đề xuất sản phẩm trong ngân sách và phù hợp mục đích\n"
            "- Nêu rõ khoảng giá và năm cập nhật\n"
            "- Hỏi thêm nếu thực sự cần để hiểu rõ hơn\n"
            "- 🚫 KHÔNG được coi thường constraint budget - PHẢI lọc sản phẩm ngoài giá\n"
            "- 🚫 KHÔNG được bịa ra sản phẩm/giá - CHỈ dùng dữ liệu search results\n"
            "- 🚫 Nếu sản phẩm từ search result vượt budget, LỌC ĐI và nói 'sản phẩm này vượt ngân sách'\n"
        )
        
        return base_prompt
    
    def _extract_state_constraints(self, dialogue_state: Any) -> str:
        """Extract constraints from dialogue state for prompt."""
        constraints_text = ""
        
        if dialogue_state.recipient:
            constraints_text += f"   - Người nhận: {dialogue_state.recipient}\n"
        
        if dialogue_state.occasion:
            constraints_text += f"   - Dịp: {dialogue_state.occasion}\n"
        
        if dialogue_state.budget_max:
            constraints_text += f"   - Ngân sách tối đa: {dialogue_state.budget_max:,} VND\n"
        
        if dialogue_state.product_category:
            constraints_text += f"   - Danh mục: {dialogue_state.product_category}\n"
        
        if dialogue_state.preferences:
            prefs = ", ".join(dialogue_state.preferences[:3])
            constraints_text += f"   - Ưu tiên: {prefs}\n"
        
        if dialogue_state.excluded_categories:
            excluded = ", ".join(dialogue_state.excluded_categories[:2])
            constraints_text += f"   - Loại trừ: {excluded}\n"
        
        if dialogue_state.price_sensitivity:
            constraints_text += f"   - Nhạy giá: {dialogue_state.price_sensitivity}\n"
        
        return constraints_text


def _format_product_results_with_urls(products: list) -> str:
    """
    Format product search results with URLs for LLM context.
    Includes verification status to indicate reliability.
    """
    if not products:
        return "Không tìm thấy sản phẩm phù hợp."
    
    formatted = "🛍️ SẢN PHẨM TÌM ĐƯỢC (CÓ URL):\n\n"
    
    for idx, product in enumerate(products, 1):
        verified_badge = "✅" if product.get("verified") else "⚠️"
        
        formatted += f"{idx}. {verified_badge} {product.get('product_name', 'N/A')}\n"
        formatted += f"   Brand: {product.get('brand', 'N/A')}\n"
        formatted += f"   Giá: {product.get('price_vnd', 'Liên hệ')}\n"
        formatted += f"   Nguồn: {product.get('source', 'Web')}\n"
        formatted += f"   🔗 URL: {product.get('url', 'N/A')}\n"
        
        if product.get("description"):
            description = product["description"][:100] + "..." if len(product["description"]) > 100 else product["description"]
            formatted += f"   Mô tả: {description}\n"
        
        formatted += "\n"
    
    formatted += "\n📌 LƯU Ý:\n"
    formatted += "✅ = Thông tin đã xác minh từ nhiều nguồn\n"
    formatted += "⚠️ = Thông tin từ một nguồn (cần kiểm tra)\n"
    formatted += "🔗 Bấm URL để xem chi tiết đầy đủ và mua hàng\n"
    
    return formatted

