"""
Enhanced Product Search Service
Searches real e-commerce platforms for accurate product information with URLs.
Focuses on Vietnamese platforms + general web search with validation.
"""

from typing import List, Dict, Optional
from duckduckgo_search import DDGS
from core.config import settings
import re


async def search_products_enhanced(
    query: str,
    category: str = "electronics",
    budget_max: Optional[float] = None,
    excluded_brands: Optional[List[str]] = None,
    num_results: int = 8
) -> List[Dict]:
    """
    Enhanced product search with multiple platform support and validation.
    
    Args:
        query: Product search query
        category: Product category (electronics, books, etc.)
        budget_max: Maximum budget in VND
        excluded_brands: List of brands to exclude
        num_results: Number of results to return
        
    Returns:
        List of validated products with URLs and pricing
    """
    
    if not settings.ENABLE_WEB_SEARCH:
        return []
    
    excluded_brands = excluded_brands or []
    all_results = []
    
    # Detect special product types
    is_gaming_phone = any(keyword in query.lower() for keyword in ["gaming", "chiến game", "chơi game", "game phone"])
    is_laptop = any(keyword in query.lower() for keyword in ["laptop", "máy tính", "notebook"])
    
    # Strategy 1: Search Vietnamese e-commerce platforms
    # (These are most reliable for Vietnam market)
    if category == "electronics" or category == "books":
        platform_results = await _search_ecommerce_platforms(
            query, category, budget_max, excluded_brands, is_gaming_phone
        )
        all_results.extend(platform_results)
    
    # Strategy 2: General web search for product details + URLs
    general_results = await _search_web_with_validation(
        query, budget_max, excluded_brands, is_gaming_phone
    )
    all_results.extend(general_results)
    
    # Merge and deduplicate (by product name + source)
    unique_results = _deduplicate_results(all_results)
    
    # Filter by excluded brands
    filtered_results = [
        r for r in unique_results 
        if not any(brand.lower() in r.get("product_name", "").lower() for brand in excluded_brands)
    ]
    
    # For gaming phones, prioritize high-performance specs
    if is_gaming_phone:
        filtered_results = _prioritize_gaming_phones(filtered_results)
    
    # Sort by verification + price relevance
    filtered_results.sort(
        key=lambda x: (
            x.get("verified", False),  # Verified first
            abs((x.get("price", 0) or 0) - (budget_max or 0)) if budget_max else 0  # Then by price proximity
        ),
        reverse=True
    )
    
    return filtered_results[:num_results]


async def _search_ecommerce_platforms(
    query: str,
    category: str,
    budget_max: Optional[float],
    excluded_brands: List[str],
    is_gaming_phone: bool = False
) -> List[Dict]:
    """Search Vietnamese e-commerce platforms (Shopee, Lazada, Tiki) via Google."""
    results = []
    
    platforms = [
        ("Shopee", "site:shopee.vn"),
        ("Lazada", "site:lazada.vn"),
        ("Tiki", "site:tiki.vn"),
    ]
    
    try:
        ddgs = DDGS(timeout=10)
        
        for platform_name, platform_query in platforms:
            try:
                # Enhance search query for gaming-specific needs
                search_query = query
                if is_gaming_phone:
                    search_query = f"gaming phone điện thoại chơi game {query} {platform_query} 2026"
                else:
                    search_query = f"{query} {platform_query} 2026 2025"
                
                platform_results = ddgs.text(search_query, max_results=5)
                
                for result in platform_results:
                    product_data = {
                        "product_name": result.get("title", ""),
                        "description": result.get("body", ""),
                        "url": result.get("href", ""),
                        "source": platform_name,
                        "verified": True,  # E-commerce platform = verified source
                        "price": None,
                        "price_vnd": "Liên hệ",
                        "brand": _extract_brand(result.get("title", ""))
                    }
                    
                    # Extract price if visible in description
                    price_match = re.search(r'(\d+(?:\.\d{3})*)\s*(?:đ|VNĐ|triệu|tr)', 
                                          result.get("body", ""), re.IGNORECASE)
                    if price_match:
                        price_str = price_match.group(1).replace(".", "")
                        if "triệu" in result.get("body", "").lower() or "tr" in result.get("body", "").lower():
                            product_data["price"] = int(price_str) * 1_000_000
                        else:
                            product_data["price"] = int(price_str)
                        product_data["price_vnd"] = f"{product_data['price']:,} VNĐ"
                    
                    # Filter by budget
                    if budget_max and product_data.get("price") and product_data["price"] > budget_max:
                        continue
                    
                    results.append(product_data)
                    
            except Exception as e:
                print(f"[E-commerce Search {platform_name}] Error: {e}")
                continue
    
    except Exception as e:
        print(f"[E-commerce Platforms Error] {e}")
    
    return results


async def _search_web_with_validation(
    query: str,
    budget_max: Optional[float],
    excluded_brands: List[str],
    is_gaming_phone: bool = False
) -> List[Dict]:
    """
    Search general web for product information + validate against multiple sources.
    Only include if found on multiple sources = likely real product.
    """
    results = []
    source_count = {}  # Track which products appear in multiple searches
    
    try:
        ddgs = DDGS(timeout=10)
        
        # Multi-strategy search for better results
        search_queries = [
            f"{query} price VNĐ 2026",
            f"{query} review 2025 2026",
            f"{query} specifications",
        ]
        
        for search_query in search_queries:
            try:
                web_results = ddgs.text(search_query, max_results=5)
                
                for result in web_results:
                    title = result.get("title", "")
                    body = result.get("body", "")
                    href = result.get("href", "")
                    
                    # Skip unreliable sources
                    if _is_unreliable_source(href):
                        continue
                    
                    product_name = _extract_product_name(title)
                    brand = _extract_brand(title)
                    
                    # Skip if brand is excluded
                    if any(excluded.lower() in brand.lower() for excluded in excluded_brands):
                        continue
                    
                    product_key = f"{brand}_{product_name}".lower()
                    
                    # Count appearances across searches
                    if product_key not in source_count:
                        source_count[product_key] = {
                            "count": 0,
                            "data": {
                                "product_name": product_name,
                                "brand": brand,
                                "description": body[:200],
                                "url": href,
                                "source": _extract_domain(href),
                                "verified": False,  # Will be True if appears in 2+ searches
                                "price": _extract_price(body),
                                "price_vnd": _format_price(body)
                            }
                        }
                    
                    source_count[product_key]["count"] += 1
                    
            except Exception as e:
                print(f"[Web Search Query Error] {e}")
                continue
        
        # Only include products that appear in multiple searches (more reliable)
        for product_key, data in source_count.items():
            if data["count"] >= 2:  # Appeared in at least 2 different searches
                data["data"]["verified"] = True
                
                # Filter by budget
                if budget_max and data["data"].get("price") and data["data"]["price"] > budget_max:
                    continue
                
                results.append(data["data"])
    
    except Exception as e:
        print(f"[Web Validation Search Error] {e}")
    
    return results


def _deduplicate_results(results: List[Dict]) -> List[Dict]:
    """Remove duplicate products (same name + similar price)."""
    seen = {}
    unique = []
    
    for result in results:
        key = result.get("product_name", "").lower()
        
        if key not in seen:
            seen[key] = result
            unique.append(result)
        else:
            # Keep the one with verified source or better info
            if result.get("verified") and not seen[key].get("verified"):
                unique.remove(seen[key])
                unique.append(result)
                seen[key] = result
    
    return unique


def _extract_brand(text: str) -> str:
    """Extract brand name from title/text."""
    brands = [
        "Apple", "Samsung", "Dell", "HP", "Lenovo", "Acer", "Asus", "Sony",
        "Microsoft", "Google", "OnePlus", "Xiaomi", "Huawei", "Oppo", "Vivo"
    ]
    
    text_lower = text.lower()
    for brand in brands:
        if brand.lower() in text_lower:
            return brand
    
    # Try to extract first word as brand
    words = text.split()
    return words[0] if words else "Unknown"


def _extract_product_name(title: str) -> str:
    """Extract product name from title."""
    # Remove special characters and clean up
    cleaned = re.sub(r'[|•\-\*]', ' ', title)
    words = cleaned.split()
    
    # Take first 5 words as product name
    product_name = " ".join(words[:5]).strip()
    return product_name if product_name else title


def _extract_price(text: str) -> Optional[float]:
    """Extract price in VND from text."""
    # Pattern: number with commas/dots + VNĐ or triệu
    patterns = [
        r'(\d+(?:[\.,]\d{3})*)\s*(?:triệu|tr)',  # 15 triệu, 15.000 tr
        r'(\d+(?:[\.,]\d{3})*)\s*(?:đ|VNĐ|vnd)',   # 15,000,000 đ
        r'giá(?:\s*chỉ)?(?:\s*từ)?\s*(\d+(?:[\.,]\d{3})*)', # giá từ 15.000.000
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            price_str = match.group(1).replace(".", "").replace(",", "")
            try:
                price = float(price_str)
                
                # If it's a small number (< 1000), it's likely in millions (e.g., 15) 
                # unless explicitly followed by 'k' or 'đ' without enough zeros
                if price < 1000 and ("triệu" in text.lower() or "tr" in text.lower() or price < 100):
                    price *= 1_000_000
                
                return price
            except ValueError:
                continue
    
    return None


def _format_price(text: str) -> str:
    """Format extracted price as readable string."""
    price = _extract_price(text)
    
    if price is None:
        return "Liên hệ"
    
    if price >= 1_000_000:
        return f"{price/1_000_000:.1f} triệu VNĐ"
    elif price >= 1000:
        return f"{price/1000:.0f}k VNĐ"
    else:
        return f"{int(price)} VNĐ"


def _is_unreliable_source(url: str) -> bool:
    """Check if URL is from unreliable source."""
    unreliable_domains = [
        "facebook.com",
        "youtube.com",
        "tiktok.com",
        "instagram.com",
        "pinterest.com",
        "reddit.com",
        "quora.com",
    ]
    
    url_lower = url.lower()
    return any(domain in url_lower for domain in unreliable_domains)


def _extract_domain(url: str) -> str:
    """Extract domain name from URL."""
    match = re.search(r'https?://(?:www\.)?([^/]+)', url)
    if match:
        domain = match.group(1)
        # Return readable domain name
        return domain.split(".")[0].capitalize()
    return "Web"


def _prioritize_gaming_phones(products: List[Dict]) -> List[Dict]:
    """
    Prioritize gaming phones based on performance specs.
    Move actual gaming phones to top, demote generic phones.
    """
    gaming_brands = [
        "ASUS ROG Phone", "Nubia Red Magic", "Black Shark", "iQOO", 
        "OnePlus", "Xiaomi 14 Ultra", "Samsung Galaxy S24 Ultra",
        "Poco F6", "Poco X6", "iPhone 15 Pro", "iPhone 16 Pro"
    ]
    
    gaming_keywords = [
        "ROG", "Red Magic", "Black Shark", "gaming", "120fps", "144Hz", 
        "GPU", "Snapdragon 8 Gen", "Dimensity 9000", "tản nhiệt", "gaming phone"
    ]
    
    # Sort by gaming score
    def gaming_score(product):
        score = 0
        name = product.get("product_name", "").lower()
        description = product.get("description", "").lower()
        brand = product.get("brand", "").lower()
        
        # Check if it's a known gaming phone
        for gaming_brand in gaming_brands:
            if gaming_brand.lower() in name or gaming_brand.lower() in brand:
                score += 100
        
        # Check for gaming keywords
        for keyword in gaming_keywords:
            if keyword.lower() in name or keyword.lower() in description:
                score += 10
        
        # Penalize non-gaming brands if searching for gaming
        generic_phones = ["Galaxy S", "Galaxy A", "Galaxy M", "Note", "A Series", "M Series"]
        for generic in generic_phones:
            if generic.lower() in name and score == 0:
                score -= 5
        
        return score
    
    products.sort(key=gaming_score, reverse=True)
    return products
