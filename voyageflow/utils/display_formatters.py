from __future__ import annotations

import re
from typing import Any, Dict

PURPOSE_JA = {
    "activity": "観光・見学",
    "meal": "食事",
    "transport": "移動",
    "arrival": "到着",
    "departure": "出発",
    "station": "駅",
    "hotel": "宿泊",
    "stay": "滞在",
    "rest": "休憩",
    "shopping": "買い物",
    "return": "帰路",
}

GENRE_JA = {
    "museum": "博物館",
    "art_gallery": "美術館",
    "gallery": "美術館",
    "station": "駅",
    "park": "公園",
    "garden": "庭園",
    "temple": "寺社",
    "shrine": "寺社",
    "shopping": "買い物",
    "mall": "商業施設",
    "restaurant": "レストラン",
    "cafe": "カフェ",
    "hotel": "ホテル",
    "lodging": "ホテル",
    "general": "一般",
    "transit": "移動",
    "indoor_alt": "屋内代替",
    "return": "帰路",
}

OUTDOOR_GENRES = {
    "park", "garden", "temple", "shrine", "outdoor", "street", "beach", "zoo", "nature",
}
OUTDOOR_KEYWORDS = ["公園", "庭園", "神社", "寺", "外苑", "展望", "海岸", "散策", "ストリート", "屋外"]


def safe_text(value: Any, default: str = "-") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def format_purpose(value: Any) -> str:
    key = safe_text(value, "").lower()
    return PURPOSE_JA.get(key, safe_text(value, "-"))


def format_genre(value: Any) -> str:
    key = safe_text(value, "").lower()
    return GENRE_JA.get(key, safe_text(value, "-"))


def clean_address(address: Any) -> str:
    text = safe_text(address, "")
    if not text or text == "-":
        return ""
    text = text.replace("日本、", "").replace("日本,", "")
    text = re.sub(r"〒\d{3}-?\d{4}\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_outdoor_row(row: Dict[str, Any]) -> bool:
    genre = safe_text(row.get("genre"), "").lower()
    purpose = safe_text(row.get("purpose"), "").lower()
    destination = safe_text(row.get("destination"), "")
    one_point = safe_text(row.get("one_point"), "")
    text = f"{destination} {one_point}"
    if genre in OUTDOOR_GENRES:
        return True
    if purpose in {"walk", "outdoor"}:
        return True
    return any(k in text for k in OUTDOOR_KEYWORDS)


def build_transport_display(row: Dict[str, Any]) -> str:
    route_summary = safe_text(row.get("route_summary"), "")
    if route_summary and route_summary != "-":
        return route_summary
    origin = safe_text(row.get("route_from"), "現在地")
    destination = safe_text(row.get("route_to"), safe_text(row.get("destination"), "次の目的地"))
    mode = format_transport_mode(row.get("transport_mode"))
    duration = int(row.get("duration_minutes", 0) or 0)
    return f"{origin}→{destination}：{mode} {duration}分"


def format_transport_mode(mode: Any) -> str:
    return {
        "walk": "徒歩",
        "train": "電車",
        "taxi": "タクシー",
        "car": "自家用車",
        "private_car": "自家用車",
        "rental_car": "レンタカー",
        "bike": "自転車",
    }.get(safe_text(mode, "").lower(), safe_text(mode, "-"))
