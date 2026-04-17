"""
Retrieves data from the DB to be injected back into the LLM logic layer.
"""

from sqlalchemy.orm import Session
from models.database_models import CustomerProfile

def get_customer_context(session_id: str, db: Session) -> str:
    """
    Returns a formatted string of the customer's known constraints 
    to be appended to the LLM system prompt.
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
        
    return "THÔNG TIN KHÁCH HÀNG (Bộ nhớ):\n- " + "\n- ".join(context_lines)
