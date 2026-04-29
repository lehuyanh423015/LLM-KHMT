# Backend Refactoring: Clean Orchestration Skeleton

**Date**: April 2026  
**Goal**: Split backend work between two developers with minimal merge conflicts  
**Status**: Skeleton complete, ready for team development

---

## Overview

This refactoring creates a **clean separation of concerns** in the FastAPI backend:

```
Frontend 
   ↓
Route Layer (Thin)
   ↓
Chat Orchestrator (NEW - Central Hub)
   ├─ Context Loaders
   │  ├─ Recent Messages (stable)
   │  ├─ Customer Memory (stable) 
   │  └─ Product Knowledge (stable - stub for Developer B)
   ├─ LLM Provider
   └─ Database Persistence

Backend Worker Tasks
   └─ Memory Update (asynchronous)
```

---

## Key Principles

1. **Orchestrator is the only coordinator** - Routes are thin, business logic is in `chat_orchestrator.py`
2. **Stable interfaces** - Developer B only touches specific functions with fixed signatures
3. **Context is king** - All knowledge injected through centralized context loaders
4. **No direct coupling** - Routes don't know about LLM, memory, products, etc.
5. **Merge-safe** - Changes to one layer don't break others

---

## Architecture Changes

### 1. New File: `services/chat_orchestrator.py`

**Purpose**: Central coordinator for all chat operations

**Class**: `ChatOrchestrator`

**Main Method**:
```python
async def handle_chat(
    user_message: str,
    session_id: str,
    db: Session
) -> Dict[str, Any]
```

**Responsibilities**:
- Create/find conversation in database
- Load recent messages (via `chat_context_service`)
- Load customer memory (via `retrieval_service.get_customer_memory_context()`)
- Load product knowledge (via `product_retrieval_service.get_product_knowledge_context()`)
- Build final prompt (via `prompt_builder`)
- Call LLM provider
- Save messages to database
- Trigger memory update task

**Key Pattern**: Every context loader returns a string (empty if no data)

---

### 2. New File: `services/prompt_builder.py`

**Purpose**: Centralized prompt assembly

**Main Function**:
```python
def build_llm_prompt(
    memory_context: str,
    product_context: str,
    recent_messages: List[Dict[str, str]],
    current_message: str
) -> Dict[str, str]
```

**Reason**: 
- Ensures consistent prompt structure across all LLM calls
- Developer B extends context, not LLM logic
- Single place to maintain prompt quality

**Prompt Assembly Order**:
1. System instructions
2. Customer memory context
3. Product knowledge context
4. Recent conversation
5. Current user message

---

### 3. New File: `services/product_retrieval_service.py`

**Purpose**: Product knowledge retrieval (STUB for Developer B)

**Current Status**: Returns empty string (no-op)

**Stable Interface**:
```python
def get_product_knowledge_context(
    user_message: str,
    session_id: str,
    db: Session
) -> str
```

**Expected Future Implementation** (Developer B):
- Parse user message for product keywords
- Load customer budget/preferences from DB
- Search Chroma vector store for matching products
- Call web search for real-time pricing
- Filter by budget and preferences
- Format results as readable string
- Return or empty string

**Helper Functions Provided**:
- `extract_product_keywords(user_message: str) -> list`
- `search_product_database(keywords, budget_max, category) -> list`
- `format_products_for_llm(products: list) -> str`

---

### 4. Updated: `services/retrieval_service.py`

**New Stable Interface**:
```python
def get_customer_memory_context(session_id: str, db: Session) -> str
```

**Note**: Old function `get_customer_context()` still exists for backward compatibility

**Returns**: Formatted customer profile or empty string

---

### 5. Updated: `services/memory_service.py`

**New Stable Interface**:
```python
def extract_and_update_customer_memory(
    session_id: str,
    user_message: str,
    assistant_response: Optional[str],
    db: Session
) -> None
```

**Changes**:
- Now accepts `assistant_response` parameter (for future ML-based extraction)
- Old function `extract_and_update_memory()` still exists for backward compatibility

---

### 6. Updated: `services/llm/base.py`

**New Stable Interface**:
```python
async def generate_response(
    user_message: str,
    memory_context: str = "",
    product_context: str = "",
    recent_messages: Optional[List[Dict[str, str]]] = None
) -> str
```

**Changes**:
- Added `product_context` parameter (new - from stable interface)
- Clear documentation of type contracts
- All providers must implement this interface

---

### 7. Updated: `services/llm/ollama_provider.py`

**Changes**:
- Accepts new `product_context` parameter
- Added `_build_system_prompt()` method (uses clean interface)
- Keeps `_build_orchestrated_system_prompt()` for backward compatibility
- Automatically chooses which prompt builder to use

---

### 8. Refactored: `routes/chat.py`

**Before**: 100+ lines of orchestration logic  
**After**: ~25 lines of clean request handling

**New Flow**:
```python
@router.post("/chat")
async def chat(request: ChatRequest, db: Session = Depends(get_db)):
    # 1. Extract session ID
    session_id = request.session_id or "default-session"
    
    # 2. Get orchestrator
    orchestrator = get_chat_orchestrator()
    
    # 3. Delegate all work
    result = await orchestrator.handle_chat(
        user_message=request.message,
        session_id=session_id,
        db=db
    )
    
    # 4. Return response
    return ChatResponse(answer=result["answer"])
```

---

## Developer Responsibilities

### Developer A: Orchestration + LLM

**Owns**:
- `services/chat_orchestrator.py` - Main coordination
- `services/prompt_builder.py` - Prompt assembly
- `routes/chat.py` - Request routing
- `services/llm/base.py` - Provider interface
- `services/llm/ollama_provider.py` - Ollama implementation
- `services/llm/provider_factory.py` - Provider selection
- `core/config.py` - Configuration

**Responsibilities**:
- Keep orchestrator stable and tested
- Coordinate different context loaders
- Ensure LLM provider is reliable
- Maintain backward compatibility
- Review Developer B's context loaders

---

### Developer B: Knowledge + Memory

**Owns**:
- `services/product_retrieval_service.py` - IMPLEMENT THIS
- `services/retrieval_service.py` - Enhance if needed
- `services/memory_service.py` - Enhance if needed
- Vector store configuration (if using Chroma)
- Web search integration (if needed)

**Implements**:
1. **Product Knowledge Context** (`product_retrieval_service.get_product_knowledge_context`)
   - Query product vector database
   - Call web search for pricing
   - Filter by budget + preferences
   - Return formatted string

2. **Memory Enhancement** (optional)
   - Extend customer preference extraction
   - Add behavioral analysis
   - Store more customer signals

3. **Testing**
   - Test with real product data
   - Verify budget filtering works
   - Ensure no hallucinations

**Does NOT touch**:
- Routes
- Orchestrator
- LLM provider
- Prompt assembly

---

## Stable Interfaces (Do Not Change)

These function signatures are FIXED. Developer B only implements the bodies.

### Interface 1: Memory Context
```python
# File: services/retrieval_service.py
def get_customer_memory_context(session_id: str, db: Session) -> str:
    """
    Returns customer profile as formatted string.
    Empty string if no profile exists.
    """
```

### Interface 2: Product Knowledge Context (PRIORITY for Developer B)
```python
# File: services/product_retrieval_service.py
def get_product_knowledge_context(
    user_message: str,
    session_id: str,
    db: Session
) -> str:
    """
    Returns product recommendations as formatted string.
    Empty string if no products found.
    """
```

### Interface 3: Memory Update
```python
# File: services/memory_service.py
def extract_and_update_customer_memory(
    session_id: str,
    user_message: str,
    assistant_response: Optional[str],
    db: Session
) -> None:
    """
    Extracts preferences and updates customer profile.
    """
```

### Interface 4: LLM Generation
```python
# File: services/llm/base.py
async def generate_response(
    user_message: str,
    memory_context: str = "",
    product_context: str = "",
    recent_messages: Optional[List[Dict[str, str]]] = None
) -> str:
    """
    Generates LLM response with context.
    All providers must implement this.
    """
```

---

## Type Contracts (Important!)

### recent_messages
```python
List[Dict[str, str]]
# Each dict has:
{
    "role": "user" | "assistant",
    "content": str
}
```

### memory_context
```python
str
# Example:
"- Tên khách hàng: Ngân
 - Ngân sách (Budget): 15 triệu VND
 - Sản phẩm đang tìm: laptop
 - Ưu tiên: gaming"
 
# Or empty: ""
```

### product_context
```python
str
# Example:
"Sản phẩm đề xuất:
 1. Laptop ASUS Gaming - 14 triệu VND - Giá rẻ, hiệu năng tốt
 2. Laptop HP Gaming - 16 triệu VND - Pin xịn, tản nhiệt tốt"
 
# Or empty: ""
```

---

## Implementation Checklist

### Phase 1: Skeleton (DONE ✅)
- [x] Create `chat_orchestrator.py`
- [x] Create `prompt_builder.py`
- [x] Create `product_retrieval_service.py` (stub)
- [x] Refactor `routes/chat.py`
- [x] Update stable interfaces
- [x] Keep project runnable

### Phase 2: Developer B - Product Knowledge (TODO)
- [ ] Implement `get_product_knowledge_context()`
- [ ] Connect to Chroma vector store
- [ ] Add web search integration
- [ ] Test with real products
- [ ] Verify budget filtering

### Phase 3: Integration Testing (TODO)
- [ ] End-to-end chat flow
- [ ] Memory + Product context together
- [ ] Performance testing
- [ ] Error handling

### Phase 4: Cleanup (TODO)
- [ ] Remove old orchestrator if not used
- [ ] Add integration tests
- [ ] Document deployment

---

## How to Test

### Test 1: Basic Chat (No Context)
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Xin chào", "session_id": "user1"}'
```

**Expected**: LLM responds, memory context is empty (OK), product context is empty (OK)

### Test 2: Chat with Memory
```bash
# First message (extracts budget)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Tôi cần laptop dưới 15 triệu", "session_id": "user1"}'

# Second message (memory should be loaded)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Giới thiệu sản phẩm nào?", "session_id": "user1"}'
```

**Expected**: In second response, memory context shows budget of 15 triệu

### Test 3: Chat with Product Context (After Developer B implements)
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Laptop gaming nào dưới 20 triệu?", "session_id": "user2"}'
```

**Expected**: Product context shows matching gaming laptops

---

## Common Mistakes to Avoid

❌ **Developer A should NOT**:
- Modify `product_retrieval_service.py` (Developer B owns it)
- Add product search logic to orchestrator
- Change stable interface signatures
- Hardcode LLM prompts (use `prompt_builder`)

❌ **Developer B should NOT**:
- Modify `chat_orchestrator.py` orchestration flow
- Modify LLM provider logic
- Add to routes
- Change context return type from `str`

❌ **Both should NOT**:
- Hardcode context assembly in multiple places
- Change interface signatures
- Skip error handling
- Ignore empty context (should still work)

---

## Next Steps

1. **Verify skeleton runs** (Developer A)
   - Run FastAPI with `uvicorn main:app --reload`
   - Test basic chat endpoint
   - Verify no runtime errors

2. **Developer B starts product_retrieval_service implementation**
   - Add vector search to `get_product_knowledge_context()`
   - Test with sample products
   - Verify budget filtering

3. **Integration & Testing**
   - Test memory + product together
   - Performance profiling
   - Error scenario testing

4. **Deployment**
   - Docker setup (if needed)
   - Environment variables
   - Monitoring

---

## Quick Reference

| Component | Purpose | File | Status |
|-----------|---------|------|--------|
| Orchestrator | Central coordinator | `services/chat_orchestrator.py` | NEW ✅ |
| Prompt Builder | Prompt assembly | `services/prompt_builder.py` | NEW ✅ |
| Product Service | Product knowledge | `services/product_retrieval_service.py` | STUB ⏳ |
| Memory Service | Customer memory | `services/memory_service.py` | UPDATED ✅ |
| Retrieval Service | Memory loading | `services/retrieval_service.py` | UPDATED ✅ |
| LLM Base | Provider interface | `services/llm/base.py` | UPDATED ✅ |
| Ollama Provider | LLM calling | `services/llm/ollama_provider.py` | UPDATED ✅ |
| Chat Route | Request handler | `routes/chat.py` | REFACTORED ✅ |

---

## Questions?

- **"Where do I add X?"** → Check stable interfaces section
- **"Can I change this function?"** → Is it in stable interfaces? If yes, no. If no, maybe ask.
- **"The context is empty, is that OK?"** → Yes! Empty string is valid. Code should handle it.
- **"Do I need to restart the server?"** → Yes, if you change imports or env vars. Hot reload works for small changes.

---

**Happy coding! 🚀**
