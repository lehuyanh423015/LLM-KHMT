"""
Dialogue Orchestrator Service
Manages conversation state, intent recognition, constraint extraction, and tool routing
for smart shopping recommendations.
"""

from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from models.database_models import DialogueState
import json
import re


class DialogueOrchestrator:
    """Orchestrates conversation flow with structured state management."""
    
    def __init__(self):
        self.intent_keywords = {
            "gift_recommendation": [
                "quà", "tặng", "quà tặng", "sinh nhật", "kỉ niệm", 
                "quà cho", "tặng cho", "hiếu hỏi", "quà hôm nay"
            ],
            "budget_advice": [
                "ngân sách", "chi bao nhiêu", "tiền", "giá", "bao nhiêu tiền",
                "khỏang giá", "cân nhắc", "hợp giá", "đắt", "rẻ"
            ],
            "product_comparison": [
                "so sánh", "cái nào tốt hơn", "khác nhau", "cái nào",
                "so với", "versus", "vs", "giữa", "chọn"
            ],
            "price_lookup": [
                "giá bao", "giá bao nhiêu", "giá hiện tại", "giá", "shop nào",
                "mua ở đâu", "còn hàng", "sale", "mã giảm"
            ],
            "category_switch": [
                "không", "khác", "cái khác", "thay đổi", "mở ra", "sang",
                "chuyển sang", "không đó", "sai rồi", "không phải"
            ]
        }
    
    async def process_user_message(
        self, 
        user_message: str, 
        current_state: Optional[DialogueState],
        conversation_history: List[Dict],
        db: Session
    ) -> Dict:
        """
        Main orchestrator function: processes user message and returns structured output.
        """
        # Step 1: Extract intent from current message
        intent_result = self._detect_intent(user_message, current_state)
        
        # Step 2: Extract constraints
        constraints = self._extract_constraints(user_message)
        
        # Step 3: Detect negative feedback
        is_negative_feedback = self._detect_negative_feedback(user_message, current_state)
        
        # Step 4: Reconcile state
        updated_state = self._reconcile_state(
            current_state,
            intent_result,
            constraints,
            is_negative_feedback,
            user_message
        )
        
        # Step 5: Decide if tool is needed
        need_tool, tool_type, tool_query = self._decide_tool_routing(
            intent_result["intent"],
            user_message,
            updated_state
        )
        
        # Step 6: Determine response strategy
        response_strategy = self._select_response_strategy(
            intent_result["intent"],
            updated_state,
            is_negative_feedback
        )
        
        # Step 7: Detect query specificity (for answer-first logic)
        specificity_result = self._detect_query_specificity(user_message, updated_state)
        
        # Step 8: Check if missing information is blocking
        is_blocking_missing = self._is_blocking_missing_information(
            specificity_result["specificity"],
            specificity_result["missing_info"],
            updated_state
        )
        
        # Step 9: Enforce answer-first logic
        answer_first_logic = self._enforce_answer_first_logic(
            intent_result["intent"],
            specificity_result["specificity"],
            specificity_result["missing_info"],
            specificity_result["can_answer_now"],
            is_blocking_missing
        )
        
        # Step 10: Validate
        validation = self._validate_output(updated_state)
        
        # Step 11: Save state
        if updated_state:
            self._save_state(updated_state, db)
        
        return {
            "intent": intent_result["intent"],
            "sub_intent": intent_result.get("sub_intent"),
            "confidence": intent_result.get("confidence", 0.5),
            "updated_state": updated_state,
            "need_tool": need_tool,
            "tool_type": tool_type,
            "tool_query": tool_query,
            "response_strategy": response_strategy,
            "specificity": specificity_result["specificity"],
            "missing_info": specificity_result["missing_info"],
            "answer_first_logic": answer_first_logic,
            "validation": validation,
            "learning_signal": {
                "user_preference_detected": constraints.get("detected_preferences", []),
                "negative_feedback_detected": is_negative_feedback,
                "category_changed": constraints.get("category_changed", False)
            }
        }
    
    def _detect_intent(self, user_message: str, current_state: Optional[DialogueState]) -> Dict:
        """Detect primary intent from user message."""
        msg_lower = user_message.lower()
        scores = {}
        
        for intent, keywords in self.intent_keywords.items():
            score = sum(1 for kw in keywords if kw in msg_lower)
            if score > 0:
                scores[intent] = score
        
        # Check for negative feedback (category switch signal)
        negative_signals = [
            "không", "sai", "khác", "không phải", "không đó",
            "không hợp lý", "quá đắt", "không ưa", "loại bỏ", "tránh"
        ]
        is_negative = any(sig in msg_lower for sig in negative_signals)
        
        # Determine primary intent
        if scores:
            primary_intent = max(scores, key=scores.get)
            confidence = min(scores[primary_intent] / 5.0, 1.0)
        elif is_negative and current_state:
            primary_intent = "category_switch"
            confidence = 0.7
        elif current_state and current_state.intent:
            # Continue previous intent
            primary_intent = current_state.intent
            confidence = 0.6
        else:
            primary_intent = "product_recommendation"
            confidence = 0.4
        
        return {
            "intent": primary_intent,
            "sub_intent": self._detect_sub_intent(user_message, primary_intent),
            "confidence": confidence,
            "is_negative_feedback": is_negative
        }
    
    def _detect_sub_intent(self, user_message: str, intent: str) -> Optional[str]:
        """Detect sub-intent based on message and intent."""
        msg_lower = user_message.lower()
        
        if intent == "gift_recommendation":
            if any(kw in msg_lower for kw in ["người yêu", "người thương", "bạn gái", "bạn trai"]):
                return "gift_for_partner"
            elif any(kw in msg_lower for kw in ["vợ", "chồng", "bố", "mẹ", "anh", "chị", "em"]):
                return "gift_for_family"
            elif any(kw in msg_lower for kw in ["bạn", "đồng nghiệp", "sếp"]):
                return "gift_for_friend"
        
        return None
    
    def _extract_constraints(self, user_message: str) -> Dict:
        """Extract shopping constraints from user message."""
        constraints = {
            "budget_min": None,
            "budget_max": None,
            "category": None,
            "excluded_categories": [],
            "recipient": None,
            "occasion": None,
            "detected_preferences": [],
            "category_changed": False
        }
        
        # Extract budget (VND)
        budget_patterns = [
            r"(\d+)\s*(triệu|tr|k)",
            r"khoảng\s+(\d+)",
            r"dưới\s+(\d+)",
            r"từ\s+(\d+)",
            r"tầm\s+(\d+)",
        ]
        
        for pattern in budget_patterns:
            matches = re.findall(pattern, user_message.lower())
            if matches:
                for match in matches:
                    amount = int(match[0]) if isinstance(match, tuple) else int(match)
                    unit = match[1] if isinstance(match, tuple) else "tr"
                    
                    if unit in ["tr", "triệu"]:
                        amount *= 1_000_000
                    elif unit == "k":
                        amount *= 1_000
                    
                    if constraints["budget_max"] is None or amount < constraints["budget_max"]:
                        constraints["budget_max"] = amount
        
        # Extract category
        electronics = ["laptop", "điện thoại", "phone", "máy tính", "tablet", "pc", "chuột", "bàn phím", "màn hình", "tai nghe"]
        books = ["sách", "truyện", "novel", "lightnovel", "light novel", "ebook", "book", "sách điện tử"]
        gifts = ["quà", "tặng", "hoa", "bánh", "thiệp", "mỹ phẩm", "nước hoa"]
        
        msg_lower = user_message.lower()
        
        detected_category = None
        for cat in electronics:
            if cat in msg_lower:
                detected_category = "electronics"
                break
        for cat in books:
            if cat in msg_lower:
                detected_category = "books"
                break
        for cat in gifts:
            if cat in msg_lower:
                detected_category = "gifts"
                break
        
        if detected_category:
            constraints["category"] = detected_category
            constraints["category_changed"] = True
        
        # Extract recipient
        recipients = {
            "người yêu|bạn gái|bạn trai": "partner",
            "vợ|chồng": "spouse",
            "mẹ|bố|cha": "parent",
            "bạn": "friend",
            "đồng nghiệp|sếp": "colleague"
        }
        
        for pattern, recipient_type in recipients.items():
            if re.search(pattern, msg_lower):
                constraints["recipient"] = recipient_type
                break
        
        # Extract occasion
        occasions = {
            "sinh nhật|đón sinh nhật": "birthday",
            "kỉ niệm|ngày": "anniversary",
            "Noel|christmas": "holiday",
            "Valentine": "valentine",
            "lễ|dạo": "celebration"
        }
        
        for pattern, occasion_type in occasions.items():
            if re.search(pattern, msg_lower):
                constraints["occasion"] = occasion_type
                break
        
        # Detect preferences
        preferences = {
            "mỏng nhẹ|nhẹ|gọn": "lightweight",
            "hiệu năng|nhanh|mượt": "performance",
            "pin|trâu": "battery",
            "đẹp|sang": "aesthetic",
            "giá rẻ|bộp|rẻ": "affordable",
            "bền|chắc": "durable"
        }
        
        for pattern, pref in preferences.items():
            if re.search(pattern, msg_lower):
                constraints["detected_preferences"].append(pref)
        
        # Extract brand exclusions for context persistence
        excluded_brands = []
        exclusion_trigger = re.search(r"không|tránh|ghét", msg_lower)
        if exclusion_trigger:
            brands_patterns = [
                (r"apple|macbook|iphone|ipad", "Apple"),
                (r"samsung|galaxy", "Samsung"),
                (r"huawei", "Huawei"),
                (r"xiaomi|redmi", "Xiaomi"),
                (r"sony", "Sony"),
                (r"microsoft|surface", "Microsoft"),
                (r"hp", "HP"),
                (r"\bdell\b", "Dell"),
                (r"lenovo|thinkpad", "Lenovo"),
                (r"acer", "Acer"),
                (r"asus|zenfone", "Asus"),
                (r"oneplus", "OnePlus"),
            ]
            for brand_pattern, brand_name in brands_patterns:
                if re.search(brand_pattern, msg_lower):
                    excluded_brands.append(brand_name)
        
        if excluded_brands:
            constraints["excluded_brands"] = excluded_brands
        
        return constraints
    
    def _detect_negative_feedback(self, user_message: str, current_state: Optional[DialogueState]) -> bool:
        """Detect if user is rejecting previous suggestion."""
        msg_lower = user_message.lower()
        negative_indicators = [
            "không hợp lý", "quá đắt", "không đúng ý", "không phải",
            "sai rồi", "không đó", "không ưa", "loại bỏ", "cái khác",
            "không muốn", "tránh", "ghét", "chê"
        ]
        
        return any(indicator in msg_lower for indicator in negative_indicators)
    
    def _reconcile_state(
        self,
        current_state: Optional[DialogueState],
        intent_result: Dict,
        constraints: Dict,
        is_negative_feedback: bool,
        user_message: str
    ) -> Optional[DialogueState]:
        """Reconcile and update dialogue state."""
        
        # Use state locally and ensure list fields are initialized
        state = current_state if current_state else DialogueState(session_id="temp")
        
        # Defensive initialization for JSON list fields
        if state.last_invalid_direction is None: state.last_invalid_direction = []
        if state.excluded_categories is None: state.excluded_categories = []
        if state.preferences is None: state.preferences = []
        if state.constraints is None: state.constraints = []
        
        # Update intent
        state.intent = intent_result["intent"]
        state.sub_intent = intent_result.get("sub_intent")
        state.confidence = intent_result.get("confidence", 0.5)
        
        # Handle category change
        if constraints.get("category_changed"):
            state.last_invalid_direction.append(state.product_category or "unknown")
            state.product_category = constraints["category"]
            # Clear old category's constraints
            state.budget_max = None
            state.excluded_categories = []
        
        # Update budget if provided
        if constraints.get("budget_max"):
            state.budget_max = constraints["budget_max"]
            state.budget_currency = "VND"
        
        # Update recipient
        if constraints.get("recipient"):
            state.recipient = constraints["recipient"]
        
        # Update occasion
        if constraints.get("occasion"):
            state.occasion = constraints["occasion"]
        
        # Update preferences
        if constraints.get("detected_preferences"):
            state.preferences = list(set((state.preferences or []) + constraints["detected_preferences"]))
        
        # CRITICAL: Merge excluded brands through turns for context persistence
        if constraints.get("excluded_brands"):
            current_excluded = state.excluded_categories or []
            new_excluded = list(set(current_excluded + constraints["excluded_brands"]))
            state.excluded_categories = new_excluded
        
        # Mark negative feedback
        if is_negative_feedback:
            state.last_feedback_was_negative = True
            state.last_invalid_direction.append(state.latest_user_goal or "previous_suggestion")
        
        # Update latest goal
        state.latest_user_goal = user_message[:200]
        
        return state
    
    def _decide_tool_routing(
        self,
        intent: str,
        user_message: str,
        state: Optional[DialogueState]
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Decide if a tool (web search) is needed."""
        msg_lower = user_message.lower()
        
        # ✅ ALWAYS use product_search for product recommendations
        # This is the KEY fix - product_recommendation (default) must use product_search
        # Specific intents get precedence for better query generation
        if intent in ["product_recommendation", "gift_recommendation", "product_comparison"]:
            search_context = {
                "query": user_message,
                "category": state.product_category if state else "electronics",
                "budget_max": state.budget_max if state else None,
                "excluded_brands": state.excluded_categories if state else [],
            }
            return True, "product_search", json.dumps(search_context)
        
        elif intent == "budget_advice":
            search_context = {
                "query": f"Smartphone gaming {state.budget_max if state and state.budget_max else '15 million'} VND gaming phone",
                "category": state.product_category if state else "electronics",
                "budget_max": state.budget_max if state else 30_000_000,
                "excluded_brands": state.excluded_categories if state else [],
            }
            return True, "product_search", json.dumps(search_context)
            
        elif intent == "price_lookup":
            return True, "product_search", json.dumps({"query": user_message})
        
        # Generic keyword fallback
        real_time_keywords = [
            "giá", "mua ở đâu", "shop", "khuyến mãi", "deal", "sale",
            "còn hàng", "tồn kho", "mã giảm", "ở đâu", "cửa hàng"
        ]
        
        if any(kw in msg_lower for kw in real_time_keywords):
            return True, "product_search", json.dumps({"query": user_message})
        
        elif state and state.need_real_time_data:
            return True, "product_search", json.dumps({"query": user_message})
        
        return False, None, None
    
    def _detect_query_specificity(
        self, 
        user_message: str, 
        state: Optional[DialogueState]
    ) -> Dict:
        """Classify query as broad, semi_specific, or specific.
        
        Returns:
            Dict with:
            - specificity: 'broad', 'semi_specific', or 'specific'
            - missing_info: list of missing fields
            - can_answer_now: bool indicating if we have enough to provide value
        """
        msg_lower = user_message.lower()
        specificity_score = 0
        missing_info = []
        
        # Check for product category (must-have for specificity)
        has_category = state and state.product_category
        if not has_category:
            missing_info.append("product_category")
            specificity_score -= 2
        else:
            specificity_score += 2
        
        # Check for budget (nice-to-have)
        has_budget = state and state.budget_max
        if not has_budget:
            missing_info.append("budget")
        else:
            specificity_score += 1
        
        # Check for recipient/occasion (nice-to-have for gifts)
        has_recipient = state and state.recipient
        has_occasion = state and state.occasion
        if not has_recipient and not has_occasion:
            missing_info.append("recipient_or_occasion")
        else:
            specificity_score += 1
        
        # Check for preferences (specific features/qualities)
        has_preferences = state and state.preferences and len(state.preferences) > 0
        if has_preferences:
            specificity_score += 1
        else:
            missing_info.append("specific_preferences")
        
        # Classify specificity
        if specificity_score >= 3:
            specificity = "specific"
        elif specificity_score >= 0:
            specificity = "semi_specific"
        else:
            specificity = "broad"
        
        # Determine if we can answer now
        can_answer_now = has_category  # Category is the minimum requirement
        
        return {
            "specificity": specificity,
            "missing_info": missing_info,
            "can_answer_now": can_answer_now,
            "specificity_score": specificity_score
        }
    
    def _is_blocking_missing_information(
        self, 
        specificity: str, 
        missing_info: List[str],
        state: Optional[DialogueState]
    ) -> bool:
        """Determine if missing information truly blocks providing an answer.
        
        Blocking: Absolutely need before recommending
        Non-blocking: Can recommend and let user refine
        
        Returns True if we MUST clarify, False if we can answer now
        """
        # Category is the only truly blocking missing information
        if "product_category" in missing_info:
            return True
        
        # If user asked "buy what?" with zero context, block
        if specificity == "broad" and len(missing_info) >= 3:
            return True
        
        # Everything else (budget, preferences, recipient, occasion) is NON-BLOCKING
        # We can provide grouped recommendations or generic suggestions
        return False
    
    def _enforce_answer_first_logic(
        self, 
        intent: str, 
        specificity: str,
        missing_info: List[str],
        can_answer_now: bool,
        is_blocking_missing: bool
    ) -> Dict:
        """Enforce answer-first behavior: always try to provide value immediately.
        
        Returns:
            Dict with:
            - should_answer_now: bool
            - max_follow_ups: int (0 to 1)
            - answer_format: str (grouped, direct, compare, clarify)
        """
        # If missing info is blocking, must clarify first
        if is_blocking_missing:
            return {
                "should_answer_now": False,
                "max_follow_ups": 1,
                "answer_format": "clarify",
                "reason": "Blocking information needed"
            }
        
        # If user said "buy what?" (ultra broad), still answer with grouped options
        if specificity == "broad" and can_answer_now:
            return {
                "should_answer_now": True,
                "max_follow_ups": 1,
                "answer_format": "grouped",
                "reason": "Provide grouped options then ask follow-up"
            }
        
        # If semi-specific, provide direct recommendations
        if specificity == "semi_specific":
            return {
                "should_answer_now": True,
                "max_follow_ups": 0,
                "answer_format": "direct",
                "reason": "Enough info for direct recommendations"
            }
        
        # If specific, provide detailed comparison
        if specificity == "specific":
            return {
                "should_answer_now": True,
                "max_follow_ups": 0,
                "answer_format": "compare",
                "reason": "Highly specific query, direct comparison"
            }
        
        return {
            "should_answer_now": True,
            "max_follow_ups": 1,
            "answer_format": "direct",
            "reason": "Default answer-first approach"
        }
    
    def _select_response_strategy(
        self,
        intent: str,
        state: Optional[DialogueState],
        is_negative_feedback: bool
    ) -> str:
        """Select response strategy based on context, now with specificity awareness."""
        
        if is_negative_feedback:
            return "ask_one_targeted_question"
        
        # Safety check: if state is None, return default strategy
        if state is None:
            return "direct_advice"
        
        # Detect query specificity
        specificity_result = self._detect_query_specificity(state.latest_user_goal or "", state)
        specificity = specificity_result["specificity"]
        missing_info = specificity_result["missing_info"]
        can_answer = specificity_result["can_answer_now"]
        
        # Check if missing info is blocking
        is_blocking_missing = self._is_blocking_missing_information(
            specificity, missing_info, state
        )
        
        # Enforce answer-first logic
        answer_first = self._enforce_answer_first_logic(
            intent, specificity, missing_info, can_answer, is_blocking_missing
        )
        
        # Map to response strategy based on answer format
        if answer_first["answer_format"] == "clarify":
            return "ask_one_targeted_question"
        elif answer_first["answer_format"] == "grouped":
            return "grouped_recommendation"
        elif answer_first["answer_format"] == "compare":
            return "compare_options"
        else:  # direct
            # Choose between direct_advice and tool-augmented based on intent
            if intent == "price_lookup":
                return "tool_augmented_recommendation"
            elif intent == "product_comparison":
                return "compare_options"
            return "direct_advice"
    
    def _validate_output(self, state: Optional[DialogueState]) -> Dict:
        """Validate state against business rules."""
        validation = {
            "budget_ok": True,
            "context_ok": True,
            "hallucination_risk": "low",
            "notes": []
        }
        
        if not state:
            return validation
        
        # Check budget is reasonable
        if state.budget_max and state.budget_max < 50_000:
            validation["notes"].append("Budget very low, considering minimal products")
        
        if state.budget_max and state.budget_max > 1_000_000_000:
            validation["budget_ok"] = False
            validation["notes"].append("Budget appears to be invalid")
        
        # Check context coherence
        if not state.intent:
            validation["context_ok"] = False
            validation["notes"].append("No clear intent detected")
        
        if state.confidence and state.confidence < 0.3:
            validation["hallucination_risk"] = "high"
            validation["notes"].append("Low confidence in understanding user intent")
        
        return validation
    
    def _save_state(self, state: DialogueState, db: Session) -> None:
        """Save state to database."""
        try:
            existing = db.query(DialogueState).filter(DialogueState.session_id == state.session_id).first()
            
            if existing:
                for key, value in vars(state).items():
                    if not key.startswith('_'):
                        setattr(existing, key, value)
                db.commit()
            else:
                db.add(state)
                db.commit()
        except Exception as e:
            print(f"[DialogueOrchestrator] Error saving state: {e}")
            db.rollback()


async def get_or_create_dialogue_state(session_id: str, db: Session) -> DialogueState:
    """Get existing dialogue state or create new one."""
    state = db.query(DialogueState).filter(DialogueState.session_id == session_id).first()
    
    if not state:
        state = DialogueState(
            session_id=session_id,
            intent=None,
            sub_intent=None,
            confidence=0.0,
            excluded_categories=[],
            preferences=[],
            constraints=[],
            last_invalid_direction=[]
        )
        db.add(state)
        db.commit()
        db.refresh(state)
    
    return state
