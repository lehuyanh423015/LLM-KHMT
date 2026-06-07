import sys
from pathlib import Path
from unittest import TestCase


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.query_understanding_service import (
    is_product_request_message,
    is_small_talk_message,
    needs_product_clarification,
    product_clarification_response,
    small_talk_response,
    understand_query,
)


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

    def test_understands_other_brand_request_as_brand_exclusion(self):
        parsed = understand_query("tôi đang có một chiếc laptop của Lenovo rồi, hãy gợi ý các hãng khác xem")

        self.assertEqual(parsed["category"], "laptop")
        self.assertIn("brand:lenovo", parsed["disliked_brands"])
        self.assertIn("brand:lenovo", parsed["owned_brands"])
        self.assertIn("brand:lenovo", parsed["excluded_brands"])
        self.assertNotIn("brand:lenovo", parsed["preferred_brands"])
        self.assertEqual(parsed["intent"], "recommendation")

    def test_understands_direct_outside_brand_exclusion(self):
        parsed = understand_query("ngoài Lenovo thì còn laptop gaming nào tầm 30 triệu không")

        self.assertEqual(parsed["category"], "laptop")
        self.assertEqual(parsed["budget"]["target"], 30_000_000)
        self.assertIn("gaming", parsed["priorities"])
        self.assertIn("brand:lenovo", parsed["excluded_brands"])
        self.assertIn("brand:lenovo", parsed["disliked_brands"])
        self.assertNotIn("brand:lenovo", parsed["preferred_brands"])
        self.assertTrue(parsed["is_alternative_request"])

    def test_understands_owned_brand_change_without_treating_it_as_preference(self):
        parsed = understand_query("mình từng dùng Dell rồi, muốn đổi thương hiệu khác, laptop văn phòng pin lâu")

        self.assertEqual(parsed["category"], "laptop")
        self.assertIn("office", parsed["priorities"])
        self.assertIn("battery", parsed["priorities"])
        self.assertIn("brand:dell", parsed["owned_brands"])
        self.assertIn("brand:dell", parsed["excluded_brands"])
        self.assertNotIn("brand:dell", parsed["preferred_brands"])

    def test_understands_positive_brand_preference_when_not_owned_or_excluded(self):
        parsed = understand_query("tôi thích laptop ASUS, cần máy mỏng nhẹ pin lâu cho văn phòng")

        self.assertEqual(parsed["category"], "laptop")
        self.assertIn("brand:asus", parsed["preferred_brands"])
        self.assertNotIn("brand:asus", parsed["disliked_brands"])
        self.assertIn("office", parsed["priorities"])
        self.assertIn("lightweight", parsed["priorities"])
        self.assertIn("battery", parsed["priorities"])

    def test_detects_small_talk_without_product_request(self):
        parsed = understand_query("tôi hiểu rồi. cảm ơn phản hồi của bạn")

        self.assertTrue(parsed["is_small_talk"])
        self.assertEqual(parsed["intent"], "small_talk")
        self.assertTrue(is_small_talk_message("tôi hiểu rồi. cảm ơn phản hồi của bạn"))
        self.assertIn("Không có gì", small_talk_response("cảm ơn bạn"))

    def test_small_talk_detector_does_not_block_product_request(self):
        self.assertFalse(is_small_talk_message("cảm ơn, hãy gợi ý thêm điện thoại pin tốt tầm 20 triệu"))

    def test_closing_purchase_message_is_small_talk(self):
        message = "cam on tu van cua ban, co le minh se mua san pham nay"

        self.assertTrue(is_small_talk_message(message))
        self.assertFalse(is_product_request_message(message))
        self.assertIn("trước khi mua", small_talk_response(message))
        self.assertFalse(is_small_talk_message("cam on, hay goi y them dien thoai pin tot tam 20 trieu"))

    def test_product_request_detector_separates_general_chat(self):
        self.assertFalse(is_product_request_message("hôm nay tôi hơi mệt, nói chuyện một chút được không"))
        self.assertFalse(is_product_request_message("bạn có thể làm được những gì"))
        self.assertFalse(is_product_request_message("xin chào, tôi có thể nhờ bạn tư vấn một chút không"))
        self.assertTrue(is_product_request_message("tư vấn giúp tôi laptop văn phòng tầm 20 triệu"))
        self.assertTrue(is_product_request_message("tôi muốn nhờ bạn tư vấn điện thoại chơi game tầm 10 triệu"))
        self.assertTrue(is_product_request_message("so sánh iPhone 15 và Galaxy S24"))
    def test_meta_llm_discussion_is_not_product_request(self):
        self.assertFalse(is_product_request_message(
            "can linh hoat hon trong viec su dung llm va template de tra loi tu nhien hon"
        ))
        self.assertTrue(is_product_request_message("tu van laptop chay llm va ai tam 40 trieu"))
