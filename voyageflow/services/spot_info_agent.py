# -*- coding: utf-8 -*-
"""
VoyageFlow v6.2.64
Spot Info Agent

役割:
- スポットの公式情報リンク・確認推奨・信頼性警告を返す
- app.pyから独立し、LLMに事実を作らせない
- 未登録スポットは「公式確認検索」へfallbackする

このファイルはStreamlitに依存しない。
app.py側は戻り値を表示するだけにする。
"""

from __future__ import annotations

import re
import urllib.parse
from datetime import datetime
from typing import Dict, List, Optional, Tuple

try:
    from data.spot_info_rules import (
        JAPANESE_PUBLIC_HOLIDAYS_2026,
        SPOT_INFO_SOURCES,
        SPOT_RELIABILITY_RULES,
    )
except Exception:
    # app.py側のfallbackを壊さないため、import失敗時は空辞書で動く。
    JAPANESE_PUBLIC_HOLIDAYS_2026 = set()
    SPOT_INFO_SOURCES = {}
    SPOT_RELIABILITY_RULES = {}


def _safe_text(value, default: str = "") -> str:
    if value is None:
        return default
    try:
        # pandas.NA / NaN対策。pandasには依存しない。
        if value != value:  # noqa: PLR0124
            return default
    except Exception:
        pass
    text = str(value).strip()
    return text if text else default


def _parse_date_value(date_text: str):
    text = _safe_text(date_text)
    if not text or text == "-":
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except Exception:
            continue
    return None


def _time_to_minutes(value: str) -> Optional[int]:
    text = _safe_text(value)
    if not text or ":" not in text:
        return None
    try:
        hour, minute = text.split(":", 1)
        return int(hour) * 60 + int(minute)
    except Exception:
        return None


def _date_in_range(date_value, start_text: str, end_text: str) -> bool:
    try:
        start = datetime.strptime(start_text, "%Y-%m-%d").date()
        end = datetime.strptime(end_text, "%Y-%m-%d").date()
        return start <= date_value <= end
    except Exception:
        return False


def _is_jp_public_holiday(date_value) -> bool:
    if not date_value:
        return False
    return date_value.strftime("%Y-%m-%d") in JAPANESE_PUBLIC_HOLIDAYS_2026


def _contains_hotel_token(name: str) -> bool:
    text = _safe_text(name)
    lowered = text.lower()
    return any(token in lowered for token in ["hotel", "inn", "resort", "hostel"]) or any(token in text for token in ["ホテル", "旅館", "宿泊先"])


def _is_station_anchor_name(name: str) -> bool:
    text = _safe_text(name)
    if not text:
        return False
    return text.endswith("駅") or text.endswith("空港") or text.endswith("港") or text in {"東京駅", "福井駅", "上野駅"}


def _spot_rule_for_destination(destination: str) -> Tuple[str, Dict[str, object]]:
    name = _safe_text(destination)
    for key, rule in SPOT_RELIABILITY_RULES.items():
        if key in name or name in key:
            return key, rule
    return "", {}


def _guess_spot_category(name: str) -> str:
    text = _safe_text(name)
    if not text:
        return "other"
    if any(token in text for token in ["美術館", "博物館", "ミュージアム", "資料館"]):
        return "museum"
    if any(token in text for token in ["劇場", "歌舞伎", "座", "シアター", "ホール"]):
        return "theater"
    if any(token in text for token in ["パーク", "公園", "庭園", "植物園", "動物園", "水族館"]):
        return "park"
    if any(token in text for token in ["寺", "神社", "大社", "宮", "院"]):
        return "shrine_temple"
    if any(token in text for token in ["モール", "百貨店", "デパート", "商店街", "市場", "SIX", "タウン", "シティ", "プラザ"]):
        return "commercial_complex"
    if any(token in text for token in ["レストラン", "食堂", "カフェ", "喫茶", "寿司", "ラーメン", "居酒屋"]):
        return "restaurant"
    return "other"


def _latest_info_search_url(destination: str, travel_date: str, category: str) -> Tuple[str, str, str]:
    name = _safe_text(destination)
    date_text = _safe_text(travel_date)
    date_suffix = f" {date_text}" if date_text and date_text != "-" else ""

    if category == "museum":
        query = f"{name} 展覧会 イベント 公式{date_suffix}"
        label = "展示・イベント情報を調べる"
        note = "辞書未登録の美術館/博物館候補です。公式カレンダー確認を優先してください。"
    elif category == "theater":
        query = f"{name} 公演 演目 公式{date_suffix}"
        label = "公演・演目情報を調べる"
        note = "日時指定イベントの可能性があります。公式公演情報を確認してください。"
    elif category == "commercial_complex":
        query = f"{name} イベント 公式{date_suffix}"
        label = "イベント情報を調べる"
        note = "営業時間・イベント情報は公式ページ確認を優先してください。"
    elif category == "park":
        query = f"{name} イベント 見頃 公式{date_suffix}"
        label = "イベント・見頃情報を調べる"
        note = "イベント・開園状況は公式情報を確認してください。"
    elif category == "shrine_temple":
        query = f"{name} 行事 拝観時間 公式{date_suffix}"
        label = "行事・拝観情報を調べる"
        note = "行事・拝観時間は公式情報を確認してください。"
    elif category == "restaurant":
        query = f"{name} 営業時間 予約 公式{date_suffix}"
        label = "営業・予約情報を調べる"
        note = "営業時間・予約可否は公式/予約サイト確認を優先してください。"
    else:
        query = f"{name} 公式 最新情報{date_suffix}"
        label = "公式情報を調べる"
        note = "辞書未登録スポットです。最新情報は公式サイトまたは検索結果から確認してください。"

    return label, "https://www.google.com/search?q=" + urllib.parse.quote(query), note


def get_spot_info(spot_name: str, area_hint: str = "", travel_date: str = "") -> Dict[str, object]:
    """
    スポット情報表示用の軽量結果を返す。

    Returns:
        {
            "spot_name": str,
            "matched_key": str,
            "category": str,
            "primary_url": str,
            "primary_label": str,
            "note": str,
            "source_type": "dictionary" | "official_search",
            "confidence": "high" | "low",
        }
    """
    name = _safe_text(spot_name)
    for key, info in SPOT_INFO_SOURCES.items():
        if key in name or name in key:
            return {
                "spot_name": name,
                "matched_key": key,
                "category": _safe_text(info.get("category"), "other"),
                "primary_url": _safe_text(info.get("primary_url")),
                "primary_label": _safe_text(info.get("primary_label"), "公式情報を見る"),
                "note": _safe_text(info.get("note")),
                "source_type": "dictionary",
                "confidence": "high",
                "area_hint": _safe_text(area_hint),
                "travel_date": _safe_text(travel_date),
            }

    category = _guess_spot_category(name)
    label, url, note = _latest_info_search_url(name, travel_date, category)
    return {
        "spot_name": name,
        "matched_key": "",
        "category": category,
        "primary_url": url,
        "primary_label": label,
        "note": note,
        "source_type": "official_search",
        "confidence": "low",
        "area_hint": _safe_text(area_hint),
        "travel_date": _safe_text(travel_date),
    }


def evaluate_spot_reliability(row_dict: Dict[str, object]) -> Dict[str, object]:
    """
    完成旅程カード用の信頼性警告を返す。

    app.py v6.2.59 の warning schema と互換:
    - level
    - title
    - message
    - action
    - url
    """
    destination = _safe_text(row_dict.get("destination"))
    if not destination or _contains_hotel_token(destination) or _is_station_anchor_name(destination):
        return {"warnings": [], "source": "spot_info_agent", "matched_key": ""}

    key, rule = _spot_rule_for_destination(destination)
    if not rule:
        return {"warnings": [], "source": "spot_info_agent", "matched_key": ""}

    visit_date = _parse_date_value(_safe_text(row_dict.get("date")))
    start_time = _safe_text(row_dict.get("start_time"))
    end_time = _safe_text(row_dict.get("end_time"))
    purpose = _safe_text(row_dict.get("purpose"))
    one_point = _safe_text(row_dict.get("one_point"))
    context = f"{destination} {purpose} {one_point}"
    warnings: List[Dict[str, str]] = []
    rule_type = _safe_text(rule.get("type"))

    if rule_type == "event_date" and visit_date:
        keywords = rule.get("event_keywords") or []
        mentions_event = any(str(token) in context for token in keywords)
        valid_ranges = rule.get("valid_ranges") or []
        in_valid_range = any(_date_in_range(visit_date, start, end) for start, end in valid_ranges)
        if mentions_event and not in_valid_range:
            warnings.append({
                "level": "warning",
                "title": "開催日注意",
                "message": _safe_text(rule.get("warning"), "この日付は対象イベントの開催期間外の可能性があります。"),
                "action": _safe_text(rule.get("alternative"), "公式スケジュールを確認してください。"),
                "url": _safe_text(rule.get("official_url")),
            })

    elif rule_type == "opening_hours" and visit_date:
        weekday = visit_date.weekday()
        closed_weekdays = rule.get("closed_weekdays") or []
        is_holiday = _is_jp_public_holiday(visit_date)
        if weekday in closed_weekdays and not (is_holiday and bool(rule.get("holiday_monday_open"))):
            warnings.append({
                "level": "warning",
                "title": "休館日注意",
                "message": _safe_text(rule.get("warning"), "休館日の可能性があります。"),
                "action": "日程変更または公式カレンダー確認をおすすめします。",
                "url": _safe_text(rule.get("official_url")),
            })

        start_min = _time_to_minutes(start_time)
        end_min = _time_to_minutes(end_time)
        open_min = _time_to_minutes(_safe_text(rule.get("open_time")))
        close_text = _safe_text(rule.get("close_time"))
        if visit_date.weekday() in {4, 5} and rule.get("fri_sat_close_time"):
            close_text = _safe_text(rule.get("fri_sat_close_time"), close_text)
        close_min = _time_to_minutes(close_text)

        last_entry = rule.get("last_entry_time")
        if last_entry:
            last_entry_min = _time_to_minutes(_safe_text(last_entry))
        elif close_min is not None and rule.get("last_entry_minutes_before_close"):
            last_entry_min = close_min - int(rule.get("last_entry_minutes_before_close") or 0)
        else:
            last_entry_min = None

        if start_min is not None and open_min is not None and start_min < open_min:
            warnings.append({
                "level": "warning",
                "title": "営業時間注意",
                "message": f"{key}の開館目安は{rule.get('open_time')}以降です。旅程の開始時刻が早すぎる可能性があります。",
                "action": "開館後に到着するよう時刻調整してください。",
                "url": _safe_text(rule.get("official_url")),
            })
        if end_min is not None and close_min is not None and end_min > close_min:
            warnings.append({
                "level": "warning",
                "title": "営業時間注意",
                "message": f"{key}の閉館目安は{close_text}です。旅程の終了時刻が営業時間外にかかる可能性があります。",
                "action": "滞在時間短縮または訪問時間の前倒しを検討してください。",
                "url": _safe_text(rule.get("official_url")),
            })
        if start_min is not None and last_entry_min is not None and start_min > last_entry_min:
            warnings.append({
                "level": "warning",
                "title": "入館締切注意",
                "message": f"{key}は閉館30分前などに入館締切となる可能性があります。",
                "action": "公式ページで最終入館時刻を確認してください。",
                "url": _safe_text(rule.get("official_url")),
            })

    elif rule_type == "official_confirmation":
        warnings.append({
            "level": "info",
            "title": "公式確認推奨",
            "message": _safe_text(rule.get("warning"), "日時指定イベントのため公式確認をおすすめします。"),
            "action": "公式スケジュール・チケット情報を確認してください。",
            "url": _safe_text(rule.get("official_url")),
        })

    return {"warnings": warnings, "source": "spot_info_agent", "matched_key": key}


__all__ = ["evaluate_spot_reliability", "get_spot_info"]
