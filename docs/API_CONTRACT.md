# API Contract

This document defines the stable backend contract for the current orchestration skeleton.

## POST /chat

Request:

```json
{
  "message": "I need a gaming laptop under 20 million VND",
  "session_id": "session-123"
}
```

Response:

```json
{
  "answer": "Assistant response...",
  "session_id": "session-123",
  "debug": {
    "llm_mode": "fast",
    "active_model": "qwen2.5:0.5b",
    "memory_enabled": true,
    "recent_context_enabled": true,
    "product_context_enabled": false,
    "recent_message_count": 4,
    "memory_context_loaded": true,
    "product_context_loaded": false
  }
}
```

The frontend may ignore `debug`. It is included for academic experiments and demos.

## GET /health

Returns runtime status:

- active LLM provider
- active LLM mode
- active Ollama model
- Ollama reachability
- configured model availability
- experiment flags for memory, recent context, and product context

## Stable Service Interfaces

Developer B implements Knowledge + Memory behind these interfaces. Developer B should not change their signatures.

```python
def get_customer_memory_context(session_id: str, db) -> str:
    ...
```

Returns formatted customer memory, or an empty string when no memory exists.

```python
def get_product_knowledge_context(user_message: str, session_id: str, db) -> str:
    ...
```

Returns formatted product/catalog/RAG context, or an empty string when no product context is available.

```python
def extract_and_update_customer_memory(
    session_id: str,
    user_message: str,
    assistant_response: str | None,
    db,
) -> None:
    ...
```

Extracts and stores customer preferences after a chat turn.

## Context Contracts

The orchestrator and provider use these types only:

```python
memory_context: str
product_context: str
recent_messages: list[dict[str, str]]
```

Recent message item:

```json
{
  "role": "user",
  "content": "..."
}
```

