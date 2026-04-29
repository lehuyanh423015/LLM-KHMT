"""
Product Retrieval Service (Knowledge Base)

=== KNOWLEDGE LAYER (Developer B) ===

This module handles product knowledge retrieval.
It provides the stable interface that Developer B should implement.

Current Status: STUB IMPLEMENTATION (returns empty string)

Expected Future Implementation by Developer B:
- Vector search over product database (Chroma)
- Real-time web search for current pricing
- Product filtering by customer budget + preferences
- Return formatted product recommendations with URLs/sources

STABLE INTERFACE:
    get_product_knowledge_context(user_message: str, session_id: str, db) -> str

The orchestrator calls this function, Developer B implements it.
NO CHANGES NEEDED in orchestrator or routes - just enhance this module.
"""

from sqlalchemy.orm import Session


def get_product_knowledge_context(
    user_message: str,
    session_id: str,
    db: Session
) -> str:
    """
    STABLE INTERFACE FOR DEVELOPER B
    
    Retrieves relevant product knowledge for the given user message.
    
    Args:
        user_message: The user's current message to search for products
        session_id: The customer session ID (to access their preferences)
        db: SQLAlchemy database session
        
    Returns:
        Formatted string with product recommendations/knowledge
        Empty string if no relevant products found
        
    Expected Implementation:
    1. Extract product keywords from user_message
    2. Load customer preferences from DB (budget, category, priorities)
    3. Search product vector database (Chroma)
    4. Filter results by budget and preferences
    5. Optionally call web search for real-time pricing
    6. Format results as string: "Product Name - Price - Why it's suitable"
    7. Include URLs/sources
    8. Return formatted string or empty string if no matches
    
    Examples of return format:
    - Empty: ""
    - With products: 
        "Sản phẩm đề xuất:
         1. Laptop Asus VivoBook 15 - 12 triệu VND - Phù hợp ngân sách, pin 10h
         2. Laptop HP Pavilion - 11 triệu VND - Hiệu năng tốt, giá hợp lý"
    """
    
    # ===== CURRENT: STUB IMPLEMENTATION (Returns empty) =====
    # Developer B: Replace this with actual product search logic
    
    # FUTURE: Remove this and implement:
    # 1. Parse user_message for product keywords
    # 2. Get customer profile from DB using session_id
    # 3. Query Chroma vector store for similar products
    # 4. Filter by budget if available
    # 5. Format results
    # 6. Return formatted string
    
    return ""


# ========== HELPER FUNCTIONS (For Developer B to use) ==========
# These are optional - helpers to make implementation easier

def extract_product_keywords(user_message: str) -> list:
    """
    Extract product-related keywords from user message.
    
    Args:
        user_message: User's input text
        
    Returns:
        List of keywords (strings)
        
    Example:
        "I want a gaming laptop under 20 million" 
        -> ["gaming", "laptop", "20 million"]
    """
    # Placeholder: implement keyword extraction
    keywords = []
    return keywords


def search_product_database(
    keywords: list,
    budget_max: float = None,
    category: str = None
) -> list:
    """
    Search product database using keywords and filters.
    
    Args:
        keywords: List of search terms
        budget_max: Maximum budget (optional)
        category: Product category filter (optional)
        
    Returns:
        List of product results (each result is a dict with product info)
        Empty list if no matches
        
    Expected fields in each result dict:
    {
        "name": str,
        "price": float,
        "currency": str,
        "description": str,
        "category": str,
        "url": str,
        "relevance_score": float
    }
    """
    # Placeholder: implement actual search
    results = []
    return results


def format_products_for_llm(products: list) -> str:
    """
    Format product search results as a readable string for LLM injection.
    
    Args:
        products: List of product dicts from search_product_database()
        
    Returns:
        Formatted string ready to be injected into LLM prompt
        Empty string if products is empty
    """
    if not products:
        return ""
    
    formatted_lines = ["Sản phẩm đề xuất:"]
    for i, product in enumerate(products, 1):
        name = product.get("name", "Unknown")
        price = product.get("price", "N/A")
        currency = product.get("currency", "VND")
        description = product.get("description", "")
        url = product.get("url", "")
        
        line = f"{i}. {name} - {price} {currency}"
        if description:
            line += f" - {description}"
        if url:
            line += f" (Link: {url})"
        
        formatted_lines.append(line)
    
    return "\n".join(formatted_lines)
