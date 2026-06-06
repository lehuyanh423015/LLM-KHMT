"""
Retrieval Service - Customer Memory Retrieval.

Stable interface used by the orchestrator:
    get_customer_memory_context(session_id: str, db) -> str
"""

from sqlalchemy.orm import Session

from models.database_models import CustomerProfile
from services.data_normalization import repair_mojibake


MEMORY_LABELS = {
    "gaming": "chơi game",
    "battery": "pin",
    "camera": "camera/chụp ảnh",
    "performance": "hiệu năng",
    "display": "màn hình",
    "storage": "lưu trữ",
    "ram": "RAM/đa nhiệm",
    "cooling": "tản nhiệt",
    "lightweight": "mỏng nhẹ",
    "durable": "độ bền",
    "build_quality": "chất lượng hoàn thiện",
    "warranty": "bảo hành/chính hãng",
    "software": "phần mềm/cập nhật",
    "value": "giá/cấu hình",
    "china_brand": "ưu tiên hãng Trung Quốc",
    "design": "thiết kế",
    "creator": "đồ họa/Adobe/render",
    "office": "văn phòng/học tập",
    "coding": "lập trình",
    "ai_work": "AI/machine learning",
    "upgradeable": "khả năng nâng cấp",
    "compact": "nhỏ gọn",
    "premium": "cao cấp",
    "android": "Android",
    "ios": "iOS",
    "windows": "Windows",
    "macos": "macOS",
}


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
        ("Tên khách hàng", getattr(profile, "name", None)),
        ("Ngân sách", getattr(profile, "budget", None)),
        ("Sản phẩm đang tìm", getattr(profile, "preferred_category", None)),
        ("Màu sắc yêu thích", getattr(profile, "preferred_color", None)),
        ("Ưu tiên", format_memory_csv(getattr(profile, "priorities", None))),
        ("Không thích/Cần tránh", format_memory_csv(getattr(profile, "dislikes", None))),
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
        return "THÔNG TIN KHÁCH HÀNG (Bộ nhớ):\n" + context
    return ""


def format_memory_csv(value: object) -> str:
    raw = repair_mojibake(value).strip()
    if not raw:
        return ""

    formatted = []
    seen = set()
    for item in [part.strip() for part in raw.split(",") if part.strip()]:
        if item.startswith("brand:"):
            label = "hãng " + item.split(":", 1)[1].title()
        elif item.startswith("os:"):
            label = item.split(":", 1)[1].upper()
        else:
            label = MEMORY_LABELS.get(item, item)
        normalized_label = label.lower()
        if normalized_label in seen:
            continue
        if normalized_label == "apple" and "hãng apple" in seen:
            continue
        if normalized_label == "hãng apple" and "apple" in seen:
            formatted = [value for value in formatted if value.lower() != "apple"]
            seen.discard("apple")
        seen.add(normalized_label)
        formatted.append(label)
    return ", ".join(formatted)


def _format_memory_csv(value: object) -> str:
    """Backward-compatible alias."""

    return format_memory_csv(value)
