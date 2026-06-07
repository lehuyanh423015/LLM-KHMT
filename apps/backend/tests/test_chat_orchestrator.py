import sys
from pathlib import Path
from types import ModuleType
from unittest import TestCase


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

if "sqlalchemy" not in sys.modules:
    sqlalchemy_stub = ModuleType("sqlalchemy")
    orm_stub = ModuleType("sqlalchemy.orm")
    orm_stub.Session = object
    sqlalchemy_stub.orm = orm_stub
    sys.modules["sqlalchemy"] = sqlalchemy_stub
    sys.modules["sqlalchemy.orm"] = orm_stub

if "dotenv" not in sys.modules:
    dotenv_stub = ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *args, **kwargs: None
    dotenv_stub.find_dotenv = lambda *args, **kwargs: ""
    sys.modules["dotenv"] = dotenv_stub

if "models" not in sys.modules:
    sys.modules["models"] = ModuleType("models")

if "models.database_models" not in sys.modules:
    database_models_stub = ModuleType("models.database_models")

    class Conversation:
        id = "id"
        session_id = "session_id"

    class Message:
        id = "id"
        conversation_id = "conversation_id"
        role = "role"

    class CustomerProfile:
        session_id = "session_id"

        def __init__(self, session_id="", budget=None, preferred_category=None, priorities=None, dislikes=None):
            self.session_id = session_id
            self.budget = budget
            self.preferred_category = preferred_category
            self.priorities = priorities
            self.dislikes = dislikes

    database_models_stub.Conversation = Conversation
    database_models_stub.Message = Message
    database_models_stub.CustomerProfile = CustomerProfile
    sys.modules["models.database_models"] = database_models_stub

if "models.schemas" not in sys.modules:
    schemas_stub = ModuleType("models.schemas")

    class ChatRequest:
        pass

    class ChatResponse:
        pass

    schemas_stub.ChatRequest = ChatRequest
    schemas_stub.ChatResponse = ChatResponse
    sys.modules["models.schemas"] = schemas_stub

if "duckduckgo_search" not in sys.modules:
    ddg_stub = ModuleType("duckduckgo_search")

    class DDGS:
        pass

    ddg_stub.DDGS = DDGS
    sys.modules["duckduckgo_search"] = ddg_stub

from services.chat_orchestrator import ChatOrchestrator


class ChatOrchestratorTests(TestCase):
    def test_general_fallback_handles_chatbot_design_discussion(self):
        orchestrator = ChatOrchestrator()

        answer = orchestrator._general_chat_fallback(
            "can linh hoat hon trong viec su dung llm va template de tra loi tu nhien hon",
            only_high_confidence=True,
        )

        self.assertIn("LLM", answer)
        self.assertIn("catalog/template", answer)
        self.assertIn("rule + memory + catalog", answer)

    def test_provider_error_text_is_invalid_for_user_response(self):
        orchestrator = ChatOrchestrator()

        self.assertTrue(
            orchestrator._looks_like_provider_error(
                "An unexpected error occurred while calling Ollama: timed out"
            )
        )
        self.assertTrue(
            orchestrator._looks_like_provider_error(
                "Error: Could not connect to Ollama. Please ensure Ollama is running locally."
            )
        )
        self.assertFalse(orchestrator._looks_like_provider_error("Chào bạn, mình có thể hỗ trợ gì?"))
