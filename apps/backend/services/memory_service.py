"""
Memory Service - Customer Memory Extraction and Update.

Stable interface used by the orchestrator:
    extract_and_update_customer_memory(session_id, user_message, assistant_response, db)
"""

from __future__ import annotations

import re
from typing import Optional

from sqlalchemy.orm import Session

from core.config import settings
from models.database_models import CustomerProfile
from services.data_normalization import (
    normalize_text,
    parse_budget_to_vnd,
    repair_mojibake,
    unique_preserve_order,
)


CATEGORY_ALIASES = {
    "laptop": ["laptop", "may tinh", "notebook"],
    "phone": ["dien thoai", "smartphone", "phone"],
    "tablet": ["may tinh bang", "tablet", "ipad"],
    "mouse": ["chuot", "mouse"],
    "keyboard": ["ban phim", "keyboard"],
    "monitor": ["man hinh", "monitor"],
    "headphones": ["tai nghe", "headphone", "headphones"],
    "book": ["sach giay", "sach dien tu", "truyen", "novel", "ebook", "book"],
}

PRIORITY_ALIASES = {
    "gaming": ["gaming", "choi game", "game", "chien game"],
    "battery": ["pin trau", "pin lau", "pin", "battery"],
    "camera": ["camera", "chup anh", "chup hinh"],
    "performance": ["hieu nang", "manh", "nhanh", "muot", "performance"],
    "lightweight": ["mong nhe", "nhe", "mong", "gon", "lightweight"],
    "durable": ["ben", "chac", "durable"],
    "value": ["gia re", "re", "hop ly", "value", "cheap"],
    "design": ["thiet ke", "dep", "design"],
}

COLOR_ALIASES = {
    "den": ["den", "black"],
    "trang": ["trang", "white"],
    "do": ["do", "red"],
    "xanh": ["xanh duong", "xanh la", "xanh", "blue", "green"],
    "xam": ["xam", "gray", "grey"],
    "bac": ["bac", "silver"],
    "vang": ["vang", "gold"],
    "hong": ["hong", "pink"],
}

DISLIKE_MARKERS = [
    "khong thich",
    "ghet",
    "tranh",
    "khong lay",
    "khong can",
    "avoid",
    "hate",
    "dislike",
    "dont want",
    "don't want",
    "no ",
]


def extract_and_update_customer_memory(
    session_id: str,
    user_message: str,
    assistant_response: Optional[str],
    db: Session,
) -> None:
    """Extract customer preferences from the user turn and update the profile."""

    if not settings.ENABLE_MEMORY or not user_message:
        return

    _extract_preferences_and_update_profile(session_id, user_message, db)


def _extract_preferences_and_update_profile(
    session_id: str,
    user_message: str,
    db: Session,
) -> None:
    normalized = normalize_text(user_message)
    if not normalized:
        return

    profile = db.query(CustomerProfile).filter(
        CustomerProfile.session_id == session_id
    ).first()
    if not profile:
        profile = CustomerProfile(session_id=session_id)
        db.add(profile)

    old_category = normalize_text(getattr(profile, "preferred_category", None))
    new_category = _extract_category(normalized)
    category_changed = bool(old_category and new_category and old_category != new_category)

    if category_changed and _is_cross_domain_change(old_category, new_category):
        profile.budget = None
        profile.preferred_color = None
        profile.priorities = None
        profile.dislikes = None

    budget_text = _extract_budget_text(user_message)
    if budget_text:
        profile.budget = budget_text
    elif parse_budget_to_vnd(user_message) is not None:
        profile.budget = repair_mojibake(user_message).strip()

    if new_category:
        profile.preferred_category = new_category

    color = _extract_color(normalized)
    if color and not category_changed:
        profile.preferred_color = color

    priorities = _extract_priorities(normalized)
    if priorities:
        profile.priorities = _merge_csv(profile.priorities, priorities)

    dislikes = _extract_dislikes(normalized)
    if dislikes:
        profile.dislikes = _merge_csv(profile.dislikes, dislikes)
        profile.priorities = _remove_csv_items(profile.priorities, dislikes)

    db.commit()


def _extract_budget_text(text: str) -> Optional[str]:
    repaired = repair_mojibake(text)
    normalized = normalize_text(repaired)
    match = re.search(
        r"(duoi|tren|khoang|tam|toi da|toi thieu|tu|budget)?\s*"
        r"\d+(?:[.,]\d+)?(?:\s*-\s*\d+(?:[.,]\d+)?)?\s*"
        r"(trieu|tr|k|nghin|ngan|m|million|vnd|usd)",
        normalized,
    )
    return match.group(0).strip() if match else None


def _extract_category(normalized: str) -> Optional[str]:
    for canonical, aliases in CATEGORY_ALIASES.items():
        if any(_contains_alias(normalized, alias) for alias in aliases):
            return canonical
    return None


def _extract_color(normalized: str) -> Optional[str]:
    for canonical, aliases in COLOR_ALIASES.items():
        if any(_contains_alias(normalized, alias) for alias in aliases):
            return canonical
    return None


def _extract_priorities(normalized: str) -> list[str]:
    priorities = []
    for canonical, aliases in PRIORITY_ALIASES.items():
        if any(_contains_alias(normalized, alias) for alias in aliases):
            priorities.append(canonical)
    return priorities


def _extract_dislikes(normalized: str) -> list[str]:
    if not any(marker in normalized for marker in DISLIKE_MARKERS):
        return []

    disliked = []
    for category, aliases in CATEGORY_ALIASES.items():
        if any(_contains_alias(normalized, alias) for alias in aliases):
            disliked.append(category)
    for priority, aliases in PRIORITY_ALIASES.items():
        if any(_contains_alias(normalized, alias) for alias in aliases):
            disliked.append(priority)

    brand_match = re.search(
        r"(?:khong thich|ghet|tranh|avoid|hate|dislike|no)\s+([a-z0-9]+)",
        normalized,
    )
    if brand_match:
        disliked.append(brand_match.group(1))

    return unique_preserve_order(disliked)


def _merge_csv(existing: Optional[str], new_values: list[str]) -> str:
    current = [item.strip() for item in repair_mojibake(existing).split(",") if item.strip()]
    return ", ".join(unique_preserve_order(current + new_values))


def _remove_csv_items(existing: Optional[str], remove_values: list[str]) -> Optional[str]:
    current = [item.strip() for item in repair_mojibake(existing).split(",") if item.strip()]
    remove_set = {normalize_text(item) for item in remove_values}
    kept = [item for item in current if normalize_text(item) not in remove_set]
    return ", ".join(kept) if kept else None


def _is_cross_domain_change(old_category: str, new_category: str) -> bool:
    electronics = {"laptop", "phone", "tablet", "mouse", "keyboard", "monitor", "headphones"}
    books = {"book"}
    return (
        old_category in electronics
        and new_category in books
        or old_category in books
        and new_category in electronics
    )


def _contains_alias(normalized: str, alias: str) -> bool:
    """Match a normalized alias as a whole token/phrase, not as a substring."""

    return re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", normalized) is not None


def extract_and_update_memory(session_id: str, user_message: str, db: Session):
    """Deprecated: use extract_and_update_customer_memory()."""

    extract_and_update_customer_memory(session_id, user_message, None, db)
