import sys
from pathlib import Path
from types import ModuleType
from unittest import TestCase
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# The sandbox used for this workspace does not always have the backend
# dependencies installed, so we provide tiny import stubs for this test module.
if "sqlalchemy" not in sys.modules:
    sqlalchemy_stub = ModuleType("sqlalchemy")
    orm_stub = ModuleType("sqlalchemy.orm")
    orm_stub.Session = object
    sqlalchemy_stub.orm = orm_stub
    sys.modules["sqlalchemy"] = sqlalchemy_stub
    sys.modules["sqlalchemy.orm"] = orm_stub

if "models" not in sys.modules:
    models_stub = ModuleType("models")
    sys.modules["models"] = models_stub

if "models.database_models" not in sys.modules:
    database_models_stub = ModuleType("models.database_models")

    class CustomerProfile:  # minimal stand-in for import-time use
        session_id = "session_id"

        def __init__(self, session_id="", budget=None, preferred_category=None, priorities=None):
            self.session_id = session_id
            self.budget = budget
            self.preferred_category = preferred_category
            self.priorities = priorities

    database_models_stub.CustomerProfile = CustomerProfile
    sys.modules["models.database_models"] = database_models_stub

if "dotenv" not in sys.modules:
    dotenv_stub = ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *args, **kwargs: None
    dotenv_stub.find_dotenv = lambda *args, **kwargs: ""
    sys.modules["dotenv"] = dotenv_stub

from services.product_retrieval_service import (
    extract_product_keywords,
    filter_by_budget,
    format_products_for_llm,
    get_product_knowledge_context,
    parse_budget,
    search_product_database,
)


class FakeQuery:
    def __init__(self, profile):
        self._profile = profile

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._profile


class FakeDB:
    def __init__(self, profile=None):
        self._profile = profile

    def query(self, model):
        return FakeQuery(self._profile)


class ProductRetrievalServiceTests(TestCase):
    def test_parse_budget_supports_common_formats(self):
        self.assertEqual(parse_budget("dưới 15 triệu"), 15_000_000)
        self.assertEqual(parse_budget("10-15 triệu"), 15_000_000)
        self.assertEqual(parse_budget("500k"), 500_000)
        self.assertEqual(parse_budget("1.5 triệu"), 1_500_000)

    def test_extract_product_keywords_keeps_category_and_priority(self):
        keywords = extract_product_keywords("Tôi cần laptop gaming dưới 20 triệu")

        self.assertIn("laptop", keywords)
        self.assertIn("gaming", keywords)
        self.assertTrue(any(item.startswith("budget:") for item in keywords))

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_search_product_database_falls_back_to_demo_catalog(self, _mock_client):
        results = search_product_database(["laptop", "gaming"], category="laptop")

        self.assertGreater(len(results), 0)
        self.assertTrue(all(result["category"] == "laptop" for result in results))
        self.assertTrue(any(result["name"] == "Lenovo IdeaPad Slim 3" for result in results))

    def test_filter_by_budget_strictly_enforces_limit(self):
        products = [
            {"name": "A", "price": 14_000_000},
            {"name": "B", "price": 15_000_000},
            {"name": "C", "price": 16_000_000},
        ]

        filtered = filter_by_budget(products, 15_000_000)

        self.assertEqual([item["name"] for item in filtered], ["A", "B"])

    def test_format_products_for_llm_returns_readable_string(self):
        text = format_products_for_llm(
            [
                {
                    "name": "Lenovo IdeaPad Slim 3",
                    "price": 12_990_000,
                    "currency": "VND",
                    "description": "Laptop mỏng nhẹ",
                    "source": "demo_catalog",
                    "url": "https://example.com/products/lenovo-ideapad-slim-3",
                }
            ]
        )

        self.assertIn("San pham de xuat:", text)
        self.assertIn("Lenovo IdeaPad Slim 3", text)
        self.assertIn("12.99 trieu", text)
        self.assertIn("demo_catalog", text)

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_get_product_knowledge_context_uses_memory_and_budget(self, _mock_client):
        from models.database_models import CustomerProfile

        profile = CustomerProfile(
            session_id="user-1",
            budget="15 triệu",
            preferred_category="laptop",
            priorities="gaming",
        )
        db = FakeDB(profile)

        context = get_product_knowledge_context(
            user_message="Gợi ý laptop gaming dưới 15 triệu",
            session_id="user-1",
            db=db,
        )

        self.assertIn("San pham de xuat:", context)
        self.assertIn("Lenovo IdeaPad Slim 3", context)
        self.assertNotIn("ASUS TUF Gaming A15", context)

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_get_product_knowledge_context_returns_empty_for_empty_message(self, _mock_client):
        db = FakeDB()

        context = get_product_knowledge_context(
            user_message="",
            session_id="user-1",
            db=db,
        )

        self.assertEqual(context, "")
