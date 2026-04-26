import os
import sys
import urllib.parse
import re
import html
import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

import pandas as pd
import requests
import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))

from orchestration.phase1_generation import Phase1Generator
from orchestration.phase2_structuring import Phase2Structuring
from orchestration.phase3_routing import Phase3Routing
from orchestration.execution_engine import ExecutionEngine
from utils.display_formatters import build_transport_display, clean_address, format_genre, format_purpose
from utils.weather_mock import build_mock_weather_context
from maps.places_api import PlacesAPI
from maps.routes_api import RoutesAPI


# =========================================================
# 【バージョン名】VoyageFlow v6.2.45-simple-mobile-compact-actions
# 【制作日】2026-04-24
# 【前バージョンからの修正内容】
# - サイドバー固定スペースに Gemini transport resolver のA/Bテストパネルを追加
# - A案: 移動時間 + 手段だけをGeminiで推定
# - B案: 経路詳細もGeminiで推定
# - 既存の旅程生成・完成旅程・実行シミュレーションには未接続の診断専用実装
# - 既存のGoogle Directions診断・Routes診断・Uber導線・天候・ホテル・カレンダー機能は変更しない
# - 完成旅程に簡易一覧表示（リンク付き・スポット/移動色分け）を追加
# - 簡易一覧をタブ内追加表示ではなく疑似画面遷移ページとして表示
# - v6.2.40: スポットカード下部に「🔎 最新情報」公式確認リンクを安全に追加
# =========================================================
APP_DISPLAY_NAME = "VoyageFlow - 対話式旅行プランナー"
APP_VERSION_NAME = "v6.2.40-spot-latest-info-links"
APP_UPDATED_DATE = "2026-04-26"


# =========================================================
# ページ設定
# =========================================================
st.set_page_config(
    page_title="VoyageFlow - AI旅行プランナー",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
<style>
    .stTabs [data-baseweb="tab-list"] button { font-size: 15px; padding: 10px 16px; }
    .vf-chat-user {
        padding: 12px 14px; border-radius: 12px; background: #dcecff; color: #10233d;
        margin-bottom: 8px; border: 1px solid #b9d6fb; line-height: 1.55;
    }
    .vf-chat-ai {
        padding: 12px 14px; border-radius: 12px; background: #f2f4f7; color: #1d2633;
        margin-bottom: 8px; border: 1px solid #d8dee8; line-height: 1.55;
    }
    .vf-tip { padding: 10px 12px; border-radius: 10px; background: #f8fff2; color: #19340d; border: 1px solid #d8efc2; }
    .vf-card {
        padding: 12px 14px; border-radius: 12px; margin-bottom: 8px; border: 1px solid #d8d8d8; line-height: 1.55;
    }
    .vf-card * { color: inherit; }
    .vf-card-completed { background: #eeeeee; border-color: #cfcfcf; color: #30343a; }
    .vf-card-current { background: #e7f7e8; border-color: #7cc48a; color: #173721; }
    .vf-card-future { background: #eaf5ff; border-color: #b6d8f7; color: #163047; }
    .vf-card-modified { background: #fff1df; border-color: #f1b25e; color: #4b2b02; }
    .vf-card-note {
        margin-top: 6px; margin-bottom: 8px; padding: 8px 10px; border-radius: 8px;
        background: rgba(255,255,255,0.72); color: #6b4308; border: 1px dashed #d49a43;
    }
    .vf-log-panel {
        padding: 12px 14px; border-radius: 12px; background: rgba(40, 55, 80, 0.08);
        border: 1px solid rgba(120, 150, 190, 0.25); margin-top: 8px; margin-bottom: 12px;
    }
    .vf-log-item {
        padding: 8px 10px; border-radius: 8px; margin-bottom: 6px; background: rgba(255,255,255,0.72);
        color: inherit; border: 1px solid rgba(120, 150, 190, 0.20); line-height: 1.5; word-break: break-word;
    }
    .vf-log-meta { font-size: 12px; opacity: 0.8; }
    textarea::placeholder, input::placeholder { opacity: 0.95 !important; }
    [data-testid="stTextArea"] textarea, [data-testid="stTextInput"] input {
        color: inherit !important; -webkit-text-fill-color: currentColor !important;
    }

    .vf-simple-table-wrap { margin-top: 10px; margin-bottom: 16px; overflow-x: auto; }
    .vf-simple-table { width: 100%; border-collapse: separate; border-spacing: 0 7px; font-size: 14px; }
    .vf-simple-table th {
        text-align: left; padding: 8px 10px; color: #344054; background: #f2f4f7;
        border-top: 1px solid #e4e7ec; border-bottom: 1px solid #e4e7ec; white-space: nowrap;
    }
    .vf-simple-table td { padding: 10px; vertical-align: top; border-top: 1px solid; border-bottom: 1px solid; }
    .vf-simple-table td:first-child, .vf-simple-table th:first-child { border-left: 1px solid; border-radius: 10px 0 0 10px; }
    .vf-simple-table td:last-child, .vf-simple-table th:last-child { border-right: 1px solid; border-radius: 0 10px 10px 0; }
    .vf-simple-row-spot td { background: #eef6ff; border-color: #c8ddf3; color: #17324d; }
    .vf-simple-row-transport td { background: #fff7e8; border-color: #f0d39a; color: #4a3310; }
    .vf-simple-row-hotel td { background: #f1f8ee; border-color: #cde6c5; color: #1f3c1b; }
    .vf-simple-row-cancelled td { background: #eeeeee; border-color: #d0d5dd; color: #667085; text-decoration: line-through; }
    .vf-simple-main { font-weight: 800; }
    .vf-simple-sub { font-size: 12px; opacity: 0.82; margin-top: 2px; }
    .vf-simple-chip { display: inline-block; padding: 2px 8px; border-radius: 999px; background: rgba(255,255,255,0.72); border: 1px solid rgba(0,0,0,0.08); font-size: 12px; font-weight: 700; white-space: nowrap; }
    .vf-simple-action { display: flex; flex-wrap: nowrap; gap: 5px; align-items: center; }
    .vf-simple-btn {
        display: inline-flex; align-items: center; justify-content: center; min-width: 30px; height: 30px;
        padding: 0 7px; border-radius: 9px; text-decoration: none !important;
        background: rgba(255,255,255,0.88); border: 1px solid rgba(0,0,0,0.16); color: inherit !important;
        font-size: 14px; font-weight: 800; white-space: nowrap;
    }
    .vf-simple-btn:hover { background: #ffffff; border-color: rgba(0,0,0,0.28); }

    @media (max-width: 768px) {
        .stTabs [data-baseweb="tab-list"] button { font-size: 13px; padding: 8px 10px; }
        .vf-chat-user, .vf-chat-ai, .vf-card, .vf-log-panel { padding: 12px; }
        .vf-card-note, .vf-log-item { font-size: 14px; }
        h1 { font-size: 2.1rem !important; }
        h2 { font-size: 1.8rem !important; }
        h3 { font-size: 1.4rem !important; }
        .vf-simple-table { font-size: 12px; min-width: 620px; }
        .vf-simple-table th { padding: 6px 7px; }
        .vf-simple-table td { padding: 8px 7px; }
        .vf-simple-chip { font-size: 11px; padding: 2px 7px; }
        .vf-simple-main { font-size: 12px; }
        .vf-simple-btn { min-width: 28px; height: 28px; padding: 0 6px; font-size: 13px; }
    }
</style>
""",
    unsafe_allow_html=True,
)


# =========================================================
# 天候API（Open-Meteo） + モック fallback
# NOTE:
# - ユーザーにはAPIの生JSONではなく、人が確認しやすい外部サイトへの日付連動リンクを見せる。
# - API取得URLは開発者向けに折りたたみ表示へ残す。
# =========================================================
_WEATHER_CODE_LABELS = {
    0: "快晴", 1: "晴れ", 2: "一部くもり", 3: "くもり",
    45: "霧", 48: "着氷性の霧",
    51: "弱い霧雨", 53: "霧雨", 55: "強い霧雨",
    61: "弱い雨", 63: "雨", 65: "強い雨",
    71: "弱い雪", 73: "雪", 75: "大雪",
    80: "にわか雨", 81: "強いにわか雨", 82: "激しいにわか雨",
    95: "雷雨", 96: "雷雨", 99: "激しい雷雨",
}


def _weather_code_label(code: int) -> str:
    try:
        return _WEATHER_CODE_LABELS.get(int(code), f"天気コード:{code}")
    except Exception:
        return "不明"


def _format_weather_fetch_time() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _build_open_meteo_api_url(base_url: str, params: Dict[str, object]) -> str:
    query = urllib.parse.urlencode(params, doseq=True)
    return f"{base_url}?{query}"


def _build_human_weather_links(place_name: str, start_date_text: str, end_date_text: str) -> Dict[str, str]:
    place = str(place_name or "").strip()
    start_date = str(start_date_text or "").strip()
    end_date = str(end_date_text or "").strip()
    date_part = start_date if start_date == end_date else f"{start_date} {end_date}"
    query = urllib.parse.quote(f"{place} 天気 {date_part}")
    place_query = urllib.parse.quote(place)
    return {
        "google": f"https://www.google.com/search?q={query}",
        "yahoo": f"https://weather.yahoo.co.jp/weather/search/?p={place_query}",
    }


def _guess_trip_end_date(planning_state: Dict[str, object], start_date_text: str) -> str:
    try:
        start_date = datetime.strptime(start_date_text, "%Y-%m-%d").date()
    except Exception:
        return start_date_text
    trip_days = max(1, int(planning_state.get("trip_days", 1) or 1))
    end_date = start_date + timedelta(days=trip_days - 1)
    return end_date.strftime("%Y-%m-%d")


def _looks_like_weather_target(value: str, departure_name: str, return_name: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if text in {str(departure_name or '').strip(), str(return_name or '').strip()}:
        return False
    lowered = text.lower()
    blocked = [
        "hotel", "ホテル", "宿", "空港", "airport", "station", "駅", "新幹線", "かがやき",
        "到着", "出発", "移動", "flight", "フライト", "航空便", "搭乗", "チェックイン"
    ]
    return not any(token in lowered for token in blocked)


def _infer_weather_target_place(planning_state: Dict[str, object]) -> str:
    primary_destination = safe_text(planning_state.get("primary_destination"), "")
    departure_name = safe_text(planning_state.get("departure_place"), "")
    return_name = safe_text(planning_state.get("return_place"), "")
    if _looks_like_weather_target(primary_destination, departure_name, return_name):
        return primary_destination

    for key in ("df_phase3", "df_phase2"):
        df = st.session_state.get(key)
        if isinstance(df, pd.DataFrame) and not df.empty:
            candidates = []
            for _, row in df.iterrows():
                if bool(row.get("is_transport", False)):
                    continue
                destination = safe_text(row.get("destination"), "")
                if _looks_like_weather_target(destination, departure_name, return_name):
                    candidates.append(destination)
            if candidates:
                # 最頻出の目的地を採用
                return pd.Series(candidates).value_counts().index[0]

    for text_value in [st.session_state.get("trip_plan_draft"), st.session_state.get("trip_plan")]:
        text = str(text_value or "")
        if not text.strip():
            continue
        patterns = [
            r"札幌", r"東京", r"大阪", r"京都", r"名古屋", r"福岡", r"仙台", r"那覇", r"函館", r"小樽"
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)

    return primary_destination or return_name or departure_name


@st.cache_data(ttl=60 * 60)
def _weather_geocode(place_name: str) -> Optional[Dict[str, object]]:
    query = str(place_name or "").strip()
    if not query:
        return None
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": query, "count": 1, "language": "ja", "format": "json"}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results") or []
    if not results:
        return None
    row = results[0]
    return {
        "name": row.get("name") or query,
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
        "country": row.get("country", ""),
        "admin1": row.get("admin1", ""),
        "timezone": row.get("timezone") or "Asia/Tokyo",
        "evidence_url": _build_open_meteo_api_url(url, params),
    }


@st.cache_data(ttl=60 * 30)
def _weather_forecast_daily(lat: float, lng: float, timezone_name: str, start_date: str, end_date: str) -> Optional[Dict[str, object]]:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lng,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": timezone_name or "Asia/Tokyo",
        "start_date": start_date,
        "end_date": end_date,
    }
    resp = requests.get(url, params=params, timeout=12)
    resp.raise_for_status()
    data = resp.json()
    data["_evidence_url"] = _build_open_meteo_api_url(url, params)
    return data


def _weather_line_for_day(day_data: Dict[str, object]) -> str:
    label = _weather_code_label(day_data.get("weather_code", -1))
    tmax = day_data.get("tmax")
    tmin = day_data.get("tmin")
    rain = day_data.get("precip")
    temp_text = ""
    if tmax is not None and tmin is not None:
        temp_text = f" / {tmin:.0f}〜{tmax:.0f}℃"
    rain_text = ""
    if rain is not None:
        rain_text = f" / 降水確率 {int(rain)}%"
    return f"{day_data.get('date')}: {label}{temp_text}{rain_text}"


def _build_mock_weather_context_with_reason(planning_state: Dict[str, object], reason: str) -> Dict[str, object]:
    ctx = build_mock_weather_context(planning_state)
    ctx["mode_label"] = "参考値"
    ctx["source_name"] = "参考データ"
    ctx["source_type"] = "fallback"
    ctx["fetched_at"] = _format_weather_fetch_time()
    ctx["evidence_url"] = ""
    ctx["api_evidence_url"] = ""
    ctx["human_weather_links"] = _build_human_weather_links(
        str(ctx.get("destination_label") or planning_state.get("primary_destination") or planning_state.get("return_place") or planning_state.get("departure_place") or ""),
        str(ctx.get("date_range_label") or planning_state.get("start_date") or ""),
        str(ctx.get("date_range_label") or planning_state.get("start_date") or ""),
    )
    ctx["fallback_reason"] = reason
    return ctx


def _build_live_weather_context(planning_state: Dict[str, object], context_label: str = "plan") -> Optional[Dict[str, object]]:
    start_date_text = safe_text(planning_state.get("start_date"), "")
    if not start_date_text:
        return None
    try:
        start_date = datetime.strptime(start_date_text, "%Y-%m-%d").date()
    except Exception:
        return None

    today = datetime.now().date()
    day_offset = (start_date - today).days

    # NOTE:
    # Open-Meteo無料予報の範囲外は「参考値」に落とす。
    # 実予報取得できたときは、絶対にモック表示文言を混ぜない。
    if day_offset < 0 or day_offset > 7:
        return None

    destination_name = _infer_weather_target_place(planning_state)
    departure_name = safe_text(planning_state.get("departure_place"), "")
    if not destination_name:
        return None

    end_date_text = _guess_trip_end_date(planning_state, start_date_text)

    try:
        dest_geo = _weather_geocode(destination_name)
        dep_geo = _weather_geocode(departure_name) if departure_name else None
        if not dest_geo or dest_geo.get("latitude") is None or dest_geo.get("longitude") is None:
            return None

        tz_name = str(dest_geo.get("timezone") or "Asia/Tokyo")
        daily_raw = _weather_forecast_daily(
            float(dest_geo["latitude"]),
            float(dest_geo["longitude"]),
            tz_name,
            start_date_text,
            end_date_text,
        )
        daily = daily_raw.get("daily") or {}
        if not daily or not daily.get("time"):
            return None

        rows = []
        for idx, date_value in enumerate(daily.get("time", [])):
            rows.append({
                "date": str(date_value),
                "weather_code": (daily.get("weather_code") or [None])[idx],
                "tmax": (daily.get("temperature_2m_max") or [None])[idx],
                "tmin": (daily.get("temperature_2m_min") or [None])[idx],
                "precip": (daily.get("precipitation_probability_max") or [None])[idx],
            })
        if not rows:
            return None

        first_row = rows[0]
        detail_lines = [_weather_line_for_day(row) for row in rows]
        headline = f"{destination_name}の天気: {_weather_code_label(first_row['weather_code'])}"
        if len(rows) == 1:
            summary = (
                f"{first_row['date']} の {destination_name} は {_weather_code_label(first_row['weather_code'])}、"
                f"{first_row['tmin']:.0f}〜{first_row['tmax']:.0f}℃、降水確率 {int(first_row['precip'])}% の見込みです。"
            )
        else:
            summary = f"{destination_name} の {start_date_text} 〜 {end_date_text} の実予報です。日別の見立ては下記を確認してください。"

        gap_advice = "出発地との大きな差はなさそうです。"
        dep_label = departure_name or "出発地"
        if dep_geo and dep_geo.get("latitude") is not None and dep_geo.get("longitude") is not None:
            dep_daily_raw = _weather_forecast_daily(
                float(dep_geo["latitude"]),
                float(dep_geo["longitude"]),
                str(dep_geo.get("timezone") or tz_name),
                start_date_text,
                start_date_text,
            )
            dep_daily = dep_daily_raw.get("daily") or {}
            if dep_daily and dep_daily.get("temperature_2m_max"):
                dep_tmax = dep_daily.get("temperature_2m_max", [None])[0]
                if dep_tmax is not None and first_row['tmax'] is not None:
                    diff = float(first_row['tmax']) - float(dep_tmax)
                    if abs(diff) >= 4:
                        direction = "暖かい" if diff > 0 else "涼しい"
                        gap_advice = f"到着地は出発地より {abs(diff):.0f}℃ほど{direction}見込みです。服装を調整してください。"

        first_precip = int(first_row.get('precip') or 0)
        packing = "折りたたみ傘と防水性のある靴があると安心です。" if first_precip >= 40 else "薄手の羽織りがあると安心です。"
        execution_hint = "雨予報が強い日は屋外スポットの入替候補を提案できます。" if any(int(r.get('precip') or 0) >= 40 for r in rows) else "大きな雨予報がなければそのまま進行しやすい見込みです。"

        evidence_url = str(daily_raw.get("_evidence_url") or "")
        human_weather_links = _build_human_weather_links(destination_name, start_date_text, end_date_text)
        return {
            "mode_label": "実予報",
            "source_name": "Open-Meteo",
            "source_type": "api_success",
            "date_range_label": start_date_text if start_date_text == end_date_text else f"{start_date_text} 〜 {end_date_text}",
            "headline": headline,
            "summary": summary,
            "detail_lines": detail_lines,
            "packing": packing,
            "departure_label": dep_label,
            "destination_label": destination_name,
            "gap_advice": gap_advice,
            "execution_hint": execution_hint,
            "fetched_at": _format_weather_fetch_time(),
            "evidence_url": human_weather_links.get("google", ""),
            "api_evidence_url": evidence_url,
            "human_weather_links": human_weather_links,
            "fallback_reason": "",
        }
    except Exception as e:
        log_event("天候API", f"実天気取得に失敗したため参考値へfallback: {e}", level="warning")
        return None


def _get_weather_context(planning_state: Dict[str, object], context_label: str = "plan") -> Dict[str, object]:
    start_date_text = safe_text(planning_state.get("start_date"), "")
    if start_date_text:
        try:
            start_date = datetime.strptime(start_date_text, "%Y-%m-%d").date()
            day_offset = (start_date - datetime.now().date()).days
            if day_offset < 0 or day_offset > 7:
                return _build_mock_weather_context_with_reason(planning_state, "予報対象外の日付のため参考値を表示しています。")
        except Exception:
            pass

    live = _build_live_weather_context(planning_state, context_label=context_label)
    if live:
        return live
    return _build_mock_weather_context_with_reason(planning_state, "天候APIの取得に失敗したため参考値を表示しています。")


def render_mock_weather_panel(planning_state: Dict[str, object], context_label: str = "plan") -> None:
    weather_context = _get_weather_context(planning_state, context_label=context_label)
    mode_label = safe_text(weather_context.get("mode_label"), "参考値")
    fallback_reason = safe_text(weather_context.get("fallback_reason"), "")
    source_name = safe_text(weather_context.get("source_name"), "-")
    source_type = safe_text(weather_context.get("source_type"), "")
    fetched_at = safe_text(weather_context.get("fetched_at"), "-")
    evidence_url = safe_text(weather_context.get("evidence_url"), "")

    with st.container():
        st.markdown("### 🌤️ 天候メモ")
        st.caption(f"天気取得: {mode_label} / 対象日: {weather_context['date_range_label']} / 対象地: {weather_context['destination_label']}")
        st.info(f"**{weather_context['headline']}**\n\n{weather_context['summary']}")

        meta1, meta2 = st.columns([2, 1])
        with meta1:
            if source_type == "api_success":
                st.write(f"- 取得元: {source_name}")
            else:
                st.write("- 表示種別: 参考値")
            st.write(f"- 取得時刻: {fetched_at}")
            if fallback_reason and fallback_reason != '-':
                st.write(f"- 補足: {fallback_reason}")
        with meta2:
            if evidence_url and evidence_url != '-':
                st.link_button("🔗 予報の根拠を見る", evidence_url, use_container_width=True)

        d1, d2 = st.columns(2)
        with d1:
            st.markdown("**気象の見立て**")
            for line in weather_context["detail_lines"]:
                st.write(f"- {line}")
            st.write(f"- 服装メモ: {weather_context['packing']}")
        with d2:
            st.markdown("**移動・地域差アドバイス**")
            st.write(f"- 出発地: {weather_context['departure_label']}")
            st.write(f"- 到着地: {weather_context['destination_label']}")
            st.write(f"- 差分メモ: {weather_context['gap_advice']}")
            if context_label == "execution":
                st.write(f"- 実行中メモ: {weather_context['execution_hint']}")


def build_weather_event_detail(planning_state: Dict[str, object]) -> str:
    weather_context = _get_weather_context(planning_state, context_label="execution")
    summary = str(weather_context.get("summary", "") or "")
    gap_advice = str(weather_context.get("gap_advice", "") or "")
    execution_hint = str(weather_context.get("execution_hint", "") or "")
    detail_lines = weather_context.get("detail_lines", [])
    rain_like = any("雨" in str(line) or "スコール" in str(line) for line in detail_lines)

    base_text = "次は屋外の予定だが、今は天候が悪い。必要なら屋内へ変更し、徒歩移動ならタクシーも提案して。"
    if rain_like:
        base_text = "次は屋外の予定だが、今は雨の想定。必要なら屋内へ変更し、徒歩移動ならタクシーも提案して。"

    parts = [base_text]
    if summary:
        parts.append(f"想定メモ: {summary}")
    if gap_advice:
        parts.append(f"地域差メモ: {gap_advice}")
    if execution_hint:
        parts.append(f"実行中メモ: {execution_hint}")

    return " ".join(part for part in parts if part).strip()

# =========================================================
# 初期化
# =========================================================
def init_session_state() -> None:
    defaults = {
        "temperature": 0.7,
        "debug_mode": False,

        "planning_state": {
            "departure_place": "福井駅",
            "return_place": "福井駅",
            "departure_time": "09:00",
            "start_date": (datetime.now().date() + timedelta(days=7)).strftime("%Y-%m-%d"),
            "trip_days": 2,
            "transport_style": "自動（おすすめ）",
            "budget_style": "普通",
            "hotel_required": True,
            "primary_destination": "",
            "conversation_notes": [],
            "revision_requests": [],
        },
        "chat_history": [],
        "advisor_question_index": 0,
        "advisor_done": False,
        "pending_confirmation": None,
        "pending_ambiguity": None,

        "phase1_prompt_text": "",
        "trip_plan_draft": None,
        "trip_plan": None,
        "df_phase2": None,
        "df_phase3": None,
        "plan_approved": False,

        "execution_engine": None,
        "event_result": None,

        "show_delay_dialog": False,
        "show_weather_dialog": False,
        "show_mood_dialog": False,
        "show_cancel_dialog": False,

        "transport_decision_locked": False,

        # タブ制御
        "active_tab": "travel_consultation",
        "app_logs": [],
        "resolved_conditions": {},
        "replan_preview_draft": None,
        "replan_preview_request": "",
        "replan_preview_source": "",
        "replan_error": "",
        "hide_completed_plan": False,
        "hide_cancelled_plan": False,
        "hide_completed_execution": False,
        "hide_cancelled_execution": False,
        "validation_agent_result": None,
        "validation_agent_raw": "",
        "validation_autofix_summary": [],
        "validation_time_overlap_candidates": [],
        "validation_source_plan_text": "",
        "validation_source_itinerary_text": "",
        "simple_itinerary_page_mode": False,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_session_state()


# =========================================================
# ヘルパー
# =========================================================
def safe_text(value, default: str = "-") -> str:
    if value is None:
        return default
    if isinstance(value, float) and pd.isna(value):
        return default
    text = str(value).strip()
    return text if text else default






# =========================================================
# 修正箇所: Googleカレンダー同期ヘルパー
# - 完成旅程から Google Calendar 登録リンク / ICS 出力を行う
# - OAuth は使わず、まずは安全な同期導線に限定
# =========================================================
def _parse_itinerary_datetime(date_text: str, time_text: str) -> Optional[datetime]:
    date_value = str(date_text or "").strip()
    time_value = str(time_text or "").strip()
    if not date_value or not time_value or time_value == "-":
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(f"{date_value} {time_value}", fmt)
        except Exception:
            continue
    return None


def _calendar_end_datetime_from_row(row: Dict[str, object]) -> Optional[datetime]:
    start_dt = _parse_itinerary_datetime(safe_text(row.get("date"), ""), safe_text(row.get("start_time"), ""))
    if start_dt is None:
        return None

    explicit_end = _parse_itinerary_datetime(safe_text(row.get("date"), ""), safe_text(row.get("end_time"), ""))
    if explicit_end and explicit_end > start_dt:
        return explicit_end

    duration_minutes = row.get("duration_minutes")
    if pd.notna(duration_minutes):
        try:
            minutes = max(1, int(float(duration_minutes)))
            return start_dt + timedelta(minutes=minutes)
        except Exception:
            pass

    stay_minutes = row.get("stay_minutes")
    if pd.notna(stay_minutes):
        try:
            minutes = max(1, int(float(stay_minutes)))
            return start_dt + timedelta(minutes=minutes)
        except Exception:
            pass

    return start_dt + timedelta(minutes=60)


def _calendar_title_from_row(row: Dict[str, object]) -> str:
    day_label = f"Day{int(row.get('day'))}" if pd.notna(row.get('day')) else "旅程"
    purpose_raw = safe_text(row.get("purpose"), "")
    purpose = format_purpose(purpose_raw) if purpose_raw and purpose_raw != "-" else "予定"
    destination = safe_text(row.get("destination"), "予定")
    if purpose in {"出発", "到着", "食事", "買い物", "観光・見学", "宿泊"}:
        return f"{day_label} {purpose}：{destination}"
    return f"{day_label} {destination}"


def _calendar_rows_from_itinerary(df: pd.DataFrame) -> List[Dict[str, object]]:
    if df is None or df.empty:
        return []

    rows: List[Dict[str, object]] = []
    normalized = df.sort_values(["day", "sequence"], kind="stable").reset_index(drop=True)
    for _, row in normalized.iterrows():
        row_dict = row.to_dict()
        if bool(row_dict.get("is_transport", False)):
            continue
        destination = safe_text(row_dict.get("destination"), "")
        if not destination:
            continue
        start_dt = _parse_itinerary_datetime(safe_text(row_dict.get("date"), ""), safe_text(row_dict.get("start_time"), ""))
        end_dt = _calendar_end_datetime_from_row(row_dict)
        if start_dt is None or end_dt is None or end_dt <= start_dt:
            continue
        purpose = safe_text(format_purpose(row_dict.get("purpose")), "予定")
        note = safe_text(row_dict.get("one_point"), "")
        rows.append({
            "title": _calendar_title_from_row(row_dict),
            "description": f"VoyageFlow旅程 / 目的: {purpose}" + (f"\n\n{note}" if note and note != "-" else ""),
            "location": destination,
            "start_dt": start_dt,
            "end_dt": end_dt,
            "day": row_dict.get("day"),
            "sequence": row_dict.get("sequence"),
        })
    return rows


def _google_calendar_event_url(event_row: Dict[str, object]) -> str:
    start_dt = event_row["start_dt"].strftime("%Y%m%dT%H%M%S")
    end_dt = event_row["end_dt"].strftime("%Y%m%dT%H%M%S")
    params = {
        "action": "TEMPLATE",
        "text": event_row.get("title", "VoyageFlow旅程"),
        "dates": f"{start_dt}/{end_dt}",
        "ctz": "Asia/Tokyo",
        "details": event_row.get("description", ""),
        "location": event_row.get("location", ""),
    }
    return "https://calendar.google.com/calendar/render?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def _escape_ics_text(value: str) -> str:
    text = str(value or "")
    text = text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    text = text.replace("\n", "\\n")
    return text


def _ics_content_from_rows(event_rows: List[Dict[str, object]]) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//VoyageFlow//Calendar Sync//JA",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:VoyageFlow旅程",
        "X-WR-TIMEZONE:Asia/Tokyo",
    ]
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    for event in event_rows:
        uid = f"{uuid.uuid4()}@voyageflow.local"
        start_local = event["start_dt"].strftime("%Y%m%dT%H%M%S")
        end_local = event["end_dt"].strftime("%Y%m%dT%H%M%S")
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{stamp}",
            f"DTSTART;TZID=Asia/Tokyo:{start_local}",
            f"DTEND;TZID=Asia/Tokyo:{end_local}",
            f"SUMMARY:{_escape_ics_text(event.get('title', 'VoyageFlow旅程'))}",
            f"DESCRIPTION:{_escape_ics_text(event.get('description', ''))}",
            f"LOCATION:{_escape_ics_text(event.get('location', ''))}",
            "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def render_google_calendar_sync_panel(df: pd.DataFrame) -> None:
    event_rows = _calendar_rows_from_itinerary(df)
    st.markdown("### 🗓️ Googleカレンダー同期")
    if not event_rows:
        st.caption("同期できる予定がまだありません。完成旅程を作成してください。")
        return

    st.caption("Googleカレンダーへ個別登録するか、旅程全体を .ics でダウンロードして取り込めます。")
    c1, c2 = st.columns([1, 1])
    with c1:
        ics_text = _ics_content_from_rows(event_rows)
        st.download_button(
            "📥 旅程全体を .ics でダウンロード",
            data=ics_text.encode("utf-8"),
            file_name="voyageflow_itinerary.ics",
            mime="text/calendar",
            use_container_width=True,
        )
    with c2:
        first_url = _google_calendar_event_url(event_rows[0])
        st.link_button("📅 最初の予定をGoogleカレンダーで開く", first_url, use_container_width=True)

    with st.expander("予定ごとのGoogleカレンダー登録リンク", expanded=False):
        for event in event_rows:
            label = f"{event['start_dt'].strftime('%m/%d %H:%M')} - {event['title']}"
            st.link_button(label, _google_calendar_event_url(event), use_container_width=True)


# =========================================================
# 修正箇所: Phase3.5 検証エージェント（実験・指摘のみ）
# =========================================================
def _itinerary_text_for_validation(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return ""

    lines: List[str] = []
    for _, row in df.reset_index(drop=True).iterrows():
        day = safe_text(row.get("day"), "")
        start_time = safe_text(row.get("start_time"), "")
        end_time = safe_text(row.get("end_time"), "")
        destination = safe_text(row.get("destination"), "")
        purpose = safe_text(row.get("purpose"), "")
        is_transport = bool(row.get("is_transport", False))
        transport_mode = safe_text(row.get("transport_mode"), "")
        route_from = safe_text(row.get("route_from"), "")
        route_to = safe_text(row.get("route_to"), "")
        one_point = safe_text(row.get("one_point"), "")

        if is_transport:
            segment = f"Day{day} {start_time}-{end_time} 移動: {route_from or destination} → {route_to or destination}"
            if transport_mode and transport_mode != '-':
                segment += f" / 手段={transport_mode}"
            if one_point and one_point != '-':
                segment += f" / メモ={one_point}"
            lines.append(segment)
        else:
            segment = f"Day{day} {start_time}-{end_time} スポット: {destination}"
            if purpose and purpose != '-':
                segment += f" / 目的={purpose}"
            if one_point and one_point != '-':
                segment += f" / メモ={one_point}"
            lines.append(segment)
    return "\n".join(lines)


def _build_phase35_validation_prompt(natural_plan_text: str, itinerary_text: str) -> str:
    return f"""
あなたは旅行プランの検証担当です。
自然文の旅程案と、完成旅程タイムラインを比較し、違和感のある点だけを指摘してください。

重要ルール:
- 自動で書き換えない
- 指摘と修正提案だけを返す
- 問題がない場合は issues を空配列にする
- 出力は必ずJSONのみ
- 最大5件まで

出力形式:
{{
  "summary": "全体所見",
  "issues": [
    {{
      "type": "duplicate_hotel",
      "severity": "medium",
      "location": "Day1 19:30 新宿のホテル",
      "issue": "抽象ホテルノードと具体ホテル名が重複している",
      "suggestion": "具体ホテル名へ統合し、中間ノードを削除する"
    }}
  ]
}}

比較対象の自然文旅程:
{natural_plan_text}

比較対象の完成旅程:
{itinerary_text}
""".strip()


def run_phase35_validation_agent(natural_plan_text: str, df: pd.DataFrame) -> Dict[str, object]:
    itinerary_text = _itinerary_text_for_validation(df)
    if not natural_plan_text.strip() or not itinerary_text.strip():
        return {"summary": "比較対象が不足しています。", "issues": []}

    prompt = _build_phase35_validation_prompt(natural_plan_text, itinerary_text)
    try:
        generator = Phase1Generator(logger=log_event)
        raw = generator.generate_trip_plan(prompt, temperature=0.0).strip()
        data = _safe_json_extract(raw) or {}
        summary = safe_text(data.get("summary"), "大きな違和感は見つかりませんでした。")
        issues = data.get("issues") if isinstance(data.get("issues"), list) else []
        normalized_issues = []
        for issue in issues[:5]:
            if not isinstance(issue, dict):
                continue
            normalized_issues.append({
                "type": safe_text(issue.get("type"), "issue"),
                "severity": safe_text(issue.get("severity"), "medium"),
                "location": safe_text(issue.get("location"), ""),
                "issue": safe_text(issue.get("issue"), ""),
                "suggestion": safe_text(issue.get("suggestion"), ""),
            })
        return {"summary": summary, "issues": normalized_issues, "raw": raw}
    except Exception as e:
        log_event("Phase3.5検証", f"検証エージェント失敗: {e}", level="warning")
        return {
            "summary": "検証エージェントの実行に失敗しました。今回は完成旅程をそのまま利用してください。",
            "issues": [],
            "raw": str(e),
        }


def render_phase35_validation_panel(natural_plan_text: str, df: pd.DataFrame) -> None:
    st.markdown("### 🧪 Phase3.5 検証エージェント（実験）")
    st.caption("自然文案と完成旅程を比較し、違和感のある点と修正提案だけを表示します。自動修正は行いません。問題があれば、この実験機能を無効扱いにしてすぐ戻せます。")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("🔍 旅程表を検証する", use_container_width=True):
            st.session_state.validation_autofix_summary = []
            st.session_state.validation_time_overlap_candidates = []
            result = run_phase35_validation_agent(natural_plan_text, df)
            st.session_state.validation_agent_result = result
            st.session_state.validation_agent_raw = safe_text(result.get("raw"), "")
            st.session_state.validation_source_plan_text = safe_text(natural_plan_text, "")
            st.session_state.validation_source_itinerary_text = _itinerary_text_for_validation(df)
    with col2:
        if st.button("🧹 検証結果をクリア", use_container_width=True):
            st.session_state.validation_agent_result = None
            st.session_state.validation_agent_raw = ""
            st.session_state.validation_autofix_summary = []
            st.session_state.validation_time_overlap_candidates = []
            st.session_state.validation_source_plan_text = ""
            st.session_state.validation_source_itinerary_text = ""
            st.rerun()

    result = st.session_state.get("validation_agent_result")
    if not result:
        st.info("必要なときだけ実行する確認用パネルです。完成旅程そのものは変更しません。")
        return

    st.info(result.get("summary", "全体所見はありません。"))
    issues = result.get("issues") or []
    if not issues:
        st.success("検証エージェントは大きな違和感を見つけませんでした。")
    else:
        for idx, issue in enumerate(issues, start=1):
            severity = safe_text(issue.get("severity"), "medium").lower()
            box = st.warning if severity in {"high", "medium"} else st.info
            location = safe_text(issue.get("location"), "該当箇所")
            issue_text = safe_text(issue.get("issue"), "")
            suggestion = safe_text(issue.get("suggestion"), "")
            type_name = safe_text(issue.get("type"), "issue")
            box(f"{idx}. [{type_name}] {location}\n\n問題: {issue_text}\n\n修正案: {suggestion}")

    autofix_summary = st.session_state.get("validation_autofix_summary") or []
    if autofix_summary:
        st.markdown("#### Phase3.5 自動反映メモ")
        for note in autofix_summary:
            st.write(f"- {safe_text(note, '')}")

    overlap_candidates = st.session_state.get("validation_time_overlap_candidates") or []
    if overlap_candidates:
        st.markdown("#### time_overlap 修正候補")
        for idx, candidate in enumerate(overlap_candidates, start=1):
            st.write(
                f"{idx}. Day{candidate.get('day')} "
                f"{candidate.get('current_destination')} 終了 {candidate.get('current_end_time')} → "
                f"{candidate.get('next_destination')} 開始 {candidate.get('next_start_time')} "
                f"(重複 {candidate.get('minutes_overlap')}分 / 候補開始 {candidate.get('suggested_next_start_time')})"
            )

    with st.expander("検証エージェントの生出力（デバッグ用）", expanded=False):
        st.code(st.session_state.get("validation_agent_raw", ""), language="json")


def _phase35_normalize_issue_type(issue_type: str) -> str:
    text = safe_text(issue_type, "").strip().lower()
    if text in {"redundant_node", "duplicate_hotel", "duplicate_spot", "redundant_spot", "duplicate_node"}:
        return "redundant_node"
    if text in {"time_overlap", "overlap", "schedule_overlap"}:
        return "time_overlap"
    return text


def _time_to_minutes(value: str) -> Optional[int]:
    text = safe_text(value, "")
    if not text or ":" not in text:
        return None
    try:
        hour, minute = text.split(":", 1)
        return int(hour) * 60 + int(minute)
    except Exception:
        return None


def _find_time_overlap_candidates(df: pd.DataFrame) -> List[Dict[str, object]]:
    candidates: List[Dict[str, object]] = []
    if df is None or df.empty:
        return candidates

    normalized = df.copy()
    if "day" in normalized.columns and "sequence" in normalized.columns:
        normalized = normalized.sort_values(["day", "sequence"], kind="stable").reset_index(drop=True)

    for day, day_df in normalized.groupby("day", sort=True):
        rows = day_df.reset_index(drop=True)
        for idx in range(len(rows) - 1):
            current = rows.iloc[idx]
            nxt = rows.iloc[idx + 1]
            current_end = _time_to_minutes(safe_text(current.get("end_time"), ""))
            next_start = _time_to_minutes(safe_text(nxt.get("start_time"), ""))
            if current_end is None or next_start is None:
                continue
            if next_start < current_end:
                candidates.append({
                    "day": int(day) if pd.notna(day) else day,
                    "current_destination": safe_text(current.get("destination"), ""),
                    "next_destination": safe_text(nxt.get("destination"), ""),
                    "current_end_time": safe_text(current.get("end_time"), ""),
                    "next_start_time": safe_text(nxt.get("start_time"), ""),
                    "suggested_next_start_time": safe_text(current.get("end_time"), ""),
                    "minutes_overlap": current_end - next_start,
                })
    return candidates


def _drop_redundant_nodes_safely(df: pd.DataFrame) -> tuple[pd.DataFrame, List[str]]:
    if df is None or df.empty:
        return df, []

    working = df.copy().reset_index(drop=True)
    notes: List[str] = []

    # 同日の generic hotel と具体ホテルが並ぶ場合だけ generic 側を削除
    drop_indexes = []
    for day, day_df in working.groupby("day", sort=True):
        hotel_rows = []
        for idx, row in day_df.iterrows():
            destination = safe_text(row.get("destination"), "")
            if _is_hotel_like_name(destination):
                hotel_rows.append((idx, destination, _is_generic_hotel_label(destination)))

        if len(hotel_rows) >= 2:
            concrete_exists = any(not is_generic for _, _, is_generic in hotel_rows)
            if concrete_exists:
                for idx, destination, is_generic in hotel_rows:
                    if is_generic:
                        drop_indexes.append(idx)
                        notes.append(f"Day{int(day)} generic hotel を削除: {destination}")

    if drop_indexes:
        working = working.drop(index=sorted(set(drop_indexes))).reset_index(drop=True)

    # 完全重複行のみ削除
    dedupe_subset = [col for col in ["day", "date", "start_time", "end_time", "destination", "purpose", "is_transport", "route_from", "route_to"] if col in working.columns]
    if dedupe_subset:
        before = len(working)
        working = working.drop_duplicates(subset=dedupe_subset, keep="last").reset_index(drop=True)
        removed = before - len(working)
        if removed > 0:
            notes.append(f"完全重複行を {removed} 件削除")

    if "day" in working.columns and "sequence" in working.columns:
        working = working.sort_values(["day", "sequence"], kind="stable").reset_index(drop=True)
        working["sequence"] = working.groupby("day").cumcount() + 1

    return working, notes


def _apply_phase35_safe_autofix(df: pd.DataFrame, validation_result: Dict[str, object]) -> tuple[pd.DataFrame, List[str], List[Dict[str, object]]]:
    working = df.copy().reset_index(drop=True)
    summary_notes: List[str] = []
    overlap_candidates: List[Dict[str, object]] = []

    issues = validation_result.get("issues") if isinstance(validation_result, dict) else []
    if not isinstance(issues, list):
        issues = []

    normalized_issue_types = [_phase35_normalize_issue_type(issue.get("type")) for issue in issues if isinstance(issue, dict)]

    if any(issue_type == "redundant_node" for issue_type in normalized_issue_types):
        working, notes = _drop_redundant_nodes_safely(working)
        summary_notes.extend(notes or ["redundant_node を安全ルールで確認しました。"])

    if any(issue_type == "time_overlap" for issue_type in normalized_issue_types):
        overlap_candidates = _find_time_overlap_candidates(working)
        if overlap_candidates:
            summary_notes.append(f"time_overlap 候補を {len(overlap_candidates)} 件記録")
        else:
            summary_notes.append("time_overlap 指摘はありましたが、候補は検出されませんでした。")

    return working, summary_notes, overlap_candidates


def _normalize_location_for_compare(name: str) -> str:
    # --- 修正箇所: 同一地点移動を抑制するため、駅名・ホテル名比較用の正規化を追加 ---
    text = safe_text(name, "").lower()
    if not text:
        return ""
    text = re.sub(r"（.*?）|\(.*?\)", "", text)
    text = text.replace("　", " ").replace("→", " ")
    removable_tokens = [
        "北陸新幹線", "新幹線", "jr", "駅構内", "周辺", "付近", "エリア",
        "hotel", "the", "宿泊ホテル", "周辺ホテル", "ホテル出発", "チェックイン",
    ]
    for token in removable_tokens:
        text = text.replace(token, "")
    text = re.sub(r"\s+", "", text)
    return text


def _same_effective_place(a: str, b: str) -> bool:
    left = _normalize_location_for_compare(a)
    right = _normalize_location_for_compare(b)
    if not left or not right:
        return False
    return left == right or left in right or right in left


def _contains_hotel_token(name: str) -> bool:
    text = safe_text(name, "")
    lowered = text.lower()
    return any(token in lowered for token in ["hotel", "inn", "resort", "hostel"]) or any(token in text for token in ["ホテル", "旅館"])


def _is_hotel_like_name(name: str) -> bool:
    text = safe_text(name, "")
    if not text:
        return False
    if _is_generic_hotel_label(text):
        return True
    return _contains_hotel_token(text)


def _is_generic_hotel_label(name: str) -> bool:
    text = safe_text(name, "")
    generic_tokens = [
        "宿泊ホテル", "周辺ホテル", "エリア周辺ホテル", "ホテル", "ホテル出発",
        "宿泊先", "ホテル周辺", "ホテルメイン", "おすすめホテル"
    ]
    if text in generic_tokens:
        return True
    if text.endswith("周辺ホテル") or text.endswith("エリア周辺ホテル"):
        return True
    return text in {"ホテル", "宿"}


def _is_valid_hotel_row(row: Dict | pd.Series) -> bool:
    destination = safe_text(_row_value(row, "destination", ""), "")
    purpose = safe_text(_row_value(row, "purpose", ""), "").lower()
    genre = safe_text(_row_value(row, "genre", ""), "").lower()
    if not destination:
        return False
    if genre == "hotel":
        return True
    if purpose in {"accommodation", "hotel", "stay", "lodging"}:
        return True
    if _contains_hotel_token(destination):
        return True
    return False


def _is_transport_service_like_destination(name: str) -> bool:
    # --- 修正箇所: 列車・航空便・船便・バス便など、移動手段名そのものの行は独立スポットとして扱わない ---
    text = safe_text(name, "")
    if not text:
        return False
    lowered = text.lower()
    non_ascii_keywords = [
        "新幹線", "かがやき", "はくたか", "のぞみ", "ひかり", "こだま", "つるぎ",
        "サンダーバード", "しらさぎ", "列車", "電車", "航空便", "飛行機", "フライト",
        "フェリー", "客船", "船便", "高速バス", "夜行バス", "バス", "タクシー"
    ]
    ascii_keywords = ["train", "rail", "flight", "air", "ship", "ferry", "bus", "taxi"]
    return any(k in text for k in non_ascii_keywords) or any(k in lowered for k in ascii_keywords)


def _infer_mode_from_service_hint(service_hint: str, fallback_mode: str) -> str:
    # --- 修正箇所: train 専用ではなく、transport 全般の service_hint から mode を推定する ---
    text = safe_text(service_hint, "").lower()
    if any(token in text for token in ["新幹線", "かがやき", "はくたか", "のぞみ", "ひかり", "こだま", "つるぎ", "サンダーバード", "しらさぎ", "列車", "電車", "train", "rail"]):
        return "train"
    if any(token in text for token in ["flight", "air", "フライト", "航空", "飛行機", "便"]):
        return "air"
    if any(token in text for token in ["ship", "ferry", "船", "客船", "フェリー", "船便"]):
        return "ship"
    if any(token in text for token in ["bus", "高速バス", "夜行バス", "バス"]):
        return "bus"
    if any(token in text for token in ["taxi", "タクシー"]):
        return "taxi"
    if any(token in text for token in ["徒歩", "walk"]):
        return "walk"
    return fallback_mode


def _is_transport_bridge_row(row: pd.Series | Dict | None) -> bool:
    # --- 修正箇所: train / flight / ship / bus などを含む transport 行を、前後スポットを橋渡しする行として判定 ---
    if row is None:
        return False
    purpose = safe_text(_row_value(row, "purpose", ""), "").lower()
    genre = safe_text(_row_value(row, "genre", ""), "").lower()
    destination = safe_text(_row_value(row, "destination", ""), "")
    bridge_genres = {"transport", "train", "flight", "air", "ship", "ferry", "bus", "taxi"}
    return purpose == "transport" or genre in bridge_genres or _is_transport_service_like_destination(destination)


def _compose_transport_bridge_hints(bridge_rows: list) -> tuple[str, str]:
    # --- 修正箇所: 複数の transport 行から service_hint / mode_hint を汎用的に組み立てる ---
    service_parts = []
    mode_hint = ""
    for row in bridge_rows:
        destination = safe_text(_row_value(row, "destination", ""), "")
        genre = safe_text(_row_value(row, "genre", ""), "").lower()
        purpose = safe_text(_row_value(row, "purpose", ""), "").lower()
        if destination:
            service_parts.append(destination)
        if not mode_hint:
            mode_hint = _infer_mode_from_service_hint(destination, "")
        if not mode_hint and genre:
            mode_hint = _infer_mode_from_service_hint(genre, "")
        if not mode_hint and purpose:
            mode_hint = _infer_mode_from_service_hint(purpose, "")
    service_hint = " / ".join([part for part in service_parts if part])
    return service_hint, (mode_hint or "train")


def _extract_concrete_hotel_name_from_plan_text(plan_text: str) -> str:
    # --- 修正箇所: Phase1自然文の「宿泊先: ...」から具体ホテル名を強制抽出 ---
    text = str(plan_text or "")
    if not text.strip():
        return ""

    for raw_line in text.splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue
        m = re.search(r"宿泊先\s*[:：]\s*(.+)$", line)
        candidate = ""
        if m:
            candidate = m.group(1).strip()
        elif "ホテル" in line and any(token in line for token in ["宿泊", "チェックイン", "ホテル"]):
            candidate = line.strip()
        if not candidate:
            continue
        candidate = re.sub(r"\s*[（(][^）)]*エリア[^）)]*[）)]\s*$", "", candidate).strip()
        candidate = re.sub(r"\s*[（(][^）)]*周辺[^）)]*[）)]\s*$", "", candidate).strip()
        candidate = re.sub(r"^(宿泊先\s*[:：]\s*)", "", candidate).strip()
        if candidate and not _is_generic_hotel_label(candidate):
            return candidate
    return ""


def _extract_concrete_hotel_name_from_day(day_df: pd.DataFrame) -> str:
    if day_df is None or day_df.empty:
        return ""
    concrete_names = []
    for _, row in day_df.iterrows():
        dest = safe_text(row.get("destination"), "")
        if _is_valid_hotel_row(row) and not _is_generic_hotel_label(dest):
            concrete_names.append(dest)
    # 同日の終盤にある accommodation を優先
    if concrete_names:
        return concrete_names[-1]
    return ""


def _extract_area_hint(name: str) -> str:
    text = safe_text(name, "")
    if not text:
        return ""
    patterns = [
        r"([一-龥ぁ-んァ-ヶA-Za-z]+(?:都|道|府|県))",
        r"([一-龥ぁ-んァ-ヶA-Za-z]+(?:市|区|町|村))",
        r"([一-龥ぁ-んァ-ヶA-Za-z]+エリア)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    for token in ["札幌", "小樽", "函館", "旭川", "東京", "新宿", "渋谷", "銀座", "上野", "浅草", "丸の内", "大阪", "梅田", "難波", "京都", "名古屋", "福井", "金沢", "博多", "福岡", "那覇", "沖縄", "北海道"]:
        if token in text:
            return token
    return ""




def _is_ambiguous_destination_label(name: str) -> bool:
    text = safe_text(name, "")
    if not text:
        return True
    blocked_exact = {"エリア", "周辺", "駅周辺", "観光地", "レストラン", "食事処", "宿泊先"}
    if text in blocked_exact:
        return True
    blocked_suffixes = ["エリア", "周辺"]
    if text in blocked_exact:
        return True
    lowered = text.lower()
    if lowered in {"area", "spot", "restaurant", "hotel area"}:
        return True
    return False


def _repair_ambiguous_destinations(df: pd.DataFrame) -> pd.DataFrame:
    # --- 修正箇所: 「エリア」などの曖昧スポット名を、近傍の具体地名から最低限補う ---
    if df is None or df.empty or "destination" not in df.columns:
        return df
    repaired = df.copy().reset_index(drop=True)
    last_anchor = ""
    for idx in range(len(repaired)):
        dest = safe_text(repaired.at[idx, "destination"], "")
        if not _is_ambiguous_destination_label(dest):
            if not _is_valid_hotel_row(repaired.iloc[idx]):
                last_anchor = dest
            continue

        candidate = ""
        if last_anchor:
            anchor_hint = _extract_area_hint(last_anchor) or last_anchor
            if anchor_hint:
                candidate = f"{anchor_hint}周辺" if anchor_hint == last_anchor else anchor_hint

        if not candidate:
            one_point = safe_text(repaired.at[idx, "one_point"], "")
            anchor_hint = _extract_area_hint(one_point)
            if anchor_hint:
                candidate = anchor_hint

        if candidate:
            log_event("Phase2正規化", f"曖昧destinationを補正: {dest} -> {candidate}", level="info")
            repaired.at[idx, "destination"] = candidate
            if not _is_valid_hotel_row(repaired.iloc[idx]):
                last_anchor = candidate
    return repaired


def _looks_like_meal_time(start_time: str, end_time: str) -> bool:
    start = safe_text(start_time, "")
    end = safe_text(end_time, "")
    if not start:
        return False
    return ("07:00" <= start <= "10:30") or ("11:00" <= start <= "14:30") or ("17:00" <= start <= "21:30") or (end and ("11:30" <= end <= "14:30" or "18:00" <= end <= "22:00"))


def _protect_meal_rows(df: pd.DataFrame) -> pd.DataFrame:
    # --- 修正箇所: shopping系施設でも食事文脈なら purpose=meal を優先保持 ---
    if df is None or df.empty:
        return df
    repaired = df.copy().reset_index(drop=True)
    for idx in range(len(repaired)):
        row = repaired.iloc[idx]
        purpose = safe_text(row.get("purpose"), "").lower()
        genre = safe_text(row.get("genre"), "").lower()
        if purpose in {"meal", "lunch", "dinner", "breakfast"}:
            continue
        if _is_valid_hotel_row(row) or bool(row.get("is_transport", False)):
            continue

        destination = safe_text(row.get("destination"), "")
        one_point = safe_text(row.get("one_point"), "")
        context = f"{destination} {one_point}".lower()
        meal_tokens = ["ランチ", "昼食", "夕食", "朝食", "ディナー", "食事", "グルメ", "レストラン", "カフェ", "喫茶", "フード", "sweets", "cafe"]
        shoppingish = genre in {"shopping", "shopping_area", "market", "department_store", "mall"} or any(token in context for token in ["ショップ", "買い物", "ショッピング", "商業施設"])
        mealish = any(token.lower() in context for token in [t.lower() for t in meal_tokens])
        if mealish and (_looks_like_meal_time(safe_text(row.get("start_time"), ""), safe_text(row.get("end_time"), "")) or shoppingish):
            repaired.at[idx, "purpose"] = "meal"
            if genre in {"shopping", "shopping_area", "market"}:
                repaired.at[idx, "genre"] = "restaurant"
            log_event("Phase2正規化", f"meal行を保護: {destination}", level="info")
    return repaired


def _detect_large_area_change_between_days(prev_day_df: pd.DataFrame, next_day_df: pd.DataFrame) -> bool:
    prev_candidates = [safe_text(row.get("destination"), "") for _, row in prev_day_df.iterrows() if not bool(row.get("is_transport", False)) and not _is_hotel_like_name(safe_text(row.get("destination"), ""))]
    next_candidates = [safe_text(row.get("destination"), "") for _, row in next_day_df.iterrows() if not bool(row.get("is_transport", False)) and not _is_hotel_like_name(safe_text(row.get("destination"), ""))]
    prev_area = next((hint for hint in (_extract_area_hint(v) for v in prev_candidates) if hint), "")
    next_area = next((hint for hint in (_extract_area_hint(v) for v in next_candidates) if hint), "")
    if not prev_area or not next_area:
        return False
    return prev_area != next_area and prev_area not in next_area and next_area not in prev_area




def _looks_like_invalid_itinerary_node_name(name: str) -> bool:
    text = safe_text(name, "")
    if not text:
        return False
    if text.startswith("*"):
        return True
    if re.match(r"^\*?\s*\d{1,2}:\d{2}\s*-\s*", text):
        return True
    return ("ホテル" in text and any(token in text for token in ["到着", "出発", "チェックイン", "旅程", "Day"]))


def _strip_itinerary_prefix(name: str) -> str:
    text = safe_text(name, "")
    if not text:
        return ""
    text = text.lstrip("*").strip()
    text = re.sub(r"^\d{1,2}:\d{2}\s*-\s*", "", text).strip()
    text = re.sub(r"^Day\s*\d+\s*", "", text, flags=re.IGNORECASE).strip()
    return text


def _derive_place_label_from_invalid_node(name: str) -> str:
    text = _strip_itinerary_prefix(name)
    if not text:
        return ""
    for pattern in [
        r"(.+?駅)到着",
        r"(.+?駅)出発",
        r"(.+?駅)発",
        r"(.+?駅)着",
        r"(.+?空港)到着",
        r"(.+?空港)出発",
        r"(.+?空港)発",
        r"(.+?空港)着",
        r"(.+?)(?:到着|出発|チェックイン)",
    ]:
        m = re.search(pattern, text)
        if m:
            candidate = safe_text(m.group(1), "")
            if candidate:
                return candidate
    area_hint = _extract_area_hint(text)
    return area_hint or text


def _derive_safe_hotel_label(name: str) -> str:
    place = _derive_place_label_from_invalid_node(name)
    if not place:
        return "周辺ホテル"
    if _contains_hotel_token(place):
        return place
    if place.endswith("周辺ホテル"):
        return place
    return f"{place}周辺ホテル"


def _normalize_invalid_node_names(df: pd.DataFrame, planning_state: Dict) -> pd.DataFrame:
    # --- 修正箇所: 自然文の行見出しが destination に混入した場合だけ、安全に正規化 ---
    if df is None or df.empty or "destination" not in df.columns:
        return df

    normalized = df.copy().reset_index(drop=True)
    for idx in range(len(normalized)):
        destination = safe_text(normalized.at[idx, "destination"], "")
        if not _looks_like_invalid_itinerary_node_name(destination):
            continue

        purpose = safe_text(normalized.at[idx, "purpose"], "").lower()
        genre = safe_text(normalized.at[idx, "genre"], "").lower()
        day = int(normalized.at[idx, "day"]) if "day" in normalized.columns and pd.notna(normalized.at[idx, "day"]) else 1

        replacement = ""
        if purpose in {"hotel", "accommodation", "stay", "lodging", "departure"} or genre == "hotel" or _contains_hotel_token(destination):
            replacement = _derive_safe_hotel_label(destination)
        else:
            replacement = _derive_place_label_from_invalid_node(destination)

        replacement = safe_text(replacement, "")
        if replacement and replacement != destination:
            log_event("Phase2正規化", f"invalid node名を補正: {destination} -> {replacement} (Day{day})", level="info")
            normalized.at[idx, "destination"] = replacement

    return normalized


def _trim_rows_after_terminal_return(df: pd.DataFrame, planning_state: Dict[str, object]) -> pd.DataFrame:
    # --- 修正箇所: 最終日の帰着地到着後に混入した後続ノードを安全に打ち切る ---
    if df is None or df.empty or "day" not in df.columns or "destination" not in df.columns:
        return df

    return_place = safe_text(planning_state.get("return_place"), "")
    if not return_place:
        return df

    trimmed = df.copy().reset_index(drop=True)
    final_day = int(trimmed["day"].dropna().astype(int).max())
    final_day_mask = trimmed["day"].astype(int) == final_day
    final_day_df = trimmed.loc[final_day_mask].sort_values("sequence", kind="stable").reset_index()
    if final_day_df.empty:
        return trimmed

    arrival_like_purposes = {"arrival", "return", "goal", "finish", "end", "home"}
    terminal_original_index = None

    for _, row in final_day_df.iterrows():
        if bool(row.get("is_transport", False)):
            continue
        destination = safe_text(row.get("destination"), "")
        purpose = safe_text(row.get("purpose"), "").lower()
        if not _same_effective_place(destination, return_place):
            continue
        if purpose in arrival_like_purposes or purpose == "arrival":
            terminal_original_index = int(row["index"])
            break

    if terminal_original_index is None:
        return trimmed

    later_rows = trimmed.loc[(trimmed["day"].astype(int) == final_day) & (trimmed.index > terminal_original_index)]
    if later_rows.empty:
        return trimmed

    removed_preview = ", ".join([safe_text(v, "") for v in later_rows["destination"].tolist()[:3]])
    log_event("Phase3正規化", f"最終帰着後の後続ノードを打ち切り: Day{final_day} / {removed_preview}", level="warning")
    trimmed = trimmed.loc[~((trimmed["day"].astype(int) == final_day) & (trimmed.index > terminal_original_index))].reset_index(drop=True)
    return trimmed


def _resolve_canonical_hotel_by_day(normalized: pd.DataFrame) -> Dict[int, str]:
    canonical_hotel_by_day: Dict[int, str] = {}
    days = sorted(normalized["day"].dropna().astype(int).unique().tolist()) if "day" in normalized.columns else []

    phase1_hotel_name = _extract_concrete_hotel_name_from_plan_text(
        st.session_state.get("trip_plan") or st.session_state.get("trip_plan_draft") or ""
    )

    explicit_by_day: Dict[int, str] = {}
    for day in days:
        day_df = normalized[normalized["day"] == day].sort_values("sequence", kind="stable").reset_index(drop=True)
        explicit_name = _extract_concrete_hotel_name_from_day(day_df)
        if explicit_name:
            explicit_by_day[day] = explicit_name
            canonical_hotel_by_day[day] = explicit_name

    if phase1_hotel_name:
        first_day = days[0] if days else 1
        canonical_hotel_by_day.setdefault(first_day, phase1_hotel_name)
        explicit_by_day.setdefault(first_day, phase1_hotel_name)

    for day in days:
        if day in canonical_hotel_by_day:
            continue
        prev_day = day - 1
        next_day = day + 1
        if prev_day in explicit_by_day:
            prev_day_df = normalized[normalized["day"] == prev_day].reset_index(drop=True)
            cur_day_df = normalized[normalized["day"] == day].reset_index(drop=True)
            if not _detect_large_area_change_between_days(prev_day_df, cur_day_df):
                canonical_hotel_by_day[day] = explicit_by_day[prev_day]
                continue
        if next_day in explicit_by_day:
            cur_day_df = normalized[normalized["day"] == day].reset_index(drop=True)
            next_day_df = normalized[normalized["day"] == next_day].reset_index(drop=True)
            if not _detect_large_area_change_between_days(cur_day_df, next_day_df):
                canonical_hotel_by_day[day] = explicit_by_day[next_day]
                continue
        if phase1_hotel_name:
            canonical_hotel_by_day[day] = phase1_hotel_name

    return canonical_hotel_by_day


def _propagate_hotel_names(df: pd.DataFrame, planning_state: Dict) -> pd.DataFrame:
    # --- 修正箇所: ホテル正本を日単位で安定保持し、generic ホテル表現だけを具体名へ置換 ---
    if df is None or df.empty:
        return df
    normalized = df.copy().reset_index(drop=True)
    if "day" not in normalized.columns:
        return normalized

    canonical_hotel_by_day = _resolve_canonical_hotel_by_day(normalized)
    days = sorted(normalized["day"].dropna().astype(int).unique().tolist())

    for day in days:
        hotel_name = canonical_hotel_by_day.get(day, "")
        if not hotel_name:
            continue
        same_day_generic_mask = (normalized["day"] == day) & normalized.apply(
            lambda row: _is_hotel_like_name(safe_text(row.get("destination"), "")) and _is_generic_hotel_label(safe_text(row.get("destination"), "")),
            axis=1,
        )
        if same_day_generic_mask.any():
            normalized.loc[same_day_generic_mask, "destination"] = hotel_name

    st.session_state["confirmed_hotel_by_day"] = canonical_hotel_by_day
    return normalized


def parse_route_diagnostic_departure_iso(departure_text: str) -> str:
    value = str(departure_text or "").strip()
    if not value:
        return ""

    # すでにタイムゾーン付き or UTC終端ならそのまま返す
    if re.search(r"(Z|[+-]\d{2}:\d{2})$", value):
        return value

    dt = None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(value, fmt)
            break
        except ValueError:
            continue

    if dt is None:
        return value

    # ユーザー前提は日本時間
    return dt.strftime("%Y-%m-%dT%H:%M:%S+09:00")


def build_route_diagnostic_body(origin: list[float], destination: list[float], mode: str, departure_text: str) -> Dict[str, object]:
    travel_mode_map = {
        "train": "TRANSIT",
        "walk": "WALK",
        "car": "DRIVE",
        "taxi": "DRIVE",
        "bike": "BICYCLE",
    }
    departure_iso = parse_route_diagnostic_departure_iso(departure_text)
    body: Dict[str, object] = {
        "origin": {
            "location": {
                "latLng": {
                    "latitude": float(origin[0]),
                    "longitude": float(origin[1]),
                }
            }
        },
        "destination": {
            "location": {
                "latLng": {
                    "latitude": float(destination[0]),
                    "longitude": float(destination[1]),
                }
            }
        },
        "travelMode": travel_mode_map.get(str(mode or "").lower(), "TRANSIT"),
        "computeAlternativeRoutes": False,
        "routeModifiers": {
            "avoidTolls": False,
            "avoidHighways": False,
            "avoidFerries": False,
        },
    }
    if departure_iso:
        body["departureTime"] = departure_iso
    return body



def format_phase1_preview_text(plan_text: str) -> str:
    if not plan_text:
        return ""

    import re
    import html

    text = html.escape(plan_text)

    text = re.sub(
        r"^【(.*?)】(.*)$",
        r"<div style='font-size:1.9rem;font-weight:800;margin:18px 0 10px 0;'>【\1】\2</div>",
        text,
        flags=re.MULTILINE,
    )

    text = re.sub(
        r"^テーマ:\s*(.*)$",
        r"<div style='margin-bottom:12px;'>テーマ：\1</div>",
        text,
        flags=re.MULTILINE,
    )

    text = re.sub(
        r"^\*\s*(\d{1,2}:\d{2}\s*-\s*.*)$",
        r"<div style='margin:12px 0 4px 0;font-weight:800;color:#2563eb;'>\1</div>",
        text,
        flags=re.MULTILINE,
    )

    text = re.sub(
        r"^\s*-\s*目的:\s*(.*)$",
        r"<div style='margin-left:16px;'>目的: \1</div>",
        text,
        flags=re.MULTILINE,
    )

    text = re.sub(
        r"^\s*-\s*滞在時間:\s*(.*)$",
        r"<div style='margin-left:16px;'>🕒 \1</div>",
        text,
        flags=re.MULTILINE,
    )

    text = re.sub(
        r"^\s*-\s*ワンポイント:\s*(.*)$",
        r"<div style='margin-left:16px;'>\1</div>",
        text,
        flags=re.MULTILINE,
    )

    text = re.sub(
        r"\*\*(.*?)\*\*",
        r"<strong>\1</strong>",
        text,
    )

    return text

def log_event(stage: str, message: str, level: str = "info") -> None:
    logs = st.session_state.get("app_logs", [])
    logs.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "stage": stage,
        "level": level,
        "message": str(message),
    })
    st.session_state.app_logs = logs[-200:]


def clear_logs() -> None:
    st.session_state.app_logs = []


def _safe_json_extract(text: str) -> Optional[Dict[str, object]]:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        pass
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    from math import radians, sin, cos, asin, sqrt
    lon1, lat1, lon2, lat2 = map(radians, [lng1, lat1, lng2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    return 6371 * c


def _estimate_minutes_from_distance(distance_km: float, mode: str) -> int:
    mode_key = str(mode or "walk").lower()
    km = max(float(distance_km or 0), 0.1)

    if mode_key in {"walk", "walking", "徒歩"}:
        return max(5, int(round((km / 4.5) * 60)))

    if mode_key in {"bike", "bicycle", "自転車"}:
        return max(3, int(round((km / 15.0) * 60)))

    if mode_key in {"train", "transit", "電車"}:
        if km < 3:
            return max(8, int(round((km / 18.0) * 60)) + 5)
        if km < 30:
            return max(12, int(round((km / 30.0) * 60)) + 8)
        if km < 120:
            return max(25, int(round((km / 70.0) * 60)) + 12)
        if km < 250:
            return max(75, int(round((km / 110.0) * 60)) + 20)
        if km < 600:
            return max(130, int(round((km / 140.0) * 60)) + 30)
        return max(240, int(round((km / 180.0) * 60)) + 45)

    if km < 5:
        speed = 22.0
    elif km < 30:
        speed = 35.0
    elif km < 120:
        speed = 55.0
    elif km < 300:
        speed = 70.0
    else:
        speed = 80.0
    return max(5, int(round((km / speed) * 60)))


def _contains_international_signal(*texts: str) -> bool:
    merged = " ".join(str(t or "") for t in texts).lower()
    keywords = [
        "international", "airport", "airports", "空港", "国際", "海外", "渡航",
        "france", "paris", "london", "new york", "los angeles", "seoul", "taipei",
        "beijing", "shanghai", "hong kong", "bangkok", "singapore", "rome", "milan",
        "sydney", "hawaii", "honolulu", "guam", "berlin", "madrid", "vancouver",
        "パリ", "ロンドン", "ニューヨーク", "ロサンゼルス", "ソウル", "台北", "北京",
        "上海", "香港", "バンコク", "シンガポール", "ローマ", "ミラノ", "シドニー",
        "ハワイ", "ホノルル", "グアム", "ベルリン", "マドリード", "バンクーバー",
        "frankfurt", "amsterdam", "dubai", "istanbul", "san francisco", "toronto",
        "フランクフルト", "アムステルダム", "ドバイ", "イスタンブール", "トロント",
    ]
    return any(k in merged for k in keywords)




def _row_value(row: pd.Series | Dict | None, key: str, default=None):
    if row is None:
        return default
    try:
        if isinstance(row, pd.Series):
            value = row.get(key, default)
        elif isinstance(row, dict):
            value = row.get(key, default)
        else:
            value = getattr(row, key, default)
        return default if value is None else value
    except Exception:
        return default
def _contains_air_travel_signal(*texts: str) -> bool:
    merged = " ".join(str(t or "") for t in texts).lower()
    keywords = [
        "航空", "航空便", "フライト", "搭乗", "出国", "入国", "経由", "乗り継ぎ", "チェックイン",
        "空港", "airport", "flight", "boarding", "terminal", "layover",
        "kmq", "hnd", "nrt", "kix", "itm", "sin", "icn", "tpe", "lax", "jfk", "cdg", "lhr",
    ]
    return any(k in merged for k in keywords)


def _is_air_transport_context(transport_row: pd.Series | Dict, prev_row: pd.Series | Dict, next_row: pd.Series | Dict) -> bool:
    texts = [
        safe_text(_row_value(transport_row, "destination", ""), ""),
        safe_text(_row_value(transport_row, "purpose", ""), ""),
        safe_text(_row_value(transport_row, "genre", ""), ""),
        safe_text(_row_value(transport_row, "one_point", ""), ""),
        safe_text(_row_value(prev_row, "destination", ""), ""),
        safe_text(_row_value(prev_row, "purpose", ""), ""),
        safe_text(_row_value(prev_row, "one_point", ""), ""),
        safe_text(_row_value(next_row, "destination", ""), ""),
        safe_text(_row_value(next_row, "purpose", ""), ""),
        safe_text(_row_value(next_row, "one_point", ""), ""),
    ]
    return _contains_air_travel_signal(*texts)


def _extract_minutes_from_text(*texts: str) -> Optional[int]:
    merged = " ".join(str(t or "") for t in texts)
    if not merged.strip():
        return None
    patterns = [
        r"(\d+)\s*分",
        r"🕒\s*(\d+)\s*分",
        r"約\s*(\d+)\s*分",
        r"(\d+)\s*時間\s*(\d+)\s*分",
        r"約\s*(\d+)\s*時間\s*(\d+)\s*分",
        r"(\d+)\s*時間",
        r"約\s*(\d+)\s*時間",
    ]
    import re as _re
    for pat in patterns:
        m = _re.search(pat, merged)
        if not m:
            continue
        if len(m.groups()) == 2:
            return int(m.group(1))*60 + int(m.group(2))
        return int(m.group(1)) * (60 if "時間" in pat and "分" not in pat else 1)
    return None


def _build_air_transport_estimate(prev_row: pd.Series | Dict, transport_row: pd.Series | Dict, next_row: pd.Series | Dict, departure_date: str, departure_time: str) -> Dict[str, object]:
    prev_texts = [safe_text(_row_value(prev_row, "destination", ""), ""), safe_text(_row_value(prev_row, "purpose", ""), ""), safe_text(_row_value(prev_row, "one_point", ""), "")]
    transport_texts = [safe_text(_row_value(transport_row, "destination", ""), ""), safe_text(_row_value(transport_row, "purpose", ""), ""), safe_text(_row_value(transport_row, "one_point", ""), "")]
    next_texts = [safe_text(_row_value(next_row, "destination", ""), ""), safe_text(_row_value(next_row, "purpose", ""), ""), safe_text(_row_value(next_row, "one_point", ""), "")]
    minutes = _extract_minutes_from_text(*prev_texts, *transport_texts, *next_texts)
    origin_name = safe_text(_row_value(prev_row, "destination", "出発空港"), "出発空港")
    destination_name = safe_text(_row_value(next_row, "destination", "到着空港"), "到着空港")
    if minutes is None:
        if _contains_international_signal(origin_name, destination_name, *transport_texts, *next_texts):
            minutes = 600
            label = "約8〜12時間（推測）"
            note = "国際・航空を含む可能性があるため概算です"
        else:
            minutes = 180
            label = "約2〜4時間（推測）"
            note = "航空移動を含む可能性があるため概算です"
        source = "air_distance_estimate"
    else:
        label = f"約{minutes}分"
        note = "プラン確認の航空移動時間を保持"
        source = "air_plan_preserved"
    return {
        "minutes": minutes,
        "label": label,
        "source": source,
        "note": note,
        "route_from": origin_name,
        "route_to": destination_name,
        "route_line_simple": f"{origin_name} → {destination_name} / ✈️ {label}",
        "route_departure_at": f"{departure_date} {departure_time}".strip(),
        "transport_mode": "air",
    }

def _validate_llm_minutes(distance_km: float, mode: str, minutes: int, origin_name: str, destination_name: str) -> bool:
    mode_key = str(mode or "walk").lower()
    km = max(float(distance_km or 0), 0.1)
    m = int(minutes)
    if m <= 0 or m > 24 * 60:
        return False

    if _contains_international_signal(origin_name, destination_name):
        return False

    if mode_key in {"walk", "walking", "徒歩"}:
        minimum = max(5, int((km / 7.0) * 60))
        maximum = max(minimum, int((km / 2.0) * 60) + 30)
    elif mode_key in {"bike", "bicycle", "自転車"}:
        minimum = max(3, int((km / 25.0) * 60))
        maximum = max(minimum, int((km / 8.0) * 60) + 20)
    elif mode_key in {"train", "transit", "電車"}:
        if km < 5:
            minimum, maximum = 8, 45
        elif km < 50:
            minimum, maximum = 15, 90
        elif km < 150:
            minimum, maximum = 35, 150
        elif km < 350:
            minimum, maximum = 90, 300
        elif km < 700:
            minimum, maximum = 150, 480
        else:
            minimum, maximum = 240, 900
    else:
        if km < 5:
            minimum, maximum = 5, 40
        elif km < 50:
            minimum, maximum = 10, 120
        elif km < 150:
            minimum, maximum = 45, 240
        elif km < 350:
            minimum, maximum = 120, 420
        else:
            minimum, maximum = 180, 900

    return minimum <= m <= maximum


def _build_safe_distance_fallback(distance_km: float, mode: str, origin_name: str, destination_name: str) -> Dict[str, object]:
    mode_key = str(mode or "walk").lower()
    km = max(float(distance_km or 0), 0.1)
    international_like = _contains_international_signal(origin_name, destination_name)

    if international_like:
        if mode_key in {"train", "transit", "電車"}:
            return {"minutes": 480, "label": "約6〜10時間（推測）", "source": "distance_estimate", "note": "国際・航空を含む可能性があるため概算です"}
        return {"minutes": 720, "label": "約8〜14時間（推測）", "source": "distance_estimate", "note": "国際・航空を含む可能性があるため概算です"}

    if mode_key in {"train", "transit", "電車"}:
        if km < 5:
            minutes = _estimate_minutes_from_distance(km, mode_key)
            return {"minutes": minutes, "label": f"約{minutes}分（推測）", "source": "distance_estimate", "note": "近距離の電車移動を距離ベースで推定"}
        if km < 50:
            lo, hi = 20, 70
        elif km < 150:
            lo, hi = 45, 120
        elif km < 350:
            lo, hi = 120, 240
        elif km < 700:
            lo, hi = 180, 420
        else:
            lo, hi = 300, 720
        return {"minutes": int(round((lo + hi) / 2)), "label": f"約{lo}〜{hi}分（推測）", "source": "distance_estimate", "note": "長距離の鉄道移動を距離帯ベースで推定"}

    if mode_key in {"walk", "walking", "徒歩"} and km > 20:
        lo, hi = 240, 999
        return {"minutes": 360, "label": "長距離移動のため要確認（推測表示）", "source": "distance_estimate", "note": "徒歩としては現実的でない長距離のため要確認"}

    minutes = _estimate_minutes_from_distance(km, mode_key)
    if km >= 150 and mode_key in {"car", "drive", "private_car", "rental_car", "taxi", "driving"}:
        lo = max(90, int(round(minutes * 0.8)))
        hi = int(round(minutes * 1.35))
        return {"minutes": int(round((lo + hi) / 2)), "label": f"約{lo}〜{hi}分（推測）", "source": "distance_estimate", "note": "長距離の道路移動を距離帯ベースで推定"}
    return {"minutes": minutes, "label": f"約{minutes}分（推測）", "source": "distance_estimate", "note": "距離ベース推定"}


def _add_minutes_to_clock(start_time: str, minutes: int) -> str:
    value = str(start_time or "").strip()
    if not value:
        return start_time
    try:
        base = datetime.strptime(value, "%H:%M")
        return (base + timedelta(minutes=int(minutes))).strftime("%H:%M")
    except Exception:
        return start_time


def _llm_transport_duration_estimate(
    origin_name: str,
    destination_name: str,
    mode: str,
    departure_date: str,
    departure_time: str,
    distance_km: float,
    origin_lat: float,
    origin_lng: float,
    destination_lat: float,
    destination_lng: float,
) -> Optional[Dict[str, object]]:
    prompt = f"""
あなたは旅行アプリの移動時間推定補助です。

次の移動について、一般的に妥当な『概算移動時間』だけを保守的に推定してください。
不確実なら minutes を null にしてください。長距離は過小評価しないでください。

【重要ルール】
- 路線名・道路名・乗換回数などを、確信がないのに捏造しない
- 断定しすぎず、一般的な目安として答える
- minutes は整数
- confidence は high / medium / low のいずれか
- JSON だけを返す
- 直線距離が長い場合に、都市内移動のような過小な minutes を出さない
- 出せない場合は minutes を null にする

【入力】
- 出発地名: {origin_name}
- 到着地名: {destination_name}
- 移動手段の想定: {mode}
- 出発予定日: {departure_date}
- 出発予定時刻: {departure_time}
- 直線距離km: {distance_km:.2f}
- 出発地座標: {origin_lat}, {origin_lng}
- 到着地座標: {destination_lat}, {destination_lng}

【出力JSON形式】
{{
  "minutes": 25,
  "confidence": "medium",
  "reason": "都市部の主要駅間として一般的な移動時間の目安"
}}

minutes を出せない場合:
{{
  "minutes": null,
  "confidence": "low",
  "reason": "情報不足で妥当な概算を出せない"
}}
""".strip()

    try:
        generator = Phase1Generator(logger=log_event)
        raw = generator.generate_trip_plan(prompt, temperature=0.1).strip()
        data = _safe_json_extract(raw)
        if not data:
            return None
        minutes = data.get("minutes")
        confidence = str(data.get("confidence", "")).lower().strip()
        reason = str(data.get("reason", "")).strip()
        if minutes is None:
            return None
        minutes = int(minutes)
        if minutes <= 0 or minutes > 24 * 60:
            return None
        if confidence not in {"high", "medium", "low"}:
            confidence = "medium"
        return {"minutes": minutes, "confidence": confidence, "reason": reason}
    except Exception as e:
        log_event("移動時間推定", f"LLM概算フォールバック: {e}", level="warning")
        return None


# =========================================================
# 修正箇所: Google Directions API（Legacy）最小導入
# - Routes API の transit ではなく Directions API の transit を局所利用
# - 失敗時は既存のLLM概算/距離推定へ安全にフォールバック
# - Place ID 強制ではなく、まずは既存座標を優先して壊れた destination 文字列の影響を下げる
# =========================================================
def _get_maps_api_key() -> str:
    try:
        key = st.secrets.get("MAPS_API_KEY") or os.getenv("MAPS_API_KEY") or ""
        return str(key).strip()
    except Exception:
        return str(os.getenv("MAPS_API_KEY") or "").strip()


def _normalize_route_query_name(name: str) -> str:
    text = safe_text(name, "")
    if not text:
        return text
    text = re.sub(r"^\*\s*", "", text).strip()
    text = re.sub(r"^\d{1,2}:\d{2}\s*-\s*", "", text).strip()
    text = re.sub(r"[（(].*?[）)]", "", text).strip()
    text = text.replace("到着・ホテルチェックイン", "").replace("ホテルチェックイン", "")
    text = text.replace("到着", "").replace("出発", "")
    text = text.replace("解散", "").replace("集合", "")
    text = re.sub(r"\s+", " ", text).strip(" -・")
    if not text:
        return safe_text(name, "")
    return text


def _build_google_directions_location_query(name: str, lat=None, lng=None) -> str:
    try:
        if lat is not None and lng is not None and not (pd.isna(lat) or pd.isna(lng)):
            return f"{float(lat):.6f},{float(lng):.6f}"
    except Exception:
        pass
    return _normalize_route_query_name(name)


def _google_directions_mode_for_transport(mode: str) -> str:
    key = safe_text(mode, "walk").lower()
    if key in {"train", "transit", "bus", "rail"}:
        return "transit"
    if key in {"car", "taxi", "drive", "driving", "private_car"}:
        return "driving"
    if key in {"bike", "bicycle"}:
        return "bicycling"
    return "walking"


def _parse_google_duration_minutes(duration_text: str) -> Optional[int]:
    text = str(duration_text or "").strip()
    if not text:
        return None
    total = 0
    m = re.search(r"(\d+)\s*day", text)
    if m:
        total += int(m.group(1)) * 24 * 60
    m = re.search(r"(\d+)\s*hour", text)
    if m:
        total += int(m.group(1)) * 60
    mins = re.findall(r"(\d+)\s*min", text)
    if mins:
        total += sum(int(v) for v in mins)
    if total > 0:
        return total
    m = re.search(r"(\d+)", text)
    return int(m.group(1)) if m else None


def _extract_google_transit_summary(steps: list) -> str:
    if not isinstance(steps, list):
        return ""
    parts = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        mode = safe_text(step.get("travel_mode"), "")
        if mode == "TRANSIT":
            detail = step.get("transit_details") or {}
            line = detail.get("line") or {}
            vehicle = (line.get("vehicle") or {}).get("name") or "公共交通"
            name = line.get("short_name") or line.get("name") or ""
            dep = (detail.get("departure_stop") or {}).get("name") or ""
            arr = (detail.get("arrival_stop") or {}).get("name") or ""
            text = f"{vehicle}"
            if name:
                text += f" {name}"
            if dep or arr:
                text += f"（{dep}→{arr}）"
            parts.append(text)
        elif mode == "WALKING":
            parts.append("徒歩")
        elif mode == "DRIVING":
            parts.append("車")
    deduped = []
    for part in parts:
        if part and part not in deduped:
            deduped.append(part)
    return " / ".join(deduped[:3])


def _fetch_google_directions_legacy(origin_query: str, destination_query: str, mode: str, departure_date: str, departure_time: str, return_debug: bool = False):
    api_key = _get_maps_api_key()
    debug_info: Dict[str, object] = {
        "origin_query": origin_query,
        "destination_query": destination_query,
        "requested_mode": mode,
        "api_mode": _google_directions_mode_for_transport(mode),
        "departure_date": departure_date,
        "departure_time": departure_time,
        "has_api_key": bool(api_key),
        "status_code": None,
        "api_status": "",
        "error_message": "",
        "response_text_preview": "",
        "request_params_preview": {},
    }
    if not api_key:
        debug_info["error_message"] = "MAPS_API_KEY が見つかりません"
        return (None, debug_info) if return_debug else None

    directions_mode = _google_directions_mode_for_transport(mode)
    params: Dict[str, object] = {
        "origin": origin_query,
        "destination": destination_query,
        "mode": directions_mode,
        "language": "ja",
        "region": "jp",
        "key": api_key,
    }

    if directions_mode == "transit":
        departure_epoch = None
        raw = f"{safe_text(departure_date, '')} {safe_text(departure_time, '')}".strip()
        for fmt in ("%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M"):
            try:
                departure_epoch = int(datetime.strptime(raw, fmt).timestamp())
                break
            except Exception:
                continue
        if departure_epoch:
            params["departure_time"] = departure_epoch

    debug_info["request_params_preview"] = {
        "origin": params.get("origin"),
        "destination": params.get("destination"),
        "mode": params.get("mode"),
        "language": params.get("language"),
        "region": params.get("region"),
        "departure_time": params.get("departure_time"),
    }

    try:
        resp = requests.get("https://maps.googleapis.com/maps/api/directions/json", params=params, timeout=15)
        debug_info["status_code"] = resp.status_code
        debug_info["response_text_preview"] = (resp.text or "")[:2000]
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        debug_info["error_message"] = str(e)
        log_event(
            "GoogleDirections",
            f"Directions API 呼び出し失敗: {e} / status_code={debug_info.get('status_code')} / body={debug_info.get('response_text_preview', '')[:300]}",
            level="warning",
        )
        return (None, debug_info) if return_debug else None

    status = str(data.get("status") or "")
    debug_info["api_status"] = status
    debug_info["error_message"] = str(data.get("error_message") or "")
    if status != "OK":
        log_event(
            "GoogleDirections",
            f"Directions API status={status} / error={debug_info.get('error_message')} / {origin_query} -> {destination_query} / body={debug_info.get('response_text_preview', '')[:300]}",
            level="warning",
        )
        return (None, debug_info) if return_debug else None

    routes = data.get("routes") or []
    if not routes:
        return None
    route = routes[0]
    legs = route.get("legs") or []
    if not legs:
        return None
    leg = legs[0]
    minutes = None
    if isinstance(leg.get("duration"), dict):
        try:
            minutes = max(1, int(round(int(leg["duration"].get("value", 0)) / 60)))
        except Exception:
            minutes = _parse_google_duration_minutes((leg.get("duration") or {}).get("text", ""))
    if not minutes:
        minutes = _parse_google_duration_minutes((leg.get("duration") or {}).get("text", ""))
    if not minutes:
        return None

    fare = route.get("fare") or {}
    transit_summary = _extract_google_transit_summary(leg.get("steps") or [])
    return {
        "minutes": int(minutes),
        "label": safe_text((leg.get("duration") or {}).get("text"), f"約{int(minutes)}分"),
        "distance_text": safe_text((leg.get("distance") or {}).get("text"), ""),
        "fare_text": safe_text(fare.get("text"), ""),
        "transit_summary": transit_summary,
        "mode": directions_mode,
        "start_address": safe_text(leg.get("start_address"), origin_query),
        "end_address": safe_text(leg.get("end_address"), destination_query),
        "source": "google_directions_legacy",
    }


def _validate_google_route_minutes(distance_km: float, minutes: int, mode: str, origin_name: str, destination_name: str) -> bool:
    if minutes <= 0:
        return False
    mode_key = safe_text(mode, "walk").lower()
    # あまりに非現実な短時間は棄却して既存フォールバックへ戻す
    if distance_km >= 20 and minutes < 20:
        return False
    if distance_km >= 60 and minutes < 45:
        return False
    if distance_km >= 120 and minutes < 70:
        return False
    if mode_key in {"walk", "walking"} and distance_km > 3.0 and minutes < 25:
        return False
    if mode_key in {"train", "transit", "bus"} and distance_km < 1.2 and minutes > 90:
        return False
    return True


@contextmanager
def _disable_live_routes_api_for_phase3():
    original = None
    try:
        import maps.routes_api as routes_api_module
        original = getattr(routes_api_module.RoutesAPI, "compute_route", None)
        if original is not None:
            def _disabled_compute_route(self, origin, destination, mode="walk", departure_time=None, use_case="final_itinerary"):
                return None
            routes_api_module.RoutesAPI.compute_route = _disabled_compute_route
        yield
    except Exception:
        yield
    finally:
        try:
            if original is not None:
                import maps.routes_api as routes_api_module
                routes_api_module.RoutesAPI.compute_route = original
        except Exception:
            pass


def enrich_transport_rows_with_estimates(df: pd.DataFrame, planning_state: Dict[str, object], use_case: str = "final_itinerary") -> pd.DataFrame:
    """
    完成旅程の transport row に対して、必要最小限の推定値だけを付与する。

    方針:
    - 短距離の地上移動だけ app.py 側で LLM概算 / 距離推定を行う
    - 航空・空港・国際移動は app.py 側では一切上書きしない
      （未実装・未解決課題。Phase2/Phase3 側で構造保持すべき領域）

    TODO:
    - 実移動時間は現在まだ推測中心
    - 飛行機を含む移動は構造化層で transport type を保持しないと安全に扱えない
    - app.py 表示層での後付け推定は地上短距離のみで運用する
    """
    if df is None or df.empty or "is_transport" not in df.columns:
        return df

    enriched = df.copy().reset_index(drop=True)
    for idx in enriched.index[enriched["is_transport"] == True].tolist():
        prev_row, next_row = _find_transport_context_rows(enriched, idx)
        if prev_row is None or next_row is None:
            continue

        origin_name = safe_text(prev_row.get("destination"), "出発地")
        destination_name = safe_text(next_row.get("destination"), "目的地")

        departure_date = safe_text(enriched.at[idx, "date"], safe_text(planning_state.get("start_date"), ""))
        departure_time = safe_text(enriched.at[idx, "start_time"], safe_text(planning_state.get("departure_time"), "09:00"))

        # --- 安全策: 航空・空港・国際移動は app.py で再計算しない ---
        # ここを無理に上書きすると「電車30分」等の破綻が起きるため、
        # 現時点では元の構造化結果を尊重してスキップする。
        if _is_air_transport_context(enriched.iloc[idx], prev_row, next_row):
            enriched.at[idx, "route_data_source"] = "non_ground_skipped"
            enriched.at[idx, "estimated_duration_label"] = ""
            enriched.at[idx, "route_departure_at"] = f"{departure_date} {departure_time}".strip()
            existing_note = safe_text(enriched.at[idx, "one_point"], "")
            safety_note = "未実装・未解決課題: 実移動時間はまだ推測中心で、飛行機を含む移動は app.py では再計算しません。"
            if safety_note not in existing_note:
                enriched.at[idx, "one_point"] = (existing_note + " / " + safety_note).strip(" /")[:180]
            continue

        # --- 新幹線や列車名そのものを destination にした行は、app.py では無理に再計算しない ---
        # TODO: 本来は Phase2 / Phase3 側で「列車サービス名」「便名」を transport type として保持すべき。
        rail_service_like = any(token in f"{origin_name} {destination_name}" for token in ["新幹線", "かがやき", "はくたか", "のぞみ", "ひかり", "こだま", "サンダーバード", "しらさぎ", "つるぎ"])
        if rail_service_like:
            enriched.at[idx, "route_data_source"] = "kept_existing_schedule"
            enriched.at[idx, "estimated_duration_label"] = ""
            enriched.at[idx, "route_departure_at"] = f"{departure_date} {departure_time}".strip()
            existing_note = safe_text(enriched.at[idx, "one_point"], "")
            note = "未解決課題: 列車サービス名を含む移動は、構造化層で transport type を保持してから再計算すべきです。"
            if note not in existing_note:
                enriched.at[idx, "one_point"] = (existing_note + " / " + note).strip(" /")[:180]
            continue

        origin_lat = prev_row.get("latitude")
        origin_lng = prev_row.get("longitude")
        destination_lat = next_row.get("latitude")
        destination_lng = next_row.get("longitude")
        if any(pd.isna(v) for v in [origin_lat, origin_lng, destination_lat, destination_lng]):
            enriched.at[idx, "route_data_source"] = "kept_existing_schedule"
            enriched.at[idx, "estimated_duration_label"] = ""
            enriched.at[idx, "route_departure_at"] = f"{departure_date} {departure_time}".strip()
            continue

        try:
            distance_km = _haversine_km(float(origin_lat), float(origin_lng), float(destination_lat), float(destination_lng))
        except Exception:
            enriched.at[idx, "route_data_source"] = "ground_estimate_unavailable"
            enriched.at[idx, "estimated_duration_label"] = "距離計算失敗のため要確認"
            enriched.at[idx, "route_departure_at"] = f"{departure_date} {departure_time}".strip()
            continue

        mode = safe_text(enriched.at[idx, "transport_mode"], "").lower()
        preferred = safe_text(planning_state.get("transport_style"), "自動（おすすめ）")
        if not mode or mode == "-":
            mode = {
                "徒歩メイン": "walk",
                "電車メイン": "train",
                "タクシー": "taxi",
                "レンタカー": "car",
            }.get(preferred, "train" if distance_km >= 2.0 else "walk")
            enriched.at[idx, "transport_mode"] = mode
        elif mode in {"car", "private_car"} and preferred == "電車メイン":
            # 表示だけでもユーザー意図に寄せる
            mode = "train"
            enriched.at[idx, "transport_mode"] = mode

        google_result = None
        origin_query = _build_google_directions_location_query(origin_name, origin_lat, origin_lng)
        destination_query = _build_google_directions_location_query(destination_name, destination_lat, destination_lng)
        # Google Directions API は最小導入。train/bus/walk/taxi/car の現実的な移動時間取得を優先する。
        if origin_query and destination_query:
            google_result = _fetch_google_directions_legacy(
                origin_query=origin_query,
                destination_query=destination_query,
                mode=mode,
                departure_date=departure_date,
                departure_time=departure_time,
            )

        if google_result and _validate_google_route_minutes(
            distance_km=distance_km,
            minutes=int(google_result["minutes"]),
            mode=mode,
            origin_name=origin_name,
            destination_name=destination_name,
        ):
            minutes = int(google_result["minutes"])
            label = f"約{minutes}分"
            line_parts = [label]
            if google_result.get("transit_summary"):
                line_parts.append(str(google_result["transit_summary"]))
            if google_result.get("fare_text") and google_result.get("fare_text") != "-":
                line_parts.append(f"運賃 {google_result['fare_text']}")
            enriched.at[idx, "route_data_source"] = str(google_result.get("source", "google_directions_legacy"))
            enriched.at[idx, "estimated_duration_label"] = label
            enriched.at[idx, "route_departure_at"] = f"{departure_date} {departure_time}".strip()
            enriched.at[idx, "duration_minutes"] = minutes
            enriched.at[idx, "end_time"] = _add_minutes_to_clock(departure_time, minutes)
            enriched.at[idx, "route_line_simple"] = " / ".join(line_parts[:3])
            enriched.at[idx, "route_from"] = origin_name
            enriched.at[idx, "route_to"] = destination_name
            note_parts = []
            if google_result.get("distance_text") and google_result.get("distance_text") != "-":
                note_parts.append(f"Google Directions 推定距離 {google_result['distance_text']}")
            if google_result.get("transit_summary"):
                note_parts.append(str(google_result["transit_summary"]))
            if google_result.get("fare_text") and google_result.get("fare_text") != "-":
                note_parts.append(f"運賃 {google_result['fare_text']}")
            if note_parts:
                enriched.at[idx, "one_point"] = " / ".join(note_parts)[:160]
        else:
            if google_result:
                log_event("移動時間推定", f"Google Directions 結果を棄却: {origin_name} → {destination_name} / {google_result.get('minutes')}分 / {distance_km:.1f}km", level="warning")
            llm_result = _llm_transport_duration_estimate(
                origin_name=origin_name,
                destination_name=destination_name,
                mode=mode,
                departure_date=departure_date,
                departure_time=departure_time,
                distance_km=distance_km,
                origin_lat=float(origin_lat),
                origin_lng=float(origin_lng),
                destination_lat=float(destination_lat),
                destination_lng=float(destination_lng),
            )

            if llm_result and llm_result.get("minutes") and _validate_llm_minutes(
                distance_km=distance_km,
                mode=mode,
                minutes=int(llm_result["minutes"]),
                origin_name=origin_name,
                destination_name=destination_name,
            ):
                minutes = int(llm_result["minutes"])
                label = f"約{minutes}分"
                enriched.at[idx, "route_data_source"] = "llm_estimate"
                enriched.at[idx, "estimated_duration_label"] = label
                enriched.at[idx, "route_departure_at"] = f"{departure_date} {departure_time}".strip()
                enriched.at[idx, "duration_minutes"] = minutes
                enriched.at[idx, "end_time"] = _add_minutes_to_clock(departure_time, minutes)
                enriched.at[idx, "route_line_simple"] = f"{label}"
                enriched.at[idx, "route_from"] = origin_name
                enriched.at[idx, "route_to"] = destination_name
                reason = str(llm_result.get("reason", "")).strip()
                if reason:
                    enriched.at[idx, "one_point"] = reason[:120]
            else:
                if llm_result and llm_result.get("minutes"):
                    log_event("移動時間推定", f"LLM概算を棄却: {origin_name} → {destination_name} / {llm_result.get('minutes')}分 / {distance_km:.1f}km", level="warning")
                fallback = _build_safe_distance_fallback(distance_km, mode, origin_name, destination_name)
                minutes = int(fallback.get("minutes", max(1, _estimate_minutes_from_distance(distance_km, mode))))
                label = str(fallback.get("label", f"約{minutes}分（推測）"))
                enriched.at[idx, "route_data_source"] = str(fallback.get("source", "distance_estimate"))
                enriched.at[idx, "estimated_duration_label"] = label
                enriched.at[idx, "route_departure_at"] = f"{departure_date} {departure_time}".strip()
                enriched.at[idx, "duration_minutes"] = minutes
                enriched.at[idx, "end_time"] = _add_minutes_to_clock(departure_time, minutes)
                enriched.at[idx, "route_line_simple"] = f"{label}"
                enriched.at[idx, "route_from"] = origin_name
                enriched.at[idx, "route_to"] = destination_name
                note = str(fallback.get("note", "")).strip()
                if note:
                    enriched.at[idx, "one_point"] = note[:120]

    return enriched



def extract_trip_days_from_text(text: str) -> Optional[int]:
    text = str(text or "")
    if not text.strip():
        return None
    # --- 修正箇所: 日帰り/◯泊/◯泊◯日 をより自然に拾う ---
    if "日帰り" in text:
        return 1
    match = re.search(r"(\d+)\s*泊\s*(\d+)\s*日", text)
    if match:
        return int(match.group(2))
    match = re.search(r"(\d+)\s*泊", text)
    if match:
        return int(match.group(1)) + 1
    match = re.search(r"(\d+)\s*日", text)
    if match:
        return int(match.group(1))
    return None



def extract_primary_destination_from_text(text: str, departure_place: str = "", return_place: str = "") -> str:
    raw_text = str(text or "").strip()
    if not raw_text:
        return ""

    cleaned = re.sub(r"[、。,.!！?？]", " ", raw_text)
    patterns = [
        r"(?:へ|に|で)?\s*([一-龥ぁ-んァ-ヶA-Za-z0-9ー・]{2,20})\s*(?:へ|に|で)?\s*\d+\s*泊",
        r"(?:へ|に|で)?\s*([一-龥ぁ-んァ-ヶA-Za-z0-9ー・]{2,20})\s*(?:旅行|観光|散策|滞在)",
        r"([一-龥ぁ-んァ-ヶA-Za-z0-9ー・]{2,20})\s*に行きたい",
    ]
    candidates = []
    for pattern in patterns:
        for match in re.finditer(pattern, cleaned):
            candidate = str(match.group(1) or "").strip(" 　")
            if candidate:
                candidates.append(candidate)

    if not candidates:
        compact = re.sub(r"\s+", "", raw_text)
        simple = re.match(r"([一-龥ぁ-んァ-ヶA-Za-z0-9ー・]{2,20})\d+\s*泊", compact)
        if simple:
            candidates.append(str(simple.group(1)).strip())

    exclusions = {
        str(departure_place or "").strip(),
        str(return_place or "").strip(),
        "旅行", "観光", "グルメ", "温泉", "ホテル", "泊", "日",
    }
    for candidate in candidates:
        if candidate and candidate not in exclusions:
            return candidate
    return ""




# --- 修正箇所: 旅行相談の曖昧性検出と自然な聞き返し ---
def detect_fixed_requirement_lines(notes: List[str]) -> List[str]:
    lines: List[str] = []
    keywords = ("開演", "開始", "集合", "予約", "会議", "ライブ", "コンサート", "試合", "観劇", "イベント", "チェックイン", "フライト", "飛行機", "新幹線")
    for note in notes:
        note_text = str(note or "").strip()
        if not note_text:
            continue
        if any(k in note_text for k in keywords) or re.search(r"\d{1,2}[:：]\d{2}|\d{1,2}/\d{1,2}|\d+人|\d+泊|日帰り", note_text):
            if note_text not in lines:
                lines.append(note_text)
    return lines


def extract_event_summary_from_text(text: str) -> Dict[str, str]:
    raw = str(text or "").strip()
    summary = {"event_name": "", "event_date": "", "event_time": "", "people_count": ""}
    if not raw:
        return summary

    date_match = re.search(r"(\d{1,2}/\d{1,2})", raw)
    if date_match:
        summary["event_date"] = date_match.group(1)

    time_match = re.search(r"(\d{1,2})\s*時\s*(?:に)?\s*(開演|開始|集合)", raw)
    if time_match:
        summary["event_time"] = f"{time_match.group(1)}時"

    people_match = re.search(r"(\d+)\s*人", raw)
    if people_match:
        summary["people_count"] = people_match.group(1)

    cleaned = re.sub(r"\d{1,2}/\d{1,2}", "", raw)
    cleaned = re.sub(r"\d{1,2}\s*時\s*(?:に)?\s*(開演|開始|集合)", "", cleaned)
    event_patterns = [
        r"([一-龥ぁ-んァ-ヶA-Za-z0-9ー・]+(?:コンサート|ライブ|試合|観劇|イベント|会議|打ち合わせ|展示会|結婚式))",
    ]
    for pattern in event_patterns:
        match = re.search(pattern, cleaned)
        if match:
            candidate = str(match.group(1)).strip(" 、。,.!！?？")
            candidate = re.sub(r"^(?:に|へ|で)", "", candidate)
            if candidate:
                summary["event_name"] = candidate
                break
    return summary

def format_trip_days_label(trip_days: int) -> str:
    trip_days = int(trip_days or 0)
    if trip_days <= 0:
        return ""
    if trip_days == 1:
        return "日帰り"
    return f"{trip_days - 1}泊{trip_days}日"


def build_trip_overview_from_state(planning_state: Dict[str, object]) -> str:
    notes = planning_state.get("conversation_notes", []) + planning_state.get("revision_requests", [])
    combined_text = " / ".join([str(note or "").strip() for note in notes if str(note or "").strip()])
    event_summary = extract_event_summary_from_text(combined_text)
    destination = safe_text(planning_state.get("primary_destination"), "")
    trip_days = int(planning_state.get("trip_days", 0) or 0)
    trip_days_label = format_trip_days_label(trip_days)

    parts: List[str] = []
    if event_summary.get("event_date"):
        parts.append(f"{event_summary['event_date']}に")
    if destination:
        parts.append(f"{destination}へ行き")
    if event_summary.get("event_name"):
        parts.append(f"目的は{event_summary['event_name']}")
    if trip_days_label:
        parts.append(trip_days_label)
    if event_summary.get("people_count"):
        parts.append(f"{event_summary['people_count']}人でのご予定")

    return "、".join(parts)


def detect_ambiguities_from_context(user_text: str, planning_state: Dict[str, object]) -> List[Dict[str, str]]:
    text_value = str(user_text or "").strip()
    if not text_value:
        return []

    event_summary = extract_event_summary_from_text(text_value)
    destination = safe_text(planning_state.get("primary_destination"), "")
    trip_days = int(planning_state.get("trip_days", 0) or 0)
    ambiguities: List[Dict[str, str]] = []

    has_event = bool(event_summary.get("event_name")) or any(word in text_value for word in ["コンサート", "ライブ", "試合", "観劇", "イベント", "会議", "結婚式"])
    explicit_place = any(token in text_value for token in ["会場", "場所", "現地", "京都で", "大阪で"])
    explicit_day = any(token in text_value for token in ["当日", "翌日", "初日", "2日目", "二日目", "最終日"])

    if has_event and destination and ("に行く" in text_value or "へ行く" in text_value) and not explicit_place:
        ambiguities.append({
            "type": "event_location",
            "priority": "1",
            "hint": destination,
        })

    if has_event and event_summary.get("event_date") and trip_days >= 2 and not explicit_day:
        ambiguities.append({
            "type": "event_day",
            "priority": "2",
            "hint": event_summary.get("event_date", ""),
        })

    return ambiguities


def get_missing_hearing_fields(planning_state: Dict[str, object]) -> List[str]:
    missing: List[str] = []
    if not safe_text(planning_state.get("primary_destination"), ""):
        missing.append("destination")
    if not int(planning_state.get("trip_days", 0) or 0):
        missing.append("trip_days")
    if safe_text(planning_state.get("transport_style"), "") in {"", "-", "未設定"}:
        missing.append("transport_style")
    if safe_text(planning_state.get("budget_style"), "") in {"", "-", "未設定"}:
        missing.append("budget_style")
    return missing


def build_confirmation_payload(user_text: str) -> Optional[Dict[str, str]]:
    text = str(user_text or "").strip()
    if not text:
        return None

    planning_state = st.session_state.planning_state
    destination = extract_primary_destination_from_text(
        text,
        planning_state.get("departure_place", ""),
        planning_state.get("return_place", ""),
    )
    trip_days = extract_trip_days_from_text(text)

    should_confirm = bool(destination or trip_days)
    if not should_confirm:
        return None

    resolved_destination = destination or safe_text(planning_state.get("primary_destination"), "")
    resolved_trip_days = trip_days or int(planning_state.get("trip_days", 2))
    departure_place = safe_text(planning_state.get("departure_place"), "-")

    temp_state = dict(planning_state)
    if resolved_destination:
        temp_state["primary_destination"] = resolved_destination
    temp_state["trip_days"] = resolved_trip_days
    overview = build_trip_overview_from_state(temp_state)
    fallback_overview = f"{resolved_destination}への{format_trip_days_label(resolved_trip_days)}のご予定"

    message = (
        f"確認です。旅の概要は「{overview or fallback_overview}」、"
        f"出発地は「{departure_place}」でよいですか？"
    )
    return {
        "primary_destination": resolved_destination,
        "trip_days": str(resolved_trip_days),
        "message": message,
        "source_text": text,
    }

def build_hearing_fallback_reply(known: Dict[str, str], ambiguities: List[Dict[str, str]], missing_fields: List[str]) -> str:
    destination = known.get("destination") or "ご予定"
    if ambiguities:
        ambiguity_type = ambiguities[0].get("type")
        if ambiguity_type == "event_location":
            return f"{destination}方面のご予定ですね。イベント会場は{destination}で合っていますか？ それとも周辺の別エリアでしょうか。"
        if ambiguity_type == "event_day":
            return "ありがとうございます。イベントは滞在の初日でしょうか？ それとも翌日でしょうか。"

    if missing_fields:
        missing = missing_fields[0]
        if missing == "destination":
            return "行き先がまだはっきりしていません。どちらへ行く予定でしょうか。"
        if missing == "trip_days":
            return f"{destination}ですね。何日くらいのご予定でしょうか。"
        if missing == "transport_style":
            return "移動はどんな感じをご希望ですか。電車メイン、歩きを減らしたい、タクシーも使いたい、などで大丈夫です。"
        if missing == "budget_style":
            return "予算感はどのくらいで考えていますか。節約・普通・少し贅沢、くらいの粒度で大丈夫です。"

    return "ありがとうございます。条件がそろってきました。この内容で確認してよいかご案内します。"


def generate_hearing_reply_with_llm(
    user_text: str,
    known: Dict[str, str],
    ambiguities: List[Dict[str, str]],
    missing_fields: List[str],
) -> str:
    # --- 修正箇所: 旅行相談フェーズの返答だけをLLMで自然化 ---
    recent_history = st.session_state.get("chat_history", [])[-4:]
    history_text = "\n".join([f"{item.get('role')}: {item.get('content')}" for item in recent_history])

    ambiguity_desc = "なし"
    if ambiguities:
        ambiguity_desc = " / ".join([f"{item.get('type')}({item.get('hint', '')})" for item in ambiguities])

    missing_desc = "なし" if not missing_fields else ", ".join(missing_fields)
    prompt = f"""
あなたは旅行相談アプリ VoyageFlow の相談フェーズ担当です。
今は「ヒアリング段階」です。まだ旅程案を作る段階ではありません。

【絶対にやってはいけないこと】
- 具体的な旅程や時刻付きプランを作る
- Day1/Day2 の提案をする
- 箇条書きや長文説明をする
- 2つ以上の質問を同時にする

【今回のユーザー入力】
{user_text}

【直近の会話】
{history_text}

【すでに分かっている条件】
- 主目的地: {known.get('destination', '未確定')}
- 旅行日数: {known.get('trip_days', '未確定')}
- 出発地: {known.get('departure_place', '未確定')}
- 移動スタイル: {known.get('transport_style', '未確定')}
- 予算感: {known.get('budget_style', '未確定')}

【曖昧な点】
{ambiguity_desc}

【不足している項目】
{missing_desc}

【出力ルール】
- 1〜2文の自然な日本語だけ
- まず理解した内容を短く確認する
- 次に、最優先の曖昧点があればそれを1つだけ質問する
- 曖昧点がなければ、最優先の不足項目を1つだけ質問する
- 旅程提案は絶対にしない
- 行頭記号・箇条書き・Markdownを使わない
""".strip()

    try:
        generator = Phase1Generator(logger=log_event)
        reply = generator.generate_trip_plan(prompt, temperature=0.3).strip()
        if not reply:
            raise ValueError("empty reply")
        if re.search(r"Day\s*1|【|\d{1,2}:\d{2}|\*|・", reply):
            return build_hearing_fallback_reply(known, ambiguities, missing_fields)
        return re.sub(r"\s+", " ", reply)[:180]
    except Exception as e:
        log_event("旅行相談LLM", f"自然返答生成フォールバック: {e}", level="warning")
        return build_hearing_fallback_reply(known, ambiguities, missing_fields)

def build_confirmation_payload(user_text: str) -> Optional[Dict[str, str]]:
    text = str(user_text or "").strip()
    if not text:
        return None

    planning_state = st.session_state.planning_state
    destination = extract_primary_destination_from_text(
        text,
        planning_state.get("departure_place", ""),
        planning_state.get("return_place", ""),
    )
    trip_days = extract_trip_days_from_text(text)

    should_confirm = bool(destination or trip_days)
    if not should_confirm:
        return None

    resolved_destination = destination or safe_text(planning_state.get("primary_destination"), "")
    resolved_trip_days = trip_days or int(planning_state.get("trip_days", 2))
    departure_place = safe_text(planning_state.get("departure_place"), "-")

    message = (
        f"確認です。主な目的地は「{resolved_destination or '-'}」、"
        f"旅行日数は「{resolved_trip_days}日」、"
        f"出発地は「{departure_place}」でよいですか？ その他希望がなければ、この条件で計画します。"
    )
    return {
        "primary_destination": resolved_destination,
        "trip_days": str(resolved_trip_days),
        "message": message,
        "source_text": text,
    }




# --- 修正箇所: state から確認ペイロードを作る関数を追加（NameError対策） ---
def build_confirmation_payload_from_state() -> Optional[Dict[str, str]]:
    planning_state = dict(st.session_state.get("planning_state", {}))
    notes = planning_state.get("conversation_notes", []) or []
    latest_text = notes[-1] if notes else ""

    destination = safe_text(planning_state.get("primary_destination"), "")
    trip_days = planning_state.get("trip_days")
    departure_place = safe_text(planning_state.get("departure_place"), "-")

    # 会話から取れる追加情報を軽く補完
    event = extract_event_purpose_from_text(latest_text) if "extract_event_purpose_from_text" in globals() else ""
    event_date = extract_event_date_from_text(latest_text) if "extract_event_date_from_text" in globals() else ""
    people = extract_people_count_from_text(latest_text) if "extract_people_count_from_text" in globals() else ""
    duration = None
    try:
        if isinstance(trip_days, int) and trip_days > 0:
            duration = "日帰り" if trip_days == 1 else f"{trip_days-1}泊{trip_days}日"
    except Exception:
        duration = None

    summary_parts = []
    if event_date:
        summary_parts.append(f"{event_date}に")
    if destination:
        summary_parts.append(f"{destination}へ行き")
    if event:
        summary_parts.append(f"目的は{event}")
    if duration:
        summary_parts.append(duration)
    if people:
        summary_parts.append(f"{people}でのご予定")

    if not summary_parts:
        if not destination and not trip_days:
            return None
        message = (
            f"確認です。旅の概要は、{destination or '未確定'}方面、"
            f"{trip_days or '-'}日間、出発地は「{departure_place}」という理解でよいですか？"
        )
    else:
        summary = "、".join(summary_parts)
        message = f"確認です。旅の概要は、{summary}、出発地は「{departure_place}」という理解でよいですか？"

    return {
        "primary_destination": destination,
        "trip_days": str(trip_days) if trip_days else "",
        "message": message,
        "source_text": latest_text,
    }

def apply_confirmation_payload(payload: Dict[str, str]) -> None:
    if not payload:
        return
    planning_state = dict(st.session_state.planning_state)
    primary_destination = str(payload.get("primary_destination", "")).strip()
    if primary_destination:
        planning_state["primary_destination"] = primary_destination
    trip_days = payload.get("trip_days")
    if str(trip_days).strip().isdigit():
        planning_state["trip_days"] = int(str(trip_days).strip())
    st.session_state.planning_state = planning_state


def build_route_source_text(row_dict: Dict) -> str:
    source = safe_text(row_dict.get("route_data_source"), "").lower()
    departure_at = safe_text(row_dict.get("route_departure_at"), "")
    duration_label = safe_text(row_dict.get("estimated_duration_label"), "")
    if source == "google_routes_api":
        if departure_at and departure_at != "-":
            return f"移動時間: 実検索（Google Routes / {departure_at} 出発想定）"
        return "移動時間: 実検索（Google Routes）"
    if source == "llm_estimate":
        if departure_at and departure_at != "-":
            return f"移動時間: LLM概算 {duration_label}（{departure_at} 出発想定）"
        return f"移動時間: LLM概算 {duration_label}"
    if source == "non_ground_skipped":
        return "移動時間: 既存行程の時間を保持（航空・空港系は app.py で再計算しない）"
    if source == "ground_estimate_unavailable":
        return "移動時間: 既存行程の時間を保持（位置情報不足）"
    if duration_label and duration_label != "-":
        return f"移動時間: {duration_label}"
    return "移動時間: 推定値（フォールバック）"


def build_transport_display_safe(row_dict: Dict) -> str:
    """表示用の重複除去 + 既存の時間表現を削除。時間は `移動時間:` 行だけに一本化する。"""
    base = safe_text(build_transport_display(row_dict), "")
    if not base:
        return "移動"
    base = re.sub(r"\s+", " ", base).strip()
    base = re.sub(r"^(徒歩|電車|タクシー|レンタカー|自家用車|自転車)\s+\1\b", r"\1", base)
    base = base.replace("電車 電車", "電車").replace("徒歩 徒歩", "徒歩").replace("タクシー タクシー", "タクシー")
    base = base.replace("レンタカー レンタカー", "レンタカー").replace("自家用車 自家用車", "自家用車")
    # 末尾の「30分」「約25分」などは削除し、時間表示は別行へ寄せる
    base = re.sub(r"\s*(約)?\d+\s*〜\s*\d+\s*分$", "", base)
    base = re.sub(r"\s*(約)?\d+\s*分$", "", base)
    base = re.sub(r"\s*[/-]\s*(約)?\d+\s*分$", "", base)
    base = re.sub(r"\s+", " ", base).strip(" ：:-")
    return base or "移動"


def resolve_planning_state() -> Dict:
    s = dict(st.session_state.planning_state)
    notes = s.get("conversation_notes", []) + s.get("revision_requests", [])
    latest_text = " / ".join(notes)
    resolved = dict(s)
    conversation_trip_days = extract_trip_days_from_text(latest_text)
    adopted_source = "基本情報"
    if conversation_trip_days and conversation_trip_days != int(s.get("trip_days", 2)):
        resolved["trip_days"] = int(conversation_trip_days)
        adopted_source = "会話"
        log_event("条件解決", f"旅行日数競合: 基本情報={s.get('trip_days')} / 会話={conversation_trip_days} → 会話優先で{conversation_trip_days}日を採用")
    else:
        resolved["trip_days"] = int(s.get("trip_days", 2))
        log_event("条件解決", f"旅行日数を採用: {resolved['trip_days']}日（採用元: {adopted_source}）")
    resolved["resolved_trip_days_source"] = adopted_source
    resolved["conversation_trip_days"] = conversation_trip_days
    resolved["primary_destination"] = safe_text(s.get("primary_destination"), "")
    st.session_state.resolved_conditions = {
        "trip_days_form": int(s.get("trip_days", 2)),
        "trip_days_conversation": conversation_trip_days,
        "trip_days_final": resolved["trip_days"],
        "trip_days_source": adopted_source,
        "primary_destination": resolved.get("primary_destination", ""),
        "transport_style_final": resolved.get("transport_style", "自動（おすすめ）"),
        "budget_style_final": resolved.get("budget_style", "普通"),
    }
    return resolved


def render_internal_logs_sidebar() -> None:
    logs = st.session_state.get("app_logs", [])
    resolved = st.session_state.get("resolved_conditions", {})
    st.markdown("### 内部ログ")
    st.markdown("<div class='vf-log-panel'>PowerShell を見なくても、条件採用・Phase進行・移動判定・不足区間をここで確認できます。</div>", unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("🧹 ログをクリア", key="clear_app_logs", use_container_width=True):
            clear_logs()
            st.rerun()
    with c2:
        st.caption(f"ログ件数: {len(logs)}")
    if resolved:
        with st.expander("採用された条件", expanded=True):
            st.write(f"旅行日数: 基本情報={resolved.get('trip_days_form')} / 会話={resolved.get('trip_days_conversation')} / 最終採用={resolved.get('trip_days_final')} ({resolved.get('trip_days_source')})")
            st.write(f"主目的地: {resolved.get('primary_destination') or '未確定'}")
            st.write(f"移動スタイル: {resolved.get('transport_style_final')}")
            st.write(f"予算感: {resolved.get('budget_style_final')}")
    if not logs:
        st.info("まだログはありません。『旅行案を作成』や『了承』のタイミングで詳細がたまります。")
        return
    with st.expander("詳細ログ", expanded=True):
        for item in reversed(logs[-60:]):
            st.markdown(
                f"<div class='vf-log-item'><div class='vf-log-meta'>[{item['time']}] {item['stage']} / {item['level']}</div><div>{item['message']}</div></div>",
                unsafe_allow_html=True,
            )


def inspect_transport_step_gaps(df: pd.DataFrame) -> List[str]:
    messages: List[str] = []
    if df is None or df.empty:
        return messages
    for day in sorted(df["day"].dropna().unique()):
        day_df = df[df["day"] == day].sort_values("sequence").reset_index(drop=True)
        for idx in range(len(day_df) - 1):
            cur = day_df.iloc[idx]
            nxt = day_df.iloc[idx + 1]
            if (not bool(cur.get("is_transport", False))) and (not bool(nxt.get("is_transport", False))):
                messages.append(f"Day{int(day)}: {safe_text(cur.get('destination'))} → {safe_text(nxt.get('destination'))} の間に移動カードがありません")
    return messages

def reset_all() -> None:
    st.session_state.planning_state = {
        "departure_place": "福井駅",
        "return_place": "福井駅",
        "departure_time": "09:00",
        "start_date": (datetime.now().date() + timedelta(days=7)).strftime("%Y-%m-%d"),
        "trip_days": 2,
        "transport_style": "自動（おすすめ）",
        "budget_style": "普通",
        "hotel_required": True,
        "primary_destination": "",
        "conversation_notes": [],
        "revision_requests": [],
    }
    st.session_state.chat_history = []
    st.session_state.advisor_question_index = 0
    st.session_state.advisor_done = False
    st.session_state.pending_confirmation = None
    st.session_state.pending_ambiguity = None
    st.session_state.phase1_prompt_text = ""
    st.session_state.trip_plan_draft = None
    st.session_state.trip_plan = None
    st.session_state.df_phase2 = None
    st.session_state.df_phase3 = None
    st.session_state.plan_approved = False
    st.session_state.execution_engine = None
    st.session_state.event_result = None
    st.session_state.show_delay_dialog = False
    st.session_state.show_weather_dialog = False
    st.session_state.show_mood_dialog = False
    st.session_state.show_cancel_dialog = False
    st.session_state.transport_decision_locked = False
    st.session_state.replan_preview_draft = None
    st.session_state.replan_preview_request = ""
    st.session_state.replan_preview_source = ""
    st.session_state.replan_error = ""
    st.session_state.rental_car_cache = {}
    st.session_state.active_tab = "travel_consultation"
    st.session_state.app_logs = []
    st.session_state.resolved_conditions = {}


def build_google_maps_search_url(place: str) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(str(place))}"


def build_google_maps_dir_url(origin: str, destination: str, travelmode: str = "walking") -> str:
    mode_map = {
        "walk": "walking",
        "徒歩": "walking",
        "walking": "walking",
        "train": "transit",
        "電車": "transit",
        "transit": "transit",
        "car": "driving",
        "private_car": "driving",
        "rental_car": "driving",
        "レンタカー": "driving",
        "自家用車": "driving",
        "driving": "driving",
        "taxi": "driving",
        "タクシー": "driving",
        None: "walking",
        "": "walking",
    }
    gm_mode = mode_map.get(travelmode, "walking")
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={urllib.parse.quote(str(origin))}"
        f"&destination={urllib.parse.quote(str(destination))}"
        f"&travelmode={gm_mode}"
    )


def get_places_api() -> Optional[PlacesAPI]:
    if "places_api_client" not in st.session_state:
        try:
            st.session_state.places_api_client = PlacesAPI()
        except Exception:
            st.session_state.places_api_client = None
    return st.session_state.places_api_client


def _find_transport_context_rows(df: pd.DataFrame, step_index: int) -> tuple[Optional[pd.Series], Optional[pd.Series]]:
    prev_row = None
    next_row = None
    if df is None or df.empty or step_index < 0 or step_index >= len(df):
        return prev_row, next_row
    day_value = df.iloc[step_index].get("day")
    for idx in range(step_index - 1, -1, -1):
        row = df.iloc[idx]
        if row.get("day") != day_value:
            break
        if not bool(row.get("is_transport", False)):
            prev_row = row
            break
    for idx in range(step_index + 1, len(df)):
        row = df.iloc[idx]
        if row.get("day") != day_value:
            break
        if not bool(row.get("is_transport", False)):
            next_row = row
            break
    return prev_row, next_row


def get_rental_car_availability(df: pd.DataFrame, step_index: int) -> Dict[str, object]:
    cache = st.session_state.setdefault("rental_car_cache", {})
    prev_row, next_row = _find_transport_context_rows(df, step_index)
    anchor_row = prev_row if prev_row is not None else next_row
    if anchor_row is None:
        return {"available": False, "reason": "周辺スポットの位置情報がないため確認できません。", "shops": []}

    lat = anchor_row.get("latitude")
    lng = anchor_row.get("longitude")
    if pd.isna(lat) or pd.isna(lng):
        return {"available": False, "reason": "周辺スポットの位置情報がないため確認できません。", "shops": []}

    cache_key = f"{round(float(lat), 4)}_{round(float(lng), 4)}"
    if cache_key in cache:
        return cache[cache_key]

    places_api = get_places_api()
    if places_api is None:
        result = {"available": False, "reason": "Places API が未設定のためレンタカー営業所を確認できません。", "shops": []}
        cache[cache_key] = result
        return result

    shops = places_api.find_nearby_rental_cars((float(lat), float(lng)), radius=1000)
    result = {
        "available": bool(shops),
        "reason": "" if shops else "周囲1km以内にレンタカー営業所が見つかりません。",
        "shops": shops[:5],
        "anchor_name": safe_text(anchor_row.get("destination"), "現在地付近"),
    }
    cache[cache_key] = result
    return result


def build_remaining_plan_text_from_engine(engine: ExecutionEngine) -> str:
    df = engine.get_updated_dataframe()
    if df is None or df.empty:
        return "残り旅程なし"

    start = getattr(engine, "current_step", 0)
    lines = []
    for idx in range(start, len(df)):
        row = df.iloc[idx]
        if str(row.get("execution_status", "")) == "completed":
            continue
        if bool(row.get("is_transport", False)):
            lines.append(
                f"- {safe_text(row.get('start_time'))}-{safe_text(row.get('end_time'))} 移動 / {safe_text(row.get('destination'))} / 手段={safe_text(row.get('transport_mode'))}"
            )
        else:
            lines.append(
                f"- {safe_text(row.get('start_time'))}-{safe_text(row.get('end_time'))} {safe_text(row.get('destination'))} / 目的={safe_text(row.get('purpose'))} / ジャンル={safe_text(row.get('genre'))}"
            )
    return "\n".join(lines)


def current_position_label_from_engine(engine: ExecutionEngine) -> str:
    df = engine.get_updated_dataframe()
    if df.empty:
        return safe_text(st.session_state.planning_state.get("departure_place"))
    idx = min(int(getattr(engine, "current_step", 0)), len(df) - 1)
    row = df.iloc[idx]
    destination = safe_text(row.get("destination"))
    if bool(row.get("is_transport", False)) and "→" in destination:
        return destination.split("→", 1)[1].strip()
    return destination


def generate_execution_replan_preview(change_request: str, source_event: str = "execution") -> None:
    engine = st.session_state.execution_engine
    if engine is None:
        raise ValueError("実行エンジンが初期化されていません。")

    current_df = engine.get_updated_dataframe()
    if current_df.empty:
        raise ValueError("旅程データがありません。")

    remaining_plan_text = build_remaining_plan_text_from_engine(engine)
    current_position = current_position_label_from_engine(engine)
    current_idx = min(int(getattr(engine, "current_step", 0)), len(current_df) - 1)
    current_row = current_df.iloc[current_idx]
    replanning_state = dict(st.session_state.planning_state)
    replanning_state["departure_place"] = current_position
    replanning_state["departure_time"] = safe_text(current_row.get("end_time"), replanning_state.get("departure_time", "09:00"))
    replanning_state["start_date"] = safe_text(current_row.get("date"), replanning_state.get("start_date"))
    replanning_state["trip_days"] = max(1, int(current_df["day"].max()) - int(current_row.get("day", 1)) + 1)

    notes_text = " / ".join(replanning_state.get("conversation_notes", [])) or "特になし"
    revision_text = change_request.strip()
    prompt_text = f"""
あなたは旅行中の旅程を組み直すAIです。

【最重要】
- すでに終わった予定は変更しません。
- 以下に示す『未実行の残り旅程』だけを自然な日本語で組み直してください。
- ユーザーの今回の変更希望を最優先してください。
- 出力は自由記述の旅程案のみ。
- 無理に別案を複数出さず、ユーザーがそのまま採用しやすい1案を出してください。

【現在地点】
- 現在地の基点: {current_position}
- 組み直し開始時刻の目安: {replanning_state['departure_time']}
- 組み直し開始日: {replanning_state['start_date']}
- 残り日数の目安: {replanning_state['trip_days']}日
- 帰着地: {replanning_state['return_place']}
- 移動スタイル: {replanning_state['transport_style']}
- 予算感: {replanning_state['budget_style']}
- これまでの相談メモ: {notes_text}

【ユーザーの今回の変更希望】
{revision_text}

【未実行の残り旅程】
{remaining_plan_text}

【出力ルール】
- Dayごとに自然文で書く
- 必要ならスポット追加・削除・並べ替えをしてよい
- 変更理由が自然にわかるように書く
- 最後に必ず次の注意書きを入れる
※移動時間や所要時間は目安です。完成旅程では、実際の移動経路や実時間にあわせて調整して表示します。
""".strip()

    log_event("再計画", f"自由組み直し案を生成: {revision_text}")
    generator = Phase1Generator(logger=log_event)
    draft = generator.generate_trip_plan(prompt_text, temperature=st.session_state.temperature)
    caution = "※移動時間や所要時間は目安です。完成旅程では、実際の移動経路や実時間にあわせて調整して表示します。"
    if caution not in draft:
        draft = draft.rstrip() + "\n\n" + caution
    st.session_state.replan_preview_draft = draft
    st.session_state.replan_preview_request = revision_text
    st.session_state.replan_preview_source = source_event
    st.session_state.replan_error = ""


def apply_execution_replan_preview() -> None:
    draft = st.session_state.get("replan_preview_draft")
    if not draft:
        raise ValueError("反映する組み直し案がありません。")
    engine = st.session_state.execution_engine
    if engine is None:
        raise ValueError("実行エンジンが初期化されていません。")

    current_df = engine.get_updated_dataframe()
    current_idx = min(int(getattr(engine, "current_step", 0)), len(current_df) - 1)
    current_row = current_df.iloc[current_idx]
    replanning_state = dict(st.session_state.planning_state)
    replanning_state["departure_place"] = current_position_label_from_engine(engine)
    replanning_state["departure_time"] = safe_text(current_row.get("end_time"), replanning_state.get("departure_time", "09:00"))
    replanning_state["start_date"] = safe_text(current_row.get("date"), replanning_state.get("start_date"))
    replanning_state["trip_days"] = max(1, int(current_df["day"].max()) - int(current_row.get("day", 1)) + 1)

    structurer = Phase2Structuring(logger=log_event)
    df2_new = structurer.structure_trip_plan(draft, replanning_state["start_date"])
    if df2_new is None or df2_new.empty:
        raise ValueError("組み直し案を構造化できませんでした。")
    df2_new = normalize_phase2_dataframe(df2_new, replanning_state)

    router = Phase3Routing(logger=log_event)
    with _disable_live_routes_api_for_phase3():
        df3_new = router.insert_routes(df2_new, user_request=draft, transport_preference=replanning_state["transport_style"])
    if df3_new is None or df3_new.empty:
        raise ValueError("組み直し案から完成旅程を作れませんでした。")
    df3_new = enrich_transport_rows_with_estimates(df3_new, replanning_state, use_case="execution")

    engine.replace_future_plan(df3_new, reason=st.session_state.get("replan_preview_request", "自由組み直しを反映"))
    st.session_state.df_phase3 = engine.get_updated_dataframe()
    st.session_state.trip_plan = draft
    st.session_state.replan_preview_draft = None
    st.session_state.replan_preview_request = ""
    st.session_state.replan_preview_source = ""
    st.session_state.event_result = None


def infer_trip_summary(df: pd.DataFrame) -> Dict[str, str]:
    activities = df[df["is_transport"] == False].reset_index(drop=True)  # noqa: E712
    if activities.empty:
        return {
            "start_time": "-",
            "start": "-",
            "hotel": "未設定",
            "final": "-",
        }

    start_time = safe_text(activities.iloc[0].get("start_time"))
    start_point = safe_text(activities.iloc[0].get("destination"))
    final_point = safe_text(activities.iloc[-1].get("destination"))

    hotel_row = activities[
        activities["destination"].astype(str).str.contains("ホテル|hotel|宿", case=False, na=False)
        | activities["purpose"].astype(str).str.contains("hotel|stay|rest", case=False, na=False)
        | activities["genre"].astype(str).str.contains("hotel|lodging", case=False, na=False)
    ]
    hotel_name = safe_text(hotel_row.iloc[0]["destination"], "未設定") if not hotel_row.empty else "未設定"

    return {
        "start_time": start_time,
        "start": start_point,
        "hotel": hotel_name,
        "final": final_point,
    }


def conversation_advisor_questions() -> List[str]:
    return [
        "どんな旅行にしたいですか？ 例: のんびり / 体験型 / 観光メイン / グルメ重視",
        "移動はどうしたいですか？ 例: 電車メイン / 歩きを減らしたい / タクシーも使いたい / レンタカー",
        "予算感はどうしますか？ 例: 節約 / 普通 / 少し贅沢",
        "ホテルは必須ですか？ また、駅近・温泉・安さ重視など希望はありますか？",
        "日ごとの希望があれば教えてください。例: 2日目はゆったり、お土産時間を確保、3日目は早めに帰る",
    ]


def append_chat(role: str, content: str) -> None:
    st.session_state.chat_history.append({"role": role, "content": content})



def update_planning_state_from_user_text(user_text: str) -> None:
    s = resolve_planning_state()
    text = user_text.strip()

    if "徒歩" in text:
        s["transport_style"] = "徒歩メイン"
    elif "電車" in text:
        s["transport_style"] = "電車メイン"
    elif "タクシー" in text:
        s["transport_style"] = "タクシー"
    elif "レンタカー" in text or "車" in text:
        s["transport_style"] = "レンタカー"

    if "節約" in text or "安く" in text:
        s["budget_style"] = "節約"
    elif "贅沢" in text or "高め" in text:
        s["budget_style"] = "贅沢"
    elif "普通" in text:
        s["budget_style"] = "普通"

    if "ホテル不要" in text or "宿はいらない" in text:
        s["hotel_required"] = False
    elif "ホテル" in text or "宿" in text:
        s["hotel_required"] = True

    # --- 修正箇所: 「京都に行く」を優先し、イベント名や人数語を目的地に混ぜにくくする ---
    travel_match = re.search(r"([一-龥ァ-ヶA-Za-zー・]{2,20})\s*(?:に|へ)行く", text)
    primary_destination = ""
    if travel_match:
        primary_destination = str(travel_match.group(1)).strip()
    else:
        primary_destination = extract_primary_destination_from_text(
            text,
            s.get("departure_place", ""),
            s.get("return_place", ""),
        )

    if primary_destination and not re.search(r"\d+人", primary_destination):
        s["primary_destination"] = primary_destination
        log_event("会話解析", f"会話から主目的地候補を検出: {primary_destination}")

    s["conversation_notes"].append(text)
    inferred_days = extract_trip_days_from_text(text)
    if inferred_days:
        log_event("会話解析", f"会話から旅行日数候補を検出: {inferred_days}日")
        s["trip_days"] = int(inferred_days)

    if st.session_state.advisor_done and text:
        s["revision_requests"].append(text)

    st.session_state.planning_state = s

def build_phase1_request_text() -> str:
    s = resolve_planning_state()

    notes_text = " / ".join(s["conversation_notes"]) if s["conversation_notes"] else "特になし"
    fixed_requirement_lines = detect_fixed_requirement_lines(s.get("conversation_notes", []) + s.get("revision_requests", []))
    revisions_text = " / ".join(s["revision_requests"]) if s["revision_requests"] else "なし"
    primary_destination = safe_text(s.get("primary_destination"), "未指定")
    hotel_instruction = "ホテル（宿泊先）は必ず含めてください。" if s["hotel_required"] else "ホテルは必須ではありません。"

    text = f"""
以下の条件で、自然で分かりやすい日本語の旅行プランを自由記述で作成してください。

【重要な前提】
- 出発地は「旅行の起点」であり、主目的地とは限りません。
- 観光や体験の中心は、ユーザーの希望内容から適切に判断してください。
- 出発地そのものを観光メインにしないでください。ただし、出発地周辺で自然な立ち寄りがある場合は短時間なら可です。
- 帰着地は旅の終点です。
- 出発地から始まり、最終的に帰着地へ戻る流れにしてください。

【旅行条件】
- 出発地: {s["departure_place"]}
- 帰着地: {s["return_place"]}
- 出発時間: {s["departure_time"]}
- 旅行開始日: {s["start_date"]}
- 旅行日数: {s["trip_days"]}日
- 主目的地: {primary_destination}
- 移動スタイル: {s["transport_style"]}
- 予算感: {s["budget_style"]}
- 相談メモ: {notes_text}
- 固定予定・日時付き要件: {" / ".join(fixed_requirement_lines) if fixed_requirement_lines else "なし"}
- 追加の修正希望: {revisions_text}

【旅程の作り方】
- 主目的地が指定されている場合は、その都市・エリアを旅の中心として優先してください。
- ユーザーの希望内容から、旅行の主目的地・主エリア・体験内容を自然に決めてください。
- Day 1, Day 2 のように日別に分けてください。
- 各日の時刻、訪問先、目的、滞在時間の目安がわかる形にしてください。
- {hotel_instruction}
- 「自動（おすすめ）」の場合は、一般的で無理のない移動手段を想定してください。
- 日ごとの個別要望があれば反映してください。
- 固定予定・予約・日時付き要件がある場合は、本文の旅程に必ず反映してください。
- 文章は読みやすく、旅行のイメージがわくようにしてください。

【最後に必ず入れる注意書き】
「※移動時間や所要時間は目安です。完成旅程では、実際の移動経路や実時間にあわせて調整して表示します。」

【出力形式】
1. まず日別の旅程を自然文で提示
2. 最後に旅行アドバイザーとしての注意点を数点添える
3. 最後の一文として、上記の注意書きをそのまま必ず入れる
"""
    return text.strip()


def generate_phase1_draft() -> None:
    clear_logs()
    resolved = resolve_planning_state()
    prompt_text = build_phase1_request_text()
    st.session_state.phase1_prompt_text = prompt_text
    log_event("Phase1", f"LLM候補生成を開始。最終採用: {resolved['trip_days']}日 / {resolved['transport_style']} / {resolved['budget_style']}")

    generator = Phase1Generator(logger=log_event)
    draft = generator.generate_trip_plan(prompt_text, temperature=st.session_state.temperature)

    # 念のため注意書きが無い場合は末尾に補完
    caution = "※移動時間や所要時間は目安です。完成旅程では、実際の移動経路や実時間にあわせて調整して表示します。"
    if caution not in draft:
        draft = draft.rstrip() + "\n\n" + caution

    st.session_state.trip_plan_draft = draft
    st.session_state.plan_approved = False
    st.session_state.active_tab = "plan_review"


def _minutes_between_clock(start_time: str, end_time: str) -> Optional[int]:
    try:
        start = datetime.strptime(str(start_time).strip(), "%H:%M")
        end = datetime.strptime(str(end_time).strip(), "%H:%M")
        diff = int((end - start).total_seconds() // 60)
        if diff < 0:
            diff += 24 * 60
        return diff
    except Exception:
        return None


def _coerce_positive_minutes(value) -> Optional[int]:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        minutes = int(float(value))
        return minutes if minutes > 0 else None
    except Exception:
        return None


def rebuild_phase2_time_consistency(df: pd.DataFrame) -> pd.DataFrame:
    # --- 修正箇所: Spot行の end_time は既存値を優先し、欠損・破綻時のみ duration_minutes で補完 ---
    if df is None or df.empty:
        return df

    normalized = df.copy().reset_index(drop=True)
    if "day" in normalized.columns and "sequence" in normalized.columns:
        normalized = normalized.sort_values(["day", "sequence"], kind="stable").reset_index(drop=True)

    for idx in normalized.index:
        start_time = safe_text(normalized.at[idx, "start_time"], "")
        end_time = safe_text(normalized.at[idx, "end_time"], "")
        duration_minutes = _coerce_positive_minutes(normalized.at[idx, "duration_minutes"] if "duration_minutes" in normalized.columns else None)
        is_transport = bool(normalized.at[idx, "is_transport"]) if "is_transport" in normalized.columns else False

        if not start_time or is_transport:
            continue

        existing_gap = _minutes_between_clock(start_time, end_time) if end_time and end_time != "-" else None
        if existing_gap is not None and 1 <= existing_gap <= 24 * 60:
            # 既存の時刻が自然ならそれを尊重する
            continue

        if duration_minutes is not None and 1 <= duration_minutes <= 24 * 60:
            normalized.at[idx, "end_time"] = _add_minutes_to_clock(start_time, duration_minutes)

    return normalized.reset_index(drop=True)


def _make_same_day_spot_row(base_row: dict, start_time: str, end_time: str, destination: str, purpose: str, genre: str, one_point: str) -> dict:
    row = dict(base_row)
    row["start_time"] = start_time
    row["end_time"] = end_time
    row["destination"] = destination
    row["purpose"] = purpose
    row["genre"] = genre
    row["duration_minutes"] = _minutes_between_clock(start_time, end_time) or 30
    row["is_transport"] = False
    row["transport_mode"] = None
    row["one_point"] = one_point
    row["route_from"] = ""
    row["route_to"] = ""
    row["route_url"] = ""
    row["route_data_source"] = ""
    row["estimated_duration_label"] = ""
    row["address"] = safe_text(row.get("address"), "")
    return row


def _merge_same_day_duplicate_hotel_rows(df: pd.DataFrame) -> pd.DataFrame:
    # --- 修正箇所: 同一日の連続ホテル行を1件に統合 ---
    if df is None or df.empty:
        return df

    merged_rows = []
    rows = [row.to_dict() for _, row in df.sort_values(["day", "sequence"], kind="stable").iterrows()]

    def _hotel_key(name: str) -> str:
        text = safe_text(name, "")
        text = re.sub(r"[\s\u3000]+", "", text)
        text = re.sub(r"[\"'「」()（）【】［］\[\]・,，.．]", "", text)
        return text.lower()

    idx = 0
    while idx < len(rows):
        current = rows[idx]
        if idx + 1 < len(rows):
            nxt = rows[idx + 1]
            same_day = int(current.get("day", 0) or 0) == int(nxt.get("day", 0) or 0)
            if same_day and _is_valid_hotel_row(current) and _is_valid_hotel_row(nxt):
                if _hotel_key(current.get("destination", "")) == _hotel_key(nxt.get("destination", "")):
                    merged = dict(current)
                    cur_start = safe_text(current.get("start_time"), "")
                    cur_end = safe_text(current.get("end_time"), "")
                    nxt_start = safe_text(nxt.get("start_time"), "")
                    nxt_end = safe_text(nxt.get("end_time"), "")
                    starts = [v for v in [cur_start, nxt_start] if v]
                    ends = [v for v in [cur_end, nxt_end] if v]
                    if starts:
                        merged["start_time"] = min(starts)
                    if ends:
                        merged["end_time"] = max(ends)
                    cur_dest = safe_text(current.get("destination"), "")
                    nxt_dest = safe_text(nxt.get("destination"), "")
                    if _is_generic_hotel_label(cur_dest) and not _is_generic_hotel_label(nxt_dest):
                        merged["destination"] = nxt_dest
                    elif _is_generic_hotel_label(nxt_dest) and not _is_generic_hotel_label(cur_dest):
                        merged["destination"] = cur_dest
                    merged["purpose"] = "accommodation"
                    merged["genre"] = "hotel"
                    merged["one_point"] = safe_text(current.get("one_point"), "") or safe_text(nxt.get("one_point"), "") or "翌日に備えてホテルで休息します。"
                    merged_rows.append(merged)
                    idx += 2
                    continue
        merged_rows.append(current)
        idx += 1

    rebuilt = pd.DataFrame(merged_rows)
    if not rebuilt.empty and "day" in rebuilt.columns:
        rebuilt = rebuilt.sort_values(["day", "sequence"], kind="stable").reset_index(drop=True)
        rebuilt["sequence"] = rebuilt.groupby("day").cumcount() + 1
    return rebuilt


def ensure_daily_hotel_rows(df: pd.DataFrame, planning_state: Dict) -> pd.DataFrame:
    # --- 修正箇所: ホテル補完を見直し。Day1 先頭ホテル禁止・日末終端と翌朝始端だけを補完 ---
    if df is None or df.empty:
        return df

    normalized = df.copy().reset_index(drop=True)
    if int(planning_state.get("trip_days", 1) or 1) <= 1 or not bool(planning_state.get("hotel_required", True)):
        return normalized

    if "day" in normalized.columns and "sequence" in normalized.columns:
        normalized = normalized.sort_values(["day", "sequence"], kind="stable").reset_index(drop=True)

    day_values = sorted([int(v) for v in normalized["day"].dropna().unique().tolist()])
    if len(day_values) <= 1:
        return normalized

    canonical_hotel_by_day = _resolve_canonical_hotel_by_day(normalized)
    rows = []
    first_day = day_values[0]
    last_day = day_values[-1]

    for day in day_values:
        day_df = normalized[normalized["day"] == day].sort_values("sequence", kind="stable").reset_index(drop=True)
        if day_df.empty:
            continue

        day_rows = [row.to_dict() for _, row in day_df.iterrows()]
        current_date = safe_text(day_rows[0].get("date"), planning_state.get("start_date", ""))

        # Day1 先頭側に誤って入った generic/補完ホテルは除外
        if day == first_day:
            cleaned_rows = []
            seen_non_hotel = False
            for row in day_rows:
                row_dest = safe_text(row.get("destination"), "")
                if not seen_non_hotel and _is_hotel_like_name(row_dest):
                    if _is_generic_hotel_label(row_dest) or safe_text(row.get("purpose"), "").lower() in {"departure", "accommodation", "hotel"}:
                        log_event("ホテル補完", f"Day1先頭側のホテル行を除外: {row_dest}", level="info")
                        continue
                if not _is_hotel_like_name(row_dest):
                    seen_non_hotel = True
                cleaned_rows.append(row)
            day_rows = cleaned_rows if cleaned_rows else day_rows

        day_hotel_name = canonical_hotel_by_day.get(day, "")
        next_day_hotel_name = canonical_hotel_by_day.get(day + 1, "")
        hotel_end_name = day_hotel_name or next_day_hotel_name

        # --- 修正箇所: generic ホテル開始行は前日ホテル正本へ置換 ---
        if day != first_day:
            prev_hotel_name = canonical_hotel_by_day.get(day - 1, "") or day_hotel_name
            if prev_hotel_name:
                for row in day_rows:
                    row_dest = safe_text(row.get("destination"), "")
                    row_purpose = safe_text(row.get("purpose"), "").lower()
                    if _is_hotel_like_name(row_dest) and (_is_generic_hotel_label(row_dest) or row_purpose == "departure"):
                        row["destination"] = prev_hotel_name
                        row["genre"] = "hotel"
                        if row_purpose in {"", "transport"}:
                            row["purpose"] = "departure"
                        break

        # 既存ホテル開始/終端の検出は valid hotel row のみに限定
        has_hotel_start = False
        has_hotel_end = False
        for row in day_rows:
            row_dest = safe_text(row.get("destination"), "")
            if not _is_valid_hotel_row(row):
                continue
            row_start = safe_text(row.get("start_time"), "")
            row_end = safe_text(row.get("end_time"), "")
            if day != first_day and row_start and row_start <= "10:30":
                has_hotel_start = True
            if day != last_day and ((row_end and row_end >= "18:00") or safe_text(row.get("purpose"), "").lower() in {"accommodation", "hotel"}):
                has_hotel_end = True

        if day != last_day and not has_hotel_end and hotel_end_name:
            last_non_hotel = next((row for row in reversed(day_rows) if not _is_hotel_like_name(safe_text(row.get("destination"), ""))), day_rows[-1])
            last_end = safe_text(last_non_hotel.get("end_time"), "20:00") or "20:00"
            hotel_end = _make_same_day_spot_row(
                last_non_hotel,
                start_time=last_end,
                end_time="23:00" if last_end < "23:00" else _add_minutes_to_clock(last_end, 60),
                destination=hotel_end_name,
                purpose="accommodation",
                genre="hotel",
                one_point="翌日に備えてホテルへチェックイン。荷物整理と休息を優先します。",
            )
            hotel_end["date"] = current_date
            hotel_end["day"] = day
            day_rows.append(hotel_end)

        if day != first_day and not has_hotel_start:
            prev_hotel_name = canonical_hotel_by_day.get(day - 1, "") or canonical_hotel_by_day.get(day, "")
            if prev_hotel_name:
                first_non_hotel = next((row for row in day_rows if not _is_hotel_like_name(safe_text(row.get("destination"), ""))), day_rows[0])
                first_start = safe_text(first_non_hotel.get("start_time"), "09:00") or "09:00"
                start_hotel = _make_same_day_spot_row(
                    first_non_hotel,
                    start_time="09:00" if first_start > "09:00" else first_start,
                    end_time=first_start,
                    destination=prev_hotel_name,
                    purpose="departure",
                    genre="hotel",
                    one_point="ホテルを出発してその日の行程を開始します。",
                )
                start_hotel["date"] = current_date
                start_hotel["day"] = day
                day_rows = [start_hotel] + day_rows

        rows.extend(day_rows)

    rebuilt = pd.DataFrame(rows)
    if "day" in rebuilt.columns:
        rebuilt["day"] = rebuilt["day"].astype(int)
    rebuilt = rebuilt.sort_values(["day", "sequence"], kind="stable").reset_index(drop=True)
    rebuilt["sequence"] = rebuilt.groupby("day").cumcount() + 1
    rebuilt = _propagate_hotel_names(rebuilt, planning_state)
    rebuilt = _merge_same_day_duplicate_hotel_rows(rebuilt)
    rebuilt = _propagate_hotel_names(rebuilt, planning_state)
    return rebuilt


def _infer_mode_from_transport_style(transport_style: str) -> str:
    mapping = {
        "徒歩メイン": "walk",
        "電車メイン": "train",
        "タクシー": "taxi",
        "レンタカー": "car",
    }
    return mapping.get(str(transport_style or "").strip(), "train")


def _llm_transport_duration_from_sequence(
    origin_name: str,
    destination_name: str,
    departure_date: str,
    departure_time: str,
    transport_style: str,
    current_purpose: str,
    next_purpose: str,
    current_note: str,
    next_note: str,
    service_hint: str = "",
) -> Optional[Dict[str, object]]:
    # --- 修正箇所: destination の意味解釈を増やさず、隣接スポットの自然文だけを LLM に渡す ---
    prompt = f"""
あなたは旅行プランの移動時間推定補助です。

次の2地点は、構造化データ上で連続して並ぶスポットです。
地点名の意味解釈を増やしすぎず、一般的に現実的な移動時間だけを保守的に推定してください。

【重要ルール】
- JSON だけを返す
- 路線名・停車駅・乗換回数などを、確信がないのに捏造しない
- minutes は整数
- confidence は high / medium / low
- 不確実なら minutes は null
- 日本国内の一般的な旅行として、過小評価しない

【入力】
- 出発地点: {origin_name}
- 到着地点: {destination_name}
- 出発予定日: {departure_date}
- 出発予定時刻: {departure_time}
- ユーザーの移動希望: {transport_style}
- 出発地点の目的: {current_purpose}
- 到着地点の目的: {next_purpose}
- 出発地点メモ: {current_note}
- 到着地点メモ: {next_note}
- 移動手段ヒント: {service_hint}

【出力JSON形式】
{{
  "minutes": 170,
  "confidence": "medium",
  "reason": "一般的な都市間移動の概算",
  "mode": "train"
}}

minutes を出せない場合:
{{
  "minutes": null,
  "confidence": "low",
  "reason": "情報不足で妥当な概算を出せない",
  "mode": "train"
}}
""".strip()
    try:
        generator = Phase1Generator(logger=log_event)
        raw = generator.generate_trip_plan(prompt, temperature=0.1).strip()
        data = _safe_json_extract(raw)
        if not data:
            return None
        minutes = data.get("minutes")
        if minutes is None:
            return None
        minutes = int(minutes)
        if minutes <= 0 or minutes > 24 * 60:
            return None
        mode = str(data.get("mode", "") or "").strip().lower()
        if mode not in {"walk", "train", "taxi", "car", "private_car", "bike", "air"}:
            mode = _infer_mode_from_transport_style(transport_style)
        mode = _infer_mode_from_service_hint(service_hint, mode)
        confidence = str(data.get("confidence", "medium") or "medium").strip().lower()
        reason = str(data.get("reason", "") or "").strip()
        return {"minutes": minutes, "mode": mode, "confidence": confidence, "reason": reason}
    except Exception as e:
        log_event("移動時間推定", f"隣接スポットLLM概算フォールバック: {e}", level="warning")
        return None


def _fallback_transport_estimate_from_sequence(
    current_row: pd.Series,
    next_row: pd.Series,
    planning_state: Dict[str, object],
) -> Dict[str, object]:
    mode = _infer_mode_from_transport_style(safe_text(planning_state.get("transport_style"), "自動（おすすめ）"))
    existing_gap = _minutes_between_clock(current_row.get("end_time"), next_row.get("start_time"))
    if existing_gap is not None and 5 <= existing_gap <= 12 * 60:
        minutes = existing_gap
        label = f"約{minutes}分"
        source = "existing_time_gap"
        note = "構造化データ上の時刻差分を採用"
    else:
        default_map = {"walk": 20, "train": 30, "bus": 35, "taxi": 25, "car": 30, "private_car": 30, "bike": 20, "ship": 90, "air": 180}
        minutes = default_map.get(mode, 30)
        label = f"約{minutes}分（推測）"
        source = "sequence_fallback"
        note = "隣接スポットの順序から保守的に推定"
    return {"minutes": minutes, "mode": mode, "label": label, "source": source, "note": note}


def build_phase3_from_sequential_destinations(df2: pd.DataFrame, planning_state: Dict[str, object]) -> pd.DataFrame:
    # --- 修正箇所: train / transport 行は独立スポットにせず、前後スポットを橋渡しする移動ヒントとして扱う ---
    if df2 is None or df2.empty:
        return df2

    source_df = df2.copy().reset_index(drop=True)
    rows: List[Dict[str, object]] = []

    for idx in range(len(source_df)):
        current = source_df.iloc[idx].copy()
        current_purpose = safe_text(current.get("purpose"), "").lower()
        current_destination = safe_text(current.get("destination"), "")
        current_is_service_transport = current_purpose == "transport" and _is_transport_service_like_destination(current_destination)

        if current_is_service_transport:
            log_event("Phase3", f"列車サービス行を単独スポット表示しない: {current_destination}", level="info")
            continue

        current_dict = current.to_dict()
        current_dict["is_transport"] = False
        current_dict["route_from"] = safe_text(current_dict.get("route_from"), "")
        current_dict["route_to"] = safe_text(current_dict.get("route_to"), "")
        current_dict["route_url"] = safe_text(current_dict.get("route_url"), "")
        current_dict["route_data_source"] = safe_text(current_dict.get("route_data_source"), "")
        current_dict["estimated_duration_label"] = safe_text(current_dict.get("estimated_duration_label"), "")
        rows.append(current_dict)

        if idx >= len(source_df) - 1:
            continue

        next_idx = idx + 1
        nxt = source_df.iloc[next_idx]
        if int(current.get("day", 1) or 1) != int(nxt.get("day", 1) or 1):
            continue

        service_hint = ""
        actual_next = nxt

        next_purpose = safe_text(nxt.get("purpose"), "").lower()
        next_destination = safe_text(nxt.get("destination"), "")
        next_is_service_transport = next_purpose == "transport" and _is_transport_service_like_destination(next_destination)

        if next_is_service_transport:
            if next_idx + 1 >= len(source_df):
                continue
            bridged = source_df.iloc[next_idx + 1]
            if int(current.get("day", 1) or 1) != int(bridged.get("day", 1) or 1):
                continue
            service_hint = next_destination
            actual_next = bridged
            log_event("Phase3", f"train橋渡し移動を生成: {safe_text(current.get('destination'), '')} → {safe_text(actual_next.get('destination'), '')} / {service_hint}", level="info")

        origin_name = safe_text(current.get("destination"), "")
        destination_name = safe_text(actual_next.get("destination"), "")
        if not origin_name or not destination_name:
            continue

        if _same_effective_place(origin_name, destination_name):
            log_event("Phase3", f"同一地点移動をスキップ: {origin_name} → {destination_name}", level="info")
            continue

        departure_time = safe_text(current.get("end_time"), safe_text(current.get("start_time"), planning_state.get("departure_time", "09:00")))
        departure_date = safe_text(current.get("date"), safe_text(planning_state.get("start_date"), ""))

        llm_result = _llm_transport_duration_from_sequence(
            origin_name=origin_name,
            destination_name=destination_name,
            departure_date=departure_date,
            departure_time=departure_time,
            transport_style=safe_text(planning_state.get("transport_style"), "自動（おすすめ）"),
            current_purpose=safe_text(current.get("purpose"), ""),
            next_purpose=safe_text(actual_next.get("purpose"), ""),
            current_note=safe_text(current.get("one_point"), ""),
            next_note=safe_text(actual_next.get("one_point"), ""),
            service_hint=service_hint,
        )

        if llm_result:
            transport_minutes = int(llm_result["minutes"])
            transport_mode = _infer_mode_from_service_hint(service_hint, str(llm_result.get("mode", _infer_mode_from_transport_style(planning_state.get("transport_style", "")))))
            duration_label = f"約{transport_minutes}分"
            route_source = "llm_sequence_estimate" if not service_hint else "llm_train_bridge_estimate"
            one_point = safe_text(llm_result.get("reason"), "")
        else:
            fallback = _fallback_transport_estimate_from_sequence(current, actual_next, planning_state)
            transport_minutes = int(fallback["minutes"])
            transport_mode = _infer_mode_from_service_hint(service_hint, str(fallback["mode"]))
            duration_label = str(fallback["label"])
            route_source = str(fallback["source"]) if not service_hint else "train_bridge_fallback"
            one_point = str(fallback["note"])

        next_start_time = safe_text(actual_next.get("start_time"), "")
        consistent_gap = _minutes_between_clock(departure_time, next_start_time) if departure_time and next_start_time else None
        if consistent_gap is not None and 1 <= consistent_gap <= 12 * 60:
            transport_minutes = consistent_gap
            arrival_time = next_start_time
            duration_label = f"約{transport_minutes}分"
            route_source = "phase2_time_gap_priority" if not service_hint else "phase2_train_bridge_time_gap_priority"
            if not one_point or one_point == "-":
                one_point = "構造化データ上の時刻差分を優先して移動時間を整合"
        else:
            arrival_time = _add_minutes_to_clock(departure_time, transport_minutes)

        route_url = build_google_maps_dir_url(origin_name, destination_name, transport_mode if transport_mode != "air" else "train")
        transport_row = {
            "day": int(current.get("day", 1) or 1),
            "sequence": float(current.get("sequence", idx + 1) or idx + 1) + 0.5,
            "date": departure_date,
            "start_time": departure_time,
            "end_time": arrival_time,
            "destination": f"{origin_name} → {destination_name}",
            "purpose": "transport",
            "genre": "transport",
            "duration_minutes": transport_minutes,
            "is_transport": True,
            "transport_mode": transport_mode if transport_mode != "air" else "train",
            "one_point": one_point,
            "address": "",
            "route_from": origin_name,
            "route_to": destination_name,
            "route_url": route_url,
            "route_data_source": route_source,
            "estimated_duration_label": duration_label,
            "route_departure_at": f"{departure_date} {departure_time}".strip(),
        }
        rows.append(transport_row)

    df3 = pd.DataFrame(rows)
    if "day" in df3.columns and "sequence" in df3.columns:
        df3 = df3.sort_values(["day", "sequence"], kind="stable").reset_index(drop=True)
        df3["sequence"] = df3.groupby("day").cumcount() + 1

    return df3


def approve_and_build_phase2_phase3() -> None:
    if not st.session_state.trip_plan_draft:
        raise ValueError("了承対象の旅程案がありません。")

    s = st.session_state.planning_state
    trip_plan = st.session_state.trip_plan_draft

    log_event("Phase2", "構造化を開始")
    structurer = Phase2Structuring(logger=log_event)
    df2 = structurer.structure_trip_plan(trip_plan, s["start_date"])
    if df2 is None or df2.empty:
        raise ValueError("フェーズ2で構造化データを生成できませんでした。")

    df2 = normalize_phase2_dataframe(df2, s)

    # --- 修正箇所: Phase3 は destination の意味を増やさず、構造化データの順番だけで移動カードを生成 ---
    log_event("Phase3", f"順番ベースの移動カード生成を開始。transport_style={s['transport_style']}")
    df3 = build_phase3_from_sequential_destinations(df2, s)
    if df3 is None or df3.empty:
        raise ValueError("フェーズ3で最終旅程表を生成できませんでした。")

    df3 = _trim_rows_after_terminal_return(df3, s)

    gap_messages = inspect_transport_step_gaps(df3)
    if gap_messages:
        for msg in gap_messages:
            log_event("検査", msg, level="warning")
    else:
        log_event("検査", "スポット間の移動カード欠落は検出されませんでした。")

    validation_result = st.session_state.get("validation_agent_result")
    validation_source_plan_text = safe_text(st.session_state.get("validation_source_plan_text"), "")
    autofix_summary: List[str] = []
    overlap_candidates: List[Dict[str, object]] = []
    if isinstance(validation_result, dict) and validation_result and validation_source_plan_text == safe_text(trip_plan, ""):
        df3, autofix_summary, overlap_candidates = _apply_phase35_safe_autofix(df3, validation_result)
        for note in autofix_summary:
            log_event("Phase3.5", note, level="info")
    elif isinstance(validation_result, dict) and validation_result:
        log_event("Phase3.5", "検証結果の元になった旅程案が現在の了承案と異なるため、自動反映をスキップ", level="warning")

    st.session_state.validation_autofix_summary = autofix_summary
    st.session_state.validation_time_overlap_candidates = overlap_candidates

    st.session_state.trip_plan = trip_plan
    st.session_state.df_phase2 = df2
    st.session_state.df_phase3 = df3
    st.session_state.execution_engine = ExecutionEngine(df3)
    st.session_state.plan_approved = True
    st.session_state.active_tab = "final_itinerary"


def normalize_phase2_dataframe(df: pd.DataFrame, planning_state: Dict) -> pd.DataFrame:
    # --- 修正箇所: Phase2の構造化結果を優先し、destination をむやみに上書きしない ---
    df = df.copy().reset_index(drop=True)

    required_cols = {
        "day": 1,
        "sequence": 1,
        "date": planning_state["start_date"],
        "start_time": planning_state["departure_time"],
        "end_time": planning_state["departure_time"],
        "destination": "",
        "purpose": "activity",
        "genre": "general",
        "duration_minutes": 30,
        "is_transport": False,
        "transport_mode": None,
        "one_point": "",
        "address": "",
        "route_from": "",
        "route_to": "",
        "route_url": "",
        "route_data_source": "",
        "estimated_duration_label": "",
    }
    for col, default in required_cols.items():
        if col not in df.columns:
            df[col] = default

    unique_days = sorted(df["day"].dropna().unique().tolist())
    day_mapping = {old: idx + 1 for idx, old in enumerate(unique_days)}
    df["day"] = df["day"].map(day_mapping).fillna(1).astype(int)

    activity_idx = df.index[df["is_transport"] == False].tolist()  # noqa: E712
    if activity_idx:
        first_idx = activity_idx[0]
        if safe_text(df.at[first_idx, "destination"], "") in {"", "-"}:
            df.at[first_idx, "destination"] = planning_state["departure_place"]
        if safe_text(df.at[first_idx, "start_time"], "") in {"", "-"}:
            df.at[first_idx, "start_time"] = planning_state["departure_time"]

    if activity_idx:
        last_idx = activity_idx[-1]
        if planning_state.get("return_place") and safe_text(df.at[last_idx, "destination"], "") in {"", "-"}:
            df.at[last_idx, "destination"] = planning_state["return_place"]

    # --- 修正箇所: Phase2安定化。新幹線・列車サービス名だけの transport 行はここで除外する ---
    drop_mask = df.apply(lambda row: safe_text(row.get("purpose"), "").lower() == "transport" and _is_transport_service_like_destination(safe_text(row.get("destination"), "")), axis=1)
    if drop_mask.any():
        dropped = [safe_text(v, "") for v in df.loc[drop_mask, "destination"].tolist()]
        for dest in dropped:
            log_event("Phase2正規化", f"列車サービス名の transport 行を除外: {dest}", level="info")
        df = df.loc[~drop_mask].reset_index(drop=True)

    # --- 修正箇所: 曖昧destination（エリア等）を最低限補正 ---
    df = _repair_ambiguous_destinations(df)
    # --- 修正箇所: 昼食/夕食文脈の行は shopping系施設でも meal を優先保持 ---
    df = _protect_meal_rows(df)
    # --- 修正箇所: 自然文見出しが destination に混入した invalid node 名を安全に補正 ---
    df = _normalize_invalid_node_names(df, planning_state)

    if planning_state["hotel_required"]:
        has_hotel = df.apply(lambda row: _is_valid_hotel_row(row), axis=1).any()
        if not has_hotel:
            insert_hotel_row(df)

    # --- 修正箇所: Phase2の既存時刻を尊重しつつ整合を取り、複数日はホテルカードを補完 ---
    df = rebuild_phase2_time_consistency(df)
    df = ensure_daily_hotel_rows(df, planning_state)
    df = _propagate_hotel_names(df, planning_state)
    df = rebuild_phase2_time_consistency(df)
    if "day" in df.columns and "sequence" in df.columns:
        df = df.sort_values(["day", "sequence"], kind="stable").reset_index(drop=True)
        df["sequence"] = df.groupby("day").cumcount() + 1
    return df.reset_index(drop=True)


def insert_hotel_row(df: pd.DataFrame) -> None:
    if df.empty:
        return

    hotel_row = {
        "day": int(df["day"].max()),
        "sequence": int(df["sequence"].max()) + 1 if "sequence" in df.columns else len(df) + 1,
        "date": safe_text(df.iloc[-1].get("date")),
        "start_time": "20:00",
        "end_time": "21:00",
        "destination": "宿泊ホテル",
        "purpose": "hotel",
        "genre": "hotel",
        "duration_minutes": 60,
        "is_transport": False,
        "transport_mode": None,
        "one_point": "旅の動線を考えて無理のない宿泊先を確保",
        "address": "",
    }
    df.loc[len(df)] = hotel_row


def get_card_style(row_dict: Dict, current_step: int | None, absolute_idx: int | None) -> tuple[str, str]:
    status = safe_text(row_dict.get("execution_status"), "pending")
    if status == "cancelled":
        return "vf-card-completed", "キャンセル"
    if current_step is not None and absolute_idx == current_step:
        return "vf-card-current", "進行中"
    note_text = safe_text(row_dict.get("modification_note"), "")
    is_modified = bool(row_dict.get("is_modified_by_event", False)) or note_text not in {"", "-"}
    if is_modified:
        return "vf-card-modified", "変更あり"
    if status == "completed":
        return "vf-card-completed", "完了"
    return "vf-card-future", "これから"


def apply_transport_change_to_plan(step_index: int, new_mode: str) -> Dict[str, str]:
    df = st.session_state.df_phase3
    if df is None or df.empty:
        return {"message": "旅程データがありません。"}

    engine = ExecutionEngine(df)
    result = engine.update_transport_step(step_index, new_mode, reason="ユーザーが完成旅程で移動手段を変更")
    st.session_state.df_phase3 = engine.get_updated_dataframe()
    st.session_state.execution_engine = ExecutionEngine(st.session_state.df_phase3)
    return result


def apply_transport_change_during_execution(step_index: int, new_mode: str) -> Dict[str, str]:
    engine = st.session_state.execution_engine
    if engine is None:
        return {"message": "実行エンジンが未初期化です。"}
    return engine.update_transport_step(step_index, new_mode, reason="ユーザーが実行中に移動手段を変更")


def _activity_position_from_phase3(df_phase3: pd.DataFrame, absolute_idx: int) -> Optional[int]:
    if df_phase3 is None or df_phase3.empty or absolute_idx < 0 or absolute_idx >= len(df_phase3):
        return None
    activity_positions = df_phase3.index[df_phase3["is_transport"] == False].tolist()  # noqa: E712
    try:
        return activity_positions.index(absolute_idx)
    except ValueError:
        return None


def rebuild_final_itinerary_from_phase2(updated_df2: pd.DataFrame, reason: str) -> Dict[str, str]:
    if updated_df2 is None or updated_df2.empty:
        raise ValueError("構造化データが空のため完成旅程を再構築できません。")

    normalized_df2 = normalize_phase2_dataframe(updated_df2.copy(), st.session_state.planning_state)
    # --- 修正箇所: 編集後の再構築でも順番ベース移動生成ロジックを維持 ---
    df3 = build_phase3_from_sequential_destinations(normalized_df2, st.session_state.planning_state)
    if df3 is None or df3.empty:
        raise ValueError("完成旅程の再構築に失敗しました。")

    st.session_state.df_phase2 = normalized_df2.reset_index(drop=True)
    st.session_state.df_phase3 = df3.reset_index(drop=True)
    st.session_state.execution_engine = ExecutionEngine(st.session_state.df_phase3)
    log_event("完成旅程編集", reason)
    return {"message": reason}


def delete_spot_from_plan(activity_position: int) -> Dict[str, str]:
    df2 = st.session_state.get("df_phase2")
    if df2 is None or df2.empty:
        raise ValueError("構造化データがありません。")
    activity_idx = df2.index[df2["is_transport"] == False].tolist()  # noqa: E712
    if activity_position is None or activity_position < 0 or activity_position >= len(activity_idx):
        raise ValueError("削除対象スポットを特定できません。")
    if len(activity_idx) <= 1:
        raise ValueError("最後の1件は削除できません。")

    target_idx = activity_idx[activity_position]
    target_name = safe_text(df2.iloc[target_idx].get("destination"))
    updated_df2 = df2.drop(index=target_idx).reset_index(drop=True)
    return rebuild_final_itinerary_from_phase2(updated_df2, f"スポットを削除しました: {target_name}")


def update_spot_in_plan(activity_position: int, new_destination: str, new_purpose: str = "", new_one_point: str = "") -> Dict[str, str]:
    df2 = st.session_state.get("df_phase2")
    if df2 is None or df2.empty:
        raise ValueError("構造化データがありません。")
    activity_idx = df2.index[df2["is_transport"] == False].tolist()  # noqa: E712
    if activity_position is None or activity_position < 0 or activity_position >= len(activity_idx):
        raise ValueError("変更対象スポットを特定できません。")

    target_idx = activity_idx[activity_position]
    updated_df2 = df2.copy()
    updated_df2.at[target_idx, "destination"] = new_destination.strip()
    if str(new_purpose).strip():
        updated_df2.at[target_idx, "purpose"] = new_purpose.strip()
    if str(new_one_point).strip():
        updated_df2.at[target_idx, "one_point"] = new_one_point.strip()

    return rebuild_final_itinerary_from_phase2(updated_df2, f"スポットを変更しました: {new_destination.strip()}")


def run_mood_change_action(engine: ExecutionEngine, action: str, free_text: str = "") -> None:
    detail_map = {
        "寄り道": ("mood_change", "近くで短時間の寄り道候補を出して、残り旅程に無理がない形で提案して。"),
        "次の予定をキャンセル": ("cancel", "次の予定をキャンセルして、この先だけを調整して。"),
        "その日の予定をキャンセル": ("cancel", "その日の残り予定をキャンセルして、以降を調整して。"),
        "全体キャンセルして帰路へ": ("cancel", "全体キャンセルして帰路へ変更して。"),
        "移動手段変更": ("mood_change", "移動手段を変更したい。徒歩を減らして楽な移動を優先して提案して。"),
    }

    if action == "自由会話":
        request = str(free_text).strip()
        if not request:
            raise ValueError("自由会話の内容を入力してください。")
        generate_execution_replan_preview(request, source_event="mood_change")
        st.session_state.show_mood_dialog = False
        return

    event_type, detail = detail_map[action]
    st.session_state.event_result = engine.trigger_event(event_type, detail)
    st.session_state.show_mood_dialog = False


def render_planning_summary() -> None:
    s = st.session_state.planning_state

    st.markdown("### 現在の確定条件")
    c1, c2, c3 = st.columns(3)
    c1.metric("出発地", s["departure_place"])
    c2.metric("帰着地", s["return_place"])
    c3.metric("出発時間", s["departure_time"])

    c4, c5, c6 = st.columns(3)
    resolved = st.session_state.get("resolved_conditions", {})
    display_days = resolved.get("trip_days_final", s["trip_days"])
    c4.metric("旅行日数", f"{display_days}日")
    c5.metric("移動スタイル", s["transport_style"])
    c6.metric("予算感", s["budget_style"])

    primary_destination = safe_text(s.get("primary_destination"), "未指定")
    overview = build_trip_overview_from_state(s)
    st.caption(f"主目的地: {primary_destination} / ホテル必須: {'あり' if s['hotel_required'] else 'なし'}")
    if overview:
        st.caption(f"旅の概要: {overview}")

    if s["conversation_notes"]:
        st.markdown("**相談メモ**")
        for note in s["conversation_notes"][-5:]:
            st.write(f"- {note}")

    if s["revision_requests"]:
        st.markdown("**追加修正依頼**")
        for note in s["revision_requests"][-5:]:
            st.write(f"- {note}")


def render_chat_history() -> None:
    st.markdown("### 旅行相談")
    if not st.session_state.chat_history:
        st.info("まず条件を少しずつ決めていきましょう。")
        first_q = conversation_advisor_questions()[0]
        append_chat("assistant", first_q)

    for item in st.session_state.chat_history:
        if item["role"] == "user":
            st.markdown(f"<div class='vf-chat-user'><b>あなた</b><br>{item['content']}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='vf-chat-ai'><b>VoyageFlow</b><br>{item['content']}</div>", unsafe_allow_html=True)


def render_timeline_visibility_controls(scope: str, title: str = "表示オプション") -> None:
    hide_completed_key = f"hide_completed_{scope}"
    hide_cancelled_key = f"hide_cancelled_{scope}"
    if hide_completed_key not in st.session_state:
        st.session_state[hide_completed_key] = False
    if hide_cancelled_key not in st.session_state:
        st.session_state[hide_cancelled_key] = False

    with st.expander(f"🗂️ {title}", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            st.checkbox("終了行程を隠す", key=hide_completed_key)
        with c2:
            st.checkbox("キャンセル行程を隠す", key=hide_cancelled_key)




# =========================================================
# 修正箇所: タクシー移動向け Uber 導線
# =========================================================
def build_uber_ride_url(origin_name: str, destination_name: str) -> str:
    pickup = str(origin_name or '').strip()
    dropoff = str(destination_name or '').strip()
    params = {
        'action': 'setPickup',
        'pickup': 'my_location',
    }
    if pickup:
        params['pickup[nickname]'] = pickup
    if dropoff:
        params['dropoff[formatted_address]'] = dropoff
        params['dropoff[nickname]'] = dropoff
    return 'https://m.uber.com/ul/?' + urllib.parse.urlencode(params)

def _format_highlight_comment_html(text: str) -> str:
    text = safe_text(text, "")
    if not text:
        return ""

    escaped = html.escape(text)
    return re.sub(
        r"\*\*(.*?)\*\*",
        lambda m: f"<span style='font-weight:700;color:#b45309;'>{m.group(1)}</span>",
        escaped,
    )


# =========================================================
# 修正箇所: スポット最新情報リンク（安全版）
# - Phase2 / Phase3 の構造化データには一切触らない
# - LLMにイベント名を作らせず、まずは公式確認リンクだけをスポットカード下部に表示
# - 固定辞書にないスポットはカテゴリ推定 + Google検索リンクでフォールバック
# =========================================================
SPOT_INFO_SOURCES = {
    "東京国立博物館": {"type": "museum", "url": "https://www.tnm.jp/modules/r_calender/index.php", "label": "展示・イベント情報を見る"},
    "国立西洋美術館": {"type": "museum", "url": "https://www.nmwa.go.jp/jp/exhibitions/", "label": "展覧会情報を見る"},
    "歌舞伎座": {"type": "theater", "url": "https://www.kabuki-bito.jp/theaters/kabukiza/", "label": "公演・演目を見る"},
    "GINZA SIX": {"type": "commercial_complex", "url": "https://ginza6.tokyo/news/news_category/events", "label": "イベント情報を見る"},
    "東京ディズニーリゾート": {"type": "theme_park", "url": "https://www.tokyodisneyresort.jp/tdr/event.html", "label": "イベント情報を見る"},
    "東京ディズニーランド": {"type": "theme_park", "url": "https://www.tokyodisneyresort.jp/tdl/event.html", "label": "イベント情報を見る"},
    "東京ディズニーシー": {"type": "theme_park", "url": "https://www.tokyodisneyresort.jp/tds/event.html", "label": "イベント情報を見る"},
    "東京スカイツリー": {"type": "commercial_complex", "url": "https://www.tokyo-skytree.jp/event/", "label": "イベント情報を見る"},
    "東京ソラマチ": {"type": "commercial_complex", "url": "https://www.tokyo-solamachi.jp/event/", "label": "イベント情報を見る"},
    "上野恩賜公園": {"type": "park", "url": "https://www.tokyo-park.or.jp/park/ueno/", "label": "公園情報を見る"},
    "浅草寺": {"type": "shrine_temple", "url": "https://www.senso-ji.jp/", "label": "公式情報を見る"},
}


def _guess_spot_category(name: str) -> str:
    text = safe_text(name, "")
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


def _spot_latest_info_search_url(destination: str, visit_date: str, category: str) -> tuple[str, str]:
    name = safe_text(destination, "")
    date_text = safe_text(visit_date, "")
    date_suffix = f" {date_text}" if date_text and date_text != "-" else ""

    if category == "museum":
        query = f"{name} 展覧会 イベント 公式{date_suffix}"
        label = "展示・イベント情報を調べる"
    elif category == "theater":
        query = f"{name} 公演 演目 公式{date_suffix}"
        label = "公演・演目情報を調べる"
    elif category == "commercial_complex":
        query = f"{name} イベント 公式{date_suffix}"
        label = "イベント情報を調べる"
    elif category == "park":
        query = f"{name} イベント 見頃 公式{date_suffix}"
        label = "イベント・見頃情報を調べる"
    elif category == "shrine_temple":
        query = f"{name} 行事 拝観時間 公式{date_suffix}"
        label = "行事・拝観情報を調べる"
    elif category == "restaurant":
        query = f"{name} 営業時間 予約 公式{date_suffix}"
        label = "営業・予約情報を調べる"
    else:
        query = f"{name} 公式 最新情報{date_suffix}"
        label = "公式情報を調べる"

    return label, "https://www.google.com/search?q=" + urllib.parse.quote(query)


def render_spot_latest_info(destination: str, visit_date: str = "") -> None:
    name = safe_text(destination, "")
    if not name or name == "-":
        return

    # ホテル行は既存のホテル導線と混ざるため、この軽量リンク表示では対象外にする。
    if _is_hotel_like_name(name):
        return

    for key, info in SPOT_INFO_SOURCES.items():
        if key in name:
            st.markdown("**🔎 最新情報**")
            st.link_button(safe_text(info.get("label"), "公式情報を見る"), safe_text(info.get("url"), ""), use_container_width=True)
            return

    category = _guess_spot_category(name)
    label, url = _spot_latest_info_search_url(name, visit_date, category)
    st.markdown("**🔎 最新情報**")
    st.link_button(label, url, use_container_width=True)



# =========================================================
# 修正箇所: 完成旅程の簡易一覧表示
# - 既存カード表示は残し、表示モードとして追加するだけ
# - スポット/移動/ホテルを色分けし、Google Maps / Uber / ホテル予約リンクだけを残す\n# - v6.2.43: 内容列の重複表示を解消し、スポット名リンクはMapsではなく公式情報リンクを優先
# - v6.2.44: 簡易一覧の移動表示ルールを確定反映（電車のみ駅間表示、その他は手段のみ）
# - v6.2.45: 簡易一覧をスマホ向けに圧縮（目的/最新情報列削除、操作アイコン短縮）
# - v6.2.46: 徒歩自動判定（表示のみ）を追加。近接スポットは「徒歩候補」として表示し、旅程本体は変更しない
# =========================================================
def _simple_row_html_class(row_dict: Dict[str, object], is_transport: bool) -> str:
    status = safe_text(row_dict.get("execution_status"), "").lower()
    if status == "cancelled":
        return "vf-simple-row-cancelled"
    if is_transport:
        return "vf-simple-row-transport"
    if _is_hotel_like_name(safe_text(row_dict.get("destination"), "")) or _is_valid_hotel_row(row_dict):
        return "vf-simple-row-hotel"
    return "vf-simple-row-spot"


def _simple_transport_origin_destination(row_dict: Dict[str, object]) -> tuple[str, str]:
    route_from = safe_text(row_dict.get("route_from"), "")
    route_to = safe_text(row_dict.get("route_to"), "")
    if route_from and route_to and route_from != "-" and route_to != "-":
        return route_from, route_to

    destination_text = safe_text(row_dict.get("destination"), "")
    if "→" in destination_text:
        left, right = [part.strip() for part in destination_text.split("→", 1)]
        return safe_text(left, "現在地"), safe_text(right, destination_text)

    one_point = safe_text(row_dict.get("one_point"), "")
    if "→" in one_point:
        left, right = [part.strip() for part in one_point.split("→", 1)]
        return safe_text(left, "現在地"), safe_text(right, destination_text)

    return "現在地", destination_text or "目的地"


def _simple_transport_mode_label(row_dict: Dict[str, object]) -> str:
    # --- 修正箇所(v6.2.44): 簡易一覧では route_from→route_to を混ぜず、手段名だけ返す ---
    mode = safe_text(row_dict.get("transport_mode"), "")
    destination_text = safe_text(row_dict.get("destination"), "")
    one_point = safe_text(row_dict.get("one_point"), "")
    display = safe_text(build_transport_display_safe(row_dict), "")
    combined = " ".join([mode, destination_text, one_point, display]).lower()

    if any(token in combined for token in ["taxi", "タクシー"]):
        return "タクシー"
    if any(token in combined for token in ["walk", "walking", "徒歩"]):
        return "徒歩"
    if any(token in combined for token in ["bus", "バス"]):
        return "バス"
    if any(token in combined for token in ["train", "transit", "rail", "電車", "列車", "新幹線"]):
        return "電車"
    if any(token in combined for token in ["air", "flight", "飛行機", "航空", "フライト"]):
        return "飛行機"
    if any(token in combined for token in ["ship", "ferry", "船", "フェリー"]):
        return "船"
    if any(token in combined for token in ["car", "車", "レンタカー", "自家用車"]):
        return "車"

    mode_map = {
        "walk": "徒歩",
        "walking": "徒歩",
        "train": "電車",
        "transit": "公共交通",
        "taxi": "タクシー",
        "car": "車",
        "private_car": "自家用車",
        "rental_car": "レンタカー",
        "bus": "バス",
        "air": "飛行機",
        "ship": "船",
    }
    return mode_map.get(mode.lower(), mode or "移動")


def _simple_extract_station_name(value: str) -> str:
    # --- 修正箇所(v6.2.44): 電車表示用に文字列から「〇〇駅」だけを抽出する ---
    text = safe_text(value, "")
    if not text or text == "-":
        return ""
    text = re.sub(r"[（(].*?[）)]", "", text).strip()
    candidates = re.findall(r"[一-龥ぁ-んァ-ヶA-Za-z0-9ー・･\s]+?駅", text)
    if candidates:
        cleaned = [re.sub(r"\s+", "", c).strip(" ・･、,/") for c in candidates if c.strip()]
        if cleaned:
            return cleaned[-1]
    return text if text.endswith("駅") else ""


def _simple_infer_walk_area_tokens(value: str) -> set[str]:
    # --- 修正箇所(v6.2.46): 簡易一覧だけで使う徒歩候補判定用のエリア推定 ---
    # 旅程データは変更しない。あくまで表示の「徒歩候補」判定に限定する。
    text = safe_text(value, "")
    if not text or text == "-":
        return set()

    explicit_tokens = [
        "銀座", "東銀座", "有楽町", "日比谷", "丸の内", "東京駅", "新橋",
        "上野", "御徒町", "浅草", "押上", "渋谷", "原宿", "表参道",
        "新宿", "初台", "六本木", "赤坂", "青山", "豊洲", "お台場",
        "名古屋", "名駅", "栄", "大須", "熱田", "金山",
    ]
    tokens = {token for token in explicit_tokens if token in text}

    alias_map = {
        "歌舞伎座": {"銀座", "東銀座"},
        "GINZA SIX": {"銀座"},
        "ギンザシックス": {"銀座"},
        "銀座木村家": {"銀座"},
        "三井ガーデンホテル銀座プレミア": {"銀座", "新橋"},
        "シアタークリエ": {"日比谷", "有楽町"},
        "帝国ホテル": {"日比谷", "有楽町"},
        "東京宝塚劇場": {"日比谷", "有楽町"},
        "上野アメ横商店街": {"上野", "御徒町"},
        "アメ横": {"上野", "御徒町"},
        "浅草寺": {"浅草"},
        "雷門": {"浅草"},
        "渋谷スクランブルスクエア": {"渋谷"},
        "SHIBUYA SKY": {"渋谷"},
        "新国立劇場": {"初台", "新宿"},
        "名古屋城": {"名古屋"},
        "大須商店街": {"大須"},
        "オアシス21": {"栄"},
    }
    for key, values in alias_map.items():
        if key in text:
            tokens.update(values)
    return tokens


def _simple_should_show_walk_candidate(row_dict: Dict[str, object], origin: str, destination: str, mode_label: str) -> bool:
    # --- 修正箇所(v6.2.46): 徒歩自動判定（表示のみ） ---
    # Google Maps APIなしでの安全な簡易判定。確定移動手段は書き換えず、簡易一覧だけ「徒歩候補」と表示する。
    if mode_label in {"徒歩", "飛行機", "船", "新幹線"}:
        return False

    origin_text = safe_text(origin, "")
    destination_text = safe_text(destination, "")
    combined = f"{origin_text} {destination_text} {safe_text(row_dict.get('destination'), '')} {safe_text(row_dict.get('one_point'), '')}"

    # 大移動・駅間移動は徒歩候補にしない
    long_distance_tokens = ["福井", "金沢", "京都", "大阪", "名古屋", "新幹線", "空港", "フライト", "航空"]
    if any(token in combined for token in long_distance_tokens) and not any(token in combined for token in ["栄", "大須", "名駅"]):
        return False

    origin_station = _simple_extract_station_name(origin_text)
    dest_station = _simple_extract_station_name(destination_text)
    if origin_station and dest_station and origin_station != dest_station:
        # すでに駅間として成立している電車表示は維持
        return False

    origin_areas = _simple_infer_walk_area_tokens(origin_text)
    dest_areas = _simple_infer_walk_area_tokens(destination_text)
    if origin_areas and dest_areas and (origin_areas & dest_areas):
        return True

    # 終了・開始の差が短い近接移動は候補扱い。ただし駅名が絡む長距離は上で除外済み。
    start_min = _time_to_minutes(safe_text(row_dict.get("start_time"), ""))
    end_min = _time_to_minutes(safe_text(row_dict.get("end_time"), ""))
    if start_min is not None and end_min is not None:
        duration = end_min - start_min
        if 1 <= duration <= 12 and mode_label in {"タクシー", "車", "バス", "移動"}:
            return True

    return False


def _simple_transport_content_label(row_dict: Dict[str, object], origin: str, destination: str, mode_label: str) -> str:
    # --- 修正箇所(v6.2.44/v6.2.46): 簡易一覧の移動表示ルールを確定 ---
    # ルール:
    # - 徒歩候補に該当する近接移動は「徒歩候補」と表示（旅程本体は変更しない）
    # - 電車のみ「電車：最寄り駅→最寄り駅」
    # - タクシー/徒歩/バス/その他は手段のみ
    # - 前後スポット名は内容列に出さない
    if _simple_should_show_walk_candidate(row_dict, origin, destination, mode_label):
        return "徒歩候補"
    if mode_label == "電車":
        from_station = _simple_extract_station_name(origin)
        to_station = _simple_extract_station_name(destination)
        if from_station and to_station:
            return f"電車：{from_station}→{to_station}"
        if from_station or to_station:
            return f"電車：{from_station or '最寄り駅'}→{to_station or '最寄り駅'}"
        return "電車：最寄り駅→最寄り駅"
    return mode_label or "移動"


def _build_hotel_booking_search_url(hotel_name: str, visit_date: str = "") -> str:
    name = safe_text(hotel_name, "ホテル")
    date_part = safe_text(visit_date, "")
    query = f"{name} ホテル 予約"
    if date_part and date_part != "-":
        query += f" {date_part}"
    return "https://www.google.com/search?q=" + urllib.parse.quote(query)


def _simple_latest_info_headline(destination: str, visit_date: str = "") -> str:
    name = safe_text(destination, "")
    if not name or name == "-" or _is_hotel_like_name(name):
        return ""
    for key, info in SPOT_INFO_SOURCES.items():
        if key in name:
            return safe_text(info.get("label"), "公式情報あり")
    category = _guess_spot_category(name)
    if category == "museum":
        return "展示・イベント確認"
    if category == "theater":
        return "公演・演目確認"
    if category == "commercial_complex":
        return "イベント確認"
    if category == "park":
        return "開園・見頃確認"
    if category == "shrine_temple":
        return "行事・拝観確認"
    return "公式情報確認"


def _simple_spot_info_url(destination: str, visit_date: str = "") -> str:
    # --- 修正箇所: 簡易一覧のスポット名リンクはMapsではなく公式情報/公式検索を優先 ---
    name = safe_text(destination, "")
    if not name or name == "-" or _is_hotel_like_name(name):
        return ""
    for key, info in SPOT_INFO_SOURCES.items():
        if key in name:
            return safe_text(info.get("url"), "")
    category = _guess_spot_category(name)
    _, url = _spot_latest_info_search_url(name, visit_date, category)
    return url


def _simple_action_link(label: str, url: str) -> str:
    clean_url = html.escape(safe_text(url, ""), quote=True)
    clean_label = html.escape(safe_text(label, ""))
    if not clean_url or clean_url == "-" or not clean_label:
        return ""
    return f'<a class="vf-simple-btn" href="{clean_url}" target="_blank" rel="noopener noreferrer">{clean_label}</a>'


def render_simple_itinerary_table(df: pd.DataFrame, city_hint: str = "") -> None:
    if df is None or df.empty:
        st.info("旅程データがありません。")
        return

    working = df.copy().reset_index(drop=True)
    if "day" in working.columns and "sequence" in working.columns:
        working = working.sort_values(["day", "sequence"], kind="stable").reset_index(drop=True)

    rows_html: List[str] = []
    current_day = None
    for _, row in working.iterrows():
        row_dict = row.to_dict()
        day = row_dict.get("day")
        day_int = int(day) if pd.notna(day) else 1
        date_text = safe_text(row_dict.get("date"), "")
        if current_day != day_int:
            current_day = day_int
            rows_html.append(
                "<tr class='vf-simple-day-row'>"
                f"<td colspan='5' style='background:#f8fafc;color:#344054;border:1px solid #e4e7ec;border-radius:10px;font-weight:800;'>Day {day_int} - {html.escape(date_text)}</td>"
                "</tr>"
            )

        start_time = html.escape(safe_text(row_dict.get("start_time"), "-"))
        end_time = html.escape(safe_text(row_dict.get("end_time"), "-"))
        is_transport = bool(row_dict.get("is_transport", False))
        row_class = _simple_row_html_class(row_dict, is_transport)

        if is_transport:
            origin, destination = _simple_transport_origin_destination(row_dict)
            mode_label = _simple_transport_mode_label(row_dict)
            transport_mode = safe_text(row_dict.get("transport_mode"), "").lower()
            route_url = safe_text(row_dict.get("route_url"), "")
            if not route_url or route_url == "-":
                route_url = build_google_maps_dir_url(origin, destination, transport_mode or "transit")
            # 内容列は確定ルールで表示する。
            # - 徒歩候補に該当する近接移動は「徒歩候補」
            # - 電車のみ「電車：最寄り駅→最寄り駅」
            # - タクシー/徒歩/バス/その他は手段のみ
            content_label = _simple_transport_content_label(row_dict, origin, destination, mode_label)
            actions = [
                _simple_action_link("🗺️", route_url),
            ]
            if content_label != "徒歩候補" and (transport_mode == "taxi" or "タクシー" in mode_label):
                actions.append(_simple_action_link("🚕", build_uber_ride_url(origin, destination)))
            content_html = f"<div class='vf-simple-main'>{html.escape(content_label)}</div>"
            purpose_html = "移動"
            latest_html = ""
            type_html = "<span class='vf-simple-chip'>移動</span>"
            action_html = "<div class='vf-simple-action'>" + "".join(actions) + "</div>"
        else:
            destination_name = safe_text(row_dict.get("destination"), "-")
            place_url = build_google_maps_search_url(destination_name)
            is_hotel = _is_hotel_like_name(destination_name) or _is_valid_hotel_row(row_dict)
            purpose = format_purpose(row_dict.get("purpose"))
            latest = "ホテル予約確認" if is_hotel else _simple_latest_info_headline(destination_name, date_text)
            actions = [_simple_action_link("🗺️", place_url)]
            if is_hotel:
                actions.append(_simple_action_link("🏨", _build_hotel_booking_search_url(destination_name, date_text)))

            # スポット名リンクはMapsではなく公式情報/公式検索を優先。Mapsはアクション列だけに残す。
            spot_info_url = "" if is_hotel else _simple_spot_info_url(destination_name, date_text)
            if spot_info_url:
                content_html = (
                    f"<div class='vf-simple-main'><a href='{html.escape(spot_info_url, quote=True)}' target='_blank' rel='noopener noreferrer' style='color:inherit;text-decoration:underline;'>{html.escape(destination_name)}</a></div>"
                )
            else:
                content_html = f"<div class='vf-simple-main'>{html.escape(destination_name)}</div>"
            purpose_html = html.escape(purpose)
            latest_html = html.escape(latest)
            type_html = "<span class='vf-simple-chip'>ホテル</span>" if is_hotel else "<span class='vf-simple-chip'>スポット</span>"
            action_html = "<div class='vf-simple-action'>" + "".join(actions) + "</div>"

        rows_html.append(
            f"<tr class='{row_class}'>"
            f"<td>{start_time}</td>"
            f"<td>{end_time}</td>"
            f"<td>{type_html}</td>"
            f"<td>{content_html}</td>"
            f"<td>{action_html}</td>"
            "</tr>"
        )

    table_html = """
<div class="vf-simple-table-wrap">
<table class="vf-simple-table">
  <thead>
    <tr>
      <th>開始</th>
      <th>終了</th>
      <th>種別</th>
      <th>内容</th>
      <th>操作</th>
    </tr>
  </thead>
  <tbody>
""" + "\n".join(rows_html) + """
  </tbody>
</table>
</div>
"""
    st.markdown(table_html, unsafe_allow_html=True)



def render_simple_itinerary_page() -> None:
    # --- 修正箇所: 簡易一覧を完成旅程タブ内の追加表示ではなく、疑似画面遷移ページとして表示 ---
    st.title("📋 簡易旅程一覧")
    st.caption("スマホでも見やすいよう、目的・最新情報列を省いた簡易ビューです。近接移動は表示上だけ『徒歩候補』として出します。")

    top_left, top_right = st.columns([1, 2])
    with top_left:
        if st.button("⬅ 完成旅程に戻る", use_container_width=True, key="back_to_final_itinerary_from_simple"):
            st.session_state.simple_itinerary_page_mode = False
            st.session_state.active_tab = "final_itinerary"
            st.rerun()
    with top_right:
        st.info("表示専用の簡易ビューです。旅程の変更・削除は戻ってカード表示から行ってください。")

    df = st.session_state.get("df_phase3")
    if df is None or df.empty:
        st.warning("簡易表示できる完成旅程がありません。")
        return

    render_simple_itinerary_table(
        df.copy().reset_index(drop=True),
        city_hint=safe_text(st.session_state.planning_state.get("primary_destination"), ""),
    )


def render_itinerary_cards(
    df: pd.DataFrame,
    current_step: int | None = None,
    allow_transport_edit: bool = False,
    transport_edit_scope: str = "plan",
    hide_completed: bool = False,
    hide_cancelled: bool = False,
) -> None:
    if df is None or df.empty:
        st.info("旅程データがありません。")
        return

    mode_options = {
        "walk": "徒歩",
        "train": "電車",
        "taxi": "タクシー",
        "private_car": "自家用車",
        "rental_car": "レンタカー",
        "bike": "自転車",
    }

    for day in sorted(df["day"].dropna().unique()):
        # reset_index() で元の絶対インデックスを保持しておく。
        # 以前は day / sequence から逆引きしていたため、
        # 同じ sequence を持つ行が複数あると Streamlit key が衝突していた。
        day_df = df[df["day"] == day].reset_index().rename(columns={"index": "_absolute_idx"})
        if hide_completed and "execution_status" in day_df.columns:
            day_df = day_df[day_df["execution_status"] != "completed"]
        if hide_cancelled and "execution_status" in day_df.columns:
            day_df = day_df[day_df["execution_status"] != "cancelled"]
        date_label = safe_text(day_df.iloc[0].get("date")) if not day_df.empty else "-"
        hidden_bits = []
        if hide_completed:
            hidden_bits.append("終了")
        if hide_cancelled:
            hidden_bits.append("キャンセル")
        suffix = f"（{'・'.join(hidden_bits)}を非表示）" if hidden_bits else ""

        with st.expander(f"Day {int(day)} - {date_label}{suffix}", expanded=(int(day) == 1)):
            if day_df.empty:
                st.caption("この日は非表示対象の行程のみです。")
                continue
            for local_pos, (_, row) in enumerate(day_df.iterrows()):
                row_dict = row.to_dict()
                is_transport = bool(row_dict.get("is_transport", False))
                absolute_idx = int(row_dict.get("_absolute_idx")) if pd.notna(row_dict.get("_absolute_idx")) else None

                current_badge = ""
                if current_step is not None and absolute_idx == current_step:
                    current_badge = " ← 今ここ"

                card_class, status_label = get_card_style(row_dict, current_step, absolute_idx)

                if is_transport:
                    destination_text = safe_text(row_dict.get("destination"))
                    if "→" in destination_text:
                        origin, destination = [part.strip() for part in destination_text.split("→", 1)]
                    else:
                        origin, destination = "現在地", destination_text

                    route_url = safe_text(row_dict.get("route_url"), "")
                    if not route_url or route_url == "-":
                        route_url = build_google_maps_dir_url(
                            origin,
                            destination,
                            safe_text(row_dict.get("transport_mode"), "walking").lower(),
                        )

                    note = safe_text(row_dict.get("modification_note"), "")
                    status_text = f"状態: {status_label}"
                    transport_display = build_transport_display_safe(row_dict)
                    route_source_text = build_route_source_text(row_dict)
                    body = f"""
<div class="vf-card {card_class}">
  <div><b>🚗 {safe_text(row_dict.get('start_time'))} - {safe_text(row_dict.get('end_time'))}{current_badge}</b></div>
  <div>{status_text}</div>
  <div>移動手段: {transport_display}</div>
  <div>{html.escape(route_source_text)}</div>
</div>
"""
                    st.markdown(body, unsafe_allow_html=True)
                    if status_label == "キャンセル":
                        st.markdown("<div class='vf-card-note' style='font-weight:700;background:#ececec;color:#555;'>キャンセル</div>", unsafe_allow_html=True)
                    if note:
                        st.markdown(f"<div class='vf-card-note'>差分: {note}</div>", unsafe_allow_html=True)
                    st.link_button("🗺️ Google Mapsでルートを見る", route_url, use_container_width=True)

                    # 修正箇所: タクシー移動カードのときだけ Uber 導線を表示
                    current_transport_mode = safe_text(row_dict.get("transport_mode"), "").lower()
                    if current_transport_mode == "taxi":
                        uber_url = build_uber_ride_url(origin, destination)
                        st.caption("タクシー移動です。移動開始の数分前に Uber を予約するとスムーズです。")
                        st.link_button("🚕 Uberで配車予約", uber_url, use_container_width=True)

                    if allow_transport_edit and absolute_idx is not None:
                        with st.expander(f"移動手段を変更 Day{int(day)}-Step{absolute_idx + 1}", expanded=False):
                            current_mode = safe_text(row_dict.get("transport_mode"), "walk").lower()
                            if current_mode == "car":
                                current_mode = "private_car"
                            selection_key = f"transport_choice_{transport_edit_scope}_{absolute_idx}"
                            if selection_key not in st.session_state:
                                st.session_state[selection_key] = current_mode if current_mode in mode_options else "walk"

                            rental_info = get_rental_car_availability(df, absolute_idx)
                            rental_available = bool(rental_info.get("available"))

                            cols = st.columns(len(mode_options))
                            for col, (mode_key, mode_label_button) in zip(cols, mode_options.items()):
                                disabled = (mode_key == "rental_car" and not rental_available)
                                selected = st.session_state.get(selection_key) == mode_key
                                label = f"✅ {mode_label_button}" if selected else mode_label_button
                                if col.button(label, key=f"pick_{transport_edit_scope}_{day}_{absolute_idx}_{local_pos}_{mode_key}", use_container_width=True, disabled=disabled):
                                    st.session_state[selection_key] = mode_key
                                    st.rerun()

                            selected_mode = st.session_state.get(selection_key, current_mode)
                            selected_label = mode_options.get(selected_mode, selected_mode)
                            st.caption(f"選択中: {selected_label}")

                            if rental_available:
                                shop_names = [str(shop.get("name")) for shop in rental_info.get("shops", [])[:3] if shop.get("name")]
                                if shop_names:
                                    st.caption(f"レンタカー候補: {' / '.join(shop_names)}")
                            else:
                                st.markdown(
                                    "<div style='padding:8px 10px;border-radius:8px;background:#f1f3f5;color:#6c757d;border:1px solid #d9dee3;margin:6px 0 10px 0;'>レンタカーはグレーアウト中です。周囲1km以内に営業所がないか、位置情報を確認できません。</div>",
                                    unsafe_allow_html=True,
                                )
                                reason = safe_text(rental_info.get("reason"), "周囲1km以内にレンタカー営業所が見つかりません。")
                                st.caption(reason)

                            apply_disabled = selected_mode == "rental_car" and not rental_available
                            if st.button("この移動手段に変更", key=f"apply_transport_{transport_edit_scope}_{day}_{absolute_idx}_{local_pos}", use_container_width=True, disabled=apply_disabled):
                                try:
                                    if transport_edit_scope == "plan":
                                        result = apply_transport_change_to_plan(absolute_idx, selected_mode)
                                    else:
                                        result = apply_transport_change_during_execution(absolute_idx, selected_mode)
                                    st.success(result.get("message", "移動手段を変更しました。"))
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"移動変更エラー: {e}")
                                    if st.session_state.debug_mode:
                                        st.exception(e)
                else:
                    place_url = build_google_maps_search_url(safe_text(row_dict.get("destination")))
                    one_point = safe_text(row_dict.get("one_point"), "")
                    note = safe_text(row_dict.get("modification_note"), "")
                    purpose = format_purpose(row_dict.get("purpose"))
                    stay_text = safe_text(row_dict.get("stay_duration"), "")
                    if not stay_text or stay_text == "-":
                        stay_minutes = row_dict.get("stay_minutes")
                        if pd.notna(stay_minutes):
                            stay_text = f"{int(float(stay_minutes))}分"
                    if not stay_text or stay_text == "-":
                        start_time = safe_text(row_dict.get("start_time"), "")
                        end_time = safe_text(row_dict.get("end_time"), "")
                        if start_time and end_time:
                            stay_text = f"{start_time} - {end_time}"
                    comment_html = _format_highlight_comment_html(one_point)
                    destination = html.escape(safe_text(row_dict.get("destination")))
                    time_text = html.escape(safe_text(row_dict.get("start_time")))
                    purpose_html = html.escape(purpose)
                    stay_html = html.escape(stay_text) if stay_text else "-"
                    comment_block = f'<div style="margin-top:6px;">{comment_html}</div>' if comment_html else ""
                    body = f"""
<div class="vf-card {card_class}">
  <div style="font-size:1.05rem;font-weight:800;color:#1d4ed8;margin-bottom:6px;">📍 {time_text} - {destination}{current_badge}</div>
  <div>状態: {status_label}</div>
  <div>目的: {purpose_html}</div>
  <div>滞在時間: {stay_html}</div>
  {comment_block}
</div>
"""
                    st.markdown(body, unsafe_allow_html=True)
                    if status_label == "キャンセル":
                        st.markdown("<div class='vf-card-note' style='font-weight:700;background:#ececec;color:#555;'>キャンセル</div>", unsafe_allow_html=True)
                    if note:
                        st.markdown(f"<div class='vf-card-note'>差分: {note}</div>", unsafe_allow_html=True)
                    st.link_button("📍 Google Mapsで場所を見る", place_url, use_container_width=True)
                    # 修正箇所: スポットカード下部に最新情報の公式確認リンクだけを追加
                    render_spot_latest_info(safe_text(row_dict.get("destination"), ""), safe_text(row_dict.get("date"), ""))

                    if transport_edit_scope == "plan" and absolute_idx is not None:
                        activity_position = _activity_position_from_phase3(df, absolute_idx)
                        edit_key = f"plan_spot_edit_{absolute_idx}"
                        current_destination_text = safe_text(row_dict.get("destination"), "")
                        current_purpose_text = safe_text(row_dict.get("purpose"), "")
                        current_comment_text = safe_text(row_dict.get("one_point"), "")

                        if f"{edit_key}_destination" not in st.session_state:
                            st.session_state[f"{edit_key}_destination"] = current_destination_text
                        if f"{edit_key}_purpose" not in st.session_state:
                            st.session_state[f"{edit_key}_purpose"] = current_purpose_text
                        if f"{edit_key}_comment" not in st.session_state:
                            st.session_state[f"{edit_key}_comment"] = current_comment_text

                        with st.expander("このスポットを編集", expanded=False):
                            edit_cols = st.columns(2)
                            with edit_cols[0]:
                                if st.button("このスポットを削除", key=f"delete_spot_{absolute_idx}_{local_pos}", use_container_width=True):
                                    try:
                                        result = delete_spot_from_plan(activity_position)
                                        st.success(result.get("message", "スポットを削除しました。"))
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"スポット削除エラー: {e}")
                                        if st.session_state.debug_mode:
                                            st.exception(e)
                            with edit_cols[1]:
                                st.caption("削除すると、このスポットに関連する完成旅程を再構築します。")

                            st.text_input("変更後のスポット名", key=f"{edit_key}_destination")
                            st.text_input("変更後の目的（任意）", key=f"{edit_key}_purpose")
                            st.text_area("変更後のワンポイント（任意）", key=f"{edit_key}_comment", height=90)

                            if st.button("この内容でスポット変更", key=f"update_spot_{absolute_idx}_{local_pos}", use_container_width=True):
                                try:
                                    new_destination_value = str(st.session_state.get(f"{edit_key}_destination", "")).strip()
                                    if not new_destination_value:
                                        st.warning("変更後のスポット名を入力してください。")
                                    else:
                                        result = update_spot_in_plan(
                                            activity_position,
                                            new_destination_value,
                                            str(st.session_state.get(f"{edit_key}_purpose", "")).strip(),
                                            str(st.session_state.get(f"{edit_key}_comment", "")).strip(),
                                        )
                                        st.success(result.get("message", "スポットを変更しました。"))
                                        st.rerun()
                                except Exception as e:
                                    st.error(f"スポット変更エラー: {e}")
                                    if st.session_state.debug_mode:
                                        st.exception(e)

def status_emoji(status: str) -> str:
    mapping = {
        "completed": "✅",
        "in_progress": "👉",
        "rerouted": "🔀",
        "pending": "⏳",
        "cancelled": "🚫",
    }
    return mapping.get(status, "⏳")




# =========================================================
# 修正箇所: Gemini transport resolver A/Bテスト（サイドバー診断専用）
# - 本番のtransport行にはまだ接続しない
# - A案: 移動時間 + 手段だけを取得
# - B案: 経路詳細も取得
# - 失敗しても既存旅程・UI・カード表示には影響しない
# =========================================================
def _build_gemini_transport_resolver_prompt(
    origin: str,
    destination: str,
    departure_datetime: str,
    mode_hint: str,
    detail_level: str,
) -> str:
    origin_text = safe_text(origin, "")
    destination_text = safe_text(destination, "")
    departure_text = safe_text(departure_datetime, "")
    mode_text = safe_text(mode_hint, "自動")
    detail_text = "minimal" if detail_level == "minimal" else "detailed"

    if detail_text == "minimal":
        output_schema = """
{
  "ok": true,
  "confidence": "high|medium|low",
  "duration_minutes": 165,
  "mode": "train|bus|walk|taxi|car|air|ship|unknown",
  "summary": "北陸新幹線などを利用する想定。乗換がある場合は1行で補足。",
  "evidence_note": "Google Maps等で最終確認が必要。API実測ではなくGemini推定。"
}
""".strip()
        instruction = """
返す情報は最小限にしてください。
駅名・路線名・乗換駅などの詳細は、確度が高い場合のみsummaryに1行で含めてください。
duration_minutes は現実的な移動時間にしてください。
例: 福井駅→京都駅が20分のような明らかに不自然な値は禁止です。
""".strip()
    else:
        output_schema = """
{
  "ok": true,
  "confidence": "high|medium|low",
  "duration_minutes": 165,
  "mode": "train|bus|walk|taxi|car|air|ship|unknown",
  "summary": "全体の経路要約",
  "route_title": "推定ルート名",
  "steps": [
    {
      "from": "出発地または駅",
      "to": "到着地または駅",
      "mode": "walk|train|bus|taxi|car|air|ship|unknown",
      "line": "路線名・便名。なければ空文字",
      "duration_minutes": 10,
      "note": "乗換・徒歩などの補足"
    }
  ],
  "transfer_count": 1,
  "evidence_note": "Google Maps等で最終確認が必要。API実測ではなくGemini推定。"
}
""".strip()
        instruction = """
経路詳細も返してください。
ただし、不明な駅名・路線名・乗換駅を断定しないでください。
不確実な場合は confidence を low にし、line や note に「要確認」と明示してください。
duration_minutes は steps の合計と大きく矛盾しないようにしてください。
例: 福井駅→京都駅が20分のような明らかに不自然な値は禁止です。
""".strip()

    return f"""
あなたは旅行AIエージェント VoyageFlow の transport resolver です。
目的は、旅程内の transport 行に使う移動時間と移動手段を、破綻しない範囲で推定することです。

重要:
- あなたの出力はAPI実測ではなく推定です。
- 不確かな情報は断定しないでください。
- 既存コード側で制御するため、出力は必ずJSONのみ。
- Markdown、説明文、コードフェンスは禁止。
- 日本国内の公共交通は、常識的な所要時間にしてください。
- 明らかに短すぎる移動時間を出さないでください。
- 指定時刻に運行がありそうか不明な場合は、その旨を evidence_note に書いてください。

入力:
- 出発地: {origin_text}
- 到着地: {destination_text}
- 出発日時: {departure_text}
- 手段ヒント: {mode_text}
- 詳細レベル: {detail_text}

追加指示:
{instruction}

出力JSON形式:
{output_schema}
""".strip()


def _normalize_gemini_transport_result(data: Dict[str, object], detail_level: str) -> Dict[str, object]:
    if not isinstance(data, dict):
        data = {}

    def _safe_int(value, default: Optional[int] = None) -> Optional[int]:
        try:
            if value is None or value == "":
                return default
            return int(float(value))
        except Exception:
            return default

    allowed_modes = {"train", "bus", "walk", "taxi", "car", "air", "ship", "unknown"}
    allowed_confidence = {"high", "medium", "low"}

    mode = safe_text(data.get("mode"), "unknown").lower()
    if mode not in allowed_modes:
        mode = _infer_mode_from_service_hint(mode, "unknown")
        if mode not in allowed_modes:
            mode = "unknown"

    confidence = safe_text(data.get("confidence"), "low").lower()
    if confidence not in allowed_confidence:
        confidence = "low"

    duration_minutes = _safe_int(data.get("duration_minutes"), None)
    if duration_minutes is not None:
        duration_minutes = max(1, min(duration_minutes, 24 * 60))

    normalized: Dict[str, object] = {
        "ok": bool(data.get("ok", True)) if data else False,
        "resolver": "gemini_transport_resolver",
        "detail_level": detail_level,
        "confidence": confidence,
        "duration_minutes": duration_minutes,
        "mode": mode,
        "summary": safe_text(data.get("summary"), ""),
        "evidence_note": safe_text(data.get("evidence_note"), "Gemini推定のため、Google Maps等で最終確認してください。"),
    }

    if detail_level == "detailed":
        raw_steps = data.get("steps") if isinstance(data.get("steps"), list) else []
        steps = []
        total_from_steps = 0
        for step in raw_steps[:12]:
            if not isinstance(step, dict):
                continue
            step_minutes = _safe_int(step.get("duration_minutes"), None)
            if step_minutes is not None:
                step_minutes = max(1, min(step_minutes, 24 * 60))
                total_from_steps += step_minutes
            step_mode = safe_text(step.get("mode"), "unknown").lower()
            if step_mode not in allowed_modes:
                step_mode = _infer_mode_from_service_hint(step_mode, "unknown")
                if step_mode not in allowed_modes:
                    step_mode = "unknown"
            steps.append({
                "from": safe_text(step.get("from"), ""),
                "to": safe_text(step.get("to"), ""),
                "mode": step_mode,
                "line": safe_text(step.get("line"), ""),
                "duration_minutes": step_minutes,
                "note": safe_text(step.get("note"), ""),
            })
        normalized["route_title"] = safe_text(data.get("route_title"), "")
        normalized["steps"] = steps
        normalized["transfer_count"] = _safe_int(data.get("transfer_count"), None)
        normalized["steps_duration_total"] = total_from_steps or None

    return normalized


def resolve_transport_with_gemini_for_test(
    origin: str,
    destination: str,
    departure_datetime: str,
    mode_hint: str = "自動",
    detail_level: str = "minimal",
) -> Dict[str, object]:
    prompt = _build_gemini_transport_resolver_prompt(
        origin=origin,
        destination=destination,
        departure_datetime=departure_datetime,
        mode_hint=mode_hint,
        detail_level=detail_level,
    )
    started_at = datetime.now()
    try:
        generator = Phase1Generator(logger=log_event)
        raw = generator.generate_trip_plan(prompt, temperature=0.0).strip()
        parsed = _safe_json_extract(raw) or {}
        normalized = _normalize_gemini_transport_result(parsed, detail_level=detail_level)
        normalized["raw"] = raw
        normalized["elapsed_seconds"] = round((datetime.now() - started_at).total_seconds(), 2)
        normalized["fallback_used"] = False
        return normalized
    except Exception as e:
        log_event("GeminiTransport診断", f"{detail_level} resolver失敗: {e}", level="warning")
        return {
            "ok": False,
            "resolver": "gemini_transport_resolver",
            "detail_level": detail_level,
            "confidence": "low",
            "duration_minutes": None,
            "mode": "unknown",
            "summary": "",
            "evidence_note": "Gemini resolver の実行に失敗しました。本番実装時は既存Routes/Directions/距離推定へfallbackします。",
            "error": str(e),
            "elapsed_seconds": round((datetime.now() - started_at).total_seconds(), 2),
            "fallback_used": True,
        }


def _render_gemini_transport_result_card(title: str, result: Dict[str, object]) -> None:
    st.markdown(f"**{title}**")
    if not result:
        st.caption("まだ実行結果がありません。")
        return

    summary_payload = {
        "ok": result.get("ok"),
        "detail_level": result.get("detail_level"),
        "confidence": result.get("confidence"),
        "duration_minutes": result.get("duration_minutes"),
        "mode": result.get("mode"),
        "summary": result.get("summary"),
        "evidence_note": result.get("evidence_note"),
        "elapsed_seconds": result.get("elapsed_seconds"),
        "fallback_used": result.get("fallback_used"),
    }
    if result.get("error"):
        summary_payload["error"] = result.get("error")
    if result.get("route_title"):
        summary_payload["route_title"] = result.get("route_title")
    if result.get("transfer_count") is not None:
        summary_payload["transfer_count"] = result.get("transfer_count")
    if result.get("steps_duration_total") is not None:
        summary_payload["steps_duration_total"] = result.get("steps_duration_total")

    st.json(summary_payload)

    steps = result.get("steps") if isinstance(result.get("steps"), list) else []
    if steps:
        st.markdown("**推定ステップ**")
        for idx, step in enumerate(steps, start=1):
            st.write(
                f"{idx}. {safe_text(step.get('from'), '')} → {safe_text(step.get('to'), '')} / "
                f"{safe_text(step.get('mode'), 'unknown')} / {safe_text(step.get('line'), '')} / "
                f"{safe_text(step.get('duration_minutes'), '-')}分"
            )
            note = safe_text(step.get("note"), "")
            if note and note != "-":
                st.caption(note)

    with st.expander("Gemini raw output", expanded=False):
        st.code(safe_text(result.get("raw"), ""), language="json")


def render_gemini_transport_ab_test_panel() -> None:
    # --- 修正箇所: 左側固定スペースでA/B両方を検証するだけ。本番transportには未接続。 ---
    with st.expander("🧪 Gemini Transport A/Bテスト", expanded=False):
        st.caption("診断専用です。ここでの結果は完成旅程・実行シミュレーションへ自動反映しません。")
        ab_origin = st.text_input("Gemini 出発地", value="福井駅", key="gemini_transport_ab_origin")
        ab_destination = st.text_input("Gemini 到着地", value="京都駅", key="gemini_transport_ab_destination")
        ab_departure = st.text_input(
            "Gemini 出発日時 (YYYY-MM-DD HH:MM)",
            value="2026-04-30 13:00",
            key="gemini_transport_ab_departure",
        )
        ab_mode_hint = st.selectbox(
            "Gemini 手段ヒント",
            options=["自動", "train", "bus", "walk", "taxi", "car", "air", "ship"],
            index=0,
            key="gemini_transport_ab_mode_hint",
        )

        col_a, col_b = st.columns(2)
        with col_a:
            run_minimal = st.button("A案: 時間+手段だけ", use_container_width=True, key="run_gemini_transport_minimal")
        with col_b:
            run_detailed = st.button("B案: 経路詳細も取得", use_container_width=True, key="run_gemini_transport_detailed")

        if st.button("A/B両方を実行", use_container_width=True, key="run_gemini_transport_both"):
            run_minimal = True
            run_detailed = True

        if run_minimal:
            st.session_state["gemini_transport_minimal_result"] = resolve_transport_with_gemini_for_test(
                origin=ab_origin,
                destination=ab_destination,
                departure_datetime=ab_departure,
                mode_hint=ab_mode_hint,
                detail_level="minimal",
            )

        if run_detailed:
            st.session_state["gemini_transport_detailed_result"] = resolve_transport_with_gemini_for_test(
                origin=ab_origin,
                destination=ab_destination,
                departure_datetime=ab_departure,
                mode_hint=ab_mode_hint,
                detail_level="detailed",
            )

        st.divider()
        _render_gemini_transport_result_card(
            "A案: 移動時間 + 手段だけ",
            st.session_state.get("gemini_transport_minimal_result", {}),
        )
        st.divider()
        _render_gemini_transport_result_card(
            "B案: 経路詳細も取得",
            st.session_state.get("gemini_transport_detailed_result", {}),
        )


# =========================================================
# サイドバー
# =========================================================
with st.sidebar:
    st.title("⚙️ 設定")
    st.session_state.temperature = st.slider("Gemini 生成温度", 0.0, 1.0, st.session_state.temperature, 0.1)
    st.session_state.debug_mode = st.checkbox("デバッグモード", value=st.session_state.debug_mode)

    st.divider()
    render_internal_logs_sidebar()

    st.divider()
    st.markdown("### VoyageFlow")
    st.caption("モデル: models/gemini-3.1-flash-lite-preview")

    # --- 修正箇所: Gemini transport resolver A/Bテストをサイドバー固定スペースへ追加 ---
    render_gemini_transport_ab_test_panel()

    # --- 修正箇所: Routes API 診断ボタンをサイドバーに追加 ---
    with st.expander("🛠 Routes診断", expanded=False):
        diag_origin = st.text_input("出発地", value="福井駅", key="routes_diag_origin")
        diag_destination = st.text_input("到着地", value="東京駅", key="routes_diag_destination")
        diag_mode = st.selectbox("移動手段", options=["train", "walk", "car", "taxi", "bike"], index=0, key="routes_diag_mode")
        diag_departure = st.text_input("出発日時 (YYYY-MM-DD HH:MM)", value="2026-04-19 12:05", key="routes_diag_departure")

        if st.button("🚨 Routes診断を実行", use_container_width=True, key="run_routes_diagnostic"):
            try:
                from route_diagnostic import geocode_place, ROUTES_URL
                import requests
                api_key = st.secrets.get("MAPS_API_KEY") or os.getenv("MAPS_API_KEY")
                if not api_key:
                    st.error("MAPS_API_KEY が見つかりません。Secrets または環境変数を確認してください。")
                else:
                    origin_raw = str(diag_origin or "")
                    destination_raw = str(diag_destination or "")
                    origin_clean = origin_raw.strip()
                    destination_clean = destination_raw.strip()
                    departure_raw = str(diag_departure or "").strip()
                    departure_iso = parse_route_diagnostic_departure_iso(departure_raw)

                    st.write("geocode入力値")
                    st.json({
                        "origin_raw": origin_raw,
                        "origin_clean": origin_clean,
                        "destination_raw": destination_raw,
                        "destination_clean": destination_clean,
                        "mode": diag_mode,
                        "departure_raw": departure_raw,
                        "departure_iso": departure_iso or departure_raw,
                    })

                    origin = geocode_place(origin_clean, api_key)
                    destination = geocode_place(destination_clean, api_key)
                    st.write("geocode結果")
                    st.json({"origin": origin, "destination": destination})
                    if not origin or not destination:
                        st.error("地名解決に失敗しました。まずは geocode入力値 の origin_clean / destination_clean が駅名やスポット名だけになっているか確認してください。")
                    else:
                        body = build_route_diagnostic_body(origin, destination, diag_mode, departure_raw)
                        headers = {
                            "Content-Type": "application/json",
                            "X-Goog-Api-Key": api_key,
                            # 診断ではまずレスポンス全体を確認する
                            "X-Goog-FieldMask": "*",
                        }
                        masked_headers = dict(headers)
                        if masked_headers.get("X-Goog-Api-Key"):
                            raw_key = str(masked_headers["X-Goog-Api-Key"])
                            if len(raw_key) > 8:
                                masked_headers["X-Goog-Api-Key"] = raw_key[:4] + "..." + raw_key[-4:]
                            else:
                                masked_headers["X-Goog-Api-Key"] = "***"
                        st.write("request headers")
                        st.json(masked_headers)
                        st.write("request body")
                        st.json(body)
                        response = requests.post(ROUTES_URL, json=body, headers=headers, timeout=20)
                        st.write(f"HTTP status: {response.status_code}")
                        st.write("response headers")
                        st.json(dict(response.headers))
                        st.write("response text")
                        st.code(response.text or "<empty response>", language="json")
                        try:
                            data = response.json() if response.text.strip() else {}
                        except Exception:
                            data = {"raw_text": response.text}
                        st.write("response")
                        st.json(data)
                        routes = data.get("routes") if isinstance(data, dict) else None
                        if isinstance(routes, list):
                            st.write("routes件数")
                            st.write(len(routes))
                            if routes:
                                first = routes[0]
                                st.write("1件目の要約")
                                st.json({
                                    "distanceMeters": first.get("distanceMeters"),
                                    "duration": first.get("duration"),
                                    "legs_count": len(first.get("legs", []) or []),
                                    "has_polyline": bool(((first.get("polyline") or {}).get("encodedPolyline"))),
                                })
            except Exception as e:
                st.error(f"Routes診断エラー: {e}")

    # --- 修正箇所: Google Directions API (Legacy) 単体診断をサイドバーに追加 ---
    with st.expander("🧪 Google Directions診断", expanded=False):
        gd_origin = st.text_input("Directions 出発地", value="東京駅", key="gd_diag_origin")
        gd_destination = st.text_input("Directions 到着地", value="国立博物館", key="gd_diag_destination")
        gd_mode = st.selectbox(
            "Directions 移動手段",
            options=["train", "bus", "walk", "car", "taxi"],
            index=0,
            key="gd_diag_mode",
        )
        gd_departure = st.text_input(
            "Directions 出発日時 (YYYY-MM-DD HH:MM)",
            value="2026-04-30 10:00",
            key="gd_diag_departure",
        )

        if st.button("🧪 Directions診断を実行", use_container_width=True, key="run_google_directions_diag"):
            try:
                api_key = _get_maps_api_key()
                st.write("APIキー状態")
                st.json({
                    "has_api_key": bool(api_key),
                    "api_key_preview": (api_key[:4] + "..." + api_key[-4:]) if api_key and len(api_key) > 8 else ("***" if api_key else ""),
                })
                if not api_key:
                    st.error("MAPS_API_KEY が見つかりません。Secrets または環境変数を確認してください。")
                else:
                    origin_raw = str(gd_origin or "")
                    destination_raw = str(gd_destination or "")
                    origin_clean = _normalize_route_query_name(origin_raw)
                    destination_clean = _normalize_route_query_name(destination_raw)
                    query_origin = _build_google_directions_location_query(origin_clean, None, None)
                    query_destination = _build_google_directions_location_query(destination_clean, None, None)
                    departure_raw = str(gd_departure or "").strip()
                    api_mode = _google_directions_mode_for_transport(gd_mode)

                    st.write("入力正規化")
                    st.json({
                        "origin_raw": origin_raw,
                        "origin_clean": origin_clean,
                        "origin_query": query_origin,
                        "destination_raw": destination_raw,
                        "destination_clean": destination_clean,
                        "destination_query": query_destination,
                        "transport_mode": gd_mode,
                        "api_mode": api_mode,
                        "departure": departure_raw,
                    })

                    result, debug_info = _fetch_google_directions_legacy(
                        query_origin,
                        query_destination,
                        gd_mode,
                        departure_raw[:10] if len(departure_raw) >= 10 else "",
                        departure_raw[11:16] if len(departure_raw) >= 16 else "09:00",
                        return_debug=True,
                    )
                    st.write("GoogleDirections 生レスポンス診断")
                    st.json(debug_info or {})
                    st.write("Directions結果（整形済み）")
                    st.json(result or {})

                    if not result:
                        st.warning("Directions API から結果を取得できませんでした。上の GoogleDirections 生レスポンス診断 を確認してください。")
                    else:
                        st.markdown("**診断サマリー**")
                        st.json({
                            "source": result.get("source"),
                            "mode": result.get("mode"),
                            "minutes": result.get("minutes"),
                            "distance_meters": result.get("distance_meters"),
                            "fare_text": result.get("fare_text"),
                            "summary": result.get("summary"),
                            "steps_count": len(result.get("steps") or []),
                            "has_transit_steps": any((step.get("travel_mode") == "TRANSIT") for step in (result.get("steps") or [])),
                        })
                        steps = result.get("steps") or []
                        if steps:
                            st.markdown("**ステップ詳細**")
                            for idx, step in enumerate(steps, start=1):
                                st.write(f"{idx}. {step.get('travel_mode')} / {step.get('duration_text')} / {step.get('instruction_text')}")
                                if step.get("transit_details"):
                                    st.json(step.get("transit_details"))
            except Exception as e:
                st.error(f"Directions診断エラー: {e}")

    if st.button("🔄 全リセット", use_container_width=True):
        reset_all()
        st.rerun()



# =========================================================
# 修正箇所: 簡易一覧ページへの疑似画面遷移
# - Streamlitの別ウインドウではなく、session_stateで安全に全画面相当へ切り替える
# - 既存タブや完成旅程カード表示は変更しない
# =========================================================
if st.session_state.get("simple_itinerary_page_mode", False):
    render_simple_itinerary_page()
    st.stop()

# =========================================================
# タブ
# =========================================================
tab_labels = {
    "travel_consultation": "🗣️ 旅行相談",
    "plan_review": "📄 プラン確認",
    "final_itinerary": "🛣️ 完成旅程",
    "execution": "🎬 実行シミュレーション",
}
tab_keys = list(tab_labels.keys())
default_index = tab_keys.index(st.session_state.active_tab) if st.session_state.active_tab in tab_keys else 0

tabs = st.tabs([tab_labels[k] for k in tab_keys])


# --- 修正箇所: テスト時にバージョンが見えるヘッダー ---
st.markdown(
    f"""
<div style="padding:12px 14px;border-radius:12px;background:#f8fafc;border:1px solid #dbe5f0;margin-bottom:10px;">
  <div style="font-size:1.6rem;font-weight:800;">✈️ {APP_DISPLAY_NAME}</div>
  <div style="font-size:0.95rem;color:#475569;margin-top:4px;">バージョン: {APP_VERSION_NAME} / 更新日: {APP_UPDATED_DATE}</div>
</div>
""",
    unsafe_allow_html=True,
)
st.markdown(
    """
<div class="vf-tip">
相談しながら条件を決めて、まずは自然文の旅行案を作成し、了承後に構造化・経路補完へ進みます。
</div>
""",
    unsafe_allow_html=True,
)

# Streamlit tabs are not programmatically switchable in a strict sense,
# so current active tab is reflected mainly by workflow guidance and session state.


# =========================================================
# タブ1: 旅行相談
# =========================================================
with tabs[0]:
    st.header("旅行相談")

    left, right = st.columns([1.4, 1.0])

    with left:
        st.markdown("### 基本条件")
        c1, c2, c3 = st.columns(3)
        with c1:
            departure_place = st.text_input(
                "出発地",
                value=st.session_state.planning_state["departure_place"],
                key="departure_place_input"
            )
        with c2:
            return_place = st.text_input(
                "帰着地",
                value=st.session_state.planning_state["return_place"],
                key="return_place_input"
            )
        with c3:
            default_t = datetime.strptime(st.session_state.planning_state["departure_time"], "%H:%M").time()
            departure_time_value = st.time_input(
                "出発時間",
                value=default_t,
                key="departure_time_input"
            )

        c4, c5, c6 = st.columns(3)
        with c4:
            start_date = st.date_input(
                "開始日",
                value=datetime.strptime(st.session_state.planning_state["start_date"], "%Y-%m-%d").date(),
                key="start_date_input"
            )
        with c5:
            trip_days = st.number_input(
                "旅行日数",
                min_value=1,
                max_value=7,
                value=int(st.session_state.planning_state["trip_days"]),
                step=1,
                key="trip_days_input"
            )
        with c6:
            hotel_required = st.checkbox(
                "ホテルを必須にする",
                value=st.session_state.planning_state["hotel_required"],
                key="hotel_required_input"
            )

        st.session_state.planning_state["departure_place"] = departure_place
        st.session_state.planning_state["return_place"] = return_place
        st.session_state.planning_state["departure_time"] = departure_time_value.strftime("%H:%M")
        st.session_state.planning_state["start_date"] = start_date.strftime("%Y-%m-%d")
        st.session_state.planning_state["trip_days"] = int(trip_days)
        st.session_state.planning_state["hotel_required"] = bool(hotel_required)

        st.markdown("### 移動スタイル")
        transport_style = st.radio(
            "移動スタイルを選んでください",
            ["自動（おすすめ）", "徒歩メイン", "電車メイン", "タクシー", "レンタカー"],
            index=["自動（おすすめ）", "徒歩メイン", "電車メイン", "タクシー", "レンタカー"].index(
                st.session_state.planning_state["transport_style"]
            )
            if st.session_state.planning_state["transport_style"] in ["自動（おすすめ）", "徒歩メイン", "電車メイン", "タクシー", "レンタカー"]
            else 0,
            key="transport_style_input",
        )
        st.session_state.planning_state["transport_style"] = transport_style

        budget_style = st.radio(
            "予算感",
            ["節約", "普通", "贅沢"],
            index=["節約", "普通", "贅沢"].index(st.session_state.planning_state["budget_style"])
            if st.session_state.planning_state["budget_style"] in ["節約", "普通", "贅沢"]
            else 1,
            horizontal=True,
            key="budget_style_input",
        )
        st.session_state.planning_state["budget_style"] = budget_style

        st.divider()
        render_chat_history()


        user_message = st.chat_input("希望や修正を自然文で入力してください")
        if user_message:
            # --- 修正箇所: 旅行相談は「曖昧性検出 → 1問だけ確認」へ ---
            append_chat("user", user_message)
            st.session_state.pending_ambiguity = None
            update_planning_state_from_user_text(user_message)

            current_state = st.session_state.planning_state
            known = {
                "destination": safe_text(current_state.get("primary_destination"), ""),
                "trip_days": str(current_state.get("trip_days", "")) if current_state.get("trip_days") else "",
                "departure_place": safe_text(current_state.get("departure_place"), ""),
                "transport_style": safe_text(current_state.get("transport_style"), ""),
                "budget_style": safe_text(current_state.get("budget_style"), ""),
            }
            ambiguities = detect_ambiguities_from_context(user_message, current_state)
            missing_fields = get_missing_hearing_fields(current_state)

            if ambiguities:
                st.session_state.pending_ambiguity = ambiguities[0]
                reply = generate_hearing_reply_with_llm(user_message, known, ambiguities, missing_fields)
                append_chat("assistant", reply)
                st.rerun()

            confirmation_payload = None if st.session_state.get("pending_confirmation") else build_confirmation_payload_from_state()
            if confirmation_payload and not missing_fields:
                st.session_state.pending_confirmation = confirmation_payload
                append_chat("assistant", confirmation_payload["message"])
                st.rerun()

            reply = generate_hearing_reply_with_llm(user_message, known, [], missing_fields)
            append_chat("assistant", reply)
            st.rerun()

        pending_ambiguity = st.session_state.get("pending_ambiguity")
        if pending_ambiguity:
            st.caption(f"確認中の曖昧点: {pending_ambiguity.get('type', 'unknown')}")
        pending_confirmation = st.session_state.get("pending_confirmation")
        if pending_confirmation:
            st.info(pending_confirmation.get("message", "確認が必要です。"))
            confirm_col1, confirm_col2 = st.columns(2)
            with confirm_col1:
                if st.button("✅ この条件で続ける", key="accept_pending_confirmation", use_container_width=True):
                    apply_confirmation_payload(pending_confirmation)
                    st.session_state.pending_confirmation = None
                    st.session_state.advisor_done = True
                    append_chat("assistant", "ありがとうございます。この条件で計画を続けます。")
                    st.rerun()
            with confirm_col2:
                if st.button("✏️ 条件を修正する", key="reject_pending_confirmation", use_container_width=True):
                    st.session_state.pending_confirmation = None
                    append_chat("assistant", "了解です。条件を修正してください。修正後に改めて確認します。")
                    st.rerun()

        st.divider()
        b1, b2 = st.columns(2)
        with b1:
            if st.button("🪄 旅行案を作成", use_container_width=True):
                if st.session_state.get("pending_confirmation"):
                    st.warning("確認待ちです。上の『この条件で続ける』または『条件を修正する』を選んでください。")
                else:
                    try:
                        generate_phase1_draft()
                        st.success("旅行案を作成しました。次の『プラン確認』タブで確認してください。")
                    except Exception as e:
                        st.error(f"旅行案作成エラー: {e}")
                        if st.session_state.debug_mode:
                            st.exception(e)

        with b2:
            if st.button("🔁 旅行案を再作成", use_container_width=True):
                if st.session_state.get("pending_confirmation"):
                    st.warning("確認待ちです。上の『この条件で続ける』または『条件を修正する』を選んでください。")
                else:
                    try:
                        generate_phase1_draft()
                        st.success("修正内容を反映して旅行案を再作成しました。")
                    except Exception as e:
                        st.error(f"旅行案再作成エラー: {e}")
                        if st.session_state.debug_mode:
                            st.exception(e)

    with right:
        render_planning_summary()

    if st.session_state.trip_plan_draft:
        st.info("旅行案ができています。上の『📄 プラン確認』タブへ進んで確認してください。")


# =========================================================
# タブ2: プラン確認
# =========================================================
with tabs[1]:
    st.header("プラン確認")

    if st.session_state.trip_plan_draft:
        st.success("相談内容をもとに作成した自由記述の旅行案です。")
        st.markdown("### Phase1: 自由記述の旅行案")
        st.markdown(format_phase1_preview_text(st.session_state.trip_plan_draft), unsafe_allow_html=True)

        st.info("※移動時間や所要時間は目安です。完成旅程では、実際の移動経路や実時間にあわせて調整して表示します。")

        render_mock_weather_panel(st.session_state.planning_state, context_label="plan")

        with st.expander("Phase1 に渡した最終プロンプトを見る", expanded=False):
            st.code(st.session_state.phase1_prompt_text, language="text")

        st.divider()
        st.markdown("### この案への追加修正")

        revision_text = st.text_area(
            "例: もっと体験型を増やして / 2日目は移動をゆったりにしてお土産時間を確保 / 3日目は早めに帰る",
            height=120,
            key="revision_textarea"
        )

        c1, c2, c3 = st.columns(3)

        with c1:
            if st.button("💬 修正を追加して再提案", use_container_width=True):
                if revision_text.strip():
                    st.session_state.planning_state["revision_requests"].append(revision_text.strip())
                    append_chat("user", revision_text.strip())
                    append_chat("assistant", "修正希望を受け取りました。旅行案を再作成します。")
                    try:
                        generate_phase1_draft()
                        st.success("修正を反映した旅行案に更新しました。")
                        st.rerun()
                    except Exception as e:
                        st.error(f"旅行案更新エラー: {e}")
                        if st.session_state.debug_mode:
                            st.exception(e)
                else:
                    st.warning("修正内容を入力してください。")

        with c2:
            if st.button("✅ この案で了承する", use_container_width=True):
                try:
                    approve_and_build_phase2_phase3()
                    st.success("了承しました。完成旅程を作成しました。")
                except Exception as e:
                    st.error(f"了承処理エラー: {e}")
                    if st.session_state.debug_mode:
                        st.exception(e)

        with c3:
            if st.button("🗑️ 下書きを破棄", use_container_width=True):
                st.session_state.trip_plan_draft = None
                st.session_state.trip_plan = None
                st.session_state.df_phase2 = None
                st.session_state.df_phase3 = None
                st.session_state.plan_approved = False
                st.session_state.active_tab = "travel_consultation"
                st.session_state.app_logs = []
                st.session_state.resolved_conditions = {}
                st.warning("現在の下書きを破棄しました。")
                st.rerun()
    else:
        st.info("まず『旅行相談』タブで条件を決めて、『旅行案を作成』を押してください。")


# =========================================================
# タブ3: 完成旅程
# =========================================================
with tabs[2]:
    st.header("完成旅程")

    if st.session_state.df_phase3 is not None:
        df_phase3 = st.session_state.df_phase3.copy().reset_index(drop=True)

        summary = infer_trip_summary(df_phase3)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("出発時刻", summary["start_time"])
        c2.metric("出発地点", summary["start"])
        c3.metric("宿泊先", summary["hotel"])
        c4.metric("最終目的地", summary["final"])

        st.divider()

        with st.expander("Phase1 の自然文案", expanded=False):
            st.markdown(st.session_state.trip_plan or "")

        with st.expander("Phase2 の構造化データ", expanded=False):
            display_cols = [
                col for col in [
                    "day", "sequence", "date", "start_time", "end_time",
                    "destination", "purpose", "genre", "duration_minutes",
                    "is_transport", "transport_mode"
                ] if col in st.session_state.df_phase2.columns
            ]
            st.dataframe(st.session_state.df_phase2[display_cols], use_container_width=True, height=320)

        st.markdown("### 完成旅程タイムライン")
        render_google_calendar_sync_panel(df_phase3)
        render_phase35_validation_panel(st.session_state.trip_plan or "", df_phase3)

        col_simple, col_note = st.columns([1, 2])
        with col_simple:
            if st.button("📋 簡易一覧で見る", use_container_width=True, key="open_simple_itinerary_page"):
                st.session_state.simple_itinerary_page_mode = True
                st.session_state.active_tab = "final_itinerary"
                st.rerun()
        with col_note:
            st.caption("簡易一覧は別画面風に表示します。スポット・移動・ホテルを色分けし、Google Maps / Uber / ホテル予約だけを残します。")

        render_timeline_visibility_controls("plan", title="完成旅程の表示切替")
        render_itinerary_cards(
            df_phase3,
            allow_transport_edit=True,
            transport_edit_scope="plan",
            hide_completed=st.session_state.hide_completed_plan,
            hide_cancelled=st.session_state.hide_cancelled_plan,
        )
    else:
        st.info("まず『プラン確認』で旅行案を了承してください。")


# =========================================================
# タブ4: 実行シミュレーション
# =========================================================
with tabs[3]:
    st.header("実行シミュレーション")

    if st.session_state.df_phase3 is not None:
        if st.session_state.execution_engine is None:
            st.session_state.execution_engine = ExecutionEngine(st.session_state.df_phase3)

        engine = st.session_state.execution_engine

        if not getattr(engine, "execution_started", False):
            st.info("最初に作った旅程をベースに進めます。イベントが起きたときだけ未来を見直します。")
            preview_df = engine.get_updated_dataframe() if hasattr(engine, "get_updated_dataframe") else st.session_state.df_phase3
            render_timeline_visibility_controls("execution", title="実行シミュレーションの表示切替")
            render_itinerary_cards(
                preview_df,
                allow_transport_edit=True,
                transport_edit_scope="execution",
                hide_completed=st.session_state.hide_completed_execution,
                hide_cancelled=st.session_state.hide_cancelled_execution,
            )

            if st.button("🚀 旅程実行を開始", use_container_width=True):
                try:
                    result = engine.start_execution()
                    if isinstance(result, dict) and result.get("message"):
                        st.success(result["message"])
                    else:
                        st.success("旅程実行を開始しました。")
                    st.rerun()
                except Exception as e:
                    st.error(f"開始エラー: {e}")
                    if st.session_state.debug_mode:
                        st.exception(e)
        else:
            status = engine.get_current_status() if hasattr(engine, "get_current_status") else {}
            df_status = engine.get_updated_dataframe() if hasattr(engine, "get_updated_dataframe") else st.session_state.df_phase3

            current_step = int(status.get("current_step", 0))
            total_steps = int(status.get("total_steps", len(df_status)))
            progress_pct = float(status.get("progress_percentage", 0))
            total_delays = status.get("total_delays", 0)
            event_count = status.get("event_count", 0)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("現在のステップ", f"{current_step + 1}/{total_steps}")
            c2.metric("進捗", f"{progress_pct:.0f}%")
            c3.metric("イベント発生数", event_count)
            c4.metric("総遅延時間", f"{total_delays}分")

            if total_steps > 0:
                st.progress(progress_pct / 100)

            st.divider()
            render_mock_weather_panel(st.session_state.planning_state, context_label="execution")

            st.divider()
            st.markdown("### ステップ操作")

            cbtn1, cbtn2, cbtn3, cbtn4, cbtn5 = st.columns(5)

            with cbtn1:
                if st.button("✅ 予定通り進む", use_container_width=True):
                    try:
                        result = engine.proceed_to_next_step()
                        if isinstance(result, dict) and result.get("status") == "completed":
                            st.success("🎉 旅程完了！")
                        elif isinstance(result, dict) and result.get("message"):
                            st.success(result["message"])
                        else:
                            st.success("次へ進みました。")
                        st.rerun()
                    except Exception as e:
                        st.error(f"進行エラー: {e}")
                        if st.session_state.debug_mode:
                            st.exception(e)

            with cbtn2:
                if st.button("⏰ 遅延", use_container_width=True):
                    st.session_state.show_delay_dialog = True

            with cbtn3:
                if st.button("🌥️ 天候不順", use_container_width=True):
                    st.session_state.show_weather_dialog = True

            with cbtn4:
                if st.button("💭 気分が変わった", use_container_width=True):
                    st.session_state.show_mood_dialog = True

            with cbtn5:
                if st.button("✈️ 欠航・運休 / 中止", use_container_width=True):
                    st.session_state.show_cancel_dialog = True

            if st.session_state.show_delay_dialog:
                st.markdown("#### ⏰ 遅延・遅れの内容")
                delay_detail = st.text_area(
                    "例: 電車が15分遅れているので、この先を少し調整したい",
                    value="電車が遅れているので、この先の予定を少し調整したい。",
                    key="delay_detail_input"
                )
                dy1, dy2, dy3 = st.columns(3)
                with dy1:
                    if st.button("簡易提案を出す", key="delay_simple", use_container_width=True):
                        try:
                            st.session_state.event_result = engine.trigger_event("delay", delay_detail)
                            st.session_state.show_delay_dialog = False
                            st.rerun()
                        except Exception as e:
                            st.error(f"イベント提案エラー: {e}")
                with dy2:
                    if st.button("自由に組み直し案を作る", key="delay_replan", use_container_width=True):
                        try:
                            generate_execution_replan_preview(delay_detail, source_event="delay")
                            st.session_state.show_delay_dialog = False
                            st.rerun()
                        except Exception as e:
                            st.error(f"組み直し案生成エラー: {e}")
                with dy3:
                    if st.button("キャンセル", key="delay_cancel", use_container_width=True):
                        st.session_state.show_delay_dialog = False
                        st.rerun()

            if st.session_state.show_weather_dialog:
                st.markdown("#### 🌥️ 天候不順の内容")
                weather_context = _get_weather_context(st.session_state.planning_state, context_label="execution")
                st.info(
                    f"**現在の天候メモ連動**\n\n"
                    f"- 想定: {weather_context['summary']}\n"
                    f"- 実行中メモ: {weather_context['execution_hint']}\n"
                    f"- 地域差: {weather_context['gap_advice']}"
                )
                weather_detail = st.text_area(
                    "例: 次は屋外の予定だが、今は強い雨。移動が徒歩ならタクシー提案もしたい。",
                    value=build_weather_event_detail(st.session_state.planning_state),
                    key="weather_detail_input"
                )
                wx1, wx2, wx3 = st.columns(3)
                with wx1:
                    if st.button("簡易提案を出す", key="weather_simple", use_container_width=True):
                        try:
                            st.session_state.event_result = engine.trigger_event("weather", weather_detail)
                            st.session_state.show_weather_dialog = False
                            st.rerun()
                        except Exception as e:
                            st.error(f"イベント提案エラー: {e}")
                            if st.session_state.debug_mode:
                                st.exception(e)
                with wx2:
                    if st.button("自由に組み直し案を作る", key="weather_replan", use_container_width=True):
                        try:
                            generate_execution_replan_preview(weather_detail, source_event="weather")
                            st.session_state.show_weather_dialog = False
                            st.rerun()
                        except Exception as e:
                            st.error(f"組み直し案生成エラー: {e}")
                            if st.session_state.debug_mode:
                                st.exception(e)
                with wx3:
                    if st.button("キャンセル", key="weather_cancel", use_container_width=True):
                        st.session_state.show_weather_dialog = False
                        st.rerun()

            if st.session_state.show_mood_dialog:
                st.markdown("#### 💭 気分が変わった")
                mood_action = st.radio(
                    "やりたい操作を選んでください",
                    ["寄り道", "次の予定をキャンセル", "その日の予定をキャンセル", "全体キャンセルして帰路へ", "移動手段変更", "自由会話"],
                    key="mood_action_choice",
                )

                free_chat_text = ""
                if mood_action == "自由会話":
                    free_chat_text = st.text_area(
                        "自由に入力してください",
                        value="疲れたので次の予定だけ軽めにして、できれば屋内中心にしたい。",
                        key="mood_free_chat_input",
                        height=120,
                    )
                elif mood_action == "寄り道":
                    st.info("近くで短時間の立ち寄り候補を提案します。")
                elif mood_action == "次の予定をキャンセル":
                    st.info("次の予定だけを外して、この先を局所的に調整します。")
                elif mood_action == "その日の予定をキャンセル":
                    st.info("その日の残り予定をキャンセルして、以降を調整します。")
                elif mood_action == "全体キャンセルして帰路へ":
                    st.info("残り予定を止めて、帰路中心の提案に切り替えます。")
                elif mood_action == "移動手段変更":
                    st.info("楽な移動を優先する方向で提案します。必要なら各移動カードから個別変更もできます。")

                md1, md2 = st.columns(2)
                with md1:
                    button_label = "自由会話から組み直し案を作る" if mood_action == "自由会話" else "この内容で提案を出す"
                    if st.button(button_label, key="mood_action_apply", use_container_width=True):
                        try:
                            run_mood_change_action(engine, mood_action, free_chat_text)
                            st.rerun()
                        except Exception as e:
                            st.error(f"気分変化処理エラー: {e}")
                            if st.session_state.debug_mode:
                                st.exception(e)
                with md2:
                    if st.button("キャンセル", key="mood_cancel", use_container_width=True):
                        st.session_state.show_mood_dialog = False
                        st.rerun()

            if st.session_state.show_cancel_dialog:
                st.markdown("#### ✈️ 欠航・運休 / 全体中止の内容")
                cancel_detail = st.text_area(
                    "例: 欠航したので今日の残りを組み直したい / 全部キャンセルして今から帰る",
                    value="全部キャンセルして今から帰る。",
                    key="cancel_detail_input"
                )
                cx1, cx2, cx3 = st.columns(3)
                with cx1:
                    if st.button("簡易提案を出す", key="cancel_simple", use_container_width=True):
                        try:
                            st.session_state.event_result = engine.trigger_event("cancel", cancel_detail)
                            st.session_state.show_cancel_dialog = False
                            st.rerun()
                        except Exception as e:
                            st.error(f"イベント提案エラー: {e}")
                with cx2:
                    if st.button("自由に組み直し案を作る", key="cancel_replan", use_container_width=True):
                        try:
                            generate_execution_replan_preview(cancel_detail, source_event="cancel")
                            st.session_state.show_cancel_dialog = False
                            st.rerun()
                        except Exception as e:
                            st.error(f"組み直し案生成エラー: {e}")
                with cx3:
                    if st.button("キャンセル", key="cancel_close", use_container_width=True):
                        st.session_state.show_cancel_dialog = False
                        st.rerun()

            if st.session_state.replan_preview_draft:
                st.divider()
                st.info("自由入力をもとに、残り旅程だけを組み直した案です。気に入ればOKで実行シミュレーションへ反映できます。")
                st.markdown(f"**変更希望**: {safe_text(st.session_state.replan_preview_request)}")
                st.markdown("### 組み直し案プレビュー")
                st.markdown(st.session_state.replan_preview_draft)
                rp1, rp2 = st.columns(2)
                with rp1:
                    if st.button("👌 OK（この案で反映）", key="apply_replan_preview", use_container_width=True):
                        try:
                            apply_execution_replan_preview()
                            st.success("残り旅程を組み直して反映しました。")
                            st.rerun()
                        except Exception as e:
                            st.error(f"再計画反映エラー: {e}")
                            if st.session_state.debug_mode:
                                st.exception(e)
                with rp2:
                    if st.button("破棄する", key="discard_replan_preview", use_container_width=True):
                        st.session_state.replan_preview_draft = None
                        st.session_state.replan_preview_request = ""
                        st.session_state.replan_preview_source = ""
                        st.rerun()

            if st.session_state.event_result:
                result = st.session_state.event_result
                st.divider()
                st.warning(result.get("message", "提案があります。"))
                analysis = result.get("analysis", {})
                if analysis:
                    st.caption(f"判断意図: {', '.join(analysis.get('intents', []))} / 入力: {analysis.get('raw_text', '')}")

                alternatives = result.get("alternative_plans", [])
                if alternatives:
                    st.markdown("### 代替案")
                    for alt in alternatives:
                        with st.expander(f"案{alt.get('id', '?')}: {alt.get('title', '提案')}"):
                            if alt.get("description"):
                                st.write(f"**説明**: {alt['description']}")
                            if alt.get("changes"):
                                st.write(f"**変更内容**: {', '.join(alt['changes'])}")
                            if alt.get("reason"):
                                st.write(f"**理由**: {alt['reason']}")

                            if st.button(f"この案を採用", key=f"apply_alt_{alt.get('id', 'x')}", use_container_width=True):
                                try:
                                    apply_result = engine.apply_alternative(alt["id"])
                                    st.session_state.event_result = None
                                    st.success(apply_result.get("message", "提案を適用しました。"))
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"提案適用エラー: {e}")
                                    if st.session_state.debug_mode:
                                        st.exception(e)

            st.divider()
            st.markdown("### 進行中の旅程")
            render_timeline_visibility_controls("execution", title="進行中旅程の表示切替")
            render_itinerary_cards(
                df_status,
                current_step=current_step,
                allow_transport_edit=True,
                transport_edit_scope="execution",
                hide_completed=st.session_state.hide_completed_execution,
                hide_cancelled=st.session_state.hide_cancelled_execution,
            )

            if "execution_status" in df_status.columns:
                st.divider()
                st.markdown("### 進捗状況テーブル")
                df_display = df_status.copy()
                if "execution_status" in df_display.columns:
                    df_display["execution_status"] = df_display["execution_status"].apply(status_emoji)
                st.dataframe(df_display, use_container_width=True, height=320)

            if hasattr(engine, "event_log") and engine.event_log:
                st.divider()
                st.markdown("### イベントログ")
                for log in reversed(engine.event_log):
                    t = log.get("timestamp")
                    ts = t.strftime("%H:%M:%S") if hasattr(t, "strftime") else "--:--:--"
                    analysis = safe_text(log.get('analysis'), '')
                    suffix = f' / 解釈: {analysis}' if analysis not in {'', '-'} else ''
                    st.write(f"- [{ts}] {safe_text(log.get('event'))} / {safe_text(log.get('details'), '')}{suffix}")
    else:
        st.info("まず『プラン確認』で旅行案を了承してください。")


st.divider()
st.caption(f"{APP_DISPLAY_NAME} | {APP_VERSION_NAME} | 更新日 {APP_UPDATED_DATE} | 対話 → 自由記述案 → 構造化 → 経路補完 → 実行")