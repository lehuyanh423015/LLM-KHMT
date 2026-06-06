import json
from pathlib import Path


CATALOG = Path("apps/backend/data/mini_product_catalog.json")


NAME_FIXES = {
    "Dell Inspir?n 15": "Dell Inspiron 15",
    "Lenovo Legi?n Pro 5 RTX 4070": "Lenovo Legion Pro 5 RTX 4070",
    "Lenovo Legi?n Pro 7 RTX 4080": "Lenovo Legion Pro 7 RTX 4080",
    "Razer Blad? 16 RTX 4080": "Razer Blade 16 RTX 4080",
}


def million(value):
    return float(value or 0) / 1_000_000


def unique(items):
    output = []
    for item in items:
        if item and item not in output:
            output.append(item)
    return output


def phone_text(item):
    name = item["name"]
    tags = set(item.get("tags") or [])
    price = million(item.get("price"))

    if price < 5:
        segment = "giá rẻ cho liên lạc, học tập, giải trí nhẹ và dùng hằng ngày"
    elif price < 10:
        segment = "phổ thông/tầm trung, phù hợp người cần máy dễ dùng và giá hợp lý"
    elif price < 18:
        segment = "tầm trung khá, cân bằng giữa hiệu năng, pin, màn hình và camera"
    elif price < 28:
        segment = "cận cao cấp, hợp người muốn trải nghiệm tốt hơn máy phổ thông"
    else:
        segment = "cao cấp, phù hợp người cần camera, màn hình, hiệu năng và trải nghiệm hoàn thiện"

    if "gaming" in tags or "performance" in tags:
        focus = "ưu tiên hiệu năng, độ mượt và khả năng chơi game trong tầm giá"
    elif "camera" in tags and "premium" in tags:
        focus = "ưu tiên camera, quay/chụp và trải nghiệm cao cấp"
    elif "camera" in tags:
        focus = "ưu tiên camera, chụp ảnh và nhu cầu mạng xã hội"
    elif "battery" in tags:
        focus = "ưu tiên pin, độ ổn định và dùng lâu trong ngày"
    elif "software" in tags:
        focus = "ưu tiên phần mềm, cập nhật và độ ổn định"
    elif "display" in tags:
        focus = "ưu tiên màn hình và trải nghiệm xem nội dung"
    else:
        focus = "phù hợp nhu cầu cân bằng"

    strengths = []
    if "gaming" in tags or "performance" in tags:
        strengths.append("hiệu năng tốt trong tầm giá")
    if "camera" in tags:
        strengths.append("camera/chụp ảnh là điểm đáng chú ý")
    if "display" in tags:
        strengths.append("màn hình phù hợp xem nội dung và thao tác hằng ngày")
    if "battery" in tags:
        strengths.append("pin là lợi thế so với nhiều mẫu cùng phân khúc")
    if "software" in tags:
        strengths.append("phần mềm/cập nhật và hệ sinh thái là điểm mạnh")
    if "premium" in tags:
        strengths.append("trải nghiệm hoàn thiện hơn nhóm phổ thông")
    if "value" in tags:
        strengths.append("giá/hiệu năng tốt trong dữ liệu demo")
    strengths = unique(strengths)[:3] or ["phù hợp nhu cầu phổ thông và dễ chọn"]

    weaknesses = [
        "giá và cấu hình có thể khác nhau theo cửa hàng/phiên bản",
        "cần kiểm tra bảo hành, nguồn hàng và bộ nhớ trước khi mua",
    ]
    if "gaming" not in tags:
        weaknesses.insert(0, "không phải lựa chọn tối ưu nếu bạn ưu tiên chơi game nặng lâu dài")
    if "camera" not in tags:
        weaknesses.insert(0, "camera có thể không phải điểm mạnh nhất trong phân khúc")
    if "premium" in tags:
        weaknesses.append("giá/hiệu năng có thể kém hơn các mẫu thiên cấu hình")
    weaknesses = unique(weaknesses)[:4]

    avoid_if = []
    if "gaming" not in tags:
        avoid_if.append("bạn ưu tiên FPS/hiệu năng game cao nhất trong tầm giá")
    if "camera" not in tags:
        avoid_if.append("bạn cần camera/quay video tốt nhất trong phân khúc")
    if "premium" in tags:
        avoid_if.append("bạn muốn tối ưu chi phí hơn trải nghiệm cao cấp")
    avoid_if = avoid_if[:2] or ["bạn có yêu cầu rất chuyên biệt chưa có trong catalog demo"]

    chipset = "nhóm phổ thông" if price < 8 else "nhóm tầm trung" if price < 18 else "nhóm cận cao cấp" if price < 28 else "nhóm flagship/cao cấp"
    specs = {
        "chipset": chipset,
        "ram_storage": "cần kiểm tra đúng phiên bản RAM/bộ nhớ trước khi mua",
        "screen": "ưu tiên màn hình đẹp/tần số quét cao nếu bạn xem phim, chơi game hoặc đọc nhiều",
        "battery": "thời lượng pin phụ thuộc phiên bản, độ sáng màn hình và cách dùng",
        "camera": "thiên camera" if "camera" in tags else "đủ dùng; nên xem review ảnh/video thực tế",
        "software": "cần kiểm tra chính sách cập nhật và bảo hành theo thị trường Việt Nam",
    }

    item["description"] = f"{name} là điện thoại {segment}; {focus}."
    item["best_for"] = build_best_for(tags, category="phone")
    item["strengths"] = strengths
    item["weaknesses"] = weaknesses
    item["avoid_if"] = avoid_if
    item["specs"] = specs
    item["decision_notes"] = {
        "verify_before_buying": [
            "giá hiện tại",
            "đúng phiên bản RAM/bộ nhớ",
            "bảo hành và nguồn bán",
        ]
    }


def laptop_text(item):
    name = item["name"]
    tags = set(item.get("tags") or [])

    office_desc = (
        f"{name} phù hợp học tập, văn phòng, Office, web, họp online và làm việc hằng ngày; "
        "ưu tiên pin, độ ổn định, bàn phím và tính cơ động hơn hiệu năng nặng."
    )
    gaming_desc = (
        f"{name} phù hợp chơi game, học kỹ thuật hoặc tác vụ cần GPU; "
        "nên kiểm tra đúng cấu hình GPU/RAM, tản nhiệt và màn hình theo từng phiên bản."
    )
    creator_desc = (
        f"{name} phù hợp tác vụ nặng hơn văn phòng cơ bản như lập trình, chỉnh ảnh, dựng video, "
        "xử lý dữ liệu hoặc đa nhiệm lớn; cần cân bằng CPU, RAM, màn hình và GPU."
    )
    hybrid_desc = (
        f"{name} là laptop hiệu năng cao cho game, kỹ thuật và tác vụ đồ họa/video; "
        "phù hợp khi bạn ưu tiên GPU, tản nhiệt và hiệu năng duy trì hơn pin/mỏng nhẹ."
    )

    office_strengths = [
        "pin và tính cơ động phù hợp làm việc/học tập hằng ngày",
        "mượt cho Office, web, họp online và đa nhiệm nhẹ",
        "dễ dùng, dễ kiểm tra bảo hành và phù hợp người dùng phổ thông",
    ]
    office_weaknesses = [
        "không tối ưu cho game nặng hoặc render/3D",
        "nên ưu tiên RAM 16GB nếu muốn dùng lâu dài và mở nhiều tab",
        "màn hình, loa và bàn phím cần kiểm tra theo từng phiên bản",
    ]
    office_specs = {
        "cpu": "CPU tiết kiệm điện hoặc dòng U/P đủ mượt cho Office, web và họp online",
        "gpu": "GPU tích hợp, không dành cho game nặng hoặc render 3D",
        "ram": "nên ưu tiên 16GB để dùng lâu dài và mở nhiều ứng dụng",
        "storage": "SSD 512GB là mức hợp lý cho học tập/văn phòng",
        "screen": "ưu tiên màn hình dễ nhìn, độ sáng ổn; OLED là lợi thế nếu làm nội dung nhẹ",
        "portability": "ưu tiên mỏng nhẹ, bàn phím tốt và dễ mang theo",
        "battery": "pin tốt hơn laptop gaming khi dùng Office, web và họp online",
    }

    gaming_strengths = [
        "hiệu năng chơi game tốt trong phân khúc",
        "GPU rời giúp xử lý game, kỹ thuật và tác vụ đồ họa tốt hơn máy văn phòng",
        "tản nhiệt và hiệu năng duy trì là điểm cần ưu tiên kiểm tra",
    ]
    gaming_weaknesses = [
        "thân máy thường dày/nặng hơn laptop văn phòng",
        "pin khi chơi game hoặc chạy tác vụ nặng sẽ hao nhanh",
        "màn hình, nhiệt độ và độ ồn khác nhau theo từng phiên bản",
    ]
    gaming_specs = {
        "cpu": "CPU hiệu năng cao dòng H/HS/HX hoặc tương đương",
        "gpu": "GPU rời RTX hoặc tương đương; cần kiểm tra đúng mã GPU/TGP",
        "ram": "RAM 16GB là tối thiểu hợp lý; 32GB tốt hơn nếu chơi game nặng, kỹ thuật hoặc dựng video",
        "storage": "SSD 512GB-1TB, game và file dự án sẽ chiếm dung lượng lớn",
        "screen": "nên ưu tiên tần số quét cao; nếu làm sáng tạo cần kiểm tra độ phủ màu",
        "portability": "đổi lại bằng thân máy dày/nặng hơn để có hiệu năng và tản nhiệt",
        "battery": "pin không phải điểm mạnh khi chơi game hoặc chạy tải nặng",
    }

    creator_strengths = [
        "phù hợp tác vụ đồ họa, dựng video, lập trình hoặc xử lý đa nhiệm nặng",
        "màn hình, RAM và hiệu năng duy trì quan trọng hơn máy văn phòng phổ thông",
        "có thể cân bằng giữa làm việc và giải trí nếu cấu hình đủ mạnh",
    ]
    creator_weaknesses = [
        "cần kiểm tra RAM, GPU, màn hình và khả năng tản nhiệt theo đúng phiên bản",
        "giá thường cao hơn máy văn phòng cùng kích thước",
        "nếu làm 3D/render nặng thường xuyên nên ưu tiên GPU rời mạnh",
    ]
    creator_specs = {
        "cpu": "CPU hiệu năng tốt, ưu tiên dòng H/HS hoặc chip Apple/Intel/AMD đủ mạnh theo tác vụ",
        "gpu": "GPU rời cần thiết cho dựng video, 3D, AI hoặc game; tác vụ nhẹ có thể dùng GPU tích hợp mạnh",
        "ram": "RAM 16GB là mức tối thiểu; 32GB nên cân nhắc nếu dựng video, 3D hoặc mở dự án lớn",
        "storage": "SSD 512GB-1TB, nên có thêm ổ ngoài nếu làm video/dữ liệu lớn",
        "screen": "ưu tiên màn hình đẹp, độ phân giải/độ phủ màu tốt nếu chỉnh ảnh/video",
        "portability": "cân bằng giữa hiệu năng và cân nặng tùy nhu cầu di chuyển",
        "battery": "pin phụ thuộc tải công việc; tác vụ nặng sẽ hao nhanh hơn văn phòng",
    }

    if "gaming" in tags and "creator" in tags:
        item["description"] = hybrid_desc
        item["strengths"] = unique([creator_strengths[0]] + gaming_strengths[:2])
        item["weaknesses"] = gaming_weaknesses
        item["avoid_if"] = [
            "bạn ưu tiên máy rất nhẹ, pin rất lâu và làm việc yên tĩnh",
            "bạn chỉ dùng Office/web cơ bản và muốn tiết kiệm chi phí",
        ]
        item["specs"] = gaming_specs
    elif "gaming" in tags:
        item["description"] = gaming_desc
        item["strengths"] = gaming_strengths
        item["weaknesses"] = gaming_weaknesses
        item["avoid_if"] = [
            "bạn ưu tiên máy rất nhẹ, pin rất lâu và làm việc yên tĩnh",
            "bạn chỉ dùng Office/web cơ bản và muốn tiết kiệm chi phí",
        ]
        item["specs"] = gaming_specs
    elif "creator" in tags:
        item["description"] = creator_desc
        item["strengths"] = creator_strengths
        item["weaknesses"] = creator_weaknesses
        item["avoid_if"] = [
            "bạn chỉ dùng Office, web và họp online cơ bản",
            "bạn cần máy cực nhẹ, pin rất lâu hơn là hiệu năng",
        ]
        item["specs"] = creator_specs
    else:
        item["description"] = office_desc
        item["strengths"] = office_strengths
        item["weaknesses"] = office_weaknesses
        item["avoid_if"] = [
            "bạn cần GPU rời để chơi game nặng, dựng video hoặc render thường xuyên",
            "bạn cần màn hình màu rất chuẩn cho thiết kế chuyên nghiệp",
        ]
        item["specs"] = office_specs

    item["best_for"] = build_best_for(tags, category="laptop")
    item["decision_notes"] = {
        "verify_before_buying": [
            "giá hiện tại",
            "đúng phiên bản CPU/GPU/RAM/SSD",
            "bảo hành chính hãng hoặc nguồn bán đáng tin cậy",
        ]
    }


def build_best_for(tags, category):
    values = []
    if category == "phone":
        if "gaming" in tags or "performance" in tags:
            values.append("chơi game và cần hiệu năng tốt")
        if "camera" in tags:
            values.append("chụp ảnh/quay video")
        if "battery" in tags:
            values.append("pin lâu và dùng hằng ngày")
        if "software" in tags:
            values.append("cập nhật phần mềm và độ ổn định")
        if "display" in tags:
            values.append("màn hình đẹp")
        if "value" in tags:
            values.append("tối ưu chi phí")
    else:
        if "office" in tags or "student" in tags:
            values.append("học tập, văn phòng, Office và họp online")
        if "gaming" in tags:
            values.append("chơi game hoặc học kỹ thuật cần GPU")
        if "creator" in tags:
            values.append("lập trình, chỉnh ảnh, dựng video hoặc tác vụ nặng")
        if "lightweight" in tags:
            values.append("di chuyển nhiều và cần máy gọn nhẹ")
        if "battery" in tags:
            values.append("ưu tiên pin")
        if "display" in tags:
            values.append("màn hình đẹp")
    return unique(values)[:4] or ["nhu cầu cân bằng"]


def main():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    for item in data:
        item["name"] = NAME_FIXES.get(item.get("name"), item.get("name"))
        if item.get("category") == "phone":
            phone_text(item)
        elif item.get("category") == "laptop":
            laptop_text(item)
    CATALOG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"repaired {len(data)} catalog items")


if __name__ == "__main__":
    main()
