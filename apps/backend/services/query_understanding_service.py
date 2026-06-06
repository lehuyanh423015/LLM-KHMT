"""
Lightweight query understanding for shopping conversations.

This is a rule-based NLU layer, not model training. It converts Vietnamese or
English user text into stable signals that retrieval and memory can share.
Developer B can extend the alias tables here without changing chat flow.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from services.data_normalization import normalize_text, parse_budget_to_vnd, unique_preserve_order


CATEGORY_ALIASES = {
    "phone": [
        "dien thoai",
        "dien thoat",
        "smartphone",
        "phone",
        "mobile",
        "iphone",
        "android",
        "dt",
    ],
    "laptop": [
        "laptop",
        "may tinh xach tay",
        "notebook",
        "macbook",
        "may tinh",
        "adobe",
        "premiere",
        "photoshop",
        "do hoa",
        "render",
        "lap trinh",
        "code",
        "dev",
        "van phong",
        "tac vu nang",
    ],
}

PRIORITY_ALIASES = {
    "gaming": ["gaming", "choi game", "game", "chien game"],
    "camera": ["camera", "chup anh", "chup hinh", "quay phim", "video", "selfie"],
    "display": ["man hinh", "display", "oled", "amoled", "tan so quet", "hien thi", "dep"],
    "battery": ["pin", "pin trau", "pin lau", "battery"],
    "performance": ["hieu nang", "manh", "nhanh", "muot", "cau hinh", "chip"],
    "value": ["gia tot", "gia re", "p/p", "ti le gia", "ty le gia", "cau hinh tot", "dang tien"],
    "ram": ["ram", "da nhiem", "multitask", "16gb", "32gb"],
    "storage": ["ssd", "bo nho", "luu tru", "storage", "rom", "1tb", "512gb"],
    "cooling": ["tan nhiet", "mat may", "khong nong", "cooling"],
    "creator": ["adobe", "premiere", "photoshop", "do hoa", "render", "edit video", "chinh anh"],
    "office": ["van phong", "office", "hoc tap", "sinh vien"],
    "coding": ["lap trinh", "code", "dev", "developer", "ide"],
    "ai_work": ["ai", "machine learning", "deep learning", "llm", "cuda"],
    "lightweight": ["nhe", "mong", "mong nhe", "gon", "de mang"],
    "build_quality": ["build", "hoan thien", "chat lieu", "vo kim loai", "ben", "chac"],
    "warranty": ["bao hanh", "chinh hang", "hau mai"],
    "software": ["phan mem", "cap nhat", "on dinh", "he sinh thai"],
    "upgradeable": ["nang cap", "them ram", "them ssd", "upgrade"],
    "premium": ["flagship", "cao cap", "premium"],
    "china_brand": ["hang trung quoc", "hang tq", "trung quoc", "hang china"],
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

POSITIVE_MARKERS = [
    "thich",
    "uu tien",
    "nghieng ve",
    "thien ve",
    "muon",
    "prefer",
]

NEGATIVE_MARKERS = [
    "khong thich",
    "khong tich",
    "khong muon",
    "khong dung",
    "khong xai",
    "khong lay",
    "tranh",
    "ghet",
    "khong can",
    "khong uu tien",
    "avoid",
    "hate",
    "dislike",
    "dont want",
    "don't want",
    "no ",
]

RECOMMENDATION_SIGNALS = ["goi y", "tu van", "nen mua", "mua", "chon", "lua chon", "mau nao"]
COMPARISON_SIGNALS = ["so sanh", "khac gi", "hon", "nen chon cai nao", "mau nao tot hon"]
FOLLOW_UP_SIGNALS = [
    "nhu tren",
    "cac mau tren",
    "lua chon tren",
    "trong so do",
    "vay",
    "con",
    "neu toi",
    "neu khong",
    "thay vao do",
    "mau nao",
    "cai nao",
    "voi nhu cau tren",
    "cung nhu cau",
]


def understand_query(user_message: str) -> Dict:
    """Return stable structured signals extracted from a user message."""

    normalized = normalize_text(user_message)
    budget = extract_budget_constraint(normalized)
    category = _extract_category(normalized)
    priorities = _extract_positive_priorities(normalized)
    dislikes = _extract_negative_priorities(normalized)
    preferred_brands = _extract_brands(normalized, positive=True)
    disliked_brands = _extract_brands(normalized, positive=False)
    preferred_os = _extract_os(normalized, positive=True)
    disliked_os = _extract_os(normalized, positive=False)
    preferred_brands = [brand for brand in preferred_brands if brand not in disliked_brands]
    preferred_os = [os_name for os_name in preferred_os if os_name not in disliked_os]
    intent = _extract_intent(normalized)
    is_follow_up = any(_contains_alias(normalized, signal) for signal in FOLLOW_UP_SIGNALS)

    confidence = 0.15
    for signal in (category, priorities, budget.get("target"), preferred_brands, dislikes, disliked_brands):
        if signal:
            confidence += 0.15
    if intent != "unknown":
        confidence += 0.1

    return {
        "intent": intent,
        "category": category,
        "budget": budget,
        "priorities": unique_preserve_order(priorities),
        "dislikes": unique_preserve_order(dislikes),
        "preferred_brands": unique_preserve_order(preferred_brands),
        "disliked_brands": unique_preserve_order(disliked_brands),
        "preferred_os": unique_preserve_order(preferred_os),
        "disliked_os": unique_preserve_order(disliked_os),
        "is_follow_up": is_follow_up,
        "confidence": min(confidence, 1.0),
    }


def extract_budget_constraint(text: object) -> Dict[str, Optional[float]]:
    normalized = normalize_text(text)
    empty = {"min": None, "target": None, "max": None, "raw": ""}
    if not normalized:
        return empty
    if not _has_budget_signal(normalized):
        return empty

    range_bounds = _extract_explicit_budget_range(normalized)
    if range_bounds:
        lower, upper, raw = range_bounds
        return {"min": lower, "target": (lower + upper) / 2, "max": upper, "raw": raw}

    target = parse_budget_to_vnd(normalized)
    if not target:
        return empty

    margin = _extract_budget_margin(normalized)
    if margin:
        return {
            "min": max(0.0, target - margin),
            "target": target,
            "max": target + margin,
            "raw": _budget_raw(normalized),
        }

    max_value = _extract_flexible_max_budget(normalized, target)
    if max_value and max_value > target:
        lower = target * 0.75 if target >= 10_000_000 else None
        return {"min": lower, "target": target, "max": max_value, "raw": _budget_raw(normalized)}

    max_only_signals = {"duoi", "toi da", "khong qua", "under", "below", "less than"}
    around_signals = {"tam", "khoang", "khoang tam", "gan", "around", "about"}

    if any(signal in normalized for signal in max_only_signals):
        return {"min": None, "target": target, "max": target, "raw": _budget_raw(normalized)}
    if any(signal in normalized for signal in around_signals) or target >= 10_000_000:
        return {"min": target * 0.75, "target": target, "max": target * 1.25, "raw": _budget_raw(normalized)}
    return {"min": None, "target": target, "max": target, "raw": _budget_raw(normalized)}


def _extract_category(normalized: str) -> Optional[str]:
    if not normalized:
        return None
    phone_score = _alias_score(normalized, CATEGORY_ALIASES["phone"])
    laptop_score = _alias_score(normalized, CATEGORY_ALIASES["laptop"])
    if phone_score == laptop_score == 0:
        return None
    return "phone" if phone_score >= laptop_score else "laptop"


def _extract_positive_priorities(normalized: str) -> List[str]:
    priorities: List[str] = []
    negative_spans = _negative_phrases(normalized)
    for canonical, aliases in PRIORITY_ALIASES.items():
        if any(_contains_alias(normalized, alias) for alias in aliases):
            if not any(any(_contains_alias(span, alias) for alias in aliases) for span in negative_spans):
                priorities.append(canonical)
    return priorities


def _extract_negative_priorities(normalized: str) -> List[str]:
    dislikes: List[str] = []
    for span in _negative_phrases(normalized):
        for canonical, aliases in PRIORITY_ALIASES.items():
            if any(_contains_alias(span, alias) for alias in aliases):
                dislikes.append(canonical)
    if any(_contains_alias(normalized, token) for token in ["khong thich ios", "khong dung ios", "tranh ios"]):
        dislikes.extend(["ios"])
    if any(_contains_alias(normalized, token) for token in ["khong thich iphone", "khong dung iphone", "tranh iphone"]):
        dislikes.extend(["ios"])
    if any(_contains_alias(normalized, token) for token in ["khong thich macbook", "khong dung macbook", "tranh macbook"]):
        dislikes.extend(["macos"])
    return dislikes


def _extract_brands(normalized: str, positive: bool) -> List[str]:
    if positive:
        if not any(marker in normalized for marker in POSITIVE_MARKERS):
            return []
        search_space = normalized
    else:
        spans = _negative_phrases(normalized)
        search_space = " ".join(spans)
        if not search_space:
            return []

    brands = []
    for canonical, aliases in BRAND_ALIASES.items():
        if any(_contains_alias(search_space, alias) for alias in aliases):
            brands.append(f"brand:{canonical}")
    return brands


def _extract_os(normalized: str, positive: bool) -> List[str]:
    priorities = _extract_positive_priorities(normalized) if positive else _extract_negative_priorities(normalized)
    return [item for item in priorities if item in {"android", "ios", "windows", "macos"}]


def _extract_intent(normalized: str) -> str:
    if any(_contains_alias(normalized, signal) for signal in COMPARISON_SIGNALS):
        return "comparison"
    if any(_contains_alias(normalized, signal) for signal in RECOMMENDATION_SIGNALS):
        return "recommendation"
    if "?" in normalized or any(signal in normalized for signal in ["co nen", "duoc khong", "phu hop khong"]):
        return "recommendation"
    return "unknown"


def _negative_phrases(normalized: str) -> List[str]:
    spans: List[str] = []
    pattern = (
        r"(?:khong thich|khong tich|khong muon|khong dung|khong xai|khong lay|khong can|khong uu tien|khong|"
        r"tranh|ghet|avoid|hate|dislike|dont want|don't want|no)"
        r"\s+((?:[a-z0-9]+\s*){1,7})"
    )
    for match in re.finditer(pattern, normalized):
        spans.append(match.group(1).strip())
    return spans


def _has_budget_signal(normalized: str) -> bool:
    signals = [
        "trieu",
        "tr",
        "vnd",
        "million",
        "ngan sach",
        "budget",
        "tam gia",
        "duoi",
        "tren",
        "khoang",
        "tam",
        "toi da",
        "under",
        "below",
        "around",
        "about",
    ]
    return any(_contains_alias(normalized, signal) for signal in signals)


def _alias_score(normalized: str, aliases: List[str]) -> int:
    return sum(1 for alias in aliases if _contains_alias(normalized, alias))


def _contains_alias(normalized: str, alias: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", normalized) is not None


def _extract_explicit_budget_range(normalized: str) -> Optional[tuple[float, float, str]]:
    patterns = [
        r"tu\s+(\d+(?:[.,]\d+)?)\s*(trieu|tr|m|k|nghin|ngan)?\s*(?:den|toi|-)\s*(\d+(?:[.,]\d+)?)\s*(trieu|tr|m|k|nghin|ngan)?",
        r"(\d+(?:[.,]\d+)?)\s*(?:-|den|toi|to)\s*(\d+(?:[.,]\d+)?)\s*(trieu|tr|m|k|nghin|ngan)",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if not match:
            continue
        if pattern.startswith("tu"):
            first, first_unit, second, second_unit = match.groups()
        else:
            first, second, second_unit = match.groups()
            first_unit = second_unit
        lower = _parse_budget_amount(first, first_unit or second_unit)
        upper = _parse_budget_amount(second, second_unit or first_unit)
        if lower and upper:
            return (min(lower, upper), max(lower, upper), match.group(0).strip())
    return None


def _extract_flexible_max_budget(normalized: str, target: float) -> Optional[float]:
    patterns = [
        r"(?:co the|neu tot thi|san sang|chap nhan|len duoc|co the len|tang len|them toi da)\s*(?:len|toi|den|them)?\s*(\d+(?:[.,]\d+)?)\s*(trieu|tr|m|k|nghin|ngan)?",
        r"(?:toi da|max|maximum|khong qua)\s*(\d+(?:[.,]\d+)?)\s*(trieu|tr|m|k|nghin|ngan)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if not match:
            continue
        value = _parse_budget_amount(match.group(1), match.group(2) or "trieu")
        if value and value >= target:
            return value
    return None


def _extract_budget_margin(normalized: str) -> Optional[float]:
    match = re.search(
        r"(?:tren duoi|cong tru|\+/-|chenh|lech|them|hon kem)\s*(\d+(?:[.,]\d+)?)\s*(trieu|tr|m|k|nghin|ngan)?",
        normalized,
    )
    if not match:
        return None
    return _parse_budget_amount(match.group(1), match.group(2) or "trieu")


def _parse_budget_amount(amount_text: str, unit: Optional[str]) -> Optional[float]:
    try:
        value = float(amount_text.replace(",", "."))
    except (TypeError, ValueError):
        return None
    unit = unit or "trieu"
    if unit in {"trieu", "tr", "m"}:
        return value * 1_000_000
    if unit in {"k", "nghin", "ngan"}:
        return value * 1_000
    return value


def _budget_raw(normalized: str) -> str:
    match = re.search(
        r"(?:duoi|tren|khoang|tam|toi da|tu|budget|under|around|about)?\s*\d+(?:[.,]\d+)?\s*(?:trieu|tr|m|k|nghin|ngan|vnd|million)?",
        normalized,
    )
    return match.group(0).strip() if match else ""
