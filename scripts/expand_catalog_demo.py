import json
from pathlib import Path
from urllib.parse import quote_plus


CATALOG = Path("apps/backend/data/mini_product_catalog.json")


def url_for(name, category):
    return "https://www.google.com/search?q=" + quote_plus(f"{name} {category} gia Viet Nam review")


def segment(price):
    m = price / 1_000_000
    if m < 5:
        return "under-5m"
    if m < 10:
        return "5-10m"
    if m < 15:
        return "10-15m"
    if m < 20:
        return "15-20m"
    if m < 25:
        return "20-25m"
    if m < 30:
        return "25-30m"
    if m < 40:
        return "30-40m"
    if m < 60:
        return "40-60m"
    if m < 80:
        return "60-80m"
    return "80-100m"


def phone(name, price, brand, tags, description, strengths, weaknesses, avoid_if, specs_extra=None):
    specs = {
        "chipset": "nhóm flagship/cao cấp" if price >= 25_000_000 else "nhóm tầm trung/cận cao cấp",
        "ram_storage": "cần kiểm tra đúng phiên bản RAM/bộ nhớ trước khi mua",
        "screen": "ưu tiên màn hình tần số quét cao nếu chơi game hoặc xem nội dung nhiều",
        "battery": "pin và sạc nhanh cần kiểm tra theo từng phiên bản/thị trường",
        "camera": "không phải trọng tâm chính" if "camera" not in tags else "thiên camera",
        "software": "cần kiểm tra ROM, bảo hành và chính sách cập nhật tại Việt Nam",
    }
    specs.update(specs_extra or {})
    return {
        "id": "phone-" + name.lower().replace(" ", "-").replace("+", "plus"),
        "name": name,
        "price": price,
        "currency": "VND",
        "description": description,
        "category": "phone",
        "url": url_for(name, "phone"),
        "source": "expanded_demo_catalog",
        "tags": tags,
        "brand": brand,
        "year": 2025 if "15" not in name and "11" not in name else 2026,
        "price_segment": segment(price),
        "last_updated": "2026-06",
        "data_confidence": "demo_estimate",
        "best_for": [
            "chơi game/hiệu năng cao",
            "pin và màn hình tốt",
            "người ưu tiên cấu hình hơn camera",
        ],
        "strengths": strengths,
        "weaknesses": weaknesses,
        "avoid_if": avoid_if,
        "specs": specs,
        "decision_notes": {
            "verify_before_buying": [
                "giá hiện tại tại Việt Nam",
                "ROM/quốc tế hay nội địa",
                "bảo hành và khả năng sửa chữa",
            ]
        },
    }


def laptop(name, price, brand, tags, description, strengths, weaknesses, avoid_if, specs, year=2025):
    return {
        "id": "laptop-" + name.lower().replace(" ", "-").replace("/", "-"),
        "name": name,
        "price": price,
        "currency": "VND",
        "description": description,
        "category": "laptop",
        "url": url_for(name, "laptop"),
        "source": "expanded_demo_catalog",
        "tags": tags,
        "brand": brand,
        "year": year,
        "price_segment": segment(price),
        "last_updated": "2026-06",
        "data_confidence": "demo_estimate",
        "best_for": [],
        "strengths": strengths,
        "weaknesses": weaknesses,
        "avoid_if": avoid_if,
        "specs": specs,
        "decision_notes": {
            "verify_before_buying": [
                "giá hiện tại",
                "đúng phiên bản CPU/GPU/RAM/SSD",
                "TGP GPU, màn hình và bảo hành",
            ]
        },
    }


PHONE_ADDITIONS = [
    phone(
        "RedMagic 10 Pro",
        24990000,
        "nubia",
        ["gaming", "performance", "battery", "display", "cooling", "value"],
        "RedMagic 10 Pro phù hợp người chơi game nghiêm túc, ưu tiên hiệu năng duy trì, tản nhiệt, pin lớn và màn hình tần số quét cao hơn camera.",
        ["hiệu năng gaming duy trì tốt", "pin lớn và sạc nhanh", "tản nhiệt chủ động phù hợp chơi lâu"],
        ["camera và phần mềm có thể không hợp người dùng phổ thông", "cần kiểm tra ROM, bảo hành và nguồn hàng"],
        ["bạn cần camera tốt, bảo hành phổ thông hoặc phần mềm dễ dùng như Samsung/iPhone"],
    ),
    phone(
        "RedMagic 11 Pro",
        31990000,
        "nubia",
        ["gaming", "performance", "battery", "display", "cooling", "premium"],
        "RedMagic 11 Pro là mẫu gaming cao cấp, hợp người muốn dùng gần hết ngân sách 30-35 triệu cho hiệu năng, tản nhiệt và pin thay vì camera.",
        ["rất mạnh cho gaming và tải nặng", "màn hình/tản nhiệt thiên chơi game", "pin lớn phù hợp chơi lâu"],
        ["nguồn hàng và bảo hành cần kiểm tra kỹ", "camera không phải điểm mạnh chính"],
        ["bạn ưu tiên camera, máy mỏng nhẹ hoặc trải nghiệm phần mềm phổ thông"],
    ),
    phone(
        "ASUS ROG Phone 9",
        26990000,
        "asus",
        ["gaming", "performance", "battery", "display", "cooling", "premium"],
        "ASUS ROG Phone 9 phù hợp game thủ cần hiệu năng cao, pin tốt, màn hình nhanh và hệ sinh thái phụ kiện gaming.",
        ["hiệu năng và tản nhiệt thiên gaming", "pin tốt trong nhóm máy hiệu năng cao", "trải nghiệm chơi game chuyên biệt"],
        ["giá/nguồn hàng có thể biến động", "camera không phải lý do chính để chọn"],
        ["bạn cần máy phổ thông dễ bảo hành hoặc camera tốt nhất trong tầm giá"],
    ),
    phone(
        "ASUS ROG Phone 9 Pro",
        34990000,
        "asus",
        ["gaming", "performance", "battery", "display", "cooling", "premium"],
        "ASUS ROG Phone 9 Pro là lựa chọn cao cấp cho người chơi game nặng, ưu tiên hiệu năng duy trì và pin hơn camera.",
        ["gaming rất mạnh", "tản nhiệt và màn hình tốt", "pin phù hợp chơi lâu"],
        ["giá cao và cần kiểm tra nguồn hàng", "không tối ưu nếu bạn chỉ dùng phổ thông"],
        ["bạn cần camera/quay video tốt nhất hoặc máy gọn nhẹ"],
    ),
    phone(
        "iQOO 13",
        21990000,
        "vivo",
        ["gaming", "performance", "battery", "display", "value"],
        "iQOO 13 hợp người cần hiệu năng flagship với giá dễ chịu hơn gaming phone chuyên dụng, phù hợp chơi game và dùng hằng ngày.",
        ["hiệu năng/giá tốt", "màn hình và pin phù hợp chơi game", "ít cực đoan hơn gaming phone chuyên dụng"],
        ["cần kiểm tra ROM và bảo hành", "camera không phải ưu tiên số một"],
        ["bạn muốn máy chính hãng dễ mua hoặc ưu tiên camera"],
    ),
    phone(
        "iQOO 15",
        29990000,
        "vivo",
        ["gaming", "performance", "battery", "display", "premium"],
        "iQOO 15 phù hợp người có ngân sách khoảng 30 triệu, muốn hiệu năng flagship, pin tốt và màn hình đẹp cho gaming.",
        ["gần đúng ngân sách 30 triệu", "hiệu năng flagship", "pin/màn hình hợp chơi game"],
        ["nguồn hàng Việt Nam cần kiểm tra", "camera không phải trọng tâm như Vivo X series"],
        ["bạn ưu tiên camera hoặc bảo hành chính hãng phổ thông"],
    ),
    phone(
        "OnePlus 13",
        22990000,
        "oneplus",
        ["gaming", "performance", "battery", "display", "premium"],
        "OnePlus 13 là flagship Android cân bằng, mạnh về hiệu năng, pin và màn hình, hợp người chơi game nhưng vẫn muốn máy dùng hằng ngày dễ chịu.",
        ["hiệu năng cao", "pin tốt", "trải nghiệm cân bằng hơn gaming phone chuyên dụng"],
        ["bảo hành/nguồn hàng cần kiểm tra", "không chuyên gaming bằng ROG/RedMagic"],
        ["bạn cần bảo hành chính hãng rộng hoặc camera zoom tốt nhất"],
    ),
    phone(
        "OnePlus 15",
        31990000,
        "oneplus",
        ["gaming", "performance", "battery", "display", "premium"],
        "OnePlus 15 phù hợp người muốn flagship hiệu năng mới, pin lớn và trải nghiệm Android cao cấp trong vùng 30-35 triệu.",
        ["hiệu năng rất cao", "pin/màn hình tốt", "hợp gaming lẫn dùng hằng ngày"],
        ["giá và nguồn hàng tùy thị trường", "không phải máy gaming chuyên dụng"],
        ["bạn muốn camera tốt nhất hoặc bảo hành chính hãng dễ kiểm tra"],
    ),
    phone(
        "Realme GT 7 Pro",
        19990000,
        "realme",
        ["gaming", "performance", "battery", "value", "display"],
        "Realme GT 7 Pro phù hợp người muốn hiệu năng cao và pin tốt với chi phí thấp hơn flagship Samsung/Apple.",
        ["hiệu năng/giá tốt", "pin lớn", "phù hợp chơi game trong tầm dưới 20-22 triệu"],
        ["phần mềm và bảo hành cần kiểm tra", "camera không phải điểm mạnh nhất"],
        ["bạn muốn dùng gần hết ngân sách 30 triệu cho trải nghiệm cao cấp hơn"],
    ),
    phone(
        "Xiaomi 15 Pro",
        28990000,
        "xiaomi",
        ["performance", "battery", "camera", "display", "premium"],
        "Xiaomi 15 Pro phù hợp người muốn flagship Android mạnh, pin tốt, màn hình đẹp và vẫn có camera tốt khi cần.",
        ["hiệu năng flagship", "pin và màn hình tốt", "trải nghiệm cao cấp trong vùng 30 triệu"],
        ["không chuyên gaming bằng ROG/RedMagic", "cần kiểm tra phiên bản và bảo hành"],
        ["bạn chỉ muốn gaming phone chuyên dụng hoặc không cần camera để tiết kiệm hơn"],
    ),
    phone(
        "Honor Magic7 Pro",
        24990000,
        "honor",
        ["performance", "battery", "camera", "display", "premium"],
        "Honor Magic7 Pro là flagship Android cân bằng, hợp người cần pin, màn hình, camera và hiệu năng tốt.",
        ["pin/màn hình/camera cân bằng", "hiệu năng cao", "trải nghiệm cao cấp"],
        ["nguồn hàng và bảo hành cần kiểm tra", "không thiên gaming bằng máy chuyên game"],
        ["bạn ưu tiên FPS/tản nhiệt gaming hơn camera"],
    ),
    phone(
        "Google Pixel 9 Pro",
        24990000,
        "google",
        ["camera", "software", "premium", "compact"],
        "Google Pixel 9 Pro phù hợp người ưu tiên camera, AI/phần mềm và trải nghiệm Android sạch hơn hiệu năng gaming.",
        ["camera và phần mềm là điểm mạnh", "máy cao cấp gọn", "phù hợp người thích Android sạch"],
        ["không tối ưu cho gaming nặng lâu dài", "bảo hành/nguồn hàng cần kiểm tra"],
        ["bạn ưu tiên hiệu năng game, pin và tản nhiệt"],
    ),
]


LAPTOP_COMMON_GAMING_SPECS = {
    "cpu": "CPU H/HS/HX hoặc tương đương, cần kiểm tra đúng đời chip",
    "gpu": "GPU rời RTX, cần kiểm tra đúng mã và TGP",
    "ram": "RAM 16GB tối thiểu; 32GB tốt hơn nếu game/tác vụ nặng",
    "storage": "SSD 512GB-1TB",
    "screen": "ưu tiên tần số quét cao; nếu làm đồ họa cần kiểm tra độ phủ màu",
    "portability": "thường dày/nặng hơn ultrabook",
    "battery": "pin không phải điểm mạnh khi chạy game/tải nặng",
}

LAPTOP_OFFICE_SPECS = {
    "cpu": "CPU tiết kiệm điện đủ mượt cho Office, web và họp online",
    "gpu": "GPU tích hợp, không dành cho game/render nặng",
    "ram": "nên ưu tiên 16GB để dùng lâu dài",
    "storage": "SSD 512GB là mức hợp lý",
    "screen": "ưu tiên màn hình sáng, dễ nhìn; OLED là lợi thế nếu làm nội dung nhẹ",
    "portability": "mỏng nhẹ, bàn phím tốt và dễ mang theo",
    "battery": "pin là tiêu chí quan trọng với văn phòng/học tập",
}

LAPTOP_ADDITIONS = [
    laptop(
        "Lenovo LOQ 15 RTX 4060 2025",
        27990000,
        "lenovo",
        ["gaming", "performance", "rtx", "value", "student"],
        "Lenovo LOQ 15 RTX 4060 2025 phù hợp người cần laptop gaming/đồ họa tầm 28-30 triệu, ưu tiên hiệu năng/giá.",
        ["RTX 4060 hợp gaming Full HD/QHD nhẹ", "giá/hiệu năng tốt", "phù hợp sinh viên kỹ thuật"],
        ["màn hình/tản nhiệt tùy phiên bản", "không mỏng nhẹ như ultrabook"],
        ["bạn cần máy rất nhẹ, pin lâu hoặc màn hình màu chuyên nghiệp"],
        LAPTOP_COMMON_GAMING_SPECS,
    ),
    laptop(
        "HP Victus 16 RTX 4060",
        25990000,
        "hp",
        ["gaming", "performance", "rtx", "value", "student"],
        "HP Victus 16 RTX 4060 phù hợp người muốn màn hình lớn hơn và GPU đủ mạnh trong vùng 25-28 triệu.",
        ["cấu hình hợp game/tác vụ kỹ thuật", "màn hình lớn dễ làm việc", "giá thường dễ tiếp cận hơn Omen"],
        ["build/tản nhiệt cần kiểm tra theo phiên bản", "không cao cấp bằng Omen/Legion"],
        ["bạn cần máy cao cấp, rất mỏng nhẹ hoặc pin lâu"],
        LAPTOP_COMMON_GAMING_SPECS,
    ),
    laptop(
        "Dell G15 RTX 4060",
        28990000,
        "dell",
        ["gaming", "performance", "rtx", "durable"],
        "Dell G15 RTX 4060 phù hợp người cần laptop gaming bền, dễ bảo hành và cấu hình ổn định quanh 30 triệu.",
        ["thương hiệu/bảo hành dễ kiểm tra", "hiệu năng gaming tốt", "khung máy chắc"],
        ["thân máy thường nặng", "màn hình/cấu hình cần kiểm tra từng mã"],
        ["bạn cần máy nhẹ hoặc pin lâu cho văn phòng"],
        LAPTOP_COMMON_GAMING_SPECS,
    ),
    laptop(
        "ASUS TUF A14 RTX 4060",
        32990000,
        "asus",
        ["gaming", "performance", "rtx", "lightweight", "premium"],
        "ASUS TUF A14 RTX 4060 phù hợp người muốn laptop gaming gọn hơn, vẫn có GPU rời và hiệu năng tốt.",
        ["gọn hơn nhiều laptop gaming 15-16 inch", "RTX 4060 phù hợp game/tác vụ kỹ thuật", "cân bằng hiệu năng và di động"],
        ["giá cao hơn laptop gaming phổ thông", "cần kiểm tra nhiệt độ do thân máy gọn"],
        ["bạn cần hiệu năng tối đa/giá tốt nhất hoặc màn hình lớn"],
        LAPTOP_COMMON_GAMING_SPECS,
    ),
    laptop(
        "Lenovo Legion 5 RTX 4070",
        45990000,
        "lenovo",
        ["gaming", "creator", "performance", "rtx", "durable"],
        "Lenovo Legion 5 RTX 4070 phù hợp game nặng, kỹ thuật, dựng video và người cần tản nhiệt tốt hơn laptop gaming phổ thông.",
        ["RTX 4070 mạnh hơn RTX 4060", "tản nhiệt và hiệu năng duy trì tốt", "hợp tác vụ nặng dài hạn"],
        ["giá cao hơn vùng phổ thông", "khá nặng nếu di chuyển nhiều"],
        ["bạn chỉ dùng văn phòng hoặc muốn máy thật nhẹ"],
        LAPTOP_COMMON_GAMING_SPECS,
    ),
    laptop(
        "ASUS ROG Strix G16 RTX 4060",
        39990000,
        "asus",
        ["gaming", "performance", "rtx", "premium", "display"],
        "ASUS ROG Strix G16 RTX 4060 phù hợp người muốn trải nghiệm gaming cao cấp hơn TUF/LOQ, ưu tiên màn hình và tản nhiệt.",
        ["trải nghiệm gaming cao cấp", "màn hình/tản nhiệt tốt", "hiệu năng ổn định"],
        ["giá cao hơn máy RTX 4060 phổ thông", "không tối ưu nếu chỉ cần Office"],
        ["bạn ưu tiên giá/hiệu năng hoặc pin/mỏng nhẹ"],
        LAPTOP_COMMON_GAMING_SPECS,
    ),
    laptop(
        "Acer Predator Helios Neo 16 RTX 4070",
        46990000,
        "acer",
        ["gaming", "creator", "performance", "rtx", "display"],
        "Acer Predator Helios Neo 16 RTX 4070 hợp game nặng và tác vụ đồ họa/video cần GPU mạnh hơn RTX 4060.",
        ["GPU mạnh cho game/tác vụ nặng", "màn hình lớn", "tản nhiệt tốt trong phân khúc"],
        ["thân máy lớn", "giá cao và cần kiểm tra đúng cấu hình"],
        ["bạn cần máy nhẹ hoặc chỉ làm văn phòng"],
        LAPTOP_COMMON_GAMING_SPECS,
    ),
    laptop(
        "ASUS Zenbook 14 OLED 2025",
        28990000,
        "asus",
        ["office", "lightweight", "display", "battery", "premium"],
        "ASUS Zenbook 14 OLED 2025 phù hợp văn phòng cao cấp, học tập, thuyết trình và chỉnh ảnh nhẹ với màn hình đẹp.",
        ["mỏng nhẹ", "màn OLED đẹp", "pin và trải nghiệm văn phòng tốt"],
        ["không dành cho game nặng", "giá cao hơn laptop văn phòng phổ thông"],
        ["bạn cần GPU rời hoặc render/game nặng"],
        LAPTOP_OFFICE_SPECS,
    ),
    laptop(
        "Lenovo Yoga Slim 7",
        27990000,
        "lenovo",
        ["office", "lightweight", "battery", "display", "premium"],
        "Lenovo Yoga Slim 7 phù hợp người làm văn phòng, học tập và di chuyển nhiều, ưu tiên pin, màn hình và độ mượt.",
        ["mỏng nhẹ và pin tốt", "phù hợp Office/web/họp online", "trải nghiệm cao cấp hơn máy phổ thông"],
        ["không tối ưu game nặng", "cấu hình thay đổi theo phiên bản"],
        ["bạn cần GPU rời hoặc chơi game thường xuyên"],
        LAPTOP_OFFICE_SPECS,
    ),
    laptop(
        "HP OmniBook Ultra 14",
        32990000,
        "hp",
        ["office", "lightweight", "battery", "premium", "ai_work"],
        "HP OmniBook Ultra 14 phù hợp người cần ultrabook mới cho văn phòng, họp online, AI nhẹ và di chuyển nhiều.",
        ["mỏng nhẹ", "pin tốt cho làm việc", "hợp văn phòng hiện đại và AI nhẹ"],
        ["không dành cho game nặng", "giá cao hơn laptop phổ thông"],
        ["bạn cần GPU rời hoặc màn hình gaming"],
        LAPTOP_OFFICE_SPECS,
    ),
    laptop(
        "Dell XPS 14",
        49990000,
        "dell",
        ["office", "creator", "premium", "display", "lightweight"],
        "Dell XPS 14 phù hợp người cần laptop cao cấp cho văn phòng, sáng tạo nội dung nhẹ-vừa và màn hình đẹp.",
        ["build cao cấp", "màn hình đẹp", "phù hợp làm việc chuyên nghiệp"],
        ["giá cao", "không tối ưu gaming/hiệu năng thô như laptop RTX lớn"],
        ["bạn ưu tiên giá/hiệu năng hoặc gaming nặng"],
        {
            **LAPTOP_OFFICE_SPECS,
            "gpu": "tùy phiên bản, có thể có GPU rời nhẹ; cần kiểm tra đúng cấu hình",
        },
    ),
]


def main():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    existing_names = {item["name"] for item in data}
    additions = PHONE_ADDITIONS + LAPTOP_ADDITIONS
    added = 0
    for item in additions:
        if item["name"] in existing_names:
            continue
        data.append(item)
        existing_names.add(item["name"])
        added += 1
    CATALOG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"added {added}, total {len(data)}")


if __name__ == "__main__":
    main()
