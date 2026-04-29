"""
Retrieval Service - Customer Memory Retrieval

=== MEMORY LAYER (Developer B) ===

This module retrieves customer memory/profile data from the database.

STABLE INTERFACE:
    get_customer_memory_context(session_id: str, db) -> str

The orchestrator calls this function to load customer memory context.
Developer B can extend this by adding more fields to CustomerProfile table
and retrieving them here - no changes needed in orchestrator.

Current Implementation: Retrieves basic profile fields (budget, preferences)
Future Enhancement: Vector search over customer history, behavioral patterns, etc.
"""

from sqlalchemy.orm import Session
from models.database_models import CustomerProfile


def get_customer_memory_context(session_id: str, db: Session) -> str:
    """
    STABLE INTERFACE FOR DEVELOPER B
    
    Retrieves customer memory/profile as a formatted string.
    Used by orchestrator to inject customer context into LLM prompt.
    
    Args:
        session_id: Unique customer session ID
        db: SQLAlchemy database session
        
    Returns:
        Formatted string with customer profile info
        Empty string if no profile exists
        
    Note: This is the same function as get_customer_context (legacy name)
    but with clear documentation of the stable interface.
    """
    profile = db.query(CustomerProfile).filter(CustomerProfile.session_id == session_id).first()
    
    if not profile:
        return ""
        
    context_lines = []
    if profile.name:
        context_lines.append(f"Tên khách hàng: {profile.name}")
    if profile.budget:
        context_lines.append(f"Ngân sách (Budget): {profile.budget}")
    if profile.preferred_category:
        context_lines.append(f"Sản phẩm đang tìm: {profile.preferred_category}")
    if profile.preferred_color:
        context_lines.append(f"Màu sắc yêu thích: {profile.preferred_color}")
    if profile.priorities:
        context_lines.append(f"Ưu tiên: {profile.priorities}")
    if profile.dislikes:
        context_lines.append(f"Không thích/Cần tránh: {profile.dislikes}")
        
    if not context_lines:
        return ""
        
    return "- " + "\n- ".join(context_lines)


# LEGACY: Keep old function name for backward compatibility
def get_customer_context(session_id: str, db: Session) -> str:
    """
    Deprecated: Use get_customer_memory_context() instead.
    Kept for backward compatibility with existing code.
    """
    context = get_customer_memory_context(session_id, db)
    if context:
        return "THÔNG TIN KHÁCH HÀNG (Bộ nhớ):\n" + context
    return ""
