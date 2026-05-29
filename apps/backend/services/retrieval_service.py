"""
Retrieval Service - Customer Memory Retrieval.

Stable interface used by the orchestrator:
    get_customer_memory_context(session_id: str, db) -> str
"""

from sqlalchemy.orm import Session

from models.database_models import CustomerProfile
from services.data_normalization import repair_mojibake


def get_customer_memory_context(session_id: str, db: Session) -> str:
    """
    Return a compact, formatted customer profile for prompt injection.

    Empty string is a valid return value when no profile exists or no useful
    fields have been learned yet.
    """

    profile = db.query(CustomerProfile).filter(
        CustomerProfile.session_id == session_id
    ).first()

    if not profile:
        return ""

    fields = [
        ("Ten khach hang", getattr(profile, "name", None)),
        ("Ngan sach", getattr(profile, "budget", None)),
        ("San pham dang tim", getattr(profile, "preferred_category", None)),
        ("Mau sac yeu thich", getattr(profile, "preferred_color", None)),
        ("Uu tien", getattr(profile, "priorities", None)),
        ("Khong thich/Can tranh", getattr(profile, "dislikes", None)),
    ]

    context_lines = []
    for label, value in fields:
        cleaned = repair_mojibake(value).strip()
        if cleaned:
            context_lines.append(f"{label}: {cleaned}")

    if not context_lines:
        return ""

    return "- " + "\n- ".join(context_lines)


def get_customer_context(session_id: str, db: Session) -> str:
    """Deprecated: use get_customer_memory_context()."""

    context = get_customer_memory_context(session_id, db)
    if context:
        return "THONG TIN KHACH HANG (Bo nho):\n" + context
    return ""
