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

        def __init__(self, session_id="", **kwargs):
            self.session_id = session_id
            self.name = kwargs.get("name")
            self.budget = kwargs.get("budget")
            self.preferred_category = kwargs.get("preferred_category")
            self.preferred_color = kwargs.get("preferred_color")
            self.priorities = kwargs.get("priorities")
            self.dislikes = kwargs.get("dislikes")

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

        self.assertIn("Ngân sách: duoi 15 trieu", context)
        self.assertIn("Sản phẩm đang tìm: laptop", context)
        self.assertIn("Ưu tiên: chơi game, pin", context)

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

    def test_product_count_does_not_overwrite_budget(self):
        db = FakeDB()
        db.profile = CustomerProfile(session_id="user-1")
        db.profile.preferred_category = "laptop"
        db.profile.budget = "khoang 50 trieu"

        extract_and_update_customer_memory(
            session_id="user-1",
            user_message="toi muon tham khao 2 mau cua hang Apple",
            assistant_response=None,
            db=db,
        )
        extract_and_update_customer_memory(
            session_id="user-1",
            user_message="vay thi cho toi 2 mau laptop cua lenovo",
            assistant_response=None,
            db=db,
        )

        self.assertEqual(db.profile.budget, "khoang 50 trieu")
        self.assertEqual(db.profile.preferred_category, "laptop")

    def test_english_million_budget_is_stored_readably(self):
        db = FakeDB()

        extract_and_update_customer_memory(
            session_id="user-1",
            user_message="I want a laptop under 20 million for gaming",
            assistant_response=None,
            db=db,
        )

        self.assertEqual(db.profile.budget, "20 trieu")
        self.assertEqual(db.profile.preferred_category, "laptop")

    def test_small_talk_does_not_update_memory(self):
        db = FakeDB()

        extract_and_update_customer_memory(
            session_id="user-1",
            user_message="toi hieu roi. cam on phan hoi cua ban",
            assistant_response=None,
            db=db,
        )

        self.assertIsNone(db.profile)
        self.assertEqual(db.commits, 0)

    def test_extracts_ios_dislike_without_capturing_filler_words(self):
        db = FakeDB()
        db.profile = CustomerProfile(session_id="user-1")
        db.profile.preferred_category = "phone"

        extract_and_update_customer_memory(
            session_id="user-1",
            user_message=(
                "toi khong thich dung IOS, neu co the thi uu tien cac hang "
                "Trung Quoc de co ty le gia thanh / cau hinh tot nhat"
            ),
            assistant_response=None,
            db=db,
        )

        self.assertIn("ios", db.profile.dislikes)
        self.assertIn("china_brand", db.profile.priorities)
        self.assertIn("value", db.profile.priorities)
        self.assertNotIn("dung", db.profile.dislikes)

    def test_dislike_phrase_does_not_store_noise_words(self):
        db = FakeDB()
        db.profile = CustomerProfile(session_id="user-1")
        db.profile.preferred_category = "laptop"

        extract_and_update_customer_memory(
            session_id="user-1",
            user_message="toi khong thich may cua nha Apple",
            assistant_response=None,
            db=db,
        )

        self.assertIn("brand:apple", db.profile.dislikes)
        self.assertNotIn("cua", db.profile.dislikes)
        self.assertNotIn("nha", db.profile.dislikes)

        context = get_customer_memory_context("user-1", db)
        self.assertIn("hãng Apple", context)

    def test_extracts_richer_memory_for_brand_os_and_constraints(self):
        db = FakeDB()

        extract_and_update_customer_memory(
            session_id="user-1",
            user_message=(
                "toi muon laptop Windows lam Photoshop, uu tien RAM 16GB, SSD lon, "
                "tan nhiet tot, bao hanh chinh hang, thich Lenovo nhung khong can game"
            ),
            assistant_response=None,
            db=db,
        )

        self.assertEqual(db.profile.preferred_category, "laptop")
        self.assertIn("windows", db.profile.priorities)
        self.assertIn("creator", db.profile.priorities)
        self.assertIn("ram", db.profile.priorities)
        self.assertIn("storage", db.profile.priorities)
        self.assertIn("cooling", db.profile.priorities)
        self.assertIn("warranty", db.profile.priorities)
        self.assertIn("brand:lenovo", db.profile.priorities)
        self.assertIn("gaming", db.profile.dislikes)
        self.assertNotIn("gaming", db.profile.priorities or "")
        self.assertIsNone(db.profile.budget)

    def test_explicit_no_gaming_moves_gaming_from_priorities_to_dislikes(self):
        db = FakeDB()
        db.profile = CustomerProfile(session_id="user-1")
        db.profile.preferred_category = "phone"
        db.profile.priorities = "gaming, performance"

        extract_and_update_customer_memory(
            session_id="user-1",
            user_message="toi khong choi game nua, can dien thoai pin tot camera dep man hinh dep",
            assistant_response=None,
            db=db,
        )

        self.assertIn("gaming", db.profile.dislikes)
        self.assertNotIn("gaming", db.profile.priorities or "")
        self.assertIn("battery", db.profile.priorities)
        self.assertIn("camera", db.profile.priorities)
        self.assertIn("display", db.profile.priorities)

    def test_memory_context_formats_structured_tokens_for_llm(self):
        db = FakeDB()
        db.profile = CustomerProfile(session_id="user-1")
        db.profile.budget = "tam 25 trieu"
        db.profile.preferred_category = "laptop"
        db.profile.priorities = "creator, ram, storage, cooling, brand:lenovo, windows"
        db.profile.dislikes = "gaming, brand:apple, macos"

        context = get_customer_memory_context("user-1", db)

        self.assertIn("Ngân sách: tam 25 trieu", context)
        self.assertIn("Ưu tiên:", context)
        self.assertIn("đồ họa/Adobe/render", context)
        self.assertIn("hãng Lenovo", context)
        self.assertIn("Windows", context)
        self.assertIn("Không thích/Cần tránh:", context)
        self.assertIn("hãng Apple", context)
