# 【ファイル名】route_diagnostic.py
# 【制作日】2026-04-12
# 【用途】
# Google Routes API がフォールバックに落ちる理由を切り分けるための単体診断スクリプト。
# VoyageFlow 本体を起動せずに、駅間・スポット間の検索成否、HTTP ステータス、
# リクエスト body、レスポンス概要を確認する。
#
# 使い方例:
# python route_diagnostic.py --origin-name "福井駅" --destination-name "東京駅" --mode train --departure "2026-04-19 12:05"
#
# 環境変数:
# MAPS_API_KEY=...
#
import argparse
import json
import os
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import requests


ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


def geocode_place(name: str, api_key: str) -> Optional[Tuple[float, float]]:
    params = {"address": name, "key": api_key, "language": "ja", "region": "jp"}
    res = requests.get(GEOCODE_URL, params=params, timeout=15)
    data = res.json()
    if data.get("status") != "OK" or not data.get("results"):
        return None
    loc = data["results"][0]["geometry"]["location"]
    return float(loc["lat"]), float(loc["lng"])


def build_body(
    origin: Tuple[float, float],
    destination: Tuple[float, float],
    mode: str,
    departure: Optional[str],
) -> Dict[str, Any]:
    mode_map = {
        "walk": "WALK",
        "train": "TRANSIT",
        "car": "DRIVE",
        "private_car": "DRIVE",
        "rental_car": "DRIVE",
        "taxi": "DRIVE",
        "bike": "BICYCLE",
    }
    body: Dict[str, Any] = {
        "origin": {
            "location": {
                "latLng": {"latitude": origin[0], "longitude": origin[1]}
            }
        },
        "destination": {
            "location": {
                "latLng": {"latitude": destination[0], "longitude": destination[1]}
            }
        },
        "travelMode": mode_map.get(mode, "TRANSIT"),
        "computeAlternativeRoutes": False,
        "routeModifiers": {
            "avoidTolls": False,
            "avoidHighways": False,
            "avoidFerries": False,
        },
    }
    if departure:
        # ローカル日時をそのまま Z にしない
        dt = datetime.strptime(departure, "%Y-%m-%d %H:%M")
        body["departureTime"] = dt.isoformat()
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin-name", required=True)
    parser.add_argument("--destination-name", required=True)
    parser.add_argument("--mode", default="train")
    parser.add_argument("--departure", default=None, help="YYYY-MM-DD HH:MM")
    parser.add_argument("--save-json", default=None, help="レスポンス保存先")
    args = parser.parse_args()

    api_key = os.getenv("MAPS_API_KEY")
    if not api_key:
        raise SystemExit("MAPS_API_KEY が未設定です")

    origin = geocode_place(args.origin_name, api_key)
    destination = geocode_place(args.destination_name, api_key)

    print("=== geocode ===")
    print(f"origin_name={args.origin_name} -> {origin}")
    print(f"destination_name={args.destination_name} -> {destination}")

    if not origin or not destination:
        raise SystemExit("地名解決に失敗しました")

    body = build_body(origin, destination, args.mode, args.departure)
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": ",".join([
            "routes.duration",
            "routes.distanceMeters",
            "routes.polyline.encodedPolyline",
            "routes.legs.steps.navigationInstruction.instructions",
            "routes.legs.steps.transitDetails.headsign",
            "routes.legs.steps.transitDetails.transitLine.name",
            "routes.legs.steps.transitDetails.transitLine.nameShort",
            "routes.legs.steps.transitDetails.stopDetails.arrivalStop.name",
            "routes.legs.steps.transitDetails.stopDetails.departureStop.name",
        ]),
    }

    print("\n=== request body ===")
    print(json.dumps(body, ensure_ascii=False, indent=2))

    res = requests.post(ROUTES_URL, json=body, headers=headers, timeout=20)

    print("\n=== response status ===")
    print(res.status_code)

    try:
        data = res.json()
    except Exception:
        data = {"raw_text": res.text}

    print("\n=== response summary ===")
    if isinstance(data, dict) and data.get("routes"):
        route = data["routes"][0]
        print(json.dumps({
            "has_routes": True,
            "duration": route.get("duration"),
            "distanceMeters": route.get("distanceMeters"),
            "first_step": (((route.get("legs") or [{}])[0].get("steps") or [{}])[0]),
        }, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))

    if args.save_json:
        Path(args.save_json).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"saved -> {args.save_json}")


if __name__ == "__main__":
    main()
