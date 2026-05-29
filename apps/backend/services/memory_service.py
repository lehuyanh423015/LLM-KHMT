"""
Memory Service - Customer Memory Extraction and Update.

Developer B owns the extraction rules behind this stable interface:
    extract_and_update_customer_memory(session_id, user_message, assistant_response, db)

The orchestrator depends only on that interface. Keep this file independent from
routes and LLM provider code so Knowledge + Memory work can evolve safely.
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
    "laptop": [
        "laptop",
        "may tinh",
        "may tinh xach tay",
        "notebook",
        "macbook",
        "adobe",
        "premiere",
        "photoshop",
        "do hoa",
        "render",
        "lap trinh",
        "van phong",
        "tac vu nang",
    ],
    "phone": ["dien thoai", "dien thoat", "smartphone", "phone", "mobile", "iphone", "dt"],
    "tablet": ["may tinh bang", "tablet", "ipad"],
    "mouse": ["chuot", "mouse"],
    "keyboard": ["ban phim", "keyboard"],
    "monitor": ["man hinh", "monitor"],
    "headphones": ["tai nghe", "headphone", "headphones", "earbud", "earbuds"],
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
    "creator": ["adobe", "premiere", "photoshop", "do hoa", "render", "edit video"],
    "office": ["van phong", "office", "hoc tap", "sinh vien"],
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
    """Stable interface called by the chat orchestrator after each user turn."""

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

    if category_changed:
        profile.preferred_color = None
        profile.priorities = None
        profile.dislikes = None
        if _is_cross_domain_change(old_category, new_category):
            profile.budget = None

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
    if _looks_like_phone_query(normalized):
        return "phone"

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
    return re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", normalized) is not None


def _looks_like_phone_query(normalized: str) -> bool:
    if any(term in normalized for term in ["dien thoai", "dien thoat", "phone", "smartphone", "iphone"]):
        return True

    tokens = re.findall(r"[a-z0-9]+", normalized)
    if "dien" not in tokens:
        return False

    phone_like_tokens = {"thoai", "thoat", "thoa", "dt", "dienthoai"}
    if any(token in phone_like_tokens for token in tokens):
        return True

    return any(_edit_distance_at_most_one(token, "thoai") for token in tokens)


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


def extract_and_update_memory(session_id: str, user_message: str, db: Session):
    """Deprecated: use extract_and_update_customer_memory()."""

    extract_and_update_customer_memory(session_id, user_message, None, db)
