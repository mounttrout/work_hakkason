# -*- coding: utf-8 -*-
"""
ui/quality_gate_panel.py
VoyageFlow v6.2.83
- Quality Gate の表示UIを app.py から分離
- LLMチェック、コード側安全補正、Phase2→Phase3再作成処理は callback に委ねる
"""

from typing import Callable, Dict

import streamlit as st


def _status_label(status: str, safe_text: Callable) -> str:
    mapping = {
        "ok": "問題なし",
        "auto_fix_available": "安全補正候補あり",
        "auto_fix_applied": "安全補正済み",
        "retry_recommended": "再作成推奨",
        "user_confirmation_required": "ユーザー確認",
        "fatal": "停止推奨",
    }
    return mapping.get(safe_text(status, ""), safe_text(status, "不明"))


def _status_box(status: str):
    if status == "ok":
        return st.success
    if status == "auto_fix_applied":
        return st.success
    if status in {"auto_fix_available", "retry_recommended"}:
        return st.warning
    if status == "fatal":
        return st.error
    return st.info


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


def _render_checks(checks, safe_text: Callable) -> None:
    if not isinstance(checks, list) or not checks:
        st.success("チェックリストの個別指摘はありません。")
        return

    st.markdown("#### チェックリスト判定")
    for idx, check in enumerate(checks, start=1):
        if not isinstance(check, dict):
            continue
        status = safe_text(check.get("status"), "warning").lower()
        severity = safe_text(check.get("severity"), "medium").lower()
        category = safe_text(check.get("category"), "quality")
        check_id = safe_text(check.get("id"), "quality_check")
        location = safe_text(check.get("location"), "該当箇所")
        evidence = safe_text(check.get("evidence"), "")
        suggestion = safe_text(check.get("suggestion"), "")
        action = safe_text(check.get("recommended_action"), "")
        source = safe_text(check.get("source"), "")
        user_message = safe_text(check.get("user_message"), "")

        icon = "✅" if status == "pass" else ("⚠️" if status == "warning" else "❌")
        body = (
            f"{idx}. {icon} **[{category}/{check_id}]** {location}\n\n"
            f"- 状態: `{status}` / 重要度: `{severity}` / 推奨: `{action}`"
        )
        if source:
            body += f" / 判定元: `{source}`"
        if evidence and evidence != "-":
            body += f"\n- 根拠: {evidence}"
        if suggestion and suggestion != "-":
            body += f"\n- 提案: {suggestion}"
        if user_message and user_message != "-":
            body += f"\n- ユーザー確認: {user_message}"

        if status == "pass":
            with st.expander(body.split("\n\n")[0], expanded=False):
                st.markdown(body)
        elif severity in {"critical", "high"}:
            st.warning(body)
        else:
            st.info(body)


def render_quality_gate_panel_ui(
    *,
    run_current_quality_gate: Callable[[], Dict[str, object]],
    retry_phase2_phase3_from_existing_phase1: Callable[[], Dict[str, str]],
    safe_text: Callable,
    log_event: Callable,
) -> None:
    st.markdown("### 🧭 Quality Gate（完成旅程チェック）")
    st.caption(
        "Phase3完成旅程をチェックリストで判定します。"
        "明確な短距離移動・同一地点移動・ホテル分類ミスなどはコード側の安全ルールで即時補正し、"
        "相撲日程やホテル選択など判断が必要なものはユーザー確認に回します。"
    )

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
            st.session_state.quality_gate_autofix_summary = []
            st.rerun()

    result = st.session_state.get("quality_gate_result")
    if not isinstance(result, dict) or not result:
        st.info("必要なときだけ実行するチェックです。実行するまで旅程の中身は変更しません。")
        return

    status = safe_text(result.get("overall_status"), "user_confirmation_required")
    score = result.get("score")
    summary = safe_text(result.get("summary"), "")
    checks = result.get("checks") if isinstance(result.get("checks"), list) else []
    issues = result.get("issues") if isinstance(result.get("issues"), list) else []
    safe_to_retry = bool(result.get("safe_to_auto_retry", False))
    retry_scope = safe_text(result.get("retry_scope"), "none")
    retry_count = int(st.session_state.get("quality_gate_retry_count", 0) or 0)
    auto_fix_summary = result.get("auto_fix_summary")
    if not isinstance(auto_fix_summary, list):
        auto_fix_summary = st.session_state.get("quality_gate_autofix_summary") or []

    st.write(f"**判定:** {_status_label(status, safe_text)} / **スコア:** {score if score is not None else '-'} / **再作成範囲:** {retry_scope}")
    _status_box(status)(summary or "Quality Gateの判定結果です。")

    if auto_fix_summary:
        st.markdown("#### ✅ 安全自動補正済み")
        for note in auto_fix_summary:
            st.write(f"- {safe_text(note, '')}")
        st.caption("補正はホワイトリスト化した明確な項目のみです。旅行日程・イベント選択・ホテル選択などは勝手に変更しません。")

    _render_checks(checks, safe_text)

    if issues and not checks:
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

    st.markdown("#### 次の操作")
    retry_allowed = safe_to_retry or retry_scope == "phase2_phase3_only" or status == "retry_recommended"
    if retry_allowed:
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
        st.caption("この判定では、Phase2→Phase3の再作成は推奨されていません。ユーザー判断が必要な項目は、上のチェック内容を確認してください。")

    c_keep, c_debug = st.columns([1, 1])
    with c_keep:
        if st.button("✅ このまま使う", use_container_width=True, key="quality_gate_accept_current"):
            st.session_state.quality_gate_user_accepted = True
            st.success("現在の完成旅程をこのまま使う判断として記録しました。")
    with c_debug:
        with st.expander("Quality Gate raw output", expanded=False):
            st.code(st.session_state.get("quality_gate_raw", ""), language="json")
