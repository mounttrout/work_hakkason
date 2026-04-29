# -*- coding: utf-8 -*-
"""
VoyageFlow / Dynamic Checklist Agent
v6.2.67-nav-shortcut-checklist-personal-filter-hotel-cafe-guard

目的:
- 固定チェックリストではなく、旅行条件・完成旅程・同行者・目的・移動手段から動的にToDo/持ち物を生成する。
- app.pyには直書きせず、外部サービスとして呼び出される前提。
- LLMを使わずルールベースで安定生成し、将来LLM補強を追加しやすい形にする。
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Any, Dict, Iterable, List, Optional

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None


ChecklistItem = Dict[str, Any]
ChecklistResult = Dict[str, Any]


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        if pd is not None and pd.isna(value):
            return default
    except Exception:
        pass
    text = str(value).strip()
    return text if text else default


def _norm(value: Any) -> str:
    return _safe_text(value).lower()


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    return any(k and k.lower() in text.lower() for k in keywords)


def _google_search_url(query: str) -> str:
    return "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)


def _google_maps_search_url(query: str) -> str:
    return "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote_plus(query)


def _item(item_id: str, text: str, category: str = "general", priority: str = "normal", action_label: str = "", action_url: str = "", note: str = "") -> ChecklistItem:
    return {
        "id": re.sub(r"[^a-zA-Z0-9_\-]", "_", item_id)[:96],
        "text": text,
        "category": category,
        "priority": priority,
        "action_label": action_label,
        "action_url": action_url,
        "note": note,
    }


def _canonical_item_text(value: Any) -> str:
    text = _safe_text(value).lower()
    text = re.sub(r"[\s\u3000・,，.．:：/／\-ー〜~()（）［］\[\]「」『』<>〈〉]+", "", text)
    return text


def _append_unique(items: List[ChecklistItem], item: ChecklistItem) -> None:
    item_text = _safe_text(item.get("text"))
    item_key = _canonical_item_text(item_text)
    existing_texts = {_canonical_item_text(x.get("text")) for x in items}
    if item_key and item_key not in existing_texts:
        items.append(item)


def _df_records(df: Any) -> List[Dict[str, Any]]:
    if df is None:
        return []
    try:
        if getattr(df, "empty", True):
            return []
        return df.copy().reset_index(drop=True).to_dict("records")
    except Exception:
        if isinstance(df, list):
            return [r for r in df if isinstance(r, dict)]
        return []


def _is_transport(row: Dict[str, Any]) -> bool:
    return bool(row.get("is_transport", False)) or _safe_text(row.get("purpose")).lower() == "transport"


def _is_hotel(row: Dict[str, Any]) -> bool:
    destination = _safe_text(row.get("destination"))
    purpose = _safe_text(row.get("purpose")).lower()
    genre = _safe_text(row.get("genre")).lower()
    return purpose in {"accommodation", "hotel", "stay", "lodging"} or genre == "hotel" or any(k in destination.lower() for k in ["ホテル", "旅館", "hotel", "inn", "resort"])


def _is_tokyo_area_name(value: str) -> bool:
    text = _safe_text(value)
    tokens = ["東京", "両国", "浅草", "上野", "渋谷", "新宿", "後楽園", "水道橋", "神楽坂", "銀座", "表参道", "秋葉原", "池袋", "品川", "台東", "墨田", "文京", "千代田"]
    return any(token in text for token in tokens)


def _is_long_distance_train_segment(seg: Dict[str, Any]) -> bool:
    text = " ".join([
        _safe_text(seg.get("label")),
        _safe_text(seg.get("origin")),
        _safe_text(seg.get("destination")),
        _safe_text(seg.get("one_point")),
        _safe_text(seg.get("route_data_source")),
    ])
    if _contains_any(text, ["新幹線", "特急", "かがやき", "はくたか", "サンダーバード", "しらさぎ"]):
        return True
    try:
        minutes = int(float(seg.get("duration_minutes") or 0))
    except Exception:
        minutes = 0
    origin = _safe_text(seg.get("origin"))
    dest = _safe_text(seg.get("destination"))
    if minutes >= 90 and not (_is_tokyo_area_name(origin) and _is_tokyo_area_name(dest)):
        return True
    return False


def _transport_mode(row: Dict[str, Any]) -> str:
    mode = _safe_text(row.get("transport_mode")).lower()
    if not mode:
        destination = _safe_text(row.get("destination")).lower()
        purpose = _safe_text(row.get("purpose")).lower()
        text = f"{destination} {purpose}"
        if _contains_any(text, ["新幹線", "電車", "列車", "train", "rail"]):
            mode = "train"
        elif _contains_any(text, ["飛行機", "航空", "フライト", "flight", "air"]):
            mode = "air"
        elif _contains_any(text, ["レンタカー", "車", "drive", "car"]):
            mode = "car"
        elif _contains_any(text, ["バス", "bus"]):
            mode = "bus"
        elif _contains_any(text, ["船", "フェリー", "ferry", "ship"]):
            mode = "ship"
        elif _contains_any(text, ["タクシー", "taxi"]):
            mode = "taxi"
        elif _contains_any(text, ["徒歩", "walk"]):
            mode = "walk"
    return mode or "unknown"


def _infer_trip_days(planning_state: Dict[str, Any], rows: List[Dict[str, Any]]) -> int:
    try:
        return max(1, int(planning_state.get("trip_days") or 1))
    except Exception:
        days = []
        for row in rows:
            try:
                days.append(int(row.get("day")))
            except Exception:
                pass
        return max(days) if days else 1


def _infer_main_destination(planning_state: Dict[str, Any], rows: List[Dict[str, Any]], user_context: Dict[str, Any]) -> str:
    for key in ["destination", "primary_destination"]:
        value = _safe_text(user_context.get(key) or planning_state.get(key))
        if value:
            return value
    candidates: List[str] = []
    for row in rows:
        if _is_transport(row):
            continue
        dest = _safe_text(row.get("destination"))
        if dest and not _is_hotel(row):
            candidates.append(dest)
    return candidates[0] if candidates else _safe_text(planning_state.get("return_place") or planning_state.get("departure_place"), "旅行先")


def _infer_purpose_text(planning_state: Dict[str, Any], rows: List[Dict[str, Any]], user_context: Dict[str, Any]) -> str:
    direct = _safe_text(user_context.get("purpose"))
    if direct:
        return direct
    purposes = " ".join(_safe_text(row.get("purpose")) + " " + _safe_text(row.get("one_point")) for row in rows[:20])
    if _contains_any(purposes, ["business", "出張", "会議", "仕事"]):
        return "仕事・出張"
    if _contains_any(purposes, ["登山", "ハイキング", "アウトドア"]):
        return "登山・アウトドア"
    if _contains_any(purposes, ["海", "ビーチ", "海水浴", "シュノーケル", "diving"]):
        return "海・リゾート"
    if _contains_any(purposes, ["法事", "葬儀", "墓参り"]):
        return "法事・帰省"
    return "観光"


def _extract_hotels(rows: List[Dict[str, Any]]) -> List[str]:
    hotels: List[str] = []
    seen = set()
    for row in rows:
        if _is_transport(row):
            continue
        if _is_hotel(row):
            name = _safe_text(row.get("destination"))
            if not name or "→" in name or name in {"ホテル", "宿泊先"}:
                continue
            key = _canonical_item_text(name)
            if key and key not in seen:
                seen.add(key)
                hotels.append(name)
    return hotels


def _extract_transport_segments(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    segments: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        if not _is_transport(row):
            continue
        mode = _transport_mode(row)
        origin = _safe_text(row.get("route_from")) or _safe_text(row.get("origin"))
        dest = _safe_text(row.get("route_to")) or _safe_text(row.get("destination"))
        if not origin and "→" in _safe_text(row.get("destination")):
            parts = _safe_text(row.get("destination")).split("→")
            origin = parts[0].strip()
            dest = parts[-1].strip()
        label = f"{origin}→{dest}" if origin and dest and origin != dest else (dest or _safe_text(row.get("destination"), "移動"))
        key = (mode, _canonical_item_text(origin), _canonical_item_text(dest), _safe_text(row.get("date")), _safe_text(row.get("start_time")))
        if key in seen:
            continue
        seen.add(key)
        segments.append({
            "mode": mode,
            "origin": origin,
            "destination": dest,
            "label": label,
            "date": _safe_text(row.get("date")),
            "start_time": _safe_text(row.get("start_time")),
            "duration_minutes": row.get("duration_minutes"),
            "one_point": _safe_text(row.get("one_point")),
            "route_data_source": _safe_text(row.get("route_data_source")),
        })
    return segments


def _detect_context_flags(destination: str, purpose: str, companions: str, personal_info: str, rows: List[Dict[str, Any]]) -> Dict[str, bool]:
    # --- v6.2.67 ---
    # 「家族・同僚へのお土産」など旅程メモ由来の単語だけで、
    # 子連れ/パーソナル特化項目を誤発火させない。
    # 子供・年齢・趣味系は、同行者/パーソナル情報/旅行目的の明示を優先する。
    row_text = " ".join(
        _safe_text(r.get("destination")) + " " + _safe_text(r.get("purpose")) + " " + _safe_text(r.get("one_point"))
        for r in rows
    )
    explicit_text = " ".join([destination, purpose, companions, personal_info])
    all_text = " ".join([explicit_text, row_text])

    child_explicit_text = " ".join([companions, personal_info, purpose])
    child_keywords = ["子供", "子ども", "こども", "子連れ", "小学生", "中学生", "幼児", "乳児", "赤ちゃん", "ベビ", "未就学", "園児"]
    baby_keywords = ["乳児", "赤ちゃん", "0歳", "1歳", "2歳", "ベビ", "おむつ", "ミルク"]
    school_keywords = ["小学生", "小学校", "低学年", "高学年", "6年生", "子供2人", "子ども2人", "こども2人"]

    children = _contains_any(child_explicit_text, child_keywords)
    # 「家族」はお土産先として旅程メモに出やすいため、同行者欄で明示された場合だけ子連れ扱い。
    if not children and _contains_any(companions, ["家族", "親子"]):
        children = True

    business = _contains_any(explicit_text, ["仕事", "出張", "会議", "商談", "展示会", "セミナー", "business", "同僚", "職場"])
    if not business and _contains_any(row_text, ["訪問先企業", "商談", "会議", "アポイント", "打ち合わせ"]):
        business = True

    return {
        "overseas": _contains_any(all_text, ["海外", "ハワイ", "hawaii", "グアム", "韓国", "台湾", "シンガポール", "ヨーロッパ", "アメリカ"]),
        "beach": _contains_any(all_text, ["ハワイ", "海水浴", "ビーチ", "シュノーケル", "ダイビング", "沖縄", "グアム", "プール", "マリンスポーツ"]),
        "business": business,
        "children": children,
        "baby": children and _contains_any(child_explicit_text, baby_keywords),
        "school_child": children and _contains_any(child_explicit_text, school_keywords),
        "senior": _contains_any(explicit_text, ["高齢", "シニア", "70代", "80代", "祖父", "祖母"]),
        "outdoor": _contains_any(all_text, ["登山", "ハイキング", "キャンプ", "アウトドア", "トレッキング", "山歩き", "高原"]),
        "formal": _contains_any(all_text, ["法事", "葬儀", "結婚式", "式典", "礼服", "喪服"]),
        "gadget": _contains_any(explicit_text, ["ガジェット", "データサイエンティスト", "エンジニア", "pc", "カメラ", "撮影", "動画"]),
        "running": _contains_any(explicit_text, ["ランニング", "ジョギング", "ランナー"]),
        "themepark": _contains_any(all_text, ["ディズニー", "usj", "ユニバ", "テーマパーク", "遊園地"]),
        "onsen": _contains_any(all_text, ["温泉", "旅館", "スパ"]),
    }


def _add_transport_todos(before: List[ChecklistItem], day_of: List[ChecklistItem], during: List[ChecklistItem], segments: List[Dict[str, Any]]) -> None:
    local_train_seen = False
    for idx, seg in enumerate(segments[:12], start=1):
        mode = seg.get("mode", "unknown")
        label = seg.get("label") or "移動"
        if mode in {"train", "rail"}:
            if _is_long_distance_train_segment(seg):
                _append_unique(before, _item(f"todo_before_train_{idx}", f"{label} の長距離列車・新幹線チケットを予約/確認する", "reservation", "high", "🚄 予約/確認", _google_search_url(f"{label} 新幹線 電車 予約")))
            elif not local_train_seen:
                local_train_seen = True
                _append_unique(during, _item("todo_during_local_train_route", "都市内の電車移動は、各移動前に現在地からの経路・乗り場を確認する", "transport", "normal"))
        elif mode == "air":
            _append_unique(before, _item(f"todo_before_air_{idx}", f"{label} の航空券・搭乗時刻を確認する", "reservation", "high", "✈️ 航空券確認", _google_search_url(f"{label} 航空券 予約 確認")))
            _append_unique(day_of, _item(f"todo_day_air_{idx}", "空港到着時刻・保安検査締切・手荷物条件を確認する", "transport", "high"))
        elif mode in {"car", "drive", "rental_car"}:
            _append_unique(before, _item(f"todo_before_car_{idx}", f"{label} のレンタカー予約・免許証・ETCカードを確認する", "reservation", "high", "🚗 レンタカー確認", _google_search_url(f"{label} レンタカー 予約")))
        elif mode == "bus":
            _append_unique(before, _item(f"todo_before_bus_{idx}", f"{label} のバス予約・乗り場を確認する", "reservation", "normal", "🚌 バス確認", _google_search_url(f"{label} バス 予約 乗り場")))
        elif mode in {"ship", "ferry"}:
            _append_unique(before, _item(f"todo_before_ship_{idx}", f"{label} の船便・フェリー予約と運航状況を確認する", "reservation", "high", "⛴️ 船便確認", _google_search_url(f"{label} フェリー 予約 運航状況")))
        elif mode == "taxi":
            _append_unique(day_of, _item(f"todo_day_taxi_{idx}", f"{label} のタクシー配車候補を確認する", "transport", "normal", "🚕 配車確認", _google_search_url(f"{label} タクシー 配車")))


def build_trip_checklist(planning_state: Optional[Dict[str, Any]] = None, itinerary_df: Any = None, user_context: Optional[Dict[str, Any]] = None) -> ChecklistResult:
    planning_state = planning_state or {}
    user_context = user_context or {}
    rows = _df_records(itinerary_df)
    trip_days = _infer_trip_days(planning_state, rows)
    destination = _infer_main_destination(planning_state, rows, user_context)
    purpose = _infer_purpose_text(planning_state, rows, user_context)
    companions = _safe_text(user_context.get("companions"), "未入力")
    personal_info = _safe_text(user_context.get("personal_info"), "未入力")
    transport_segments = _extract_transport_segments(rows)
    hotels = _extract_hotels(rows)
    flags = _detect_context_flags(destination, purpose, companions, personal_info, rows)

    before: List[ChecklistItem] = []
    day_of: List[ChecklistItem] = []
    during: List[ChecklistItem] = []

    _append_unique(before, _item("todo_before_itinerary_review", "完成旅程の日時・集合場所・移動手段を確認する", "planning", "high"))
    _append_unique(before, _item("todo_before_calendar", "旅程をカレンダーに登録し、出発/移動の通知を設定する", "planning", "normal"))
    _append_unique(day_of, _item("todo_day_valuables", "財布・スマホ・鍵・身分証を出発前に確認する", "departure", "high"))
    _append_unique(day_of, _item("todo_day_route", "最初の移動経路と出発時刻を確認する", "transport", "high"))
    _append_unique(during, _item("todo_during_next_route", "次の移動前にGoogle Maps等で現在地からの経路を確認する", "execution", "normal"))
    _append_unique(during, _item("todo_during_weather_hours", "屋外予定・営業時間・イベント有無を当日再確認する", "execution", "normal"))

    for idx, hotel in enumerate(hotels[:5], start=1):
        _append_unique(before, _item(f"todo_before_hotel_{idx}", f"{hotel} の予約・チェックイン時刻を確認する", "reservation", "high", "🏨 予約/確認", _google_search_url(f"{hotel} 予約 確認")))
        _append_unique(day_of, _item(f"todo_day_hotel_{idx}", f"{hotel} の住所・チェックイン方法をスマホですぐ見られるようにする", "hotel", "normal", "🗺️ 地図", _google_maps_search_url(hotel)))

    _add_transport_todos(before, day_of, during, transport_segments)

    if flags["overseas"]:
        _append_unique(before, _item("todo_before_passport", "パスポート残存期限・入国条件・海外旅行保険を確認する", "documents", "high"))
        _append_unique(before, _item("todo_before_currency", "現地決済手段・クレジットカード・通信手段を確認する", "money", "high"))
    if flags["business"]:
        _append_unique(before, _item("todo_before_business_docs", "名刺・PC・会議資料・訪問先住所を確認する", "business", "high"))
        _append_unique(day_of, _item("todo_day_business_battery", "PCとスマホを満充電にし、充電器を取り出しやすくする", "business", "high"))
    if flags["children"]:
        _append_unique(before, _item("todo_before_child_plan", "子供の年齢に合わせて休憩・トイレ・食事タイミングを確認する", "family", "high"))
        _append_unique(day_of, _item("todo_day_child_contact", "迷子対策として集合場所・連絡方法を子供と確認する", "family", "high"))
    if flags["beach"]:
        _append_unique(before, _item("todo_before_beach_weather", "海・ビーチ予定日の天候、日差し、遊泳可否を確認する", "beach", "high"))
    if flags["outdoor"]:
        _append_unique(before, _item("todo_before_outdoor_weather", "登山・屋外予定の天候、装備、撤退判断ラインを確認する", "outdoor", "high"))
    if flags["themepark"]:
        _append_unique(before, _item("todo_before_themepark_ticket", "テーマパークのチケット、入園時間、アプリ登録を確認する", "ticket", "high", "🎫 チケット確認", _google_search_url(f"{destination} チケット アプリ")))
    if flags["formal"]:
        _append_unique(before, _item("todo_before_formal_clothes", "礼服・靴・数珠/招待状など式典に必要なものを確認する", "formal", "high"))

    packing: Dict[str, List[ChecklistItem]] = {
        "必須アイテム（貴重品・書類）": [],
        "衣類・身の回り品": [],
        "パーソナル特化アイテム": [],
        "ガジェット・仕事道具": [],
        "目的地・目的に応じた便利グッズ": [],
    }

    for item in [
        _item("pack_wallet", "財布・クレジットカード・交通系IC", "packing", "high"),
        _item("pack_phone", "スマホ", "packing", "high"),
        _item("pack_id", "身分証・保険証", "packing", "high"),
        _item("pack_ticket", "予約番号・チケット・QRコード控え", "packing", "high"),
    ]:
        _append_unique(packing["必須アイテム（貴重品・書類）"], item)

    if flags["overseas"]:
        for item in [
            _item("pack_passport", "パスポート", "packing", "high"),
            _item("pack_overseas_insurance", "海外旅行保険・入国関連書類", "packing", "high"),
            _item("pack_foreign_payment", "海外利用可能なカード・現金・通信手段", "packing", "high"),
        ]:
            _append_unique(packing["必須アイテム（貴重品・書類）"], item)

    clothing_base = [
        _item("pack_clothes", f"{trip_days}日分の着替え", "packing", "normal"),
        _item("pack_toiletries", "洗面用具・常備薬", "packing", "normal"),
        _item("pack_rain", "折りたたみ傘または軽量レインウェア", "packing", "normal"),
    ]
    for item in clothing_base:
        _append_unique(packing["衣類・身の回り品"], item)

    if flags["beach"]:
        for item in [
            _item("pack_swimsuit", "水着・ラッシュガード", "packing", "high"),
            _item("pack_sunscreen", "日焼け止め・アフターサンケア", "packing", "high"),
            _item("pack_beach_sandals", "ビーチサンダル・防水バッグ", "packing", "normal"),
            _item("pack_sunglasses", "サングラス・帽子", "packing", "normal"),
        ]:
            _append_unique(packing["目的地・目的に応じた便利グッズ"], item)

    if flags["children"]:
        child_items = [
            _item("pack_child_snack", "子供用のおやつ・飲み物", "packing", "normal"),
            _item("pack_child_change", "子供の着替え多め・羽織り", "packing", "normal"),
            _item("pack_child_entertainment", "移動中の暇つぶしグッズ・イヤホン", "packing", "normal"),
        ]
        if flags["baby"]:
            child_items.extend([
                _item("pack_baby_diaper", "おむつ・おしりふき・ビニール袋", "packing", "high"),
                _item("pack_baby_milk", "ミルク・哺乳瓶・離乳食", "packing", "high"),
                _item("pack_baby_carrier", "抱っこ紐・ベビーカー関連用品", "packing", "normal"),
            ])
        if flags["school_child"]:
            child_items.extend([
                _item("pack_school_child_ic", "子供用ICカード・小銭", "packing", "normal"),
                _item("pack_school_child_motion", "酔い止め・絆創膏", "packing", "normal"),
            ])
        for item in child_items:
            _append_unique(packing["パーソナル特化アイテム"], item)

    if flags["business"]:
        for item in [
            _item("pack_business_cards", "名刺", "packing", "high"),
            _item("pack_pc", "PC・ACアダプタ", "packing", "high"),
            _item("pack_business_docs", "会議資料・筆記具", "packing", "high"),
            _item("pack_formal_shirt", "ジャケット・シャツ・革靴などビジネス服", "packing", "normal"),
        ]:
            _append_unique(packing["ガジェット・仕事道具"], item)

    gadget_items = [
        _item("pack_charger", "スマホ充電器・ケーブル", "packing", "high"),
        _item("pack_mobile_battery", "モバイルバッテリー", "packing", "high"),
    ]
    if flags["gadget"]:
        gadget_items.extend([
            _item("pack_camera", "カメラ・予備バッテリー・SDカード", "packing", "normal"),
            _item("pack_pc_extra", "PC周辺機器・USB-Cハブ", "packing", "normal"),
        ])
    for item in gadget_items:
        _append_unique(packing["ガジェット・仕事道具"], item)

    if flags["outdoor"]:
        for item in [
            _item("pack_outdoor_shoes", "歩きやすい靴・登山靴", "packing", "high"),
            _item("pack_outdoor_rainwear", "防水レインウェア", "packing", "high"),
            _item("pack_outdoor_food", "水・行動食・救急セット", "packing", "high"),
        ]:
            _append_unique(packing["目的地・目的に応じた便利グッズ"], item)

    if flags["onsen"]:
        for item in [
            _item("pack_onsen_pouch", "温泉用の小さめポーチ", "packing", "normal"),
            _item("pack_skin_care", "スキンケア用品", "packing", "normal"),
        ]:
            _append_unique(packing["目的地・目的に応じた便利グッズ"], item)

    if flags["running"]:
        for item in [
            _item("pack_running_shoes", "ランニングシューズ", "packing", "normal"),
            _item("pack_running_wear", "ランニングウェア・汗拭きタオル", "packing", "normal"),
        ]:
            _append_unique(packing["パーソナル特化アイテム"], item)

    advice: List[str] = []
    if transport_segments:
        advice.append("長距離移動や乗換があるため、出発前にチケット・乗り場・発車時刻をスクリーンショットで保存しておくと安心です。")
    if hotels:
        advice.append("ホテルはチェックイン時刻と荷物預かり可否を確認しておくと、初日・最終日の動きが安定します。")
    if flags["beach"]:
        advice.append("海・リゾート予定では日差しと急な雨の両方に備え、日焼け止めと防水バッグをすぐ出せる場所に入れてください。")
    if flags["children"]:
        advice.append("子連れ旅行は予定を詰めすぎず、移動前にトイレ・飲み物・休憩ポイントを確認すると崩れにくくなります。")
    if flags["business"]:
        advice.append("出張ではPC充電・名刺・資料に加え、領収書の保存ルールを事前に決めておくと後処理が楽になります。")
    if not advice:
        advice.append("当日は天気・交通状況・営業時間が変わる可能性があるため、出発前と各移動前に最新情報を確認してください。")
    while len(advice) < 3:
        if len(advice) == 1:
            advice.append("スマホの電池切れが旅程実行の大きなリスクになるため、モバイルバッテリーは最優先で準備してください。")
        else:
            advice.append("予約情報・地図リンク・ホテル住所はオフラインでも見られるように保存しておくと安心です。")

    # --- v6.2.66: 生成後にも念のためセクション内重複を除去 ---
    def _dedupe_items(items: List[ChecklistItem]) -> List[ChecklistItem]:
        cleaned: List[ChecklistItem] = []
        for item in items:
            _append_unique(cleaned, item)
        return cleaned

    before = _dedupe_items(before)
    day_of = _dedupe_items(day_of)
    during = _dedupe_items(during)
    for section_name in list(packing.keys()):
        packing[section_name] = _dedupe_items(packing[section_name])

    return {
        "meta": {
            "destination": destination,
            "purpose": purpose,
            "companions": companions,
            "personal_info": personal_info,
            "trip_days": trip_days,
            "detected_flags": flags,
            "transport_modes": sorted({seg.get("mode", "unknown") for seg in transport_segments}),
            "hotel_names": hotels,
        },
        "todo_sections": {
            "出発前（1週間前〜前日）": before,
            "出発当日": day_of,
            "旅行中": during,
        },
        "packing_sections": packing,
        "advice": advice[:3],
    }
