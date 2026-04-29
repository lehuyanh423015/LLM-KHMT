"""
Memory Service - Customer Memory Extraction and Update

=== MEMORY LAYER (Developer B) ===

This module handles extraction of customer preferences/memory from conversations.

STABLE INTERFACE:
    extract_and_update_customer_memory(
        session_id: str,
        user_message: str, 
        assistant_response: str | None,
        db: Session
    ) -> None

The orchestrator calls this function after each turn.
Developer B can enhance the extraction logic without changing the orchestrator.

Current Implementation: Rule-based/heuristic extraction (Vietnamese + English)
Future Enhancement: ML-based preference extraction, behavioral patterns, etc.
"""

import re
from typing import Optional
from sqlalchemy.orm import Session
from models.database_models import CustomerProfile


def extract_and_update_customer_memory(
    session_id: str,
    user_message: str,
    assistant_response: Optional[str],
    db: Session
) -> None:
    """
    STABLE INTERFACE FOR DEVELOPER B
    
    Extracts customer preferences from user message and updates memory.
    Called asynchronously after each LLM response.
    
    Args:
        session_id: Unique customer session ID
        user_message: The user's input message
        assistant_response: The LLM's response (for context, optional)
        db: SQLAlchemy database session
        
    Returns:
        None (updates database in-place)
        
    Implementation Strategy:
    - Parse user_message for preference signals (budget, category, priorities, dislikes)
    - Update CustomerProfile record in database
    - Handle topic switching (product category changes)
    - Remove conflicting preferences
    
    Future Enhancement Ideas:
    - Use NLP/ML to detect implicit preferences
    - Analyze assistant_response for feedback signals
    - Track preference changes over time
    - Implement preference confidence scoring
    """
    from core.config import settings
    if not settings.ENABLE_MEMORY:
        return
    
    # Delegate to existing implementation
    _extract_preferences_and_update_profile(session_id, user_message, db)


def _extract_preferences_and_update_profile(
    session_id: str,
    user_message: str,
    db: Session
) -> None:
    """
    Internal: Extracts preferences from user message using rule-based heuristics.
    Updates the CustomerProfile record.
    """
    normalized_msg = user_message.lower()
    
    # Improved Heuristics Patterns (Vietnamese + English support)
    # Extracts explicit numbers, including ranges (e.g., 10-15 triệu)
    budget_pattern = re.search(r'(dưới|khoảng|tầm|tối đa|từ|budget.*?)?\s*(\d+[\d\.,\s\-]*\d*)\s*(triệu|tr|k|usd|vnd|million|m)', normalized_msg)
    category_pattern = re.search(r'(laptop|điện thoại|phone|máy tính bảng|tablet|pc|chuột|mouse|bàn phím|keyboard|màn hình|kính|tai nghe|sách|truyện|novel|lightnovel|light novel|ebook|book|sách điện tử)', normalized_msg)
    color_pattern = re.search(r'(màu\s+)?(đen|trắng|đỏ|xanh dương|xanh lá|xanh|xám|bạc|vàng|hồng|black|white|red|blue|green|gray|grey|silver|gold|pink)', normalized_msg)
    priority_pattern = re.search(r'(hiệu năng|pin trâu|gaming|chơi game|giá rẻ|kết cấu|mỏng nhẹ|nhẹ|thiết kế|bền|camera|chụp hình|chụp ảnh|mượt|performance|battery|value|cheap|lightweight|design|durable|hay|tạo tác|tác giả|thể loại|hình ảnh|bìa sách)', normalized_msg)
    dislike_pattern = re.search(r'(không thích|ghét|tránh|không lấy|chê|không cần|don\'t want|hate|dislike|avoid|no.*?)\s+(nặng|apple|samsung|đắt|gaming|ồn|cũ|heavy|expensive)', normalized_msg)
    
    # Find existing or create new profile
    profile = db.query(CustomerProfile).filter(CustomerProfile.session_id == session_id).first()
    if not profile:
        profile = CustomerProfile(session_id=session_id)
        db.add(profile)
    
    # Detect if user has switched to a different category (topic change)
    old_category = profile.preferred_category.lower() if profile.preferred_category else None
    new_category = category_pattern.group(1).strip().lower() if category_pattern else None
    
    # If category changed, clear conflicting old preferences
    category_changed = False
    if new_category and old_category and new_category != old_category:
        # Check if they're from different domains (e.g., electronics to books)
        electronics = {'laptop', 'điện thoại', 'phone', 'máy tính bảng', 'tablet', 'pc', 'chuột', 'mouse', 'bàn phím', 'keyboard', 'màn hình', 'kính', 'tai nghe'}
        books = {'sách', 'truyện', 'novel', 'lightnovel', 'light novel', 'ebook', 'book', 'sách điện tử'}
        
        old_in_electronics = old_category in electronics
        new_in_books = new_category in books
        old_in_books = old_category in books
        new_in_electronics = new_category in electronics
        
        # If switching between different product domains, reset conflicting preferences
        if (old_in_electronics and new_in_books) or (old_in_books and new_in_electronics):
            category_changed = True
            profile.budget = None
            profile.preferred_color = None
            profile.priorities = None
            profile.dislikes = None
    
    # Update fields with absolute overwrites where appropriate to reflect newest constraints
    if budget_pattern:
        prefix = budget_pattern.group(1) or ""
        amount = budget_pattern.group(2).strip()
        unit = budget_pattern.group(3).strip()
        profile.budget = f"{prefix} {amount} {unit}".strip()
        
    if category_pattern:
        profile.preferred_category = category_pattern.group(1).strip()
        
    if color_pattern and not category_changed:
        color = color_pattern.group(2) if color_pattern.group(2) else color_pattern.group(1)
        profile.preferred_color = color.strip()
        
    if priority_pattern:
        new_priority = priority_pattern.group(1).strip()
        if profile.priorities:
            if new_priority not in profile.priorities.lower():
                profile.priorities = profile.priorities + f", {new_priority}"
        else:
            profile.priorities = new_priority
            
    if dislike_pattern:
        nv = dislike_pattern.group(2).strip()
        if profile.dislikes:
            if nv not in profile.dislikes.lower():
                profile.dislikes = profile.dislikes + f", {nv}"
        else:
            profile.dislikes = nv
            
    # Remove overlaps: if something is now explicitly disliked, remove it from priority
    if profile.dislikes and profile.priorities:
        dislikes_list = [d.strip().lower() for d in profile.dislikes.split(",")]
        priorities_list = [p.strip() for p in profile.priorities.split(",")]
        new_priorities = [p for p in priorities_list if p.lower() not in dislikes_list]
        profile.priorities = ", ".join(new_priorities) if new_priorities else None
            
    db.commit()


# LEGACY: Keep old function name for backward compatibility
def extract_and_update_memory(session_id: str, user_message: str, db: Session):
    """
    Deprecated: Use extract_and_update_customer_memory() instead.
    Kept for backward compatibility with existing code.
    """
    extract_and_update_customer_memory(session_id, user_message, None, db)
