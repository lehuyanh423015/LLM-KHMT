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
        "office",
        "excel",
        "word",
        "powerpoint",
        "hop online",
        "tac vu nang",
    ],
}

PRIORITY_ALIASES = {
    "gaming": ["gaming", "choi game", "game", "chien game", "fps", "aaa", "valorant", "lol", "lien minh", "genshin"],
    "camera": ["camera", "chup anh", "chup hinh", "quay phim", "video", "selfie"],
    "display": ["man hinh", "display", "oled", "amoled", "tan so quet", "hien thi", "dep"],
    "battery": ["pin", "pin trau", "pin lau", "battery"],
    "performance": ["hieu nang", "manh", "nhanh", "muot", "cau hinh", "chip"],
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
    "value": ["gia tot", "gia re", "p/p", "ti le gia", "ty le gia", "cau hinh tot", "dang tien"],
    "ram": ["ram", "da nhiem", "multitask", "16gb", "32gb"],
    "storage": ["ssd", "bo nho", "luu tru", "storage", "rom", "1tb", "512gb"],
    "cooling": ["tan nhiet", "mat may", "khong nong", "cooling"],
    "creator": ["adobe", "premiere", "photoshop", "do hoa", "render", "edit video", "chinh anh", "dung video", "thiet ke", "cad", "3d"],
    "office": ["van phong", "office", "hoc tap", "sinh vien", "excel", "word", "powerpoint", "hop online", "zoom", "teams"],
    "coding": ["lap trinh", "code", "dev", "developer", "ide"],
    "ai_work": ["ai", "machine learning", "deep learning", "llm", "cuda"],
    "lightweight": ["nhe", "mong", "mong nhe", "gon", "de mang"],
    "build_quality": ["build", "hoan thien", "chat lieu", "vo kim loai", "ben", "chac"],
    "warranty": ["bao hanh", "chinh hang", "hau mai"],
    "software": ["phan mem", "cap nhat", "on dinh", "he sinh thai"],
    "keyboard": ["ban phim", "keyboard", "go phim", "typing"],
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

BRAND_CATEGORY_HINTS = {
    "laptop": {
        "acer",
        "asus",
        "dell",
        "hp",
        "lenovo",
        "lg",
        "microsoft",
        "msi",
    },
    "phone": {
        "google",
        "honor",
        "nothing",
        "oneplus",
        "oppo",
        "realme",
        "samsung",
        "vivo",
        "xiaomi",
    },
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
    "khong choi",
    "khong dung de",
    "khong lien quan den",
    "khong phuc vu",
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
    "san pham tren",
    "mau tren",
    "ban vua goi y",
    "mau do",
    "con do",
    "cai do",
]

SMALL_TALK_PATTERNS = [
    "cam on",
    "cam on ban",
    "thanks",
    "thank you",
    "ok",
    "oke",
    "okay",
    "duoc roi",
    "toi hieu roi",
    "minh hieu roi",
    "hieu roi",
    "da hieu",
    "ro roi",
    "dung roi",
    "hay qua",
    "tot qua",
    "de toi xem",
    "de minh xem",
    "toi se xem them",
    "minh se xem them",
    "tam thoi vay",
    "hen gap lai",
    "chao",
    "xin chao",
]

ALTERNATIVE_SIGNALS = [
    "lua chon khac",
    "mau khac",
    "chon khac",
    "phuong an khac",
    "goi y khac",
    "san pham khac",
    "cac hang khac",
    "hang khac",
    "cac thuong hieu khac",
    "thuong hieu khac",
    "brand khac",
    "ngoai",
    "tot hon",
    "cao cap hon",
    "xung dang hon",
]

OWNED_SIGNALS = [
    "dang co",
    "da co",
    "co roi",
    "dang dung",
    "da dung",
    "mua roi",
    "xai roi",
    "dung roi",
    "tung dung",
]


def understand_query(user_message: str) -> Dict:
    """Return stable structured signals extracted from a user message."""

    normalized = normalize_text(user_message)
    is_small_talk = is_small_talk_message(user_message)
    budget = extract_budget_constraint(normalized)
    category = _extract_category(normalized)
    priorities = _extract_positive_priorities(normalized)
    dislikes = _extract_negative_priorities(normalized)
    owned_brands = _extract_owned_brands(normalized)
    is_alternative_request = _is_alternative_query(normalized)
    preferred_brands = _extract_brands(normalized, positive=True)
    disliked_brands = _extract_brands(normalized, positive=False)
    excluded_brands = _extract_other_brand_exclusions(
        normalized,
        owned_brands=owned_brands,
        is_alternative_request=is_alternative_request,
    )
    disliked_brands.extend(excluded_brands)
    preferred_os = _extract_os(normalized, positive=True)
    disliked_os = _extract_os(normalized, positive=False)
    preferred_brands = [
        brand for brand in preferred_brands
        if brand not in disliked_brands and not (is_alternative_request and brand in owned_brands)
    ]
    preferred_os = [os_name for os_name in preferred_os if os_name not in disliked_os]
    intent = _extract_intent(normalized)
    if is_small_talk:
        intent = "small_talk"
    is_follow_up = (
        is_alternative_request
        or any(_contains_alias(normalized, signal) for signal in FOLLOW_UP_SIGNALS)
    )

    confidence = 0.15
    for signal in (category, priorities, budget.get("target"), preferred_brands, dislikes, disliked_brands):
        if signal:
            confidence += 0.15
    if intent != "unknown":
        confidence += 0.1

    return {
        "intent": intent,
        "is_small_talk": is_small_talk,
        "category": category,
        "budget": budget,
        "priorities": unique_preserve_order(priorities),
        "dislikes": unique_preserve_order(dislikes),
        "preferred_brands": unique_preserve_order(preferred_brands),
        "disliked_brands": unique_preserve_order(disliked_brands),
        "owned_brands": unique_preserve_order(owned_brands),
        "excluded_brands": unique_preserve_order(excluded_brands),
        "preferred_os": unique_preserve_order(preferred_os),
        "disliked_os": unique_preserve_order(disliked_os),
        "is_follow_up": is_follow_up,
        "is_alternative_request": is_alternative_request,
        "confidence": min(confidence, 1.0),
    }


def is_small_talk_message(user_message: object) -> bool:
    normalized = normalize_text(user_message)
    if not normalized:
        return False
    if _is_closing_or_thanks_message(normalized):
        return True
    if _has_product_request_signal(normalized):
        return False

    compact = re.sub(r"[^a-z0-9\s]", " ", normalized)
    compact = re.sub(r"\s+", " ", compact).strip()
    if any(_contains_alias(compact, pattern) for pattern in SMALL_TALK_PATTERNS):
        meaningful_tokens = [token for token in compact.split() if token not in {"ban", "toi", "minh", "nhe", "nha", "a", "da"}]
        return len(meaningful_tokens) <= 8
    return False


def is_product_request_message(user_message: object) -> bool:
    """True when the user is asking about shopping/product advice."""
    normalized = normalize_text(user_message)
    if _is_closing_or_thanks_message(normalized):
        return False
    if _is_meta_system_discussion(normalized):
        return False
    if _is_vague_consultation_opener(normalized):
        return False
    return _has_product_request_signal(normalized)


def needs_product_clarification(user_message: object) -> bool:
    """
    True when a shopping request is too underspecified for a useful recommendation.

    This keeps the assistant conversational: "I want to buy a phone" should ask
    for budget and usage first instead of immediately forcing a catalog answer.
    """
    normalized = normalize_text(user_message)
    if not is_product_request_message(user_message):
        return False

    parsed = understand_query(str(user_message or ""))
    if parsed.get("intent") == "comparison":
        return False

    detail_signals = ["cau hinh", "thong so", "chi tiet", "review", "danh gia", "so sanh"]
    if any(_contains_alias(normalized, signal) for signal in detail_signals):
        return False

    has_category = bool(parsed.get("category"))
    budget = parsed.get("budget") or {}
    has_budget = bool(budget.get("target") or budget.get("max") or budget.get("min"))
    has_need = bool(
        parsed.get("priorities")
        or parsed.get("dislikes")
        or parsed.get("preferred_brands")
        or parsed.get("disliked_brands")
        or parsed.get("preferred_os")
        or parsed.get("disliked_os")
    )

    if not has_category and (
        parsed.get("preferred_brands")
        or parsed.get("priorities")
        or parsed.get("is_follow_up")
    ):
        return False

    if not has_category:
        return any(_contains_alias(normalized, signal) for signal in RECOMMENDATION_SIGNALS)

    # Category-only or category + very broad buying intent is too vague.
    if not has_budget and not has_need:
        return True
    if not has_budget and not parsed.get("preferred_brands") and any(
        _contains_alias(normalized, signal)
        for signal in ["muon mua", "can mua", "dang muon mua", "mua", "tu van", "goi y"]
    ):
        return True
    return False


def product_clarification_response(user_message: object) -> str:
    """Deterministic fallback question for underspecified product requests."""
    parsed = understand_query(str(user_message or ""))
    category = parsed.get("category")

    if category == "phone":
        return (
            "Được, mình sẽ tư vấn điện thoại cho bạn. Bạn cho mình thêm một chút thông tin nhé: "
            "ngân sách khoảng bao nhiêu, ưu tiên pin/camera/chơi game/màn hình hay dùng cơ bản, "
            "và có hãng hoặc hệ điều hành nào muốn tránh không? "
            "Ví dụ: “điện thoại tầm 10 triệu, pin tốt, không cần camera, không thích iPhone”."
        )
    if category == "laptop":
        return (
            "Được, mình sẽ tư vấn laptop cho bạn. Bạn cho mình thêm ngân sách, mục đích chính "
            "(văn phòng, học tập, chơi game, lập trình, đồ họa) và có cần mỏng nhẹ/pin lâu/GPU rời không nhé. "
            "Ví dụ: “laptop tầm 25 triệu, văn phòng pin lâu, nhẹ, không cần chơi game”."
        )
    return (
        "Được chứ. Bạn muốn mình tư vấn điện thoại, laptop hay một sản phẩm cụ thể nào? "
        "Nếu có thể, bạn nói thêm ngân sách và mục đích sử dụng để mình gợi ý sát hơn."
    )


def small_talk_response(user_message: object) -> str:
    normalized = normalize_text(user_message)
    if _is_closing_or_thanks_message(normalized) and any(
        _contains_alias(normalized, token)
        for token in ["se mua", "s mua", "mua san pham nay", "mua s n ph m n y", "lay san pham nay", "chon san pham nay", "chot mau nay", "chot san pham nay"]
    ):
        return "Không có gì. Nếu bạn đã nghiêng về mẫu đó thì trước khi mua nhớ kiểm tra lại đúng phiên bản, giá hiện tại và bảo hành nhé."
    if any(_contains_alias(normalized, token) for token in ["cam on", "thanks", "thank you"]):
        return "Không có gì. Khi nào bạn cần xem thêm mẫu hoặc so sánh sản phẩm thì cứ nhắn mình."
    if any(_contains_alias(normalized, token) for token in ["toi hieu roi", "minh hieu roi", "hieu roi", "da hieu", "ro roi", "ok", "oke", "okay", "duoc roi"]):
        return "Ừ, mình hiểu. Khi nào bạn muốn xem tiếp lựa chọn nào thì mình sẽ hỗ trợ."
    if any(_contains_alias(normalized, token) for token in ["chao", "xin chao"]):
        return "Chào bạn. Bạn cần mình hỗ trợ gì hôm nay?"
    return "Mình hiểu rồi. Khi nào bạn cần tư vấn thêm thì cứ nhắn mình."


def _is_closing_or_thanks_message(normalized: str) -> bool:
    if not normalized:
        return False

    thanks_or_closing = [
        "cam on",
        "c m n",
        "thanks",
        "thank you",
        "toi hieu roi",
        "minh hieu roi",
        "duoc roi",
        "ok",
        "oke",
    ]
    purchase_closing = [
        "se mua",
        "s mua",
        "mua san pham nay",
        "mua s n ph m n y",
        "lay san pham nay",
        "chon san pham nay",
        "chot mau nay",
        "chot san pham nay",
        "nghieng ve mau nay",
        "co le minh se mua",
        "co le toi se mua",
    ]
    new_request_signals = [
        "goi y",
        "g i",
        "tu van them",
        "tu van giup",
        "nho tu van",
        "so sanh",
        "cau hinh",
        "thong so",
        "chi tiet",
        "mau nao",
        "san pham nao",
        "laptop",
        "dien thoai",
        "i n tho i",
        "ngan sach",
        "tam gia",
        "duoi",
        "trieu",
        "tri u",
    ]

    has_closing = any(_contains_alias(normalized, signal) for signal in thanks_or_closing + purchase_closing)
    has_new_request = any(_contains_alias(normalized, signal) for signal in new_request_signals)
    return has_closing and not has_new_request


def _has_product_request_signal(normalized: str) -> bool:
    if not normalized:
        return False
    signal_groups = [
        RECOMMENDATION_SIGNALS,
        COMPARISON_SIGNALS,
        ALTERNATIVE_SIGNALS,
        [alias for aliases in CATEGORY_ALIASES.values() for alias in aliases],
        [alias for aliases in PRIORITY_ALIASES.values() for alias in aliases],
        ["gia", "ngan sach", "budget", "trieu", "duoi", "tam", "khoang", "cau hinh", "thong so", "chi tiet"],
    ]
    return any(_contains_alias(normalized, signal) for group in signal_groups for signal in group)


def _is_meta_system_discussion(normalized: str) -> bool:
    if not normalized:
        return False

    meta_terms = [
        "llm",
        "chatbot",
        "chat bot",
        "prompt",
        "template",
        "catalog",
        "rag",
        "memory",
        "flow",
        "logic",
        "intent",
        "phan hoi",
        "tra loi",
        "giao tiep",
    ]
    design_terms = [
        "linh hoat",
        "su dung",
        "ap dung",
        "ket hop",
        "chiu trach nhiem",
        "chinh xac",
        "tu nhien",
        "can cai thien",
        "khac phuc",
        "du an",
        "he thong",
    ]
    shopping_terms = [
        "dien thoai",
        "laptop",
        "may tinh",
        "iphone",
        "android",
        "macbook",
        "mua",
        "chon mua",
        "goi y san pham",
        "san pham nao",
        "tam gia",
        "ngan sach",
        "trieu",
    ]

    has_meta = any(_contains_alias(normalized, term) for term in meta_terms)
    has_design = any(_contains_alias(normalized, term) for term in design_terms)
    has_shopping = any(_contains_alias(normalized, term) for term in shopping_terms)

    return has_meta and not has_shopping and (
        has_design
        or any(_contains_alias(normalized, term) for term in ["llm", "chatbot", "chat bot", "template", "catalog", "rag", "memory", "flow"])
    )


def _is_vague_consultation_opener(normalized: str) -> bool:
    if not normalized:
        return False
    opener_signals = [
        "nho ban tu van",
        "nho tu van",
        "tu van mot chut",
        "tu van 1 chut",
        "hoi mot chut",
        "hoi 1 chut",
        "can ban tu van",
        "ban tu van giup",
    ]
    if not any(_contains_alias(normalized, signal) for signal in opener_signals):
        return False

    concrete_signal_groups = [
        [alias for aliases in CATEGORY_ALIASES.values() for alias in aliases],
        [alias for aliases in PRIORITY_ALIASES.values() for alias in aliases],
        ["gia", "ngan sach", "budget", "trieu", "duoi", "tam", "khoang", "cau hinh", "thong so", "chi tiet", "mua", "chon"],
    ]
    return not any(
        _contains_alias(normalized, signal)
        for group in concrete_signal_groups
        for signal in group
    )


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
        return _infer_category_from_brand(normalized)
    return "phone" if phone_score >= laptop_score else "laptop"


def _infer_category_from_brand(normalized: str) -> Optional[str]:
    for category, brands in BRAND_CATEGORY_HINTS.items():
        for brand in brands:
            aliases = BRAND_ALIASES.get(brand, [brand])
            if any(_contains_alias(normalized, alias) for alias in aliases):
                return category
    return None


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
        has_preference_signal = any(marker in normalized for marker in POSITIVE_MARKERS)
        has_shopping_signal = any(
            _contains_alias(normalized, signal)
            for signal in RECOMMENDATION_SIGNALS + ["mua", "tim", "can", "laptop", "dien thoai"]
        )
        if not (has_preference_signal or has_shopping_signal):
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


def _extract_owned_brands(normalized: str) -> List[str]:
    if not normalized:
        return []

    owned = []
    for canonical, aliases in BRAND_ALIASES.items():
        for alias in aliases:
            if not _contains_alias(normalized, alias):
                continue
            if _has_nearby_signal(normalized, alias, OWNED_SIGNALS, before=7, after=5):
                owned.append(f"brand:{canonical}")
                break
    return unique_preserve_order(owned)


def _extract_other_brand_exclusions(
    normalized: str,
    owned_brands: Optional[List[str]] = None,
    is_alternative_request: bool = False,
) -> List[str]:
    if not normalized:
        return []

    other_brand_signals = [
        "cac hang khac",
        "hang khac",
        "cac thuong hieu khac",
        "thuong hieu khac",
        "cac brand khac",
        "brand khac",
        "ngoai hang",
        "ngoai brand",
        "khac ngoai",
        "ngoai",
        "khong phai",
        "khong lay",
        "doi hang",
        "doi thuong hieu",
    ]
    has_other_signal = any(_contains_alias(normalized, signal) for signal in other_brand_signals)
    has_owned_signal = any(_contains_alias(normalized, signal) for signal in OWNED_SIGNALS)
    if not has_other_signal and not (is_alternative_request and owned_brands):
        return []

    disliked = []
    if is_alternative_request and owned_brands:
        disliked.extend(owned_brands)

    for canonical, aliases in BRAND_ALIASES.items():
        brand_key = f"brand:{canonical}"
        if brand_key in disliked:
            continue
        if not any(_contains_alias(normalized, alias) for alias in aliases):
            continue
        direct_exclusion = any(
            _has_nearby_signal(normalized, alias, other_brand_signals, before=5, after=5)
            for alias in aliases
        )
        owned_then_other = has_owned_signal and has_other_signal
        if direct_exclusion or owned_then_other:
            disliked.append(f"brand:{canonical}")
    return unique_preserve_order(disliked)


def _is_alternative_query(normalized: str) -> bool:
    return any(_contains_alias(normalized, signal) for signal in ALTERNATIVE_SIGNALS)


def _has_nearby_signal(
    normalized: str,
    alias: str,
    signals: List[str],
    before: int,
    after: int,
) -> bool:
    tokens = normalized.split()
    alias_tokens = alias.split()
    if not tokens or not alias_tokens:
        return False

    for index in range(0, len(tokens) - len(alias_tokens) + 1):
        if tokens[index : index + len(alias_tokens)] != alias_tokens:
            continue
        left = max(0, index - before)
        right = min(len(tokens), index + len(alias_tokens) + after)
        window = " ".join(tokens[left:right])
        if any(_contains_alias(window, signal) for signal in signals):
            return True
    return False


def _extract_os(normalized: str, positive: bool) -> List[str]:
    priorities = _extract_positive_priorities(normalized) if positive else _extract_negative_priorities(normalized)
    return [item for item in priorities if item in {"android", "ios", "windows", "macos"}]


def _extract_intent(normalized: str) -> str:
    if any(_contains_alias(normalized, signal) for signal in COMPARISON_SIGNALS):
        return "comparison"
    if any(_contains_alias(normalized, signal) for signal in RECOMMENDATION_SIGNALS + ALTERNATIVE_SIGNALS):
        return "recommendation"
    if "?" in normalized or any(signal in normalized for signal in ["co nen", "duoc khong", "phu hop khong"]):
        return "recommendation"
    return "unknown"


def _negative_phrases(normalized: str) -> List[str]:
    spans: List[str] = []
    pattern = (
        r"(?:khong thich|khong tich|khong muon|khong dung|khong xai|khong lay|khong can|khong uu tien|"
        r"khong choi|khong dung de|khong lien quan den|khong phuc vu|khong|"
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
