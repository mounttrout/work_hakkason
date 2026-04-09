from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, List


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


_FORECAST_LIBRARY: Dict[str, Dict[str, object]] = {
    "hokkaido": {
        "summary": "朝晩はひんやりしやすく、風の影響を受けやすい見込みです。",
        "temp_range": "8〜16℃",
        "precipitation": "にわか雨の可能性あり",
        "packing": "薄手の上着と折りたたみ傘があると安心です。",
    },
    "tohoku": {
        "summary": "気温差が出やすく、時間帯によって体感が変わりやすい見込みです。",
        "temp_range": "10〜18℃",
        "precipitation": "一時的な雨に注意",
        "packing": "羽織ものと歩きやすい靴がおすすめです。",
    },
    "hokuriku": {
        "summary": "雲が広がりやすく、急な雨に備えたい見込みです。",
        "temp_range": "11〜18℃",
        "precipitation": "雨の可能性やや高め",
        "packing": "折りたたみ傘と防水性のある靴があると安心です。",
    },
    "tokyo": {
        "summary": "日中は動きやすい一方、時間帯によっては汗ばむ可能性があります。",
        "temp_range": "14〜22℃",
        "precipitation": "弱い雨の可能性あり",
        "packing": "脱ぎ着しやすい服装と飲み物の確保がおすすめです。",
    },
    "kanto": {
        "summary": "比較的動きやすい気温ですが、風やにわか雨に注意したい見込みです。",
        "temp_range": "13〜21℃",
        "precipitation": "一時的な雨に注意",
        "packing": "薄手の上着と折りたたみ傘があると安心です。",
    },
    "chubu": {
        "summary": "朝晩と日中の寒暖差が出やすい見込みです。",
        "temp_range": "11〜19℃",
        "precipitation": "場所により雨の可能性あり",
        "packing": "重ね着しやすい服装がおすすめです。",
    },
    "kansai": {
        "summary": "観光しやすい気温ですが、日差しが出ると体感はやや高めです。",
        "temp_range": "14〜22℃",
        "precipitation": "短時間の雨に注意",
        "packing": "薄手の羽織りと歩きやすい靴が便利です。",
    },
    "chugoku": {
        "summary": "日中は動きやすく、夕方以降はやや冷えやすい見込みです。",
        "temp_range": "13〜20℃",
        "precipitation": "弱い雨の可能性あり",
        "packing": "軽い上着があると安心です。",
    },
    "shikoku": {
        "summary": "比較的過ごしやすいですが、沿岸部は風に注意したい見込みです。",
        "temp_range": "14〜21℃",
        "precipitation": "にわか雨の可能性あり",
        "packing": "羽織ものと折りたたみ傘がおすすめです。",
    },
    "kyushu": {
        "summary": "やや暖かめで、場所によっては湿度を感じやすい見込みです。",
        "temp_range": "15〜23℃",
        "precipitation": "一時的な雨の可能性あり",
        "packing": "通気性のよい服装と折りたたみ傘が便利です。",
    },
    "okinawa": {
        "summary": "暖かく湿度も感じやすいため、屋外では日差し対策が必要です。",
        "temp_range": "22〜27℃",
        "precipitation": "スコールの可能性あり",
        "packing": "半袖に加えて日差し対策と薄い羽織りがおすすめです。",
    },
    "default": {
        "summary": "天候は大きく崩れにくい想定ですが、移動日は急な変化に備えると安心です。",
        "temp_range": "12〜20℃",
        "precipitation": "念のため雨具があると安心",
        "packing": "脱ぎ着しやすい服装がおすすめです。",
    },
}


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


def _build_execution_hint(summary: str, precipitation: str) -> str:
    if "雨" in precipitation or "スコール" in precipitation:
        return f"実行中は屋外スポットの前に天候確認を挟くと安全です。{summary}"
    return f"実行中は気温差に備えて休憩と水分補給を取りながら進めると安心です。{summary}"


def build_mock_weather_context(planning_state: Dict[str, object]) -> Dict[str, object]:
    departure_place = str(planning_state.get("departure_place", "") or "")
    destination_place = str(planning_state.get("return_place", "") or "")
    start_date_value = _parse_date(str(planning_state.get("start_date", "") or ""))
    trip_days = max(1, int(planning_state.get("trip_days", 1) or 1))
    end_date_value = start_date_value + timedelta(days=max(0, trip_days - 1))

    today = date.today()
    use_forecast = (start_date_value - today).days <= 7

    destination_area = _detect_area(destination_place)
    departure_area = _detect_area(departure_place)

    forecast = _FORECAST_LIBRARY.get(destination_area, _FORECAST_LIBRARY["default"])
    monthly = _MONTHLY_LIBRARY.get(start_date_value.month, _MONTHLY_LIBRARY[4])

    mode_label = "1週間以内の想定予報" if use_forecast else "季節統計ベースの目安"
    headline = f"{_area_label(destination_place)} の天候メモ"

    if use_forecast:
        summary = str(forecast["summary"])
        packing = str(forecast["packing"])
        detail_lines: List[str] = [
            f"気温目安: {forecast['temp_range']}",
            f"降水傾向: {forecast['precipitation']}",
        ]
        execution_hint = _build_execution_hint(summary, str(forecast["precipitation"]))
    else:
        summary = str(monthly["summary"])
        packing = str(monthly["packing"])
        detail_lines = [
            f"時期の目安: {start_date_value.month}月の傾向を基にした簡易アドバイスです。",
            "直前の実測天気ではないため、出発前に最新確認が必要です。",
        ]
        execution_hint = f"実行中は当日の空模様に応じて屋外・屋内の切替判断をしやすいよう、候補を柔軟に見ておくと安心です。{summary}"

    return {
        "headline": headline,
        "mode_label": mode_label,
        "date_range_label": f"{start_date_value.strftime('%Y-%m-%d')} 〜 {end_date_value.strftime('%Y-%m-%d')}",
        "summary": summary,
        "detail_lines": detail_lines,
        "packing": packing,
        "gap_advice": _build_gap_advice(departure_area, destination_area),
        "execution_hint": execution_hint,
        "departure_label": _area_label(departure_place),
        "destination_label": _area_label(destination_place),
    }
