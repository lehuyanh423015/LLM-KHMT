"""
Product Retrieval Service (Knowledge Base).

Stable interface used by the orchestrator:
    get_product_knowledge_context(user_message: str, session_id: str, db) -> str

This module owns product keyword extraction, product dataset retrieval, Chroma
retrieval when available, strict budget filtering, and LLM-ready formatting.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

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
    "laptop": {"laptop", "may tinh", "notebook"},
    "phone": {"dien thoai", "smartphone", "phone", "mobile"},
    "tablet": {"may tinh bang", "tablet", "ipad"},
    "mouse": {"chuot", "mouse"},
    "keyboard": {"ban phim", "keyboard"},
    "monitor": {"man hinh", "monitor"},
    "headphones": {"tai nghe", "headphone", "headphones", "earbud", "earbuds"},
}

PRIORITY_KEYWORDS = {
    "gaming": {"gaming", "choi game", "game", "chien game"},
    "battery": {"pin", "battery", "pin trau", "pin lau"},
    "camera": {"camera", "chup anh", "chup hinh"},
    "lightweight": {"nhe", "mong", "mong nhe", "gon", "lightweight"},
    "performance": {"hieu nang", "performance", "manh", "nhanh", "muot"},
    "durable": {"ben", "durable", "chac"},
    "value": {"re", "gia re", "value", "affordable", "hop ly"},
    "student": {"hoc tap", "sinh vien", "student", "van phong"},
}

STOPWORDS = {
    "a",
    "an",
    "and",
    "about",
    "around",
    "below",
    "budget",
    "cai",
    "can",
    "cho",
    "co",
    "de",
    "duoc",
    "duoi",
    "gia",
    "goi",
    "hon",
    "khoang",
    "khong",
    "la",
    "less",
    "mua",
    "muon",
    "nay",
    "san",
    "pham",
    "tam",
    "than",
    "the",
    "tim",
    "toi",
    "tr",
    "trieu",
    "under",
    "vnd",
    "voi",
    "y",
}


def get_product_knowledge_context(
    user_message: str,
    session_id: str,
    db: Session,
) -> str:
    """
    Return relevant product knowledge as a formatted string, or "" if there is
    no reliable product context.
    """

    if not user_message or not user_message.strip():
        return ""

    keywords = extract_product_keywords(user_message)
    if not keywords:
        return ""

    profile = db.query(CustomerProfile).filter(
        CustomerProfile.session_id == session_id
    ).first()

    query_budget = parse_budget(user_message)
    memory_budget = parse_budget(profile.budget) if profile and profile.budget else None
    budget_max = query_budget if query_budget is not None else memory_budget

    category = _resolve_category(keywords, profile.preferred_category if profile else None)
    priorities = _extract_priorities(keywords, profile.priorities if profile else None)
    dislikes = _extract_dislikes(getattr(profile, "dislikes", None) if profile else None)

    try:
        products = search_product_database(
            keywords=keywords,
            budget_max=None,
            category=category,
        )
    except Exception as exc:
        print(f"[Product Retrieval] Search failed: {exc}")
        return ""

    products = _drop_disliked_products(products, dislikes)
    products = _apply_context_scoring(products, keywords, category, priorities)

    if budget_max is not None:
        products = filter_by_budget(products, budget_max)

    if not products:
        return ""

    return format_products_for_llm(products[:5])


def extract_product_keywords(user_message: str) -> List[str]:
    """Extract category, priority, budget, and useful search tokens."""

    normalized = normalize_text(user_message)
    if not normalized:
        return []

    keywords: List[str] = []

    for category, tokens in CATEGORY_KEYWORDS.items():
        if any(token in normalized for token in tokens):
            keywords.append(category)
            break

    for priority, tokens in PRIORITY_KEYWORDS.items():
        if any(token in normalized for token in tokens):
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

    return products[:8]


def filter_by_budget(products: List[Dict], budget_max: float) -> List[Dict]:
    """Remove products that exceed the maximum budget."""

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
    """Convert product records into prompt-safe text."""

    if not products:
        return ""

    lines = [
        "San pham de xuat:",
        "Don vi gia: VND (trieu VND), khong quy doi sang USD.",
        "Luu y: chi su dung cac san pham duoi ngan sach neu da co budget.",
    ]
    for index, product in enumerate(products, 1):
        name = product.get("name", "Unknown")
        price = format_vnd(product.get("price"))
        currency = product.get("currency", "VND")
        description = product.get("description", "")
        source = product.get("source", "")
        url = product.get("url", "")

        line = f"{index}. {name} - {price} {currency}"
        if description:
            line += f" - {description}"
        if source:
            line += f" - Nguon: {source}"
        if url:
            line += f" - Link: {url}"
        lines.append(line)

    return "\n".join(lines)


def parse_budget(budget_str: str) -> Optional[float]:
    return parse_budget_to_vnd(budget_str)


def format_price(price: object) -> str:
    return format_vnd(price)


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


def _resolve_category(keywords: List[str], preferred_category: Optional[str]) -> Optional[str]:
    for keyword in keywords:
        if keyword in CATEGORY_KEYWORDS:
            return keyword

    normalized = normalize_text(preferred_category)
    if not normalized:
        return None
    for category, tokens in CATEGORY_KEYWORDS.items():
        if category in normalized or any(token in normalized for token in tokens):
            return category
    return normalized.replace(" ", "_")


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
        haystack = normalize_text(
            f"{product.get('name', '')} {product.get('description', '')} {product.get('category', '')}"
        )
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
        for priority in priorities:
            if any(token in haystack for token in PRIORITY_KEYWORDS.get(priority, set())):
                score += 1.0

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
            if keyword in tags or any(token in haystack for token in PRIORITY_KEYWORDS[keyword]):
                score += 1.5
        elif keyword in haystack or keyword in tags:
            score += 0.7

    return score


def _product_haystack(product: Dict) -> str:
    tags = " ".join(str(tag) for tag in product.get("tags", []))
    return normalize_text(
        f"{product.get('name', '')} {product.get('description', '')} "
        f"{product.get('category', '')} {tags}"
    )
