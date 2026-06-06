import sys
from pathlib import Path
from unittest import TestCase


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.query_understanding_service import understand_query


class QueryUnderstandingServiceTests(TestCase):
    def test_understands_vietnamese_phone_budget_and_priorities(self):
        parsed = understand_query("gợi ý điện thoạt tầm 30 triệu chơi game, chụp ảnh, màn hình đẹp")

        self.assertEqual(parsed["category"], "phone")
        self.assertEqual(parsed["budget"]["target"], 30_000_000)
        self.assertEqual(parsed["budget"]["min"], 22_500_000)
        self.assertEqual(parsed["budget"]["max"], 37_500_000)
        self.assertIn("gaming", parsed["priorities"])
        self.assertIn("camera", parsed["priorities"])
        self.assertIn("display", parsed["priorities"])

    def test_understands_laptop_creator_query(self):
        parsed = understand_query(
            "laptop làm Photoshop tầm 25 triệu, không cần gaming, ưu tiên RAM 16GB SSD và tản nhiệt"
        )

        self.assertEqual(parsed["category"], "laptop")
        self.assertEqual(parsed["budget"]["target"], 25_000_000)
        self.assertIn("creator", parsed["priorities"])
        self.assertIn("ram", parsed["priorities"])
        self.assertIn("storage", parsed["priorities"])
        self.assertIn("cooling", parsed["priorities"])
        self.assertIn("gaming", parsed["dislikes"])

    def test_understands_follow_up_and_platform_dislike(self):
        parsed = understand_query("nếu không thích iPhone thì mẫu nào ổn hơn?")

        self.assertTrue(parsed["is_follow_up"])
        self.assertIn("ios", parsed["dislikes"])
        self.assertIn("brand:apple", parsed["disliked_brands"])
        self.assertEqual(parsed["intent"], "comparison")

    def test_understands_laptop_without_exact_word_laptop(self):
        parsed = understand_query("máy tính để code, nhẹ, pin lâu, không MacBook")

        self.assertEqual(parsed["category"], "laptop")
        self.assertIn("coding", parsed["priorities"])
        self.assertIn("lightweight", parsed["priorities"])
        self.assertIn("battery", parsed["priorities"])
        self.assertIn("macos", parsed["dislikes"])
        self.assertIn("brand:apple", parsed["disliked_brands"])
