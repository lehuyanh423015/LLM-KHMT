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
from services.data_normalization import (
    format_vnd,
    normalize_text,
    parse_budget_to_vnd,
    tokenize,
    unique_preserve_order,
)
from services.query_understanding_service import understand_query
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
    "durable": {"ben", "durable", "chac"},
    "build_quality": {"build", "vo kim loai", "hoan thien", "chat lieu", "cao cap"},
    "warranty": {"bao hanh", "chinh hang", "hau mai", "bao tri"},
    "software": {"phan mem", "cap nhat", "on dinh", "he sinh thai"},
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

    retrieval = _retrieve_products(user_message, session_id, db)
    if retrieval.get("needs_clarification"):
        return retrieval.get("clarification", "")

    candidates = retrieval.get("candidates", [])
    if not candidates:
        return ""

    category = retrieval.get("category") or candidates[0].get("category")
    budget_target = retrieval.get("budget_target")
    budget_max = retrieval.get("budget_max")
    query_tags = set(retrieval.get("priorities", []))
    detailed_answer = True
    answer_mode = retrieval.get("answer_mode", "broad")
    group_limit = _candidate_group_limit(answer_mode, query_tags)

    lines = [_answer_heading(category, query_tags) + ":"]

    best_pick = candidates[0]
    lines.extend(_format_best_pick(best_pick, budget_target or budget_max, query_tags))

    if answer_mode == "single_product":
        lines.append(_checklist_for(category, query_tags))
        return "\n".join(lines)

    remaining = candidates[1:]
    fits = [item for item in remaining if item.get("budget_status") == "fits"]
    maybe = [item for item in remaining if item.get("budget_status") == "maybe"]
    unknown = [item for item in remaining if item.get("budget_status") == "unknown"]

    if budget_max and not fits and maybe:
        lines.append(
            f"Tôi chưa có mẫu nào chắc chắn dưới {_display_vnd(budget_max)} trong dữ liệu hiện có. "
            "Các mẫu sau có thể chạm ngân sách ở cấu hình thấp hoặc khi giảm giá."
        )

    if fits:
        lines.extend(_format_candidate_group("Phương án thay thế phù hợp ngân sách", fits, detailed_answer, group_limit))
    if maybe:
        lines.extend(_format_candidate_group("Có thể cân nhắc nếu săn sale/chọn cấu hình thấp", maybe, detailed_answer, group_limit))
    if unknown:
        lines.extend(_format_candidate_group("Ngoài hệ thống hoặc cần kiểm tra thêm", unknown, detailed_answer, group_limit))

    lines.append(_checklist_for(category, query_tags))
    return "\n".join(lines)


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

    profile = db.query(CustomerProfile).filter(
        CustomerProfile.session_id == session_id
    ).first()

    parsed = understand_query(user_message)
    keywords = extract_product_keywords(user_message)
    direct_category = parsed.get("category") or _detect_category_from_text(normalize_text(user_message))
    preferred_category = profile.preferred_category if profile else None
    category = parsed.get("category") or _resolve_category(user_message, keywords, preferred_category)
    priorities = _extract_priorities(keywords, profile.priorities if profile else None)
    priorities = unique_preserve_order(
        priorities
        + parsed.get("priorities", [])
        + parsed.get("preferred_brands", [])
        + parsed.get("preferred_os", [])
    )
    dislikes = _extract_dislikes(getattr(profile, "dislikes", None) if profile else None)
    dislikes = unique_preserve_order(
        dislikes
        + _extract_inline_dislikes(user_message)
        + parsed.get("dislikes", [])
        + parsed.get("disliked_brands", [])
        + parsed.get("disliked_os", [])
    )
    priority_dislikes = {item for item in dislikes if item in PRIORITY_KEYWORDS}
    if priority_dislikes:
        priorities = [priority for priority in priorities if priority not in priority_dislikes]

    parsed_budget = parsed.get("budget") or {}
    query_budget = (
        parsed_budget
        if parsed_budget.get("target") or parsed_budget.get("max")
        else _extract_budget_constraint(user_message)
    )
    memory_budget = _extract_budget_constraint(profile.budget if profile and profile.budget else "")
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

    exact_product_name = _detect_exact_product_name(user_message, category)
    answer_mode = _answer_mode_from_query(user_message, priorities, exact_product_name)

    products = search_product_database(keywords=keywords, budget_max=None, category=category)
    brand_products = _preferred_brand_product_pool(priorities, category)
    if brand_products:
        products = brand_products
    products = _drop_disliked_products(products, dislikes)
    if exact_product_name:
        products = _filter_exact_product(products, exact_product_name)
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

    return {
        "type": "hybrid_product_context",
        "category": category,
        "budget_min": budget_min,
        "budget_max": budget_max,
        "budget_target": budget_target,
        "priorities": priorities,
        "answer_mode": answer_mode,
        "exact_product_name": exact_product_name,
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
                "specs": product.get("specs", {}),
                "best_for": product.get("best_for", []),
                "strengths": product.get("strengths", []),
                "weaknesses": product.get("weaknesses", []),
                "avoid_if": product.get("avoid_if", []),
                "decision_notes": product.get("decision_notes", {}),
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

    priority_set = {normalize_text(priority) for priority in priorities}
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

    return score


def _extract_budget_constraint(text: object) -> Dict[str, Optional[float]]:
    normalized = normalize_text(text)
    empty = {"min": None, "target": None, "max": None}
    if not normalized:
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
        # Prefer the requested price band. Add at most one cheaper option as a
        # budget-saving alternative instead of flooding recommendations with
        # much cheaper products.
        return (fits[:5] + budget_saver[:1] + unknown[:1])[:6]
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
    try:
        conversation = (
            db.query(Conversation)
            .filter(Conversation.session_id == session_id)
            .first()
        )
        if not conversation:
            return set()
        messages = (
            db.query(Message)
            .filter(Message.conversation_id == conversation.id)
            .filter(Message.role == "assistant")
            .order_by(Message.id.desc())
            .limit(4)
            .all()
        )
    except Exception:
        return set()

    catalog_names = {normalize_text(item.get("name")) for item in _load_mini_catalog()}
    found = set()
    for message in messages:
        content = normalize_text(getattr(message, "content", ""))
        for name in catalog_names:
            if name and name in content:
                found.add(name)
    return found


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
    normalized = normalize_text(user_message)
    if not normalized:
        return None

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
    ]
    has_exact_signal = any(_contains_alias(normalized, signal) for signal in exact_signals)

    matches = []
    for item in _load_mini_catalog():
        if category and normalize_text(item.get("category")) != category:
            continue
        name = normalize_text(item.get("name"))
        if name and _contains_alias(normalized, name):
            matches.append(item.get("name"))

    if len(matches) == 1:
        return matches[0]
    if matches and has_exact_signal:
        return max(matches, key=lambda name: len(normalize_text(name)))
    return None


def _filter_exact_product(products: List[Dict], product_name: str) -> List[Dict]:
    normalized_name = normalize_text(product_name)
    exact = [item for item in products if normalize_text(item.get("name")) == normalized_name]
    return exact or products


def _answer_mode_from_query(
    user_message: str,
    priorities: List[str],
    exact_product_name: Optional[str],
) -> str:
    if exact_product_name:
        return "single_product"
    if any(priority.startswith("brand:") for priority in priorities if isinstance(priority, str)):
        return "brand_constrained"
    normalized = normalize_text(user_message)
    if any(_contains_alias(normalized, signal) for signal in ["mau nao", "goi y", "tu van", "lua chon"]):
        return "broad"
    return "focused"


def _format_candidate_group(
    title: str,
    candidates: List[Dict],
    detailed_answer: bool,
    limit: int = 5,
) -> List[str]:
    lines = [f"\n{title}:"]
    for index, item in enumerate(candidates[:limit], 1):
        source = item.get("source", "product_search")
        price = _display_vnd(item.get("price")) if item.get("price") is not None else "chưa rõ giá"
        description = _humanize_vi(item.get("description", ""))
        url = _source_url_for_item(item)
        if detailed_answer:
            lines.append(
                f"{index}. {item.get('name', 'Unknown')} - {price} [{source}]\n"
                f"   - Hợp khi: {description}\n"
                f"   - Điểm đáng chú ý: {_list_summary(item.get('strengths'), fallback='khớp nhu cầu chính')}.\n"
                f"   - Cần cân nhắc: {_list_summary(item.get('weaknesses'), fallback='kiểm tra lại thông số theo phiên bản')}.\n"
                f"   - Nên kiểm tra thêm: {_verification_summary(item)}.\n"
                f"   - Link kiểm tra: {url}."
            )
        else:
            lines.append(
                f"{index}. {item.get('name', 'Unknown')} - {price} [{source}]: {description}. "
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
        "cpu": "CPU",
        "gpu": "GPU",
        "ram": "RAM",
        "storage": "lưu trữ",
        "screen": "màn hình",
        "battery": "pin",
        "camera": "camera",
        "software": "phần mềm",
        "chipset": "chipset",
        "portability": "tính di động",
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
    return normalize_text(
        f"{product.get('name', '')} {product.get('description', '')} "
        f"{product.get('category', '')} {product.get('brand', '')} "
        f"{tags} {best_for} {strengths} {weaknesses} {avoid_if} {specs_text}"
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
