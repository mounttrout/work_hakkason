# -*- coding: utf-8 -*-
"""
VoyageFlow / Execution Monitor Agent
v6.2.65-dynamic-checklist-execution-monitor

目的:
- 完成旅程・現在地・現在時刻から、予定通り/遅延/到着済み/予定外移動を判定する。
- 再計画はまだ行わない。実行シミュレーション画面の実験機能として使う。
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None


KNOWN_LOCATION_COORDS: Dict[str, Tuple[float, float]] = {
    "福井駅": (36.0621, 136.2236),
    "東京駅": (35.681236, 139.767125),
    "上野駅": (35.713768, 139.777254),
    "上野": (35.713768, 139.777254),
    "浅草駅": (35.710832, 139.798532),
    "浅草寺": (35.714765, 139.796655),
    "仲見世商店街": (35.7119, 139.7967),
    "仲見世通り": (35.7119, 139.7967),
    "両国国技館": (35.6969, 139.7933),
    "両国": (35.6969, 139.7933),
    "第一ホテル両国": (35.6966, 139.7952),
    "明治神宮野球場": (35.6745, 139.7166),
    "東京ドームシティ": (35.7056, 139.7519),
    "東京ドーム": (35.7056, 139.7519),
    "渋谷スクランブルスクエア": (35.6585, 139.7020),
    "渋谷駅": (35.6580, 139.7016),
    "表参道": (35.6652, 139.7123),
    "表参道駅": (35.6652, 139.7123),
    "郡上八幡城": (35.7486, 136.9605),
    "郡上八幡": (35.7480, 136.9610),
    "飛騨の里": (36.1326, 137.2356),
    "高山市内": (36.1461, 137.2522),
    "大王わさび農場": (36.3397, 137.9099),
    "安曇野わさび田湧水群": (36.3397, 137.9099),
    "安曇野アートヒルズミュージアム": (36.3502, 137.8724),
    "安曇野 穂高ビューホテル": (36.3368, 137.8192),
    "お宿なごみ野": (36.3503, 137.8579),
    "上高地": (36.2474, 137.6375),
    "河童橋": (36.2485, 137.6371),
    "松本城": (36.2386, 137.9694),
    "ホテル ブエナビスタ": (36.2260, 137.9686),
    "美ヶ原高原美術館": (36.2319, 138.1342),
}


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        if pd is not None and pd.isna(value):
            return default
    except Exception:
        pass
    text = str(value).strip()
    return text if text else default


def _df_records(df: Any) -> List[Dict[str, Any]]:
    if df is None:
        return []
    try:
        if getattr(df, "empty", True):
            return []
        working = df.copy().reset_index(drop=True)
        if "day" in working.columns and "sequence" in working.columns:
            working = working.sort_values(["day", "sequence"], kind="stable").reset_index(drop=True)
        return working.to_dict("records")
    except Exception:
        if isinstance(df, list):
            return [r for r in df if isinstance(r, dict)]
        return []


def _parse_dt(date_text: Any, time_text: Any) -> Optional[datetime]:
    date_value = _safe_text(date_text)
    time_value = _safe_text(time_text)
    if not date_value or not time_value or time_value == "-":
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(f"{date_value} {time_value}", fmt)
        except Exception:
            pass
    return None


def parse_current_time(value: Any, fallback: Optional[datetime] = None) -> datetime:
    text = _safe_text(value)
    if not text or text.lower() == "now":
        return datetime.now().replace(second=0, microsecond=0)
    for fmt in ("%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%H:%M"):
        try:
            parsed = datetime.strptime(text, fmt)
            if fmt == "%H:%M":
                base = fallback or datetime.now()
                return base.replace(hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0)
            return parsed
        except Exception:
            pass
    return fallback or datetime.now().replace(second=0, microsecond=0)


def _coords_from_row(row: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    for lat_key, lng_key in [("latitude", "longitude"), ("lat", "lng")]:
        lat = row.get(lat_key)
        lng = row.get(lng_key)
        try:
            if lat is not None and lng is not None and not (pd is not None and (pd.isna(lat) or pd.isna(lng))):
                return float(lat), float(lng)
        except Exception:
            pass
    name = _safe_text(row.get("destination"))
    return coords_for_name(name)


def coords_for_name(name: str) -> Optional[Tuple[float, float]]:
    text = _safe_text(name)
    if not text:
        return None
    for key, coords in KNOWN_LOCATION_COORDS.items():
        if key in text or text in key:
            return coords
    # 「東京駅→上野駅」のような文字列では到着側を優先
    if "→" in text:
        right = text.split("→")[-1].strip()
        return coords_for_name(right)
    return None


def haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    lat1, lng1 = a
    lat2, lng2 = b
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lng2 - lng1)
    x = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(x), math.sqrt(1 - x))


def _row_label(row: Dict[str, Any]) -> str:
    if bool(row.get("is_transport", False)):
        origin = _safe_text(row.get("route_from"))
        dest = _safe_text(row.get("route_to")) or _safe_text(row.get("destination"))
        if origin and dest:
            return f"{origin}→{dest}"
    return _safe_text(row.get("destination"), "予定")


def _row_type(row: Dict[str, Any]) -> str:
    if bool(row.get("is_transport", False)) or _safe_text(row.get("purpose")).lower() == "transport":
        return "transport"
    dest = _safe_text(row.get("destination"))
    purpose = _safe_text(row.get("purpose")).lower()
    if purpose in {"accommodation", "hotel", "stay", "lodging"} or "ホテル" in dest or "hotel" in dest.lower():
        return "hotel"
    return "spot"


def _normalize_rows(df: Any) -> List[Dict[str, Any]]:
    rows = _df_records(df)
    normalized: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows):
        start_dt = _parse_dt(row.get("date"), row.get("start_time"))
        end_dt = _parse_dt(row.get("date"), row.get("end_time"))
        if start_dt and end_dt and end_dt < start_dt:
            end_dt = end_dt + timedelta(days=1)
        normalized.append({
            "index": idx,
            "raw": row,
            "label": _row_label(row),
            "type": _row_type(row),
            "start_dt": start_dt,
            "end_dt": end_dt,
            "coords": _coords_from_row(row),
            "day": row.get("day"),
            "date": _safe_text(row.get("date")),
            "start_time": _safe_text(row.get("start_time")),
            "end_time": _safe_text(row.get("end_time")),
        })
    return normalized


def find_active_or_next_step(df: Any, current_time: datetime) -> Optional[Dict[str, Any]]:
    rows = _normalize_rows(df)
    if not rows:
        return None
    for row in rows:
        start_dt = row.get("start_dt")
        end_dt = row.get("end_dt")
        if start_dt and end_dt and start_dt <= current_time <= end_dt:
            row["relation"] = "active"
            return row
    upcoming = [r for r in rows if r.get("start_dt") and r["start_dt"] > current_time]
    if upcoming:
        upcoming[0]["relation"] = "next"
        return upcoming[0]
    rows[-1]["relation"] = "past_last"
    return rows[-1]


def _status_label(status: str) -> str:
    return {
        "on_schedule": "予定通り",
        "arrived": "到着済み",
        "delay_risk": "遅延リスク",
        "off_route": "予定外移動の可能性",
        "time_only": "時刻ベース確認",
        "unknown": "確認不足",
    }.get(status, status)


def evaluate_execution_progress(itinerary_df: Any, current_time: Any, current_location: Optional[Dict[str, Any]] = None, tolerance_m: int = 300, off_route_m: int = 1200) -> Dict[str, Any]:
    rows = _normalize_rows(itinerary_df)
    if not rows:
        return {
            "status": "unknown",
            "status_label": _status_label("unknown"),
            "severity": "info",
            "message": "完成旅程がないため監視できません。",
            "actions": [],
        }

    first_dt = next((r.get("start_dt") for r in rows if r.get("start_dt")), None)
    now = parse_current_time(current_time, fallback=first_dt)
    target = find_active_or_next_step(itinerary_df, now)
    if not target:
        return {"status": "unknown", "status_label": _status_label("unknown"), "severity": "info", "message": "対象ステップが見つかりません。", "actions": []}

    loc_coords: Optional[Tuple[float, float]] = None
    loc_label = "未指定"
    if current_location:
        loc_label = _safe_text(current_location.get("label"), "現在地")
        try:
            lat = current_location.get("lat")
            lng = current_location.get("lng")
            if lat is not None and lng is not None:
                loc_coords = (float(lat), float(lng))
        except Exception:
            loc_coords = None
        if loc_coords is None and loc_label:
            loc_coords = coords_for_name(loc_label)

    target_coords = target.get("coords")
    distance_m: Optional[int] = None
    if loc_coords and target_coords:
        distance_m = int(round(haversine_km(loc_coords, target_coords) * 1000))

    start_dt = target.get("start_dt")
    end_dt = target.get("end_dt")
    relation = target.get("relation")
    minutes_to_start = int((start_dt - now).total_seconds() // 60) if start_dt else None
    minutes_after_end = int((now - end_dt).total_seconds() // 60) if end_dt else None

    actions = [
        "Google Mapsで現在地から次の予定までの経路を確認する",
        "必要なら次の予定の滞在時間短縮を検討する",
        "予約や営業時間がある予定は公式情報を確認する",
    ]

    status = "time_only"
    severity = "info"
    message = "現在時刻から次の予定を確認しました。"

    if distance_m is not None:
        if distance_m <= tolerance_m:
            if relation in {"active", "next"}:
                status = "arrived"
                severity = "success"
                message = f"{target['label']} 付近にいます。予定地点への到着/滞在中と判断できます。"
            else:
                status = "arrived"
                severity = "success"
                message = f"最終予定 {target['label']} 付近にいます。"
        elif distance_m >= off_route_m and relation == "active" and target.get("type") != "transport":
            status = "off_route"
            severity = "warning"
            message = f"本来は {target['label']} 付近にいる時間ですが、現在地が約{distance_m}m離れています。予定外移動の可能性があります。"
        elif end_dt and now > end_dt + timedelta(minutes=10):
            status = "delay_risk"
            severity = "warning"
            message = f"{target['label']} の予定終了時刻を過ぎています。現在地からの距離は約{distance_m}mです。"
        elif start_dt and minutes_to_start is not None and minutes_to_start <= 10 and distance_m > off_route_m:
            status = "delay_risk"
            severity = "warning"
            message = f"{target['label']} の開始まで約{max(minutes_to_start, 0)}分ですが、現在地が約{distance_m}m離れています。遅延リスクがあります。"
        else:
            status = "on_schedule"
            severity = "success"
            message = f"{target['label']} まで約{distance_m}mです。大きな逸脱は検出していません。"
    else:
        if end_dt and now > end_dt + timedelta(minutes=10):
            status = "delay_risk"
            severity = "warning"
            message = f"{target['label']} の予定終了時刻を過ぎています。位置情報がないため時刻ベースでの警告です。"
        elif relation == "active":
            status = "time_only"
            severity = "info"
            message = f"現在時刻は {target['label']} の予定時間内です。位置情報を入れると到着/逸脱も判定できます。"
        elif relation == "next":
            status = "time_only"
            severity = "info"
            message = f"次の予定は {target['label']} です。開始まで約{minutes_to_start}分です。"

    return {
        "status": status,
        "status_label": _status_label(status),
        "severity": severity,
        "message": message,
        "current_time": now.strftime("%Y-%m-%d %H:%M"),
        "current_location_label": loc_label,
        "distance_m": distance_m,
        "target_step": {
            "index": target.get("index"),
            "label": target.get("label"),
            "type": target.get("type"),
            "relation": relation,
            "date": target.get("date"),
            "start_time": target.get("start_time"),
            "end_time": target.get("end_time"),
            "has_coords": bool(target_coords),
        },
        "actions": actions,
    }


def build_dummy_current_location(itinerary_df: Any, mode: str, current_time: Any = None) -> Dict[str, Any]:
    rows = _normalize_rows(itinerary_df)
    first_dt = next((r.get("start_dt") for r in rows if r.get("start_dt")), None)
    now = parse_current_time(current_time, fallback=first_dt)
    target = find_active_or_next_step(itinerary_df, now)
    if not target:
        return {"label": "東京駅", "lat": 35.681236, "lng": 139.767125}

    if mode == "予定地点付近":
        coords = target.get("coords") or coords_for_name(target.get("label")) or (35.681236, 139.767125)
        return {"label": f"{target.get('label')}付近", "lat": coords[0], "lng": coords[1]}
    if mode == "遅延サンプル":
        # 次予定から少し離れた東京駅付近を使う
        return {"label": "東京駅付近（遅延サンプル）", "lat": 35.681236, "lng": 139.767125}
    if mode == "予定外移動サンプル":
        return {"label": "渋谷駅付近（予定外移動サンプル）", "lat": 35.6580, "lng": 139.7016}
    return {"label": "東京駅", "lat": 35.681236, "lng": 139.767125}


# =========================================================
# v6.2.72: ハッカソン説明用デモシナリオ生成
# - 実GPSがなくても、予定通り/到着/遅延/予定外移動/天候悪化の見せ方を確認できる
# - 完成旅程は変更しない。Execution Monitorの入力値を作るだけ
# =========================================================
def _pick_demo_target(rows: List[Dict[str, Any]], prefer_transport: bool = False) -> Optional[Dict[str, Any]]:
    if not rows:
        return None
    if prefer_transport:
        for row in rows:
            if row.get("type") == "transport" and row.get("start_dt"):
                return row
    for row in rows:
        if row.get("type") == "spot" and row.get("start_dt"):
            return row
    for row in rows:
        if row.get("start_dt"):
            return row
    return rows[0]


def _far_sample_location_for(target: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    label = _safe_text((target or {}).get("label"), "")
    # 対象地に合わせて、わざと離れた場所を選ぶ
    if any(token in label for token in ["長野", "安曇野", "松本", "上高地", "河童橋", "美ヶ原", "岐阜", "高山", "郡上"]):
        return {"label": "福井駅付近（デモ用・予定地から離れています）", "lat": 36.0621, "lng": 136.2236}
    return {"label": "渋谷駅付近（デモ用・予定地から離れています）", "lat": 35.6580, "lng": 139.7016}


def build_execution_demo_context(itinerary_df: Any, scenario: str) -> Dict[str, Any]:
    rows = _normalize_rows(itinerary_df)
    target = _pick_demo_target(rows, prefer_transport=(scenario == "予定通りデモ"))
    if not target:
        now = datetime.now().replace(second=0, microsecond=0)
        return {
            "current_time": now.strftime("%Y-%m-%d %H:%M"),
            "current_location": {"label": "東京駅", "lat": 35.681236, "lng": 139.767125},
            "scenario_label": scenario,
            "note": "完成旅程が不足しているため、固定サンプルで表示します。",
        }

    start_dt = target.get("start_dt") or datetime.now().replace(second=0, microsecond=0)
    coords = target.get("coords") or coords_for_name(target.get("label"))
    near_location = {
        "label": f"{target.get('label')}付近（デモ）",
        "lat": coords[0] if coords else 35.681236,
        "lng": coords[1] if coords else 139.767125,
    }

    if scenario == "到着済みデモ":
        demo_time = start_dt + timedelta(minutes=5)
        return {
            "current_time": demo_time.strftime("%Y-%m-%d %H:%M"),
            "current_location": near_location,
            "scenario_label": scenario,
            "note": "現在地を予定地付近に置き、到着済み/滞在中の表示を確認します。",
        }

    if scenario == "遅延リスクデモ":
        demo_time = start_dt - timedelta(minutes=5)
        return {
            "current_time": demo_time.strftime("%Y-%m-%d %H:%M"),
            "current_location": _far_sample_location_for(target),
            "scenario_label": scenario,
            "note": "予定開始直前なのに現在地が離れている状態を作り、遅延リスクを確認します。",
        }

    if scenario == "予定外移動デモ":
        demo_time = start_dt + timedelta(minutes=10)
        return {
            "current_time": demo_time.strftime("%Y-%m-%d %H:%M"),
            "current_location": _far_sample_location_for(target),
            "scenario_label": scenario,
            "note": "本来は予定地にいる時間なのに現在地が離れている状態を作り、予定外移動を確認します。",
        }

    if scenario == "天候悪化デモ":
        demo_time = start_dt + timedelta(minutes=5)
        return {
            "current_time": demo_time.strftime("%Y-%m-%d %H:%M"),
            "current_location": near_location,
            "scenario_label": scenario,
            "note": "現在地は予定地付近のまま、屋外予定に天候悪化が起きた想定の説明表示を確認します。",
        }

    # 予定通りデモ
    demo_time = start_dt + timedelta(minutes=3)
    return {
        "current_time": demo_time.strftime("%Y-%m-%d %H:%M"),
        "current_location": near_location,
        "scenario_label": scenario,
        "note": "現在地を予定地付近に置き、予定通り進行している見せ方を確認します。",
    }
