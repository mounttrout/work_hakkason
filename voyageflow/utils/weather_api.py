from __future__ import annotations

"""Open-Meteo ベースの天候メモ生成。

- 7日以内: 実予報 API
- 8日以降: 16日予報が取れればその日を利用
- それ以降: 気候傾向 API と月別フォールバックを併用

出力形式は既存 build_mock_weather_context と互換に寄せる。
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple
import requests

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


_AREA_PATTERNS = [
    ("hokkaido", ["北海道", "札幌", "函館", "小樽", "旭川", "富良野"]),
    ("tohoku", ["青森", "岩手", "宮城", "秋田", "山形", "福島", "仙台"]),
    ("hokuriku", ["福井", "石川", "富山", "金沢", "富山駅", "福井駅", "北陸"]),
    ("tokyo", ["東京", "新宿", "渋谷", "浅草", "上野", "秋葉原", "銀座", "東京駅", "羽田"]),
    ("kanto", ["神奈川", "横浜", "鎌倉", "千葉", "埼玉", "箱根", "成田"]),
    ("chubu", ["長野", "岐阜", "静岡", "名古屋", "愛知", "山梨"]),
    ("kansai", ["大阪", "京都", "奈良", "兵庫", "神戸", "滋賀", "和歌山", "関西"]),
    ("chugoku", ["広島", "岡山", "山口", "鳥取", "島根"]),
    ("shikoku", ["香川", "愛媛", "高知", "徳島"]),
    ("kyushu", ["福岡", "熊本", "大分", "長崎", "佐賀", "宮崎", "鹿児島", "博多"]),
    ("okinawa", ["沖縄", "那覇", "石垣", "宮古"]),
]

_MONTHLY_LIBRARY: Dict[int, Dict[str, str]] = {
    1: {"summary": "寒さが厳しく、朝晩の冷え込み対策が重要です。", "packing": "防寒着、手袋、保温インナーがあると安心です。"},
    2: {"summary": "冬の寒さが続き、風で体感温度が下がりやすい時期です。", "packing": "厚手の上着と防寒小物がおすすめです。"},
    3: {"summary": "寒暖差が大きく、雨の日は体感がぐっと下がりやすい時期です。", "packing": "羽織ものと折りたたみ傘があると安心です。"},
    4: {"summary": "春らしく動きやすい一方、日によって気温差が出やすい時期です。", "packing": "薄手の上着と歩きやすい靴がおすすめです。"},
    5: {"summary": "比較的安定して観光しやすい時期ですが、日差しが強まります。", "packing": "羽織ものと日差し対策が便利です。"},
    6: {"summary": "梅雨を意識した雨対策が必要な時期です。", "packing": "折りたたみ傘、防水の靴、薄手の替えを用意すると安心です。"},
    7: {"summary": "蒸し暑くなりやすく、屋外は熱中症対策が重要です。", "packing": "通気性のよい服、飲み物、日差し対策がおすすめです。"},
    8: {"summary": "真夏日や強い日差しを想定した準備が必要です。", "packing": "帽子、飲み物、汗対策グッズがあると安心です。"},
    9: {"summary": "残暑と急な雨の両方に備えたい時期です。", "packing": "薄手の服装に加え、折りたたみ傘があると便利です。"},
    10: {"summary": "過ごしやすい一方、朝晩は少し冷えやすい時期です。", "packing": "軽い上着を1枚持つのがおすすめです。"},
    11: {"summary": "空気が乾きやすく、朝晩は冷え込みが強まります。", "packing": "上着と乾燥対策を意識すると安心です。"},
    12: {"summary": "冬の気温を意識した防寒が必要な時期です。", "packing": "コートや防寒小物を準備すると安心です。"},
}

_WEATHER_CODE_LABELS = {
    0: "晴れ", 1: "おおむね晴れ", 2: "晴れ時々くもり", 3: "くもり",
    45: "霧", 48: "霧", 51: "弱い霧雨", 53: "霧雨", 55: "強い霧雨",
    61: "弱い雨", 63: "雨", 65: "強い雨", 71: "弱い雪", 73: "雪", 75: "強い雪",
    80: "にわか雨", 81: "にわか雨", 82: "強いにわか雨", 95: "雷雨",
}


@dataclass
class LocationInfo:
    name: str
    latitude: float
    longitude: float
    timezone: str


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        return date.today()


def _detect_area(place: str) -> str:
    text = (place or "").strip()
    for area_key, keywords in _AREA_PATTERNS:
        if any(keyword in text for keyword in keywords):
            return area_key
    return "default"


def _area_label(place: str) -> str:
    text = (place or "").strip()
    return text if text else "未設定"


def _build_gap_advice(departure_area: str, destination_area: str) -> str:
    if departure_area == destination_area:
        return "出発地と到着地で大きな気候差は小さめ想定です。現地の雨具・羽織りを意識する程度で十分です。"
    cool_areas = {"hokkaido", "tohoku", "hokuriku"}
    warm_areas = {"kyushu", "okinawa"}
    if departure_area in cool_areas and destination_area in {"tokyo", "kanto", "kansai", "chugoku", "shikoku", "kyushu", "okinawa"}:
        return "出発地より到着地のほうが暖かく感じやすい想定です。重ね着しやすい服装にすると調整しやすいです。"
    if departure_area in {"tokyo", "kanto", "kansai", "chugoku", "shikoku", "kyushu", "okinawa"} and destination_area in cool_areas:
        return "到着地のほうが肌寒く感じやすい想定です。薄手でも1枚多く羽織れる準備があると安心です。"
    if destination_area in warm_areas:
        return "到着地は湿度や気温を高めに感じる可能性があります。通気性のよい服装がおすすめです。"
    return "地域差による体感差が出る可能性があります。脱ぎ着しやすい服装で調整しやすくしておくと安心です。"


def _build_execution_hint(summary: str, precipitation_like: bool) -> str:
    if precipitation_like:
        return f"実行中は屋外スポットの前に天候確認を挟くと安全です。{summary}"
    return f"実行中は気温差に備えて休憩と水分補給を取りながら進めると安心です。{summary}"


def _safe_get(url: str, params: Dict[str, object], timeout: int = 10) -> Dict[str, object]:
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def geocode_place(place: str) -> Optional[LocationInfo]:
    place = (place or "").strip()
    if not place:
        return None
    data = _safe_get(GEOCODE_URL, {"name": place, "count": 1, "language": "ja", "format": "json"})
    results = data.get("results") or []
    if not results:
        return None
    top = results[0]
    return LocationInfo(
        name=str(top.get("name") or place),
        latitude=float(top["latitude"]),
        longitude=float(top["longitude"]),
        timezone=str(top.get("timezone") or "Asia/Tokyo"),
    )


def _weather_code_to_label(code: Optional[int]) -> str:
    try:
        return _WEATHER_CODE_LABELS.get(int(code), "天候変化あり")
    except Exception:
        return "天候変化あり"


def _packing_from_values(temp_max: Optional[float], temp_min: Optional[float], rain_mm: Optional[float], wind_kmh: Optional[float]) -> str:
    tips: List[str] = []
    try:
        if temp_max is not None and temp_max >= 26:
            tips.append("日差し対策")
        elif temp_max is not None and temp_max <= 12:
            tips.append("防寒着")
        else:
            tips.append("薄手の羽織り")
    except Exception:
        tips.append("薄手の羽織り")
    try:
        if rain_mm is not None and rain_mm >= 1:
            tips.append("折りたたみ傘")
    except Exception:
        pass
    try:
        if wind_kmh is not None and wind_kmh >= 25:
            tips.append("風を防げる上着")
    except Exception:
        pass
    if temp_min is not None and temp_max is not None and (temp_max - temp_min) >= 8:
        tips.append("重ね着しやすい服装")
    return "、".join(dict.fromkeys(tips)) + "がおすすめです。"


def _build_live_forecast_context(location: LocationInfo, target_date: date) -> Dict[str, object]:
    params = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "timezone": location.timezone or "Asia/Tokyo",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max",
        "start_date": target_date.strftime("%Y-%m-%d"),
        "end_date": target_date.strftime("%Y-%m-%d"),
        "forecast_days": 16,
    }
    data = _safe_get(FORECAST_URL, params)
    daily = data.get("daily") or {}
    code = (daily.get("weather_code") or [None])[0]
    temp_max = (daily.get("temperature_2m_max") or [None])[0]
    temp_min = (daily.get("temperature_2m_min") or [None])[0]
    precip = (daily.get("precipitation_sum") or [None])[0]
    precip_prob = (daily.get("precipitation_probability_max") or [None])[0]
    wind = (daily.get("wind_speed_10m_max") or [None])[0]
    label = _weather_code_to_label(code)
    summary = f"{label}の見込みです。"
    if temp_max is not None and temp_min is not None:
        summary += f" 気温は{temp_min:.0f}〜{temp_max:.0f}℃程度を想定しています。"
    detail_lines = []
    if temp_max is not None and temp_min is not None:
        detail_lines.append(f"気温目安: {temp_min:.0f}〜{temp_max:.0f}℃")
    if precip_prob is not None:
        detail_lines.append(f"降水確率の目安: {precip_prob:.0f}%")
    if precip is not None:
        detail_lines.append(f"降水量の目安: {precip:.1f}mm")
    if wind is not None:
        detail_lines.append(f"最大風速の目安: {wind:.0f}km/h")
    return {
        "summary": summary,
        "detail_lines": detail_lines,
        "packing": _packing_from_values(temp_max, temp_min, precip, wind),
        "precipitation_like": bool((precip_prob or 0) >= 40 or (precip or 0) >= 1 or int(code or 0) in {51,53,55,61,63,65,80,81,82,95}),
        "source_mode": "live_forecast",
    }


def _build_climate_fallback_context(target_date: date) -> Dict[str, object]:
    monthly = _MONTHLY_LIBRARY.get(target_date.month, _MONTHLY_LIBRARY[4])
    return {
        "summary": monthly["summary"],
        "detail_lines": [
            f"時期の目安: {target_date.month}月の傾向を基にした簡易アドバイスです。",
            "長期計画のため、直前に最新予報で最終確認してください。",
        ],
        "packing": monthly["packing"],
        "precipitation_like": target_date.month in {6, 7, 9},
        "source_mode": "seasonal_fallback",
    }


def build_weather_context(planning_state: Dict[str, object]) -> Dict[str, object]:
    departure_place = str(planning_state.get("departure_place", "") or "")
    destination_place = str(planning_state.get("primary_destination") or planning_state.get("return_place", "") or "")
    start_date_value = _parse_date(str(planning_state.get("start_date", "") or ""))
    trip_days = max(1, int(planning_state.get("trip_days", 1) or 1))
    end_date_value = start_date_value
    departure_area = _detect_area(departure_place)
    destination_area = _detect_area(destination_place)

    mode_label = "実天気API（Open-Meteo）"
    try:
        loc = geocode_place(destination_place)
        if loc:
            live = _build_live_forecast_context(loc, start_date_value)
        else:
            live = _build_climate_fallback_context(start_date_value)
            mode_label = "季節傾向（地名解決失敗時フォールバック）"
    except Exception:
        live = _build_climate_fallback_context(start_date_value)
        mode_label = "季節傾向（APIフォールバック）"

    if live.get("source_mode") == "live_forecast":
        days_ahead = (start_date_value - date.today()).days
        mode_label = "実天気API（Open-Meteo / 予報）" if days_ahead <= 16 else "実天気API（Open-Meteo）"

    summary = str(live.get("summary", ""))
    return {
        "headline": f"{_area_label(destination_place)} の天候メモ",
        "mode_label": mode_label,
        "date_range_label": f"{start_date_value.strftime('%Y-%m-%d')} 〜 {end_date_value.strftime('%Y-%m-%d')}",
        "summary": summary,
        "detail_lines": list(live.get("detail_lines", [])),
        "packing": str(live.get("packing", "薄手の羽織りがおすすめです。")),
        "gap_advice": _build_gap_advice(departure_area, destination_area),
        "execution_hint": _build_execution_hint(summary, bool(live.get("precipitation_like", False))),
        "departure_label": _area_label(departure_place),
        "destination_label": _area_label(destination_place),
        "attribution": "Weather data by Open-Meteo.com",
    }
