# -*- coding: utf-8 -*-
"""
ui/quality_gate_panel.py
VoyageFlow v6.2.82
- Quality Gate の表示UIを app.py から分離
- LLM判定、Phase2→Phase3再作成処理は app.py/services 側の callback に委ねる
"""

from typing import Callable, Dict

import streamlit as st


def _status_label(status: str, safe_text: Callable) -> str:
    mapping = {
        "ok": "問題なし",
        "retry_recommended": "再作成推奨",
        "user_confirmation_required": "ユーザー確認",
        "fatal": "停止推奨",
    }
    return mapping.get(safe_text(status, ""), safe_text(status, "不明"))


def _issue_signature(result: Dict[str, object], safe_text: Callable) -> str:
    issues = result.get("issues") if isinstance(result, dict) else []
    if not isinstance(issues, list):
        return ""
    parts = []
    for issue in issues[:6]:
        if not isinstance(issue, dict):
            continue
        parts.append(
            "|".join([
                safe_text(issue.get("type"), ""),
                safe_text(issue.get("severity"), ""),
                safe_text(issue.get("location"), ""),
                safe_text(issue.get("problem"), ""),
            ])
        )
    return "\n".join(parts)


def render_quality_gate_panel_ui(
    *,
    run_current_quality_gate: Callable[[], Dict[str, object]],
    retry_phase2_phase3_from_existing_phase1: Callable[[], Dict[str, str]],
    safe_text: Callable,
    log_event: Callable,
) -> None:
    st.markdown("### 🧭 Quality Gate（完成旅程チェック）")
    st.caption("Geminiには品質判定だけをさせます。自動修正は行わず、必要な場合のみ Phase2→Phase3 を再作成します。")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("🧭 完成旅程を品質チェックする", use_container_width=True, key="run_quality_gate_check"):
            result = run_current_quality_gate()
            st.session_state.quality_gate_result = result
            st.session_state.quality_gate_raw = safe_text(result.get("raw"), "")
            st.session_state.quality_gate_last_signature = _issue_signature(result, safe_text)
            st.session_state.quality_gate_user_accepted = False
    with col2:
        if st.button("🧹 Quality Gate結果をクリア", use_container_width=True, key="clear_quality_gate_check"):
            st.session_state.quality_gate_result = None
            st.session_state.quality_gate_raw = ""
            st.session_state.quality_gate_last_signature = ""
            st.session_state.quality_gate_user_accepted = False
            st.rerun()

    result = st.session_state.get("quality_gate_result")
    if not isinstance(result, dict) or not result:
        st.info("必要なときだけ実行するチェックです。旅程の中身はここでは変更しません。")
        return

    status = safe_text(result.get("overall_status"), "user_confirmation_required")
    score = result.get("score")
    summary = safe_text(result.get("summary"), "")
    issues = result.get("issues") if isinstance(result.get("issues"), list) else []
    safe_to_retry = bool(result.get("safe_to_auto_retry", False))
    retry_scope = safe_text(result.get("retry_scope"), "none")
    retry_count = int(st.session_state.get("quality_gate_retry_count", 0) or 0)

    st.write(f"**判定:** {_status_label(status, safe_text)} / **スコア:** {score if score is not None else '-'} / **再作成範囲:** {retry_scope}")
    if status == "ok":
        st.success(summary or "大きな問題は見つかりませんでした。")
    elif status == "retry_recommended":
        st.warning(summary or "Phase2→Phase3の再作成を検討してください。")
    elif status == "fatal":
        st.error(summary or "自動再作成せず、内容確認が必要です。")
    else:
        st.info(summary or "ユーザー確認が必要な点があります。")

    if issues:
        st.markdown("#### 検出された確認点")
        for idx, issue in enumerate(issues, start=1):
            severity = safe_text(issue.get("severity"), "medium").lower()
            location = safe_text(issue.get("location"), "該当箇所")
            issue_type = safe_text(issue.get("type"), "issue")
            problem = safe_text(issue.get("problem"), "")
            suggestion = safe_text(issue.get("suggestion"), "")
            user_message = safe_text(issue.get("user_message"), "")
            body = f"{idx}. [{issue_type}] {location}\n\n問題: {problem}"
            if suggestion and suggestion != "-":
                body += f"\n\n提案: {suggestion}"
            if user_message and user_message != "-":
                body += f"\n\n確認: {user_message}"
            if severity == "critical":
                st.error(body)
            elif severity == "high":
                st.warning(body)
            else:
                st.info(body)
    else:
        st.success("個別の問題は返されていません。")

    st.markdown("#### 次の操作")
    if safe_to_retry and retry_scope == "phase2_phase3_only":
        if retry_count >= 2:
            st.warning("Phase2→Phase3再作成を複数回実行済みです。同じ問題が続く場合は、自動的に直そうとせずユーザー判断に切り替えるのが安全です。")
        if st.button("🔁 Phase2→Phase3だけ再作成する", use_container_width=True, key="retry_phase2_phase3_quality_gate"):
            try:
                result_message = retry_phase2_phase3_from_existing_phase1()
                st.success(result_message.get("message", "再作成しました。"))
                st.rerun()
            except Exception as e:
                log_event("Quality Gate", f"Phase2→Phase3再作成に失敗: {e}", level="error")
                st.error(f"Phase2→Phase3再作成に失敗しました: {e}")
    else:
        st.caption("この判定では、Phase2→Phase3の自動再作成は推奨されていません。")

    c_keep, c_debug = st.columns([1, 1])
    with c_keep:
        if st.button("✅ このまま使う", use_container_width=True, key="quality_gate_accept_current"):
            st.session_state.quality_gate_user_accepted = True
            st.success("現在の完成旅程をこのまま使う判断として記録しました。")
    with c_debug:
        with st.expander("Quality Gate raw output", expanded=False):
            st.code(st.session_state.get("quality_gate_raw", ""), language="json")
