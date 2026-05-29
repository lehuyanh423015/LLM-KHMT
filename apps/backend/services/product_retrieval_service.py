"""
Product Retrieval Service (Knowledge Base)

Developer B owns the real implementation behind this stable interface.

This prototype uses hybrid retrieval:
- internal demo catalog first
- optional external web search fallback for products outside the catalog
- one normalized candidate schema for both sources
- strict budget grouping: fits / maybe / unknown
"""

import json
import re
import unicodedata
from typing import Dict, List, Optional

from duckduckgo_search import DDGS
from sqlalchemy.orm import Session

from core.config import settings
from models.database_models import CustomerProfile


DEMO_PRODUCTS = [
    {
        "name": "POCO X7 Pro",
        "category": "phone",
        "year": "2025",
        "use_case": ["gaming", "performance", "battery"],
        "price_min": 10_000_000,
        "price_max": 14_000_000,
        "why": "chip Dimensity 8400-Ultra và pin lớn, hợp với gaming tầm giá 15 triệu",
        "tradeoff": "cần kiểm tra hàng chính hãng và giá từng cửa hàng",
    },
    {
        "name": "POCO F6",
        "category": "phone",
        "year": "2024",
        "use_case": ["gaming", "performance"],
        "price_min": 9_000_000,
        "price_max": 12_500_000,
        "why": "Snapdragon 8s Gen 3, hiệu năng tốt trong tầm giá",
        "tradeoff": "cần kiểm tra nhiệt độ khi chơi game lâu",
    },
    {
        "name": "Xiaomi 14T",
        "category": "phone",
        "year": "2024",
        "use_case": ["balanced", "performance"],
        "price_min": 11_000_000,
        "price_max": 15_000_000,
        "why": "cân bằng giữa hiệu năng và trải nghiệm hằng ngày",
        "tradeoff": "không thiên gaming bằng dòng POCO hiệu năng/giá",
    },
    {
        "name": "Samsung Galaxy A56 5G",
        "category": "phone",
        "year": "2025",
        "use_case": ["balanced", "battery"],
        "price_min": 9_000_000,
        "price_max": 12_500_000,
        "why": "ổn định nếu cần máy chính hãng, dễ bảo hành",
        "tradeoff": "hiệu năng gaming không phải điểm mạnh nhất",
    },
    {
        "name": "ASUS Vivobook Pro 15",
        "category": "laptop",
        "year": "2024-2025",
        "use_case": ["creator", "office", "performance"],
        "price_min": 21_000_000,
        "price_max": 26_000_000,
        "why": "hợp làm văn phòng nặng, Photoshop/Premiere nếu chọn bản GPU rời",
        "tradeoff": "một số cấu hình màn đẹp/GPU rời có thể vượt 25 triệu",
    },
    {
        "name": "Lenovo IdeaPad Pro 5",
        "category": "laptop",
        "year": "2024-2025",
        "use_case": ["creator", "office", "performance"],
        "price_min": 20_000_000,
        "price_max": 26_000_000,
        "why": "phù hợp làm việc văn phòng nặng, đa nhiệm và chỉnh ảnh/video vừa phải",
        "tradeoff": "không phải mọi cấu hình đều có GPU rời, cần kiểm tra đúng phiên bản",
    },
    {
        "name": "Acer Swift X 14",
        "category": "laptop",
        "year": "2024-2025",
        "use_case": ["creator", "office", "lightweight", "performance"],
        "price_min": 22_000_000,
        "price_max": 28_000_000,
        "why": "hướng creator mỏng nhẹ, hợp Photoshop/Premiere nếu tìm được cấu hình trong ngân sách",
        "tradeoff": "giá dao động mạnh, cấu hình tốt có thể vượt 25 triệu",
    },
    {
        "name": "HP Victus 15",
        "category": "laptop",
        "year": "2024-2025",
        "use_case": ["gaming", "creator", "office", "balanced"],
        "price_min": 18_000_000,
        "price_max": 24_000_000,
        "why": "cân bằng giữa làm việc, học tập và tác vụ đồ họa/video phổ thông",
        "tradeoff": "nên ưu tiên bản 16GB RAM và GPU rời nếu dùng Premiere thường xuyên",
    },
    {
        "name": "Lenovo LOQ 15",
        "category": "laptop",
        "year": "2024-2025",
        "use_case": ["gaming", "creator", "performance"],
        "price_min": 20_000_000,
        "price_max": 25_000_000,
        "why": "hiệu năng tốt trong tầm 25 triệu, thường có tùy chọn RTX 4050",
        "tradeoff": "màn hình và pin tùy cấu hình, cần kiểm tra đúng mã máy",
    },
    {
        "name": "Acer Nitro V 15",
        "category": "laptop",
        "year": "2024-2025",
        "use_case": ["gaming", "creator", "value"],
        "price_min": 18_000_000,
        "price_max": 24_000_000,
        "why": "dễ tìm trong phân khúc hiệu năng/giá, có cấu hình RTX 4050",
        "tradeoff": "tản nhiệt và chất lượng màn hình khác nhau theo phiên bản",
    },
]


def get_product_knowledge_context(
    user_message: str,
    session_id: str,
    db: Session,
) -> str:
    """Stable interface for product knowledge retrieval."""
    retrieval = _retrieve_products(user_message, session_id, db)
    if not retrieval["candidates"]:
        return ""
    return json.dumps(retrieval, ensure_ascii=False)


def get_grounded_product_answer(
    user_message: str,
    session_id: str,
    db: Session,
) -> str:
    """Render a grounded answer from internal and external candidates."""
    retrieval = _retrieve_products(user_message, session_id, db)
    candidates = retrieval["candidates"]
    if not candidates:
        return ""

    category = retrieval.get("category") or candidates[0]["category"]
    query_tags = set(_extract_intent_tags(user_message))
    budget_max = retrieval.get("budget_max")
    quality_mode = settings.LLM_MODE.strip().lower() == "quality"

    heading = _answer_heading(category, query_tags)
    lines = [f"{heading}:"]

    fits = [item for item in candidates if item["budget_status"] == "fits"]
    maybe = [item for item in candidates if item["budget_status"] == "maybe"]
    unknown = [item for item in candidates if item["budget_status"] == "unknown"]

    if budget_max and not fits and maybe:
        lines.append(
            f"Tôi chưa có mẫu nào chắc chắn thấp hơn {_format_price(budget_max)} trong dữ liệu hiện có. "
            "Các mẫu dưới đây có thể có cấu hình/đợt sale chạm ngân sách, cần kiểm tra giá thực tế."
        )

    if fits:
        lines.extend(_format_candidate_group("Phù hợp ngân sách", fits, quality_mode))
    if maybe:
        lines.extend(_format_candidate_group("Có thể cân nhắc nếu chọn cấu hình thấp/săn sale", maybe, quality_mode))
    if unknown:
        lines.extend(_format_candidate_group("Ngoài hệ thống / cần kiểm tra thêm", unknown, quality_mode))

    if category == "laptop" and "creator" in query_tags:
        lines.append(
            "Checklist: CPU dòng H/HS hoặc tương đương, RAM 16GB+, SSD 512GB+, "
            "GPU rời nếu dùng Premiere/Photoshop nặng, bảo hành và giá hiện tại."
        )
    elif category == "laptop":
        lines.append(
            "Checklist: CPU/GPU đúng cấu hình, RAM 16GB+, SSD 512GB+, "
            "tản nhiệt, màn hình, bảo hành và giá hiện tại."
        )
    elif category == "phone":
        lines.append(
            "Checklist: chipset, RAM/bộ nhớ, tản nhiệt, pin, bảo hành và giá hiện tại."
        )
    else:
        lines.append("Checklist: giá hiện tại, nguồn bán, bảo hành, thông số chính và độ phù hợp nhu cầu.")

    return "\n".join(lines)


def extract_product_keywords(user_message: str) -> list:
    """Extract simple product and intent keywords for the demo catalog."""
    msg = _normalize_text(user_message)
    keywords = []
    for keyword in [
        "gaming", "game", "pin", "battery", "cheap", "re", "hieu nang", "ben",
        "van phong", "office", "adobe", "premiere", "photoshop", "do hoa",
        "edit", "render", "tac vu nang", "creator", "da nhiem", "review",
        "gia hien tai", "so sanh",
    ]:
        if keyword in msg:
            keywords.append(keyword)
    return keywords


def search_product_database(
    keywords: list,
    budget_max: Optional[float] = None,
    category: Optional[str] = None,
) -> list:
    """Search the internal demo catalog and normalize to ProductCandidate dicts."""
    results = []
    for product in DEMO_PRODUCTS:
        if category and product["category"] != category:
            continue

        candidate = _to_candidate(product, source_type="internal", source_url=None)
        if keywords and not _candidate_matches_intent(candidate, keywords):
            continue
        candidate["relevance_score"] = _score_candidate(candidate, keywords, budget_max)
        candidate["budget_status"] = _budget_status(candidate, budget_max)
        results.append(candidate)

    results.sort(key=lambda item: (item["budget_rank"], item["relevance_score"]), reverse=True)
    return results[:5]


def format_products_for_llm(products: list) -> str:
    """Backward-compatible formatter for LLM prompt injection."""
    if not products:
        return ""
    return json.dumps({"products": products}, ensure_ascii=False)


def _retrieve_products(user_message: str, session_id: str, db: Session) -> Dict:
    category = _detect_category(user_message, session_id, db)
    budget_max = _extract_budget_max(user_message) or _profile_budget_max(session_id, db)
    keywords = _extract_intent_tags(user_message)

    internal = search_product_database(keywords, budget_max=budget_max, category=category)
    internal = _filter_visible_candidates(internal, budget_max)

    external = []
    if _should_use_external_search(user_message, internal):
        external = _search_external_products(user_message, category, budget_max)

    candidates = _deduplicate_candidates(internal + external)
    candidates.sort(key=lambda item: (item["budget_rank"], item["relevance_score"], item["confidence"]), reverse=True)

    return {
        "type": "hybrid_product_context",
        "category": category,
        "budget_max": budget_max,
        "notice": "Internal catalog is preferred. External results are references and must be verified.",
        "candidates": candidates[:7],
    }


def _filter_visible_candidates(candidates: List[Dict], budget_max: Optional[float]) -> List[Dict]:
    if not budget_max:
        return candidates[:4]

    fits = [item for item in candidates if item["budget_status"] == "fits"]
    maybe = [item for item in candidates if item["budget_status"] == "maybe"]
    if fits:
        return (fits + maybe)[:4]
    return maybe[:4]


def _should_use_external_search(user_message: str, internal_candidates: List[Dict]) -> bool:
    if not settings.ENABLE_WEB_SEARCH or not settings.ENABLE_EXTERNAL_PRODUCT_SEARCH:
        return False

    msg = _normalize_text(user_message)
    search_signals = [
        "gia hien tai", "moi nhat", "review", "danh gia", "so sanh",
        "co hang", "ngoai he thong", "cua hang khong co", "chi tiet",
    ]
    if any(signal in msg for signal in search_signals):
        return True

    return len(internal_candidates) < 2


def _search_external_products(
    user_message: str,
    category: Optional[str],
    budget_max: Optional[float],
) -> List[Dict]:
    try:
        query = _build_external_query(user_message, category, budget_max)
        ddgs = DDGS(timeout=5)
        results = list(ddgs.text(query, max_results=settings.EXTERNAL_PRODUCT_SEARCH_RESULTS))
    except Exception as e:
        print(f"[External Product Search] {e}")
        return [_external_unavailable_candidate(category, str(e))]

    candidates = []
    for result in results:
        title = result.get("title", "").strip()
        href = result.get("href", "").strip()
        body = result.get("body", "").strip()
        if not title or not href:
            continue
        candidate = {
            "name": _clean_external_title(title),
            "category": category or "unknown",
            "year": _extract_year(title + " " + body) or "unknown",
            "use_case": ["external_reference"],
            "price_min": None,
            "price_max": None,
            "currency": "VND",
            "source_type": "external",
            "source_url": href,
            "in_store": False,
            "last_checked": "search result",
            "confidence": 0.45,
            "why": body[:180] if body else "kết quả ngoài hệ thống, cần mở nguồn để kiểm tra",
            "tradeoff": "chưa xác minh giá/tồn kho/thông số trong hệ thống",
            "budget_status": "unknown",
            "budget_rank": 1,
            "relevance_score": 1.0,
        }
        candidates.append(candidate)
    return candidates


def _external_unavailable_candidate(category: Optional[str], error: str) -> Dict:
    return {
        "name": "Không truy xuất được kết quả ngoài hệ thống",
        "category": category or "unknown",
        "year": "unknown",
        "use_case": ["external_reference"],
        "price_min": None,
        "price_max": None,
        "currency": "VND",
        "source_type": "external",
        "source_url": None,
        "in_store": False,
        "last_checked": "external search unavailable",
        "confidence": 0.0,
        "why": "nguồn tìm kiếm ngoài hệ thống đang lỗi hoặc bị giới hạn tần suất",
        "tradeoff": f"không thể xác minh thông tin hiện tại qua web search ({error[:80]})",
        "budget_status": "unknown",
        "budget_rank": 1,
        "relevance_score": 0.0,
    }


def _build_external_query(user_message: str, category: Optional[str], budget_max: Optional[float]) -> str:
    budget_text = f" dưới {_format_price(budget_max)}" if budget_max else ""
    category_text = category or "sản phẩm"
    return f"{category_text} {user_message}{budget_text} giá đánh giá 2025 2026 Việt Nam"


def _to_candidate(product: Dict, source_type: str, source_url: Optional[str]) -> Dict:
    return {
        "name": product["name"],
        "category": product["category"],
        "year": product.get("year", "unknown"),
        "use_case": product.get("use_case", []),
        "price_min": product.get("price_min"),
        "price_max": product.get("price_max"),
        "currency": "VND",
        "source_type": source_type,
        "source_url": source_url,
        "in_store": source_type == "internal",
        "last_checked": "demo catalog",
        "confidence": 0.75 if source_type == "internal" else 0.45,
        "why": product.get("why", ""),
        "tradeoff": product.get("tradeoff", ""),
    }


def _score_candidate(candidate: Dict, keywords: List[str], budget_max: Optional[float]) -> float:
    score = 0.0
    tags = set(candidate.get("use_case", []))
    for keyword in keywords:
        if keyword in {"game", "gaming"} and "gaming" in tags:
            score += 3
        elif keyword in {"hieu nang", "performance"} and "performance" in tags:
            score += 3
        elif keyword in {"adobe", "premiere", "photoshop", "do hoa", "edit", "render", "tac vu nang", "creator"} and "creator" in tags:
            score += 4
        elif keyword in {"van phong", "office", "da nhiem"} and "office" in tags:
            score += 2
        elif keyword in tags:
            score += 2

    if budget_max and candidate.get("price_max"):
        score += max(0, 1 - abs(candidate["price_max"] - budget_max) / 10_000_000)
    return score


def _candidate_matches_intent(candidate: Dict, keywords: List[str]) -> bool:
    tags = set(candidate.get("use_case", []))
    for keyword in keywords:
        if keyword in {"game", "gaming"} and "gaming" in tags:
            return True
        if keyword in {"hieu nang", "performance"} and "performance" in tags:
            return True
        if keyword in {"adobe", "premiere", "photoshop", "do hoa", "edit", "render", "tac vu nang", "creator"} and "creator" in tags:
            return True
        if keyword in {"van phong", "office", "da nhiem"} and "office" in tags:
            return True
        if keyword in tags:
            return True
    return False


def _budget_status(candidate: Dict, budget_max: Optional[float]) -> str:
    if not budget_max:
        candidate["budget_rank"] = 2
        return "unknown"

    price_min = candidate.get("price_min")
    price_max = candidate.get("price_max")
    if price_min is None or price_max is None:
        candidate["budget_rank"] = 1
        return "unknown"
    if price_max <= budget_max:
        candidate["budget_rank"] = 3
        return "fits"
    if price_min <= budget_max < price_max:
        candidate["budget_rank"] = 2
        return "maybe"

    candidate["budget_rank"] = 0
    return "over_budget"


def _format_candidate_group(title: str, candidates: List[Dict], quality_mode: bool) -> List[str]:
    lines = [f"\n{title}:"]
    for i, item in enumerate(candidates, 1):
        source = "trong hệ thống" if item["source_type"] == "internal" else "ngoài hệ thống"
        price = _candidate_price_text(item)
        if quality_mode:
            lines.append(
                f"{i}. {item['name']} ({item.get('year', 'unknown')}) - {price} [{source}]\n"
                f"   - Lý do phù hợp: {item['why']}.\n"
                f"   - Cần cân nhắc: {item['tradeoff']}.\n"
                f"   - Nguồn: {item['source_url'] or item['last_checked']}."
            )
        else:
            lines.append(
                f"{i}. {item['name']} - {price} [{source}]: {item['why']}. "
                f"Cần kiểm tra: {item['tradeoff']}."
            )
    return lines


def _candidate_price_text(item: Dict) -> str:
    if item.get("price_min") and item.get("price_max"):
        return f"{_format_price(item['price_min'])}-{_format_price(item['price_max'])}"
    return "chưa rõ giá"


def _answer_heading(category: Optional[str], tags: set) -> str:
    if category == "phone":
        return "Một vài điện thoại đáng cân nhắc"
    if category == "laptop" and "creator" in tags:
        return "Một vài laptop cho văn phòng nặng/Adobe đáng cân nhắc"
    if category == "laptop" and "gaming" in tags:
        return "Một vài laptop gaming đáng cân nhắc"
    if category == "laptop":
        return "Một vài laptop đáng cân nhắc"
    return "Một vài lựa chọn đáng cân nhắc"


def _deduplicate_candidates(candidates: List[Dict]) -> List[Dict]:
    seen = set()
    unique = []
    for item in candidates:
        key = _normalize_text(item["name"])[:50]
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _detect_category(user_message: str, session_id: str, db: Session) -> Optional[str]:
    msg = _normalize_text(user_message)
    if _looks_like_phone_query(msg):
        return "phone"
    if any(term in msg for term in ["laptop", "notebook", "may tinh xach tay", "macbook"]):
        return "laptop"
    if _looks_like_laptop_work_query(msg):
        return "laptop"

    profile = db.query(CustomerProfile).filter(CustomerProfile.session_id == session_id).first()
    if profile and profile.preferred_category:
        category = _normalize_text(profile.preferred_category)
        if category in {"dien thoai", "phone", "smartphone"}:
            return "phone"
        if category in {"laptop", "notebook", "may tinh xach tay"}:
            return "laptop"
    return None


def _looks_like_phone_query(normalized_message: str) -> bool:
    if any(term in normalized_message for term in ["dien thoai", "phone", "smartphone", "iphone"]):
        return True
    tokens = re.findall(r"[a-z0-9]+", normalized_message)
    if "dien" not in tokens:
        return False
    phone_like_tokens = {"thoai", "thoat", "thoa", "dt", "dienthoai"}
    if any(token in phone_like_tokens for token in tokens):
        return True
    return any(_edit_distance_at_most_one(token, "thoai") for token in tokens)


def _looks_like_laptop_work_query(normalized_message: str) -> bool:
    work_terms = [
        "van phong", "adobe", "premiere", "photoshop", "do hoa",
        "edit video", "render", "tac vu nang", "lap trinh", "may tinh",
    ]
    if any(term in normalized_message for term in work_terms):
        return True
    tokens = set(re.findall(r"[a-z0-9]+", normalized_message))
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


def _extract_intent_tags(user_message: str) -> list:
    msg = _normalize_text(user_message)
    tags = extract_product_keywords(msg)
    if any(term in msg for term in ["game", "gaming", "choi game"]):
        tags.append("gaming")
    if any(term in msg for term in ["pin", "battery"]):
        tags.append("battery")
    if any(term in msg for term in ["ben", "durable"]):
        tags.append("durable")
    if any(term in msg for term in ["adobe", "premiere", "photoshop", "do hoa", "edit", "render", "tac vu nang"]):
        tags.append("creator")
    if "van phong" in msg or "office" in msg or "da nhiem" in msg:
        tags.append("office")
    if "hieu nang" in msg or "performance" in msg:
        tags.append("performance")
    return list(dict.fromkeys(tags))


def _extract_budget_max(text: str) -> Optional[float]:
    msg = _normalize_text(text)
    match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(tr|trieu|m|million)", msg)
    if not match:
        return None
    amount = float(match.group(1).replace(",", "."))
    return amount * 1_000_000


def _profile_budget_max(session_id: str, db: Session) -> Optional[float]:
    profile = db.query(CustomerProfile).filter(CustomerProfile.session_id == session_id).first()
    if not profile or not profile.budget:
        return None
    return _extract_budget_max(profile.budget)


def _format_price(value: float) -> str:
    return f"{value / 1_000_000:.0f} triệu"


def _clean_external_title(title: str) -> str:
    title = re.sub(r"\s*[-|].*$", "", title).strip()
    return title[:90]


def _extract_year(text: str) -> Optional[str]:
    match = re.search(r"\b(202[4-6])\b", text)
    return match.group(1) if match else None


def _normalize_text(value: str) -> str:
    text = value.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()
