import html
import os
import sys
import urllib.parse
import re
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
from maps.places_api import PlacesAPI


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
            "conversation_notes": [],
            "revision_requests": [],
        },
        "chat_history": [],
        "advisor_question_index": 0,
        "advisor_done": False,

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


def extract_trip_days_from_text(text: str) -> Optional[int]:
    text = str(text or "")
    match = re.search(r"(\d+)\s*泊\s*(\d+)\s*日", text)
    if match:
        return int(match.group(2))
    match = re.search(r"(\d+)\s*日", text)
    if match:
        return int(match.group(1))
    return None


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
    st.session_state.resolved_conditions = {
        "trip_days_form": int(s.get("trip_days", 2)),
        "trip_days_conversation": conversation_trip_days,
        "trip_days_final": resolved["trip_days"],
        "trip_days_source": adopted_source,
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
        "conversation_notes": [],
        "revision_requests": [],
    }
    st.session_state.chat_history = []
    st.session_state.advisor_question_index = 0
    st.session_state.advisor_done = False
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
    df3_new = router.insert_routes(df2_new, user_request=draft, transport_preference=replanning_state["transport_style"])
    if df3_new is None or df3_new.empty:
        raise ValueError("組み直し案から完成旅程を作れませんでした。")

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

    s["conversation_notes"].append(text)
    inferred_days = extract_trip_days_from_text(text)
    if inferred_days:
        log_event("会話解析", f"会話から旅行日数候補を検出: {inferred_days}日")

    if st.session_state.advisor_done and text:
        s["revision_requests"].append(text)


def build_phase1_request_text() -> str:
    s = resolve_planning_state()

    notes_text = " / ".join(s["conversation_notes"]) if s["conversation_notes"] else "特になし"
    revisions_text = " / ".join(s["revision_requests"]) if s["revision_requests"] else "なし"
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
- 移動スタイル: {s["transport_style"]}
- 予算感: {s["budget_style"]}
- 相談メモ: {notes_text}
- 追加の修正希望: {revisions_text}

【旅程の作り方】
- ユーザーの希望内容から、旅行の主目的地・主エリア・体験内容を自然に決めてください。
- Day 1, Day 2 のように日別に分けてください。
- 各日の時刻、訪問先、目的、滞在時間の目安がわかる形にしてください。
- {hotel_instruction}
- 「自動（おすすめ）」の場合は、一般的で無理のない移動手段を想定してください。
- 日ごとの個別要望があれば反映してください。
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
    df3 = router.insert_routes(df2, user_request=build_phase1_request_text(), transport_preference=s["transport_style"])
    if df3 is None or df3.empty:
        raise ValueError("フェーズ3で最終旅程表を生成できませんでした。")

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

    st.caption(f"ホテル必須: {'あり' if s['hotel_required'] else 'なし'}")

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
                    body = f"""
<div class="vf-card {card_class}">
  <div><b>🚗 {safe_text(row_dict.get('start_time'))} - {safe_text(row_dict.get('end_time'))}{current_badge}</b></div>
  <div>{status_text}</div>
  <div>移動手段: {transport_display}</div>
</div>
"""
                    st.markdown(body, unsafe_allow_html=True)
                    if status_label == "キャンセル":
                        st.markdown("<div class='vf-card-note' style='font-weight:700;background:#ececec;color:#555;'>キャンセル</div>", unsafe_allow_html=True)
                    if note:
                        st.markdown(f"<div class='vf-card-note'>差分: {note}</div>", unsafe_allow_html=True)
                    st.link_button("🗺️ Google Mapsでルートを見る", route_url, use_container_width=True)

                    if allow_transport_edit and absolute_idx is not None:
                        current_mode = safe_text(row_dict.get("transport_mode"), "walk").lower()
                        if current_mode == "car":
                            current_mode = "private_car"
                        selection_key = f"transport_choice_{transport_edit_scope}_{absolute_idx}"
                        if selection_key not in st.session_state:
                            st.session_state[selection_key] = current_mode if current_mode in mode_options else "walk"

                        rental_info = get_rental_car_availability(df, absolute_idx)
                        rental_available = bool(rental_info.get("available"))

                        st.caption(f"移動手段を変更 Day{int(day)}-Step{absolute_idx + 1}")
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

st.title("✈️ VoyageFlow - 対話式旅行プランナー")
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
            append_chat("user", user_message)
            update_planning_state_from_user_text(user_message)

            questions = conversation_advisor_questions()
            idx = st.session_state.advisor_question_index

            if not st.session_state.advisor_done:
                if idx + 1 < len(questions):
                    st.session_state.advisor_question_index += 1
                    append_chat("assistant", questions[st.session_state.advisor_question_index])
                else:
                    st.session_state.advisor_done = True
                    append_chat(
                        "assistant",
                        "ありがとうございます。条件がだいたい揃いました。『旅行案を作成』を押すと、まず自由記述の旅程案を作ります。"
                    )
            else:
                append_chat(
                    "assistant",
                    "修正希望を受け取りました。『旅行案を再作成』を押すと、この内容を反映した案を作り直します。"
                )
            st.rerun()

        st.divider()
        b1, b2 = st.columns(2)
        with b1:
            if st.button("🪄 旅行案を作成", use_container_width=True):
                try:
                    generate_phase1_draft()
                    st.success("旅行案を作成しました。次の『プラン確認』タブで確認してください。")
                except Exception as e:
                    st.error(f"旅行案作成エラー: {e}")
                    if st.session_state.debug_mode:
                        st.exception(e)

        with b2:
            if st.button("🔁 旅行案を再作成", use_container_width=True):
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
        st.markdown(st.session_state.trip_plan_draft)

        st.info("※移動時間や所要時間は目安です。完成旅程では、実際の移動経路や実時間にあわせて調整して表示します。")

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
                weather_detail = st.text_area(
                    "例: 次は屋外の予定だが、今は強い雨。移動が徒歩ならタクシー提案もしたい。",
                    value="次は屋外の予定だが、今は天候が悪い。必要なら屋内へ変更し、徒歩移動ならタクシーも提案して。",
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
                st.markdown("#### 💭 気分の変化")
                mood_detail = st.text_area(
                    "例: 疲れたので次の予定は短めにして、移動は楽にしたい",
                    value="疲れたので次の予定を少し軽くして、移動は楽にしたい。",
                    key="mood_detail_input"
                )
                md1, md2, md3 = st.columns(3)
                with md1:
                    if st.button("簡易提案を出す", key="mood_simple", use_container_width=True):
                        try:
                            st.session_state.event_result = engine.trigger_event("mood_change", mood_detail)
                            st.session_state.show_mood_dialog = False
                            st.rerun()
                        except Exception as e:
                            st.error(f"イベント提案エラー: {e}")
                            if st.session_state.debug_mode:
                                st.exception(e)
                with md2:
                    if st.button("自由に組み直し案を作る", key="mood_replan", use_container_width=True):
                        try:
                            generate_execution_replan_preview(mood_detail, source_event="mood_change")
                            st.session_state.show_mood_dialog = False
                            st.rerun()
                        except Exception as e:
                            st.error(f"組み直し案生成エラー: {e}")
                            if st.session_state.debug_mode:
                                st.exception(e)
                with md3:
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
def format_phase1_preview_text(plan_text: str) -> str:
    if not plan_text:
        return ""

    text = html.escape(plan_text)

    # 【日付】を強調
    text = re.sub(
        r"^【(.*?)】(.*)$",
        r"<div style='font-size:1.9rem;font-weight:800;color:#1f3b73;margin:18px 0 10px 0;'>【\1】\2</div>",
        text,
        flags=re.MULTILINE,
    )

    # テーマ（弱め表示）
    text = re.sub(
        r"^テーマ:\s*(.*)$",
        r"<div style='font-size:0.95rem;color:#6b7280;margin-bottom:12px;'>\1</div>",
        text,
        flags=re.MULTILINE,
    )

    # スポット（主役）
    text = re.sub(
        r"^\*\s*(\d{1,2}:\d{2}\s*-\s*.*)$",
        r"<div style='margin:12px 0 4px 0;font-weight:800;color:#1d4ed8;'>\1</div>",
        text,
        flags=re.MULTILINE,
    )

    # 目的
    text = re.sub(
        r"^\s*-\s*目的:\s*(.*)$",
        r"<div style='margin-left:16px;font-size:0.9rem;color:#374151;'>\1</div>",
        text,
        flags=re.MULTILINE,
    )

    # 滞在時間
    text = re.sub(
        r"^\s*-\s*滞在時間:\s*(.*)$",
        r"<div style='margin-left:16px;font-size:0.85rem;color:#6b7280;'>⏱ \1</div>",
        text,
        flags=re.MULTILINE,
    )

    # 🔥 ワンポイント → ラベル削除して本文だけ
    text = re.sub(
        r"^\s*-\s*ワンポイント:\s*(.*)$",
        r"<div style='margin-left:16px;font-size:0.95rem;color:#111827;'>\1</div>",
        text,
        flags=re.MULTILINE,
    )

    # 強調
    text = re.sub(
        r"\*\*(.*?)\*\*",
        r"<span style='font-weight:800;color:#dc2626;'>\1</span>",
        text,
    )

    return text

st.divider()
st.caption("VoyageFlow | 対話 → 自由記述案 → 構造化 → 経路補完 → 実行")