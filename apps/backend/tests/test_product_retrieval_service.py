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

        def __init__(self, session_id="", budget=None, preferred_category=None, priorities=None, dislikes=None):
            self.session_id = session_id
            self.budget = budget
            self.preferred_category = preferred_category
            self.priorities = priorities
            self.dislikes = dislikes

    database_models_stub.CustomerProfile = CustomerProfile

    class Conversation:
        session_id = "session_id"
        id = "id"

    class Message:
        conversation_id = "conversation_id"
        role = "role"
        id = "id"

    database_models_stub.Conversation = Conversation
    database_models_stub.Message = Message
    sys.modules["models.database_models"] = database_models_stub

if "dotenv" not in sys.modules:
    dotenv_stub = ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *args, **kwargs: None
    dotenv_stub.find_dotenv = lambda *args, **kwargs: ""
    sys.modules["dotenv"] = dotenv_stub

from services.product_retrieval_service import (
    extract_product_keywords,
    filter_by_budget,
    get_grounded_product_answer,
    format_products_for_llm,
    get_product_knowledge_context,
    _extract_budget_constraint,
    _load_mini_catalog,
    _search_external_products,
    parse_budget,
    search_product_database,
)
from services.answer_planning_service import _product_summary
from services.data_normalization import normalize_text


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


class FakeListQuery:
    def __init__(self, first_value=None, all_values=None):
        self._first_value = first_value
        self._all_values = all_values or []

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def first(self):
        return self._first_value

    def all(self):
        return self._all_values


class FakeConversation:
    id = 1


class FakeAssistantMessage:
    def __init__(self, content):
        self.content = content


class FakeConversationDB:
    def __init__(self, assistant_messages):
        self._assistant_messages = assistant_messages

    def query(self, model):
        model_name = getattr(model, "__name__", "")
        if model_name == "CustomerProfile":
            return FakeQuery(None)
        if model_name == "Conversation":
            return FakeListQuery(first_value=FakeConversation())
        if model_name == "Message":
            return FakeListQuery(
                all_values=[FakeAssistantMessage(content) for content in self._assistant_messages]
            )
        return FakeQuery(None)


class ProductRetrievalServiceTests(TestCase):
    def test_normalize_text_preserves_vietnamese_words_as_ascii(self):
        normalized = normalize_text("điện thoại tầm giá 30 triệu, chụp ảnh")

        self.assertIn("dien thoai", normalized)
        self.assertIn("tam gia", normalized)
        self.assertIn("chup anh", normalized)

    def test_parse_budget_supports_common_formats(self):
        self.assertEqual(parse_budget("dưới 15 triệu"), 15_000_000)
        self.assertEqual(parse_budget("10-15 triệu"), 15_000_000)
        self.assertEqual(parse_budget("500k"), 500_000)
        self.assertEqual(parse_budget("1.5 triệu"), 1_500_000)

    def test_budget_constraint_supports_range_target_and_margin(self):
        range_budget = _extract_budget_constraint("dien thoai tu 15 den 25 trieu")
        self.assertEqual(range_budget["min"], 15_000_000)
        self.assertEqual(range_budget["target"], 20_000_000)
        self.assertEqual(range_budget["max"], 25_000_000)

        margin_budget = _extract_budget_constraint("laptop tam 20 trieu co the them 5 trieu")
        self.assertEqual(margin_budget["min"], 15_000_000)
        self.assertEqual(margin_budget["target"], 20_000_000)
        self.assertEqual(margin_budget["max"], 25_000_000)

        max_only_budget = _extract_budget_constraint("dien thoai duoi 20 trieu")
        self.assertIsNone(max_only_budget["min"])
        self.assertEqual(max_only_budget["target"], 20_000_000)
        self.assertEqual(max_only_budget["max"], 20_000_000)

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
        self.assertTrue(any("gaming" in result.get("tags", []) for result in results))

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

        self.assertIn("Sản phẩm đề xuất:", text)
        self.assertIn("Lenovo IdeaPad Slim 3", text)
        self.assertIn("12.99 triệu", text)
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

        self.assertIn("Sản phẩm đề xuất:", context)
        self.assertIn("laptop", context.lower())
        self.assertNotIn("ASUS TUF Gaming A15", context)

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_small_talk_does_not_create_product_context_or_grounded_answer(self, _mock_client):
        db = FakeDB()
        user_message = "toi hieu roi. cam on phan hoi cua ban"

        context = get_product_knowledge_context(
            user_message=user_message,
            session_id="user-1",
            db=db,
        )
        answer = get_grounded_product_answer(
            user_message=user_message,
            session_id="user-1",
            db=db,
        )

        self.assertEqual(context, "")
        self.assertEqual(answer, "")

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_around_budget_prioritizes_requested_price_band(self, _mock_client):
        from models.database_models import CustomerProfile

        profile = CustomerProfile(
            session_id="user-1",
            preferred_category="phone",
            priorities="camera, performance",
        )
        db = FakeDB(profile)

        context = get_product_knowledge_context(
            user_message="goi y dien thoai tam 20 trieu chup anh tot",
            session_id="user-1",
            db=db,
        )

        self.assertIn("Vùng giá ưu tiên: 15 triệu - 25 triệu", context)
        self.assertTrue(
            any(name in context for name in ["Xiaomi 14", "Samsung Galaxy S24", "OPPO Find X8", "iPhone 15"])
        )
        first_product_line = next(line for line in context.splitlines() if line.startswith("1. "))
        self.assertNotIn("Redmi Note", first_product_line)
        self.assertNotIn("POCO X6 Pro", first_product_line)

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_explicit_budget_margin_is_included_in_context(self, _mock_client):
        context = get_product_knowledge_context(
            user_message="goi y dien thoai tam 20 trieu tren duoi 5 trieu",
            session_id="user-1",
            db=FakeDB(),
        )

        self.assertIn("Vùng giá ưu tiên: 15 triệu - 25 triệu", context)

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_get_product_knowledge_context_returns_empty_for_empty_message(self, _mock_client):
        db = FakeDB()

        context = get_product_knowledge_context(
            user_message="",
            session_id="user-1",
            db=db,
        )

        self.assertEqual(context, "")

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_small_talk_does_not_return_product_context_or_answer(self, _mock_client):
        db = FakeDB()

        self.assertEqual(
            get_product_knowledge_context(
                user_message="tôi hiểu rồi. cảm ơn phản hồi của bạn",
                session_id="user-1",
                db=db,
            ),
            "",
        )
        self.assertEqual(
            get_grounded_product_answer(
                user_message="tôi hiểu rồi. cảm ơn phản hồi của bạn",
                session_id="user-1",
                db=db,
            ),
            "",
        )

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_grounded_answer_asks_when_machine_category_is_ambiguous(self, _mock_client):
        answer = get_grounded_product_answer(
            user_message="toi can mua may choi game duoi 20 trieu",
            session_id="user-1",
            db=FakeDB(),
        )

        self.assertIn("điện thoại hay laptop", answer.lower())

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_grounded_answer_includes_buying_note_for_best_pick(self, _mock_client):
        answer = get_grounded_product_answer(
            user_message="dien thoai choi game duoi 20 trieu",
            session_id="user-1",
            db=FakeDB(),
        )

        self.assertIn("Đánh giá nhanh", answer)
        self.assertIn("Lưu ý khi chốt mua", answer)
        self.assertNotIn("Không nên chọn nếu", answer)

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_phone_recommendation_alternatives_use_distinct_product_facts(self, _mock_client):
        answer = get_grounded_product_answer(
            user_message="goi y dien thoai choi game tam 20 trieu",
            session_id="user-1",
            db=FakeDB(),
        )

        self.assertIn("Realme GT 7 Pro", answer)
        self.assertIn("6500mAh", answer)
        self.assertIn("iQOO 13", answer)
        self.assertIn("144Hz", answer)
        self.assertIn("RedMagic 10 Pro", answer)
        self.assertIn("gaming phone", answer)
        self.assertNotIn(
            "Hiệu năng là điểm đáng chú ý, hợp người ưu tiên độ mượt và chơi game; "
            "pin là lợi thế cho nhu cầu dùng lâu trong ngày; màn hình tốt giúp trải nghiệm game",
            answer,
        )

    def test_laptop_recommendation_blurbs_vary_by_product_family(self):
        catalog = _load_mini_catalog()

        def summary_for(name):
            item = next(product for product in catalog if product.get("name") == name)
            return _product_summary(
                item=item,
                category="laptop",
                priorities={"gaming", "performance"},
                budget_target=35_000_000,
            )["recommendation_blurb"]

        rog = summary_for("ASUS ROG Strix G16 RTX 4060")
        tuf = summary_for("ASUS TUF A14 RTX 4060")
        dell = summary_for("Dell G15 RTX 4060")

        self.assertIn("màn hình", rog)
        self.assertTrue(any(token in tuf for token in ["tính cơ động", "pin/cân nặng", "di chuyển"]))
        self.assertTrue(any(token in dell for token in ["hiệu năng", "RTX", "GPU"]))
        self.assertNotEqual(rog.split(".")[0], tuf.split(".")[0])
        self.assertNotEqual(tuf.split(".")[0], dell.split(".")[0])

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_grounded_answer_respects_ios_dislike_from_memory(self, _mock_client):
        from models.database_models import CustomerProfile

        profile = CustomerProfile(
            session_id="user-1",
            budget="15 trieu",
            preferred_category="phone",
            priorities="camera, value, china_brand",
            dislikes="ios, apple, iphone",
        )

        answer = get_grounded_product_answer(
            user_message="toi can dien thoai chup anh trong tam 15 trieu",
            session_id="user-1",
            db=FakeDB(profile),
        )

        self.assertNotIn("iPhone", answer)
        self.assertNotIn("Apple", answer)
        self.assertIn("điện thoại", answer.lower())

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_grounded_answer_respects_inline_ios_dislike(self, _mock_client):
        answer = get_grounded_product_answer(
            user_message="khong thich iPhone, uu tien Android tam 30 trieu chup anh choi game",
            session_id="user-1",
            db=FakeDB(),
        )

        self.assertNotIn("iPhone", answer)
        self.assertNotIn("Apple", answer)
        self.assertTrue(any(name in answer for name in ["Samsung", "Xiaomi", "OPPO", "Vivo", "OnePlus"]))

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_retrieval_handles_vietnamese_typo_phone(self, _mock_client):
        answer = get_grounded_product_answer(
            user_message="goi y dien thoat tam 30 trieu choi game chup anh man hinh dep",
            session_id="user-1",
            db=FakeDB(),
        )

        self.assertIn("điện thoại", answer.lower())
        self.assertNotIn("laptop", answer.lower().splitlines()[0])
        self.assertTrue(any(name in answer for name in ["Galaxy", "Xiaomi", "OPPO", "Vivo", "OnePlus", "iPhone"]))

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_high_phone_budget_gaming_prefers_near_budget_performance_models(self, _mock_client):
        answer = get_grounded_product_answer(
            user_message=(
                "toi muon mua dien thoai tam 30 trieu, can hieu nang tot, pin trau, "
                "choi game la chu yeu, khong can camera tot, toi khong tich apple"
            ),
            session_id="user-1",
            db=FakeDB(),
        )

        first_choice = next(line for line in answer.splitlines() if line.startswith("Mình sẽ ưu tiên:"))
        self.assertNotIn("OnePlus 12R", first_choice)
        self.assertNotIn("Samsung Galaxy A56", first_choice)
        self.assertNotIn("Samsung Galaxy Z Flip6", first_choice)
        self.assertNotIn("iPhone", answer)
        self.assertTrue(
            any(
                name in first_choice
                for name in [
                    "ASUS ROG Phone",
                    "RedMagic",
                    "iQOO",
                    "OnePlus 13",
                    "OnePlus 15",
                    "Samsung Galaxy S25",
                    "Samsung Galaxy S25 Plus",
                    "Samsung Galaxy S24 Ultra",
                    "Samsung Galaxy S25 Ultra",
                    "Xiaomi 15",
                    "OPPO Find X8",
                ]
            )
        )

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_unlimited_budget_ignores_old_budget_and_brand_memory(self, _mock_client):
        from models.database_models import CustomerProfile

        profile = CustomerProfile(
            session_id="user-1",
            budget="50 trieu",
            preferred_category="laptop",
            priorities="choi game, brand:lenovo, gia/cau hinh, hieu nang",
        )

        answer = get_grounded_product_answer(
            user_message=(
                "toi muon laptop cau hinh sieu manh de choi tat ca game nang hien tai "
                "khong can quan tam ve gia"
            ),
            session_id="user-1",
            db=FakeDB(profile),
        )

        first_choice = next(line for line in answer.splitlines() if line.startswith("Mình sẽ ưu tiên:"))
        self.assertIn("MSI Raider 18 RTX 5090", first_choice)
        self.assertNotIn("ngân sách 50", answer)
        self.assertIn("Razer Blade 16 RTX 4080", answer)
        self.assertIn("Lenovo Legion Pro 7 RTX 4080", answer)

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_brand_preference_filters_to_brand_when_available(self, _mock_client):
        answer = get_grounded_product_answer(
            user_message=(
                "toi thich mua dien thoai Xiaomi tam 20 trieu, choi game, pin tot, "
                "khong thich Apple"
            ),
            session_id="user-1",
            db=FakeDB(),
        )

        first_choice = next(line for line in answer.splitlines() if line.startswith("Mình sẽ ưu tiên:"))
        self.assertTrue(any(name in first_choice for name in ["Xiaomi", "POCO"]))
        self.assertNotIn("ASUS ROG", first_choice)
        self.assertNotIn("RedMagic", first_choice)
        self.assertLessEqual(answer.count("\n1. "), 1)

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_exact_product_query_focuses_on_one_product(self, _mock_client):
        answer = get_grounded_product_answer(
            user_message="danh gia chi tiet Xiaomi 15 Pro co nen mua khong",
            session_id="user-1",
            db=FakeDB(),
        )

        self.assertIn("Xiaomi 15 Pro", answer)
        self.assertNotIn("Phương án thay thế", answer)

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_spec_detail_query_uses_product_detail_template(self, _mock_client):
        answer = get_grounded_product_answer(
            user_message="hay cho toi cau hinh chi tiet cua ASUS ROG Zephyrus G14",
            session_id="user-1",
            db=FakeDB(),
        )

        self.assertIn("ASUS ROG Zephyrus G14 - cấu hình và đánh giá nhanh", answer)
        self.assertIn("AMD Ryzen 9 8945HS", answer)
        self.assertIn("16GB/32GB LPDDR5X", answer)
        self.assertIn("1TB NVMe SSD", answer)
        self.assertIn("CPU", answer)
        self.assertIn("GPU", answer)
        self.assertIn("Tản nhiệt", answer)
        self.assertIn("khả năng nâng cấp", answer)
        self.assertIn("Đánh giá theo trải nghiệm mua", answer)
        self.assertNotIn("Cách đọc cấu hình này", answer)
        self.assertNotIn("Phương án thay thế", answer)
        self.assertNotIn("[mini_catalog]", answer)
        self.assertNotIn("[expanded_demo_catalog]", answer)

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_partial_product_name_resolves_to_specific_model(self, _mock_client):
        answer = get_grounded_product_answer(
            user_message="cho toi cau hinh chi tiet cua Lenovo Legion Pro 5",
            session_id="user-1",
            db=FakeDB(),
        )

        self.assertIn("Lenovo Legion Pro 5 RTX 4070", answer)
        self.assertIn("Intel Core i7-14650HX", answer)
        self.assertIn("RTX 4070", answer)
        self.assertIn("16GB/32GB DDR5", answer)
        self.assertIn("1TB NVMe SSD", answer)
        self.assertIn("Đánh giá theo trải nghiệm mua", answer)
        self.assertNotIn("ASUS ROG Zephyrus", answer)

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_phone_detail_template_avoids_repeating_spec_sections(self, _mock_client):
        answer = get_grounded_product_answer(
            user_message="cho toi cau hinh chi tiet Xiaomi 14T",
            session_id="user-1",
            db=FakeDB(),
        )

        self.assertIn("Xiaomi 14T - cấu hình và đánh giá nhanh", answer)
        self.assertIn("Thông số chính", answer)
        self.assertIn("MediaTek Dimensity 8300-Ultra", answer)
        self.assertIn("Đánh giá theo trải nghiệm mua", answer)
        self.assertNotIn("Cách đọc cấu hình này", answer)
        self.assertNotIn("Nhu cầu phù hợp", answer)
        self.assertLessEqual(answer.count("MediaTek Dimensity 8300-Ultra"), 1)
        self.assertLessEqual(answer.count("5000mAh"), 1)

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_iqoo_detail_query_uses_spec_detail_with_rule_flow(self, _mock_client):
        answer = get_grounded_product_answer(
            user_message="duoc roi vay hay phan tich chi tiet hon ve cau hinh cua iqoo 13 xem no manh me o nhung diem nao",
            session_id="user-1",
            db=FakeDB(),
        )

        self.assertIn("iQOO 13", answer)
        self.assertIn("cấu hình", answer.lower())
        self.assertIn("Thông số chính", answer)
        self.assertIn("Qualcomm Snapdragon 8 Elite", answer)
        self.assertIn("6150mAh", answer)
        self.assertNotIn("Xin lỗi", answer)

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_top_end_laptop_detail_includes_exact_reference_specs(self, _mock_client):
        answer = get_grounded_product_answer(
            user_message="cau hinh chi tiet MSI Raider 18 RTX 5090",
            session_id="user-1",
            db=FakeDB(),
        )

        self.assertIn("MSI Raider 18 RTX 5090", answer)
        self.assertIn("Intel Core Ultra 9 285HX", answer)
        self.assertIn("RTX 5090 Laptop GPU 24GB GDDR7", answer)
        self.assertIn("64GB DDR5", answer)
        self.assertIn("2TB NVMe SSD", answer)

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_contextual_reference_uses_recent_product(self, _mock_client):
        db = FakeConversationDB(
            assistant_messages=[
                "Mình vừa gợi ý Lenovo Legion Pro 5 RTX 4070 - 54.99 triệu cho nhu cầu gaming."
            ]
        )

        answer = get_grounded_product_answer(
            user_message="cau hinh chi tiet cua san pham tren nhu the nao",
            session_id="user-1",
            db=db,
        )

        self.assertIn("Lenovo Legion Pro 5 RTX 4070", answer)
        self.assertIn("Đánh giá theo trải nghiệm mua", answer)

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_comparison_query_compares_named_products_only(self, _mock_client):
        answer = get_grounded_product_answer(
            user_message="so sanh ASUS ROG Zephyrus G14 voi Lenovo LOQ 15 RTX 4060 choi game",
            session_id="user-1",
            db=FakeDB(),
        )

        self.assertIn("mình nghiêng về", answer.lower())
        self.assertIn("ASUS ROG Zephyrus G14", answer)
        self.assertIn("Lenovo LOQ 15 RTX 4060", answer)
        self.assertIn("GPU", answer)
        self.assertIn("Kết luận", answer)
        self.assertNotIn("Phương án thay thế", answer)
        self.assertNotIn("HP Omen", answer)

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_comparison_with_two_full_product_names_includes_both_specs(self, _mock_client):
        answer = get_grounded_product_answer(
            user_message=(
                "có vẻ như Lenovo Legion 5 RTX 4070 và Acer Predator Helios Neo 16 RTX 4070 "
                "khá giống nhau về cấu hình, so sánh 2 sản phẩm này"
            ),
            session_id="user-1",
            db=FakeDB(),
        )

        self.assertIn("Lenovo Legion 5 RTX 4070", answer)
        self.assertIn("Acer Predator Helios Neo 16 RTX 4070", answer)
        self.assertIn("Thông số chính", answer)
        self.assertIn("So sánh trực tiếp", answer)
        self.assertIn("Điểm tương đồng", answer)
        self.assertIn("NVIDIA GeForce RTX 4070 Laptop GPU 8GB GDDR6", answer)
        self.assertIn("Intel Core i7-14650HX", answer)
        self.assertIn("AMD Ryzen 7 8845HS", answer)
        self.assertNotIn("Phương án thay thế", answer)

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_phone_comparison_includes_both_products_and_direct_criteria(self, _mock_client):
        answer = get_grounded_product_answer(
            user_message="so sanh mau xiaomi 14 va realme gt 7 pro de choi game",
            session_id="user-1",
            db=FakeDB(),
        )

        self.assertIn("Xiaomi 14", answer)
        self.assertIn("Realme GT 7 Pro", answer)
        self.assertIn("Snapdragon 8 Gen 3", answer)
        self.assertIn("Snapdragon 8 Elite", answer)
        self.assertIn("So sánh trực tiếp", answer)
        self.assertIn("Hiệu năng/chip", answer)
        self.assertIn("Chọn theo nhu cầu", answer)
        self.assertIn("nghiêng về Realme GT 7 Pro", answer)

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_brand_named_in_recommendation_keeps_recommendations_in_brand(self, _mock_client):
        answer = get_grounded_product_answer(
            user_message="goi y laptop Lenovo tam 30 trieu choi game",
            session_id="user-1",
            db=FakeDB(),
        )

        self.assertIn("Lenovo", answer)
        self.assertNotIn("HP Omen", answer)
        self.assertNotIn("ASUS TUF", answer)

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_brand_follow_up_uses_existing_laptop_budget(self, _mock_client):
        from models.database_models import CustomerProfile

        profile = CustomerProfile(
            session_id="user-1",
            budget="khoang 50 trieu",
            preferred_category="laptop",
            priorities="gaming, performance",
        )

        apple_answer = get_grounded_product_answer(
            user_message="toi muon tham khao mot vai mau cua hang Apple",
            session_id="user-1",
            db=FakeDB(profile),
        )
        lenovo_answer = get_grounded_product_answer(
            user_message="vay thi cho toi mot vai mau laptop cua lenovo",
            session_id="user-1",
            db=FakeDB(profile),
        )

        self.assertIn("MacBook", apple_answer)
        self.assertNotIn("Xin lỗi", apple_answer)
        self.assertIn("Lenovo", lenovo_answer)
        self.assertNotIn("Xin lỗi", lenovo_answer)

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_unrealistic_laptop_memory_budget_does_not_block_retrieval(self, _mock_client):
        from models.database_models import CustomerProfile

        profile = CustomerProfile(
            session_id="user-1",
            budget="2 trieu",
            preferred_category="laptop",
            priorities="gaming, performance",
        )

        answer = get_grounded_product_answer(
            user_message="vay thi cho toi mot vai mau laptop cua lenovo",
            session_id="user-1",
            db=FakeDB(profile),
        )

        self.assertIn("Lenovo", answer)
        self.assertNotIn("Xin lỗi", answer)

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_other_brand_request_excludes_owned_brand_and_recent_pick(self, _mock_client):
        from models.database_models import CustomerProfile

        profile = CustomerProfile(
            session_id="user-1",
            budget="tam 30 trieu",
            preferred_category="laptop",
            priorities="gaming, performance, brand:lenovo",
        )

        class DBWithProfileAndRecent(FakeConversationDB):
            def query(self, model):
                model_name = getattr(model, "__name__", "")
                if model_name == "CustomerProfile":
                    return FakeQuery(profile)
                return super().query(model)

        db = DBWithProfileAndRecent(
            assistant_messages=[
                "Mình vừa gợi ý Lenovo LOQ 15 RTX 4060 và Lenovo Legion 5 RTX 4070 cho nhu cầu gaming."
            ]
        )

        answer = get_grounded_product_answer(
            user_message="tôi đang có một chiếc laptop của Lenovo rồi, hãy thử gợi ý các hãng khác xem",
            session_id="user-1",
            db=db,
        )

        self.assertIn("laptop", answer.lower())
        self.assertNotIn("Lenovo", answer)
        self.assertTrue(any(name in answer for name in ["ASUS", "Acer", "HP", "Dell", "MSI", "Gigabyte"]))

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_other_brand_follow_up_excludes_recent_recommended_brand(self, _mock_client):
        from models.database_models import CustomerProfile

        profile = CustomerProfile(
            session_id="user-1",
            budget="tam 20 trieu",
            preferred_category="phone",
            priorities="gaming, performance, brand:xiaomi",
        )

        class DBWithProfileAndRecent(FakeConversationDB):
            def query(self, model):
                model_name = getattr(model, "__name__", "")
                if model_name == "CustomerProfile":
                    return FakeQuery(profile)
                return super().query(model)

        db = DBWithProfileAndRecent(
            assistant_messages=[
                "Minh vua goi y Xiaomi 14, POCO X7 Pro va Xiaomi 14T cho nhu cau choi game."
            ]
        )

        answer = get_grounded_product_answer(
            user_message="goi y mot vai san pham cua hang khac",
            session_id="user-1",
            db=db,
        )

        self.assertIn("điện thoại", answer.lower())
        self.assertNotIn("Xiaomi", answer)
        self.assertNotIn("POCO", answer)
        self.assertTrue(any(name in answer for name in ["Realme", "iQOO", "OnePlus", "Samsung", "Honor"]))

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_explicit_xiaomi_poco_request_overrides_old_brand_memory(self, _mock_client):
        from models.database_models import CustomerProfile

        profile = CustomerProfile(
            session_id="user-1",
            budget="tam 30 trieu",
            preferred_category="phone",
            priorities="gaming, battery, brand:samsung",
        )

        answer = get_grounded_product_answer(
            user_message="cho toi mot vai mau dien thoai Xiaomi/Poco trong tam gia 30 trieu",
            session_id="user-1",
            db=FakeDB(profile),
        )

        first_choice_line = next(
            line for line in answer.splitlines()
            if line.startswith("Mình sẽ ưu tiên:") or line.startswith("MÃ¬nh sáº½ Æ°u tiÃªn:")
        )
        self.assertTrue(any(name in first_choice_line for name in ["Xiaomi", "POCO", "Redmi"]))
        self.assertNotIn("Samsung", first_choice_line)

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_memory_category_guides_vague_budget_follow_up(self, _mock_client):
        from models.database_models import CustomerProfile

        profile = CustomerProfile(
            session_id="user-1",
            budget="khoang 50 trieu",
            preferred_category="laptop",
            priorities="choi game",
        )

        answer = get_grounded_product_answer(
            user_message="tai chinh cua toi dang o khoang 50 trieu, hay dua ra nhung san pham tot hon",
            session_id="user-1",
            db=FakeDB(profile),
        )

        self.assertIn("laptop", answer.lower())
        self.assertNotIn("Galaxy Z Fold", answer)
        self.assertNotIn("điện thoại", answer.lower())

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_direct_outside_brand_request_excludes_brand(self, _mock_client):
        answer = get_grounded_product_answer(
            user_message="ngoài Lenovo thì còn laptop gaming nào tầm 30 triệu không",
            session_id="user-1",
            db=FakeDB(),
        )

        self.assertIn("laptop", answer.lower())
        self.assertNotIn("Lenovo", answer)
        self.assertTrue(any(name in answer for name in ["ASUS", "Acer", "HP", "Dell", "MSI", "Gigabyte"]))

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_retrieval_uses_memory_category_for_follow_up_dislike(self, _mock_client):
        from models.database_models import CustomerProfile

        profile = CustomerProfile(
            session_id="user-1",
            budget="tam 30 trieu",
            preferred_category="phone",
            priorities="camera, display, performance",
            dislikes=None,
        )

        answer = get_grounded_product_answer(
            user_message="neu khong thich iPhone thi mau nao on hon",
            session_id="user-1",
            db=FakeDB(profile),
        )

        self.assertIn("điện thoại", answer.lower())
        self.assertNotIn("iPhone", answer)
        self.assertNotIn("Apple", answer)

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_current_phone_needs_override_old_gaming_memory_in_answer_text(self, _mock_client):
        from models.database_models import CustomerProfile

        profile = CustomerProfile(
            session_id="user-1",
            budget="tam 30 trieu",
            preferred_category="phone",
            priorities="gaming, performance",
        )

        answer = get_grounded_product_answer(
            user_message="toi can dien thoai tam 30 trieu uu tien pin camera chup anh thiet ke man hinh",
            session_id="user-1",
            db=FakeDB(profile),
        )

        self.assertIn("điện thoại", answer.lower())
        self.assertNotIn("chơi game", answer.lower())
        self.assertNotIn("trải nghiệm game", answer.lower())
        self.assertIn("camera", answer.lower())
        self.assertIn("màn hình", answer.lower())

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_retrieval_infers_laptop_from_workload_without_keyword(self, _mock_client):
        answer = get_grounded_product_answer(
            user_message="may tinh lam photoshop premiere tam 25 trieu ram 16gb ssd tan nhiet tot",
            session_id="user-1",
            db=FakeDB(),
        )

        self.assertIn("laptop", answer.lower())
        self.assertTrue(any(name in answer for name in ["Lenovo", "ASUS", "Acer", "HP", "Dell", "MSI"]))

    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_product_retrieval_uses_brand_and_os_memory(self, _mock_client):
        from models.database_models import CustomerProfile

        profile = CustomerProfile(
            session_id="user-1",
            budget="tam 25 trieu",
            preferred_category="laptop",
            priorities="creator, ram, storage, cooling, brand:lenovo, windows",
            dislikes="brand:apple, macos, gaming",
        )

        context = get_product_knowledge_context(
            user_message="goi y laptop lam photoshop va van phong",
            session_id="user-1",
            db=FakeDB(profile),
        )

        self.assertIn("Lenovo", context)
        self.assertNotIn("MacBook", context)

    @patch("services.product_retrieval_service.DDGS")
    def test_external_search_failure_is_not_returned_as_product(self, mock_ddgs):
        mock_ddgs.side_effect = RuntimeError("_get_url() https://links.duckduckgo.com/d.js")

        results = _search_external_products(
            user_message="dien thoai gia hien tai",
            category="phone",
            budget_max=20_000_000,
        )

        self.assertEqual(results, [])

    @patch("services.product_retrieval_service.DDGS")
    @patch("services.product_retrieval_service.get_chroma_client", return_value=None)
    def test_grounded_answer_uses_internal_catalog_when_external_search_fails(self, _mock_client, mock_ddgs):
        mock_ddgs.side_effect = RuntimeError("_get_url() https://links.duckduckgo.com/d.js")

        answer = get_grounded_product_answer(
            user_message="goi y dien thoai tam 20 trieu gia hien tai",
            session_id="user-1",
            db=FakeDB(),
        )

        self.assertNotIn("Khong truy xuat duoc", answer)
        self.assertNotIn("ngoai he thong dang loi", answer)
        self.assertIn("điện thoại", answer.lower())
