"""
Answer planning layer for grounded shopping responses.

The retrieval layer decides which products are relevant. This planner decides
what the assistant should say for each intent, then renders a deterministic
fallback answer. The LLM may polish this output, but the plan is the source of
truth for products, reasons, trade-offs, and conclusions.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from services.data_normalization import format_vnd, normalize_text


def build_answer_plan(retrieval: Dict, user_message: str = "") -> Dict:
    candidates = retrieval.get("candidates") or []
    if not candidates:
        return {}

    category = retrieval.get("category") or candidates[0].get("category")
    priorities = set(retrieval.get("priorities") or [])
    intent = retrieval.get("answer_mode") or "broad"

    if intent == "comparison":
        return _build_comparison_plan(candidates[:3], category, priorities)
    if intent == "spec_detail":
        return _build_detail_plan(candidates[0], category, priorities)
    if intent == "single_product":
        return _build_single_product_plan(candidates[0], category, priorities, user_message)
    return _build_recommendation_plan(retrieval, candidates, category, priorities)


def render_answer_plan(plan: Dict) -> str:
    if not plan:
        return ""

    intent = plan.get("intent")
    if intent == "comparison":
        return _render_comparison(plan)
    if intent == "detail":
        return _render_detail(plan)
    if intent == "single_product":
        return _render_single_product(plan)
    return _render_recommendation(plan)


def _build_recommendation_plan(retrieval: Dict, candidates: List[Dict], category: Optional[str], priorities: set) -> Dict:
    best = candidates[0]
    answer_mode = retrieval.get("answer_mode") or "broad"
    group_limit = 2 if answer_mode == "brand_constrained" else (3 if len(priorities) >= 4 else 5)
    alternatives = candidates[1 : 1 + group_limit]

    budget_target = retrieval.get("budget_target") or retrieval.get("budget_max")
    return {
        "intent": "recommendation",
        "category": category,
        "heading": _heading(category, priorities),
        "best": _product_summary(best, category, priorities, budget_target),
        "alternatives": [
            _product_summary(item, category, priorities, budget_target)
            for item in alternatives
            if _is_reasonable_alternative(item, retrieval)
        ],
        "checklist": _checklist(category, priorities),
    }


def _build_single_product_plan(item: Dict, category: Optional[str], priorities: set, user_message: str) -> Dict:
    return {
        "intent": "single_product",
        "category": category,
        "product": _product_summary(item, category, priorities, None),
        "decision": _buying_decision(item, category, priorities, user_message),
        "checklist": _checklist(category, priorities),
    }


def _build_detail_plan(item: Dict, category: Optional[str], priorities: set) -> Dict:
    detail = item.get("detail_profile") or {}
    configuration = detail.get("configuration") if isinstance(detail, dict) else {}
    performance = detail.get("performance_profile") if isinstance(detail, dict) else {}
    advice = detail.get("buying_advice") if isinstance(detail, dict) else {}
    snapshot = item.get("spec_snapshot") or {}
    spec_rows = _ordered_spec_snapshot(snapshot if isinstance(snapshot, dict) else {}, category)
    config_rows = _ordered_config(configuration if isinstance(configuration, dict) else {}, category)
    if spec_rows:
        spec_labels = {label for label, _value in spec_rows}
        config_rows = [(label, value) for label, value in config_rows if label not in spec_labels]

    return {
        "intent": "detail",
        "category": category,
        "product": _product_summary(item, category, priorities, None),
        "positioning": _clean(detail.get("positioning") or item.get("description")),
        "spec_snapshot": spec_rows,
        "variant_note": _clean(snapshot.get("variant_note")) if isinstance(snapshot, dict) else "",
        "configuration": config_rows,
        "configuration_analysis": _configuration_analysis(item, category),
        "performance": _ordered_performance(performance if isinstance(performance, dict) else {}, category),
        "choose_if": _as_list(advice.get("choose_if") if isinstance(advice, dict) else []),
        "avoid_if": _as_list(advice.get("avoid_if") if isinstance(advice, dict) else []),
        "verify": _as_list(advice.get("verify") if isinstance(advice, dict) else []),
    }


def _build_comparison_plan(items: List[Dict], category: Optional[str], priorities: set) -> Dict:
    winner = _choose_winner(items, category, priorities)
    priority_text = _priority_text(priorities)
    rows = [_comparison_product_row(item, category, priorities) for item in items]
    takeaways = _comparison_takeaways(items, category, priorities)

    return {
        "intent": "comparison",
        "category": category,
        "priority_text": priority_text,
        "winner": winner.get("name") if winner else items[0].get("name"),
        "products": rows,
        "criterion_rows": _comparison_criterion_rows(items, category),
        "decision_lines": _comparison_decision_lines(items, category, priorities, winner),
        "takeaways": takeaways,
        "similarities": _comparison_similarities(items, category),
        "checklist": _checklist(category, priorities),
    }


def _render_recommendation(plan: Dict) -> str:
    best = plan["best"]
    lines = [
        f"{plan['heading']}:",
        "",
        f"Mình sẽ ưu tiên: {best['name']} - {best['price']}",
        f"- Vì sao hợp với bạn: {best['reason']}. {best['fit']}.",
        f"- Điểm nổi bật: {best['strengths']}.",
        f"- Đánh giá nhanh: {best['sales_analysis']}.",
    ]
    if best.get("buyer_note"):
        lines.append(f"- Lưu ý khi chốt mua: {best['buyer_note']}.")
    lines.append(f"- Link kiểm tra nhanh: {best['url']}")

    if plan.get("alternatives"):
        lines.append("")
        lines.append("Một vài lựa chọn khác đáng cân nhắc:")
        for index, item in enumerate(plan["alternatives"], 1):
            lines.append(
                f"{index}. {item['name']} - {item['price']}: {item['recommendation_blurb']}"
            )

    lines.append(plan["checklist"])
    return "\n".join(lines)


def _render_single_product(plan: Dict) -> str:
    product = plan["product"]
    decision = plan["decision"]
    lines = [
        f"Về {product['name']}: {decision['summary']}",
        f"- Giá tham khảo trong catalog: {product['price']}.",
        f"- Phù hợp khi: {product['fit']}.",
        f"- Điểm nổi bật: {product['strengths']}.",
        f"- Đánh giá nhanh: {product['sales_analysis']}.",
    ]
    if decision.get("recommendation"):
        lines.append(f"- Kết luận: {decision['recommendation']}.")
    lines.append(f"- Link kiểm tra nhanh: {product['url']}")
    lines.append(plan["checklist"])
    return "\n".join(lines)


def _render_detail(plan: Dict) -> str:
    product = plan["product"]
    lines = [
        f"{product['name']} - cấu hình và đánh giá nhanh:",
        "",
        f"- Giá tham khảo trong catalog: {product['price']}.",
        f"- Nhóm sản phẩm: {plan.get('positioning') or product['fit']}.",
    ]

    if plan.get("spec_snapshot"):
        lines.append("")
        lines.append("Thông số chính:")
        for label, value in plan["spec_snapshot"]:
            lines.append(f"  - {label}: {value}.")

    if plan.get("configuration_analysis"):
        lines.append("")
        lines.append("Đánh giá theo trải nghiệm mua:")
        for item in plan["configuration_analysis"]:
            lines.append(f"  - {item}")

    if plan.get("performance"):
        focused = _focused_performance_notes(plan["performance"], plan.get("category"))
        if focused and plan.get("category") != "phone":
            lines.append("")
            lines.append("Nhu cầu phù hợp:")
            for item in focused:
                lines.append(f"  - {item}")

    if plan.get("choose_if"):
        lines.append("")
        lines.append(f"Nên cân nhắc nếu: {_join(plan['choose_if'])}.")
    if plan.get("verify"):
        lines.append(f"Trước khi chốt mua nên kiểm tra: {_join(plan['verify'])}.")
    if plan.get("variant_note"):
        lines.append(f"Ghi chú SKU: {plan['variant_note']}.")
    lines.append(f"Link kiểm tra nhanh: {product['url']}")
    return "\n".join(lines)


def _render_comparison(plan: Dict) -> str:
    lines = [
        f"Nếu xét theo {plan['priority_text']}, mình nghiêng về {plan['winner']}.",
        "Mình sẽ so theo thông số và vai trò sử dụng để bạn thấy rõ hai mẫu khác nhau ở đâu:",
        "",
        "Thông số chính:",
    ]
    for product in plan["products"]:
        lines.append(f"- {product['name']} ({product['price']}): {product['spec_line']}")
        lines.append(f"  Hợp nhất khi: {product['role']}")

    if plan.get("takeaways") and not plan.get("criterion_rows"):
        lines.append("")
        lines.append("Khác biệt đáng chú ý:")
        for item in plan["takeaways"]:
            lines.append(f"- {item}")

    if plan.get("similarities"):
        lines.append("")
        lines.append("Điểm tương đồng:")
        for item in plan["similarities"]:
            lines.append(f"- {item}")

    lines.append(
        f"Kết luận: chọn {plan['winner']} nếu bạn muốn phương án cân bằng nhất theo {plan['priority_text']}. "
        "Nếu mẫu còn lại có ưu thế đúng với nhu cầu riêng của bạn, ví dụ pin lớn hơn, màn hình hợp mắt hơn hoặc giá thực tế tốt hơn, thì mẫu đó vẫn đáng chọn."
    )
    lines.append(plan["checklist"])
    return "\n".join(lines)


def _render_comparison(plan: Dict) -> str:
    """Render comparisons as real side-by-side buying advice."""
    lines = [
        f"Kết luận nhanh: nếu xét theo {plan['priority_text']}, mình nghiêng về {plan['winner']}.",
        "Nhưng hai mẫu này nên so theo từng tiêu chí, vì mỗi máy mạnh ở một kiểu dùng khác nhau:",
        "",
        "Thông số chính:",
    ]
    for product in plan["products"]:
        lines.append(f"- {product['name']} ({product['price']}): {product['spec_line']}")
        lines.append(f"  Hợp nhất khi: {product['role']}")

    if plan.get("criterion_rows"):
        lines.append("")
        lines.append("So sánh trực tiếp:")
        for item in plan["criterion_rows"]:
            lines.append(f"- {item}")

    if plan.get("takeaways") and not plan.get("criterion_rows"):
        lines.append("")
        lines.append("Khác biệt đáng chú ý:")
        for item in plan["takeaways"]:
            lines.append(f"- {item}")

    if plan.get("similarities"):
        lines.append("")
        lines.append("Điểm tương đồng:")
        for item in plan["similarities"]:
            lines.append(f"- {item}")

    if plan.get("decision_lines"):
        lines.append("")
        lines.append("Chọn theo nhu cầu:")
        for item in plan["decision_lines"]:
            lines.append(f"- {item}")

    lines.append(
        f"Kết luận: chọn {plan['winner']} nếu đó là nhóm ưu tiên chính của bạn; "
        "nếu nhu cầu lệch sang tiêu chí mà mẫu còn lại mạnh hơn thì nên chọn theo tiêu chí đó."
    )
    lines.append(plan["checklist"])
    return "\n".join(lines)


def _product_summary(item: Dict, category: Optional[str], priorities: set, budget_target: Optional[float]) -> Dict:
    tags = {normalize_text(tag) for tag in item.get("tags", [])}
    strengths = _as_list(item.get("strengths"))
    strengths = _filter_strengths_for_priorities(strengths, priorities)
    weaknesses = _as_list(item.get("weaknesses"))
    avoid_if = _as_list(item.get("avoid_if"))
    avoid_if = _filter_budget_specific_notes(avoid_if, budget_target)
    matched = sorted((tags & priorities) - {"phone", "laptop"})

    reasons = []
    if budget_target and item.get("price") is not None:
        try:
            price = float(item.get("price"))
            if price <= budget_target:
                reasons.append(f"nằm trong ngân sách {_price(budget_target)}")
            elif price <= budget_target * 1.15:
                reasons.append("có thể chạm ngân sách nếu săn sale/chọn cấu hình thấp")
        except (TypeError, ValueError):
            pass
    if matched:
        reasons.append("khớp nhu cầu " + ", ".join(_tag_label(tag) for tag in matched))
    if not reasons:
        reasons.append("có điểm phù hợp cao nhất trong dữ liệu hiện có")

    return {
        "name": item.get("name", "Unknown"),
        "price": _price(item.get("price")) if item.get("price") is not None else "chưa rõ giá",
        "fit": _fit_for_query(item, category, priorities),
        "reason": ", ".join(reasons),
        "strengths": _join(strengths[:3], "phù hợp nhu cầu chính"),
        "tradeoffs": _join(weaknesses[:3], "cần kiểm tra thêm theo nhu cầu thực tế"),
        "buyer_note": _buyer_note(weaknesses, item),
        "sales_analysis": _sales_analysis(item, category, matched),
        "sales_pitch": _sales_pitch(item, category, matched),
        "recommendation_blurb": _recommendation_blurb(item, category, matched, budget_target),
        "avoid_if": _join(avoid_if[:2], ""),
        "short_strength": _clean(strengths[0]) if strengths else "nhu cầu chính",
        "short_tradeoff": _clean(weaknesses[0]) if weaknesses else "giá/cấu hình thực tế",
        "url": item.get("url") or "",
        "tags": tags,
        "raw": item,
    }


def _comparison_criterion_rows(items: List[Dict], category: Optional[str]) -> List[str]:
    if len(items) < 2:
        return []
    if category == "phone":
        return _phone_comparison_criterion_rows(items[0], items[1])
    if category == "laptop":
        return _laptop_comparison_criterion_rows(items[0], items[1])
    return []


def _phone_comparison_criterion_rows(first: Dict, second: Dict) -> List[str]:
    first_snapshot = first.get("spec_snapshot") or {}
    second_snapshot = second.get("spec_snapshot") or {}
    if not isinstance(first_snapshot, dict) or not isinstance(second_snapshot, dict):
        return []

    first_name = first.get("name", "Mẫu 1")
    second_name = second.get("name", "Mẫu 2")
    rows = []

    first_chip = first_snapshot.get("chipset")
    second_chip = second_snapshot.get("chipset")
    if first_chip and second_chip:
        better = _better_phone_chip(first, second)
        verdict = f"{better.get('name')} có lợi thế hiệu năng" if better else "hai mẫu khá gần nhau về hiệu năng"
        rows.append(
            f"Hiệu năng/chip: {first_name} dùng {first_chip}; {second_name} dùng {second_chip}. {verdict}, nhất là khi chơi game hoặc dùng lâu dài."
        )

    first_battery = first_snapshot.get("battery")
    second_battery = second_snapshot.get("battery")
    if first_battery and second_battery:
        better = _larger_numeric_spec(first, second, "battery")
        verdict = f"{better.get('name')} nhỉnh hơn về pin" if better else "pin tương đối khó kết luận nếu chưa xem test thực tế"
        rows.append(f"Pin: {first_name} {first_battery}; {second_name} {second_battery}. {verdict}.")

    first_display = first_snapshot.get("display")
    second_display = second_snapshot.get("display")
    if first_display and second_display:
        first_size = _first_number(first_display)
        second_size = _first_number(second_display)
        if first_size and second_size and abs(first_size - second_size) >= 0.2:
            larger = first_name if first_size > second_size else second_name
            smaller = second_name if larger == first_name else first_name
            rows.append(
                f"Màn hình/cầm nắm: {first_name} {first_display}; {second_name} {second_display}. {larger} hợp xem nội dung/chơi game hơn, còn {smaller} gọn và dễ cầm hơn."
            )
        else:
            rows.append(f"Màn hình: {first_name} {first_display}; {second_name} {second_display}. Cả hai đều thuộc nhóm màn hình cao cấp, nên cần xem thêm độ sáng/màu thực tế.")

    first_camera = first_snapshot.get("camera")
    second_camera = second_snapshot.get("camera")
    if first_camera and second_camera:
        camera_winner = _better_phone_camera(first, second)
        if camera_winner:
            rows.append(
                f"Camera: {first_name} {first_camera}; {second_name} {second_camera}. {camera_winner.get('name')} đáng ưu tiên hơn nếu bạn chụp/quay nhiều."
            )
        else:
            rows.append(f"Camera: {first_name} {first_camera}; {second_name} {second_camera}. Nên xem thêm ảnh mẫu vì thông số chưa nói hết chất lượng xử lý ảnh.")

    first_storage = first_snapshot.get("storage")
    second_storage = second_snapshot.get("storage")
    if first_storage and second_storage and normalize_text(first_storage) != normalize_text(second_storage):
        rows.append(f"Bộ nhớ: {first_name} có {first_storage}; {second_name} có {second_storage}. Mẫu có tùy chọn bộ nhớ cao hơn hợp hơn nếu bạn quay video, lưu game hoặc dùng lâu dài.")

    return rows[:5]


def _laptop_comparison_criterion_rows(first: Dict, second: Dict) -> List[str]:
    first_snapshot = first.get("spec_snapshot") or {}
    second_snapshot = second.get("spec_snapshot") or {}
    if not isinstance(first_snapshot, dict) or not isinstance(second_snapshot, dict):
        return []

    first_name = first.get("name", "Mẫu 1")
    second_name = second.get("name", "Mẫu 2")
    rows = []
    for label, key in [("CPU", "cpu"), ("GPU", "gpu"), ("RAM/lưu trữ", "ram"), ("Màn hình", "display"), ("Pin/cân nặng", "battery")]:
        first_value = first_snapshot.get(key)
        second_value = second_snapshot.get(key)
        if first_value and second_value and normalize_text(first_value) != normalize_text(second_value):
            rows.append(f"{label}: {first_name} {first_value}; {second_name} {second_value}. Cần xem review đúng SKU để biết hiệu năng duy trì, nhiệt độ và độ ồn.")
    return rows[:5]


def _comparison_decision_lines(
    items: List[Dict],
    category: Optional[str],
    priorities: set,
    winner: Optional[Dict],
) -> List[str]:
    if len(items) < 2:
        return []
    if category == "phone":
        return _phone_comparison_decision_lines(items[0], items[1], priorities, winner)
    if category == "laptop":
        winner_name = winner.get("name") if winner else items[0].get("name")
        return [
            f"Chọn {winner_name} nếu tiêu chí chính là hiệu năng/tổng thể theo nhu cầu bạn nêu.",
            "Nếu ưu tiên di động, pin, màn hình hoặc giá thực tế hơn, hãy đối chiếu từng SKU và review nhiệt độ trước khi chốt.",
        ]
    return []


def _phone_comparison_decision_lines(
    first: Dict,
    second: Dict,
    priorities: set,
    winner: Optional[Dict],
) -> List[str]:
    winner_name = winner.get("name") if winner else first.get("name")
    lines = []
    performance_winner = _better_phone_chip(first, second)
    battery_winner = _larger_numeric_spec(first, second, "battery")
    camera_winner = _better_phone_camera(first, second)

    if performance_winner:
        lines.append(f"Chơi game/hiệu năng: chọn {performance_winner.get('name')} vì chip mạnh hơn là lợi thế rõ nhất khi chơi lâu hoặc giữ FPS ổn định.")
    if battery_winner:
        lines.append(f"Pin/dùng lâu: chọn {battery_winner.get('name')} nếu bạn ưu tiên thời lượng pin và ít phải sạc.")
    if camera_winner:
        lines.append(f"Camera/quay chụp: chọn {camera_winner.get('name')} nếu ảnh, video và độ đa dụng camera quan trọng.")

    first_display = (first.get("spec_snapshot") or {}).get("display")
    second_display = (second.get("spec_snapshot") or {}).get("display")
    first_size = _first_number(first_display)
    second_size = _first_number(second_display)
    if first_size and second_size and abs(first_size - second_size) >= 0.2:
        compact = first if first_size < second_size else second
        large = second if compact is first else first
        lines.append(f"Gọn nhẹ/dễ cầm: chọn {compact.get('name')}; xem phim/chơi game màn lớn hơn thì {large.get('name')} hợp hơn.")

    if not lines:
        lines.append(f"Chọn {winner_name} nếu bạn muốn phương án cân bằng nhất theo dữ liệu hiện có.")
    return lines[:4]


def _better_phone_chip(first: Dict, second: Dict) -> Optional[Dict]:
    first_rank = _phone_chip_rank((first.get("spec_snapshot") or {}).get("chipset"))
    second_rank = _phone_chip_rank((second.get("spec_snapshot") or {}).get("chipset"))
    if first_rank == second_rank:
        return None
    return first if first_rank > second_rank else second


def _phone_chip_rank(value: object) -> int:
    normalized = normalize_text(value)
    ranks = [
        ("snapdragon 8 elite", 100),
        ("dimensity 9400", 96),
        ("snapdragon 8 gen 3", 92),
        ("snapdragon 8s gen 3", 84),
        ("dimensity 8400", 82),
        ("dimensity 8300", 80),
        ("snapdragon 7", 70),
        ("exynos 1480", 65),
    ]
    for token, rank in ranks:
        if token in normalized:
            return rank
    return 0


def _larger_numeric_spec(first: Dict, second: Dict, key: str) -> Optional[Dict]:
    first_value = _first_number((first.get("spec_snapshot") or {}).get(key))
    second_value = _first_number((second.get("spec_snapshot") or {}).get(key))
    if first_value is None or second_value is None or first_value == second_value:
        return None
    return first if first_value > second_value else second


def _better_phone_camera(first: Dict, second: Dict) -> Optional[Dict]:
    first_score = _phone_camera_score((first.get("spec_snapshot") or {}).get("camera"))
    second_score = _phone_camera_score((second.get("spec_snapshot") or {}).get("camera"))
    if first_score == second_score:
        return None
    return first if first_score > second_score else second


def _phone_camera_score(value: object) -> int:
    normalized = normalize_text(value)
    score = 0
    score += normalized.count("50mp") * 2
    if "telephoto" in normalized or "periscope" in normalized:
        score += 2
    if "ultrawide" in normalized:
        score += 1
    if "8mp ultrawide" in normalized:
        score -= 1
    return score


def _comparison_product_row(item: Dict, category: Optional[str], priorities: set) -> Dict:
    return {
        "name": item.get("name", "Unknown"),
        "price": _price(item.get("price")) if item.get("price") is not None else "chưa rõ giá",
        "role": _comparison_role(item, category, priorities),
        "spec_line": _comparison_spec_line(item, category),
    }


def _comparison_role(item: Dict, category: Optional[str], priorities: set) -> str:
    if category == "laptop":
        name = normalize_text(item.get("name"))
        tags = {normalize_text(tag) for tag in item.get("tags", [])}
        if "loq" in name and "rtx" in tags:
            return "hợp hơn nếu bạn ưu tiên hiệu năng/giá, chơi game và tác vụ đồ họa trong ngân sách hợp lý; cần kiểm tra đúng GPU, TGP, RAM/SSD và màn hình."
        if "zephyrus g14" in name:
            return "hợp hơn nếu bạn muốn máy cao cấp, gọn hơn laptop gaming phổ thông và vẫn cần hiệu năng mạnh; đổi lại giá cao hơn và cấu hình GPU/nâng cấp phải kiểm tra kỹ."
        if "legion" in name:
            return "hợp nếu bạn ưu tiên hiệu năng duy trì, tản nhiệt và trải nghiệm gaming nghiêm túc; cần kiểm tra đúng SKU CPU/GPU vì dòng Legion có nhiều cấu hình bán ra."
    detail = item.get("detail_profile") or {}
    role = detail.get("positioning") or item.get("description")
    strengths = _as_list(item.get("strengths"))
    weaknesses = _as_list(item.get("weaknesses"))
    return f"hợp khi {_clean(role)}; mạnh ở {_join(strengths[:2], 'nhu cầu chính')}; cần cân nhắc {_join(weaknesses[:2], 'cấu hình thực tế')}."


def _sales_analysis(item: Dict, category: Optional[str], matched_tags: List[str]) -> str:
    tags = {normalize_text(tag) for tag in item.get("tags", [])}
    name = normalize_text(item.get("name"))

    if category == "phone":
        parts = []
        if "gaming" in matched_tags:
            parts.append("hiệu năng là điểm đáng chú ý, hợp người ưu tiên độ mượt và chơi game")
        elif "performance" in matched_tags:
            parts.append("hiệu năng là điểm đáng chú ý, hợp người ưu tiên độ mượt và phản hồi nhanh khi dùng hằng ngày")
        if "battery" in tags:
            parts.append("pin là lợi thế cho nhu cầu dùng lâu trong ngày")
        if "display" in tags:
            if "gaming" in matched_tags:
                parts.append("màn hình tốt giúp trải nghiệm game, phim và thao tác hằng ngày dễ chịu hơn")
            else:
                parts.append("màn hình tốt giúp xem phim, đọc nội dung và thao tác hằng ngày dễ chịu hơn")
        if "camera" in tags and "camera" in matched_tags:
            parts.append("camera là điểm cộng nếu bạn chụp/quay thường xuyên")
        if "premium" in tags:
            parts.append("trải nghiệm tổng thể thuộc nhóm cao hơn máy phổ thông")
        return "; ".join(parts[:3]) or "đây là lựa chọn cân bằng, phù hợp nếu giá thực tế đang tốt và đúng phiên bản bạn cần"

    if category == "laptop":
        parts = []
        if "rtx 5090" in name:
            parts.append("RTX 5090 là lựa chọn mạnh nhất trong catalog hiện tại, phù hợp mục tiêu chơi game nặng ở thiết lập cao")
        elif "rtx 4080" in name:
            parts.append("RTX 4080 thuộc nhóm rất mạnh, hợp người muốn hiệu năng gaming cao và dùng lâu dài")
        elif "rtx 4070" in name:
            if "creator" in matched_tags:
                parts.append("RTX 4070 là điểm hấp dẫn nhất, hợp game nặng, đồ họa và tác vụ cần GPU")
            else:
                parts.append("RTX 4070 là điểm hấp dẫn nhất, hợp game nặng và thiết lập đồ họa cao")
        elif "rtx 4060" in name:
            parts.append("RTX 4060 tạo cân bằng tốt giữa hiệu năng và chi phí")
        elif "rtx" in tags:
            parts.append("GPU rời giúp máy vượt xa laptop văn phòng ở game và đồ họa")
        if "gaming" in tags:
            parts.append("hợp người cần hiệu năng duy trì, tản nhiệt và trải nghiệm game ổn định")
        if "creator" in tags and "creator" in matched_tags:
            parts.append("phù hợp thêm cho dựng video, thiết kế, lập trình hoặc đa nhiệm nặng")
        if "lightweight" in tags:
            parts.append("thiết kế gọn hơn giúp dễ mang theo hơn nhóm gaming truyền thống")
        if "office" in tags and "office" in matched_tags:
            parts.append("phù hợp làm việc, học tập, họp online và dùng hằng ngày")
        return "; ".join(parts[:3]) or "đây là lựa chọn đáng cân nhắc nếu cấu hình bán ra khớp đúng nhu cầu"

    return "đây là lựa chọn đáng cân nhắc nếu giá thực tế và bảo hành phù hợp"


def _filter_strengths_for_priorities(strengths: List[str], priorities: set) -> List[str]:
    if not strengths:
        return strengths
    if "gaming" in priorities and not ({"creator", "coding", "ai_work"} & priorities):
        filtered = []
        for strength in strengths:
            normalized = normalize_text(strength)
            if any(token in normalized for token in ["do hoa", "dung video", "lap trinh", "da nhiem nang"]):
                continue
            filtered.append(strength)
        return filtered or strengths
    if "office" in priorities and not ({"gaming", "creator"} & priorities):
        filtered = []
        for strength in strengths:
            normalized = normalize_text(strength)
            if any(token in normalized for token in ["game", "gpu", "render"]):
                continue
            filtered.append(strength)
        return filtered or strengths
    return strengths


def _fit_for_query(item: Dict, category: Optional[str], priorities: set) -> str:
    tags = {normalize_text(tag) for tag in item.get("tags", [])}
    name = normalize_text(item.get("name"))

    if category == "laptop":
        if "max_performance" in priorities:
            if "rtx 5090" in name or "rtx 4080" in name:
                return "phù hợp khi bạn muốn cấu hình laptop gaming thuộc nhóm rất mạnh trong catalog, ưu tiên GPU, tản nhiệt, màn hình và hiệu năng duy trì hơn giá bán"
            return "phù hợp khi bạn muốn laptop gaming hiệu năng cao và không đặt nặng yếu tố giá"
        if "gaming" in priorities:
            return "phù hợp khi mục tiêu chính là chơi game, cần GPU rời, tản nhiệt ổn và hiệu năng duy trì khi chạy tải nặng"
        if "creator" in priorities:
            return "phù hợp khi bạn làm đồ họa, dựng video, render hoặc các tác vụ cần CPU/GPU/RAM mạnh"
        if "office" in priorities:
            return "phù hợp khi bạn ưu tiên làm việc văn phòng, học tập, họp online, pin và độ ổn định hằng ngày"

    if category == "phone":
        if "gaming" in priorities:
            return "phù hợp khi bạn ưu tiên chơi game, độ mượt, pin và khả năng giữ hiệu năng trong thời gian dài"
        if "camera" in priorities:
            return "phù hợp khi bạn ưu tiên chụp ảnh/quay video và trải nghiệm camera"
        if "battery" in priorities:
            return "phù hợp khi bạn cần pin tốt, dùng lâu trong ngày và trải nghiệm ổn định"

    return _clean(item.get("description"))


def _sales_pitch(item: Dict, category: Optional[str], matched_tags: List[str]) -> str:
    analysis = _sales_analysis(item, category, matched_tags)
    return analysis[0].upper() + analysis[1:] if analysis else "Đáng cân nhắc nếu giá thực tế tốt"


def _buyer_note(weaknesses: List[str], item: Dict) -> str:
    verify_terms = []
    notes = (item.get("decision_notes") or {}).get("verify_before_buying") if isinstance(item.get("decision_notes"), dict) else []
    verify_terms.extend(_as_list(notes)[:2])
    if not verify_terms:
        verify_terms.extend(_as_list(weaknesses)[:1])
    if not verify_terms:
        return "kiểm tra giá hiện tại, đúng phiên bản và bảo hành"
    return _join(verify_terms, "kiểm tra giá hiện tại, đúng phiên bản và bảo hành")


def _generic_recommendation_notes(
    item: Dict,
    category: Optional[str],
    matched_tags: List[str],
    source: Dict,
) -> List[str]:
    if not isinstance(source, dict) or not source:
        return []

    facts = _product_fact_cards(item, category, matched_tags, source)
    if not facts:
        return []

    lead_kind = _lead_fact_kind(item, category, matched_tags, source, facts)
    ordered = _order_facts(facts, lead_kind, item.get("name"))
    return [_render_fact_card(card, item.get("name")) for card in ordered[:4]]


def _product_fact_cards(item: Dict, category: Optional[str], matched_tags: List[str], source: Dict) -> List[Dict]:
    cards: List[Dict] = []
    if category == "phone":
        name = normalize_text(item.get("name"))
        chipset = source.get("chipset")
        ram = source.get("ram") or _extract_before_semicolon(source.get("ram_storage"))
        storage = source.get("storage")
        display = source.get("display") or source.get("screen")
        battery = source.get("battery")
        charging = source.get("charging")
        camera = source.get("camera")
        os_name = source.get("os") or source.get("software")

        if "redmagic" in name or "rog phone" in name:
            cards.append({"kind": "gaming_phone", "value": item.get("name", "mẫu gaming phone")})
        if chipset:
            value = f"{chipset}" + (f", RAM {ram}" if ram else "")
            cards.append({"kind": "performance", "value": value})
        if battery:
            value = str(battery)
            if charging:
                value += f", sạc {charging}"
            cards.append({"kind": "battery", "value": value})
        if display:
            cards.append({"kind": "display", "value": str(display)})
        if camera:
            cards.append({"kind": "camera", "value": str(camera)})
        if storage:
            cards.append({"kind": "storage", "value": str(storage)})
        if os_name:
            cards.append({"kind": "software", "value": str(os_name)})

    elif category == "laptop":
        cpu = source.get("cpu")
        gpu = source.get("gpu")
        ram = source.get("ram")
        storage = source.get("storage")
        display = source.get("display")
        battery = source.get("battery")
        weight = source.get("weight")

        if gpu:
            cards.append({"kind": "gpu", "value": str(gpu)})
        if cpu:
            cards.append({"kind": "cpu", "value": str(cpu)})
        if ram or storage:
            cards.append({"kind": "memory", "value": ", ".join(part for part in [ram, storage] if part)})
        if display:
            cards.append({"kind": "display", "value": str(display)})
        if battery or weight:
            cards.append({"kind": "mobility", "value": ", ".join(part for part in [weight, battery] if part)})

    for card in cards:
        card["matched_tags"] = list(matched_tags or [])
    return cards


def _lead_fact_kind(
    item: Dict,
    category: Optional[str],
    matched_tags: List[str],
    source: Dict,
    facts: List[Dict],
) -> str:
    tags = {normalize_text(tag) for tag in item.get("tags", [])}
    price = item.get("price")
    battery_size = _first_number(source.get("battery"))
    display_text = normalize_text(source.get("display") or source.get("screen"))
    weight = _first_number(source.get("weight"))
    name = normalize_text(item.get("name"))

    if category == "phone":
        if "gaming" in tags and ("redmagic" in name or "rog phone" in name):
            return "gaming_phone"
        if battery_size and battery_size >= 6500:
            return "battery"
        if "144hz" in display_text or "144 hz" in display_text:
            return "display"
        if source.get("charging") and "wireless" in normalize_text(source.get("charging")):
            return "battery"
        if "camera" in matched_tags:
            return "camera"
        if "gaming" in matched_tags or "performance" in matched_tags:
            return "performance"

    if category == "laptop":
        if weight and weight <= 1.6:
            return "mobility"
        if "oled" in display_text or "240hz" in display_text or "165hz" in display_text:
            return "display"
        try:
            if price is not None and float(price) <= 30_000_000:
                return "gpu" if any(card["kind"] == "gpu" for card in facts) else "cpu"
        except (TypeError, ValueError):
            pass
        if "gaming" in matched_tags or "creator" in matched_tags:
            return "gpu" if any(card["kind"] == "gpu" for card in facts) else "cpu"
        if "office" in matched_tags:
            return "mobility" if any(card["kind"] == "mobility" for card in facts) else "display"

    return facts[_stable_variant_index(item.get("name"), len(facts))]["kind"]


def _order_facts(facts: List[Dict], lead_kind: str, product_name: object) -> List[Dict]:
    by_kind = {card["kind"]: card for card in facts}
    ordered = []
    if lead_kind in by_kind:
        ordered.append(by_kind[lead_kind])

    remaining = [card for card in facts if card["kind"] != lead_kind]
    if remaining:
        offset = _stable_variant_index(product_name, len(remaining))
        remaining = remaining[offset:] + remaining[:offset]
    ordered.extend(remaining)
    return ordered


def _render_fact_card(card: Dict, product_name: object) -> str:
    kind = card.get("kind")
    value = card.get("value")
    variant = _stable_variant_index(f"{product_name}-{kind}", 3)
    matched_tags = set(card.get("matched_tags") or [])
    is_gaming_context = "gaming" in matched_tags
    templates = {
        "performance": [
            f"hiệu năng là trọng tâm với {value}, hợp nhu cầu cần độ mượt và tải nặng.",
            f"điểm mạnh về sức mạnh xử lý nằm ở {value}; nên ưu tiên đúng bản RAM/bộ nhớ khi mua.",
            f"nếu ưu tiên tốc độ phản hồi, {value} là phần đáng chú ý nhất.",
        ],
        "gaming_phone": [
            "đây là gaming phone rõ rệt, hợp người ưu tiên FPS, tản nhiệt và pin hơn camera.",
            "máy thiên về chơi game chuyên dụng hơn điện thoại phổ thông, nên chú ý nhiệt độ, quạt/tản nhiệt và bảo hành.",
            "nếu mục tiêu là game nặng lâu dài, gaming phone này đáng cân nhắc hơn các mẫu cân bằng camera.",
        ],
        "battery": [
            f"pin/sạc {value} giúp máy hợp hơn với người dùng nhiều trong ngày.",
            (
                f"lợi thế dùng lâu nằm ở {value}, đặc biệt khi chơi game hoặc dùng 4G/5G nhiều."
                if is_gaming_context
                else f"lợi thế dùng lâu nằm ở {value}, phù hợp nếu bạn ưu tiên pin và ít phải sạc trong ngày."
            ),
            f"{value} là điểm nên cân nhắc nếu bạn không muốn sạc quá thường xuyên.",
        ],
        "display": [
            (
                f"màn hình {value} ảnh hưởng trực tiếp đến cảm giác chơi game, xem phim và thao tác."
                if is_gaming_context
                else f"màn hình {value} phù hợp xem nội dung, đọc chữ và thao tác hằng ngày."
            ),
            f"trải nghiệm nhìn là điểm đáng chú ý nhờ {value}.",
            f"nếu bạn quan tâm độ mượt và không gian hiển thị, {value} là lợi thế rõ.",
        ],
        "camera": [
            f"camera {value}; nên xem review thực tế nếu chụp/quay là tiêu chí chính.",
            f"cụm camera {value} giúp máy linh hoạt hơn ngoài nhu cầu hiệu năng.",
            f"về ảnh/quay, thông số đáng chú ý là {value}, nhưng vẫn nên kiểm tra chất ảnh thực tế.",
        ],
        "storage": [
            (
                f"bộ nhớ {value} hợp hơn nếu bạn cài nhiều app, game hoặc lưu video."
                if is_gaming_context
                else f"bộ nhớ {value} hợp hơn nếu bạn lưu nhiều ảnh, video và ứng dụng."
            ),
            f"về lưu trữ, {value} là điểm nên chọn rộng ngay từ đầu nếu dùng lâu dài.",
            f"dung lượng {value} giúp giảm áp lực phải dọn bộ nhớ thường xuyên.",
        ],
        "software": [
            f"phần mềm {value}; nên cân nhắc giao diện, cập nhật và bảo hành theo thị trường bán ra.",
            f"máy chạy {value}, vì vậy trải nghiệm giao diện và chính sách cập nhật cũng nên được kiểm tra.",
            f"{value} là phần ảnh hưởng đến trải nghiệm dùng lâu hơn là chỉ nhìn cấu hình.",
        ],
        "gpu": [
            f"GPU {value} là nền tảng chính cho game, đồ họa và các tác vụ cần tăng tốc hình ảnh.",
            f"với {value}, máy phù hợp hơn laptop văn phòng khi chơi game hoặc làm đồ họa.",
            f"nếu nhu cầu là game/tác vụ nặng, {value} là thông số cần kiểm tra đầu tiên, gồm cả TGP thực tế.",
        ],
        "cpu": [
            f"CPU {value} quyết định nhiều đến hiệu năng duy trì khi chạy tải lâu.",
            f"{value} là phần đáng chú ý nếu bạn render, code, giả lập hoặc đa nhiệm nặng.",
            f"về xử lý tác vụ, {value} là điểm cần so với các mẫu cùng GPU.",
        ],
        "memory": [
            f"RAM/SSD {value} phù hợp đa nhiệm và lưu trữ game/app nặng.",
            f"cấu hình bộ nhớ {value}; nếu SSD 512GB thì nên tính đến nhu cầu nâng cấp.",
            f"phần RAM/lưu trữ ở mức {value}, nên chọn đúng phiên bản ngay từ đầu.",
        ],
        "mobility": [
            f"tính cơ động nằm ở {value}, hợp nếu bạn hay mang máy đi.",
            f"pin/cân nặng {value} là điểm cần cân bằng với hiệu năng.",
            f"nếu di chuyển nhiều, {value} là thông tin đáng chú ý không kém CPU/GPU.",
        ],
    }
    choices = templates.get(kind, [f"điểm đáng chú ý: {value}."])
    return choices[variant]


def _stable_variant_index(value: object, modulo: int) -> int:
    if modulo <= 1:
        return 0
    text = normalize_text(value)
    return sum(ord(ch) for ch in text) % modulo


def _comparison_spec_line(item: Dict, category: Optional[str]) -> str:
    snapshot = item.get("spec_snapshot") or {}
    specs = item.get("specs") or {}
    source = snapshot if isinstance(snapshot, dict) and snapshot else specs if isinstance(specs, dict) else {}
    if not source:
        return "chưa có thông số chi tiết trong catalog, cần kiểm tra đúng SKU trước khi mua"

    keys = (
        ["chipset", "ram", "storage", "display", "battery", "camera", "os"]
        if category == "phone"
        else ["cpu", "gpu", "ram", "storage", "display", "battery", "weight", "os"]
    )
    parts = []
    for key in keys:
        value = source.get(key)
        if value:
            parts.append(f"{_label(key)} {str(value).strip()}")
    return "; ".join(parts[:7]) if parts else "cần kiểm tra đúng SKU trước khi mua"


def _recommendation_blurb(
    item: Dict,
    category: Optional[str],
    matched_tags: List[str],
    budget_target: Optional[float],
) -> str:
    reason = _budget_fit_text(item, budget_target)
    snapshot = item.get("spec_snapshot") or {}
    specs = item.get("specs") or {}
    source = snapshot if isinstance(snapshot, dict) and snapshot else specs if isinstance(specs, dict) else {}
    strengths = [_clean(value) for value in _as_list(item.get("strengths")) if value]
    notes = []

    generic_notes = _generic_recommendation_notes(
        item=item,
        category=category,
        matched_tags=matched_tags,
        source=source,
    )
    if generic_notes:
        intro = f"{reason}; " if reason else ""
        return intro + " ".join(generic_notes[:3])

    if category == "phone" and source:
        chipset = source.get("chipset")
        ram = source.get("ram") or _extract_before_semicolon(source.get("ram_storage"))
        storage = source.get("storage")
        display = source.get("display") or source.get("screen")
        battery = source.get("battery")
        charging = source.get("charging")
        camera = source.get("camera")
        os_name = source.get("os") or source.get("software")
        name = normalize_text(item.get("name"))

        headline = ""
        headline_focus = ""
        battery_size = _first_number(battery)
        if "redmagic" in name:
            headline = "thiên về gaming phone rõ rệt, hợp người ưu tiên FPS, tản nhiệt và pin hơn camera."
            headline_focus = "gaming"
        elif battery_size and battery_size >= 6500:
            headline = f"nổi bật ở pin {battery}"
            if charging:
                headline += f" kèm sạc {charging}"
            headline += ", hợp nếu bạn chơi lâu hoặc dùng máy nhiều trong ngày."
            headline_focus = "battery"
        elif display and ("144hz" in normalize_text(display) or "144 hz" in normalize_text(display)):
            headline = f"màn hình {display} là điểm khác biệt, hợp game tốc độ cao và thao tác mượt."
            headline_focus = "display"
        elif charging and "wireless" in normalize_text(charging):
            headline = f"sạc {charging} tạo trải nghiệm cao cấp hơn nhóm chỉ có sạc dây."
            headline_focus = "charging"
        elif camera and "periscope" in normalize_text(camera):
            headline = f"camera {camera} là điểm cộng nếu bạn vẫn muốn zoom/chụp linh hoạt."
            headline_focus = "camera"
        if headline:
            notes.append(headline)

        if "gaming" in matched_tags or "performance" in matched_tags:
            if chipset:
                perf = f"dùng {chipset}"
                if ram:
                    perf += f", RAM {ram}"
                notes.append(perf + ", nên hợp hơn với nhu cầu hiệu năng/chơi game.")
        if battery and headline_focus != "battery":
            battery_text = f"pin {battery}"
            if charging:
                battery_text += f", sạc {charging}"
            notes.append(battery_text + " là điểm đáng chú ý khi chơi hoặc dùng lâu.")
        if display and headline_focus != "display":
            notes.append(f"màn hình {display} là lợi thế cho game, phim và thao tác hằng ngày.")
        if camera and "camera" in matched_tags and headline_focus != "camera":
            notes.append(f"camera {camera}; nên kiểm tra review ảnh/quay thực tế nếu bạn quan tâm camera.")
        elif os_name:
            notes.append(f"chạy {os_name}, cần cân nhắc giao diện/phần mềm và bảo hành theo thị trường bán ra.")
        if storage and len(notes) < 3:
            notes.append(f"bộ nhớ có tùy chọn {storage}, nên chọn bản đủ dung lượng nếu cài nhiều game.")

    elif category == "laptop" and source:
        cpu = source.get("cpu")
        gpu = source.get("gpu")
        ram = source.get("ram")
        storage = source.get("storage")
        display = source.get("display")
        battery = source.get("battery")
        weight = source.get("weight")
        name = normalize_text(item.get("name"))
        spec_pack = ", ".join(part for part in [cpu, gpu] if part)
        memory_pack = ", ".join(part for part in [ram, storage] if part)

        if "tuf a14" in name or ("14" in name and weight):
            if weight or battery:
                notes.append(
                    f"điểm khác biệt là tính cơ động: {', '.join(part for part in [weight, battery] if part)}, hợp hơn nếu bạn hay mang máy đi."
                )
            if spec_pack:
                notes.append(f"dù gọn hơn, cấu hình vẫn đáng chú ý với {spec_pack}.")
            if display or memory_pack:
                notes.append(f"phần còn lại khá thực dụng: {', '.join(part for part in [display, memory_pack] if part)}.")
        elif "predator" in name:
            if display:
                notes.append(f"Predator Helios Neo thiên về khung máy lớn và màn {display}, hợp người đặt trải nghiệm chơi game trên bàn hơn tính cơ động.")
            if gpu and cpu:
                notes.append(f"bộ đôi {cpu} + {gpu} phù hợp game nặng, nhưng nên kiểm tra nhiệt độ và độ ồn khi tải lâu.")
            if battery or weight:
                notes.append(f"điểm cần cân nhắc nằm ở thân máy: {', '.join(part for part in [weight, battery] if part)}.")
        elif "omen" in name:
            if gpu:
                notes.append(f"OMEN thường hợp người muốn máy gaming hoàn thiện hơn Victus/Nitro, với {gpu} làm nền tảng hiệu năng.")
            if display or cpu:
                notes.append(f"cấu hình {', '.join(part for part in [cpu, display] if part)} phù hợp vừa chơi game vừa làm việc nặng.")
            if memory_pack:
                notes.append(f"nên kiểm tra đúng bản {memory_pack}, nhất là nếu bạn cài nhiều game lớn.")
        elif "rog" in name or "strix" in name:
            if display:
                notes.append(f"mẫu này thiên về trải nghiệm gaming cao hơn, nhất là màn hình {display}.")
            if gpu:
                notes.append(f"{gpu} là nền tảng chính cho game/đồ họa, nhưng vẫn nên kiểm tra TGP theo đúng SKU.")
            if cpu or memory_pack:
                notes.append(f"cấu hình đi kèm gồm {', '.join(part for part in [cpu, memory_pack] if part)}, hợp tải nặng dài hơn máy phổ thông.")
        elif "dell g15" in name or "g15" in name:
            if item.get("price") is not None:
                notes.append(f"Dell G15 đáng chú ý ở mức giá {_price(item.get('price'))}: ưu tiên hiệu năng thực dụng hơn ngoại hình mỏng nhẹ.")
            if cpu and gpu:
                notes.append(f"cặp {cpu} và {gpu} phù hợp chơi game 1080p/2K tùy thiết lập, nên kiểm tra kỹ tản nhiệt từng SKU.")
            if memory_pack:
                notes.append(f"cấu hình {memory_pack}; bản SSD 512GB có thể nhanh đầy nếu cài nhiều game.")
        elif "victus" in name or "loq" in name or "nitro" in name:
            if item.get("price") is not None:
                notes.append(f"đây là lựa chọn thiên về hiệu năng/giá ở mức {_price(item.get('price'))}, hợp nếu bạn muốn RTX nhưng vẫn giữ ngân sách hợp lý.")
            if gpu and cpu:
                notes.append(f"cặp {cpu} + {gpu} đủ tốt cho game nặng hơn laptop văn phòng rất nhiều.")
            if memory_pack:
                notes.append(f"nên ưu tiên đúng bản {memory_pack}; nếu chọn SSD 512GB thì có thể cần nâng cấp sau.")
        elif "legion" in name:
            if gpu and cpu:
                notes.append(f"điểm đáng tiền của Legion thường nằm ở hiệu năng duy trì: {cpu} kết hợp {gpu}.")
            if display:
                notes.append(f"màn {display} phù hợp chơi game và làm việc lâu hơn màn FHD cơ bản.")
            if weight or battery:
                notes.append(f"đổi lại cần cân nhắc độ cơ động: {', '.join(part for part in [weight, battery] if part)}.")
        else:
            if gpu:
                notes.append(f"về sức mạnh đồ họa, máy dùng {gpu}, phù hợp game/đồ họa hơn laptop văn phòng.")
            if cpu:
                notes.append(f"CPU {cpu} là phần cần kiểm tra nếu bạn chạy tác vụ nặng lâu.")
            if memory_pack:
                notes.append(f"RAM/SSD: {memory_pack}, nên chọn bản đủ dung lượng ngay từ đầu.")
            if display:
                notes.append(f"màn hình {display} ảnh hưởng trực tiếp đến trải nghiệm game/làm việc.")

    if not notes and strengths:
        notes = [f"điểm đáng chú ý là {strengths[0]}.", _sales_pitch(item, category, matched_tags) + "."]

    intro = f"{reason}; " if reason else ""
    return intro + " ".join(notes[:3])


def _budget_fit_text(item: Dict, budget_target: Optional[float]) -> str:
    if not budget_target or item.get("price") is None:
        return ""
    try:
        price = float(item.get("price"))
    except (TypeError, ValueError):
        return ""
    if price <= budget_target:
        return f"nằm trong ngân sách {_price(budget_target)}"
    if price <= budget_target * 1.15:
        return "hơi vượt ngân sách nhưng có thể cân nhắc nếu săn sale hoặc chọn đúng phiên bản"
    return "vượt ngân sách, chỉ nên cân nhắc nếu bạn sẵn sàng nâng mức chi"


def _extract_before_semicolon(value: object) -> str:
    text = str(value or "").strip()
    return text.split(";")[0].strip()


def _first_number(value: object) -> Optional[float]:
    import re

    match = re.search(r"\d+(?:[.,]\d+)?", str(value or ""))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def _comparison_similarities(items: List[Dict], category: Optional[str]) -> List[str]:
    if len(items) < 2:
        return []
    first, second = items[0], items[1]
    first_snapshot = first.get("spec_snapshot") or {}
    second_snapshot = second.get("spec_snapshot") or {}
    if not isinstance(first_snapshot, dict) or not isinstance(second_snapshot, dict):
        return []

    keys = (
        ["chipset", "ram", "storage", "display", "battery", "camera"]
        if category == "phone"
        else ["gpu", "ram", "storage", "display"]
    )
    similarities = []
    for key in keys:
        first_value = first_snapshot.get(key)
        second_value = second_snapshot.get(key)
        if first_value and second_value and normalize_text(first_value) == normalize_text(second_value):
            similarities.append(f"{_label(key)} gần như tương đương: {_clean(first_value)}.")
    return similarities[:3]


def _comparison_takeaways(items: List[Dict], category: Optional[str], priorities: set) -> List[str]:
    if len(items) < 2:
        return []
    first, second = items[0], items[1]
    takeaways = []

    price_note = _price_gap_takeaway(first, second)
    if price_note:
        takeaways.append(price_note)

    snapshot_takeaways = _snapshot_comparison_takeaways(first, second, category)
    takeaways.extend(snapshot_takeaways)

    for key in _comparison_keys(category)[:4]:
        if len(takeaways) >= 4:
            break
        first_value = (first.get("comparison_profile") or {}).get(key)
        second_value = (second.get("comparison_profile") or {}).get(key)
        if first_value and second_value and normalize_text(first_value) != normalize_text(second_value):
            takeaways.append(
                f"{_label(key)} - {first.get('name')}: {_clean(first_value)}; {second.get('name')}: {_clean(second_value)}."
            )

    takeaways = _dedupe_sentences(takeaways)

    if not takeaways:
        takeaways.append("Cả hai đều cần kiểm tra đúng cấu hình bán ra, vì cùng tên sản phẩm có thể có nhiều phiên bản.")
    return takeaways[:4]


def _dedupe_sentences(sentences: List[str]) -> List[str]:
    seen = set()
    unique = []
    for sentence in sentences:
        key = normalize_text(sentence)
        if key in seen:
            continue
        seen.add(key)
        unique.append(sentence)
    return unique


def _snapshot_comparison_takeaways(first: Dict, second: Dict, category: Optional[str]) -> List[str]:
    first_snapshot = first.get("spec_snapshot") or {}
    second_snapshot = second.get("spec_snapshot") or {}
    if not isinstance(first_snapshot, dict) or not isinstance(second_snapshot, dict):
        return []
    if not first_snapshot or not second_snapshot:
        return []

    keys = (
        ["chipset", "ram", "storage", "display", "battery", "camera"]
        if category == "phone"
        else ["cpu", "gpu", "ram", "storage", "display", "battery"]
    )
    takeaways = []
    for key in keys:
        first_value = first_snapshot.get(key)
        second_value = second_snapshot.get(key)
        if first_value and second_value and normalize_text(first_value) != normalize_text(second_value):
            takeaways.append(
                f"{_label(key)} - {first.get('name')}: {_clean(first_value)}; {second.get('name')}: {_clean(second_value)}."
            )
    return takeaways[:3]


def _choose_winner(items: List[Dict], category: Optional[str], priorities: set) -> Optional[Dict]:
    if not items:
        return None

    def score(item: Dict) -> float:
        tags = {normalize_text(tag) for tag in item.get("tags", [])}
        name = normalize_text(item.get("name"))
        value = float(item.get("relevance_score", 0.0) or 0.0)
        value += len(tags & priorities) * 5
        if {"gaming", "creator", "performance"} & priorities:
            if "rtx" in tags:
                value += 4
            if "rtx 4060" in name or "rtx 4070" in name:
                value += 3
            if "lightweight" in tags and "gaming" in priorities:
                value -= 1
        if category == "phone":
            snapshot = item.get("spec_snapshot") or {}
            if isinstance(snapshot, dict):
                value += _phone_chip_rank(snapshot.get("chipset")) / 10
                if {"gaming", "performance"} & priorities:
                    value += _phone_chip_rank(snapshot.get("chipset")) / 8
                    battery = _first_number(snapshot.get("battery"))
                    if battery:
                        value += min(battery / 1000, 8)
                if "camera" in priorities:
                    value += _phone_camera_score(snapshot.get("camera"))
                if "value" in priorities:
                    try:
                        value -= float(item.get("price", 0) or 0) / 10_000_000
                    except (TypeError, ValueError):
                        pass
        if "value" in tags and category == "laptop":
            value += 2
        return value

    return max(items, key=score)


def _buying_decision(item: Dict, category: Optional[str], priorities: set, user_message: str) -> Dict:
    tags = {normalize_text(tag) for tag in item.get("tags", [])}
    matched = sorted((tags & priorities) - {"phone", "laptop"})
    if matched:
        summary = f"mẫu này đáng cân nhắc vì khớp {', '.join(_tag_label(tag) for tag in matched)}."
        recommendation = "nên cân nhắc nếu giá thực tế và cấu hình đúng với bản bạn định mua"
    else:
        summary = "mẫu này có thể cân nhắc, nhưng cần đối chiếu lại với nhu cầu chính của bạn."
        recommendation = "chỉ nên mua nếu các điểm mạnh của nó đúng với nhu cầu sử dụng"
    return {"summary": summary, "recommendation": recommendation}


def _ordered_spec_snapshot(snapshot: Dict, category: Optional[str]) -> List[tuple[str, str]]:
    if not snapshot:
        return []
    keys = (
        ["chipset", "ram", "storage", "display", "battery", "charging", "camera", "os"]
        if category == "phone"
        else ["cpu", "gpu", "ram", "storage", "display", "battery", "weight", "os"]
    )
    return [(_label(key), _clean(snapshot.get(key))) for key in keys if snapshot.get(key)]


def _ordered_config(config: Dict, category: Optional[str]) -> List[tuple[str, str]]:
    keys = (
        ["chipset_tier", "ram_storage", "display", "battery_charging", "camera", "cooling", "software"]
        if category == "phone"
        else ["cpu_class", "gpu_class", "ram", "storage", "display", "thermal", "portability", "battery", "upgrade_notes"]
    )
    return [(_label(key), _clean(config.get(key))) for key in keys if config.get(key)]


def _ordered_performance(perf: Dict, category: Optional[str]) -> List[tuple[str, str]]:
    keys = ["gaming", "multitasking", "camera", "battery"] if category == "phone" else ["office", "gaming", "creator", "coding", "battery"]
    return [(_label(key), _clean(perf.get(key))) for key in keys if perf.get(key)]


def _focused_performance_notes(rows: List[tuple[str, str]], category: Optional[str]) -> List[str]:
    if not rows:
        return []
    notes = []
    for label, value in rows:
        normalized = normalize_text(label)
        if category == "phone":
            if normalized in {"choi game", "gaming"}:
                notes.append(f"Chơi game: {value}.")
            elif normalized == "camera":
                notes.append(f"Camera: {value}.")
            elif normalized in {"pin", "battery"}:
                notes.append(f"Pin: {value}.")
        else:
            if normalized in {"choi game", "gaming"}:
                notes.append(f"Game/đồ họa: {value}.")
            elif normalized in {"van phong", "office"}:
                notes.append(f"Văn phòng: {value}.")
            elif normalized in {"do hoa/sang tao", "creator"}:
                notes.append(f"Sáng tạo nội dung: {value}.")
            elif normalized in {"pin", "battery"}:
                notes.append(f"Pin: {value}.")
    return notes[:3]


def _configuration_analysis(item: Dict, category: Optional[str]) -> List[str]:
    tags = {normalize_text(tag) for tag in item.get("tags", [])}
    name = normalize_text(item.get("name"))
    snapshot = item.get("spec_snapshot") or {}
    analysis = []

    if category == "laptop":
        if isinstance(snapshot, dict) and snapshot:
            gpu = normalize_text(snapshot.get("gpu"))
            ram = normalize_text(snapshot.get("ram"))
            storage = normalize_text(snapshot.get("storage"))
            cpu = snapshot.get("cpu")
            if cpu:
                analysis.append(f"CPU {snapshot.get('cpu')} là nền tảng chính cho tác vụ nặng, đa nhiệm và giữ FPS ổn định khi game cần nhiều CPU.")
            if "rtx 5090" in gpu:
                analysis.append("RTX 5090 Laptop GPU 24GB là cấu hình mạnh nhất trong catalog hiện tại, hợp mục tiêu chơi game rất nặng, màn hình độ phân giải cao, render/AI nhẹ-vừa và dùng lâu dài.")
            elif "rtx 4080" in gpu:
                analysis.append("RTX 4080 Laptop GPU 12GB thuộc nhóm rất mạnh, đáng chọn nếu bạn muốn hiệu năng cao rõ rệt hơn RTX 4060/4070 và có ngân sách rộng.")
            elif "rtx 4070" in gpu:
                analysis.append("RTX 4070 Laptop GPU 8GB hợp gaming nặng ở mức cao và tác vụ đồ họa tốt hơn RTX 4050/4060, nhưng vẫn nên xem TGP vì hiệu năng khác nhau theo máy.")
            elif "rtx 4060" in gpu:
                analysis.append("RTX 4060 Laptop GPU 8GB là mức cân bằng cho gaming 1080p/2K vừa phải, hợp người muốn hiệu năng tốt nhưng chưa cần nhóm cao cấp.")
            elif "rtx 4050" in gpu:
                analysis.append("RTX 4050 Laptop GPU 6GB hợp game eSports/AAA vừa phải và tác vụ đồ họa nhẹ-vừa; nếu muốn dùng lâu dài cho game nặng nên ưu tiên RTX 4060 trở lên.")
            elif "rtx" in gpu:
                analysis.append("GPU RTX rời là lợi thế lớn so với laptop văn phòng, phù hợp game, đồ họa và các tác vụ cần tăng tốc GPU.")
            elif "integrated" in gpu or "igpu" in gpu or "iris" in gpu or "radeon" in gpu:
                analysis.append("GPU tích hợp hợp văn phòng, học tập, giải trí nhẹ và tiết kiệm pin; không phải hướng chính cho game AAA hoặc render 3D nặng.")
            if "64gb" in ram:
                analysis.append("RAM 64GB rất rộng cho đa nhiệm nặng, project lớn, máy ảo, dựng video hoặc tác vụ AI cục bộ.")
            elif "32gb" in ram:
                analysis.append("RAM 32GB là mức đẹp cho laptop hiệu năng cao, giúp thoải mái hơn khi chơi game, mở nhiều ứng dụng, lập trình hoặc dựng nội dung.")
            elif "16gb" in ram:
                analysis.append("RAM 16GB là mức nên có tối thiểu hiện nay; nếu dùng game/tác vụ nặng lâu dài thì nên kiểm tra khả năng nâng cấp lên 32GB.")
            if "2tb" in storage:
                analysis.append("SSD 2TB thoải mái cho nhiều game nặng và project lớn.")
            elif "1tb" in storage:
                analysis.append("SSD 1TB hợp thực tế hơn 512GB nếu cài nhiều game, lưu project hoặc dùng lâu dài.")
            if "gaming" in tags or "performance" in tags:
                analysis.append("Tản nhiệt, TGP GPU, độ ồn và chất lượng màn hình vẫn cần xem review đúng SKU vì chúng quyết định hiệu năng duy trì, không chỉ thông số CPU/GPU.")
            if "lightweight" in tags:
                analysis.append("Thiết kế gọn nhẹ là lợi thế khi di chuyển, nhưng nên kiểm tra nhiệt độ, độ ồn và khả năng nâng cấp nếu dùng tải nặng thường xuyên.")
            if "battery" not in tags and ("gaming" in tags or "rtx" in gpu):
                analysis.append("Khi chơi game hoặc chạy tải nặng, máy nên cắm sạc để đạt hiệu năng tốt nhất; pin phù hợp hơn cho tác vụ nhẹ.")
            return unique_keep(analysis)

        if "rtx 4070" in name:
            analysis.append("GPU RTX 4070 thường là điểm đáng giá nhất của máy: hợp chơi game nặng, dựng video, đồ họa và tác vụ cần GPU hơn các cấu hình RTX 4050/4060 phổ thông.")
        elif "rtx 4060" in name:
            analysis.append("GPU RTX 4060 là mức cân bằng tốt cho gaming/đồ họa tầm trung-cao; vẫn cần kiểm tra TGP vì cùng RTX 4060 nhưng hiệu năng có thể khác nhau theo máy.")
        elif "rtx" in tags:
            analysis.append("GPU rời RTX giúp máy phù hợp game, đồ họa và tác vụ tăng tốc GPU hơn laptop văn phòng.")
        else:
            analysis.append("Nếu không có GPU rời, máy sẽ hợp văn phòng/học tập hơn là game nặng hoặc dựng hình.")

        if "gaming" in tags or "performance" in tags:
            analysis.append("CPU hiệu năng cao là phù hợp với nhóm máy này, nhưng hiệu năng thực tế phụ thuộc tản nhiệt và giới hạn điện của từng phiên bản.")
            analysis.append("RAM 16GB là mức tối thiểu nên có; 32GB đáng cân nhắc nếu bạn chơi game nặng, mở nhiều app, lập trình, dựng video hoặc dùng lâu dài.")
            analysis.append("SSD 1TB thực tế thoải mái hơn 512GB nếu cài nhiều game hoặc lưu project lớn.")
            analysis.append("Tản nhiệt, độ ồn và chất lượng màn hình là các điểm phải xem review thực tế, vì chúng ảnh hưởng trực tiếp tới trải nghiệm chứ không chỉ thông số CPU/GPU.")
        if "lightweight" in tags:
            analysis.append("Thiết kế gọn nhẹ là lợi thế khi di chuyển, nhưng thường phải đánh đổi với nhiệt độ, độ ồn hoặc khả năng nâng cấp.")
        if "battery" not in tags and ("gaming" in tags or "rtx" in tags):
            analysis.append("Khi chơi game hoặc chạy tải nặng, máy sẽ phát huy tốt nhất khi cắm sạc; pin phù hợp hơn cho tác vụ nhẹ và di chuyển ngắn.")
        return unique_keep(analysis)

    if category == "phone":
        if isinstance(snapshot, dict) and snapshot:
            chipset = normalize_text(snapshot.get("chipset"))
            ram = snapshot.get("ram")
            battery = snapshot.get("battery")
            display = snapshot.get("display")
            camera = snapshot.get("camera")
            if "snapdragon 8 elite" in chipset:
                analysis.append("Hiệu năng thuộc nhóm flagship, phù hợp người ưu tiên chơi game nặng, đa nhiệm lâu dài và độ mượt cao.")
            elif "snapdragon 8 gen 3" in chipset or "dimensity 9400" in chipset:
                analysis.append("Hiệu năng vẫn rất mạnh trong thực tế; đáng ưu tiên nếu giá bán hiện tại tốt hơn các flagship mới.")
            elif "dimensity 8400" in chipset or "dimensity 8300" in chipset or "snapdragon 8s gen 3" in chipset:
                analysis.append("Hiệu năng/giá là điểm mạnh: đủ tốt cho đa số nhu cầu nặng nhưng vẫn thấp tiền hơn nhóm flagship thật sự.")
            if ram:
                analysis.append("RAM ở mức tốt cho đa nhiệm; nếu chênh giá không lớn, nên chọn bản bộ nhớ cao để dùng lâu hơn.")
            if battery:
                analysis.append("Pin/sạc đáp ứng tốt nhu cầu một ngày, nhưng thời lượng thực tế còn phụ thuộc độ sáng, 5G, nhiệt độ và game.")
            if display:
                analysis.append("Màn hình là điểm nên chú ý nếu bạn xem phim, chơi game hoặc dùng ngoài trời; hãy kiểm tra thêm độ sáng và màu sắc thực tế.")
            if camera and "camera" in tags:
                analysis.append("Camera có đủ các tiêu cự chính; nếu chụp/quay là nhu cầu lớn, nên xem thêm ảnh mẫu và khả năng quay video.")
            return unique_keep(analysis[:5])

        if "gaming" in tags or "performance" in tags:
            analysis.append("Nếu mua để chơi game, cần xem thêm nhiệt độ, FPS duy trì và độ tụt sáng sau 20-30 phút chơi.")
        if "battery" in tags:
            analysis.append("Pin là điểm phù hợp với nhu cầu dùng lâu, nhưng không nên chỉ nhìn mAh mà bỏ qua tối ưu phần mềm.")
        if "camera" in tags:
            analysis.append("Camera là lợi thế nếu bạn chụp/quay nhiều; nếu không chụp ảnh, có thể ưu tiên hiệu năng và pin hơn.")
        if "premium" in tags:
            analysis.append("Phân khúc cao cấp thường cho trải nghiệm hoàn thiện hơn, nhưng cần cân nhắc liệu phần chênh giá có đúng nhu cầu của bạn không.")
        return unique_keep(analysis)

    return []


def _price_gap_takeaway(first: Dict, second: Dict) -> str:
    try:
        first_price = float(first.get("price"))
        second_price = float(second.get("price"))
    except (TypeError, ValueError):
        return ""
    if abs(first_price - second_price) < 5_000_000:
        return ""
    cheaper = first if first_price < second_price else second
    pricier = second if cheaper is first else first
    return f"{cheaper.get('name')} có lợi thế giá; {pricier.get('name')} chỉ đáng trả thêm nếu bạn thật sự cần các điểm mạnh riêng của nó."


def _is_reasonable_alternative(item: Dict, retrieval: Dict) -> bool:
    budget_min = retrieval.get("budget_min")
    budget_max = retrieval.get("budget_max")
    budget_target = retrieval.get("budget_target")
    status = item.get("budget_status")

    if not budget_min and not budget_max and not budget_target:
        return True

    if status == "fits":
        if budget_target and budget_target >= 15_000_000 and "value" not in set(retrieval.get("priorities") or []):
            try:
                price = float(item.get("price"))
            except (TypeError, ValueError):
                return True
            if price < budget_target * 0.65:
                return False
        return True
    if status == "unknown":
        return False
    if status == "budget_saver":
        # Do not pad a 20m+ request with very cheap phones/laptops. Only allow
        # budget savers for low budgets or when they are still close to target.
        if not budget_target or budget_target >= 15_000_000:
            return False
        try:
            price = float(item.get("price"))
        except (TypeError, ValueError):
            return False
        return price >= budget_target * 0.8
    if budget_min and budget_max:
        try:
            price = float(item.get("price"))
        except (TypeError, ValueError):
            return False
        return budget_min <= price <= budget_max
    return False


def _filter_budget_specific_notes(notes: List[str], budget_target: Optional[float]) -> List[str]:
    if not notes or not budget_target:
        return notes

    current_million = round(budget_target / 1_000_000)
    filtered = []
    for note in notes:
        normalized = normalize_text(note)
        amounts = []
        for token in normalized.replace("-", " ").split():
            try:
                value = float(token.replace(",", "."))
            except ValueError:
                continue
            if 3 <= value <= 150:
                amounts.append(round(value))
        if amounts and all(abs(amount - current_million) > 3 for amount in amounts):
            continue
        filtered.append(note)
    return filtered


def _comparison_keys(category: Optional[str]) -> List[str]:
    if category == "phone":
        return ["performance", "gaming", "display", "battery", "camera", "software", "value", "risk"]
    if category == "laptop":
        return ["cpu", "gpu", "ram_storage", "display", "thermal", "portability_battery", "upgrade", "value"]
    return ["performance", "display", "battery", "value"]


def _heading(category: Optional[str], priorities: set) -> str:
    if category == "phone":
        return "Một vài điện thoại đáng cân nhắc"
    if category == "laptop":
        if "gaming" in priorities:
            return "Một vài laptop gaming đáng cân nhắc"
        return "Một vài laptop đáng cân nhắc"
    return "Một vài sản phẩm đáng cân nhắc"


def _checklist(category: Optional[str], priorities: set) -> str:
    if category == "laptop":
        return "Checklist: CPU/GPU đúng cấu hình, RAM 16GB+, SSD 512GB+, tản nhiệt, màn hình và bảo hành."
    if category == "phone":
        return "Checklist: chipset, RAM/bộ nhớ, tản nhiệt, pin, bảo hành và giá hiện tại."
    return "Checklist: giá hiện tại, cấu hình đúng mã, bảo hành và nguồn bán."


def _priority_text(priorities: set) -> str:
    visible = sorted(tag for tag in priorities if not str(tag).startswith("brand:"))[:3]
    return ", ".join(_tag_label(tag) for tag in visible) or "nhu cầu tổng thể"


def _label(key: str) -> str:
    labels = {
        "battery": "Pin",
        "battery_charging": "Pin/sạc",
        "camera": "Camera",
        "charging": "Sạc",
        "chipset_tier": "Chip/hiệu năng",
        "coding": "Lập trình",
        "cooling": "Tản nhiệt",
        "cpu": "CPU",
        "cpu_class": "CPU",
        "creator": "Đồ họa/sáng tạo",
        "display": "Màn hình",
        "gaming": "Chơi game",
        "gpu": "GPU",
        "gpu_class": "GPU",
        "multitasking": "Đa nhiệm",
        "office": "Văn phòng",
        "os": "Hệ điều hành",
        "performance": "Hiệu năng",
        "portability": "Tính di động",
        "portability_battery": "Di động/pin",
        "ram": "RAM",
        "ram_storage": "RAM/bộ nhớ",
        "risk": "Điểm cần kiểm tra",
        "software": "Phần mềm",
        "storage": "Lưu trữ",
        "thermal": "Tản nhiệt/độ ồn",
        "upgrade": "Nâng cấp",
        "upgrade_notes": "Khả năng nâng cấp",
        "value": "Giá trị/giá bán",
        "weight": "Cân nặng",
    }
    return labels.get(key, key.replace("_", " "))


def _tag_label(tag: str) -> str:
    labels = {
        "ai_work": "AI",
        "battery": "pin",
        "camera": "camera",
        "creator": "tác vụ nặng/sáng tạo",
        "display": "màn hình",
        "gaming": "chơi game",
        "lightweight": "mỏng nhẹ",
        "office": "văn phòng",
        "performance": "hiệu năng",
        "max_performance": "cấu hình mạnh nhất",
        "ram": "RAM",
        "storage": "lưu trữ",
        "value": "giá trị/giá bán",
    }
    if tag.startswith("brand:"):
        return "hãng " + tag.split(":", 1)[1].title()
    return labels.get(tag, tag)


def _as_list(values) -> List[str]:
    if not values:
        return []
    if isinstance(values, list):
        return [_clean(value) for value in values if str(value).strip()]
    return [_clean(values)]


def unique_keep(values: List[str]) -> List[str]:
    seen = set()
    output = []
    for value in values:
        key = normalize_text(value)
        if key and key not in seen:
            seen.add(key)
            output.append(value)
    return output


def _join(values: List[str], fallback: str = "") -> str:
    cleaned = [_clean(value) for value in values if _clean(value)]
    return "; ".join(cleaned) if cleaned else fallback


def _clean(value) -> str:
    text = str(value or "").strip().rstrip(".")
    replacements = {
        "pin không phải điểm mạnh khi chơi game; dùng pin chỉ phù hợp tác vụ nhẹ": "pin phù hợp hơn cho tác vụ nhẹ; khi chơi game hoặc chạy tải nặng nên cắm sạc để đạt hiệu năng tốt nhất",
        "không phải lựa chọn tối ưu nếu bạn ưu tiên chơi game nặng lâu dài": "nếu chơi game nặng lâu dài, nên kiểm tra thêm nhiệt độ và hiệu năng duy trì",
        "camera có thể không phải điểm mạnh nhất trong phân khúc": "camera nên được kiểm tra thêm nếu bạn chụp/quay nhiều",
        "không tối ưu cho game nặng hoặc render/3D": "phù hợp hơn với tác vụ nhẹ; nếu game nặng hoặc render/3D nên chọn cấu hình mạnh hơn",
    }
    for raw, pretty in replacements.items():
        text = text.replace(raw, pretty)
    return text


def _price(value) -> str:
    return format_vnd(value).replace("trieu", "triệu").replace("ty", "tỷ")
