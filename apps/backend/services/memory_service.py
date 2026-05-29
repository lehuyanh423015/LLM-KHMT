"""
Memory Service - Customer Memory Extraction and Update

Developer B owns the internals of this file. The stable interface is:

extract_and_update_customer_memory(
    session_id: str,
    user_message: str,
    assistant_response: str | None,
    db: Session
) -> None

This implementation is intentionally lightweight and rule-based. It normalizes
Vietnamese accents and handles common typos such as "dien thoat" for
"dien thoai" so memory does not keep the wrong product category.
"""

import re
import unicodedata
from typing import Optional

from sqlalchemy.orm import Session

from models.database_models import CustomerProfile


def extract_and_update_customer_memory(
    session_id: str,
    user_message: str,
    assistant_response: Optional[str],
    db: Session,
) -> None:
    """Stable interface called by the chat orchestrator after each turn."""
    from core.config import settings

    if not settings.ENABLE_MEMORY:
        return

    _extract_preferences_and_update_profile(session_id, user_message, db)


def _extract_preferences_and_update_profile(
    session_id: str,
    user_message: str,
    db: Session,
) -> None:
    normalized_msg = _normalize_text(user_message)

    profile = db.query(CustomerProfile).filter(CustomerProfile.session_id == session_id).first()
    if not profile:
        profile = CustomerProfile(session_id=session_id)
        db.add(profile)

    old_category = _normalize_text(profile.preferred_category) if profile.preferred_category else None
    new_category = _detect_category(normalized_msg)

    category_changed = bool(new_category and old_category and new_category != old_category)
    if category_changed:
        profile.preferred_color = None
        profile.priorities = None
        profile.dislikes = None

    budget = _extract_budget(normalized_msg)
    if budget:
        profile.budget = budget

    if new_category:
        profile.preferred_category = new_category

    color = _extract_color(normalized_msg)
    if color and not category_changed:
        profile.preferred_color = color

    priority = _extract_priority(normalized_msg)
    if priority:
        profile.priorities = _append_unique(profile.priorities, priority)

    dislike = _extract_dislike(normalized_msg)
    if dislike:
        profile.dislikes = _append_unique(profile.dislikes, dislike)

    if profile.dislikes and profile.priorities:
        dislikes = {item.strip().lower() for item in profile.dislikes.split(",")}
        priorities = [item.strip() for item in profile.priorities.split(",")]
        kept_priorities = [item for item in priorities if item.lower() not in dislikes]
        profile.priorities = ", ".join(kept_priorities) if kept_priorities else None

    db.commit()


def _extract_budget(normalized_msg: str) -> Optional[str]:
    match = re.search(
        r"(duoi|khoang|tam|toi da|tu|budget.*?)?\s*"
        r"(\d+[\d\.,\s\-]*\d*)\s*"
        r"(trieu|tr|k|usd|vnd|million|m)",
        normalized_msg,
    )
    if not match:
        return None

    prefix = match.group(1) or ""
    amount = match.group(2).strip()
    unit = match.group(3).strip()
    return f"{prefix} {amount} {unit}".strip()


def _detect_category(normalized_msg: str) -> Optional[str]:
    if "laptop" in normalized_msg or "notebook" in normalized_msg:
        return "laptop"
    if _looks_like_laptop_work_query(normalized_msg):
        return "laptop"
    if _looks_like_phone_query(normalized_msg):
        return "phone"
    if "tablet" in normalized_msg or "may tinh bang" in normalized_msg:
        return "tablet"
    if "sach" in normalized_msg or "truyen" in normalized_msg or "book" in normalized_msg:
        return "book"
    if "tai nghe" in normalized_msg:
        return "headphone"
    return None


def _extract_color(normalized_msg: str) -> Optional[str]:
    match = re.search(
        r"(mau\s+)?(den|trang|do|xanh duong|xanh la|xanh|xam|bac|vang|hong|"
        r"black|white|red|blue|green|gray|grey|silver|gold|pink)",
        normalized_msg,
    )
    return match.group(2).strip() if match else None


def _extract_priority(normalized_msg: str) -> Optional[str]:
    priorities = [
        ("adobe", "adobe/creator"),
        ("premiere", "video editing"),
        ("photoshop", "photo editing"),
        ("tac vu nang", "tac vu nang"),
        ("do hoa", "do hoa"),
        ("van phong", "van phong"),
        ("hieu nang", "hieu nang"),
        ("choi game", "choi game"),
        ("gaming", "gaming"),
        ("pin trau", "pin trau"),
        ("battery", "battery"),
        ("gia re", "gia re"),
        ("mong nhe", "mong nhe"),
        ("nhe", "nhe"),
        ("ben", "ben"),
        ("camera", "camera"),
        ("muot", "muot"),
        ("performance", "performance"),
        ("lightweight", "lightweight"),
        ("durable", "durable"),
    ]
    for keyword, label in priorities:
        if keyword in normalized_msg:
            return label
    return None


def _extract_dislike(normalized_msg: str) -> Optional[str]:
    if not any(term in normalized_msg for term in ["khong thich", "ghet", "tranh", "khong lay", "khong can", "avoid", "hate", "dislike"]):
        return None

    dislike_targets = ["nang", "apple", "samsung", "xiaomi", "dat", "gaming", "on", "cu", "heavy", "expensive"]
    for target in dislike_targets:
        if target in normalized_msg:
            return target
    return None


def _append_unique(current: Optional[str], value: str) -> str:
    if not current:
        return value

    items = [item.strip() for item in current.split(",") if item.strip()]
    if value.lower() not in {item.lower() for item in items}:
        items.append(value)
    return ", ".join(items)


def _looks_like_phone_query(normalized_msg: str) -> bool:
    if any(term in normalized_msg for term in ["dien thoai", "phone", "smartphone"]):
        return True

    tokens = re.findall(r"[a-z0-9]+", normalized_msg)
    if "dien" not in tokens:
        return False

    phone_like_tokens = {"thoai", "thoat", "thoa", "dt", "dienthoai"}
    if any(token in phone_like_tokens for token in tokens):
        return True

    return any(_edit_distance_at_most_one(token, "thoai") for token in tokens)


def _looks_like_laptop_work_query(normalized_msg: str) -> bool:
    work_terms = [
        "van phong", "adobe", "premiere", "photoshop", "do hoa",
        "edit video", "render", "tac vu nang", "lap trinh", "may tinh",
    ]
    if any(term in normalized_msg for term in work_terms):
        return True

    tokens = set(re.findall(r"[a-z0-9]+", normalized_msg))
    return "may" in tokens and bool(tokens & {"adobe", "premiere", "photoshop", "render"})


def _edit_distance_at_most_one(value: str, target: str) -> bool:
    if value == target:
        return True
    if abs(len(value) - len(target)) > 1:
        return False

    i = j = edits = 0
    while i < len(value) and j < len(target):
        if value[i] == target[j]:
            i += 1
            j += 1
            continue
        edits += 1
        if edits > 1:
            return False
        if len(value) > len(target):
            i += 1
        elif len(value) < len(target):
            j += 1
        else:
            i += 1
            j += 1
    return True


def _normalize_text(value: str) -> str:
    text = value.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


def extract_and_update_memory(session_id: str, user_message: str, db: Session):
    """Deprecated: use extract_and_update_customer_memory()."""
    extract_and_update_customer_memory(session_id, user_message, None, db)
