"""
Shared normalization helpers for the Knowledge + Memory layer.

The functions here intentionally avoid database or orchestration dependencies so
memory extraction, memory retrieval, and product retrieval can share one parsing
model.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, List, Optional


def repair_mojibake(text: object) -> str:
    """Best-effort repair for UTF-8 text that was decoded as cp1252."""

    if text is None:
        return ""

    value = str(text)
    if not value:
        return ""

    mojibake_markers = ("Ã", "Â", "Ä", "Æ", "áº", "á»", "â€", "�")
    if not any(marker in value for marker in mojibake_markers):
        return value

    try:
        repaired = value.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value

    return repaired if repaired else value


def normalize_text(text: object) -> str:
    """
    Lowercase, repair common mojibake, remove Vietnamese accents, and collapse
    punctuation into searchable ASCII tokens.
    """

    repaired = repair_mojibake(text).lower()
    decomposed = unicodedata.normalize("NFD", repaired)
    without_marks = "".join(
        ch for ch in decomposed if unicodedata.category(ch) != "Mn"
    )
    without_marks = without_marks.replace("đ", "d")
    without_marks = re.sub(r"[^a-z0-9\s\-\.,:/]", " ", without_marks)
    return re.sub(r"\s+", " ", without_marks).strip()


def tokenize(text: object) -> List[str]:
    return [token.strip() for token in normalize_text(text).split() if token.strip()]


def unique_preserve_order(items: Iterable[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            output.append(item)
    return output


def parse_budget_to_vnd(text: object) -> Optional[float]:
    """
    Parse common Vietnamese and English budget formats into VND.

    Examples:
    - "duoi 15 trieu" -> 15000000
    - "10-15 trieu" -> 15000000
    - "500k" -> 500000
    - "1.5 million" -> 1500000
    """

    normalized = normalize_text(text)
    if not normalized:
        return None

    range_match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(?:-|to|den)\s*"
        r"(\d+(?:[.,]\d+)?)\s*"
        r"(trieu|tr|k|nghin|ngan|m|million|vnd|usd)?",
        normalized,
    )
    if range_match:
        return _parse_amount(range_match.group(2), range_match.group(3))

    match = re.search(
        r"(?:duoi|tren|khoang|tam|toi da|toi thieu|tu|budget|under|below|about|around)?"
        r"\s*(\d+(?:[.,]\d+)?)\s*"
        r"(trieu|tr|k|nghin|ngan|m|million|vnd|usd)?",
        normalized,
    )
    if not match:
        return None

    return _parse_amount(match.group(1), match.group(2))


def format_vnd(value: object) -> str:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return str(value)

    if price >= 1_000_000:
        millions = f"{price / 1_000_000:.2f}".rstrip("0").rstrip(".")
        return f"{millions} trieu"
    if price >= 1_000:
        thousands = f"{price / 1_000:.2f}".rstrip("0").rstrip(".")
        return f"{thousands}k"
    return str(int(price))


def _parse_amount(amount_text: str, unit: Optional[str]) -> Optional[float]:
    try:
        amount = float(amount_text.replace(",", "."))
    except (TypeError, ValueError):
        return None

    normalized_unit = (unit or "").lower()
    if normalized_unit in {"trieu", "tr", "m", "million"}:
        return amount * 1_000_000
    if normalized_unit in {"k", "nghin", "ngan"}:
        return amount * 1_000
    if normalized_unit == "usd":
        return amount * 25_000

    return amount
