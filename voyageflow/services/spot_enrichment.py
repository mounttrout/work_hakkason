# -*- coding: utf-8 -*-
"""
VoyageFlow Spot Enrichment Service
version: v0.2.0
created: 2026-04-27

目的:
- スポット名から公式情報・イベント情報・予約導線を返す
- LLMに最新イベントを生成させず、辞書ベースで安全に補完する
- 未登録スポットは検索/公式確認fallback用データを返す
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

try:
    from data.spot_event_dictionary import SPOT_EVENT_DICTIONARY
except Exception:
    SPOT_EVENT_DICTIONARY = {}


def normalize_spot_name(name: Any) -> str:
    if name is None:
        return ""
    text = str(name).strip().replace("　", " ")
    return text


def find_spot_key(spot_name: Any) -> Optional[str]:
    name = normalize_spot_name(spot_name)
    if not name:
        return None
    if name in SPOT_EVENT_DICTIONARY:
        return name
    for key in SPOT_EVENT_DICTIONARY.keys():
        if key in name or name in key:
            return key
    return None


def build_google_search_url(query: str) -> str:
    return "https://www.google.com/search?q=" + quote_plus(query)


def enrich_spot_info(
    spot_name: Any,
    area_hint: Optional[str] = None,
    travel_date: Optional[str] = None,
) -> Dict[str, Any]:
    name = normalize_spot_name(spot_name)
    key = find_spot_key(name)

    if key:
        data = SPOT_EVENT_DICTIONARY.get(key, {})
        return {
            "matched": True,
            "spot_name": name,
            "matched_name": key,
            "area": data.get("area"),
            "category": data.get("category"),
            "official_url": data.get("official_url"),
            "latest_info_url": data.get("latest_info_url") or data.get("official_url"),
            "reservation_url": data.get("reservation_url"),
            "display_note": data.get("display_note", "最新情報は公式サイトで確認してください。"),
            "known_events": data.get("known_events", []),
            "fallback_search_url": build_google_search_url(f"{key} 公式 最新情報"),
        }

    search_query_parts = [name]
    if area_hint:
        search_query_parts.append(str(area_hint))
    if travel_date:
        search_query_parts.append(str(travel_date))
    search_query_parts.append("公式 最新情報")
    fallback_url = build_google_search_url(" ".join(search_query_parts))

    return {
        "matched": False,
        "spot_name": name,
        "matched_name": None,
        "area": area_hint,
        "category": None,
        "official_url": None,
        "latest_info_url": fallback_url,
        "reservation_url": None,
        "display_note": "このスポットは辞書未登録です。最新情報は公式サイトまたは検索結果から確認してください。",
        "known_events": [],
        "fallback_search_url": fallback_url,
    }


def spot_enrichment_headline(info: Dict[str, Any]) -> str:
    if not info:
        return "公式情報確認"
    events = info.get("known_events") or []
    if events:
        return f"公式情報・登録イベント {len(events)}件"
    if info.get("matched"):
        category = str(info.get("category") or "")
        if category in {"museum"}:
            return "展示・公式情報確認"
        if category in {"theater"}:
            return "公演・公式情報確認"
        if category in {"theme_park"}:
            return "イベント・運営情報確認"
        return "公式情報確認"
    return "公式情報検索"


def primary_spot_info_url(info: Dict[str, Any]) -> str:
    if not info:
        return ""
    return str(info.get("latest_info_url") or info.get("official_url") or info.get("fallback_search_url") or "")


def format_spot_enrichment_markdown(info: Dict[str, Any]) -> str:
    if not info:
        return ""

    lines: List[str] = []
    lines.append("**🔎 最新情報**")

    if info.get("display_note"):
        lines.append(f"- 注意: {info.get('display_note')}")

    events = info.get("known_events") or []
    if events:
        lines.append("- 登録済みイベント/展示:")
        for ev in events:
            name = ev.get("name", "名称未設定")
            period = ev.get("period", "期間未設定")
            source_url = ev.get("source_url")
            if source_url:
                lines.append(f"  - [{name}]({source_url})（{period}）")
            else:
                lines.append(f"  - {name}（{period}）")
    elif info.get("matched"):
        lines.append("- 登録済みイベント/展示: なし（公式ページで最新情報を確認）")
    else:
        lines.append("- 登録済みイベント/展示: 未登録")

    official_url = info.get("official_url")
    latest_info_url = info.get("latest_info_url")
    reservation_url = info.get("reservation_url")

    if official_url:
        lines.append(f"- [公式サイト]({official_url})")
    if latest_info_url:
        lines.append(f"- [最新情報を確認]({latest_info_url})")
    if reservation_url:
        lines.append(f"- [予約・チケット確認]({reservation_url})")

    return "\n".join(lines)


def enrich_spot_as_markdown(
    spot_name: Any,
    area_hint: Optional[str] = None,
    travel_date: Optional[str] = None,
) -> str:
    info = enrich_spot_info(spot_name=spot_name, area_hint=area_hint, travel_date=travel_date)
    return format_spot_enrichment_markdown(info)
