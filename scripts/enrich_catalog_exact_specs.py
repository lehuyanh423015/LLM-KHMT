from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "apps" / "backend" / "data" / "mini_product_catalog.json"


def norm(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def phone_specs(name: str) -> dict:
    n = norm(name)
    exact = {
        "xiaomi redmi 14c": ("MediaTek Helio G81 Ultra", "4GB/6GB/8GB", "128GB/256GB", "6.88-inch IPS LCD 120Hz", "5160mAh", "18W", "50MP main", "Android/HyperOS"),
        "samsung galaxy a06": ("MediaTek Helio G85", "4GB/6GB", "64GB/128GB", "6.7-inch PLS LCD 60Hz", "5000mAh", "25W", "50MP main + 2MP depth", "Android/One UI Core"),
        "realme c67": ("Qualcomm Snapdragon 685", "8GB", "128GB/256GB", "6.72-inch IPS LCD 90Hz", "5000mAh", "33W", "108MP main", "Android/realme UI"),
        "samsung galaxy a16 5g": ("MediaTek Dimensity 6300", "4GB/6GB/8GB", "128GB/256GB", "6.7-inch Super AMOLED 90Hz", "5000mAh", "25W", "50MP main + 5MP ultrawide + 2MP macro", "Android/One UI"),
        "xiaomi redmi note 14": ("MediaTek Helio G99-Ultra", "6GB/8GB", "128GB/256GB", "6.67-inch AMOLED 120Hz", "5500mAh", "33W", "108MP main", "Android/HyperOS"),
        "cmf phone 2 pro": ("MediaTek Dimensity 7300 Pro", "8GB", "128GB/256GB", "6.77-inch AMOLED 120Hz", "5000mAh", "33W", "50MP main + 50MP telephoto + 8MP ultrawide", "Android/Nothing OS"),
        "xiaomi redmi note 13 pro": ("Qualcomm Snapdragon 7s Gen 2", "8GB/12GB", "256GB/512GB", "6.67-inch AMOLED 120Hz", "5100mAh", "67W", "200MP main + 8MP ultrawide + 2MP macro", "Android/HyperOS"),
        "xiaomi redmi note 14 pro 5g": ("MediaTek Dimensity 7300-Ultra", "8GB/12GB", "256GB/512GB", "6.67-inch AMOLED 120Hz", "5110mAh", "45W", "200MP main + 8MP ultrawide + 2MP macro", "Android/HyperOS"),
        "nothing phone 2a": ("MediaTek Dimensity 7200 Pro", "8GB/12GB", "128GB/256GB", "6.7-inch AMOLED 120Hz", "5000mAh", "45W", "50MP main + 50MP ultrawide", "Android/Nothing OS"),
        "samsung galaxy a36 5g": ("Qualcomm Snapdragon 6 Gen 3", "6GB/8GB/12GB", "128GB/256GB", "6.7-inch Super AMOLED 120Hz", "5000mAh", "45W", "50MP main + 8MP ultrawide + 5MP macro", "Android/One UI"),
        "oppo reno13 f": ("Qualcomm Snapdragon 6 Gen 1", "8GB/12GB", "256GB/512GB", "6.67-inch AMOLED 120Hz", "5800mAh", "45W", "50MP main + 8MP ultrawide + 2MP macro", "Android/ColorOS"),
        "poco x6 pro": ("MediaTek Dimensity 8300-Ultra", "8GB/12GB", "256GB/512GB", "6.67-inch AMOLED 120Hz", "5000mAh", "67W", "64MP main + 8MP ultrawide + 2MP macro", "Android/HyperOS"),
        "vivo v50 lite": ("Qualcomm Snapdragon 685 / Dimensity 6300 tùy bản", "8GB/12GB", "256GB", "6.77-inch AMOLED 120Hz", "6500mAh", "90W", "50MP main + 8MP ultrawide", "Android/Funtouch OS"),
        "samsung galaxy a55": ("Samsung Exynos 1480", "8GB/12GB", "128GB/256GB", "6.6-inch Super AMOLED 120Hz", "5000mAh", "25W", "50MP main + 12MP ultrawide + 5MP macro", "Android/One UI"),
        "google pixel 8a": ("Google Tensor G3", "8GB", "128GB/256GB", "6.1-inch OLED 120Hz", "4492mAh", "18W wired + wireless", "64MP main + 13MP ultrawide", "Android/Pixel UI"),
        "poco f6": ("Qualcomm Snapdragon 8s Gen 3", "8GB/12GB", "256GB/512GB", "6.67-inch AMOLED 120Hz", "5000mAh", "90W", "50MP main + 8MP ultrawide", "Android/HyperOS"),
        "samsung galaxy a56 5g": ("Samsung Exynos 1580", "8GB/12GB", "128GB/256GB", "6.7-inch Super AMOLED 120Hz", "5000mAh", "45W", "50MP main + 12MP ultrawide + 5MP macro", "Android/One UI"),
        "iphone 13": ("Apple A15 Bionic", "4GB", "128GB/256GB/512GB", "6.1-inch Super Retina XDR OLED 60Hz", "3240mAh class", "20W wired + MagSafe", "12MP main + 12MP ultrawide", "iOS"),
        "poco x7 pro": ("MediaTek Dimensity 8400-Ultra", "8GB/12GB", "256GB/512GB", "6.67-inch AMOLED 120Hz", "6000mAh", "90W", "50MP main + 8MP ultrawide", "Android/HyperOS"),
        "xiaomi 14t": ("MediaTek Dimensity 8300-Ultra", "12GB", "256GB/512GB", "6.67-inch AMOLED 144Hz", "5000mAh", "67W", "50MP main + 50MP telephoto + 12MP ultrawide", "Android/HyperOS"),
        "oneplus 12r": ("Qualcomm Snapdragon 8 Gen 2", "8GB/16GB", "128GB/256GB", "6.78-inch LTPO AMOLED 120Hz", "5500mAh", "100W", "50MP main + 8MP ultrawide + 2MP macro", "Android/OxygenOS"),
        "samsung galaxy s24 fe": ("Samsung Exynos 2400e", "8GB", "128GB/256GB", "6.7-inch Dynamic AMOLED 2X 120Hz", "4700mAh", "25W wired + wireless", "50MP main + 8MP telephoto + 12MP ultrawide", "Android/One UI"),
        "iphone 15": ("Apple A16 Bionic", "6GB", "128GB/256GB/512GB", "6.1-inch Super Retina XDR OLED 60Hz", "3349mAh class", "20W wired + MagSafe", "48MP main + 12MP ultrawide", "iOS"),
        "xiaomi 14": ("Qualcomm Snapdragon 8 Gen 3", "12GB/16GB", "256GB/512GB", "6.36-inch LTPO OLED 120Hz", "4610mAh", "90W wired + 50W wireless", "50MP main + 50MP telephoto + 50MP ultrawide", "Android/HyperOS"),
        "iphone 16": ("Apple A18", "8GB", "128GB/256GB/512GB", "6.1-inch Super Retina XDR OLED 60Hz", "3561mAh class", "20W wired + MagSafe", "48MP main + 12MP ultrawide", "iOS"),
        "samsung galaxy s24": ("Qualcomm Snapdragon 8 Gen 3 / Exynos 2400 tùy thị trường", "8GB", "128GB/256GB", "6.2-inch Dynamic AMOLED 2X 120Hz", "4000mAh", "25W wired + wireless", "50MP main + 10MP telephoto + 12MP ultrawide", "Android/One UI"),
        "xiaomi 15": ("Qualcomm Snapdragon 8 Elite", "12GB/16GB", "256GB/512GB/1TB", "6.36-inch LTPO OLED 120Hz", "5400mAh", "90W wired + 50W wireless", "50MP main + 50MP telephoto + 50MP ultrawide", "Android/HyperOS"),
        "oppo find x8": ("MediaTek Dimensity 9400", "12GB/16GB", "256GB/512GB/1TB", "6.59-inch LTPO AMOLED 120Hz", "5630mAh", "80W wired + 50W wireless", "50MP main + 50MP periscope + 50MP ultrawide", "Android/ColorOS"),
        "samsung galaxy z flip6": ("Qualcomm Snapdragon 8 Gen 3 for Galaxy", "12GB", "256GB/512GB", "6.7-inch Foldable Dynamic AMOLED 2X 120Hz + 3.4-inch cover", "4000mAh", "25W wired + wireless", "50MP main + 12MP ultrawide", "Android/One UI"),
        "iphone 16 plus": ("Apple A18", "8GB", "128GB/256GB/512GB", "6.7-inch Super Retina XDR OLED 60Hz", "4674mAh class", "20W wired + MagSafe", "48MP main + 12MP ultrawide", "iOS"),
        "samsung galaxy s25": ("Qualcomm Snapdragon 8 Elite for Galaxy", "12GB", "128GB/256GB/512GB", "6.2-inch Dynamic AMOLED 2X 120Hz", "4000mAh", "25W wired + wireless", "50MP main + 10MP telephoto + 12MP ultrawide", "Android/One UI"),
        "vivo x100 pro": ("MediaTek Dimensity 9300", "12GB/16GB", "256GB/512GB/1TB", "6.78-inch LTPO AMOLED 120Hz", "5400mAh", "100W wired + 50W wireless", "50MP main + 50MP periscope + 50MP ultrawide", "Android/Funtouch OS"),
        "iphone 15 pro max": ("Apple A17 Pro", "8GB", "256GB/512GB/1TB", "6.7-inch Super Retina XDR OLED ProMotion 120Hz", "4441mAh class", "20W wired + MagSafe", "48MP main + 12MP 5x telephoto + 12MP ultrawide", "iOS"),
        "samsung galaxy s25 plus": ("Qualcomm Snapdragon 8 Elite for Galaxy", "12GB", "256GB/512GB", "6.7-inch QHD+ Dynamic AMOLED 2X 120Hz", "4900mAh", "45W wired + wireless", "50MP main + 10MP telephoto + 12MP ultrawide", "Android/One UI"),
        "iphone 16 pro": ("Apple A18 Pro", "8GB", "128GB/256GB/512GB/1TB", "6.3-inch Super Retina XDR OLED ProMotion 120Hz", "3582mAh class", "20W wired + MagSafe", "48MP main + 12MP 5x telephoto + 48MP ultrawide", "iOS"),
        "samsung galaxy s24 ultra": ("Qualcomm Snapdragon 8 Gen 3 for Galaxy", "12GB", "256GB/512GB/1TB", "6.8-inch QHD+ Dynamic AMOLED 2X 120Hz", "5000mAh", "45W wired + wireless", "200MP main + 50MP 5x telephoto + 10MP 3x telephoto + 12MP ultrawide", "Android/One UI"),
        "samsung galaxy s25 ultra": ("Qualcomm Snapdragon 8 Elite for Galaxy", "12GB", "256GB/512GB/1TB", "6.9-inch QHD+ Dynamic AMOLED 2X 120Hz", "5000mAh", "45W wired + wireless", "200MP main + 50MP 5x telephoto + 10MP 3x telephoto + 50MP ultrawide", "Android/One UI"),
        "iphone 16 pro max": ("Apple A18 Pro", "8GB", "256GB/512GB/1TB", "6.9-inch Super Retina XDR OLED ProMotion 120Hz", "4685mAh class", "20W wired + MagSafe", "48MP main + 12MP 5x telephoto + 48MP ultrawide", "iOS"),
        "samsung galaxy z fold6": ("Qualcomm Snapdragon 8 Gen 3 for Galaxy", "12GB", "256GB/512GB/1TB", "7.6-inch foldable Dynamic AMOLED 2X 120Hz + 6.3-inch cover", "4400mAh", "25W wired + wireless", "50MP main + 10MP telephoto + 12MP ultrawide", "Android/One UI"),
        "redmagic 10 pro": ("Qualcomm Snapdragon 8 Elite", "12GB/16GB/24GB", "256GB/512GB/1TB", "6.85-inch AMOLED 144Hz", "7050mAh", "80W/100W tùy thị trường", "50MP main + 50MP ultrawide", "Android/RedMagic OS"),
        "redmagic 11 pro": ("Qualcomm Snapdragon 8 Elite/Elite Gen 5 class", "12GB/16GB/24GB", "256GB/512GB/1TB", "6.85-inch AMOLED 144Hz", "7000mAh+ class", "80W/100W tùy thị trường", "50MP main + ultrawide", "Android/RedMagic OS"),
        "asus rog phone 9": ("Qualcomm Snapdragon 8 Elite", "12GB/16GB", "256GB/512GB", "6.78-inch LTPO AMOLED up to 185Hz", "5800mAh", "65W wired + wireless", "50MP main + 13MP ultrawide + 5MP macro", "Android/ROG UI"),
        "asus rog phone 9 pro": ("Qualcomm Snapdragon 8 Elite", "16GB/24GB", "512GB/1TB", "6.78-inch LTPO AMOLED up to 185Hz", "5800mAh", "65W wired + wireless", "50MP main + 32MP telephoto + 13MP ultrawide", "Android/ROG UI"),
        "iqoo 13": ("Qualcomm Snapdragon 8 Elite", "12GB/16GB", "256GB/512GB/1TB", "6.82-inch LTPO AMOLED 144Hz", "6150mAh", "120W", "50MP main + 50MP telephoto + 50MP ultrawide", "Android/Funtouch OS"),
        "iqoo 15": ("Qualcomm Snapdragon 8 Elite Gen 5 class", "12GB/16GB", "256GB/512GB/1TB", "6.8-inch LTPO AMOLED 144Hz class", "6000mAh+ class", "100W+ class", "50MP class triple camera", "Android/Funtouch OS"),
        "oneplus 13": ("Qualcomm Snapdragon 8 Elite", "12GB/16GB/24GB", "256GB/512GB/1TB", "6.82-inch QHD+ LTPO AMOLED 120Hz", "6000mAh", "100W wired + 50W wireless", "50MP main + 50MP periscope + 50MP ultrawide", "Android/OxygenOS"),
        "oneplus 15": ("Qualcomm Snapdragon 8 Elite Gen 5 class", "12GB/16GB", "256GB/512GB/1TB", "6.8-inch LTPO AMOLED 120Hz class", "6000mAh+ class", "100W class", "50MP class triple camera", "Android/OxygenOS"),
        "realme gt 7 pro": ("Qualcomm Snapdragon 8 Elite", "12GB/16GB", "256GB/512GB/1TB", "6.78-inch LTPO OLED 120Hz", "6500mAh", "120W", "50MP main + 50MP periscope + 8MP ultrawide", "Android/realme UI"),
        "xiaomi 15 pro": ("Qualcomm Snapdragon 8 Elite", "12GB/16GB", "256GB/512GB/1TB", "6.73-inch 2K LTPO OLED 120Hz", "6100mAh", "90W wired + 50W wireless", "50MP main + 50MP periscope + 50MP ultrawide", "Android/HyperOS"),
        "honor magic7 pro": ("Qualcomm Snapdragon 8 Elite", "12GB/16GB", "256GB/512GB/1TB", "6.8-inch LTPO OLED 120Hz", "5850mAh", "100W wired + 80W wireless", "50MP main + 200MP periscope + 50MP ultrawide", "Android/MagicOS"),
        "google pixel 9 pro": ("Google Tensor G4", "16GB", "128GB/256GB/512GB/1TB", "6.3-inch LTPO OLED 120Hz", "4700mAh class", "27W wired + wireless", "50MP main + 48MP telephoto + 48MP ultrawide", "Android/Pixel UI"),
    }
    values = exact.get(n)
    if not values:
        values = ("Chipset cần kiểm tra theo SKU", "8GB", "128GB/256GB", "AMOLED/LCD 90-120Hz tùy phiên bản", "5000mAh class", "25W+ class", "camera chính 50MP class", "Android/iOS tùy máy")
    chipset, ram, storage, display, battery, charging, camera, os_name = values
    return {
        "variant_name": f"{name} - biến thể tham chiếu catalog",
        "chipset": chipset,
        "ram": ram,
        "storage": storage,
        "display": display,
        "battery": battery,
        "charging": charging,
        "camera": camera,
        "os": os_name,
        "spec_confidence": "reference_variant",
        "variant_note": "Thông số là biến thể tham chiếu trong catalog; khi mua cần kiểm tra đúng SKU/RAM/bộ nhớ và thị trường bán ra.",
    }


def laptop_specs(name: str) -> dict:
    n = norm(name)
    exact = {
        "asus vivobook go 15": ("AMD Ryzen 5 7520U", "AMD Radeon 610M", "8GB/16GB LPDDR5", "512GB NVMe SSD", "15.6-inch FHD IPS/OLED tùy SKU", "42Wh class", "khoảng 1.6-1.7kg", "Windows 11"),
        "hp 15s": ("Intel Core i5-1334U / AMD Ryzen 5 7530U tùy SKU", "Intel Iris Xe / AMD Radeon iGPU", "8GB/16GB DDR4/DDR5", "512GB NVMe SSD", "15.6-inch FHD IPS", "41Wh class", "khoảng 1.6-1.7kg", "Windows 11"),
        "acer aspire lite 15": ("Intel Core i5-1235U / Ryzen 5 5500U tùy SKU", "Intel Iris Xe / AMD Radeon iGPU", "8GB/16GB", "512GB NVMe SSD", "15.6-inch FHD IPS", "36-50Wh class", "khoảng 1.6-1.8kg", "Windows 11"),
        "lenovo v14": ("Intel Core i5-13420H / Ryzen 5 7520U tùy SKU", "Intel UHD/Iris Xe / AMD Radeon iGPU", "8GB/16GB", "512GB NVMe SSD", "14-inch FHD IPS", "38Wh class", "khoảng 1.4-1.5kg", "Windows 11"),
        "lenovo ideapad slim 3": ("AMD Ryzen 5 7530U / Intel Core i5-13420H tùy SKU", "AMD Radeon / Intel UHD", "8GB/16GB", "512GB NVMe SSD", "15.6-inch FHD IPS", "47Wh class", "khoảng 1.6-1.7kg", "Windows 11"),
        "dell inspiron 15": ("Intel Core i5-1334U / Core 5 120U tùy SKU", "Intel Iris Xe / Intel Graphics", "8GB/16GB DDR4/DDR5", "512GB NVMe SSD", "15.6-inch FHD 120Hz/IPS tùy SKU", "41Wh class", "khoảng 1.6kg", "Windows 11"),
        "acer aspire 7": ("AMD Ryzen 5 5500U / Intel Core i5 H-series tùy SKU", "NVIDIA GeForce GTX 1650 / RTX 2050 tùy SKU", "8GB/16GB", "512GB NVMe SSD", "15.6-inch FHD IPS 144Hz tùy SKU", "48Wh class", "khoảng 2.1kg", "Windows 11"),
        "lenovo thinkbook 14 g6": ("Intel Core i5-1335U / AMD Ryzen 5 7530U tùy SKU", "Intel Iris Xe / AMD Radeon iGPU", "16GB DDR5", "512GB NVMe SSD", "14-inch WUXGA IPS", "45Wh/60Wh tùy SKU", "khoảng 1.4kg", "Windows 11"),
        "hp victus 15": ("Intel Core i5-13420H / AMD Ryzen 5 7535HS tùy SKU", "NVIDIA GeForce RTX 3050 6GB / RTX 4050 6GB tùy SKU", "16GB DDR4/DDR5", "512GB NVMe SSD", "15.6-inch FHD 144Hz", "52.5Wh class", "khoảng 2.3kg", "Windows 11"),
        "asus tuf gaming a15": ("AMD Ryzen 7 7735HS", "NVIDIA GeForce RTX 4050 Laptop GPU 6GB", "16GB DDR5", "512GB/1TB NVMe SSD", "15.6-inch FHD 144Hz", "90Wh class", "khoảng 2.2kg", "Windows 11"),
        "asus vivobook 16x rtx 4050": ("Intel Core i5-13500H / Core i7-13700H tùy SKU", "NVIDIA GeForce RTX 4050 Laptop GPU 6GB", "16GB DDR4/DDR5", "512GB/1TB NVMe SSD", "16-inch WUXGA/3.2K OLED tùy SKU", "50-70Wh class", "khoảng 1.8-2.0kg", "Windows 11"),
        "acer swift go 14 oled": ("Intel Core Ultra 5 125H / Ultra 7 155H tùy SKU", "Intel Arc integrated graphics", "16GB LPDDR5X", "512GB/1TB NVMe SSD", "14-inch 2.8K OLED 90Hz", "65Wh class", "khoảng 1.3kg", "Windows 11"),
        "msi thin 15 rtx 4050": ("Intel Core i5-13420H", "NVIDIA GeForce RTX 4050 Laptop GPU 6GB", "16GB DDR4/DDR5", "512GB NVMe SSD", "15.6-inch FHD 144Hz", "52.4Wh class", "khoảng 1.86kg", "Windows 11"),
        "acer nitro v 15 rtx 4050": ("Intel Core i5-13420H / Core i7-13620H tùy SKU", "NVIDIA GeForce RTX 4050 Laptop GPU 6GB", "16GB DDR5", "512GB NVMe SSD", "15.6-inch FHD 144Hz", "57Wh class", "khoảng 2.1kg", "Windows 11"),
        "lenovo loq 15 rtx 4050": ("Intel Core i5-13450HX / AMD Ryzen 5 7640HS tùy SKU", "NVIDIA GeForce RTX 4050 Laptop GPU 6GB", "16GB DDR5", "512GB NVMe SSD", "15.6-inch FHD 144Hz", "60Wh class", "khoảng 2.4kg", "Windows 11"),
        "macbook air m2 13": ("Apple M2 8-core CPU", "Apple M2 8-core/10-core GPU", "8GB/16GB unified memory", "256GB/512GB SSD", "13.6-inch Liquid Retina", "52.6Wh class", "1.24kg", "macOS"),
        "lenovo ideapad pro 5": ("AMD Ryzen 7 8845HS / Intel Core Ultra 5 tùy SKU", "AMD Radeon 780M / Intel Arc iGPU", "16GB/32GB LPDDR5X", "512GB/1TB NVMe SSD", "14/16-inch 2.8K OLED/IPS 120Hz tùy SKU", "75Wh class", "khoảng 1.5-1.9kg", "Windows 11"),
        "asus zenbook 14 oled": ("Intel Core Ultra 7 155H", "Intel Arc integrated graphics", "16GB LPDDR5X", "1TB NVMe SSD", "14-inch 3K OLED 120Hz", "75Wh class", "khoảng 1.2kg", "Windows 11"),
        "macbook air m3 13": ("Apple M3 8-core CPU", "Apple M3 8-core/10-core GPU", "8GB/16GB/24GB unified memory", "256GB/512GB/1TB SSD", "13.6-inch Liquid Retina", "52.6Wh class", "1.24kg", "macOS"),
        "gigabyte g5 rtx 4060": ("Intel Core i5-12500H / Core i7-13620H tùy SKU", "NVIDIA GeForce RTX 4060 Laptop GPU 8GB", "16GB DDR4/DDR5", "512GB NVMe SSD", "15.6-inch FHD 144Hz", "54Wh class", "khoảng 2.0kg", "Windows 11"),
        "hp omen 16 rtx 4060": ("Intel Core i7-13620H / Ryzen 7 7840HS tùy SKU", "NVIDIA GeForce RTX 4060 Laptop GPU 8GB", "16GB DDR5", "1TB NVMe SSD", "16.1-inch FHD/QHD 165Hz tùy SKU", "83Wh class", "khoảng 2.3kg", "Windows 11"),
        "lenovo loq 15 rtx 4060": ("Intel Core i5-13450HX / Core i7-13650HX tùy SKU", "NVIDIA GeForce RTX 4060 Laptop GPU 8GB", "16GB DDR5", "512GB/1TB NVMe SSD", "15.6-inch FHD 144Hz", "60Wh class", "khoảng 2.4kg", "Windows 11"),
        "macbook air m4 13": ("Apple M4 10-core CPU", "Apple M4 8-core/10-core GPU", "16GB/24GB/32GB unified memory", "256GB/512GB/1TB SSD", "13.6-inch Liquid Retina", "53.8Wh class", "1.24kg", "macOS"),
        "asus tuf gaming f15 rtx 4060": ("Intel Core i7-13620H", "NVIDIA GeForce RTX 4060 Laptop GPU 8GB", "16GB DDR5", "512GB/1TB NVMe SSD", "15.6-inch FHD 144Hz/165Hz", "90Wh class", "khoảng 2.2kg", "Windows 11"),
        "macbook air m3 15": ("Apple M3 8-core CPU", "Apple M3 10-core GPU", "8GB/16GB/24GB unified memory", "256GB/512GB/1TB SSD", "15.3-inch Liquid Retina", "66.5Wh class", "1.51kg", "macOS"),
        "acer predator helios neo 16 rtx 4060": ("Intel Core i7-14650HX", "NVIDIA GeForce RTX 4060 Laptop GPU 8GB", "16GB DDR5", "1TB NVMe SSD", "16-inch WQXGA 165Hz", "90Wh class", "khoảng 2.6kg", "Windows 11"),
        "asus rog zephyrus g14": ("AMD Ryzen 9 8945HS", "NVIDIA GeForce RTX 4060/4070 Laptop GPU 8GB tùy SKU", "16GB/32GB LPDDR5X", "1TB NVMe SSD", "14-inch 3K OLED 120Hz", "73Wh class", "khoảng 1.5kg", "Windows 11"),
        "dell xps 13": ("Intel Core Ultra 7 155H / Snapdragon X Elite tùy SKU", "Intel Arc / Qualcomm Adreno iGPU", "16GB/32GB LPDDR5X", "512GB/1TB NVMe SSD", "13.4-inch FHD+/OLED tùy SKU", "55Wh class", "khoảng 1.2kg", "Windows 11"),
        "lg gram 16": ("Intel Core Ultra 7 155H", "Intel Arc integrated graphics", "16GB/32GB LPDDR5X", "1TB NVMe SSD", "16-inch WQXGA IPS/OLED tùy SKU", "77Wh class", "khoảng 1.2kg", "Windows 11"),
        "macbook pro m3 14": ("Apple M3 8-core CPU", "Apple M3 10-core GPU", "8GB/16GB/24GB unified memory", "512GB/1TB SSD", "14.2-inch Liquid Retina XDR 120Hz", "70Wh class", "1.55kg", "macOS"),
        "lenovo thinkpad x1 carbon": ("Intel Core Ultra 7 155U/155H tùy SKU", "Intel Arc / Intel Graphics", "16GB/32GB LPDDR5X", "512GB/1TB NVMe SSD", "14-inch WUXGA/2.8K OLED tùy SKU", "57Wh class", "khoảng 1.1kg", "Windows 11"),
        "macbook pro m4 14": ("Apple M4 10-core CPU", "Apple M4 10-core GPU", "16GB/24GB/32GB unified memory", "512GB/1TB SSD", "14.2-inch Liquid Retina XDR 120Hz", "72.4Wh class", "1.55kg", "macOS"),
        "lenovo legion pro 5 rtx 4070": ("Intel Core i7-14650HX / Core i9-14900HX tùy SKU", "NVIDIA GeForce RTX 4070 Laptop GPU 8GB GDDR6, TGP up to 140W", "16GB/32GB DDR5", "1TB NVMe SSD", "16-inch WQXGA 2560x1600 165Hz/240Hz", "80Wh class", "khoảng 2.5kg", "Windows 11"),
        "asus rog strix g16 rtx 4070": ("Intel Core i9-14900HX", "NVIDIA GeForce RTX 4070 Laptop GPU 8GB GDDR6", "16GB/32GB DDR5", "1TB NVMe SSD", "16-inch QHD+ 240Hz / FHD+ 165Hz tùy SKU", "90Wh class", "khoảng 2.5kg", "Windows 11"),
        "dell xps 16": ("Intel Core Ultra 7 155H / Ultra 9 185H tùy SKU", "NVIDIA GeForce RTX 4050/4060 Laptop GPU tùy SKU", "16GB/32GB/64GB LPDDR5X", "512GB/1TB/2TB NVMe SSD", "16.3-inch FHD+/4K OLED tùy SKU", "99.5Wh class", "khoảng 2.1-2.2kg", "Windows 11"),
        "macbook pro m4 pro 16": ("Apple M4 Pro 14-core CPU", "Apple M4 Pro 20-core GPU", "24GB/48GB unified memory", "512GB/1TB/2TB SSD", "16.2-inch Liquid Retina XDR 120Hz", "100Wh class", "2.14kg", "macOS"),
        "lenovo legion pro 7 rtx 4080": ("Intel Core i9-14900HX", "NVIDIA GeForce RTX 4080 Laptop GPU 12GB GDDR6, TGP up to 175W", "32GB DDR5", "1TB/2TB NVMe SSD", "16-inch WQXGA 2560x1600 240Hz", "99.9Wh class", "khoảng 2.6kg", "Windows 11"),
        "razer blade 16 rtx 4080": ("Intel Core i9-14900HX", "NVIDIA GeForce RTX 4080 Laptop GPU 12GB GDDR6", "32GB DDR5-5600", "1TB NVMe SSD", "16-inch QHD+ OLED 240Hz / dual-mode mini-LED tùy SKU", "95.2Wh class", "khoảng 2.45kg", "Windows 11"),
        "msi raider 18 rtx 5090": ("Intel Core Ultra 9 285HX", "NVIDIA GeForce RTX 5090 Laptop GPU 24GB GDDR7", "64GB DDR5", "2TB NVMe SSD", "18-inch UHD+/Mini LED 120Hz hoặc QHD+ 240Hz tùy SKU", "99.9Wh class", "khoảng 3.6kg", "Windows 11"),
        "lenovo loq 15 rtx 4060 2025": ("Intel Core i7-13650HX / Core i7-14650HX tùy SKU", "NVIDIA GeForce RTX 4060 Laptop GPU 8GB GDDR6", "16GB DDR5", "512GB/1TB NVMe SSD", "15.6-inch FHD 144Hz", "60Wh class", "khoảng 2.4kg", "Windows 11"),
        "hp victus 16 rtx 4060": ("Intel Core i7-13700H / Ryzen 7 7840HS tùy SKU", "NVIDIA GeForce RTX 4060 Laptop GPU 8GB GDDR6", "16GB DDR5", "512GB/1TB NVMe SSD", "16.1-inch FHD/QHD 144-165Hz", "70Wh/83Wh tùy SKU", "khoảng 2.3kg", "Windows 11"),
        "dell g15 rtx 4060": ("Intel Core i7-13650HX / Core i7-14650HX tùy SKU", "NVIDIA GeForce RTX 4060 Laptop GPU 8GB GDDR6", "16GB DDR5", "512GB/1TB NVMe SSD", "15.6-inch FHD 165Hz", "86Wh class", "khoảng 2.6kg", "Windows 11"),
        "asus tuf a14 rtx 4060": ("AMD Ryzen AI 9 HX 370 / Ryzen 7 class tùy SKU", "NVIDIA GeForce RTX 4060 Laptop GPU 8GB GDDR6", "16GB/32GB LPDDR5X", "1TB NVMe SSD", "14-inch 2.5K IPS 165Hz", "73Wh class", "khoảng 1.46kg", "Windows 11"),
        "lenovo legion 5 rtx 4070": ("AMD Ryzen 7 8845HS / Intel Core i7 tùy SKU", "NVIDIA GeForce RTX 4070 Laptop GPU 8GB GDDR6", "16GB/32GB DDR5", "1TB NVMe SSD", "16-inch WQXGA 165Hz", "80Wh class", "khoảng 2.3-2.5kg", "Windows 11"),
        "asus rog strix g16 rtx 4060": ("Intel Core i7-13650HX / Core i9-14900HX tùy SKU", "NVIDIA GeForce RTX 4060 Laptop GPU 8GB GDDR6", "16GB DDR5", "1TB NVMe SSD", "16-inch FHD+ 165Hz / QHD+ 240Hz tùy SKU", "90Wh class", "khoảng 2.5kg", "Windows 11"),
        "acer predator helios neo 16 rtx 4070": ("Intel Core i7-14650HX", "NVIDIA GeForce RTX 4070 Laptop GPU 8GB GDDR6", "16GB/32GB DDR5", "1TB NVMe SSD", "16-inch WQXGA 165Hz", "90Wh class", "khoảng 2.6kg", "Windows 11"),
        "asus zenbook 14 oled 2025": ("Intel Core Ultra 7 258V / Ultra 7 155H tùy SKU", "Intel Arc integrated graphics", "16GB/32GB LPDDR5X", "1TB NVMe SSD", "14-inch 3K OLED 120Hz", "75Wh class", "khoảng 1.2kg", "Windows 11"),
        "lenovo yoga slim 7": ("AMD Ryzen 7 8845HS / Intel Core Ultra 7 tùy SKU", "AMD Radeon 780M / Intel Arc iGPU", "16GB/32GB LPDDR5X", "1TB NVMe SSD", "14-inch OLED/IPS 2.8K 120Hz tùy SKU", "65Wh/70Wh class", "khoảng 1.3-1.5kg", "Windows 11"),
        "hp omnibook ultra 14": ("AMD Ryzen AI 9 HX 375", "AMD Radeon 890M integrated graphics", "16GB/32GB LPDDR5X", "1TB NVMe SSD", "14-inch 2.2K IPS/OLED tùy SKU", "68Wh class", "khoảng 1.35kg", "Windows 11"),
        "dell xps 14": ("Intel Core Ultra 7 155H", "Intel Arc / NVIDIA GeForce RTX 4050 Laptop GPU tùy SKU", "16GB/32GB LPDDR5X", "512GB/1TB NVMe SSD", "14.5-inch FHD+/3.2K OLED 120Hz tùy SKU", "69.5Wh class", "khoảng 1.7-1.8kg", "Windows 11"),
    }
    values = exact.get(n)
    if not values:
        values = ("CPU cần kiểm tra theo SKU", "GPU cần kiểm tra theo SKU", "16GB", "512GB/1TB NVMe SSD", "màn hình FHD/2K tùy SKU", "pin tùy SKU", "cân nặng tùy SKU", "Windows/macOS tùy máy")
    cpu, gpu, ram, storage, display, battery, weight, os_name = values
    return {
        "variant_name": f"{name} - biến thể tham chiếu catalog",
        "cpu": cpu,
        "gpu": gpu,
        "ram": ram,
        "storage": storage,
        "display": display,
        "battery": battery,
        "weight": weight,
        "os": os_name,
        "spec_confidence": "reference_variant",
        "variant_note": "Thông số là biến thể tham chiếu trong catalog; laptop thường có nhiều SKU nên cần kiểm tra đúng CPU/GPU/RAM/SSD/màn hình trước khi mua.",
    }


def update_profiles(item: dict, snapshot: dict) -> None:
    category = item.get("category")
    item["spec_snapshot"] = snapshot
    item["data_confidence"] = "reference_variant"
    item["last_updated"] = "2026-06"

    if category == "phone":
        item["specs"] = {
            "chipset": snapshot["chipset"],
            "ram_storage": f"{snapshot['ram']}; {snapshot['storage']}",
            "screen": snapshot["display"],
            "battery": f"{snapshot['battery']}; sạc {snapshot['charging']}",
            "camera": snapshot["camera"],
            "software": snapshot["os"],
        }
        config = {
            "chipset_tier": snapshot["chipset"],
            "ram_storage": f"RAM {snapshot['ram']}, bộ nhớ {snapshot['storage']}",
            "display": snapshot["display"],
            "battery_charging": f"{snapshot['battery']}, sạc {snapshot['charging']}",
            "camera": snapshot["camera"],
            "software": snapshot["os"],
        }
        comparison = {
            "performance": snapshot["chipset"],
            "gaming": f"{snapshot['chipset']}; RAM {snapshot['ram']}",
            "display": snapshot["display"],
            "battery": f"{snapshot['battery']}; {snapshot['charging']}",
            "camera": snapshot["camera"],
            "software": snapshot["os"],
            "value": "so sánh theo giá thực tế, RAM/bộ nhớ và bảo hành của đúng phiên bản",
        }
    else:
        item["specs"] = {
            "cpu": snapshot["cpu"],
            "gpu": snapshot["gpu"],
            "ram": snapshot["ram"],
            "storage": snapshot["storage"],
            "screen": snapshot["display"],
            "portability": snapshot["weight"],
            "battery": snapshot["battery"],
        }
        config = {
            "cpu_class": snapshot["cpu"],
            "gpu_class": snapshot["gpu"],
            "ram": snapshot["ram"],
            "storage": snapshot["storage"],
            "display": snapshot["display"],
            "thermal": "cần xem review đúng SKU về nhiệt độ, độ ồn và TGP GPU nếu là laptop gaming",
            "portability": snapshot["weight"],
            "battery": snapshot["battery"],
            "upgrade_notes": "kiểm tra RAM hàn/nâng cấp được, số khe SSD và điều kiện bảo hành khi nâng cấp",
        }
        comparison = {
            "cpu": snapshot["cpu"],
            "gpu": snapshot["gpu"],
            "ram_storage": f"RAM {snapshot['ram']}; SSD {snapshot['storage']}",
            "display": snapshot["display"],
            "thermal": "so sánh thêm TGP GPU, nhiệt độ và độ ồn theo review đúng SKU",
            "portability_battery": f"{snapshot['weight']}; pin {snapshot['battery']}",
            "upgrade": "kiểm tra RAM hàn/nâng cấp được và số khe SSD",
            "value": "so sánh theo đúng CPU/GPU/RAM/SSD/màn hình của biến thể bán ra",
        }

    detail = item.setdefault("detail_profile", {})
    if isinstance(detail, dict):
        detail["configuration"] = config
    item["comparison_profile"] = comparison


def main() -> None:
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    for item in data:
        if item.get("category") == "phone":
            snapshot = phone_specs(item.get("name", ""))
        else:
            snapshot = laptop_specs(item.get("name", ""))
        update_profiles(item, snapshot)
    CATALOG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Updated {len(data)} products with exact spec snapshots.")


if __name__ == "__main__":
    main()
