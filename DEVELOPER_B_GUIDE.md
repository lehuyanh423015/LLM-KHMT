# Developer B: Product Knowledge Implementation Guide

**This document is for Developer B**  
**Focus**: Implementing `services/product_retrieval_service.py`  
**Stable Interface**: `get_product_knowledge_context(user_message, session_id, db) -> str`

---

## Your Mission

Implement the product knowledge retrieval system so that when a customer asks about products, the LLM gets real-time, filtered, and budget-conscious recommendations.

### Current Status
- ❌ Function exists but returns empty string `""`
- ❌ No product search implemented
- ❌ No web integration
- ❌ No budget filtering

### Your Goal
- ✅ Extract product keywords from user message
- ✅ Load customer preferences from database
- ✅ Search product catalog (Chroma vector store)
- ✅ Call web search for real-time pricing
- ✅ Filter results by customer budget
- ✅ Format as readable string for LLM
- ✅ Handle edge cases (no results, budget exceeded, etc.)

---

## 📋 Implementation Steps

### Step 1: Understand the Interface

**File**: `services/product_retrieval_service.py`

**Your Function**:
```python
def get_product_knowledge_context(
    user_message: str,      # "Tôi cần laptop gaming dưới 20 triệu"
    session_id: str,        # "user123"
    db: Session             # Database session
) -> str:                   # Return formatted string or ""
    """
    Load and filter products based on user query and preferences.
    """
```

**Return Type**: `str`
- **If products found**: Formatted text like `"Sản phẩm đề xuất:\n1. Laptop A - 15 triệu..."`
- **If no products**: Empty string `""`
- **If error**: Empty string `""` (fail gracefully)

---

### Step 2: Get Customer Preferences

**Why?**: To filter products by customer's known budget, category, and priorities

**How**:
```python
from models.database_models import CustomerProfile
from sqlalchemy.orm import Session

# Load customer profile from database
profile = db.query(CustomerProfile).filter(
    CustomerProfile.session_id == session_id
).first()

if profile:
    budget_max = profile.budget          # "15 triệu" or None
    preferred_category = profile.preferred_category  # "laptop" or None
    priorities = profile.priorities      # "gaming, pin xịn" or None
```

**Important**: Preferences might be None - handle gracefully

---

### Step 3: Extract Keywords from User Message

**Why?**: To search for relevant products

**Current Helper** (use or improve):
```python
def extract_product_keywords(user_message: str) -> list:
    """
    Extract product keywords from user message.
    
    Example:
    - Input: "Tôi cần laptop gaming dưới 20 triệu"
    - Output: ["laptop", "gaming", "20 triệu"]
    """
    # TODO: Implement keyword extraction
    # Suggestions:
    # 1. Split message into words
    # 2. Remove stopwords (là, được, cái, etc.)
    # 3. Identify product categories (laptop, điện thoại, etc.)
    # 4. Identify priorities (gaming, pin, camera, etc.)
    # 5. Extract numbers for budget clues
    
    keywords = []
    return keywords
```

---

### Step 4: Search Product Database

**Prerequisite**: You need a Chroma vector store with products

**Current Helper**:
```python
def search_product_database(
    keywords: list,           # ["laptop", "gaming"]
    budget_max: float = None, # 20000000 (in VND)
    category: str = None      # "laptop"
) -> list:
    """
    Search products by keywords, budget, and category.
    
    Returns:
    [
        {
            "name": str,           # "Laptop ASUS TUF Gaming"
            "price": float,        # 14000000
            "currency": str,       # "VND"
            "description": str,    # "Gaming laptop with RTX 4060..."
            "category": str,       # "laptop"
            "url": str,            # "https://..."
            "relevance_score": float  # 0.95
        },
        ...
    ]
    """
    # TODO: Implement vector search in Chroma
    # Pseudocode:
    # 1. Initialize Chroma client
    # 2. Query collection with keywords
    # 3. Filter by budget_max if provided
    # 4. Filter by category if provided
    # 5. Sort by relevance_score descending
    # 6. Return top N results (8-10)
    
    results = []
    return results
```

---

### Step 5: Call Web Search for Real-Time Pricing (Optional)

**Why?**: Chroma might have old data. Web search gives current prices.

**Available Service** (if you want to use it):
```python
from services.web_search_service import get_enriched_context

# You can reuse existing web search
context = await get_enriched_context(
    user_message="Giá laptop gaming RTX 4060 hiện tại",
    memory_context="Budget: 20 triệu"
)
```

---

### Step 6: Filter by Budget

**Critical Requirement**: NEVER recommend products exceeding customer's budget

```python
def filter_by_budget(products: list, budget_max: float) -> list:
    """
    Filter products that exceed budget.
    
    Important: STRICTLY enforce budget limit.
    If customer says "dưới 15 triệu", remove all products >= 15 triệu.
    """
    if not budget_max:
        return products  # No budget limit
    
    filtered = [p for p in products if p["price"] <= budget_max]
    return filtered
```

**Test Case**:
```
Customer budget: 15 triệu
Products:
- Laptop A: 14 triệu ✅ Include
- Laptop B: 15 triệu ✅ Include (exactly at limit)
- Laptop C: 16 triệu ❌ EXCLUDE (exceeds)

Result: [Laptop A, Laptop B]
```

---

### Step 7: Format Results for LLM

**Current Helper**:
```python
def format_products_for_llm(products: list) -> str:
    """
    Convert product list into readable string for LLM injection.
    
    Example output:
    "Sản phẩm đề xuất:
     1. Laptop ASUS TUF Gaming - 14 triệu VND - RTX 4060, 16GB RAM
     2. Laptop MSI Bravo - 15 triệu VND - RTX 4050, 8GB RAM
     
     📌 Lưu ý: Giá cập nhật ngày 29/04/2026"
    """
    if not products:
        return ""
    
    lines = ["Sản phẩm đề xuất:"]
    for i, product in enumerate(products, 1):
        name = product.get("name", "Unknown")
        price = product.get("price", "N/A")
        currency = product.get("currency", "VND")
        desc = product.get("description", "")
        
        line = f"{i}. {name} - {price} {currency}"
        if desc:
            line += f" - {desc}"
        
        lines.append(line)
    
    return "\\n".join(lines)
```

---

### Step 8: Handle Edge Cases

**What if no products found?**
```python
if not products:
    return ""  # Empty string is OK, LLM will handle
```

**What if all products exceed budget?**
```python
# First search without budget filter
products = search_product_database(keywords, budget_max=None)

# Then filter
filtered = filter_by_budget(products, budget_max)

if not filtered:
    # All products exceed budget - return empty
    # LLM will tell customer "Xin lỗi, không có sản phẩm trong ngân sách"
    return ""
```

**What if customer has no budget set?**
```python
# Return products anyway, without budget constraint
products = search_product_database(keywords, budget_max=None)
return format_products_for_llm(products)
```

---

## 🔧 Complete Implementation Template

```python
"""
Product Retrieval Service - Implementation Template for Developer B

This is where YOU implement product knowledge retrieval.
Follow the stable interface and type contracts.
"""

from sqlalchemy.orm import Session
from typing import List, Dict
from models.database_models import CustomerProfile

def get_product_knowledge_context(
    user_message: str,
    session_id: str,
    db: Session
) -> str:
    """
    IMPLEMENT THIS FUNCTION
    
    Load product recommendations based on user query and customer preferences.
    """
    
    # Step 1: Extract keywords from user message
    keywords = extract_product_keywords(user_message)
    if not keywords:
        return ""  # Can't determine what customer wants
    
    # Step 2: Load customer preferences
    profile = db.query(CustomerProfile).filter(
        CustomerProfile.session_id == session_id
    ).first()
    
    budget_max = None
    category = None
    if profile:
        # Parse budget string to number if possible
        budget_max = parse_budget(profile.budget) if profile.budget else None
        category = profile.preferred_category
    
    # Step 3: Search products
    try:
        products = search_product_database(
            keywords=keywords,
            budget_max=budget_max,
            category=category
        )
    except Exception as e:
        print(f"[Product Search Error] {e}")
        return ""
    
    # Step 4: Filter by budget (CRITICAL)
    if budget_max:
        products = filter_by_budget(products, budget_max)
    
    # Step 5: Format and return
    if not products:
        return ""  # No matching products
    
    return format_products_for_llm(products)


def extract_product_keywords(user_message: str) -> List[str]:
    """
    Parse user message to extract product search keywords.
    
    Hints:
    - Look for product names (laptop, điện thoại, tablet, etc.)
    - Look for priorities (gaming, pin xịn, camera, etc.)
    - Look for budget indicators (dưới 20 triệu, tối đa 30 triệu, etc.)
    """
    # TODO: Implement
    keywords = []
    return keywords


def search_product_database(
    keywords: List[str],
    budget_max: float = None,
    category: str = None
) -> List[Dict]:
    """
    Query Chroma vector store for products.
    
    Expected to use:
    - services/vector_store/client.py (if exists)
    - Chroma collection with product embeddings
    - Metadata filtering (price, category)
    """
    # TODO: Implement vector search
    results = []
    return results


def filter_by_budget(products: List[Dict], budget_max: float) -> List[Dict]:
    """
    Remove products exceeding budget.
    
    CRITICAL: This is a hard constraint.
    Never recommend products over budget.
    """
    return [p for p in products if p.get("price", float('inf')) <= budget_max]


def format_products_for_llm(products: List[Dict]) -> str:
    """
    Format product list as string for LLM injection.
    """
    if not products:
        return ""
    
    lines = ["Sản phẩm đề xuất:"]
    for i, product in enumerate(products, 1):
        name = product.get("name", "Unknown")
        price = product.get("price", "N/A")
        currency = product.get("currency", "VND")
        desc = product.get("description", "")
        url = product.get("url", "")
        
        line = f"{i}. {name} - {price} {currency}"
        if desc:
            line += f" - {desc}"
        if url:
            line += f" (Xem: {url})"
        
        lines.append(line)
    
    return "\\n".join(lines)


def parse_budget(budget_str: str) -> float:
    """
    Parse budget string to numeric value.
    
    Examples:
    - "15 triệu" -> 15000000
    - "khoảng 20 triệu" -> 20000000
    - "dưới 10 triệu" -> 10000000
    """
    # TODO: Implement parsing
    # Hints: Use regex to extract numbers, handle "triệu" vs "k" units
    return None
```

---

## 🧪 Testing Your Implementation

### Test 1: No Products Found
```python
# Test query with no matching products
result = get_product_knowledge_context(
    user_message="UFO giá rẻ",  # Unlikely to have products
    session_id="test_user",
    db=db_session
)
assert result == ""  # Should return empty string
```

### Test 2: Budget Filtering
```python
# Customer with 15 triệu budget
# Should exclude products > 15 triệu
result = get_product_knowledge_context(
    user_message="laptop dưới 15 triệu",
    session_id="budget_user",
    db=db_session
)
assert "16 triệu" not in result  # No expensive products
assert "14 triệu" in result or "15 triệu" in result  # Has affordable products
```

### Test 3: Category Matching
```python
# Customer looking for gaming laptop
# Should prioritize gaming products
result = get_product_knowledge_context(
    user_message="laptop gaming RTX 4060",
    session_id="gamer_user",
    db=db_session
)
assert "gaming" in result.lower() or "RTX" in result
```

### Test 4: Empty Message
```python
# No query = no results
result = get_product_knowledge_context(
    user_message="",
    session_id="user_empty",
    db=db_session
)
assert result == ""
```

### Test 5: Integration with Orchestrator
```python
# Full chat flow - product context should be injected
# In the LLM response, should see product recommendations
response = await orchestrator.handle_chat(
    user_message="Gợi ý laptop gaming dưới 20 triệu",
    session_id="integration_test",
    db=db_session
)
assert len(response["answer"]) > 0  # LLM responded
# (Product context was successfully injected)
```

---

## ❌ Common Mistakes to Avoid

### ❌ Mistake 1: Ignoring Budget Constraint
```python
# WRONG:
return format_products_for_llm(products)  # Didn't filter by budget!

# CORRECT:
if budget_max:
    products = filter_by_budget(products, budget_max)
return format_products_for_llm(products)
```

### ❌ Mistake 2: Returning Wrong Type
```python
# WRONG:
return {"products": products}  # Returned dict instead of str

# CORRECT:
return format_products_for_llm(products)  # Return str
```

### ❌ Mistake 3: Not Handling Empty Results
```python
# WRONG:
return format_products_for_llm([])  # Returns "\n" or error

# CORRECT:
if not products:
    return ""  # Empty string, LLM handles it
return format_products_for_llm(products)
```

### ❌ Mistake 4: Throwing Exceptions
```python
# WRONG:
vector_client = chroma.Client()  # Might crash if Chroma not running
return format_products_for_llm(search_results)

# CORRECT:
try:
    vector_client = chroma.Client()
    search_results = vector_client.search(...)
except Exception as e:
    print(f"[Product Search Error] {e}")
    return ""  # Fail gracefully
return format_products_for_llm(search_results)
```

### ❌ Mistake 5: Modifying Stable Interface
```python
# WRONG: Changing function signature
def get_product_knowledge_context(
    user_message: str,
    db: Session  # ❌ Missing session_id parameter
) -> str:

# CORRECT: Keep interface stable
def get_product_knowledge_context(
    user_message: str,
    session_id: str,  # ✅ Must have
    db: Session       # ✅ Must have
) -> str:
```

---

## 🔗 Resources You'll Need

### If Using Chroma
```python
from services.vector_store.client import get_chroma_client
# or
from vector_store.client import get_chroma_client

# Initialize and query
client = get_chroma_client()
collection = client.get_collection(name="products")
results = collection.query(
    query_embeddings=embeddings,
    n_results=10,
    where={"price": {"$lte": budget_max}}
)
```

### If Using Web Search
```python
from services.web_search_service import get_enriched_context

# Get real-time context
context = await get_enriched_context(
    user_message="Giá laptop gaming RTX 4060 hiện tại",
    memory_context="Budget: 20 triệu"
)
```

### Database Models
```python
# Customer profile fields
from models.database_models import CustomerProfile

profile = db.query(CustomerProfile).filter(
    CustomerProfile.session_id == session_id
).first()

# Available fields:
profile.session_id
profile.name
profile.budget              # "15 triệu" (string)
profile.preferred_category  # "laptop" (string)
profile.preferred_color     # "đen" (string)
profile.priorities          # "gaming, pin" (string)
profile.dislikes           # "heavy, apple" (string)
profile.updated_at         # datetime
```

---

## ✅ Success Criteria

Your implementation is complete when:

1. ✅ Function returns correct type (`str`)
2. ✅ Empty results return `""` (not None, not [])
3. ✅ Budget constraint is strictly enforced
4. ✅ No exceptions thrown (always fail gracefully)
5. ✅ Formatted output is readable for LLM
6. ✅ Works with empty customer profile
7. ✅ Works with all keywords found/not found
8. ✅ Integrates with orchestrator without errors

---

## 📞 Questions?

| Question | Answer |
|----------|--------|
| "Can I modify the function signature?" | No. It's a stable interface. |
| "What if search fails?" | Return empty string `""`. Orchestrator handles it. |
| "Do I need to call the LLM?" | No. Just prepare context, orchestrator calls LLM. |
| "Should I log debug info?" | Yes, but catch errors and return `""`. |
| "Can I modify the return type?" | No. Must return `str`. |
| "What if no budget is set?" | Return products anyway without budget filter. |

---

**You've got this! 🚀 The skeleton is ready, now make the knowledge layer shine! ✨**
