import os
import sys
import urllib.parse
import re
import html
import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

import pandas as pd
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
# 【バージョン名】VoyageFlow v6.2.1-routes-diagnostic-button
# 【制作日】2026-04-11
# 【修正内容】
# - 旅行相談の確認文を「主な目的地」ではなく「旅の概要」要約に変更
# - 日付・目的地・旅の目的・人数・宿泊条件を分解して自然な概要文を生成
# - 「5/16嵐のコンサートに京都に行く」のような入力で目的地が崩れる問題を抑制
# - 画面上部にアプリ名・バージョン名・更新日を表示
# =========================================================
APP_DISPLAY_NAME = "VoyageFlow - 対話式旅行プランナー"
APP_VERSION_NAME = "v6.2.6-llm-travel-time-fallback"
APP_UPDATED_DATE = "2026-04-16"


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
    @media (max-width: 768px) {
        .stTabs [data-baseweb="tab-list"] button { font-size: 13px; padding: 8px 10px; }
        .vf-chat-user, .vf-chat-ai, .vf-card, .vf-log-panel { padding: 12px; }
        .vf-card-note, .vf-log-item { font-size: 14px; }
        h1 { font-size: 2.1rem !important; }
        h2 { font-size: 1.8rem !important; }
        h3 { font-size: 1.4rem !important; }
    }
</style>
""",
    unsafe_allow_html=True,
)


def render_mock_weather_panel(planning_state: Dict[str, object], context_label: str = "plan") -> None:
    weather_context = build_mock_weather_context(planning_state)
    caption_suffix = "※モック表示です。後で実天気APIに差し替え可能な形にしています。"

    with st.container():
        st.markdown("### 🌤️ 天候メモ")
        st.caption(f"{weather_context['mode_label']} / {weather_context['date_range_label']} / {caption_suffix}")
        st.info(f"**{weather_context['headline']}**\n\n{weather_context['summary']}")

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
    weather_context = build_mock_weather_context(planning_state)
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
    if df is None or df.empty or "is_transport" not in df.columns:
        return df

    enriched = df.copy().reset_index(drop=True)
    for idx in enriched.index[enriched["is_transport"] == True].tolist():
        prev_row, next_row = _find_transport_context_rows(enriched, idx)
        if prev_row is None or next_row is None:
            continue

        origin_name = safe_text(prev_row.get("destination"), "出発地")
        destination_name = safe_text(next_row.get("destination"), "目的地")

        origin_lat = prev_row.get("latitude")
        origin_lng = prev_row.get("longitude")
        destination_lat = next_row.get("latitude")
        destination_lng = next_row.get("longitude")
        if any(pd.isna(v) for v in [origin_lat, origin_lng, destination_lat, destination_lng]):
            continue

        try:
            distance_km = _haversine_km(float(origin_lat), float(origin_lng), float(destination_lat), float(destination_lng))
        except Exception:
            continue

        mode = safe_text(enriched.at[idx, "transport_mode"], "").lower()
        if not mode or mode == "-":
            preferred = safe_text(planning_state.get("transport_style"), "自動（おすすめ）")
            mode = {
                "徒歩メイン": "walk",
                "電車メイン": "train",
                "タクシー": "taxi",
                "レンタカー": "car",
            }.get(preferred, "car" if distance_km >= 1.0 else "walk")
            enriched.at[idx, "transport_mode"] = mode

        departure_date = safe_text(enriched.at[idx, "date"], safe_text(planning_state.get("start_date"), ""))
        departure_time = safe_text(enriched.at[idx, "start_time"], safe_text(planning_state.get("departure_time"), "09:00"))

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
            enriched.at[idx, "route_line_simple"] = f"{origin_name} → {destination_name} / {label}"
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
            enriched.at[idx, "route_line_simple"] = f"{origin_name} → {destination_name} / {label}"
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
    if source == "llm_estimate":
        if departure_at and departure_at != "-":
            return f"移動時間: LLM概算 {duration_label} / {departure_at} 出発想定"
        return f"移動時間: LLM概算 {duration_label}"
    if source == "distance_estimate":
        return f"移動時間: {duration_label or '距離ベース推定（推測）'}"
    if source == "google_routes_api":
        if departure_at and departure_at != "-":
            return f"移動時間: 実検索（Google Routes / {departure_at} 出発想定）"
        return "移動時間: 実検索（Google Routes）"
    return "移動時間: 推定値（フォールバック）"


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

    log_event("Phase3", f"移動経路挿入を開始。transport_style={s['transport_style']}")
    router = Phase3Routing(logger=log_event)
    with _disable_live_routes_api_for_phase3():
        df3 = router.insert_routes(df2, user_request=build_phase1_request_text(), transport_preference=s["transport_style"])
    if df3 is None or df3.empty:
        raise ValueError("フェーズ3で最終旅程表を生成できませんでした。")
    df3 = enrich_transport_rows_with_estimates(df3, s, use_case="final_itinerary")

    gap_messages = inspect_transport_step_gaps(df3)
    if gap_messages:
        for msg in gap_messages:
            log_event("検査", msg, level="warning")
    else:
        log_event("検査", "スポット間の移動カード欠落は検出されませんでした。")

    st.session_state.trip_plan = trip_plan
    st.session_state.df_phase2 = df2
    st.session_state.df_phase3 = df3
    st.session_state.execution_engine = ExecutionEngine(df3)
    st.session_state.plan_approved = True
    st.session_state.active_tab = "final_itinerary"


def normalize_phase2_dataframe(df: pd.DataFrame, planning_state: Dict) -> pd.DataFrame:
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
        df.at[first_idx, "destination"] = planning_state["departure_place"]
        df.at[first_idx, "start_time"] = planning_state["departure_time"]

    if activity_idx:
        last_idx = activity_idx[-1]
        if planning_state["return_place"]:
            df.at[last_idx, "destination"] = planning_state["return_place"]

    if planning_state["hotel_required"]:
        has_hotel = df["destination"].astype(str).str.contains("ホテル|hotel|宿", case=False, na=False).any()
        if not has_hotel:
            insert_hotel_row(df)

    preferred = planning_state["transport_style"]
    if preferred == "徒歩メイン":
        preferred_mode = "walk"
    elif preferred == "電車メイン":
        preferred_mode = "train"
    elif preferred == "タクシー":
        preferred_mode = "taxi"
    elif preferred == "レンタカー":
        preferred_mode = "car"
    else:
        preferred_mode = None

    if preferred_mode and "is_transport" in df.columns:
        transport_idx = df.index[df["is_transport"] == True].tolist()  # noqa: E712
        for idx in transport_idx:
            df.at[idx, "transport_mode"] = preferred_mode

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
    router = Phase3Routing(logger=log_event)
    request_text = st.session_state.trip_plan or st.session_state.trip_plan_draft or build_phase1_request_text()
    with _disable_live_routes_api_for_phase3():
        df3 = router.insert_routes(
            normalized_df2,
            user_request=request_text,
            transport_preference=st.session_state.planning_state["transport_style"],
        )
    if df3 is None or df3.empty:
        raise ValueError("完成旅程の再構築に失敗しました。")
    df3 = enrich_transport_rows_with_estimates(df3, st.session_state.planning_state, use_case="final_itinerary")

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
                    transport_display = build_transport_display(row_dict)
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

    if st.button("🔄 全リセット", use_container_width=True):
        reset_all()
        st.rerun()


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
                weather_context = build_mock_weather_context(st.session_state.planning_state)
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