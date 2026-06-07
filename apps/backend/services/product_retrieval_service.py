"""
Product Retrieval Service - Knowledge layer.

Developer B owns product retrieval behind this stable interface:
    get_product_knowledge_context(user_message: str, session_id: str, db) -> str

Developer A's orchestrator may also call get_grounded_product_answer() as a
safe deterministic fallback to avoid local models hallucinating product lists.
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
from models.database_models import Conversation, CustomerProfile, Message
from services.answer_planning_service import build_answer_plan, render_answer_plan
from services.data_normalization import (
    format_vnd,
    normalize_text,
    parse_budget_to_vnd,
    tokenize,
    unique_preserve_order,
)
from services.query_understanding_service import is_small_talk_message, understand_query
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
    "display": {"man hinh", "display", "oled", "amoled", "tan so quet"},
    "storage": {"bo nho", "luu tru", "ssd", "storage", "rom"},
    "ram": {"ram", "da nhiem", "multitask"},
    "cooling": {"tan nhiet", "mat may", "khong nong", "cooling"},
    "lightweight": {"nhe", "mong", "mong nhe", "gon", "lightweight"},
    "performance": {"hieu nang", "performance", "manh", "nhanh", "muot"},
    "max_performance": {
        "sieu manh",
        "manh me",
        "manh nhat",
        "cau hinh sieu manh",
        "khong quan tam gia",
        "khong gioi han ngan sach",
        "tat ca game nang",
        "game nang hien tai",
    },
    "durable": {"ben", "durable", "chac"},
    "build_quality": {"build", "vo kim loai", "hoan thien", "chat lieu", "cao cap"},
    "warranty": {"bao hanh", "chinh hang", "hau mai", "bao tri"},
    "software": {"phan mem", "cap nhat", "on dinh", "he sinh thai"},
    "keyboard": {"ban phim", "keyboard", "go phim", "typing"},
    "value": {"re", "gia re", "value", "affordable", "hop ly", "gia thanh", "cau hinh", "p/p"},
    "china_brand": {"hang trung quoc", "trung quoc", "hang tq", "china brand", "hang china"},
    "student": {"hoc tap", "sinh vien", "student"},
    "office": {"van phong", "office"},
    "creator": {"adobe", "premiere", "photoshop", "do hoa", "render", "edit"},
    "coding": {"lap trinh", "code", "dev", "developer", "ide"},
    "ai_work": {"ai", "machine learning", "deep learning", "llm", "cuda"},
    "upgradeable": {"nang cap", "them ram", "them ssd", "upgrade"},
    "compact": {"nho gon", "compact", "de cam", "de mang"},
    "premium": {"flagship", "cao cap", "premium"},
    "android": {"android"},
    "ios": {"ios", "iphone"},
    "windows": {"windows"},
    "macos": {"macos", "macbook"},
}

CHINESE_VALUE_BRANDS = {
    "honor",
    "huawei",
    "iqoo",
    "lenovo",
    "meizu",
    "nubia",
    "oneplus",
    "oppo",
    "poco",
    "realme",
    "redmi",
    "tecno",
    "vivo",
    "xiaomi",
    "zte",
}

APPLE_PLATFORM_DISLIKES = {"ios", "apple", "iphone", "ipad", "macos", "macbook"}

VOLATILE_NEED_PRIORITIES = {
    "ai_work",
    "battery",
    "build_quality",
    "camera",
    "coding",
    "compact",
    "cooling",
    "creator",
    "design",
    "display",
    "durable",
    "gaming",
    "lightweight",
    "max_performance",
    "office",
    "performance",
    "premium",
    "ram",
    "software",
    "storage",
    "student",
    "upgradeable",
    "value",
    "warranty",
    "keyboard",
}

BRAND_PRIORITY_ALIASES = {
    "apple": {"apple", "iphone", "macbook", "ipad"},
    "samsung": {"samsung", "galaxy"},
    "xiaomi": {"xiaomi", "redmi", "poco"},
    "oppo": {"oppo"},
    "vivo": {"vivo", "iqoo"},
    "realme": {"realme"},
    "oneplus": {"oneplus"},
    "lenovo": {"lenovo", "thinkpad", "loq", "legion", "ideapad"},
    "asus": {"asus", "vivobook", "zenbook", "tuf", "rog"},
    "acer": {"acer", "aspire", "nitro", "predator"},
    "hp": {"hp", "victus", "pavilion", "omen"},
    "dell": {"dell", "inspiron", "xps", "alienware"},
    "msi": {"msi"},
    "lg": {"lg", "gram"},
    "microsoft": {"surface", "microsoft"},
    "google": {"google", "pixel"},
    "nothing": {"nothing"},
    "honor": {"honor"},
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
    if is_small_talk_message(user_message):
        return ""

    retrieval = _retrieve_products(user_message, session_id, db)
    if retrieval.get("needs_clarification"):
        return retrieval.get("clarification", "")

    candidates = retrieval.get("candidates", [])
    if not candidates:
        return ""

    context = format_products_for_llm(candidates[:5])
    budget_line = _budget_context_line(
        retrieval.get("budget_min"),
        retrieval.get("budget_target"),
        retrieval.get("budget_max"),
    )
    return f"{budget_line}\n{context}" if budget_line else context


def get_grounded_product_answer(
    user_message: str,
    session_id: str,
    db: Session,
) -> str:
    """
    Render a deterministic product answer from retrieved candidates.

    This keeps the current demo responsive and prevents local models from
    inventing stale product names. The LLM path remains available when product
    context is disabled or no product data is found.
    """
    if is_small_talk_message(user_message):
        return ""

    retrieval = _retrieve_products(user_message, session_id, db)
    if retrieval.get("needs_clarification"):
        return retrieval.get("clarification", "")

    candidates = retrieval.get("candidates", [])
    if not candidates:
        return ""

    plan = build_answer_plan(retrieval, user_message=user_message)
    answer = render_answer_plan(plan)
    if answer:
        return answer

    return ""


def extract_product_keywords(user_message: str) -> List[str]:
    """Extract category, priority, budget, and useful product search tokens."""

    normalized = normalize_text(user_message)
    if not normalized:
        return []

    keywords: List[str] = []
    parsed = understand_query(user_message)
    parsed_dislikes = set(parsed.get("dislikes", []))
    category = parsed.get("category") or _detect_category_from_text(normalized)
    if category:
        keywords.append(category)

    for priority in parsed.get("priorities", []):
        keywords.append(priority)
    for brand in parsed.get("preferred_brands", []):
        keywords.append(brand)
    for os_name in parsed.get("preferred_os", []):
        keywords.append(os_name)

    for priority, tokens in PRIORITY_KEYWORDS.items():
        if priority in parsed_dislikes:
            continue
        if any(_contains_alias(normalized, token) for token in tokens):
            keywords.append(priority)

    budget_value = parse_budget(user_message) if _has_budget_signal(normalized) else None
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

    return products[:80]


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
        "Sản phẩm đề xuất:",
        "Đơn vị giá: VND. Chỉ coi đây là dữ liệu nội bộ/demo nếu source là mini_catalog.",
        "Không bịa thêm mẫu sản phẩm, giá hoặc thông số ngoài danh sách này.",
    ]
    for index, product in enumerate(products, 1):
        name = product.get("name", "Unknown")
        currency = product.get("currency", "VND")
        description = _humanize_vi(product.get("description", ""))
        source = product.get("source", "")
        url = _source_url_for_item(product)

        line = f"{index}. {name} - {_display_vnd(product.get('price'))} {currency}"
        if description:
            line += f" - {description}"
        if source:
            line += f" - Nguồn: {source}"
        strengths = _list_summary(product.get("strengths"))
        weaknesses = _list_summary(product.get("weaknesses"))
        if strengths:
            line += f" - Điểm mạnh: {strengths}"
        if weaknesses:
            line += f" - Cần cân nhắc: {weaknesses}"
        line += f" - Thông số chính: {_spec_summary(product)}"
        line += f" - Link kiểm tra: {url}"
        lines.append(line)

    return "\n".join(lines)


def _budget_context_line(
    budget_min: Optional[float],
    budget_target: Optional[float],
    budget_max: Optional[float],
) -> str:
    if budget_min and budget_target and budget_max:
        return (
            "Vùng giá ưu tiên: "
            f"{_display_vnd(budget_min)} - {_display_vnd(budget_max)} "
            f"(mốc mong muốn khoảng {_display_vnd(budget_target)}). "
            "Ưu tiên sản phẩm trong vùng này; chỉ đưa sản phẩm rẻ hơn như lựa chọn tiết kiệm."
        )
    if budget_max:
        return f"Ngân sách tối đa: {_display_vnd(budget_max)}."
    return ""


def parse_budget(budget_str: str) -> Optional[float]:
    return parse_budget_to_vnd(budget_str)


def format_price(price: object) -> str:
    return format_vnd(price)


def _retrieve_products(user_message: str, session_id: str, db: Session) -> Dict:
    if not user_message or not user_message.strip():
        return {"candidates": []}
    if is_small_talk_message(user_message):
        return {"candidates": [], "answer_mode": "small_talk"}

    profile = db.query(CustomerProfile).filter(
        CustomerProfile.session_id == session_id
    ).first()

    parsed = understand_query(user_message)
    unlimited_budget = _has_unlimited_budget_signal(user_message)
    keywords = extract_product_keywords(user_message)
    direct_category = parsed.get("category") or _detect_category_from_text(normalize_text(user_message))
    preferred_category = profile.preferred_category if profile else None
    category = parsed.get("category") or _resolve_category(user_message, keywords, preferred_category)
    memory_priorities = _extract_priorities([], profile.priorities if profile else None)
    query_priorities = unique_preserve_order(
        [kw for kw in keywords if kw in PRIORITY_KEYWORDS]
        + parsed.get("priorities", [])
        + parsed.get("preferred_brands", [])
        + parsed.get("preferred_os", [])
    )
    priorities = _merge_turn_priorities(memory_priorities, query_priorities)
    explicit_preferred_brands = {
        item for item in parsed.get("preferred_brands", [])
        if isinstance(item, str) and item.startswith("brand:")
    }
    if explicit_preferred_brands:
        # A brand named in the current turn is a hard preference for this
        # retrieval pass. Keep older memory needs, but do not let an older
        # remembered brand compete with the brand the user just requested.
        priorities = [
            item for item in priorities
            if not (isinstance(item, str) and item.startswith("brand:"))
            or item in explicit_preferred_brands
        ]
    if unlimited_budget and "max_performance" not in priorities:
        priorities.append("max_performance")
    if (unlimited_budget or "max_performance" in parsed.get("priorities", [])) and not parsed.get("preferred_brands"):
        # A fresh "best possible / no budget limit" request should not be
        # constrained by an older remembered brand preference.
        priorities = [
            priority for priority in priorities
            if not str(priority).startswith("brand:")
            and priority not in {"value", "office", "student", "lightweight"}
        ]
    dislikes = _extract_dislikes(getattr(profile, "dislikes", None) if profile else None)
    recent_brand_dislikes = _extract_recent_brand_dislikes_for_alternative(
        user_message=user_message,
        session_id=session_id,
        db=db,
        category=category,
    )
    if explicit_preferred_brands:
        recent_brand_dislikes = [
            item for item in recent_brand_dislikes
            if item not in explicit_preferred_brands
        ]
    dislikes = unique_preserve_order(
        dislikes
        + _extract_inline_dislikes(user_message)
        + _extract_other_brand_dislikes(user_message)
        + recent_brand_dislikes
        + parsed.get("dislikes", [])
        + parsed.get("disliked_brands", [])
        + parsed.get("excluded_brands", [])
        + parsed.get("disliked_os", [])
    )
    priority_dislikes = {item for item in dislikes if item in PRIORITY_KEYWORDS}
    if priority_dislikes:
        priorities = [priority for priority in priorities if priority not in priority_dislikes]
    disliked_brand_priorities = {
        item for item in dislikes
        if isinstance(item, str) and item.startswith("brand:")
    }
    if disliked_brand_priorities:
        priorities = [
            priority for priority in priorities
            if priority not in disliked_brand_priorities
        ]

    parsed_budget = parsed.get("budget") or {}
    query_budget = (
        parsed_budget
        if parsed_budget.get("target") or parsed_budget.get("max")
        else _extract_budget_constraint(user_message)
    )
    memory_budget = _extract_budget_constraint(profile.budget if profile and profile.budget else "")
    if unlimited_budget:
        budget_constraint = {"min": None, "target": None, "max": None}
    else:
        if not (query_budget.get("target") or query_budget.get("max")) and _is_unrealistic_memory_budget(memory_budget, category):
            memory_budget = {"min": None, "target": None, "max": None}
        budget_constraint = query_budget if query_budget.get("target") or query_budget.get("max") else memory_budget
    budget_min = budget_constraint.get("min")
    budget_max = budget_constraint.get("max")
    budget_target = budget_constraint.get("target")

    if _needs_category_clarification(user_message, direct_category, preferred_category, priorities):
        return {
            "needs_clarification": True,
            "clarification": _build_category_clarification(budget_max, priorities),
            "candidates": [],
        }

    exact_product_names = _detect_exact_product_names(user_message, category)
    if not exact_product_names and not _is_alternative_request(user_message):
        exact_product_names = _resolve_contextual_product_names(user_message, session_id, db, category)
    exact_product_name = exact_product_names[0] if exact_product_names else None
    answer_mode = _answer_mode_from_query(user_message, priorities, exact_product_name, exact_product_names)

    products = search_product_database(keywords=keywords, budget_max=None, category=category)
    brand_products = _preferred_brand_product_pool(priorities, category)
    if brand_products:
        products = brand_products
    products = _drop_disliked_products(products, dislikes)
    if exact_product_names:
        products = _filter_exact_products(products, exact_product_names)
    else:
        products = _filter_products_to_preferred_brands_when_possible(products, priorities)
    products = _apply_context_scoring(products, keywords, category, priorities)
    candidates = _with_budget_status(products, budget_min, budget_max, budget_target)
    candidates = _filter_core_mismatches(candidates, priorities)
    candidates = _filter_to_preferred_brands_when_possible(candidates, priorities)
    if _is_alternative_request(user_message):
        candidates = _drop_recently_recommended_products(candidates, session_id, db)
    candidates.sort(
        key=lambda item: (
            item.get("budget_rank", 0),
            item.get("relevance_score", 0.0),
        ),
        reverse=True,
    )
    candidates = _visible_candidates(candidates, budget_min, budget_max)

    if _should_use_external_search(user_message, candidates):
        candidates.extend(_search_external_products(user_message, category, budget_max))

    candidates = _drop_unusable_candidates(candidates)
    candidates = _deduplicate_candidates(candidates)
    candidates = _filter_to_preferred_brands_when_possible(candidates, priorities)
    candidates.sort(
        key=lambda item: (
            item.get("budget_rank", 0),
            item.get("relevance_score", 0.0),
        ),
        reverse=True,
    )
    if answer_mode == "brand_constrained" and not _first_candidate_matches_preferred_brand(candidates, priorities):
        brand_candidates = _build_preferred_brand_candidates(
            priorities=priorities,
            keywords=keywords,
            category=category,
            dislikes=dislikes,
            budget_min=budget_min,
            budget_max=budget_max,
            budget_target=budget_target,
        )
        if brand_candidates:
            candidates = brand_candidates
    if answer_mode == "comparison" and exact_product_names:
        order = {normalize_text(name): index for index, name in enumerate(exact_product_names)}
        candidates.sort(key=lambda item: order.get(normalize_text(item.get("name")), len(order)))

    return {
        "type": "hybrid_product_context",
        "category": category,
        "budget_min": budget_min,
        "budget_max": budget_max,
        "budget_target": budget_target,
        "priorities": priorities,
        "answer_mode": answer_mode,
        "exact_product_name": exact_product_name,
        "exact_product_names": exact_product_names,
        "notice": "Internal catalog/Chroma is preferred. External results must be verified.",
        "candidates": candidates[:7],
    }


def _drop_unusable_candidates(candidates: List[Dict]) -> List[Dict]:
    unusable_sources = {"external_search_unavailable"}
    unusable_names = {"khong truy xuat duoc ket qua ngoai he thong"}
    kept = []
    for item in candidates:
        source = normalize_text(item.get("source"))
        name = normalize_text(item.get("name"))
        if source in unusable_sources or name in unusable_names:
            continue
        kept.append(item)
    return kept


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
                "brand": product.get("brand"),
                "year": product.get("year"),
                "price_segment": product.get("price_segment"),
                "spec_snapshot": product.get("spec_snapshot", {}),
                "specs": product.get("specs", {}),
                "best_for": product.get("best_for", []),
                "strengths": product.get("strengths", []),
                "weaknesses": product.get("weaknesses", []),
                "avoid_if": product.get("avoid_if", []),
                "decision_notes": product.get("decision_notes", {}),
                "detail_profile": product.get("detail_profile", {}),
                "comparison_profile": product.get("comparison_profile", {}),
                "last_updated": product.get("last_updated"),
                "data_confidence": product.get("data_confidence"),
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
    brand_category = _infer_category_from_brand(normalized)
    if brand_category:
        return brand_category

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
        for raw_item in str(profile_priorities or "").split(","):
            item = normalize_text(raw_item.strip())
            if item.startswith("brand:") or item.startswith("os:"):
                priorities.append(item)
            elif item in PRIORITY_KEYWORDS:
                priorities.append(item)
        for priority, tokens in PRIORITY_KEYWORDS.items():
            if any(token in normalized for token in tokens):
                priorities.append(priority)
    return unique_preserve_order(priorities)


def _merge_turn_priorities(memory_priorities: List[str], query_priorities: List[str]) -> List[str]:
    """Let explicit current-turn needs override older volatile memory needs.

    Brand and OS preferences are long-lived. Use-case needs such as gaming,
    camera, office, battery, or creator are more situational, so a fresh query
    with explicit needs should not keep injecting stale needs from prior turns.
    """

    current_need_priorities = {
        normalize_text(priority)
        for priority in query_priorities
        if normalize_text(priority) in VOLATILE_NEED_PRIORITIES
    }
    if not current_need_priorities:
        return unique_preserve_order(memory_priorities + query_priorities)

    stable_memory = [
        priority for priority in memory_priorities
        if normalize_text(priority) not in VOLATILE_NEED_PRIORITIES
    ]
    return unique_preserve_order(stable_memory + query_priorities)


def _extract_dislikes(profile_dislikes: Optional[str]) -> List[str]:
    dislikes = []
    for raw_item in str(profile_dislikes or "").split(","):
        item = normalize_text(raw_item.strip())
        if item and item not in STOPWORDS:
            dislikes.append(item)
    dislikes.extend(token for token in tokenize(profile_dislikes) if token not in STOPWORDS)
    return unique_preserve_order(dislikes)


def _extract_inline_dislikes(user_message: str) -> List[str]:
    normalized = normalize_text(user_message)
    if not normalized:
        return []

    dislike_markers = [
        "khong thich",
        "khong tich",
        "khong muon",
        "khong dung",
        "khong xai",
        "tranh",
        "ghet",
        "dislike",
        "avoid",
        "dont want",
        "don't want",
    ]
    if not any(marker in normalized for marker in dislike_markers):
        return []

    dislikes = []
    if any(_contains_alias(normalized, token) for token in ["iphone", "ios", "apple"]):
        dislikes.extend(["ios", "apple", "iphone", "brand:apple"])
    if any(_contains_alias(normalized, token) for token in ["macbook", "macos"]):
        dislikes.extend(["macos", "brand:apple", "macbook"])

    negative_phrases = []
    pattern = (
        r"(?:khong thich|khong tich|khong muon|khong dung|khong xai|tranh|ghet|dislike|avoid|dont want|don't want)"
        r"\s+((?:[a-z0-9]+\s*){1,5})"
    )
    for match in re.finditer(pattern, normalized):
        negative_phrases.append(match.group(1).strip())

    for phrase in negative_phrases:
        for brand, aliases in BRAND_PRIORITY_ALIASES.items():
            if any(_contains_alias(phrase, alias) for alias in aliases):
                dislikes.append(f"brand:{brand}")
        for priority, tokens in PRIORITY_KEYWORDS.items():
            if any(_contains_alias(phrase, token) for token in tokens):
                dislikes.append(priority)

    return unique_preserve_order(dislikes)


def _extract_other_brand_dislikes(user_message: str) -> List[str]:
    normalized = normalize_text(user_message)
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
        "doi hang",
        "doi thuong hieu",
    ]
    owned_signals = [
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
    has_other_signal = any(_contains_alias(normalized, signal) for signal in other_brand_signals)
    has_owned_signal = any(_contains_alias(normalized, signal) for signal in owned_signals)
    if not has_other_signal:
        return []

    dislikes = []
    for brand, aliases in BRAND_PRIORITY_ALIASES.items():
        if not any(_contains_alias(normalized, alias) for alias in aliases):
            continue
        direct_exclusion = any(
            _brand_alias_has_nearby_signal(normalized, alias, other_brand_signals)
            for alias in aliases
        )
        if direct_exclusion or has_owned_signal:
            dislikes.append(f"brand:{brand}")
    return unique_preserve_order(dislikes)


def _extract_recent_brand_dislikes_for_alternative(
    user_message: str,
    session_id: str,
    db: Session,
    category: Optional[str],
) -> List[str]:
    normalized = normalize_text(user_message)
    if not normalized or not _is_alternative_request(user_message):
        return []

    brand_change_signals = [
        "cac hang khac",
        "hang khac",
        "cac thuong hieu khac",
        "thuong hieu khac",
        "cac brand khac",
        "brand khac",
        "san pham cua hang khac",
        "san pham hang khac",
    ]
    if not any(_contains_alias(normalized, signal) for signal in brand_change_signals):
        return []

    disliked_brands = []
    for product_name in _recent_product_names(session_id, db, category=category, limit=8):
        brand = _brand_from_recent_product_name(product_name)
        if brand:
            disliked_brands.append(f"brand:{brand}")
    return unique_preserve_order(disliked_brands)


def _brand_from_recent_product_name(product_name: str) -> str:
    normalized_name = normalize_text(product_name)
    if not normalized_name:
        return ""

    for item in _load_mini_catalog():
        if normalize_text(item.get("name")) == normalized_name:
            catalog_brand = normalize_text(item.get("brand"))
            if catalog_brand:
                for brand, aliases in BRAND_PRIORITY_ALIASES.items():
                    if catalog_brand == brand or catalog_brand in aliases:
                        return brand
                return catalog_brand

    for brand, aliases in BRAND_PRIORITY_ALIASES.items():
        if any(_contains_alias(normalized_name, alias) for alias in aliases):
            return brand
    return ""


def _brand_alias_has_nearby_signal(normalized: str, alias: str, signals: List[str]) -> bool:
    tokens = normalized.split()
    alias_tokens = alias.split()
    if not tokens or not alias_tokens:
        return False

    for index in range(0, len(tokens) - len(alias_tokens) + 1):
        if tokens[index : index + len(alias_tokens)] != alias_tokens:
            continue
        left = max(0, index - 5)
        right = min(len(tokens), index + len(alias_tokens) + 5)
        window = " ".join(tokens[left:right])
        if any(_contains_alias(window, signal) for signal in signals):
            return True
    return False


def _drop_disliked_products(products: List[Dict], dislikes: List[str]) -> List[Dict]:
    if not dislikes:
        return products

    kept = []
    for product in products:
        haystack = _product_haystack(product)
        if any(_product_matches_dislike(product, dislike, haystack) for dislike in dislikes):
            continue
        kept.append(product)
    return kept


def _product_matches_dislike(product: Dict, dislike: str, haystack: Optional[str] = None) -> bool:
    normalized_dislike = normalize_text(dislike)
    if not normalized_dislike:
        return False

    haystack = haystack if haystack is not None else _product_haystack(product)
    brand = normalize_text(product.get("brand"))
    name = normalize_text(product.get("name"))

    if normalized_dislike in APPLE_PLATFORM_DISLIKES:
        return brand == "apple" or "iphone" in name or "ipad" in name or "macbook" in name
    if normalized_dislike.startswith("brand:"):
        disliked_brand = normalized_dislike.split(":", 1)[1]
        return _product_matches_brand(product, disliked_brand)
    if normalized_dislike.startswith("os:"):
        disliked_os = normalized_dislike.split(":", 1)[1]
        return _product_matches_os(product, disliked_os)
    if normalized_dislike in {"android", "windows", "macos"}:
        return _product_matches_os(product, normalized_dislike)
    if normalized_dislike in PRIORITY_KEYWORDS:
        # Attribute dislikes such as "khong can camera" are soft preferences.
        # Do not hard-filter products, because many good gaming/performance
        # phones also have camera tags. Brand/OS dislikes remain hard filters.
        return False

    return normalized_dislike in haystack


def _is_chinese_value_brand(product: Dict) -> bool:
    brand = normalize_text(product.get("brand"))
    name = normalize_text(product.get("name"))
    if brand in CHINESE_VALUE_BRANDS:
        return True
    return any(re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", name) for token in CHINESE_VALUE_BRANDS)


def _product_matches_brand(product: Dict, brand_name: str) -> bool:
    normalized_brand = normalize_text(brand_name)
    product_brand = normalize_text(product.get("brand"))
    name = normalize_text(product.get("name"))
    if product_brand == normalized_brand:
        return True
    aliases = BRAND_PRIORITY_ALIASES.get(normalized_brand, {normalized_brand})
    return any(_contains_alias(name, alias) for alias in aliases)


def _product_matches_os(product: Dict, os_name: str) -> bool:
    normalized_os = normalize_text(os_name)
    category = normalize_text(product.get("category"))
    brand = normalize_text(product.get("brand"))
    name = normalize_text(product.get("name"))
    haystack = _product_haystack(product)

    if normalized_os == "ios":
        return category == "phone" and (brand == "apple" or "iphone" in name)
    if normalized_os == "macos":
        return category == "laptop" and (brand == "apple" or "macbook" in name)
    if normalized_os == "android":
        return category == "phone" and not _product_matches_os(product, "ios")
    if normalized_os == "windows":
        return category == "laptop" and not _product_matches_os(product, "macos")
    return normalized_os in haystack


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
            elif priority.startswith("brand:") and _product_matches_brand(product, priority.split(":", 1)[1]):
                score += 3.0
            elif priority.startswith("os:") and _product_matches_os(product, priority.split(":", 1)[1]):
                score += 2.0
            elif priority in {"android", "ios", "windows", "macos"} and _product_matches_os(product, priority):
                score += 2.0
            elif priority == "china_brand" and _is_chinese_value_brand(product):
                score += 2.2
            elif any(token in haystack for token in PRIORITY_KEYWORDS.get(priority, set())):
                score += 0.5

        score += _core_need_alignment_score(tags, priorities)
        if "max_performance" in _priority_set(priorities):
            score += _max_performance_score(product)

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
            elif keyword in {"android", "ios", "windows", "macos"} and _product_matches_os(product, keyword):
                score += 2.0
            elif keyword == "china_brand" and _is_chinese_value_brand(product):
                score += 2.5
            elif any(token in haystack for token in PRIORITY_KEYWORDS[keyword]):
                score += 0.8
        elif keyword in haystack or keyword in tags:
            score += 0.7

    return score


def _core_need_alignment_score(tags: set, priorities: List[str]) -> float:
    """Reward products that match must-have needs and penalize mismatches."""

    priority_set = _priority_set(priorities)
    score = 0.0

    if "gaming" in priority_set:
        if tags & {"gaming", "performance"}:
            score += 3.0
        else:
            score -= 6.0
    if "performance" in priority_set:
        if tags & {"performance", "gaming", "premium"}:
            score += 2.0
        else:
            score -= 3.5
    if "battery" in priority_set:
        if "battery" in tags:
            score += 2.0
        else:
            score -= 2.0
    if "camera" in priority_set:
        if "camera" in tags:
            score += 2.0
        else:
            score -= 2.0
    if "display" in priority_set:
        if "display" in tags:
            score += 1.6
        else:
            score -= 1.0
    if "max_performance" in priority_set:
        if tags & {"gaming", "performance", "premium"}:
            score += 5.0
        else:
            score -= 8.0
        if "rtx" in tags:
            score += 3.0

    return score


def _priority_set(priorities: Iterable[str]) -> set:
    output = set()
    for priority in priorities or []:
        raw = str(priority)
        output.add(raw)
        output.add(normalize_text(raw))
        output.add(normalize_text(raw).replace(" ", "_"))
    return output


def _max_performance_score(product: Dict) -> float:
    name = normalize_text(product.get("name"))
    tags = {normalize_text(tag) for tag in product.get("tags", [])}
    score = 0.0
    if "rtx 5090" in name:
        score += 16.0
    elif "rtx 4080" in name:
        score += 13.0
    elif "rtx 4070" in name:
        score += 8.0
    elif "rtx 4060" in name:
        score += 3.0
    if "premium" in tags:
        score += 2.5
    if "display" in tags:
        score += 1.0
    if "value" in tags:
        score -= 2.0
    return score


def _extract_budget_constraint(text: object) -> Dict[str, Optional[float]]:
    normalized = normalize_text(text)
    empty = {"min": None, "target": None, "max": None}
    if not normalized:
        return empty
    if _has_unlimited_budget_signal(normalized):
        return empty
    if not _has_budget_signal(normalized):
        return empty

    range_bounds = _extract_explicit_budget_range(normalized)
    if range_bounds:
        lower, upper = range_bounds
        return {"min": lower, "target": (lower + upper) / 2, "max": upper}

    target = parse_budget(normalized)
    if not target:
        return empty

    margin = _extract_budget_margin(normalized)
    if margin:
        return {"min": max(0.0, target - margin), "target": target, "max": target + margin}

    max_value = _extract_flexible_max_budget(normalized, target)
    if max_value and max_value > target:
        lower = target * 0.75 if target >= 10_000_000 else None
        return {"min": lower, "target": target, "max": max_value}

    max_only_signals = {"duoi", "toi da", "khong qua", "under", "below", "less than"}
    around_signals = {"tam", "khoang", "khoang tam", "gan", "around", "about"}

    if any(signal in normalized for signal in max_only_signals):
        return {"min": None, "target": target, "max": target}
    if any(signal in normalized for signal in around_signals) or target >= 10_000_000:
        return {"min": target * 0.75, "target": target, "max": target * 1.25}

    return {"min": None, "target": target, "max": target}


def _is_unrealistic_memory_budget(
    budget_constraint: Dict[str, Optional[float]],
    category: Optional[str],
) -> bool:
    max_budget = budget_constraint.get("max") or budget_constraint.get("target")
    if not max_budget:
        return False
    if category == "laptop":
        return max_budget < 5_000_000
    if category == "phone":
        return max_budget < 2_000_000
    return False


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
        "k",
        "nghin",
        "ngan",
    ]
    return any(_contains_alias(normalized, signal) for signal in signals)


def _budget_bounds(
    user_message: str,
    memory_budget_text: str,
    budget_value: Optional[float],
) -> tuple[Optional[float], Optional[float]]:
    """Backward-compatible helper for older tests/callers."""

    constraint = _extract_budget_constraint(user_message or memory_budget_text)
    if constraint.get("min") or constraint.get("max"):
        return constraint.get("min"), constraint.get("max")
    if not budget_value:
        return None, None
    return None, budget_value


def _extract_explicit_budget_range(normalized: str) -> Optional[tuple[float, float]]:
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
            return (min(lower, upper), max(lower, upper))
    return None


def _infer_category_from_brand(normalized: str) -> Optional[str]:
    for category, brands in BRAND_CATEGORY_HINTS.items():
        for brand in brands:
            aliases = BRAND_PRIORITY_ALIASES.get(brand, {brand})
            if any(_contains_alias(normalized, alias) for alias in aliases):
                return category
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
        r"(?:tren duoi|cong tru|\+/-|±|chenh|lech|them|hon kem)\s*(\d+(?:[.,]\d+)?)\s*(trieu|tr|m|k|nghin|ngan)?",
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


def _with_budget_status(
    products: List[Dict],
    budget_min: Optional[float],
    budget_max: Optional[float],
    budget_target: Optional[float],
) -> List[Dict]:
    output = []
    for product in products:
        item = dict(product)
        item["budget_status"], item["budget_rank"] = _budget_status(item, budget_min, budget_max)
        item["relevance_score"] = float(item.get("relevance_score", 0.0) or 0.0)
        item["relevance_score"] += _budget_fit_score(item, budget_min, budget_max, budget_target)
        output.append(item)
    return output


def _budget_status(
    product: Dict,
    budget_min: Optional[float],
    budget_max: Optional[float],
) -> tuple[str, int]:
    if not budget_max:
        return "unknown", 2

    try:
        price = float(product.get("price"))
    except (TypeError, ValueError):
        return "unknown", 1

    if price > budget_max:
        return "over_budget", 0
    if budget_min and price < budget_min:
        return "budget_saver", 1
    if price <= budget_max:
        return "fits", 3
    return "over_budget", 0


def _visible_candidates(
    candidates: List[Dict],
    budget_min: Optional[float],
    budget_max: Optional[float],
) -> List[Dict]:
    if not budget_max:
        return candidates[:5]

    fits = [item for item in candidates if item.get("budget_status") == "fits"]
    budget_saver = [item for item in candidates if item.get("budget_status") == "budget_saver"]
    unknown = [item for item in candidates if item.get("budget_status") == "unknown"]

    if fits:
        # Prefer the requested price band. Do not pad the answer with much
        # cheaper "budget saver" products when enough in-band choices exist.
        return fits[:6]
    if budget_saver:
        return (budget_saver + unknown)[:5]
    return unknown[:3]


def _filter_core_mismatches(candidates: List[Dict], priorities: List[str]) -> List[Dict]:
    """Keep products that satisfy the main use case when enough exist."""

    priority_set = {normalize_text(priority) for priority in priorities}
    if not ({"gaming", "performance"} & priority_set):
        return candidates

    aligned = []
    for item in candidates:
        tags = {normalize_text(tag) for tag in item.get("tags", [])}
        if tags & {"gaming", "performance"}:
            aligned.append(item)

    visible_aligned = [
        item for item in aligned
        if item.get("budget_status") in {"fits", "budget_saver", "unknown"}
    ]
    return aligned if len(visible_aligned) >= 2 else candidates


def _filter_to_preferred_brands_when_possible(
    candidates: List[Dict],
    priorities: List[str],
) -> List[Dict]:
    preferred_brands = [
        priority.split(":", 1)[1]
        for priority in priorities
        if isinstance(priority, str) and priority.startswith("brand:")
    ]
    if not preferred_brands:
        return candidates

    preferred = [
        item
        for item in candidates
        if any(_product_matches_brand(item, brand) for brand in preferred_brands)
    ]
    visible_preferred = [
        item for item in preferred
        if item.get("budget_status") in {"fits", "budget_saver", "unknown"}
    ]
    return preferred if visible_preferred else candidates


def _filter_products_to_preferred_brands_when_possible(
    products: List[Dict],
    priorities: List[str],
) -> List[Dict]:
    preferred_brands = [
        priority.split(":", 1)[1]
        for priority in priorities
        if isinstance(priority, str) and priority.startswith("brand:")
    ]
    if not preferred_brands:
        return products

    preferred = [
        item
        for item in products
        if any(_product_matches_brand(item, brand) for brand in preferred_brands)
    ]
    return preferred or products


def _preferred_brand_product_pool(
    priorities: List[str],
    category: Optional[str],
) -> List[Dict]:
    preferred_brands = [
        priority.split(":", 1)[1]
        for priority in priorities
        if isinstance(priority, str) and priority.startswith("brand:")
    ]
    if not preferred_brands:
        return []

    products = []
    for item in _load_mini_catalog():
        if category and normalize_text(item.get("category")) != category:
            continue
        if any(_product_matches_brand(item, brand) for brand in preferred_brands):
            product = dict(item)
            product["relevance_score"] = 0.0
            products.append(product)
    return _normalize_product_records(products)


def _first_candidate_matches_preferred_brand(candidates: List[Dict], priorities: List[str]) -> bool:
    preferred_brands = [
        priority.split(":", 1)[1]
        for priority in priorities
        if isinstance(priority, str) and priority.startswith("brand:")
    ]
    if not preferred_brands:
        return True
    if not candidates:
        return False
    return any(_product_matches_brand(candidates[0], brand) for brand in preferred_brands)


def _build_preferred_brand_candidates(
    priorities: List[str],
    keywords: List[str],
    category: Optional[str],
    dislikes: List[str],
    budget_min: Optional[float],
    budget_max: Optional[float],
    budget_target: Optional[float],
) -> List[Dict]:
    products = _preferred_brand_product_pool(priorities, category)
    if not products:
        return []
    products = _drop_disliked_products(products, dislikes)
    products = _apply_context_scoring(products, keywords, category, priorities)
    candidates = _with_budget_status(products, budget_min, budget_max, budget_target)
    candidates.sort(
        key=lambda item: (
            item.get("budget_rank", 0),
            item.get("relevance_score", 0.0),
        ),
        reverse=True,
    )
    return _visible_candidates(candidates, budget_min, budget_max)


def _budget_fit_score(
    product: Dict,
    budget_min: Optional[float],
    budget_max: Optional[float],
    budget_target: Optional[float],
) -> float:
    """Prefer products inside and near the requested budget band."""

    if not budget_max:
        return 0.0

    try:
        price = float(product.get("price"))
    except (TypeError, ValueError):
        return 0.0

    if price <= 0 or price > budget_max:
        return 0.0

    tags = {normalize_text(tag) for tag in product.get("tags", [])}
    score = 0.0

    if budget_min and price < budget_min:
        score -= min((budget_min - price) / budget_min, 1.0) * 5.0
    else:
        score += 2.0

    if budget_target:
        closeness = 1.0 - min(abs(price - budget_target) / max(budget_target, 1.0), 1.0)
        score += closeness * 4.0
        target_ratio = min(price / budget_target, 1.25)
        if budget_target >= 15_000_000 and price < budget_target * 0.75:
            shortfall = (budget_target * 0.75 - price) / (budget_target * 0.75)
            score -= 2.5 + min(shortfall, 1.0) * 8.0
    else:
        target_ratio = min(price / budget_max, 1.0)
        score += target_ratio * 2.8

    if "gaming" in tags or "performance" in tags:
        score += target_ratio * 0.8
    if "gaming" in tags:
        score += 0.8
    if budget_max >= 20_000_000 and "premium" in tags:
        score += target_ratio * 0.8

    return score


def _is_alternative_request(user_message: str) -> bool:
    normalized = normalize_text(user_message)
    signals = [
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
        "cac brand khac",
        "brand khac",
        "ngoai",
        "tot hon",
        "cao cap hon",
        "xung dang hon",
    ]
    return any(signal in normalized for signal in signals)


def _drop_recently_recommended_products(
    candidates: List[Dict],
    session_id: str,
    db: Session,
) -> List[Dict]:
    names = _recently_recommended_product_names(session_id, db)
    if not names:
        return candidates

    kept = []
    for item in candidates:
        item_name = normalize_text(item.get("name"))
        if item_name and item_name in names:
            continue
        kept.append(item)

    original_fits = [item for item in candidates if item.get("budget_status") == "fits"]
    kept_fits = [item for item in kept if item.get("budget_status") == "fits"]
    if original_fits and not kept_fits:
        if len(original_fits) > 1:
            return original_fits[1:] + original_fits[:1]
        return original_fits

    return kept or candidates


def _recently_recommended_product_names(session_id: str, db: Session) -> set:
    return {normalize_text(name) for name in _recent_product_names(session_id, db, category=None, limit=4)}


def _recent_product_names(
    session_id: str,
    db: Session,
    category: Optional[str],
    limit: int = 4,
) -> List[str]:
    try:
        conversation = (
            db.query(Conversation)
            .filter(Conversation.session_id == session_id)
            .first()
        )
        if not conversation:
            return set()
        message_query = (
            db.query(Message)
            .filter(Message.conversation_id == conversation.id)
            .filter(Message.role == "assistant")
        )
        try:
            message_query = message_query.order_by(Message.id.desc())
        except Exception:
            pass
        messages = message_query.limit(limit).all()
    except Exception:
        return []

    catalog_items = [
        item for item in _load_mini_catalog()
        if not category or normalize_text(item.get("category")) == category
    ]
    catalog_names = [(normalize_text(item.get("name")), item.get("name")) for item in catalog_items]
    found = []
    for message in messages:
        content = normalize_text(getattr(message, "content", ""))
        for normalized_name, display_name in catalog_names:
            name = normalized_name
            if name and name in content:
                found.append(display_name)
    return unique_preserve_order(found)


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
        return []

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

def _build_external_query(user_message: str, category: Optional[str], budget_max: Optional[float]) -> str:
    budget_text = f" duoi {format_vnd(budget_max)}" if budget_max else ""
    category_text = category or "san pham"
    return f"{category_text} {user_message}{budget_text} gia danh gia 2025 2026 Viet Nam"


def _detect_exact_product_name(user_message: str, category: Optional[str]) -> Optional[str]:
    names = _detect_exact_product_names(user_message, category)
    return names[0] if names else None


def _detect_exact_product_names(user_message: str, category: Optional[str]) -> List[str]:
    normalized = normalize_text(user_message)
    if not normalized:
        return []

    exact_signals = [
        "danh gia",
        "review",
        "chi tiet",
        "thong tin",
        "co nen mua",
        "san pham nay",
        "mau nay",
        "con nay",
        "ve",
        "so sanh",
        "nen chon",
        "khac gi",
        "vs",
    ]
    has_exact_signal = any(_contains_alias(normalized, signal) for signal in exact_signals)

    matches = []
    for item in _load_mini_catalog():
        if category and normalize_text(item.get("category")) != category:
            continue
        name = normalize_text(item.get("name"))
        if name and _contains_alias(normalized, name):
            matches.append(item.get("name"))

    if not matches:
        matches = _detect_partial_product_names(user_message, category, has_exact_signal)

    matches = unique_preserve_order(matches)
    if len(matches) >= 2:
        return sorted(matches, key=lambda name: normalized.find(normalize_text(name)))
    if len(matches) == 1:
        return matches
    if matches and has_exact_signal:
        return [max(matches, key=lambda name: len(normalize_text(name)))]
    return []


def _detect_partial_product_names(
    user_message: str,
    category: Optional[str],
    has_exact_signal: bool,
) -> List[str]:
    normalized = normalize_text(user_message)
    if not normalized:
        return []

    # Partial resolution is only for product-specific questions. For broad
    # recommendations, partial names like "Lenovo" should remain brand filters.
    if not has_exact_signal and not _is_comparison_request(user_message):
        return []

    query_tokens = {
        token for token in tokenize(normalized)
        if token not in STOPWORDS and (len(token) >= 2 or re.search(r"\d", token))
    }
    query_numeric_tokens = {token for token in query_tokens if re.search(r"\d", token)}
    if not query_tokens:
        return []

    scored = []
    for item in _load_mini_catalog():
        if category and normalize_text(item.get("category")) != category:
            continue
        name = normalize_text(item.get("name"))
        name_tokens = [
            token for token in tokenize(name)
            if token not in STOPWORDS and (len(token) >= 2 or re.search(r"\d", token))
        ]
        if not name_tokens:
            continue
        if query_numeric_tokens and not query_numeric_tokens.issubset(set(name_tokens)):
            continue
        overlap = [token for token in name_tokens if token in query_tokens]
        if len(overlap) < 2:
            continue

        # Important model markers such as RTX 4070 or Pro 5 should carry more
        # weight than generic brand tokens.
        weighted = 0
        for token in overlap:
            weighted += 2 if re.search(r"\d", token) or token in {"pro", "ultra", "rtx", "loq", "legion", "rog"} else 1
        coverage = len(overlap) / max(len(name_tokens), 1)
        score = weighted + coverage
        if score >= 3.0:
            scored.append((score, len(name), item.get("name")))

    if not scored:
        return []
    scored.sort(reverse=True)
    best_score = scored[0][0]
    return [name for score, _length, name in scored if score >= best_score - 0.5][:3]


def _resolve_contextual_product_names(
    user_message: str,
    session_id: str,
    db: Session,
    category: Optional[str],
) -> List[str]:
    normalized = normalize_text(user_message)
    reference_signals = [
        "san pham tren",
        "mau tren",
        "may tren",
        "dien thoai tren",
        "laptop tren",
        "ban vua goi y",
        "ban da goi y",
        "mau do",
        "may do",
        "con do",
        "no",
        "cai nay",
        "mau nay",
        "san pham nay",
    ]
    if not any(_contains_alias(normalized, signal) for signal in reference_signals):
        return []

    recent = _recent_product_names(session_id, db, category=category, limit=6)
    return recent[:1]


def _filter_exact_product(products: List[Dict], product_name: str) -> List[Dict]:
    normalized_name = normalize_text(product_name)
    exact = [item for item in products if normalize_text(item.get("name")) == normalized_name]
    return exact or products


def _filter_exact_products(products: List[Dict], product_names: List[str]) -> List[Dict]:
    normalized_names = [normalize_text(name) for name in product_names]
    exact = []
    for name in normalized_names:
        exact.extend([item for item in products if normalize_text(item.get("name")) == name])
    return _deduplicate_candidates(exact) or products


def _answer_mode_from_query(
    user_message: str,
    priorities: List[str],
    exact_product_name: Optional[str],
    exact_product_names: Optional[List[str]] = None,
) -> str:
    if exact_product_names and len(exact_product_names) >= 2 and _is_comparison_request(user_message):
        return "comparison"
    if exact_product_name:
        normalized = normalize_text(user_message)
        if any(_contains_alias(normalized, signal) for signal in [
            "cau hinh",
            "thong so",
            "spec",
            "specs",
            "chi tiet",
            "phan tich chi tiet",
            "phan tich cau hinh",
            "manh o diem nao",
            "manh me o diem nao",
            "cau hinh chi tiet",
        ]):
            return "spec_detail"
        return "single_product"
    if any(priority.startswith("brand:") for priority in priorities if isinstance(priority, str)):
        return "brand_constrained"
    normalized = normalize_text(user_message)
    if any(_contains_alias(normalized, signal) for signal in ["mau nao", "goi y", "tu van", "lua chon"]):
        return "broad"
    return "focused"


def _is_comparison_request(user_message: str) -> bool:
    normalized = normalize_text(user_message)
    raw = str(user_message or "").lower()
    comparison_signals = [
        "so sanh",
        "so s nh",
        "so sánh",
        "khac gi",
        "kh c gi",
        "khác gì",
        "nen chon",
        "n n ch n",
        "nên chọn",
        "chon mau nao",
        "mau nao tot hon",
        "cai nao tot hon",
        "t t h n",
        "tốt hơn",
        "hay hon",
        "vs",
        "voi",
        "v i",
        "với",
    ]
    return (
        any(_contains_alias(normalized, normalize_text(signal)) for signal in comparison_signals)
        or any(signal in raw for signal in comparison_signals if any(ord(ch) > 127 for ch in signal))
    )


def _format_candidate_group(
    title: str,
    candidates: List[Dict],
    detailed_answer: bool,
    limit: int = 5,
) -> List[str]:
    lines = [f"\n{title}:"]
    for index, item in enumerate(candidates[:limit], 1):
        price = _display_vnd(item.get("price")) if item.get("price") is not None else "chưa rõ giá"
        description = _humanize_vi(item.get("description", ""))
        url = _source_url_for_item(item)
        if detailed_answer:
            lines.append(
                f"{index}. {item.get('name', 'Unknown')} - {price}\n"
                f"   - Hợp khi: {description}\n"
                f"   - Điểm đáng chú ý: {_list_summary(item.get('strengths'), fallback='khớp nhu cầu chính')}.\n"
                f"   - Cần cân nhắc: {_list_summary(item.get('weaknesses'), fallback='kiểm tra lại thông số theo phiên bản')}.\n"
                f"   - Nên kiểm tra thêm: {_verification_summary(item)}.\n"
                f"   - Link kiểm tra: {url}."
            )
        else:
            lines.append(
                f"{index}. {item.get('name', 'Unknown')} - {price}: {description}. "
                f"Điểm mạnh: {_list_summary(item.get('strengths'), fallback='khớp nhu cầu chính')}. "
                "Cần kiểm tra giá/cấu hình thực tế."
            )
    return lines


def _candidate_group_limit(answer_mode: str, query_tags: set) -> int:
    if answer_mode == "single_product":
        return 0
    if answer_mode == "brand_constrained":
        return 2
    if len(query_tags) >= 4:
        return 3
    return 5


def _format_best_pick(
    item: Dict,
    budget_max: Optional[float],
    query_tags: set,
) -> List[str]:
    price = _display_vnd(item.get("price")) if item.get("price") is not None else "chưa rõ giá"
    tags = {normalize_text(tag) for tag in item.get("tags", [])}
    reasons = []

    if budget_max and item.get("price") is not None:
        try:
            price_value = float(item.get("price"))
            if price_value <= budget_max:
                reasons.append(f"nằm trong ngân sách {_display_vnd(budget_max)}")
            elif price_value <= budget_max * 1.15:
                reasons.append("có thể chạm ngân sách nếu chọn cấu hình thấp hoặc săn sale")
        except (TypeError, ValueError):
            pass

    matched_tags = sorted((query_tags & tags) - {"phone", "laptop"})
    if matched_tags:
        reasons.append("khớp nhu cầu " + ", ".join(_tag_label(tag) for tag in matched_tags))

    if not reasons:
        reasons.append("có điểm phù hợp cao nhất trong dữ liệu hiện có")

    lines = [
        "",
        f"Mình sẽ ưu tiên: {item.get('name', 'Unknown')} - {price}",
        f"- Lý do chọn: {', '.join(reasons)}.",
        f"- Hợp nhất khi: {_humanize_vi(item.get('description', ''))}",
        f"- Điểm mạnh chính: {_strength_summary_for_query(item, query_tags)}.",
        f"- Đánh đổi cần biết: {_list_summary(item.get('weaknesses'), fallback='cần kiểm tra thêm theo nhu cầu thực tế')}.",
        f"- Không nên chọn nếu: {_avoid_summary(item, query_tags)}.",
        f"- Trước khi mua nên kiểm tra: {_verification_summary(item)}.",
        f"- Link kiểm tra nhanh: {_source_url_for_item(item)}",
    ]
    return lines


def _format_product_detail_answer(item: Dict, category: Optional[str]) -> str:
    name = item.get("name", "Sản phẩm")
    price = _display_vnd(item.get("price")) if item.get("price") is not None else "chưa rõ giá"
    detail = item.get("detail_profile") or {}
    configuration = detail.get("configuration") if isinstance(detail, dict) else {}
    performance = detail.get("performance_profile") if isinstance(detail, dict) else {}
    advice = detail.get("buying_advice") if isinstance(detail, dict) else {}

    lines = [
        f"{name} - cấu hình/thông tin chính:",
        "",
        f"- Giá tham khảo trong catalog: {price}.",
        f"- Vai trò sản phẩm: {_humanize_vi(detail.get('positioning') or item.get('description', ''))}",
    ]

    profile_config = configuration if isinstance(configuration, dict) else {}
    specs = item.get("specs") or {}
    if profile_config:
        lines.append("- Cấu hình/tiêu chí cần xem theo đúng phiên bản:")
        for key in _profile_config_keys_for_category(category):
            value = profile_config.get(key)
            if value:
                lines.append(f"  - {_spec_label(key)}: {_humanize_vi(value)}.")
    elif isinstance(specs, dict) and specs:
        lines.append("- Cấu hình cần kiểm tra:")
        for key in _spec_keys_for_category(category):
            value = specs.get(key)
            if value:
                lines.append(f"  - {_spec_label(key)}: {_humanize_vi(value)}.")
    else:
        lines.append("- Catalog hiện chưa có cấu hình chi tiết theo từng phiên bản.")

    if isinstance(performance, dict) and performance:
        lines.append("- Nhận xét theo nhu cầu:")
        for key, value in list(performance.items())[:5]:
            if value:
                lines.append(f"  - {_spec_label(key)}: {_humanize_vi(value)}.")

    if isinstance(advice, dict) and advice:
        choose_if = _list_summary(advice.get("choose_if"), fallback="")
        avoid_if = _list_summary(advice.get("avoid_if"), fallback="")
        verify = _list_summary(advice.get("verify"), fallback="")
        if choose_if:
            lines.append(f"- Nên chọn nếu: {choose_if}.")
        if avoid_if:
            lines.append(f"- Nên bỏ qua nếu: {avoid_if}.")
        if verify:
            lines.append(f"- Cần kiểm tra thêm: {verify}.")

    lines.extend(
        [
            f"- Điểm mạnh: {_list_summary(item.get('strengths'), fallback='phù hợp nhu cầu chính')}.",
            f"- Cần cân nhắc: {_list_summary(item.get('weaknesses'), fallback='kiểm tra đúng phiên bản trước khi mua')}.",
            f"- Link kiểm tra nhanh: {_source_url_for_item(item)}",
            "Lưu ý: catalog demo dùng để tư vấn và so sánh hướng mua; trước khi mua vẫn nên đối chiếu đúng mã cấu hình, giá và bảo hành tại cửa hàng.",
        ]
    )
    return "\n".join(lines)


def _format_comparison_answer(candidates: List[Dict], category: Optional[str], query_tags: set) -> str:
    items = candidates[:3]
    if len(items) < 2:
        return _format_product_detail_answer(items[0], category) if items else ""

    winner = _choose_comparison_winner(items, query_tags, category)
    priority_text = ", ".join(_tag_label(tag) for tag in sorted(query_tags)[:3]) or "nhu cầu tổng thể"
    winner_name = winner.get("name") if winner else items[0].get("name")

    lines = [
        f"Nếu xét theo {priority_text}, mình nghiêng về {winner_name}.",
        "Hai mẫu này không nên so kiểu chỉ nhìn giá, vì chúng thường phục vụ hơi khác nhau:",
    ]

    for item in items:
        price = _display_vnd(item.get("price")) if item.get("price") is not None else "chưa rõ giá"
        lines.append(
            f"- {item.get('name', 'Unknown')} ({price}): {_comparison_role_sentence(item, category, query_tags)}"
        )

    lines.append("Điểm khác biệt đáng chú ý:")
    for sentence in _comparison_takeaways(items, category, query_tags):
        lines.append(f"- {sentence}")

    if winner:
        lines.append(
            f"Kết luận: chọn {winner.get('name')} nếu bạn muốn phương án hợp nhất với {priority_text}. "
            "Chỉ đổi sang mẫu còn lại nếu các điểm mạnh riêng của nó quan trọng hơn với bạn."
        )

    lines.append(_checklist_for(category, query_tags))
    return "\n".join(lines)


def _comparison_role_sentence(item: Dict, category: Optional[str], query_tags: set) -> str:
    custom_role = _custom_comparison_role(item, category, query_tags)
    if custom_role:
        return custom_role

    detail = item.get("detail_profile") or {}
    role = _humanize_vi(detail.get("positioning") or item.get("description", ""))
    strengths = _strength_summary_for_query(item, query_tags)
    tradeoff = _list_summary(item.get("weaknesses"), fallback="cần kiểm tra đúng cấu hình và giá bán")
    return f"hợp khi {role}; điểm mạnh là {strengths}; đổi lại {tradeoff}."


def _custom_comparison_role(item: Dict, category: Optional[str], query_tags: set) -> str:
    if category != "laptop":
        return ""

    name = normalize_text(item.get("name"))
    tags = {normalize_text(tag) for tag in item.get("tags", [])}
    if "loq" in name and "rtx" in tags:
        return (
            "hợp hơn nếu bạn ưu tiên hiệu năng/giá, chơi game và tác vụ đồ họa trong ngân sách hợp lý; "
            "điểm cần kiểm tra là đúng GPU, TGP, RAM/SSD và chất lượng màn hình theo từng cấu hình."
        )
    if "zephyrus g14" in name:
        return (
            "hợp hơn nếu bạn muốn máy cao cấp, gọn hơn laptop gaming phổ thông và vẫn cần hiệu năng mạnh; "
            "đổi lại giá cao hơn, cấu hình GPU cụ thể và khả năng nâng cấp phải kiểm tra rất kỹ."
        )
    if "legion" in name:
        return (
            "hợp nếu bạn ưu tiên hiệu năng duy trì, tản nhiệt và trải nghiệm gaming nghiêm túc; "
            "đổi lại máy thường nặng hơn và pin không phải ưu tiên chính."
        )
    if "zenbook" in name or "yoga" in name or "x1 carbon" in name:
        return (
            "hợp nếu bạn ưu tiên mỏng nhẹ, pin và màn hình cho làm việc hằng ngày; "
            "không phải lựa chọn chính nếu mục tiêu là game nặng hoặc GPU mạnh."
        )
    return ""


def _comparison_takeaways(items: List[Dict], category: Optional[str], query_tags: set) -> List[str]:
    takeaways = []
    if len(items) < 2:
        return takeaways

    first, second = items[0], items[1]
    first_price = first.get("price")
    second_price = second.get("price")
    if first_price is not None and second_price is not None:
        try:
            gap = abs(float(first_price) - float(second_price))
            if gap >= 5_000_000:
                cheaper = first if float(first_price) < float(second_price) else second
                pricier = second if cheaper is first else first
                takeaways.append(
                    f"{cheaper.get('name')} có lợi thế giá; {pricier.get('name')} chỉ đáng trả thêm nếu bạn thật sự cần các điểm mạnh riêng của nó."
                )
        except (TypeError, ValueError):
            pass

    for criterion in _comparison_keys_for_category(category)[:4]:
        values = []
        for item in items[:2]:
            profile = item.get("comparison_profile") or {}
            value = profile.get(criterion)
            if value:
                values.append(f"{item.get('name')}: {_humanize_vi(value)}")
        if len(values) == 2:
            takeaways.append(f"{_spec_label(criterion)} - {values[0]}; {values[1]}.")

    if not takeaways:
        takeaways.append("Cả hai đều cần kiểm tra đúng cấu hình bán ra, vì cùng tên sản phẩm có thể có nhiều phiên bản.")
    return takeaways[:5]


def should_use_llm_grounded_rewrite(user_message: str, session_id: str, db: Session) -> bool:
    """
    Return True for product answers where template facts are useful but the
    final response needs natural reasoning, such as comparisons and deep dives.
    """

    if not settings.ENABLE_LLM_GROUNDED_REWRITE:
        return False
    retrieval = _retrieve_products(user_message, session_id, db)
    answer_mode = retrieval.get("answer_mode")
    if answer_mode == "comparison":
        # Comparisons must keep every named product and criterion. Local rewrite
        # models have sometimes collapsed the answer to one product, so the
        # grounded comparison renderer is safer for the demo.
        return False
    if answer_mode in {"spec_detail", "single_product"}:
        return True

    normalized = normalize_text(user_message)
    reasoning_signals = [
        "so sanh",
        "nen chon",
        "co nen mua",
        "danh gia",
        "khac gi",
        "tot hon",
        "phu hop hon",
        "phan tich",
    ]
    return any(_contains_alias(normalized, signal) for signal in reasoning_signals)


def _choose_comparison_winner(items: List[Dict], query_tags: set, category: Optional[str]) -> Optional[Dict]:
    if not items:
        return None

    def score(item: Dict) -> float:
        tags = {normalize_text(tag) for tag in item.get("tags", [])}
        name = normalize_text(item.get("name"))
        value = item.get("relevance_score", 0.0) or 0.0
        value += len(tags & query_tags) * 5
        if {"gaming", "creator", "performance"} & query_tags:
            if "rtx" in tags:
                value += 4
            if "rtx 4060" in name or "rtx 4070" in name:
                value += 3
            if "lightweight" in tags and "gaming" in query_tags:
                value -= 1
        price = item.get("price")
        if price is not None:
            try:
                price_value = float(price)
                if category == "phone" and price_value >= 15_000_000:
                    value += 1
                if category == "laptop" and price_value >= 18_000_000:
                    value += 1
                if "value" in tags and category == "laptop":
                    value += 2
            except (TypeError, ValueError):
                pass
        return value

    return max(items, key=score)


def _comparison_keys_for_category(category: Optional[str]) -> List[str]:
    if category == "phone":
        return ["performance", "gaming", "display", "battery", "camera", "software", "value", "risk"]
    if category == "laptop":
        return ["cpu", "gpu", "ram_storage", "display", "thermal", "portability_battery", "upgrade", "value"]
    return ["performance", "display", "battery", "value"]


def _profile_config_keys_for_category(category: Optional[str]) -> List[str]:
    if category == "phone":
        return ["chipset_tier", "ram_storage", "display", "battery_charging", "camera", "cooling", "software"]
    if category == "laptop":
        return ["cpu_class", "gpu_class", "ram", "storage", "display", "thermal", "portability", "battery", "upgrade_notes"]
    return []


def _spec_keys_for_category(category: Optional[str]) -> List[str]:
    if category == "phone":
        return ["chipset", "ram_storage", "screen", "battery", "camera", "software"]
    if category == "laptop":
        return ["cpu", "gpu", "ram", "storage", "screen", "portability", "battery"]
    return []


def _spec_label(key: str) -> str:
    labels = {
        "chipset": "Chipset",
        "ram_storage": "RAM/bộ nhớ",
        "screen": "Màn hình",
        "battery": "Pin",
        "camera": "Camera",
        "software": "Phần mềm",
        "cpu": "CPU",
        "gpu": "GPU",
        "ram": "RAM",
        "storage": "Lưu trữ",
        "portability": "Thiết kế/di động",
    }
    return labels.get(key, key)


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


def _list_summary(values: object, fallback: str = "") -> str:
    if not values:
        return _humanize_vi(fallback)
    if isinstance(values, str):
        return _humanize_vi(values)
    if isinstance(values, list):
        cleaned = [str(value).strip() for value in values if str(value).strip()]
        return _humanize_vi("; ".join(cleaned[:3]) if cleaned else fallback)
    return _humanize_vi(str(values))


def _strength_summary_for_query(item: Dict, query_tags: set) -> str:
    strengths = item.get("strengths")
    if not isinstance(strengths, list):
        return _list_summary(strengths, fallback="phù hợp nhất trong dữ liệu hiện có")

    filtered = []
    for strength in strengths:
        normalized = normalize_text(strength)
        if "camera" not in query_tags and any(token in normalized for token in ["camera", "chup anh", "quay video"]):
            continue
        filtered.append(strength)

    return _list_summary(filtered or strengths, fallback="phù hợp nhất trong dữ liệu hiện có")


def _spec_summary(item: Dict) -> str:
    snapshot = item.get("spec_snapshot") or {}
    if isinstance(snapshot, dict) and snapshot:
        category = normalize_text(item.get("category"))
        if category == "phone":
            keys = ["chipset", "ram", "storage", "display", "battery", "charging", "camera", "os"]
        elif category == "laptop":
            keys = ["cpu", "gpu", "ram", "storage", "display", "battery", "weight", "os"]
        else:
            keys = list(snapshot.keys())

        parts = []
        for key in keys:
            value = snapshot.get(key)
            if value:
                label = _spec_label(key)
                parts.append(f"{label}: {_humanize_vi(value)}")
        if parts:
            return "; ".join(parts[:6])

    specs = item.get("specs") or {}
    if not isinstance(specs, dict) or not specs:
        return "chưa có thông số chi tiết trong catalog demo"

    category = normalize_text(item.get("category"))
    if category == "phone":
        keys = ["chipset", "ram_storage", "screen", "battery", "camera", "software"]
    elif category == "laptop":
        keys = ["cpu", "gpu", "ram", "storage", "screen", "portability", "battery"]
    else:
        keys = list(specs.keys())

    parts = []
    for key in keys:
        value = specs.get(key)
        if value:
            label = _spec_label(key)
            parts.append(f"{label}: {_humanize_vi(value)}")
    return "; ".join(parts[:5]) if parts else "chưa có thông số chi tiết trong catalog demo"


def _spec_label(key: str) -> str:
    labels = {
        "ram_storage": "RAM/bộ nhớ",
        "chipset_tier": "Chip/hiệu năng",
        "battery_charging": "Pin/sạc",
        "cpu_class": "CPU",
        "gpu_class": "GPU",
        "thermal": "Tản nhiệt/độ ồn",
        "upgrade_notes": "Khả năng nâng cấp",
        "performance": "Hiệu năng",
        "gaming": "Chơi game",
        "office": "Văn phòng",
        "creator": "Đồ họa/sáng tạo",
        "coding": "Lập trình",
        "value": "Giá trị/giá bán",
        "risk": "Điểm cần kiểm tra",
        "portability_battery": "Di động/pin",
        "upgrade": "Nâng cấp",
        "cpu": "CPU",
        "gpu": "GPU",
        "ram": "RAM",
        "storage": "Lưu trữ",
        "screen": "Màn hình",
        "display": "Màn hình",
        "battery": "Pin",
        "camera": "Camera",
        "software": "Phần mềm",
        "chipset": "Chipset",
        "charging": "Sạc",
        "os": "Hệ điều hành",
        "weight": "Cân nặng",
        "portability": "Tính di động",
    }
    return labels.get(key, key.replace("_", " "))


def _verification_summary(item: Dict) -> str:
    notes = item.get("decision_notes") or {}
    if isinstance(notes, dict):
        values = notes.get("verify_before_buying")
        if values:
            return _list_summary(values)
    return "giá hiện tại; cấu hình đúng mã; bảo hành"


def _humanize_vi(value: object) -> str:
    """Make no-accent demo catalog text more readable in Vietnamese answers."""

    text = str(value or "")
    if not text:
        return ""

    replacements = {
        "Dien thoai": "Điện thoại",
        "dien thoai": "điện thoại",
        "Laptop": "Laptop",
        "duoi": "dưới",
        "trieu": "triệu",
        "gia": "giá",
        "may tinh": "máy tính",
        "may": "máy",
        "man hinh": "màn hình",
        "hieu nang": "hiệu năng",
        "choi game": "chơi game",
        "chup anh": "chụp ảnh",
        "chup hinh": "chụp hình",
        "pin tot": "pin tốt",
        "pin lau": "pin lâu",
        "pin trau": "pin trâu",
        "pin lon": "pin lớn",
        "tam gia": "tầm giá",
        "gia tot": "giá tốt",
        "gia re": "giá rẻ",
        "giá re": "giá rẻ",
        "gia hien tai": "giá hiện tại",
        "gia/cau hinh": "giá/cấu hình",
        "cau hinh": "cấu hình",
        "phu hop": "phù hợp",
        "phu hợp": "phù hợp",
        "can bang": "cân bằng",
        "can kiem tra": "cần kiểm tra",
        "can": "cần",
        "hop nhu cau": "hợp nhu cầu",
        "giua": "giữa",
        "vua": "vừa",
        "dung hang ngay": "dùng hằng ngày",
        "dung lượng": "dung lượng",
        "dung luong": "dung lượng",
        "dung ma": "đúng mã",
        "dùng ma": "đúng mã",
        "dung": "dùng",
        "hang ngay": "hằng ngày",
        "hoc tap": "học tập",
        "van phong": "văn phòng",
        "cong viec": "công việc",
        "co ban": "cơ bản",
        "luot web": "lướt web",
        "giai tri nhe": "giải trí nhẹ",
        "giai tri": "giải trí",
        "online meeting": "họp online",
        "do hoa": "đồ họa",
        "lap trinh": "lập trình",
        "render nang": "render nặng",
        "game nang": "game nặng",
        "GPU nhieu": "GPU nhiều",
        "gpu nhieu": "GPU nhiều",
        "nhom tam trung/pho thong": "nhóm tầm trung/phổ thông",
        "nhom flagship/cao cap": "nhóm flagship/cao cấp",
        "nhom flagship": "nhóm flagship",
        "tam trung": "tầm trung",
        "pho thong": "phổ thông",
        "phan mem": "phần mềm",
        "he sinh thai": "hệ sinh thái",
        "trong tam": "trong tầm",
        "phan khuc": "phân khúc",
        "cap nhat": "cập nhật",
        "la loi the": "là lợi thế",
        "loi the": "lợi thế",
        "nho gon": "nhỏ gọn",
        "cao cap": "cao cấp",
        "cac mau": "các mẫu",
        "thich": "thích",
        "gon": "gọn",
        "hon": "hơn",
        "lon": "lớn",
        "hoac": "hoặc",
        "toi uu": "tối ưu",
        "khong phai": "không phải",
        "khong": "không",
        "uu tien": "ưu tiên",
        "lua chon": "lựa chọn",
        "tot nhat": "tốt nhất",
        "nhat": "nhất",
        "de dung": "dễ dùng",
        "de dùng": "dễ dùng",
        "de mang theo": "dễ mang theo",
        "hieu nang tho": "hiệu năng thô",
        "hiệu năng tho": "hiệu năng thô",
        "ly tuong": "lý tưởng",
        "yeu cau": "yêu cầu",
        "thap hon": "thấp hơn",
        "tich hop": "tích hợp",
        "tiet kiem dien": "tiết kiệm điện",
        "dong": "dòng",
        "tuong duong": "tương đương",
        "nen": "nên",
        "tro len": "trở lên",
        "tuy nhu cau": "tùy nhu cầu",
        "kha nang": "khả năng",
        "nang cap": "nâng cấp",
        "can nang": "cân nặng",
        "do co dong": "độ cơ động",
        "tac vu": "tác vụ",
        "se hao pin nhanh hon": "sẽ hao pin nhanh hơn",
        "performance": "hiệu năng",
        "performace": "hiệu năng",
        "tan so quet": "tần số quét",
        "phu thuoc": "phụ thuộc",
        "cach dung": "cách dùng",
        "thien camera": "thiên camera",
        "thien hieu nang": "thiên hiệu năng",
        "thien gaming": "thiên gaming",
        "thien value": "thiên value",
        "thien": "thiên",
        "tot": "tốt",
        "so voi": "so với",
        "kem": "kém",
        "trai nghiem": "trải nghiệm",
        "hien thi": "hiển thị",
        "nhiet do": "nhiệt độ",
        "duy tri": "duy trì",
        "tai nang": "tải nặng",
        "co the": "có thể",
        "cao nhat": "cao nhất",
        "tren moi dong": "trên mọi dòng",
        "chu yeu": "chủ yếu",
        "ban": "bạn",
        "dep": "đẹp",
        "hon la": "hơn là",
        "gaming nang": "gaming nặng",
        "gia tri": "giá trị",
        "chinh hang": "chính hãng",
        "nguoi": "người",
        "muon": "muốn",
        "on dinh": "ổn định",
        "mong nhe": "mỏng nhẹ",
        "tan nhiet": "tản nhiệt",
        "bao hanh": "bảo hành",
        "bo nho": "bộ nhớ",
        "phien ban": "phiên bản",
        "kiem tra": "kiểm tra",
        "camera la diem manh": "camera là điểm mạnh",
        "pin la diem manh": "pin là điểm mạnh",
        "diem manh": "điểm mạnh",
        "diem chinh": "điểm chính",
        "danh doi": "đánh đổi",
        "ho tro": "hỗ trợ",
        "mau sac": "màu sắc",
        "mau san pham": "mẫu sản phẩm",
        "cac mau": "các mẫu",
        "mau": "mẫu",
        "gpu roi": "GPU rời",
        "roi": "rời",
        "sac nhanh": "sạc nhanh",
        "sac": "sạc",
        "rat": "rất",
        "lam viec": "làm việc",
        "nhu cau": "nhu cầu",
        "manh": "mạnh",
        "hieu nang nang": "hiệu năng cao",
        "nang": "nặng",
        "mang theo": "mang theo",
        "nhe": "nhẹ",
        "nguon hang": "nguồn hàng",
        "nguon": "nguồn",
        "day": "dày",
        "screen": "màn hình",
        "battery": "pin",
        "software": "phần mềm",
        "storage": "lưu trữ",
        "portability": "tính di động",
    }
    for raw, pretty in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        text = re.sub(rf"(?<![A-Za-z0-9]){re.escape(raw)}(?![A-Za-z0-9])", pretty, text)
    text = text.replace(" va ", " và ")
    return text


def _display_vnd(value: object) -> str:
    return _humanize_vi(format_vnd(value))


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
    avoid_if = item.get("avoid_if")
    if avoid_if:
        return _list_summary(avoid_if)

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
        return "mạnh cho game, kỹ thuật và tác vụ đồ họa/video"
    if "gaming" in tags:
        return "ưu tiên chơi game/hiệu năng"
    if "creator" in tags:
        return "ưu tiên đồ họa, dựng video, render hoặc sáng tạo nội dung"
    if "office" in tags:
        return "ưu tiên văn phòng, học tập, họp online, pin và tính ổn định"
    if "camera" in tags:
        return "ưu tiên camera và trải nghiệm cân bằng"
    if "battery" in tags:
        return "ưu tiên pin và tính ổn định"
    return "phương án cân bằng"


def _answer_heading(category: Optional[str], tags: set) -> str:
    if category == "phone":
        return "Một vài điện thoại đáng cân nhắc"
    if category == "laptop" and "creator" in tags:
        return "Một vài laptop cho tác vụ nặng/sáng tạo nội dung đáng cân nhắc"
    if category == "laptop" and "gaming" in tags:
        return "Một vài laptop gaming đáng cân nhắc"
    if category == "laptop":
        return "Một vài laptop đáng cân nhắc"
    return "Một vài lựa chọn đáng cân nhắc"


def _checklist_for(category: Optional[str], tags: set) -> str:
    if category == "laptop" and "creator" in tags:
        return (
            "Checklist: CPU đủ mạnh, RAM 16GB+ hoặc 32GB nếu làm nặng, SSD 512GB-1TB, "
            "GPU rời nếu dựng video/3D, màn hình đúng nhu cầu màu sắc và bảo hành."
        )
    if category == "laptop" and "office" in tags and "gaming" not in tags:
        return "Checklist: pin, cân nặng, độ mượt khi mở nhiều tab/Office, RAM 16GB nếu dùng lâu dài, bàn phím và bảo hành."
    if category == "laptop":
        return "Checklist: CPU/GPU đúng cấu hình, RAM 16GB+, SSD 512GB+, tản nhiệt, màn hình và bảo hành."
    if category == "phone":
        return "Checklist: chipset, RAM/bộ nhớ, tản nhiệt, pin, bảo hành và giá hiện tại."
    return "Checklist: giá hiện tại, nguồn bán, bảo hành, thông số chính và độ phù hợp nhu cầu."


def _tag_label(tag: str) -> str:
    labels = {
        "gaming": "chơi game",
        "camera": "camera/chụp ảnh",
        "display": "màn hình",
        "battery": "pin",
        "performance": "hiệu năng",
        "value": "giá/hiệu năng",
        "creator": "tác vụ nặng/sáng tạo",
        "office": "văn phòng",
        "coding": "lập trình",
        "ram": "RAM/đa nhiệm",
        "storage": "lưu trữ",
        "cooling": "tản nhiệt",
        "lightweight": "mỏng nhẹ",
        "software": "phần mềm/cập nhật",
        "premium": "trải nghiệm cao cấp",
        "build_quality": "hoàn thiện",
        "warranty": "bảo hành",
    }
    return labels.get(normalize_text(tag), _humanize_vi(tag))


def _product_haystack(product: Dict) -> str:
    tags = " ".join(str(tag) for tag in product.get("tags", []))
    best_for = " ".join(str(item) for item in product.get("best_for", []))
    strengths = " ".join(str(item) for item in product.get("strengths", []))
    weaknesses = " ".join(str(item) for item in product.get("weaknesses", []))
    avoid_if = " ".join(str(item) for item in product.get("avoid_if", []))
    specs = product.get("specs") or {}
    specs_text = " ".join(str(value) for value in specs.values()) if isinstance(specs, dict) else str(specs)
    snapshot = product.get("spec_snapshot") or {}
    snapshot_text = " ".join(str(value) for value in snapshot.values()) if isinstance(snapshot, dict) else str(snapshot)
    return normalize_text(
        f"{product.get('name', '')} {product.get('description', '')} "
        f"{product.get('category', '')} {product.get('brand', '')} "
        f"{tags} {best_for} {strengths} {weaknesses} {avoid_if} {specs_text} {snapshot_text}"
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
