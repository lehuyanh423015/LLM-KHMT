# Work Split

## Developer A: Orchestration + LLM

Developer A owns:

- `apps/backend/routes/chat.py`
- `apps/backend/services/chat_orchestrator.py`
- `apps/backend/services/prompt_builder.py`
- `apps/backend/services/llm/base.py`
- `apps/backend/services/llm/ollama_provider.py`
- `apps/backend/services/llm/provider_factory.py`
- `apps/backend/core/config.py`
- API response/debug contract

Responsibilities:

- Keep `/chat` route thin.
- Keep the central chat flow in `chat_orchestrator.py`.
- Keep Ollama answer synthesis behind `settings.active_model`.
- Keep prompt assembly centralized in `prompt_builder.py`.
- Keep provider logic focused on LLM calls, not product search or memory extraction.

## Developer B: Knowledge + Memory

Developer B owns the implementation behind:

- `apps/backend/services/retrieval_service.py`
- `apps/backend/services/product_retrieval_service.py`
- `apps/backend/services/memory_service.py`
- optional vector store helpers under `apps/backend/vector_store/`

Developer B should implement:

- better customer memory retrieval
- product catalog or RAG retrieval
- product filtering by budget/preferences/dislikes
- stronger memory extraction and update logic

Developer B should not modify these files unless agreed:

- `apps/backend/routes/chat.py`
- `apps/backend/services/chat_orchestrator.py`
- `apps/backend/services/llm/ollama_provider.py`
- `apps/backend/core/config.py`

## Integration Rule

Developer B returns formatted strings through stable interfaces. Developer A's orchestrator injects those strings into the LLM flow.

This keeps merges simple: Developer B can improve Knowledge + Memory without changing the main chat pipeline.

