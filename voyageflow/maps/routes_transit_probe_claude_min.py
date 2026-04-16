# routes_transit_probe_claude_min.py
# 目的:
# - app.py を介さずに Google Geocoding API + Routes API を直接叩く
# - Claude案の最小変更だけを適用して TRANSIT の {} を切り分ける
#
# 変更点:
# 1. TRANSIT では routeModifiers を送らない
# 2. TRANSIT では polylineQuality = "OVERVIEW" を追加
# 3. train のときだけ departureTime を送る
# 4. car は従来どおりの成功確認用として残す

import os
import json
from datetime import datetime
from typing import Optional, Tuple

import requests

MAPS_API_KEY = os.getenv("MAPS_API_KEY", "").strip()
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"


def require_api_key() -> None:
    if not MAPS_API_KEY:
        raise RuntimeError("MAPS_API_KEY が未設定です。")


def geocode(place: str) -> Optional[Tuple[float, float]]:
    params = {
        "address": place,
        "key": MAPS_API_KEY,
    }
    resp = requests.get(GEOCODE_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") != "OK" or not data.get("results"):
        return None

    loc = data["results"][0]["geometry"]["location"]
    return float(loc["lat"]), float(loc["lng"])


def to_rfc3339_jst(text: str) -> str:
    dt = datetime.strptime(text, "%Y-%m-%d %H:%M")
    return dt.strftime("%Y-%m-%dT%H:%M:%S+09:00")


def build_body(
    origin_latlng: Tuple[float, float],
    destination_latlng: Tuple[float, float],
    mode: str,
    departure_text: Optional[str] = None,
) -> dict:
    """
    Claude案ベースの最小修正版:
    - TRANSIT では routeModifiers を送らない
    - TRANSIT では polylineQuality を追加
    """
    mode = str(mode).lower().strip()
    mode_map = {
        "train": "TRANSIT",
        "car": "DRIVE",
        "walk": "WALK",
        "bike": "BICYCLE",
        "taxi": "DRIVE",
    }

    travel_mode = mode_map.get(mode, "TRANSIT")

    body = {
        "origin": {
            "location": {
                "latLng": {
                    "latitude": origin_latlng[0],
                    "longitude": origin_latlng[1],
                }
            }
        },
        "destination": {
            "location": {
                "latLng": {
                    "latitude": destination_latlng[0],
                    "longitude": destination_latlng[1],
                }
            }
        },
        "travelMode": travel_mode,
        "computeAlternativeRoutes": False,
    }

    # DRIVE 系だけ routeModifiers を付与
    if travel_mode == "DRIVE":
        body["routeModifiers"] = {
            "avoidTolls": False,
            "avoidHighways": False,
            "avoidFerries": False,
        }

    # TRANSIT のときだけ追加
    if travel_mode == "TRANSIT":
        body["polylineQuality"] = "OVERVIEW"

    # train のときだけ departureTime を送る
    if mode == "train" and departure_text:
        body["departureTime"] = to_rfc3339_jst(departure_text)

    return body


def build_headers(field_mask: str = "routes") -> dict:
    return {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": MAPS_API_KEY,
        "X-Goog-FieldMask": field_mask,
    }


def run_case(origin_name: str, destination_name: str, mode: str, departure_text: str) -> None:
    print("\n" + "=" * 80)
    print(f"CASE: {origin_name} -> {destination_name} / mode={mode}")

    origin = geocode(origin_name)
    destination = geocode(destination_name)

    print("geocode origin:", origin)
    print("geocode destination:", destination)

    if not origin or not destination:
        print("geocode failed")
        return

    body = build_body(origin, destination, mode, departure_text)
    headers = build_headers("routes")

    print("\nrequest headers:")
    print(json.dumps(headers, ensure_ascii=False, indent=2))

    print("\nrequest body:")
    print(json.dumps(body, ensure_ascii=False, indent=2))

    resp = requests.post(ROUTES_URL, json=body, headers=headers, timeout=20)

    print("\nHTTP status:", resp.status_code)
    print("\nresponse text:")
    print(resp.text)

    try:
        data = resp.json()
    except Exception:
        print("\nresponse is not valid JSON")
        return

    routes = data.get("routes", [])
    print("\nroutes_count:", len(routes))

    if routes:
        first = routes[0]
        summary = {
            "distanceMeters": first.get("distanceMeters"),
            "duration": first.get("duration"),
            "has_legs": bool(first.get("legs")),
            "has_polyline": bool((first.get("polyline") or {}).get("encodedPolyline")),
        }
        print("\nfirst_route_summary:")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("\n⚠️  routes が返っていません")


if __name__ == "__main__":
    require_api_key()
    departure = "2026-04-19 12:05"

    # 成功確認用
    run_case("東京駅", "新宿駅", "car", departure)

    # Claude案の最小修正で再検証
    run_case("東京駅", "新宿駅", "train", departure)
    run_case("福井駅", "東京駅", "train", departure)