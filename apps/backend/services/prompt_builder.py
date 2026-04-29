"""
Prompt Builder Module

=== CENTRAL PROMPT ASSEMBLY (Developer A) ===

This module centralizes ALL prompt building logic.
All LLM prompts must go through this builder to ensure consistency.

The final prompt structure is:
1. System prompt (instructions, roles, constraints)
2. Customer memory context (budget, preferences, dislikes)
3. Product knowledge context (real-time product info, search results)
4. Recent conversation messages (multi-turn context)
5. Current user message (the new input to respond to)

Developer B should NOT modify LLM provider code to inject context.
Instead, they should enhance get_product_knowledge_context() in product_retrieval_service.py.

Type Contract:
- memory_context: str (can be empty)
- product_context: str (can be empty)
- recent_messages: List[Dict] with keys: "role", "content"
- current_message: str
"""

from typing import Dict, List, Optional


def build_llm_prompt(
    memory_context: str,
    product_context: str,
    recent_messages: List[Dict[str, str]],
    current_message: str
) -> Dict[str, str]:
    """
    Build the final prompt structure for LLM input.
    
    Args:
        memory_context: Customer profile info (budget, preferences, etc.)
        product_context: Product/knowledge information (search results, recommendations)
        recent_messages: Recent conversation history
        current_message: The user's current input message
        
    Returns:
        Dict with keys:
            - "system": str, the system prompt
            - "conversation_history": List[Dict], the recent messages
            - "current_message": str, the current user input
    """
    
    # Build the system prompt with all injected context
    system_prompt = _build_system_prompt(memory_context, product_context)
    
    return {
        "system": system_prompt,
        "conversation_history": recent_messages,
        "current_message": current_message
    }


def _build_system_prompt(memory_context: str, product_context: str) -> str:
    """
    Build the comprehensive system prompt.
    
    This is where all context gets assembled for the LLM.
    The order is important:
    1. Base instructions
    2. Customer memory
    3. Product knowledge
    4. Special constraints
    
    Developer A maintains this function.
    Developer B should only extend product_context via product_retrieval_service.
    """
    
    # BASE INSTRUCTIONS & ROLES
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
    
    # INJECT CUSTOMER MEMORY
    if memory_context.strip():
        base_prompt += f"📋 THÔNG TIN KHÁCH HÀNG (Memory):\n{memory_context}\n\n"
    
    # INJECT PRODUCT KNOWLEDGE
    if product_context.strip():
        base_prompt += f"📦 KIẾN THỨC SẢN PHẨM (Knowledge Base):\n{product_context}\n\n"
    
    # FINAL INSTRUCTIONS
    base_prompt += (
        "📝 HƯỚNG DẪN PHẢN HỒI:\n"
        "    - Trả lời bằng Tiếng Việt, rõ ràng, tự nhiên\n"
        "    - Nếu người dùng hỏi về sản phẩm, tham khảo THÔNG TIN KHÁCH HÀNG + KIẾN THỨC SẢN PHẨM\n"
        "    - Luôn lấy ý kiến của khách hàng trước khi gợi ý\n"
        "    - Giải thích lý do tại sao sản phẩm phù hợp với nhu cầu họ\n"
    )
    
    return base_prompt


def format_recent_messages_for_llm(recent_messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Format recent messages into LLM-compatible format.
    
    Args:
        recent_messages: List of {"role": "user"|"assistant", "content": "..."} dicts
        
    Returns:
        Same format, validated and cleaned
    """
    formatted = []
    for msg in recent_messages:
        if "role" in msg and "content" in msg:
            formatted.append({
                "role": msg["role"],
                "content": str(msg["content"]).strip()
            })
    return formatted
