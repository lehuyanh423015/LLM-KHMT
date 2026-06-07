import sys
from pathlib import Path
from unittest import TestCase


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.query_understanding_service import (
    needs_product_clarification,
    product_clarification_response,
    understand_query,
)


class ClarificationFlowTests(TestCase):
    def test_category_only_product_request_asks_for_more_information(self):
        self.assertTrue(needs_product_clarification("minh dang muon mua dien thoai"))
        self.assertTrue(needs_product_clarification("toi muon mua laptop"))
        self.assertTrue(needs_product_clarification("toi can mua dien thoai pin tot"))

    def test_specific_product_request_does_not_trigger_clarification(self):
        self.assertFalse(needs_product_clarification("toi muon mua dien thoai tam 10 trieu pin tot"))
        self.assertFalse(needs_product_clarification("so sanh iPhone 15 va Galaxy S24"))
        self.assertFalse(needs_product_clarification("cho toi cau hinh Lenovo Legion Pro 5"))
        self.assertFalse(needs_product_clarification("goi y mot vai mau Lenovo, toi thich ban phim cua ho"))

    def test_clarification_response_mentions_missing_decision_inputs(self):
        response = product_clarification_response("minh dang muon mua dien thoai")

        self.assertIn("ngân sách", response)
        self.assertIn("điện thoại", response)
        self.assertIn("Ví dụ", response)

    def test_brand_follow_up_infers_category_and_keyboard_preference(self):
        parsed = understand_query("goi y mot vai mau Lenovo, toi thich ban phim cua ho")

        self.assertEqual(parsed["category"], "laptop")
        self.assertIn("brand:lenovo", parsed["preferred_brands"])
        self.assertIn("keyboard", parsed["priorities"])
