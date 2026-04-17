"""
Memory Service using rule-based/heuristic logic to extract customer shopping preferences.
"""

import re
from sqlalchemy.orm import Session
from models.database_models import CustomerProfile

def extract_and_update_memory(session_id: str, user_message: str, db: Session):
    """
    Parses user message with heuristics to find preferences,
    and upserts into the CustomerProfile table.
    """
    from core.config import settings
    if not settings.ENABLE_MEMORY:
        return
        
    normalized_msg = user_message.lower()
    
    # Improved Heuristics Patterns (Vietnamese + English support)
    # Extracts explicit numbers, including ranges (e.g., 10-15 triệu)
    budget_pattern = re.search(r'(dưới|khoảng|tầm|tối đa|từ|budget.*?)?\s*(\d+[\d\.,\s\-]*\d*)\s*(triệu|tr|k|usd|vnd|million|m)', normalized_msg)
    category_pattern = re.search(r'(laptop|điện thoại|phone|máy tính bảng|tablet|pc|chuột|mouse|bàn phím|keyboard|màn hình|kính|tai nghe)', normalized_msg)
    color_pattern = re.search(r'(màu\s+)?(đen|trắng|đỏ|xanh dương|xanh lá|xanh|xám|bạc|vàng|hồng|black|white|red|blue|green|gray|grey|silver|gold|pink)', normalized_msg)
    priority_pattern = re.search(r'(hiệu năng|pin trâu|gaming|chơi game|giá rẻ|kết cấu|mỏng nhẹ|nhẹ|thiết kế|bền|camera|chụp hình|chụp ảnh|mượt|performance|battery|value|cheap|lightweight|design|durable)', normalized_msg)
    dislike_pattern = re.search(r'(không thích|ghét|tránh|không lấy|chê|không cần|don\'t want|hate|dislike|avoid|no.*?)\s+(nặng|apple|samsung|đắt|gaming|ồn|cũ|heavy|expensive)', normalized_msg)
    
    # Find existing or create new profile
    profile = db.query(CustomerProfile).filter(CustomerProfile.session_id == session_id).first()
    if not profile:
        profile = CustomerProfile(session_id=session_id)
        db.add(profile)
    
    # Update fields with absolute overwrites where appropriate to reflect newest constraints
    if budget_pattern:
        prefix = budget_pattern.group(1) or ""
        amount = budget_pattern.group(2).strip()
        unit = budget_pattern.group(3).strip()
        profile.budget = f"{prefix} {amount} {unit}".strip()
        
    if category_pattern:
        profile.preferred_category = category_pattern.group(1).strip()
        
    if color_pattern:
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
