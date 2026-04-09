import streamlit as st


def render_planning_summary(planning_state: dict, resolved_conditions: dict) -> None:
    st.markdown("### 現在の確定条件")
    c1, c2, c3 = st.columns(3)
    c1.metric("出発地", planning_state["departure_place"])
    c2.metric("帰着地", planning_state["return_place"])
    c3.metric("出発時間", planning_state["departure_time"])

    c4, c5, c6 = st.columns(3)
    display_days = resolved_conditions.get("trip_days_final", planning_state["trip_days"])
    c4.metric("旅行日数", f"{display_days}日")
    c5.metric("移動スタイル", planning_state["transport_style"])
    c6.metric("予算感", planning_state["budget_style"])

    st.caption(f"ホテル必須: {'あり' if planning_state['hotel_required'] else 'なし'}")

    if planning_state["conversation_notes"]:
        st.markdown("**相談メモ**")
        for note in planning_state["conversation_notes"][-5:]:
            st.write(f"- {note}")

    if planning_state["revision_requests"]:
        st.markdown("**追加修正依頼**")
        for note in planning_state["revision_requests"][-5:]:
            st.write(f"- {note}")


def render_chat_history(chat_history: list, advisor_questions_fn, append_chat_fn) -> None:
    st.markdown("### 旅行相談")
    if not chat_history:
        st.info("まず条件を少しずつ決めていきましょう。")
        first_q = advisor_questions_fn()[0]
        append_chat_fn("assistant", first_q)
        chat_history = st.session_state.chat_history

    for item in chat_history:
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
