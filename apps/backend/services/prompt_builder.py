"""
Prompt Builder Module

Developer A owns this file. It is the single place where LLM prompt structure
is assembled from stable context contracts.

Developer B should not edit provider code to inject knowledge. They should
return formatted strings from product_retrieval_service.py or retrieval_service.py.
"""

from typing import Any, Dict, List


def build_llm_prompt(
    memory_context: str,
    product_context: str,
    recent_messages: List[Dict[str, str]],
    current_message: str,
) -> Dict[str, Any]:
    """
    Build provider-neutral LLM input in a fixed order:
    1. system prompt
    2. customer memory context
    3. product knowledge context
    4. recent conversation history
    5. current user message
    """
    return {
        "system": _build_system_prompt(memory_context, product_context),
        "conversation_history": format_recent_messages_for_llm(recent_messages),
        "current_message": current_message,
    }


def _build_system_prompt(memory_context: str, product_context: str) -> str:
    """Build concise shopping-assistant instructions plus optional contexts."""
    prompt = (
        "You are a focused shopping assistant for customer support and product advice.\n"
        "Reply in natural Vietnamese with full diacritics. Do not write Vietnamese without accents.\n"
        "Keep answers concise, practical, and easy to compare.\n"
        "Use customer memory when it is provided. Use product knowledge only when it is provided.\n"
        "Do not invent exact prices, stock status, URLs, colors, versions, or product facts that are not in context.\n"
        "Do not discuss camera, color, or accessories unless the user asks or product context includes them.\n"
        "If no product knowledge is available, say the recommendation is general and explain what should be verified.\n"
        "Respect the customer's stated budget, dislikes, and priorities.\n"
        "If product context includes a preferred price range, prioritize products inside that range.\n"
        "Only mention much cheaper products as budget-saving alternatives, not as the main recommendations.\n"
        "Ask at most one follow-up question when required to make a useful recommendation.\n"
        "Stay focused on shopping, recommendation, comparison, and customer support tasks.\n\n"
    )

    if memory_context.strip():
        prompt += f"CUSTOMER MEMORY:\n{memory_context}\n\n"

    if product_context.strip():
        prompt += f"PRODUCT KNOWLEDGE CONTEXT:\n{product_context}\n\n"

    if "GROUNDED PRODUCT DRAFT FROM RETRIEVAL" in product_context:
        prompt += (
            "Grounded rewrite mode:\n"
            "- Treat the grounded draft as factual notes, not as final wording.\n"
            "- Write naturally in Vietnamese with full diacritics.\n"
            "- For comparisons, make an actual judgment: which product fits which user, where each wins, and the final recommendation.\n"
            "- For one named product, focus only on that product unless the user explicitly asks for alternatives.\n"
            "- Do not introduce products, specs, prices, links, or claims that are absent from the context.\n\n"
        )

    if "GROUNDED PRODUCT DRAFT FROM RETRIEVAL" in product_context:
        prompt += (
            "Response style:\n"
            "- Keep the answer compact but complete.\n"
            "- Start with the conclusion, then explain the most important reasons.\n"
            "- Use short paragraphs or bullets only when they improve readability.\n"
            "- End with what the user should verify before buying.\n"
        )
    else:
        prompt += (
            "Response style:\n"
            "- Keep the answer under 180 Vietnamese words unless the user asks for more.\n"
            "- Start with the most useful answer first.\n"
            "- If product context contains candidates, recommend 3 to 4 concrete options from that context only.\n"
            "- For each option, use this format: name - price range - fit reason - trade-off - verify price/warranty/stock.\n"
            "- Explain why each suggestion fits the customer.\n"
            "- Separate confirmed context from general advice.\n"
        )
    return prompt


def format_recent_messages_for_llm(
    recent_messages: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """Validate recent messages into the shared role/content contract."""
    formatted = []
    for msg in recent_messages or []:
        role = msg.get("role")
        content = msg.get("content")
        if role in {"user", "assistant"} and content:
            formatted.append({"role": role, "content": str(content).strip()})
    return formatted
