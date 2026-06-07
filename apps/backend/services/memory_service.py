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
    tokenize,
    unique_preserve_order,
)
from services.query_understanding_service import is_small_talk_message, understand_query


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
    "max_performance": [
        "sieu manh",
        "manh me",
        "manh nhat",
        "cau hinh sieu manh",
        "khong quan tam gia",
        "khong gioi han ngan sach",
        "tat ca game nang",
        "game nang hien tai",
    ],
    "display": ["man hinh", "display", "oled", "amoled", "tan so quet"],
    "storage": ["bo nho", "luu tru", "ssd", "storage", "rom"],
    "ram": ["ram", "da nhiem", "multitask", "nhieu ung dung"],
    "cooling": ["tan nhiet", "mat may", "khong nong", "cooling"],
    "lightweight": ["mong nhe", "nhe", "mong", "gon", "lightweight"],
    "durable": ["ben", "chac", "durable"],
    "build_quality": ["build", "vo kim loai", "hoan thien", "chat lieu", "cao cap"],
    "warranty": ["bao hanh", "chinh hang", "hau mai", "bao tri"],
    "software": ["phan mem", "cap nhat", "on dinh", "he sinh thai"],
    "keyboard": ["ban phim", "keyboard", "go phim", "typing"],
    "value": ["gia re", "re", "hop ly", "value", "cheap", "gia thanh", "cau hinh", "p/p"],
    "china_brand": ["hang trung quoc", "trung quoc", "hang tq", "china brand", "hang china"],
    "design": ["thiet ke", "dep", "design"],
    "creator": ["adobe", "premiere", "photoshop", "do hoa", "render", "edit video"],
    "office": ["van phong", "office", "hoc tap", "sinh vien"],
    "coding": ["lap trinh", "code", "dev", "developer", "ide"],
    "ai_work": ["ai", "machine learning", "deep learning", "llm", "cuda"],
    "upgradeable": ["nang cap", "them ram", "them ssd", "upgrade"],
    "compact": ["nho gon", "compact", "de cam", "de mang"],
    "premium": ["flagship", "cao cap", "premium"],
    "android": ["android"],
    "ios": ["ios", "iphone"],
    "windows": ["windows"],
    "macos": ["macos", "macbook"],
}

BRAND_ALIASES = {
    "apple": ["apple", "iphone", "macbook", "ipad"],
    "samsung": ["samsung", "galaxy"],
    "xiaomi": ["xiaomi", "redmi", "poco"],
    "oppo": ["oppo"],
    "vivo": ["vivo", "iqoo"],
    "realme": ["realme"],
    "oneplus": ["oneplus"],
    "lenovo": ["lenovo", "thinkpad", "loq", "legion", "ideapad"],
    "asus": ["asus", "vivobook", "zenbook", "tuf", "rog"],
    "acer": ["acer", "aspire", "nitro", "predator"],
    "hp": ["hp", "victus", "pavilion", "omen"],
    "dell": ["dell", "inspiron", "xps", "alienware"],
    "msi": ["msi"],
    "lg": ["lg", "gram"],
    "microsoft": ["surface", "microsoft"],
    "google": ["google", "pixel"],
    "nothing": ["nothing"],
    "honor": ["honor"],
}

POSITIVE_PREFERENCE_MARKERS = [
    "thich",
    "uu tien",
    "muon",
    "can",
    "nen",
    "chon",
    "nghieng ve",
    "thien ve",
    "prefer",
]

NEGATED_PRIORITY_MARKERS = [
    "khong can",
    "khong uu tien",
    "khong quan trong",
    "khong qua quan trong",
    "khong choi",
    "khong dung de",
    "khong lien quan den",
    "khong phuc vu",
    "it quan trong",
    "bo qua",
]

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
    "khong tich",
    "ghet",
    "tranh",
    "khong lay",
    "khong can",
    "khong muon",
    "khong dung",
    "khong xai",
    "avoid",
    "hate",
    "dislike",
    "dont want",
    "don't want",
    "no ",
]

DISLIKE_VALUE_ALIASES = {
    "ios": ["ios", "he dieu hanh ios"],
    "apple": ["apple"],
    "iphone": ["iphone"],
    "macbook": ["macbook"],
}

DISLIKE_FILLER_WORDS = {
    "dung",
    "su",
    "su dung",
    "xai",
    "lay",
    "mua",
    "chon",
    "he",
    "he dieu hanh",
    "cua",
    "nha",
    "hang",
    "thuong hieu",
}

FREEFORM_DISLIKE_STOPWORDS = {
    "neu",
    "co",
    "the",
    "thi",
    "nen",
    "uu",
    "tien",
    "cac",
    "cua",
    "nha",
    "hang",
    "thuong",
    "hieu",
}


def extract_and_update_customer_memory(
    session_id: str,
    user_message: str,
    assistant_response: Optional[str],
    db: Session,
) -> None:
    """Stable interface called by the chat orchestrator after each user turn."""

    if not settings.ENABLE_MEMORY or not user_message or is_small_talk_message(user_message):
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

    parsed = understand_query(user_message)
    profile = db.query(CustomerProfile).filter(
        CustomerProfile.session_id == session_id
    ).first()
    if not profile:
        profile = CustomerProfile(session_id=session_id)
        db.add(profile)

    old_category = normalize_text(getattr(profile, "preferred_category", None))
    new_category = parsed.get("category") or _extract_category(normalized)
    category_changed = bool(old_category and new_category and old_category != new_category)

    if category_changed:
        profile.preferred_color = None
        profile.priorities = None
        profile.dislikes = None
        if _is_cross_domain_change(old_category, new_category):
            profile.budget = None

    if _has_unlimited_budget_signal(user_message):
        profile.budget = "khong gioi han"
    else:
        budget_text = _extract_budget_text(user_message) or (parsed.get("budget") or {}).get("raw")
        if budget_text:
            profile.budget = budget_text
        elif _has_budget_signal(user_message) and parse_budget_to_vnd(user_message) is not None:
            profile.budget = repair_mojibake(user_message).strip()

    if new_category:
        profile.preferred_category = new_category

    color = _extract_color(normalized)
    if color and not category_changed:
        profile.preferred_color = color

    priorities = _extract_priorities(normalized)
    priorities.extend(_extract_preferred_brands(normalized))
    priorities.extend(parsed.get("priorities", []))
    priorities.extend(parsed.get("preferred_brands", []))
    priorities.extend(parsed.get("preferred_os", []))
    if priorities:
        profile.priorities = _merge_csv(profile.priorities, priorities)

    dislikes = _extract_dislikes(normalized)
    dislikes.extend(parsed.get("dislikes", []))
    dislikes.extend(parsed.get("disliked_brands", []))
    dislikes.extend(parsed.get("disliked_os", []))
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
        r"(million|trieu|tr|k|nghin|ngan|m|vnd|usd)(?![a-z0-9])",
        normalized,
    )
    return _format_budget_text_for_memory(match.group(0).strip()) if match else None


def _format_budget_text_for_memory(text: str) -> str:
    return (
        text.replace("million", "trieu")
        .replace(" m", " trieu")
        .replace("ngan", "k")
        .strip()
    )


def _has_budget_signal(text: str) -> bool:
    normalized = normalize_text(text)
    signals = ["trieu", "tr", "vnd", "ngan", "nghin", "budget", "ngan sach", "tam gia", "gia"]
    return any(_contains_alias(normalized, signal) for signal in signals)


def _has_unlimited_budget_signal(text: object) -> bool:
    normalized = normalize_text(text)
    signals = [
        "khong quan tam gia",
        "khong quan tam ve gia",
        "khong can quan tam ve gia",
        "khong can quan tam gia",
        "khong gioi han ngan sach",
        "khong gioi han gia",
        "bat ke gia",
        "gia nao cung duoc",
        "khong can biet gia",
        "khong lo ve gia",
        "no budget limit",
        "unlimited budget",
    ]
    return any(_contains_alias(normalized, signal) for signal in signals)


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


def _extract_preferred_brands(normalized: str) -> list[str]:
    if not any(marker in normalized for marker in POSITIVE_PREFERENCE_MARKERS):
        return []

    brands = []
    for canonical, aliases in BRAND_ALIASES.items():
        if any(_contains_alias(normalized, alias) for alias in aliases):
            brands.append(f"brand:{canonical}")
    return brands


def _extract_dislikes(normalized: str) -> list[str]:
    if not any(marker in normalized for marker in DISLIKE_MARKERS):
        return []

    disliked = []
    for canonical, aliases in DISLIKE_VALUE_ALIASES.items():
        if any(_contains_alias(normalized, alias) for alias in aliases):
            disliked.append(canonical)

    disliked.extend(_extract_negated_priorities(normalized))
    disliked.extend(_extract_disliked_brands(normalized))
    disliked.extend(_extract_freeform_dislike_terms(normalized))

    return unique_preserve_order(disliked)


def _extract_negated_priorities(normalized: str) -> list[str]:
    if not any(marker in normalized for marker in NEGATED_PRIORITY_MARKERS):
        return []

    dislikes = []
    pattern = (
        r"(?:khong can|khong uu tien|khong quan trong|khong qua quan trong|it quan trong|bo qua)"
        r"\s+((?:[a-z0-9]+\s*){1,5})"
    )
    for match in re.finditer(pattern, normalized):
        phrase = match.group(1).strip()
        for canonical, aliases in PRIORITY_ALIASES.items():
            if any(_contains_alias(phrase, alias) for alias in aliases):
                dislikes.append(canonical)
    return dislikes


def _extract_disliked_brands(normalized: str) -> list[str]:
    if not any(marker in normalized for marker in DISLIKE_MARKERS + NEGATED_PRIORITY_MARKERS):
        return []

    dislikes = []
    pattern = (
        r"(?:khong thich|khong tich|ghet|tranh|khong muon|khong dung|khong xai|khong can|"
        r"khong uu tien|khong quan trong|khong qua quan trong|it quan trong|bo qua|"
        r"avoid|hate|dislike|no)"
        r"\s+((?:[a-z0-9]+\s*){1,5})"
    )
    for match in re.finditer(pattern, normalized):
        phrase = match.group(1).strip()
        for canonical, aliases in BRAND_ALIASES.items():
            if any(_contains_alias(phrase, alias) for alias in aliases):
                dislikes.append(f"brand:{canonical}")
    return dislikes


def _extract_freeform_dislike_terms(normalized: str) -> list[str]:
    terms: list[str] = []
    pattern = (
        r"(?:khong thich|khong tich|ghet|tranh|khong muon|khong dung|khong xai|avoid|hate|dislike|no)"
        r"\s+((?:[a-z0-9]+\s*){1,4})"
    )
    for match in re.finditer(pattern, normalized):
        phrase = match.group(1).strip()
        for filler in sorted(DISLIKE_FILLER_WORDS, key=len, reverse=True):
            phrase = re.sub(rf"(?<![a-z0-9]){re.escape(filler)}(?![a-z0-9])", " ", phrase)
        phrase = re.sub(r"\s+", " ", phrase).strip()
        for token in tokenize(phrase):
            if token in FREEFORM_DISLIKE_STOPWORDS:
                continue
            canonical = _canonical_memory_token(token)
            if canonical:
                terms.append(canonical)
    return terms


def _canonical_memory_token(token: str) -> Optional[str]:
    for priority, aliases in PRIORITY_ALIASES.items():
        if token == priority or token in aliases:
            return priority
    for brand, aliases in BRAND_ALIASES.items():
        if token == brand or token in aliases:
            return f"brand:{brand}"
    return token if token not in DISLIKE_FILLER_WORDS else None


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
