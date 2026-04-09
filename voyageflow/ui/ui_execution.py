import re
from typing import Callable, Dict, Optional

import pandas as pd
import streamlit as st


def get_card_style(safe_text_fn: Callable, row_dict: Dict, current_step: Optional[int], absolute_idx: Optional[int]) -> tuple[str, str]:
    status = safe_text_fn(row_dict.get("execution_status"), "pending")
    if status == "cancelled":
        return "vf-card-completed", "キャンセル"
    if current_step is not None and absolute_idx == current_step:
        return "vf-card-current", "進行中"
    note_text = safe_text_fn(row_dict.get("modification_note"), "")
    is_modified = bool(row_dict.get("is_modified_by_event", False)) or note_text not in {"", "-"}
    if is_modified:
        return "vf-card-modified", "変更あり"
    if status == "completed":
        return "vf-card-completed", "完了"
    return "vf-card-future", "これから"


def _style_emphasis(text: str) -> str:
    if not text:
        return ""
    escaped = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(
        r"\*\*(.+?)\*\*",
        r"<span style='font-weight:700;color:#a64b00;'>\1</span>",
        escaped,
    )


def render_transport_editor(
    *,
    row_dict: Dict,
    day: int,
    absolute_idx: int,
    local_pos: int,
    scope: str,
    mode_options: Dict[str, str],
    rental_info: Dict,
    apply_change_fn: Callable[[str, int, str], Dict[str, str]],
    safe_text_fn: Callable,
) -> None:
    current_mode = safe_text_fn(row_dict.get("transport_mode"), "walk").lower()
    if current_mode == "car":
        current_mode = "private_car"

    selection_key = f"transport_choice_{scope}_{absolute_idx}"
    if selection_key not in st.session_state:
        st.session_state[selection_key] = current_mode if current_mode in mode_options else "walk"

    panel_key = f"transport_editor_open_{scope}_{absolute_idx}"
    if panel_key not in st.session_state:
        st.session_state[panel_key] = False

    if st.button(
        "🚗 移動手段を変更する" if not st.session_state[panel_key] else "🚗 移動手段の変更を閉じる",
        key=f"toggle_transport_editor_{scope}_{day}_{absolute_idx}_{local_pos}",
        use_container_width=True,
    ):
        st.session_state[panel_key] = not st.session_state[panel_key]
        st.rerun()

    if not st.session_state[panel_key]:
        return

    rental_available = bool(rental_info.get("available"))
    st.caption(f"移動手段を変更 Day{int(day)}-Step{absolute_idx + 1}")

    items = list(mode_options.items())
    for chunk_start in range(0, len(items), 2):
        cols = st.columns(2)
        for col, item in zip(cols, items[chunk_start:chunk_start + 2]):
            mode_key, mode_label_button = item
            disabled = mode_key == "rental_car" and not rental_available
            selected = st.session_state.get(selection_key) == mode_key
            label = f"✅ {mode_label_button}" if selected else mode_label_button
            if col.button(
                label,
                key=f"pick_{scope}_{day}_{absolute_idx}_{local_pos}_{mode_key}",
                use_container_width=True,
                disabled=disabled,
            ):
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
        reason = safe_text_fn(rental_info.get("reason"), "周囲1km以内にレンタカー営業所が見つかりません。")
        st.caption(reason)

    apply_disabled = selected_mode == "rental_car" and not rental_available
    if st.button(
        "この移動手段に変更",
        key=f"apply_transport_{scope}_{day}_{absolute_idx}_{local_pos}",
        use_container_width=True,
        disabled=apply_disabled,
    ):
        result = apply_change_fn(scope, absolute_idx, selected_mode)
        st.success(result.get("message", "移動手段を変更しました。"))
        st.rerun()


def render_itinerary_cards(
    *,
    df: pd.DataFrame,
    safe_text_fn: Callable,
    build_google_maps_search_url_fn: Callable,
    build_google_maps_dir_url_fn: Callable,
    build_transport_display_fn: Callable,
    clean_address_fn: Callable,
    format_genre_fn: Callable,
    format_purpose_fn: Callable,
    get_rental_car_availability_fn: Callable,
    apply_change_fn: Callable[[str, int, str], Dict[str, str]],
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
        day_df = df[df["day"] == day].reset_index().rename(columns={"index": "_absolute_idx"})
        if hide_completed and "execution_status" in day_df.columns:
            day_df = day_df[day_df["execution_status"] != "completed"]
        if hide_cancelled and "execution_status" in day_df.columns:
            day_df = day_df[day_df["execution_status"] != "cancelled"]
        date_label = safe_text_fn(day_df.iloc[0].get("date")) if not day_df.empty else "-"
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
                current_badge = " ← 今ここ" if current_step is not None and absolute_idx == current_step else ""
                card_class, status_label = get_card_style(safe_text_fn, row_dict, current_step, absolute_idx)
                start_time = safe_text_fn(row_dict.get("start_time"))
                destination = safe_text_fn(row_dict.get("destination"))
                note = safe_text_fn(row_dict.get("modification_note"), "")

                if is_transport:
                    destination_text = destination
                    if "→" in destination_text:
                        origin, destination_name = [part.strip() for part in destination_text.split("→", 1)]
                    else:
                        origin, destination_name = "現在地", destination_text
                    route_url = safe_text_fn(row_dict.get("route_url"), "")
                    if not route_url or route_url == "-":
                        route_url = build_google_maps_dir_url_fn(
                            origin,
                            destination_name,
                            safe_text_fn(row_dict.get("transport_mode"), "walking").lower(),
                        )
                    transport_display = build_transport_display_fn(row_dict)
                    st.markdown(
                        f"""
<div class="vf-card {card_class}">
  <div><b>🚗 {start_time}{current_badge}</b></div>
  <div>状態: {status_label}</div>
  <div>移動手段: {transport_display}</div>
</div>
""",
                        unsafe_allow_html=True,
                    )
                    if status_label == "キャンセル":
                        st.markdown("<div class='vf-card-note' style='font-weight:700;background:#ececec;color:#555;text-align:center;font-size:22px;'>キャンセル</div>", unsafe_allow_html=True)
                    if note:
                        st.markdown(f"<div class='vf-card-note'>差分: {note}</div>", unsafe_allow_html=True)
                    st.link_button("🗺️ Google Mapsでルートを見る", route_url, use_container_width=True)
                    if allow_transport_edit and absolute_idx is not None:
                        rental_info = get_rental_car_availability_fn(df, absolute_idx)
                        render_transport_editor(
                            row_dict=row_dict,
                            day=int(day),
                            absolute_idx=absolute_idx,
                            local_pos=local_pos,
                            scope=transport_edit_scope,
                            mode_options=mode_options,
                            rental_info=rental_info,
                            apply_change_fn=apply_change_fn,
                            safe_text_fn=safe_text_fn,
                        )
                else:
                    place_url = build_google_maps_search_url_fn(destination)
                    address = clean_address_fn(row_dict.get("address"))
                    one_point = safe_text_fn(row_dict.get("one_point"), "")
                    if status_label == "キャンセル":
                        st.markdown(
                            f"""
<div class="vf-card {card_class}">
  <div style="font-weight:700;font-size:19px;color:#6b7280;">📍 {destination}</div>
</div>
""",
                            unsafe_allow_html=True,
                        )
                        st.markdown("<div class='vf-card-note' style='font-weight:700;background:#ececec;color:#555;text-align:center;font-size:22px;'>キャンセル</div>", unsafe_allow_html=True)
                        if note:
                            st.markdown(f"<div class='vf-card-note'>差分: {note}</div>", unsafe_allow_html=True)
                        continue

                    time_line = f"<span style='font-weight:700;color:#0f4c81;font-size:19px;'>{start_time} - {destination}{current_badge}</span>"
                    detail_lines = [f"目的: {format_purpose_fn(row_dict.get('purpose'))}"]
                    if address:
                        detail_lines.append(address)
                    if one_point:
                        detail_lines.append(_style_emphasis(one_point))
                    details_html = "<br>".join(detail_lines)
                    st.markdown(
                        f"""
<div class="vf-card {card_class}">
  <div>{time_line}</div>
  <div style="margin-top:6px;">{details_html}</div>
</div>
""",
                        unsafe_allow_html=True,
                    )
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
