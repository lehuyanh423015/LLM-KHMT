"""
Web Search Service using DuckDuckGo for retrieving real-time information.
Used for retrieval-augmented generation to provide accurate, up-to-date context.
Focuses on recent information (2025-2026) with multiple search strategies.
"""

from typing import List, Dict
from duckduckgo_search import DDGS
from core.config import settings
from datetime import datetime


async def search_web(query: str, num_results: int = None) -> List[Dict[str, str]]:
    """
    Performs web search using DuckDuckGo with recency optimization.
    Performs multiple searches with different strategies to get recent results.
    
    Args:
        query: Search query string
        num_results: Number of results to return (defaults to WEB_SEARCH_RESULTS config)
        
    Returns:
        List of dicts with 'title', 'body', 'href', and implicit recency priority
    """
    if not settings.ENABLE_WEB_SEARCH:
        return []
    
    if num_results is None:
        num_results = settings.WEB_SEARCH_RESULTS
    
    try:
        ddgs = DDGS(timeout=10)
        all_results = []
        
        # Strategy 1: Search with current year filter for maximum recency
        try:
            recency_query = f"{query} 2026 2025"
            results_recency = ddgs.text(recency_query, max_results=num_results)
            all_results.extend(results_recency)
        except Exception as e:
            print(f"[Web Search - Strategy 1 Error] {e}")
        
        # Strategy 2: Search with "latest" keyword for trending/recent info
        try:
            latest_query = f"{query} latest newest 2026"
            results_latest = ddgs.text(latest_query, max_results=int(num_results * 0.5))
            all_results.extend(results_latest)
        except Exception as e:
            print(f"[Web Search - Strategy 2 Error] {e}")
        
        # Strategy 3: Fallback to general search if needed
        if len(all_results) < num_results * 0.3:
            try:
                results_general = ddgs.text(query, max_results=num_results)
                all_results.extend(results_general)
            except Exception as e:
                print(f"[Web Search - Strategy 3 Error] {e}")
        
        # Remove duplicates while preserving order (prioritize earlier/recent results)
        seen = set()
        formatted_results = []
        for result in all_results:
            href = result.get("href", "")
            if href not in seen:
                seen.add(href)
                formatted_results.append({
                    "title": result.get("title", ""),
                    "body": result.get("body", ""),
                    "href": href,
                    "priority": _calculate_recency_score(result)
                })
        
        # Sort by recency score (higher = more recent)
        formatted_results.sort(key=lambda x: x.get("priority", 0), reverse=True)
        
        # Return top N results
        return formatted_results[:num_results]
        
    except Exception as e:
        print(f"[Web Search Critical Error] {e}")
        return []


def _calculate_recency_score(result: Dict) -> float:
    """
    Calculates a score for result recency based on content indicators.
    Higher score = more likely to be recent information.
    """
    score = 0.0
    body = result.get("body", "").lower()
    title = result.get("title", "").lower()
    
    content = body + " " + title
    
    # Year indicators - boost for 2026, 2025
    if "2026" in content:
        score += 10
    elif "2025" in content:
        score += 8
    elif "2024" in content:
        score += 3
    elif "2023" in content or "2022" in content or "2021" in content:
        score -= 5
    else:
        score += 2  # Neutral for unknown years
    
    # Recency keywords
    recency_keywords = ["latest", "newest", "now", "today", "recent", "current", "just released", "vừa phát hành", "mới nhất", "hiện tại"]
    for keyword in recency_keywords:
        if keyword in content:
            score += 2
    
    # Negative indicators for old content
    old_keywords = ["old", "obsolete", "outdated", "deprecated", "lỗi thời", "cũ"]
    for keyword in old_keywords:
        if keyword in content:
            score -= 3
    
    return score


def format_search_results_for_llm(search_results: List[Dict[str, str]]) -> str:
    """
    Formats web search results into a readable context string for LLM injection.
    Emphasizes recency and source credibility.
    """
    if not search_results:
        return ""
    
    context = "🌐 THÔNG TIN TỪ INTERNET (ƯU TIÊN 2025-2026):\n"
    context += "=" * 60 + "\n"
    
    for i, result in enumerate(search_results, 1):
        context += f"\n[{i}] {result['title']}\n"
        context += f"    Tóm tắt: {result['body']}\n"
        context += f"    Nguồn: {result['href']}\n"
        
        # Add recency indicator if available
        if result.get("priority", 0) > 8:
            context += f"    ⭐ [ƯU TIÊN - THÔNG TIN MỚI]\n"
    
    context += "=" * 60 + "\n"
    context += f"(Cập nhật: {datetime.now().year})\n"
    
    return context


async def get_enriched_context(user_query: str, memory_context: str = "") -> str:
    """
    Combines memory context with web search results for enriched LLM context.
    Aggressively prioritizes recent information.
    """
    enriched = ""
    
    if memory_context:
        enriched += memory_context + "\n\n"
    
    # Perform web search for product/book recommendations with aggressive recency focus
    search_keywords = ["lightnovel", "sách", "truyện", "laptop", "điện thoại", "phone", 
                      "product", "price", "review", "mua", "đánh giá", "chi phí", "giá tiền",
                      "bộ truyện", "tác phẩm", "novel", "book"]
    should_search = any(keyword in user_query.lower() for keyword in search_keywords)
    
    if should_search:
        print(f"[Web Search] Searching for: {user_query}")
        search_results = await search_web(user_query, num_results=settings.WEB_SEARCH_RESULTS)
        
        if search_results:
            print(f"[Web Search] Found {len(search_results)} results")
            enriched += format_search_results_for_llm(search_results)
        else:
            print(f"[Web Search] No results found for query: {user_query}")
    
    return enriched

    
    return enriched
