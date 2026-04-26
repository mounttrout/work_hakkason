# -*- coding: utf-8 -*-
"""
VoyageFlow spot_enrichment.py

【役割】
- data/spot_event_dictionary.py の辞書を検索する。
- Phase2 / Phase3 の旅程データは変更しない。
- 完成旅程カード下部に表示する「🔎 最新情報」用の表示データを返す。
- 取得できない場合は公式検索リンクへフォールバックする。

【app.py からの利用イメージ】
from services.spot_enrichment import render_spot_latest_info

# スポットカード描画の末尾だけで呼ぶ
render_spot_latest_info(destination, visit_date=date_text, city_hint=primary_destination)

"""

from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple

try:
    from data.spot_event_dictionary import (
        SPOT_EVENT_DICTIONARY,
        DICTIONARY_UPDATED_AT,
    )
except Exception:
    SPOT_EVENT_DICTIONARY = []
    DICTIONARY_UPDATED_AT = ""


def _safe_text(value, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _parse_date(value: str) -> Optional[date]:
    text = _safe_text(value)
    if not text or text == "-":
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except Exception:
            continue
    return None


def _normalize_for_match(value: str) -> str:
    text = _safe_text(value).lower()
    text = text.replace("　", " ")
    text = re.sub(r"[（）()\[\]【】「」『』]", " ", text)
    text = re.sub(r"\s+", "", text)
    return text


def _date_in_range(visit_date: Optional[str], valid_from: str, valid_to: str) -> bool:
    target = _parse_date(visit_date or "")
    if target is None:
        return True
    start = _parse_date(valid_from)
    end = _parse_date(valid_to)
    if start and target < start:
        return False
    if end and target > end:
        return False
    return True


def _is_closed_date(visit_date: Optional[str], closed_dates: List[str]) -> bool:
    target = _parse_date(visit_date or "")
    if target is None:
        return False
    for closed in closed_dates or []:
        if _parse_date(closed) == target:
            return True
    return False


def _guess_category(name: str) -> str:
    text = _safe_text(name)
    if any(k in text for k in ["美術館", "博物館", "ミュージアム", "Museum"]):
        return "museum"
    if any(k in text for k in ["劇場", "座", "シアター", "能楽堂", "歌舞伎"]):
        return "theater"
    if any(k in text for k in ["水族館", "Aquarium"]):
        return "aquarium"
    if any(k in text for k in ["動物園", "Zoo"]):
        return "zoo"
    if any(k in text for k in ["公園", "庭園", "Park", "Garden"]):
        return "park"
    if any(k in text for k in ["寺", "神社", "宮"]):
        return "shrine_temple"
    if any(k in text for k in ["城"]):
        return "castle"
    if any(k in text for k in ["タワー", "スカイツリー", "Tower"]):
        return "tower_observation"
    if any(k in text for k in ["ディズニー", "ランド", "ピューロ", "レゴランド", "遊園地"]):
        return "theme_park"
    if any(k in text for k in ["市場", "商店街"]):
        return "market"
    if any(k in text for k in ["SIX", "ヒルズ", "ミッドタウン", "スクエア", "モール", "商業施設"]):
        return "commercial_complex"
    return "other"


def _fallback_query_for_category(name: str, category: str, visit_date: Optional[str]) -> Tuple[str, str]:
    date_part = ""
    parsed = _parse_date(visit_date or "")
    if parsed:
        date_part = f" {parsed.year}年{parsed.month}月{parsed.day}日"

    if category == "museum":
        q = f"{name} 展覧会{date_part}"
        label = "展示情報を調べる"
    elif category == "theater":
        q = f"{name} 公演 演目{date_part}"
        label = "公演情報を調べる"
    elif category in {"commercial_complex", "market", "area"}:
        q = f"{name} イベント{date_part}"
        label = "イベント情報を調べる"
    elif category in {"theme_park", "amusement"}:
        q = f"{name} イベント チケット{date_part}"
        label = "イベント・チケット情報を調べる"
    elif category in {"park", "garden", "nature"}:
        q = f"{name} イベント 開園{date_part}"
        label = "開園・イベント情報を調べる"
    elif category == "shrine_temple":
        q = f"{name} 行事 参拝{date_part}"
        label = "行事・参拝情報を調べる"
    else:
        q = f"{name} 公式 最新情報{date_part}"
        label = "公式情報を調べる"

    url = "https://www.google.com/search?q=" + urllib.parse.quote(q)
    return label, url


def _score_entry(destination: str, entry: Dict[str, object], city_hint: str = "") -> int:
    dest_norm = _normalize_for_match(destination)
    if not dest_norm:
        return 0

    names = [entry.get("spot_name", "")]
    names.extend(entry.get("aliases", []) or [])

    best = 0
    for name in names:
        name_norm = _normalize_for_match(name)
        if not name_norm:
            continue
        if dest_norm == name_norm:
            best = max(best, 100)
        elif name_norm in dest_norm:
            best = max(best, 90)
        elif dest_norm in name_norm:
            best = max(best, 75)

    if best and city_hint:
        city = _safe_text(entry.get("city"))
        if city and city in _safe_text(city_hint):
            best += 5

    return best


def _find_best_entry(destination: str, visit_date: Optional[str] = None, city_hint: str = "") -> Optional[Dict[str, object]]:
    candidates: List[Tuple[int, Dict[str, object]]] = []
    for entry in SPOT_EVENT_DICTIONARY:
        score = _score_entry(destination, entry, city_hint=city_hint)
        if score <= 0:
            continue

        # 期間外でもリンクは使えるが、イベント詳細は出さない。
        if entry.get("type") == "event" and not _date_in_range(visit_date, entry.get("valid_from", ""), entry.get("valid_to", "")):
            score -= 20

        candidates.append((score, entry))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    if candidates[0][0] < 60:
        return None
    return candidates[0][1]


def get_spot_latest_info(destination: str, visit_date: Optional[str] = None, city_hint: str = "") -> Dict[str, object]:
    """
    スポット名と旅行日から、カード表示用の最新情報を返す。
    旅程本体は変更しない。
    """
    name = _safe_text(destination)
    if not name or name == "-":
        return {"found": False, "should_render": False}

    entry = _find_best_entry(name, visit_date=visit_date, city_hint=city_hint)
    category = _guess_category(name)

    if entry:
        closed = _is_closed_date(visit_date, entry.get("closed_dates", []) or [])
        in_range = _date_in_range(visit_date, entry.get("valid_from", ""), entry.get("valid_to", ""))

        details = list(entry.get("details", []) or [])
        status_label = "公式情報確認"
        display_type = "link_only"

        if entry.get("type") == "event" and in_range:
            status_label = "旅行予定日に開催情報あり"
            display_type = "event"

        if entry.get("type") == "event" and not in_range:
            status_label = "旅行予定日は会期外の可能性あり"
            display_type = "out_of_range"

        if closed:
            status_label = "旅行予定日は休演・休館の可能性あり"
            display_type = "closed_warning"
            details = ["この日は休演・休館日に該当する可能性があります。日程変更または公式確認を推奨。"] + details

        return {
            "found": True,
            "should_render": True,
            "display_type": display_type,
            "spot_name": entry.get("spot_name", name),
            "category": entry.get("category", category),
            "status_label": status_label,
            "headline": entry.get("headline", "公式情報確認"),
            "details": details,
            "source_label": entry.get("source_label", "公式情報"),
            "source_url": entry.get("source_url", ""),
            "confidence": entry.get("confidence", "official_link"),
            "fetched_at": DICTIONARY_UPDATED_AT,
        }

    label, url = _fallback_query_for_category(name, category, visit_date)
    return {
        "found": False,
        "should_render": True,
        "display_type": "fallback_search",
        "spot_name": name,
        "category": category,
        "status_label": "公式情報確認",
        "headline": label,
        "details": ["辞書未登録スポットのため、公式情報・イベント情報の確認リンクを表示します。"],
        "source_label": "Google検索",
        "source_url": url,
        "confidence": "search_fallback",
        "fetched_at": DICTIONARY_UPDATED_AT,
    }


def build_spot_latest_info_markdown(info: Dict[str, object]) -> str:
    if not info or not info.get("should_render"):
        return ""

    status = _safe_text(info.get("status_label"), "公式情報確認")
    headline = _safe_text(info.get("headline"), "")
    source_label = _safe_text(info.get("source_label"), "公式情報")
    fetched_at = _safe_text(info.get("fetched_at"), "")

    lines = ["**🔎 最新情報**"]
    if status:
        lines.append(f"- {status}")
    if headline:
        lines.append(f"- {headline}")

    for detail in info.get("details", []) or []:
        detail_text = _safe_text(detail)
        if detail_text:
            lines.append(f"- {detail_text}")

    if source_label:
        lines.append(f"- 情報元: {source_label}")
    if fetched_at:
        lines.append(f"- 情報取得日: {fetched_at}")

    return "\n".join(lines)


def render_spot_latest_info(destination: str, visit_date: Optional[str] = None, city_hint: str = "") -> None:
    """
    Streamlit UI用。
    app.py側ではスポットカード末尾でこれを1回呼ぶだけにする。
    """
    try:
        import streamlit as st
    except Exception:
        return

    info = get_spot_latest_info(destination, visit_date=visit_date, city_hint=city_hint)
    if not info.get("should_render"):
        return

    markdown = build_spot_latest_info_markdown(info)
    if markdown:
        st.markdown(markdown)

    url = _safe_text(info.get("source_url"), "")
    source_label = _safe_text(info.get("source_label"), "公式情報")
    if url:
        st.link_button(f"🔗 {source_label}を見る", url, use_container_width=True)
