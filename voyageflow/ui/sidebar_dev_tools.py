# -*- coding: utf-8 -*-
"""
ui/sidebar_dev_tools.py
VoyageFlow v6.2.90
- サイドバー診断ツールを app.py から分離
- 通常時は開発者ツールを非表示
- app.py 側の既存関数を context/callback として受け取り、診断機能自体は削除しない
- v6.2.90: ホテル継続ガードの候補・統一先・補正結果を左サイドバーで確認できる診断欄を追加
"""

import os
from typing import Callable, Optional

import requests
import streamlit as st


def _safe_call(fn: Callable, *args, **kwargs):
    if fn is None:
        return None
    return fn(*args, **kwargs)


def _render_hotel_continuity_guard_status(*, safe_text: Callable) -> None:
    """ホテル継続ガードが効いたかを左側テストスペースで確認する。"""
    with st.expander("🏨 ホテル継続ガード確認", expanded=False):
        st.caption("完成旅程のホテル候補が複数化したとき、同一都市・明示指示なしなら統一されたかを確認します。")
        diag = st.session_state.get("hotel_continuity_guard_last_diag")
        if not isinstance(diag, dict):
            st.info("まだホテル継続ガードの診断結果はありません。完成旅程生成またはQuality Gate実行後に表示されます。")
        else:
            status = safe_text(diag.get("status"), "")
            status_label = {
                "applied": "✅ 自動統一済み",
                "no_multiple_hotels": "✅ 複数ホテルなし",
                "not_safe_to_unify": "⚠️ 自動統一せず",
                "skipped": "ℹ️ スキップ",
                "not_applied": "⚠️ 未適用",
                "no_replacement": "ℹ️ 置換対象なし",
            }.get(status, status or "不明")
            st.write(f"状態: {status_label}")
            if diag.get("checked_at"):
                st.caption(f"確認時刻: {safe_text(diag.get('checked_at'), '')}")
            if diag.get("candidates"):
                st.write("検出したホテル候補")
                st.json(diag.get("candidates"))
            if diag.get("canonical"):
                st.write(f"統一先: {safe_text(diag.get('canonical'), '')}")
            if diag.get("replaced"):
                st.write("置換したホテル候補")
                st.json(diag.get("replaced"))
            if diag.get("notes"):
                st.write("補正メモ")
                for note in diag.get("notes") or []:
                    st.caption(f"- {safe_text(note, '')}")
            if diag.get("reason"):
                st.caption(f"理由: {safe_text(diag.get('reason'), '')}")

        df = st.session_state.get("df_phase3")
        try:
            if df is not None and not df.empty and "destination" in df.columns:
                hotel_rows = []
                for _, row in df.iterrows():
                    dest = safe_text(row.get("destination"), "")
                    purpose = safe_text(row.get("purpose"), "")
                    genre = safe_text(row.get("genre"), "")
                    is_transport = bool(row.get("is_transport", False))
                    if is_transport:
                        continue
                    if ("ホテル" in dest) or (genre.lower() == "hotel") or (purpose.lower() in {"accommodation", "hotel", "stay", "lodging"}):
                        hotel_rows.append({
                            "day": int(row.get("day")) if row.get("day") is not None else "",
                            "start": safe_text(row.get("start_time"), ""),
                            "destination": dest,
                            "purpose": purpose,
                            "genre": genre,
                        })
                if hotel_rows:
                    st.write("現在の完成旅程内ホテル行")
                    st.dataframe(hotel_rows, use_container_width=True, hide_index=True)
                else:
                    st.caption("現在の完成旅程内にホテル行は見つかりません。")
        except Exception as e:
            st.caption(f"ホテル行の読み取りをスキップしました: {e}")

        summary = st.session_state.get("quality_gate_autofix_summary")
        if summary:
            st.write("Quality Gate安全補正の直近メモ")
            for note in summary:
                st.caption(f"- {safe_text(note, '')}")


def _render_routes_diagnostic(
    *,
    parse_route_diagnostic_departure_iso: Callable,
    build_route_diagnostic_body: Callable,
) -> None:
    with st.expander("🛠 Routes診断", expanded=False):
        st.caption("開発者向け診断です。完成旅程には反映しません。")
        diag_origin = st.text_input("出発地", value="福井駅", key="routes_diag_origin")
        diag_destination = st.text_input("到着地", value="東京駅", key="routes_diag_destination")
        diag_mode = st.selectbox("移動手段", options=["train", "walk", "car", "taxi", "bike"], index=0, key="routes_diag_mode")
        diag_departure = st.text_input("出発日時 (YYYY-MM-DD HH:MM)", value="2026-04-19 12:05", key="routes_diag_departure")

        if st.button("🚨 Routes診断を実行", use_container_width=True, key="run_routes_diagnostic"):
            try:
                from route_diagnostic import geocode_place, ROUTES_URL

                api_key = st.secrets.get("MAPS_API_KEY") or os.getenv("MAPS_API_KEY")
                if not api_key:
                    st.error("MAPS_API_KEY が見つかりません。Secrets または環境変数を確認してください。")
                    return

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
                    st.error("地名解決に失敗しました。origin_clean / destination_clean を確認してください。")
                    return

                body = build_route_diagnostic_body(origin, destination, diag_mode, departure_raw)
                headers = {
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": api_key,
                    "X-Goog-FieldMask": "*",
                }
                masked_headers = dict(headers)
                if masked_headers.get("X-Goog-Api-Key"):
                    raw_key = str(masked_headers["X-Goog-Api-Key"])
                    masked_headers["X-Goog-Api-Key"] = raw_key[:4] + "..." + raw_key[-4:] if len(raw_key) > 8 else "***"

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


def _render_google_directions_diagnostic(
    *,
    get_maps_api_key: Callable,
    normalize_route_query_name: Callable,
    build_google_directions_location_query: Callable,
    google_directions_mode_for_transport: Callable,
    fetch_google_directions_legacy: Callable,
) -> None:
    with st.expander("🧪 Google Directions診断", expanded=False):
        st.caption("開発者向け診断です。完成旅程には反映しません。")
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
                api_key = get_maps_api_key()
                st.write("APIキー状態")
                st.json({
                    "has_api_key": bool(api_key),
                    "api_key_preview": (api_key[:4] + "..." + api_key[-4:]) if api_key and len(api_key) > 8 else ("***" if api_key else ""),
                })
                if not api_key:
                    st.error("MAPS_API_KEY が見つかりません。Secrets または環境変数を確認してください。")
                    return

                origin_raw = str(gd_origin or "")
                destination_raw = str(gd_destination or "")
                origin_clean = normalize_route_query_name(origin_raw)
                destination_clean = normalize_route_query_name(destination_raw)
                query_origin = build_google_directions_location_query(origin_clean, None, None)
                query_destination = build_google_directions_location_query(destination_clean, None, None)
                departure_raw = str(gd_departure or "").strip()
                api_mode = google_directions_mode_for_transport(gd_mode)

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

                result, debug_info = fetch_google_directions_legacy(
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
                    st.warning("Directions API から結果を取得できませんでした。")
                    return

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


def _render_transit_station_trial(
    *,
    get_maps_api_key: Callable,
    normalize_route_query_name: Callable,
    build_google_directions_location_query: Callable,
    fetch_google_directions_transit_station_trial: Callable,
    safe_text: Callable,
) -> None:
    with st.expander("🧪 Transit駅名抽出トライ", expanded=False):
        st.caption("Directions API の transit_details から駅名が取れるかだけ確認します。完成旅程には反映しません。")
        trial_origin = st.text_input("駅名抽出 出発地", value="仲見世商店街", key="station_trial_origin")
        trial_destination = st.text_input("駅名抽出 到着地", value="上野", key="station_trial_destination")
        trial_departure = st.text_input(
            "駅名抽出 出発日時 (YYYY-MM-DD HH:MM / now / epoch秒)",
            value="2026-05-06 12:00",
            key="station_trial_departure",
        )
        if st.button("🚉 駅名抽出を試す", use_container_width=True, key="run_station_name_trial"):
            try:
                api_key = get_maps_api_key()
                if not api_key:
                    st.error("MAPS_API_KEY が見つかりません。Secrets または環境変数を確認してください。")
                    return

                origin_clean = normalize_route_query_name(trial_origin)
                destination_clean = normalize_route_query_name(trial_destination)
                query_origin = build_google_directions_location_query(origin_clean, None, None)
                query_destination = build_google_directions_location_query(destination_clean, None, None)
                departure_raw = str(trial_departure or "").strip()
                result, debug_info = fetch_google_directions_transit_station_trial(
                    origin_query=query_origin,
                    destination_query=query_destination,
                    departure_raw=departure_raw,
                )

                st.write("入力正規化")
                st.json({
                    "origin_raw": trial_origin,
                    "origin_clean": origin_clean,
                    "origin_query": query_origin,
                    "destination_raw": trial_destination,
                    "destination_clean": destination_clean,
                    "destination_query": query_destination,
                    "departure": departure_raw,
                    "timezone_assumption": "Asia/Tokyo",
                    "note": "この結果は完成旅程には反映していません。",
                })
                st.write("時刻変換診断")
                st.json((debug_info or {}).get("departure_parse", {}))
                st.write("Directions API 診断")
                st.json(debug_info or {})

                if not result:
                    st.warning("駅名抽出に使える transit 結果を取得できませんでした。")
                    return

                station_label = safe_text(result.get("station_label"), "")
                if station_label:
                    st.success(f"抽出候補: 電車：{station_label}")
                else:
                    st.warning("Directions結果は取得できましたが、departure_stop / arrival_stop が空でした。")
                st.write("駅名抽出結果")
                st.json({
                    "station_label": station_label,
                    "duration_text": result.get("duration_text"),
                    "distance_text": result.get("distance_text"),
                    "fare_text": result.get("fare_text"),
                    "start_address": result.get("start_address"),
                    "end_address": result.get("end_address"),
                    "transit_station_steps_count": len(result.get("transit_station_steps") or []),
                })
                station_steps = result.get("transit_station_steps") or []
                if station_steps:
                    st.markdown("**Transit station steps**")
                    for idx, step in enumerate(station_steps, start=1):
                        line = safe_text(step.get("line_name"), "")
                        vehicle = safe_text(step.get("vehicle_name"), "公共交通")
                        dep = safe_text(step.get("departure_stop"), "")
                        arr = safe_text(step.get("arrival_stop"), "")
                        dep_time = safe_text(step.get("departure_time"), "")
                        arr_time = safe_text(step.get("arrival_time"), "")
                        st.write(f"{idx}. {vehicle} {line}: {dep} → {arr} ({dep_time} - {arr_time})")
                    with st.expander("駅名抽出 step JSON", expanded=False):
                        st.json(station_steps)
                with st.expander("全 step JSON", expanded=False):
                    st.json(result.get("steps") or [])
            except Exception as e:
                st.error(f"駅名抽出トライ エラー: {e}")


def render_sidebar_dev_tools(
    *,
    app_name: str,
    model_name: str,
    reset_all: Callable,
    render_internal_logs_sidebar: Callable,
    render_gemini_transport_ab_test_panel: Callable,
    render_transport_estimation_test_panel: Callable,
    parse_route_diagnostic_departure_iso: Callable,
    build_route_diagnostic_body: Callable,
    get_maps_api_key: Callable,
    normalize_route_query_name: Callable,
    build_google_directions_location_query: Callable,
    google_directions_mode_for_transport: Callable,
    fetch_google_directions_legacy: Callable,
    fetch_google_directions_transit_station_trial: Callable,
    safe_text: Callable,
) -> None:
    st.markdown(f"### {app_name}")
    st.caption(f"モデル: {model_name}")

    st.session_state.show_developer_tools = st.checkbox(
        "開発者ツールを表示",
        value=bool(st.session_state.get("show_developer_tools", False)),
        key="show_developer_tools_checkbox",
    )

    if st.button("🔄 全リセット", use_container_width=True, key="sidebar_reset_all"):
        reset_all()
        st.rerun()

    if not st.session_state.show_developer_tools:
        st.caption("診断ツール・生成温度・デバッグモードは開発者ツール内に隠しています。")
        return

    st.divider()
    st.markdown("### ⚙️ 開発者設定")
    st.session_state.temperature = st.slider(
        "Gemini 生成温度",
        0.0,
        1.0,
        float(st.session_state.get("temperature", 0.7)),
        0.1,
        key="temperature_slider_devtools",
    )
    st.session_state.debug_mode = st.checkbox(
        "デバッグモード",
        value=bool(st.session_state.get("debug_mode", False)),
        key="debug_mode_checkbox_devtools",
    )

    st.divider()
    render_internal_logs_sidebar()

    st.divider()
    st.markdown("### 🧪 診断ツール")
    render_gemini_transport_ab_test_panel()
    render_transport_estimation_test_panel()
    _render_hotel_continuity_guard_status(safe_text=safe_text)

    _render_routes_diagnostic(
        parse_route_diagnostic_departure_iso=parse_route_diagnostic_departure_iso,
        build_route_diagnostic_body=build_route_diagnostic_body,
    )
    _render_google_directions_diagnostic(
        get_maps_api_key=get_maps_api_key,
        normalize_route_query_name=normalize_route_query_name,
        build_google_directions_location_query=build_google_directions_location_query,
        google_directions_mode_for_transport=google_directions_mode_for_transport,
        fetch_google_directions_legacy=fetch_google_directions_legacy,
    )
    _render_transit_station_trial(
        get_maps_api_key=get_maps_api_key,
        normalize_route_query_name=normalize_route_query_name,
        build_google_directions_location_query=build_google_directions_location_query,
        fetch_google_directions_transit_station_trial=fetch_google_directions_transit_station_trial,
        safe_text=safe_text,
    )
