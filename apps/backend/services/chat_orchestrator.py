"""
Chat Orchestrator Service

Developer A owns this file. It is the only coordinator for the chat pipeline:
session handling, context loading, LLM call, persistence, and memory update.

Developer B plugs Knowledge + Memory logic behind the stable service functions:
- retrieval_service.get_customer_memory_context()
- product_retrieval_service.get_product_knowledge_context()
- memory_service.extract_and_update_customer_memory()
"""

from typing import Any, Dict, List

from sqlalchemy.orm import Session

from core.config import settings
from models.database_models import Conversation, Message
from models.schemas import ChatRequest, ChatResponse
from services.chat_context_service import get_recent_messages
from services.llm.provider_factory import get_llm_provider
from services.memory_service import extract_and_update_customer_memory
from services.product_retrieval_service import (
    get_grounded_product_answer,
    get_product_knowledge_context,
    should_use_llm_grounded_rewrite,
)
from services.query_understanding_service import (
    is_product_request_message,
    is_small_talk_message,
    needs_product_clarification,
    product_clarification_response,
    small_talk_response,
)
from services.retrieval_service import get_customer_memory_context


class ChatOrchestrator:
    """Main orchestration service for chat handling."""

    async def handle_chat(
        self,
        user_message: str,
        session_id: str,
        db: Session,
    ) -> Dict[str, Any]:
        """
        Coordinate one chat turn end-to-end.

        Context contracts:
        - recent_messages: list[dict] with role/content keys
        - memory_context: str
        - product_context: str
        """
        conversation = self._get_or_create_conversation(session_id, user_message, db)
        conversation_id = conversation.id

        if is_small_talk_message(user_message):
            recent_messages = self._load_recent_messages(conversation_id, db)
            self._save_user_message(conversation_id, user_message, db)
            fallback_answer = self._general_chat_fallback(
                user_message,
                only_high_confidence=True,
            ) or small_talk_response(user_message)
            assistant_answer = await self._handle_casual_chat(
                user_message=user_message,
                recent_messages=recent_messages,
                fallback_answer=fallback_answer,
            )
            assistant_msg = self._save_assistant_message(conversation_id, assistant_answer, db)
            return {
                "answer": assistant_answer,
                "session_id": session_id,
                "conversation_id": conversation_id,
                "message_id": assistant_msg.id,
                "debug": self._build_debug_context(
                    recent_messages=recent_messages,
                    memory_context="",
                    product_context="",
                    grounded_answer_used=False,
                    answer_strategy="small_talk_llm" if assistant_answer != fallback_answer else "small_talk_fallback",
                ),
            }

        if not is_product_request_message(user_message):
            recent_messages = self._load_recent_messages(conversation_id, db)
            self._save_user_message(conversation_id, user_message, db)
            assistant_answer = await self._handle_general_chat(user_message, recent_messages)
            assistant_msg = self._save_assistant_message(conversation_id, assistant_answer, db)
            return {
                "answer": assistant_answer,
                "session_id": session_id,
                "conversation_id": conversation_id,
                "message_id": assistant_msg.id,
                "debug": self._build_debug_context(
                    recent_messages=recent_messages,
                    memory_context="",
                    product_context="",
                    grounded_answer_used=False,
                    answer_strategy="general_chat",
                ),
            }

        if needs_product_clarification(user_message):
            recent_messages = self._load_recent_messages(conversation_id, db)
            self._save_user_message(conversation_id, user_message, db)
            fallback_question = product_clarification_response(user_message)
            assistant_answer = await self._handle_product_clarification(
                user_message=user_message,
                fallback_question=fallback_question,
                recent_messages=recent_messages,
            )
            assistant_msg = self._save_assistant_message(conversation_id, assistant_answer, db)

            # Let memory capture safe facts such as category, but avoid retrieval
            # until the user gives budget/use-case details.
            extract_and_update_customer_memory(
                session_id=session_id,
                user_message=user_message,
                assistant_response=assistant_answer,
                db=db,
            )

            return {
                "answer": assistant_answer,
                "session_id": session_id,
                "conversation_id": conversation_id,
                "message_id": assistant_msg.id,
                "debug": self._build_debug_context(
                    recent_messages=recent_messages,
                    memory_context="",
                    product_context="",
                    grounded_answer_used=False,
                    answer_strategy="clarification",
                ),
            }

        recent_messages = self._load_recent_messages(conversation_id, db)
        memory_context = self._load_memory_context(session_id, db)
        product_context = self._load_product_context(user_message, session_id, db)

        self._save_user_message(conversation_id, user_message, db)

        grounded_answer_used = False
        answer_strategy = "llm_synthesis"
        if product_context and settings.ENABLE_GROUNDED_PRODUCT_ANSWER:
            grounded_draft = get_grounded_product_answer(
                user_message=user_message,
                session_id=session_id,
                db=db,
            )
            assistant_answer = grounded_draft
            grounded_answer_used = bool(assistant_answer)
            answer_strategy = "grounded_template" if grounded_answer_used else "llm_synthesis"

            if grounded_draft and should_use_llm_grounded_rewrite(user_message, session_id, db):
                llm_answer = await self._rewrite_grounded_answer_with_llm(
                    user_message=user_message,
                    grounded_draft=grounded_draft,
                    memory_context=memory_context,
                    product_context=product_context,
                    recent_messages=recent_messages,
                )
                if llm_answer:
                    assistant_answer = llm_answer
                    grounded_answer_used = False
                    answer_strategy = "grounded_llm_rewrite"
        else:
            assistant_answer = ""

        if not assistant_answer:
            try:
                provider = get_llm_provider()
                assistant_answer = await provider.generate_response(
                    user_message=user_message,
                    memory_context=memory_context,
                    product_context=product_context,
                    recent_messages=recent_messages,
                )
                if self._looks_like_provider_error(assistant_answer):
                    assistant_answer = ""
                answer_strategy = "llm_synthesis"
            except Exception as e:
                print(f"[Chat Orchestrator] LLM synthesis failed: {e}")
                assistant_answer = ""

        if not assistant_answer.strip() and product_context:
            assistant_answer = get_grounded_product_answer(
                user_message=user_message,
                session_id=session_id,
                db=db,
            )
            grounded_answer_used = bool(assistant_answer)
            if grounded_answer_used:
                answer_strategy = "grounded_template"

        if not assistant_answer.strip():
            assistant_answer = (
                "Xin lỗi, tôi chưa tạo được câu trả lời. "
                "Bạn có thể thử lại hoặc bật grounded product answer nếu Ollama đang chạy chậm."
            )

        assistant_msg = self._save_assistant_message(conversation_id, assistant_answer, db)

        # Synchronous update keeps this student prototype DB-session safe.
        # Developer B can improve extraction internals without changing this call.
        extract_and_update_customer_memory(
            session_id=session_id,
            user_message=user_message,
            assistant_response=assistant_answer,
            db=db,
        )

        return {
            "answer": assistant_answer,
            "session_id": session_id,
            "conversation_id": conversation_id,
            "message_id": assistant_msg.id,
            "debug": self._build_debug_context(
                recent_messages=recent_messages,
                memory_context=memory_context,
                product_context=product_context,
                grounded_answer_used=grounded_answer_used,
                answer_strategy=answer_strategy,
            ),
        }

    async def _handle_general_chat(self, user_message: str, recent_messages: List[Dict[str, str]]) -> str:
        """Answer non-product conversation without forcing catalog recommendations."""
        deterministic_answer = self._general_chat_fallback(user_message, only_high_confidence=True)
        if deterministic_answer:
            return deterministic_answer

        try:
            provider = get_llm_provider()
            if hasattr(provider, "generate_general_response"):
                answer = await provider.generate_general_response(
                    user_message=user_message,
                    recent_messages=recent_messages,
                )
            else:
                answer = await provider.generate_response(
                    user_message=(
                        "Hãy trả lời ngắn gọn, tự nhiên bằng tiếng Việt. "
                        "Đây không phải yêu cầu tư vấn sản phẩm: "
                        f"{user_message}"
                    ),
                    recent_messages=recent_messages,
                )
        except Exception as exc:
            print(f"[Chat Orchestrator] General chat failed: {exc}")
            answer = ""

        if (
            not answer
            or not answer.strip()
            or self._looks_like_product_answer(answer)
            or self._looks_like_provider_error(answer)
        ):
            return self._general_chat_fallback(user_message) or (
                "Mình hiểu. Nếu bạn muốn trao đổi tiếp hoặc cần mình hỗ trợ phần nào cụ thể thì cứ nhắn nhé."
            )
        return answer.strip()

    async def _handle_general_chat(self, user_message: str, recent_messages: List[Dict[str, str]]) -> str:
        """Answer non-product conversation through LLM first when enabled."""
        deterministic_answer = self._general_chat_fallback(
            user_message,
            only_high_confidence=not settings.ENABLE_LLM_CASUAL_CHAT,
        )
        if deterministic_answer and not settings.ENABLE_LLM_CASUAL_CHAT:
            return deterministic_answer

        return await self._handle_casual_chat(
            user_message=user_message,
            recent_messages=recent_messages,
            fallback_answer=deterministic_answer or self._general_chat_fallback(user_message),
        )

    async def _handle_casual_chat(
        self,
        user_message: str,
        recent_messages: List[Dict[str, str]],
        fallback_answer: str,
    ) -> str:
        """Let the LLM handle low-risk conversation, with strict fallback."""
        if not settings.ENABLE_LLM_CASUAL_CHAT:
            return fallback_answer

        try:
            provider = get_llm_provider()
            if hasattr(provider, "generate_general_response"):
                answer = await provider.generate_general_response(
                    user_message=user_message,
                    recent_messages=recent_messages,
                )
            else:
                answer = await provider.generate_response(
                    user_message=(
                        "Hãy trả lời ngắn gọn, tự nhiên bằng tiếng Việt. "
                        "Đây không phải yêu cầu tư vấn sản phẩm: "
                        f"{user_message}"
                    ),
                    recent_messages=recent_messages,
                )
        except Exception as exc:
            print(f"[Chat Orchestrator] Casual chat failed: {exc}")
            answer = ""

        if (
            not answer
            or not answer.strip()
            or self._looks_like_product_answer(answer)
            or self._looks_like_provider_error(answer)
            or self._looks_like_bad_casual_answer(answer, user_message)
        ):
            return fallback_answer or (
                "Mình hiểu. Nếu bạn muốn trao đổi tiếp hoặc cần mình hỗ trợ phần nào cụ thể thì cứ nhắn nhé."
            )
        return answer.strip()

    def _looks_like_bad_casual_answer(self, answer: str, user_message: str) -> bool:
        normalized_answer = self._normalize_ascii(answer)
        normalized_question = self._normalize_ascii(user_message)
        over_refusal_markers = [
            "khong the giup gi",
            "khong the ho tro",
            "lien he voi mot chuyen gia y te",
            "chuyen gia y te",
            "nguoi than gan nhat",
        ]
        role_confusion_markers = [
            "minh cam thay hoi met",
            "minh thay hoi met",
            "vi hom nay ban hoi met",
        ]
        if any(marker in normalized_answer for marker in role_confusion_markers):
            return True
        if any(marker in normalized_answer for marker in over_refusal_markers):
            mild_context = any(
                marker in normalized_question
                for marker in ["hoi met", "met mot chut", "cang thang", "stress", "buon", "noi chuyen"]
            )
            danger_context = any(
                marker in normalized_question
                for marker in ["tu tu", "tu hai", "muon chet", "nguy hiem", "dau nguc", "kho tho"]
            )
            return mild_context and not danger_context
        return False

    async def _handle_product_clarification(
        self,
        user_message: str,
        fallback_question: str,
        recent_messages: List[Dict[str, str]],
    ) -> str:
        """
        Ask for missing buying details naturally.

        The LLM can soften the wording, but the deterministic question remains
        the source of truth and fallback.
        """
        if not settings.ENABLE_LLM_CLARIFICATION:
            return fallback_question

        try:
            provider = get_llm_provider()
            if hasattr(provider, "generate_clarification_response"):
                answer = await provider.generate_clarification_response(
                    user_message=user_message,
                    fallback_question=fallback_question,
                    recent_messages=recent_messages,
                )
            else:
                answer = ""
        except Exception as exc:
            print(f"[Chat Orchestrator] Clarification LLM failed: {exc}")
            answer = ""

        if (
            not answer
            or not answer.strip()
            or self._looks_like_provider_error(answer)
            or self._looks_like_product_answer(answer)
            or not self._looks_like_clarification_question(answer)
        ):
            return fallback_question
        return answer.strip()

    def _looks_like_clarification_question(self, answer: str) -> bool:
        normalized = self._normalize_ascii(answer)
        if "tim mot cho minh" in normalized or normalized.startswith("toi ") or " toi " in normalized:
            return False
        asks_user = any(signal in normalized for signal in ["ban", "cho minh", "minh can", "hay cho"])
        has_question_shape = "?" in answer or any(
            signal in normalized
            for signal in ["bao nhieu", "gi", "nao", "khong", "duoc khong", "nhu the nao"]
        )
        asks_for_inputs = any(
            signal in normalized
            for signal in [
                "ngan sach",
                "muc dich",
                "nhu cau",
                "uu tien",
                "hang",
                "he dieu hanh",
                "su dung",
                "gaming",
                "van phong",
            ]
        )
        return asks_user and has_question_shape and asks_for_inputs

    def _general_chat_fallback(self, user_message: str, only_high_confidence: bool = False) -> str:
        normalized = self._normalize_ascii(user_message)
        if self._looks_like_chatbot_design_discussion(user_message):
            return (
                "Đúng, hướng ổn định hơn là tách rõ vai trò: LLM xử lý các đoạn giao tiếp tự nhiên, hỏi lại khi thiếu dữ kiện "
                "và diễn đạt câu trả lời cho mềm hơn; còn catalog/template giữ các phần cần chính xác như giá, cấu hình, so sánh "
                "và danh sách sản phẩm. Với demo hiện tại, nên ưu tiên flow rule + memory + catalog trước để luôn có câu trả lời, "
                "sau đó chỉ dùng LLM như lớp diễn đạt hoặc giải thích khi dữ liệu đã được xác định rõ."
            )
        if any(signal in normalized for signal in ["ban co the lam", "ban lam duoc gi", "co the lam gi", "kha nang cua ban", "giup duoc gi"]):
            return (
                "Mình có thể trò chuyện, giải thích ngắn gọn, hỗ trợ bạn phân tích nhu cầu "
                "và tư vấn mua sắm khi bạn cần. Nếu bạn hỏi về sản phẩm, mình sẽ dùng thông tin "
                "trong catalog và memory để gợi ý phù hợp hơn."
            )
        if any(signal in normalized for signal in ["ban la ai", "gioi thieu ve ban", "ban ten gi"]):
            return (
                "Mình là trợ lý trò chuyện kiêm tư vấn mua sắm trong demo này. "
                "Mình có thể trao đổi bình thường, và khi bạn cần mua điện thoại hoặc laptop thì mình sẽ phân tích nhu cầu để gợi ý."
            )
        if any(signal in normalized for signal in ["toi met", "minh met", "hoi met", "buon", "cang thang", "stress"]):
            return (
                "Nghe có vẻ bạn đang không thoải mái lắm. Mình có thể trò chuyện nhẹ nhàng với bạn một chút, "
                "hoặc nếu bạn muốn tập trung vào việc cụ thể nào đó thì mình sẽ hỗ trợ từng bước."
            )
        if any(signal in normalized for signal in ["noi chuyen", "tam su", "tro chuyen"]):
            return "Được, mình có thể trò chuyện cùng bạn. Bạn muốn nói về chuyện gì trước?"
        if any(signal in normalized for signal in ["tu van mot chut", "tu van 1 chut", "nho ban tu van", "nho tu van", "hoi mot chut", "hoi 1 chut"]):
            return "Được chứ. Bạn muốn mình tư vấn về điện thoại, laptop hay một nhu cầu khác? Nếu có ngân sách và mục đích sử dụng, bạn nói thêm để mình phân tích chính xác hơn."
        if only_high_confidence:
            return ""
        return "Mình hiểu. Bạn muốn mình hỗ trợ theo hướng nào tiếp?"

    def _looks_like_chatbot_design_discussion(self, user_message: str) -> bool:
        normalized = self._normalize_ascii(user_message)
        meta_terms = [
            "llm",
            "chatbot",
            "chat bot",
            "template",
            "catalog",
            "rag",
            "memory",
            "flow",
            "logic",
            "intent",
            "phan hoi",
            "tra loi",
            "giao tiep",
        ]
        design_terms = [
            "linh hoat",
            "su dung",
            "ap dung",
            "ket hop",
            "chiu trach nhiem",
            "chinh xac",
            "tu nhien",
            "can cai thien",
            "khac phuc",
            "du an",
            "he thong",
        ]
        shopping_terms = [
            "dien thoai",
            "laptop",
            "may tinh",
            "iphone",
            "android",
            "macbook",
            "mua",
            "chon mua",
            "san pham nao",
            "ngan sach",
            "trieu",
        ]
        return (
            any(term in normalized for term in meta_terms)
            and (
                any(term in normalized for term in design_terms)
                or any(term in normalized for term in ["llm", "chatbot", "chat bot", "template", "catalog", "rag", "memory", "flow"])
            )
            and not any(term in normalized for term in shopping_terms)
        )

    def _looks_like_provider_error(self, answer: str) -> bool:
        normalized = self._normalize_ascii(answer)
        error_markers = [
            "an unexpected error occurred",
            "unexpected error occurred while calling ollama",
            "could not connect to ollama",
            "error from ollama api",
            "model",
            "not found in ollama",
            "ollama provider error",
            "xin loi, da co loi",
            "xin loi, toi chua tao duoc",
        ]
        return any(marker in normalized for marker in error_markers)

    def _looks_like_product_answer(self, answer: str) -> bool:
        normalized = self._normalize_ascii(answer)
        product_markers = [
            "mot vai lua chon",
            "san pham dang can nhac",
            "minh se uu tien",
            "checklist:",
            "link kiem tra",
        ]
        return any(marker in normalized for marker in product_markers)

    async def _rewrite_grounded_answer_with_llm(
        self,
        user_message: str,
        grounded_draft: str,
        memory_context: str,
        product_context: str,
        recent_messages: List[Dict[str, str]],
    ) -> str:
        """
        Let the LLM write a natural final answer from grounded product facts.

        The deterministic draft remains the fallback, so complex comparison and
        deep-dive answers can be more natural without losing reliability.
        """
        try:
            provider = get_llm_provider()
            if hasattr(provider, "rewrite_grounded_answer"):
                answer = await provider.rewrite_grounded_answer(
                    user_message=user_message,
                    grounded_draft=grounded_draft,
                    memory_context=memory_context,
                )
                return self._valid_llm_answer(answer, grounded_draft, user_message)

            synthesis_context = (
                "GROUNDED PRODUCT DRAFT FROM RETRIEVAL:\n"
                f"{grounded_draft}\n\n"
                "Use the draft and product context as the only product facts."
            )
            synthesis_request = (
                f"Người dùng hỏi: {user_message}\n\n"
                "Hãy viết câu trả lời cuối cùng bằng tiếng Việt tự nhiên, có dấu đầy đủ. "
                "Nếu đây là câu so sánh, hãy thật sự so sánh và kết luận mẫu nào hợp hơn "
                "theo từng nhu cầu, không chỉ liệt kê thông số. Nếu đây là câu hỏi cấu hình "
                "hoặc đánh giá một sản phẩm, hãy tập trung vào đúng sản phẩm đó. "
                "Không thêm sản phẩm, giá, cấu hình hoặc đường link ngoài context."
            )
            answer = await provider.generate_response(
                user_message=synthesis_request,
                memory_context=memory_context,
                product_context=synthesis_context,
                recent_messages=recent_messages,
            )
        except Exception as exc:
            print(f"[Chat Orchestrator] Grounded LLM rewrite failed: {exc}")
            return ""

        return self._valid_llm_answer(answer, grounded_draft, user_message)

    def _valid_llm_answer(self, answer: str, grounded_draft: str = "", user_message: str = "") -> str:
        if not answer or not answer.strip():
            return ""
        lowered = answer.lower()
        normalized_question = self._normalize_ascii(user_message)
        normalized_answer = self._normalize_ascii(answer)
        error_markers = [
            "error:",
            "could not connect to ollama",
            "model",
            "unexpected error occurred",
            "xin lỗi, tôi chưa tạo được",
            "okay,",
            "let's",
            "the user",
            "i need to",
            "first, i",
            "let me",
        ]
        if any(marker in lowered for marker in error_markers):
            return ""
        if self._contains_unsupported_specific_specs(answer, grounded_draft):
            return ""
        if self._contains_misplaced_comparison_fields(answer):
            return ""
        if self._mentions_unsupported_model_variant(answer, grounded_draft):
            return ""
        if self._looks_too_thin_for_detail(answer, grounded_draft, user_message):
            return ""
        is_comparison = any(signal in normalized_question for signal in ["so sanh", "so s nh", "compare"])
        if is_comparison and "ket luan" not in normalized_answer:
            return ""
        if is_comparison and not self._mentions_compared_products(answer, grounded_draft):
            return ""
        if is_comparison and "thong so chinh" in self._normalize_ascii(grounded_draft):
            if not all(token in normalized_answer for token in ["cpu", "gpu"]):
                return ""
            if "khac biet" not in normalized_answer and "tuong dong" not in normalized_answer:
                return ""
        return answer.strip()

    def _normalize_ascii(self, value: str) -> str:
        import unicodedata

        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = text.replace("đ", "d").replace("Đ", "D")
        return text.lower()

    def _contains_unsupported_specific_specs(self, answer: str, grounded_draft: str) -> bool:
        """Reject LLM rewrites that invent concrete chip/GPU/CPU names."""
        import re

        answer_norm = answer.lower()
        draft_norm = (grounded_draft or "").lower()
        patterns = [
            r"\bintel\s+core\s+i[3579]\b",
            r"\bcore\s+i[3579]\b",
            r"\bryzen\s+[3579]\b",
            r"\brtx\s+\d{4}\b",
            r"\bgtx\s+\d{4}\b",
            r"\bsnapdragon\s+\d+\b",
            r"\bdimensity\s+\d+\b",
            r"\bexynos\s+\d+\b",
        ]
        for pattern in patterns:
            for match in re.findall(pattern, answer_norm):
                if match not in draft_norm:
                    return True
        return False

    def _contains_misplaced_comparison_fields(self, answer: str) -> bool:
        conclusion_count = answer.lower().count("kết luận")
        if conclusion_count > 1:
            return True

        for line in answer.splitlines():
            normalized = self._normalize_ascii(line)
            if normalized.startswith("- gpu") and any(token in normalized for token in ["16gb", "32gb", "ssd", "1tb"]):
                return True
            if normalized.startswith("gpu") and any(token in normalized for token in ["trieu", "gia"]):
                return True
            if normalized.startswith("- gpu") and any(token in normalized for token in ["trieu", "gia"]):
                return True
            if normalized.startswith("- man hinh") and any(token in normalized for token in ["ssd", "1tb", "512gb"]):
                return True
            if normalized.startswith("- ram") and any(token in normalized for token in ["rtx", "gpu roi"]):
                return True
        return False

    def _mentions_unsupported_model_variant(self, answer: str, grounded_draft: str) -> bool:
        answer_norm = self._normalize_ascii(answer)
        draft_norm = self._normalize_ascii(grounded_draft)
        guarded_families = ["zephyrus", "loq", "legion", "rog phone", "redmagic", "poco", "iphone", "galaxy"]
        for family in guarded_families:
            if family not in answer_norm:
                continue
            tokens = [token for token in answer_norm.split() if family.split()[0] in token]
            # The broad token check above is intentionally conservative; exact
            # model-number hallucinations are caught by the regex below.
        import re

        model_patterns = [
            r"zephyrus\s+g\d+",
            r"loq\s+\d+",
            r"legion\s+\d+",
            r"rtx\s+\d{4}",
            r"iphone\s+\d+",
            r"galaxy\s+[a-z]\d+",
            r"poco\s+[a-z]\d+",
        ]
        for pattern in model_patterns:
            for match in re.findall(pattern, answer_norm):
                if match not in draft_norm:
                    return True
        return False

    def _looks_too_thin_for_detail(self, answer: str, grounded_draft: str, user_message: str) -> bool:
        normalized_question = self._normalize_ascii(user_message)
        if not any(signal in normalized_question for signal in ["cau hinh", "thong so", "chi tiet"]):
            return False
        normalized_answer = self._normalize_ascii(answer)
        required = ["cpu", "gpu"] if "laptop" in self._normalize_ascii(grounded_draft) else []
        if required and not all(token in normalized_answer for token in required):
            return True
        return len(answer.strip()) < 450 and len(grounded_draft.strip()) > 900

    def _mentions_compared_products(self, answer: str, grounded_draft: str) -> bool:
        import re

        names = []
        for line in grounded_draft.splitlines():
            stripped = line.strip()
            match = re.match(r"^-\s+(.+?)\s+\(", stripped)
            if not match:
                match = re.match(r"^\d+\.\s+(.+?)\s+-\s+", stripped)
            if match:
                names.append(match.group(1).strip())
            if len(names) >= 2:
                break

        if len(names) < 2:
            return True
        normalized_answer = self._normalize_ascii(answer)
        return all(self._normalize_ascii(name) in normalized_answer for name in names[:2])

    def _load_recent_messages(self, conversation_id: int, db: Session) -> List[Dict[str, str]]:
        """Load recent role/content messages when the experiment flag is enabled."""
        if not settings.ENABLE_RECENT_CONTEXT:
            return []
        return get_recent_messages(
            conversation_id=conversation_id,
            db=db,
            limit=settings.RECENT_CONTEXT_LIMIT,
        )

    def _load_memory_context(self, session_id: str, db: Session) -> str:
        """Load formatted customer memory through Developer B's stable interface."""
        if not settings.ENABLE_MEMORY:
            return ""
        return get_customer_memory_context(session_id=session_id, db=db)

    def _load_product_context(self, user_message: str, session_id: str, db: Session) -> str:
        """Load formatted product knowledge through Developer B's stable interface."""
        if not settings.ENABLE_PRODUCT_CONTEXT:
            return ""
        return get_product_knowledge_context(
            user_message=user_message,
            session_id=session_id,
            db=db,
        )

    def _get_or_create_conversation(
        self,
        session_id: str,
        user_message: str,
        db: Session,
    ) -> Conversation:
        """Find existing conversation or create a new one."""
        conversation = (
            db.query(Conversation)
            .filter(Conversation.session_id == session_id)
            .first()
        )
        if conversation:
            return conversation

        conversation = Conversation(
            title=user_message[:50] if user_message else "New Conversation",
            session_id=session_id,
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        return conversation

    def _save_user_message(self, conversation_id: int, message: str, db: Session) -> Message:
        """Persist the user's message."""
        return self._save_message(conversation_id, "user", message, db)

    def _save_assistant_message(self, conversation_id: int, message: str, db: Session) -> Message:
        """Persist the assistant's response."""
        return self._save_message(conversation_id, "assistant", message, db)

    def _save_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        db: Session,
    ) -> Message:
        msg = Message(conversation_id=conversation_id, role=role, content=content)
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return msg

    def _build_debug_context(
        self,
        recent_messages: List[Dict[str, str]],
        memory_context: str,
        product_context: str,
        grounded_answer_used: bool,
        answer_strategy: str,
    ) -> Dict[str, Any]:
        """Expose lightweight debug metadata for demos and experiments."""
        return {
            "active_model": settings.active_model,
            "answer_strategy": answer_strategy,
            "memory_enabled": settings.ENABLE_MEMORY,
            "recent_context_enabled": settings.ENABLE_RECENT_CONTEXT,
            "product_context_enabled": settings.ENABLE_PRODUCT_CONTEXT,
            "llm_grounded_rewrite_enabled": settings.ENABLE_LLM_GROUNDED_REWRITE,
            "llm_clarification_enabled": settings.ENABLE_LLM_CLARIFICATION,
            "llm_casual_chat_enabled": settings.ENABLE_LLM_CASUAL_CHAT,
            "recent_message_count": len(recent_messages or []),
            "memory_context_loaded": bool(memory_context.strip()),
            "product_context_loaded": bool(product_context.strip()),
            "grounded_answer_used": grounded_answer_used,
        }


_orchestrator_instance = None


def get_chat_orchestrator() -> ChatOrchestrator:
    """Get or create the orchestrator singleton."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = ChatOrchestrator()
    return _orchestrator_instance


async def handle_chat(request: ChatRequest, db: Session) -> ChatResponse:
    """
    Route-facing entry point.

    Keep routes/chat.py thin by delegating the full pipeline here.
    """
    session_id = request.session_id or "default-session"
    result = await get_chat_orchestrator().handle_chat(
        user_message=request.message,
        session_id=session_id,
        db=db,
    )
    return ChatResponse(
        answer=result["answer"],
        session_id=result["session_id"],
        debug=result["debug"],
    )
