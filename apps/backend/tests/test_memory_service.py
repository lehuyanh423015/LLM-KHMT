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

if "models" not in sys.modules:
    models_stub = ModuleType("models")
    sys.modules["models"] = models_stub

if "models.database_models" not in sys.modules:
    database_models_stub = ModuleType("models.database_models")

    class CustomerProfile:
        session_id = "session_id"

        def __init__(self, session_id=""):
            self.session_id = session_id
            self.name = None
            self.budget = None
            self.preferred_category = None
            self.preferred_color = None
            self.priorities = None
            self.dislikes = None

    database_models_stub.CustomerProfile = CustomerProfile
    sys.modules["models.database_models"] = database_models_stub

if "dotenv" not in sys.modules:
    dotenv_stub = ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *args, **kwargs: None
    dotenv_stub.find_dotenv = lambda *args, **kwargs: ""
    sys.modules["dotenv"] = dotenv_stub

from models.database_models import CustomerProfile
from services.memory_service import extract_and_update_customer_memory
from services.retrieval_service import get_customer_memory_context


class FakeQuery:
    def __init__(self, db):
        self._db = db

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._db.profile


class FakeDB:
    def __init__(self):
        self.profile = None
        self.commits = 0

    def query(self, model):
        return FakeQuery(self)

    def add(self, profile):
        self.profile = profile

    def commit(self):
        self.commits += 1


class MemoryServiceTests(TestCase):
    def test_extracts_customer_profile_fields(self):
        db = FakeDB()

        extract_and_update_customer_memory(
            session_id="user-1",
            user_message="Toi can laptop gaming duoi 15 trieu, pin lau, mau den",
            assistant_response=None,
            db=db,
        )

        self.assertIsNotNone(db.profile)
        self.assertEqual(db.profile.preferred_category, "laptop")
        self.assertEqual(db.profile.budget, "duoi 15 trieu")
        self.assertEqual(db.profile.preferred_color, "den")
        self.assertIn("gaming", db.profile.priorities)
        self.assertIn("battery", db.profile.priorities)
        self.assertEqual(db.commits, 1)

    def test_retrieval_formats_profile_context(self):
        db = FakeDB()
        db.profile = CustomerProfile(session_id="user-1")
        db.profile.budget = "duoi 15 trieu"
        db.profile.preferred_category = "laptop"
        db.profile.priorities = "gaming, battery"

        context = get_customer_memory_context("user-1", db)

        self.assertIn("Ngan sach: duoi 15 trieu", context)
        self.assertIn("San pham dang tim: laptop", context)
        self.assertIn("Uu tien: gaming, battery", context)

    def test_budget_update_does_not_turn_ngan_sach_into_book_category(self):
        db = FakeDB()
        db.profile = CustomerProfile(session_id="user-1")
        db.profile.preferred_category = "laptop"
        db.profile.budget = "duoi 15 trieu"

        extract_and_update_customer_memory(
            session_id="user-1",
            user_message="tang ngan sach len 20 trieu",
            assistant_response=None,
            db=db,
        )

        self.assertEqual(db.profile.preferred_category, "laptop")
        self.assertEqual(db.profile.budget, "20 trieu")
