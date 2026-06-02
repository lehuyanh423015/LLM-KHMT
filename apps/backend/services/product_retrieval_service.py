"""
Product Retrieval Service - Knowledge layer.

Developer B owns product retrieval behind this stable interface:
    get_product_knowledge_context(user_message: str, session_id: str, db) -> str

Developer A's orchestrator may also call get_grounded_product_answer() as a
safe fast path to avoid small local models hallucinating product lists.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.parse import quote_plus

from duckduckgo_search import DDGS
from sqlalchemy.orm import Session

from core.config import settings
from models.database_models import CustomerProfile
from services.data_normalization import (
    format_vnd,
    normalize_text,
    parse_budget_to_vnd,
    tokenize,
    unique_preserve_order,
)
from vector_store.client import get_chroma_client


CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "mini_product_catalog.json"

CATEGORY_KEYWORDS = {
    "laptop": {"laptop", "may tinh", "may tinh xach tay", "notebook", "macbook"},
    "phone": {"dien thoai", "dien thoat", "smartphone", "phone", "mobile", "iphone", "dt"},
    "tablet": {"may tinh bang", "tablet", "ipad"},
    "mouse": {"chuot", "mouse"},
    "keyboard": {"ban phim", "keyboard"},
    "monitor": {"man hinh", "monitor"},
    "headphones": {"tai nghe", "headphone", "headphones", "earbud", "earbuds"},
}

LAPTOP_WORK_SIGNALS = {
    "adobe",
    "premiere",
    "photoshop",
    "do hoa",
    "render",
    "edit video",
    "lap trinh",
    "van phong",
    "tac vu nang",
}

PRIORITY_KEYWORDS = {
    "gaming": {"gaming", "choi game", "game", "chien game"},
    "battery": {"pin", "battery", "pin trau", "pin lau"},
    "camera": {"camera", "chup anh", "chup hinh"},
    "lightweight": {"nhe", "mong", "mong nhe", "gon", "lightweight"},
    "performance": {"hieu nang", "performance", "manh", "nhanh", "muot"},
    "durable": {"ben", "durable", "chac"},
    "value": {"re", "gia re", "value", "affordable", "hop ly"},
    "student": {"hoc tap", "sinh vien", "student"},
    "office": {"van phong", "office"},
    "creator": {"adobe", "premiere", "photoshop", "do hoa", "render", "edit"},
}

STOPWORDS = {
    "a", "an", "and", "about", "around", "below", "budget", "cai", "can",
    "cho", "co", "de", "duoc", "duoi", "gia", "goi", "hon", "khoang",
    "khong", "la", "less", "mua", "muon", "nay", "san", "pham", "tam",
    "than", "the", "tim", "toi", "tr", "trieu", "under", "vnd", "voi", "y",
}


def get_product_knowledge_context(
    user_message: str,
    session_id: str,
    db: Session,
) -> str:
    """Return prompt-safe product context, or an empty string if nothing is reliable."""

    retrieval = _retrieve_products(user_message, session_id, db)
    if retrieval.get("needs_clarification"):
        return retrieval.get("clarification", "")

    candidates = retrieval.get("candidates", [])
    if not candidates:
        return ""

    return format_products_for_llm(candidates[:5])


def get_grounded_product_answer(
    user_message: str,
    session_id: str,
    db: Session,
) -> str:
    """
    Render a deterministic product answer from retrieved candidates.

    This keeps the current demo responsive and prevents fast local models from
    inventing stale product names. The LLM path remains available when product
    context is disabled or no product data is found.
    """

    retrieval = _retrieve_products(user_message, session_id, db)
    if retrieval.get("needs_clarification"):
        return retrieval.get("clarification", "")

    candidates = retrieval.get("candidates", [])
    if not candidates:
        return ""

    category = retrieval.get("category") or candidates[0].get("category")
    budget_max = retrieval.get("budget_max")
    query_tags = set(retrieval.get("priorities", []))
    quality_mode = settings.LLM_MODE.strip().lower() == "quality"

    lines = [_answer_heading(category, query_tags) + ":"]

    best_pick = candidates[0]
    lines.extend(_format_best_pick(best_pick, budget_max, query_tags))

    remaining = candidates[1:]
    fits = [item for item in remaining if item.get("budget_status") == "fits"]
    maybe = [item for item in remaining if item.get("budget_status") == "maybe"]
    unknown = [item for item in remaining if item.get("budget_status") == "unknown"]

    if budget_max and not fits and maybe:
        lines.append(
            f"Tôi chưa có mẫu nào chắc chắn dưới {format_vnd(budget_max)} trong dữ liệu hiện có. "
            "Các mẫu sau có thể chạm ngân sách ở cấu hình thấp hoặc khi giảm giá."
        )

    if fits:
        lines.extend(_format_candidate_group("Phương án thay thế phù hợp ngân sách", fits, quality_mode))
    if maybe:
        lines.extend(_format_candidate_group("Có thể cân nhắc nếu săn sale/chọn cấu hình thấp", maybe, quality_mode))
    if unknown:
        lines.extend(_format_candidate_group("Ngoài hệ thống hoặc cần kiểm tra thêm", unknown, quality_mode))

    lines.append(_checklist_for(category, query_tags))
    return "\n".join(lines)


def extract_product_keywords(user_message: str) -> List[str]:
    """Extract category, priority, budget, and useful product search tokens."""

    normalized = normalize_text(user_message)
    if not normalized:
        return []

    keywords: List[str] = []
    category = _detect_category_from_text(normalized)
    if category:
        keywords.append(category)

    for priority, tokens in PRIORITY_KEYWORDS.items():
        if any(_contains_alias(normalized, token) for token in tokens):
            keywords.append(priority)

    budget_value = parse_budget(user_message)
    if budget_value is not None:
        keywords.append(f"budget:{int(budget_value)}")

    for token in tokenize(normalized):
        if token in STOPWORDS or token in keywords:
            continue
        if len(token) < 2 or any(ch.isdigit() for ch in token):
            continue
        keywords.append(token)

    return unique_preserve_order(keywords)


def search_product_database(
    keywords: List[str],
    budget_max: float = None,
    category: str = None,
) -> List[Dict]:
    """Search Chroma first, then fall back to the local mini product dataset."""

    search_terms = [kw for kw in keywords if not kw.startswith("budget:")]
    query_text = " ".join(search_terms) or category or "san pham"

    results = _search_chroma_products(query_text=query_text, category=category)
    if not results:
        results = _search_mini_catalog(search_terms, category)

    products = _normalize_product_records(results)
    if budget_max is not None:
        products = filter_by_budget(products, budget_max)

    return products[:24]


def filter_by_budget(products: List[Dict], budget_max: float) -> List[Dict]:
    """Strict public helper used by tests and simple retrieval flows."""

    if budget_max is None:
        return products

    filtered: List[Dict] = []
    for product in products:
        try:
            price = float(product.get("price"))
        except (TypeError, ValueError):
            continue
        if price <= budget_max:
            filtered.append(product)
    return filtered


def format_products_for_llm(products: List[Dict]) -> str:
    """Convert product records into compact prompt-safe text."""

    if not products:
        return ""

    lines = [
        "San pham de xuat:",
        "Don vi gia: VND. Chi coi day la du lieu noi bo/demo neu source la mini_catalog.",
        "Khong bia them mau san pham, gia hoac thong so ngoai danh sach nay.",
    ]
    for index, product in enumerate(products, 1):
        name = product.get("name", "Unknown")
        price = format_vnd(product.get("price"))
        currency = product.get("currency", "VND")
        description = product.get("description", "")
        source = product.get("source", "")
        url = _source_url_for_item(product)

        line = f"{index}. {name} - {price} {currency}"
        if description:
            line += f" - {description}"
        if source:
            line += f" - Nguon: {source}"
        line += f" - Link kiem tra: {url}"
        lines.append(line)

    return "\n".join(lines)


def parse_budget(budget_str: str) -> Optional[float]:
    return parse_budget_to_vnd(budget_str)


def format_price(price: object) -> str:
    return format_vnd(price)


def _retrieve_products(user_message: str, session_id: str, db: Session) -> Dict:
    if not user_message or not user_message.strip():
        return {"candidates": []}

    profile = db.query(CustomerProfile).filter(
        CustomerProfile.session_id == session_id
    ).first()

    keywords = extract_product_keywords(user_message)
    direct_category = _detect_category_from_text(normalize_text(user_message))
    preferred_category = profile.preferred_category if profile else None
    category = _resolve_category(user_message, keywords, preferred_category)
    priorities = _extract_priorities(keywords, profile.priorities if profile else None)
    dislikes = _extract_dislikes(getattr(profile, "dislikes", None) if profile else None)

    query_budget = parse_budget(user_message)
    memory_budget = parse_budget(profile.budget) if profile and profile.budget else None
    budget_max = query_budget if query_budget is not None else memory_budget

    if _needs_category_clarification(user_message, direct_category, preferred_category, priorities):
        return {
            "needs_clarification": True,
            "clarification": _build_category_clarification(budget_max, priorities),
            "candidates": [],
        }

    products = search_product_database(keywords=keywords, budget_max=None, category=category)
    products = _drop_disliked_products(products, dislikes)
    products = _apply_context_scoring(products, keywords, category, priorities)
    candidates = _with_budget_status(products, budget_max)
    candidates.sort(
        key=lambda item: (
            item.get("budget_rank", 0),
            item.get("relevance_score", 0.0),
        ),
        reverse=True,
    )
    candidates = _visible_candidates(candidates, budget_max)

    if _should_use_external_search(user_message, candidates):
        candidates.extend(_search_external_products(user_message, category, budget_max))

    candidates = _deduplicate_candidates(candidates)
    candidates.sort(
        key=lambda item: (
            item.get("budget_rank", 0),
            item.get("relevance_score", 0.0),
        ),
        reverse=True,
    )

    return {
        "type": "hybrid_product_context",
        "category": category,
        "budget_max": budget_max,
        "priorities": priorities,
        "notice": "Internal catalog/Chroma is preferred. External results must be verified.",
        "candidates": candidates[:7],
    }


def _load_mini_catalog() -> List[Dict]:
    try:
        with CATALOG_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except Exception as exc:
        print(f"[Product Retrieval] Could not load mini catalog: {exc}")
        return []
    return data if isinstance(data, list) else []


def _search_chroma_products(query_text: str, category: Optional[str]) -> List[Dict]:
    client = get_chroma_client()
    if not client:
        return []

    collection = None
    for name in ("products", "product_catalog", "catalog"):
        try:
            collection = client.get_collection(name=name)
            break
        except Exception:
            continue

    if collection is None:
        return []

    query_kwargs = {"query_texts": [query_text], "n_results": 8}
    if category:
        query_kwargs["where"] = {"category": category}

    try:
        result = collection.query(**query_kwargs)
    except Exception as exc:
        print(f"[Product Retrieval] Chroma query failed: {exc}")
        return []

    return _convert_chroma_result(result)


def _convert_chroma_result(result: Dict) -> List[Dict]:
    documents = result.get("documents") or []
    metadatas = result.get("metadatas") or []
    distances = result.get("distances") or []
    ids = result.get("ids") or []

    products: List[Dict] = []
    for group_index, document_group in enumerate(documents):
        for item_index, document in enumerate(document_group or []):
            metadata = _nested_get(metadatas, group_index, item_index, default={}) or {}
            distance = _nested_get(distances, group_index, item_index)
            product_id = _nested_get(ids, group_index, item_index)
            products.append(
                {
                    "id": product_id,
                    "name": metadata.get("name")
                    or metadata.get("product_name")
                    or metadata.get("title")
                    or str(document)[:80],
                    "price": metadata.get("price"),
                    "currency": metadata.get("currency", "VND"),
                    "description": metadata.get("description") or str(document),
                    "category": metadata.get("category"),
                    "url": metadata.get("url", ""),
                    "source": metadata.get("source", "chroma"),
                    "tags": metadata.get("tags", []),
                    "relevance_score": _distance_to_score(distance),
                }
            )

    return products


def _nested_get(groups: List, group_index: int, item_index: int, default=None):
    try:
        return groups[group_index][item_index]
    except (IndexError, TypeError):
        return default


def _distance_to_score(distance: Optional[float]) -> float:
    if distance is None:
        return 0.5
    try:
        return max(0.0, 1.0 - float(distance))
    except (TypeError, ValueError):
        return 0.5


def _search_mini_catalog(keywords: List[str], category: Optional[str]) -> List[Dict]:
    candidates = []
    for product in _load_mini_catalog():
        product_category = normalize_text(product.get("category"))
        if category and category != product_category:
            continue
        candidates.append(dict(product))

    if not candidates:
        candidates = [dict(product) for product in _load_mini_catalog()]

    for product in candidates:
        product["relevance_score"] = _score_product(product, keywords, category)

    candidates.sort(key=lambda item: item.get("relevance_score", 0.0), reverse=True)
    return candidates


def _normalize_product_records(products: List[Dict]) -> List[Dict]:
    normalized: List[Dict] = []
    for product in products:
        if not isinstance(product, dict):
            continue
        normalized.append(
            {
                "id": product.get("id"),
                "name": product.get("name") or product.get("product_name") or "Unknown",
                "price": product.get("price"),
                "currency": product.get("currency", "VND"),
                "description": product.get("description", ""),
                "category": normalize_text(product.get("category")),
                "url": product.get("url", ""),
                "source": product.get("source", "product_search"),
                "tags": product.get("tags", []),
                "relevance_score": float(product.get("relevance_score", 0.0) or 0.0),
            }
        )
    return normalized


def _resolve_category(
    user_message: str,
    keywords: List[str],
    preferred_category: Optional[str],
) -> Optional[str]:
    normalized = normalize_text(user_message)
    direct = _detect_category_from_text(normalized)
    if direct:
        return direct

    for keyword in keywords:
        if keyword in CATEGORY_KEYWORDS:
            return keyword

    preferred = normalize_text(preferred_category)
    if preferred:
        for category, tokens in CATEGORY_KEYWORDS.items():
            if category in preferred or any(token in preferred for token in tokens):
                return category

    return None


def _detect_category_from_text(normalized: str) -> Optional[str]:
    if _looks_like_phone_query(normalized):
        return "phone"
    if any(_contains_alias(normalized, token) for token in CATEGORY_KEYWORDS["laptop"]):
        return "laptop"
    if any(_contains_alias(normalized, token) for token in LAPTOP_WORK_SIGNALS):
        return "laptop"

    for category, tokens in CATEGORY_KEYWORDS.items():
        if category == "laptop":
            continue
        if any(_contains_alias(normalized, token) for token in tokens):
            return category
    return None


def _extract_priorities(keywords: List[str], profile_priorities: Optional[str]) -> List[str]:
    priorities = [kw for kw in keywords if kw in PRIORITY_KEYWORDS]
    normalized = normalize_text(profile_priorities)
    if normalized:
        for priority, tokens in PRIORITY_KEYWORDS.items():
            if any(token in normalized for token in tokens):
                priorities.append(priority)
    return unique_preserve_order(priorities)


def _extract_dislikes(profile_dislikes: Optional[str]) -> List[str]:
    return [token for token in tokenize(profile_dislikes) if token not in STOPWORDS]


def _drop_disliked_products(products: List[Dict], dislikes: List[str]) -> List[Dict]:
    if not dislikes:
        return products

    kept = []
    for product in products:
        haystack = _product_haystack(product)
        if any(dislike in haystack for dislike in dislikes):
            continue
        kept.append(product)
    return kept


def _apply_context_scoring(
    products: List[Dict],
    keywords: List[str],
    category: Optional[str],
    priorities: List[str],
) -> List[Dict]:
    for product in products:
        score = float(product.get("relevance_score", 0.0) or 0.0)
        score += _score_product(product, keywords, category)

        haystack = _product_haystack(product)
        tags = {normalize_text(tag) for tag in product.get("tags", [])}
        for priority in priorities:
            if priority in tags:
                score += 2.0
            elif any(token in haystack for token in PRIORITY_KEYWORDS.get(priority, set())):
                score += 0.5

        product["relevance_score"] = score

    products.sort(key=lambda item: item.get("relevance_score", 0.0), reverse=True)
    return products


def _score_product(product: Dict, keywords: Iterable[str], category: Optional[str]) -> float:
    score = 0.0
    haystack = _product_haystack(product)
    product_category = normalize_text(product.get("category"))

    if category and category == product_category:
        score += 3.0

    tags = {normalize_text(tag) for tag in product.get("tags", [])}
    for keyword in keywords:
        if keyword.startswith("budget:"):
            continue
        if keyword in CATEGORY_KEYWORDS and keyword == product_category:
            score += 2.0
        elif keyword in PRIORITY_KEYWORDS:
            if keyword in tags:
                score += 2.5
            elif any(token in haystack for token in PRIORITY_KEYWORDS[keyword]):
                score += 0.8
        elif keyword in haystack or keyword in tags:
            score += 0.7

    return score


def _with_budget_status(products: List[Dict], budget_max: Optional[float]) -> List[Dict]:
    output = []
    for product in products:
        item = dict(product)
        item["budget_status"], item["budget_rank"] = _budget_status(item, budget_max)
        item["relevance_score"] = float(item.get("relevance_score", 0.0) or 0.0)
        item["relevance_score"] += _budget_fit_score(item, budget_max)
        output.append(item)
    return output


def _budget_status(product: Dict, budget_max: Optional[float]) -> tuple[str, int]:
    if not budget_max:
        return "unknown", 2

    try:
        price = float(product.get("price"))
    except (TypeError, ValueError):
        return "unknown", 1

    if price <= budget_max:
        return "fits", 3
    if price <= budget_max * 1.15:
        return "maybe", 2
    return "over_budget", 0


def _visible_candidates(candidates: List[Dict], budget_max: Optional[float]) -> List[Dict]:
    if not budget_max:
        return candidates[:5]

    fits = [item for item in candidates if item.get("budget_status") == "fits"]
    maybe = [item for item in candidates if item.get("budget_status") == "maybe"]
    unknown = [item for item in candidates if item.get("budget_status") == "unknown"]

    if fits:
        return (fits + maybe + unknown)[:5]
    if maybe:
        return (maybe + unknown)[:5]
    return unknown[:3]


def _budget_fit_score(product: Dict, budget_max: Optional[float]) -> float:
    """Prefer stronger products near the user's budget instead of always the cheapest fit."""

    if not budget_max:
        return 0.0

    try:
        price = float(product.get("price"))
    except (TypeError, ValueError):
        return 0.0

    if price <= 0 or price > budget_max * 1.15:
        return 0.0

    tags = {normalize_text(tag) for tag in product.get("tags", [])}
    target_ratio = min(price / budget_max, 1.0)
    score = target_ratio * 2.8

    if "gaming" in tags or "performance" in tags:
        score += target_ratio * 0.8
    if "gaming" in tags:
        score += 0.8
    if budget_max >= 20_000_000 and "premium" in tags:
        score += target_ratio * 1.4

    return score


def _should_use_external_search(user_message: str, internal_candidates: List[Dict]) -> bool:
    if not settings.ENABLE_WEB_SEARCH or not settings.ENABLE_EXTERNAL_PRODUCT_SEARCH:
        return False

    normalized = normalize_text(user_message)
    search_signals = [
        "gia hien tai",
        "moi nhat",
        "review",
        "danh gia",
        "so sanh",
        "co hang",
        "ngoai he thong",
        "cua hang khong co",
        "chi tiet",
    ]
    return any(signal in normalized for signal in search_signals) or len(internal_candidates) < 2


def _search_external_products(
    user_message: str,
    category: Optional[str],
    budget_max: Optional[float],
) -> List[Dict]:
    try:
        query = _build_external_query(user_message, category, budget_max)
        ddgs = DDGS(timeout=5)
        results = list(ddgs.text(query, max_results=settings.EXTERNAL_PRODUCT_SEARCH_RESULTS))
    except Exception as exc:
        print(f"[External Product Search] {exc}")
        return [_external_unavailable_candidate(category, str(exc))]

    candidates = []
    for result in results:
        title = result.get("title", "").strip()
        href = result.get("href", "").strip()
        body = result.get("body", "").strip()
        if not title or not href:
            continue
        candidates.append(
            {
                "name": _clean_external_title(title),
                "price": None,
                "currency": "VND",
                "description": body[:180] if body else "Ket qua ngoai he thong, can mo nguon de kiem tra.",
                "category": category or "unknown",
                "url": href,
                "source": "external_search",
                "tags": ["external_reference"],
                "relevance_score": 0.5,
                "budget_status": "unknown",
                "budget_rank": 1,
            }
        )
    return candidates


def _external_unavailable_candidate(category: Optional[str], error: str) -> Dict:
    return {
        "name": "Khong truy xuat duoc ket qua ngoai he thong",
        "price": None,
        "currency": "VND",
        "description": f"Tim kiem ngoai he thong dang loi hoac bi gioi han tan suat: {error[:80]}",
        "category": category or "unknown",
        "url": "",
        "source": "external_search_unavailable",
        "tags": ["external_reference"],
        "relevance_score": 0.0,
        "budget_status": "unknown",
        "budget_rank": 1,
    }


def _build_external_query(user_message: str, category: Optional[str], budget_max: Optional[float]) -> str:
    budget_text = f" duoi {format_vnd(budget_max)}" if budget_max else ""
    category_text = category or "san pham"
    return f"{category_text} {user_message}{budget_text} gia danh gia 2025 2026 Viet Nam"


def _format_candidate_group(title: str, candidates: List[Dict], quality_mode: bool) -> List[str]:
    lines = [f"\n{title}:"]
    for index, item in enumerate(candidates[:4], 1):
        source = item.get("source", "product_search")
        price = format_vnd(item.get("price")) if item.get("price") is not None else "chua ro gia"
        description = item.get("description", "")
        url = _source_url_for_item(item)
        if quality_mode:
            lines.append(
                f"{index}. {item.get('name', 'Unknown')} - {price} [{source}]\n"
                f"   - Phù hợp: {description}\n"
                f"   - Vai trò: {_role_summary(item)}\n"
                f"   - Cần kiểm tra: giá hiện tại, cấu hình đúng mã, bảo hành.\n"
                f"   - Link kiểm tra: {url}."
            )
        else:
            lines.append(
                f"{index}. {item.get('name', 'Unknown')} - {price} [{source}]: {description}. "
                "Cần kiểm tra giá/cấu hình thực tế."
            )
    return lines


def _format_best_pick(
    item: Dict,
    budget_max: Optional[float],
    query_tags: set,
) -> List[str]:
    price = format_vnd(item.get("price")) if item.get("price") is not None else "chưa rõ giá"
    tags = {normalize_text(tag) for tag in item.get("tags", [])}
    reasons = []

    if budget_max and item.get("price") is not None:
        try:
            price_value = float(item.get("price"))
            if price_value <= budget_max:
                reasons.append(f"nằm trong ngân sách {format_vnd(budget_max)}")
            elif price_value <= budget_max * 1.15:
                reasons.append("có thể chạm ngân sách nếu chọn cấu hình thấp hoặc săn sale")
        except (TypeError, ValueError):
            pass

    matched_tags = sorted((query_tags & tags) - {"phone", "laptop"})
    if matched_tags:
        reasons.append("khớp nhu cầu " + ", ".join(matched_tags))

    if not reasons:
        reasons.append("có điểm phù hợp cao nhất trong dữ liệu hiện có")

    lines = [
        "",
        f"Lựa chọn phù hợp nhất: {item.get('name', 'Unknown')} - {price}",
        f"- Vì sao: {', '.join(reasons)}.",
        f"- Mô tả: {item.get('description', '')}",
        f"- Không nên chọn nếu: {_avoid_summary(item, query_tags)}",
        f"- Link kiểm tra: {_source_url_for_item(item)}",
        f"- Lưu ý: đây là dữ liệu demo/nội bộ; nên kiểm tra lại giá, cấu hình đúng mã và bảo hành trước khi mua.",
    ]
    return lines


def _source_url_for_item(item: Dict) -> str:
    """
    Return a user-clickable verification URL.

    Demo catalog rows may not have exact retailer URLs. In that case we return
    a search URL instead of exposing fake example.com links as if they were
    product pages.
    """

    url = str(item.get("url") or "").strip()
    if url and "example.com/products" not in url:
        return url

    name = str(item.get("name") or "san pham").strip()
    category = str(item.get("category") or "").strip()
    query = f"{name} {category} giá Việt Nam review"
    return f"https://www.google.com/search?q={quote_plus(query)}"


def _needs_category_clarification(
    user_message: str,
    direct_category: Optional[str],
    preferred_category: Optional[str],
    priorities: List[str],
) -> bool:
    if direct_category or preferred_category:
        return False

    normalized = normalize_text(user_message)
    has_buying_signal = any(
        term in normalized
        for term in ["mua", "goi y", "tu van", "chon", "nen mua", "duoi", "tam", "khoang"]
    )
    has_generic_machine = any(term in normalized for term in ["may", "san pham", "thiet bi"])
    has_product_intent = bool(priorities) or parse_budget(user_message) is not None
    return has_buying_signal and has_generic_machine and has_product_intent


def _build_category_clarification(
    budget_max: Optional[float],
    priorities: List[str],
) -> str:
    budget_text = f" với ngân sách khoảng {format_vnd(budget_max)}" if budget_max else ""
    priority_text = f" và nhu cầu {', '.join(priorities)}" if priorities else ""
    return (
        f"Bạn đang muốn mua điện thoại hay laptop{budget_text}{priority_text}? "
        "Hai nhóm này có tiêu chí rất khác nhau: điện thoại ưu tiên chipset, pin, camera và tản nhiệt; "
        "laptop ưu tiên CPU, GPU, RAM, màn hình và tản nhiệt. "
        "Bạn xác nhận loại sản phẩm trước, rồi tôi sẽ gợi ý mẫu phù hợp nhất."
    )


def _avoid_summary(item: Dict, query_tags: set) -> str:
    tags = {normalize_text(tag) for tag in item.get("tags", [])}
    category = normalize_text(item.get("category"))

    if category == "phone":
        if "gaming" in query_tags and "gaming" not in tags:
            return "bạn ưu tiên chơi game nặng trong thời gian dài"
        if "camera" in query_tags and "camera" not in tags:
            return "bạn cần camera/video tốt nhất trong phân khúc"
        if "battery" in query_tags and "battery" not in tags:
            return "bạn ưu tiên pin trâu hơn hiệu năng/camera"
        if "premium" in tags:
            return "bạn muốn tối ưu hiệu năng/giá thay vì trải nghiệm cao cấp"
        return "bạn cần thông số rất chuyên biệt chưa có trong catalog demo"

    if category == "laptop":
        if "gaming" in query_tags and "gaming" not in tags:
            return "bạn cần chơi game nặng hoặc GPU rời mạnh"
        if "creator" in query_tags and "creator" not in tags:
            return "bạn dùng Premiere/Photoshop nặng hoặc render thường xuyên"
        if "lightweight" in query_tags and "lightweight" not in tags:
            return "bạn cần máy thật nhẹ và pin rất lâu"
        if "gaming" in tags:
            return "bạn ưu tiên máy mỏng nhẹ, pin lâu và ít ồn hơn hiệu năng"
        return "bạn cần cấu hình đặc thù chưa có trong catalog demo"

    return "nhu cầu của bạn khác với điểm mạnh chính của sản phẩm"


def _role_summary(item: Dict) -> str:
    tags = {normalize_text(tag) for tag in item.get("tags", [])}
    if "gaming" in tags and "creator" in tags:
        return "mạnh cho game và tác vụ đồ họa/video"
    if "gaming" in tags:
        return "ưu tiên chơi game/hiệu năng"
    if "creator" in tags:
        return "ưu tiên đồ họa, Adobe, render hoặc sáng tạo nội dung"
    if "office" in tags:
        return "ưu tiên học tập, văn phòng và làm việc hằng ngày"
    if "camera" in tags:
        return "ưu tiên camera và trải nghiệm cân bằng"
    if "battery" in tags:
        return "ưu tiên pin và tính ổn định"
    return "phương án cân bằng"


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


def _checklist_for(category: Optional[str], tags: set) -> str:
    if category == "laptop" and "creator" in tags:
        return (
            "Checklist: CPU H/HS hoặc tương đương, RAM 16GB+, SSD 512GB+, "
            "GPU rời nếu dùng Premiere/Photoshop nặng, màn hình và bảo hành."
        )
    if category == "laptop":
        return "Checklist: CPU/GPU đúng cấu hình, RAM 16GB+, SSD 512GB+, tản nhiệt, màn hình và bảo hành."
    if category == "phone":
        return "Checklist: chipset, RAM/bộ nhớ, tản nhiệt, pin, bảo hành và giá hiện tại."
    return "Checklist: giá hiện tại, nguồn bán, bảo hành, thông số chính và độ phù hợp nhu cầu."


def _product_haystack(product: Dict) -> str:
    tags = " ".join(str(tag) for tag in product.get("tags", []))
    return normalize_text(
        f"{product.get('name', '')} {product.get('description', '')} "
        f"{product.get('category', '')} {tags}"
    )


def _deduplicate_candidates(candidates: List[Dict]) -> List[Dict]:
    seen = set()
    unique = []
    for item in candidates:
        key = normalize_text(item.get("name", ""))[:60]
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


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


def _clean_external_title(title: str) -> str:
    title = re.sub(r"\s*[-|].*$", "", title).strip()
    return title[:90]
