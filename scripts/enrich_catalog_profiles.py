import json
from pathlib import Path


CATALOG_PATH = Path(__file__).resolve().parents[1] / "apps" / "backend" / "data" / "mini_product_catalog.json"


def price_tier(price):
    if price is None:
        return "unknown"
    if price < 10_000_000:
        return "budget"
    if price < 20_000_000:
        return "mid"
    if price < 35_000_000:
        return "upper_mid"
    if price < 60_000_000:
        return "premium"
    return "ultra"


def text_tags(item):
    return {str(tag).lower() for tag in item.get("tags", [])}


def phone_detail_profile(item):
    tags = text_tags(item)
    tier = price_tier(item.get("price"))
    name = item.get("name", "")
    brand = str(item.get("brand") or "").lower()

    if tier in {"premium", "ultra"}:
        chipset = "nhóm flagship hoặc cận flagship; phù hợp game nặng, đa nhiệm và dùng lâu dài"
        ram = "nên kiểm tra bản 12GB/16GB RAM và bộ nhớ 256GB/512GB; ưu tiên bộ nhớ lớn nếu chơi game nhiều"
    elif tier == "upper_mid":
        chipset = "nhóm cận cao cấp hoặc tầm trung mạnh; đủ tốt cho game phổ biến ở thiết lập hợp lý"
        ram = "nên ưu tiên 8GB-12GB RAM và 256GB bộ nhớ để dùng lâu dài"
    elif tier == "mid":
        chipset = "nhóm tầm trung khá; hợp game phổ biến, cần giảm thiết lập với game nặng"
        ram = "nên ưu tiên 8GB RAM và 128GB-256GB bộ nhớ"
    else:
        chipset = "nhóm phổ thông; hợp nhu cầu cơ bản, game nhẹ hoặc game phổ biến ở thiết lập thấp"
        ram = "nên kiểm tra tối thiểu 6GB-8GB RAM và bộ nhớ 128GB"

    if "gaming" in tags or "performance" in tags:
        gaming = "mạnh về hiệu năng; nên kiểm tra nhiệt độ, độ ổn định FPS và sạc khi chơi lâu"
        cooling = "ưu tiên mẫu có tản nhiệt tốt, thân máy không quá nóng khi tải dài"
    else:
        gaming = "chơi game ở mức phù hợp phân khúc; không nên kỳ vọng hiệu năng gaming chuyên sâu"
        cooling = "tản nhiệt cần kiểm tra qua review thực tế nếu chơi game nhiều"

    if "battery" in tags:
        battery = "pin là điểm đáng chú ý; vẫn cần kiểm tra thời lượng thực tế theo độ sáng, 4G/5G và game"
    else:
        battery = "pin ở mức phụ thuộc phiên bản và cách dùng; chơi game sẽ hao nhanh hơn"

    if "camera" in tags:
        camera = "camera là điểm mạnh tương đối; phù hợp chụp/quay thường ngày nhưng cần xem review ảnh thực tế"
    else:
        camera = "camera không phải trọng tâm; phù hợp nếu bạn ưu tiên hiệu năng/giá hơn chụp ảnh"

    if brand == "apple":
        software = "iOS ổn định và cập nhật lâu; không hợp nếu bạn không thích hệ sinh thái Apple"
    elif "android" in tags or brand in {"xiaomi", "oppo", "vivo", "oneplus", "samsung", "realme", "honor", "google", "nothing"}:
        software = "Android; cần kiểm tra ROM, chính sách cập nhật, bảo hành và hàng chính hãng tại Việt Nam"
    else:
        software = "cần kiểm tra hệ điều hành, bảo hành và chính sách cập nhật theo thị trường"

    if "Ultra" in name or "Pro" in name or "ROG" in name or "RedMagic" in name:
        positioning = "mẫu thiên về trải nghiệm cao cấp hoặc hiệu năng cao, hợp người muốn máy mạnh và dùng lâu dài"
    elif "Flip" in name or "Fold" in name:
        positioning = "mẫu thiên về thiết kế/trải nghiệm đặc biệt hơn là tối ưu hiệu năng trên giá"
    else:
        positioning = "mẫu cân bằng theo phân khúc, cần đối chiếu nhu cầu chính trước khi chọn"

    return {
        "positioning": positioning,
        "configuration": {
            "chipset_tier": chipset,
            "ram_storage": ram,
            "display": "nên kiểm tra loại tấm nền, độ sáng và tần số quét; 120Hz/OLED là lợi thế cho game và xem nội dung",
            "battery_charging": battery,
            "camera": camera,
            "cooling": cooling,
            "software": software,
        },
        "performance_profile": {
            "gaming": gaming,
            "multitasking": "ổn nếu chọn đúng RAM/bộ nhớ; càng nhiều app/game càng nên ưu tiên RAM và bộ nhớ lớn",
            "camera": camera,
            "battery": battery,
        },
        "buying_advice": {
            "choose_if": [
                "nó khớp đúng nhu cầu ưu tiên của bạn hơn là chỉ rẻ nhất",
                "giá thực tế nằm gần ngân sách và có bảo hành rõ ràng",
            ],
            "avoid_if": [
                "bạn cần một điểm mạnh mà mẫu này không tập trung",
                "phiên bản bán ra có RAM/bộ nhớ thấp hơn nhu cầu",
            ],
            "verify": [
                "chip/phiên bản RAM-bộ nhớ",
                "bảo hành và nguồn hàng",
                "review nhiệt độ, pin và camera thực tế",
            ],
        },
    }


def laptop_detail_profile(item):
    tags = text_tags(item)
    tier = price_tier(item.get("price"))
    name = item.get("name", "")

    has_rtx = "rtx" in tags or "RTX" in name.upper()
    gaming = "gaming" in tags
    creator = "creator" in tags
    office = "office" in tags
    lightweight = "lightweight" in tags

    if has_rtx:
        gpu = "GPU rời RTX; cần kiểm tra đúng mã GPU, VRAM và TGP vì cùng tên máy có nhiều cấu hình"
    elif "macbook" in name.lower():
        gpu = "GPU tích hợp trong Apple Silicon; mạnh cho pin, media và app tối ưu, không phải lựa chọn chính cho game Windows"
    elif gaming or (creator and tier in {"upper_mid", "premium", "ultra"}):
        gpu = "thường có phiên bản GPU rời hoặc GPU mạnh hơn máy văn phòng; cần kiểm tra đúng mã GPU/VRAM trước khi mua"
    else:
        gpu = "GPU tích hợp; hợp Office/web/học tập, không phù hợp game nặng hoặc render 3D thường xuyên"

    if tier in {"premium", "ultra"} or gaming or creator:
        cpu = "CPU hiệu năng cao hoặc thế hệ mới; cần kiểm tra đúng mã CPU vì ảnh hưởng lớn tới hiệu năng duy trì"
        ram = "nên ưu tiên 16GB tối thiểu; 32GB tốt hơn cho đồ họa, lập trình, AI nhẹ hoặc đa nhiệm nặng"
        storage = "SSD 512GB là tối thiểu; 1TB hợp hơn nếu cài game, lưu project hoặc dữ liệu lớn"
    else:
        cpu = "CPU tiết kiệm điện hoặc tầm trung; đủ tốt cho Office, web, học tập và họp online"
        ram = "nên ưu tiên 16GB nếu dùng lâu dài; 8GB chỉ hợp nhu cầu cơ bản"
        storage = "SSD 512GB là mức hợp lý cho học tập/văn phòng"

    if gaming:
        thermal = "tản nhiệt là tiêu chí rất quan trọng; nên xem review nhiệt độ, độ ồn và hiệu năng sau 20-30 phút tải nặng"
        battery = "pin không phải điểm mạnh khi chơi game; dùng pin chỉ phù hợp tác vụ nhẹ"
    elif office or lightweight:
        thermal = "ưu tiên máy mát, êm, bàn phím tốt và ít ồn khi làm việc văn phòng"
        battery = "pin và độ cơ động nên được ưu tiên hơn GPU nếu chủ yếu Office, web, họp online"
    else:
        thermal = "cần kiểm tra nhiệt độ và độ ồn theo đúng cấu hình bán ra"
        battery = "thời lượng pin phụ thuộc CPU/GPU, màn hình và cách dùng"

    if lightweight:
        portability = "mỏng nhẹ/dễ mang theo là lợi thế; có thể đánh đổi một phần hiệu năng hoặc khả năng nâng cấp"
    elif gaming or has_rtx:
        portability = "thường dày/nặng hơn laptop văn phòng để đổi lấy GPU và tản nhiệt"
    else:
        portability = "độ cơ động ở mức tùy phiên bản; nên kiểm tra cân nặng và sạc đi kèm"

    if creator:
        display = "nên kiểm tra độ phủ màu, độ sáng và độ phân giải nếu làm ảnh/video/thiết kế"
    elif gaming:
        display = "nên ưu tiên tần số quét cao; kiểm tra độ sáng và độ phủ màu theo từng cấu hình"
    else:
        display = "ưu tiên màn hình dễ nhìn, độ sáng ổn và chống mỏi mắt cho học tập/văn phòng"

    if gaming:
        positioning = "laptop thiên về hiệu năng và GPU, phù hợp game, kỹ thuật hoặc tác vụ nặng hơn nhu cầu văn phòng"
    elif creator:
        positioning = "laptop cân bằng giữa hiệu năng, màn hình và tính cơ động cho sáng tạo nội dung/lập trình"
    elif office:
        positioning = "laptop thiên về học tập, văn phòng, pin và độ ổn định hằng ngày"
    else:
        positioning = "laptop đa dụng, cần đối chiếu cấu hình cụ thể với nhu cầu chính"

    return {
        "positioning": positioning,
        "configuration": {
            "cpu_class": cpu,
            "gpu_class": gpu,
            "ram": ram,
            "storage": storage,
            "display": display,
            "thermal": thermal,
            "portability": portability,
            "battery": battery,
            "upgrade_notes": "cần kiểm tra RAM hàn/nâng cấp được, số khe SSD và điều kiện bảo hành khi nâng cấp",
        },
        "performance_profile": {
            "office": "mượt nếu cấu hình RAM/SSD đủ; văn phòng nên ưu tiên pin, bàn phím, webcam và độ ồn",
            "gaming": "phụ thuộc mạnh vào GPU/TGP/tản nhiệt; nên xem benchmark đúng cấu hình",
            "creator": "cần RAM, SSD và màn hình tốt; GPU rời hữu ích cho video/3D/AI nhẹ",
            "coding": "ưu tiên CPU, RAM 16GB+, SSD nhanh và bàn phím tốt",
            "battery": battery,
        },
        "buying_advice": {
            "choose_if": [
                "đúng nhóm nhu cầu chính của bạn",
                "cấu hình CPU/GPU/RAM/SSD bán ra khớp với mức giá",
            ],
            "avoid_if": [
                "bạn chỉ dùng nhu cầu nhẹ nhưng đang trả tiền cho GPU/hiệu năng không cần thiết",
                "bạn cần pin rất lâu nhưng chọn laptop gaming nặng",
            ],
            "verify": [
                "CPU/GPU đúng mã, TGP nếu là laptop gaming",
                "RAM hàn hay nâng cấp được",
                "màn hình, nhiệt độ, độ ồn và bảo hành",
            ],
        },
    }


def comparison_profile(item):
    category = item.get("category")
    detail = item.get("detail_profile") or {}
    config = detail.get("configuration") or {}
    perf = detail.get("performance_profile") or {}

    if category == "phone":
        return {
            "performance": config.get("chipset_tier", ""),
            "gaming": perf.get("gaming", ""),
            "display": config.get("display", ""),
            "battery": config.get("battery_charging", ""),
            "camera": config.get("camera", ""),
            "software": config.get("software", ""),
            "value": "so sánh theo giá thực tế, RAM/bộ nhớ và mức độ khớp nhu cầu chính",
            "risk": "cần kiểm tra hàng chính hãng, ROM, bảo hành và review nhiệt/pin thực tế",
        }
    return {
        "cpu": config.get("cpu_class", ""),
        "gpu": config.get("gpu_class", ""),
        "ram_storage": "; ".join(part for part in [config.get("ram"), config.get("storage")] if part),
        "display": config.get("display", ""),
        "thermal": config.get("thermal", ""),
        "portability_battery": "; ".join(part for part in [config.get("portability"), config.get("battery")] if part),
        "upgrade": config.get("upgrade_notes", ""),
        "value": "so sánh theo đúng cấu hình bán ra, đặc biệt CPU/GPU/RAM/SSD và bảo hành",
    }


def main():
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    for item in data:
        if item.get("category") == "phone":
            item["detail_profile"] = phone_detail_profile(item)
        elif item.get("category") == "laptop":
            item["detail_profile"] = laptop_detail_profile(item)
        else:
            item["detail_profile"] = {
                "positioning": "sản phẩm demo, cần bổ sung hồ sơ chi tiết",
                "configuration": {},
                "performance_profile": {},
                "buying_advice": {"choose_if": [], "avoid_if": [], "verify": ["giá, cấu hình và bảo hành"]},
            }
        item["comparison_profile"] = comparison_profile(item)

    CATALOG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Updated {len(data)} catalog products with detail/comparison profiles.")


if __name__ == "__main__":
    main()
