"""
maps/routes_api.py
Google Routes API（移動時間、経路取得）のラッパー

【改修方針】
- departureTime は「今の時刻」ではなく、「その移動を開始する想定時刻」として扱う
- mode ごとに departureTime の有無を制御する
    - train / TRANSIT: 使う
    - car / taxi / walk / bike: 今回は送らない（TRAFFIC_UNAWARE エラー回避）
- 用途ごとの整理
    - final_itinerary: 完成旅程
    - execution: 実行シミュレーション
    - diagnostic: 診断
"""

import os
import json
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

load_dotenv()


class RoutesAPI:
    """Google Routes API クライアント"""

    BASE_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

    TRANSPORT_MODES = {
        "walk": "WALK",
        "train": "TRANSIT",
        "car": "DRIVE",
        "private_car": "DRIVE",
        "rental_car": "DRIVE",
        "taxi": "DRIVE",
        "bike": "BICYCLE",
    }

    DEPARTURE_TIME_ALLOWED_MODES = {"train"}

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("MAPS_API_KEY")
        if not self.api_key:
            raise ValueError("MAPS_API_KEY 環境変数が設定されていません")

    @staticmethod
    def _normalize_mode(mode: str) -> str:
        return str(mode or "walk").strip().lower()

    @staticmethod
    def _normalize_departure_time(departure_time: datetime) -> datetime:
        if departure_time.tzinfo is not None:
            return departure_time

        tz_name = os.getenv("VOYAGEFLOW_TIMEZONE") or os.getenv("TZ") or "Asia/Tokyo"
        try:
            tzinfo = ZoneInfo(tz_name)
        except Exception:
            tzinfo = datetime.now().astimezone().tzinfo or timezone.utc

        return departure_time.replace(tzinfo=tzinfo)

    @classmethod
    def _format_rfc3339_departure_time(cls, departure_time: datetime) -> str:
        aware_dt = cls._normalize_departure_time(departure_time)
        return aware_dt.isoformat()

    @classmethod
    def should_include_departure_time(
        cls,
        mode: str,
        departure_time: Optional[datetime],
        use_case: str = "final_itinerary",
    ) -> bool:
        normalized_mode = cls._normalize_mode(mode)
        if departure_time is None:
            return False
        if normalized_mode not in cls.DEPARTURE_TIME_ALLOWED_MODES:
            return False
        return use_case in {"final_itinerary", "execution", "diagnostic"}

    def build_request_body(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
        mode: str = "walk",
        departure_time: Optional[datetime] = None,
        use_case: str = "final_itinerary",
    ) -> Dict[str, Any]:
        normalized_mode = self._normalize_mode(mode)
        travel_mode = self.TRANSPORT_MODES.get(normalized_mode, "WALK")

        body: Dict[str, Any] = {
            "origin": {
                "location": {
                    "latLng": {
                        "latitude": origin[0],
                        "longitude": origin[1],
                    }
                }
            },
            "destination": {
                "location": {
                    "latLng": {
                        "latitude": destination[0],
                        "longitude": destination[1],
                    }
                }
            },
            "travelMode": travel_mode,
            "computeAlternativeRoutes": False,
            "routeModifiers": {
                "avoidTolls": False,
                "avoidHighways": False,
                "avoidFerries": False,
            },
        }

        if self.should_include_departure_time(
            mode=normalized_mode,
            departure_time=departure_time,
            use_case=use_case,
        ):
            body["departureTime"] = self._format_rfc3339_departure_time(departure_time)

        return body

    def build_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": "routes",
        }

    def compute_route(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
        mode: str = "walk",
        departure_time: Optional[datetime] = None,
        use_case: str = "final_itinerary",
    ) -> Optional[Dict[str, Any]]:
        normalized_mode = self._normalize_mode(mode)
        body = self.build_request_body(
            origin=origin,
            destination=destination,
            mode=normalized_mode,
            departure_time=departure_time,
            use_case=use_case,
        )
        headers = self.build_headers()

        try:
            response = requests.post(
                self.BASE_URL,
                json=body,
                headers=headers,
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            if not data.get("routes"):
                print(
                    "Routes API: 経路が見つかりません / "
                    f"use_case={use_case} / mode={normalized_mode} / "
                    f"request={json.dumps(body, ensure_ascii=False)} / "
                    f"response={json.dumps(data, ensure_ascii=False)}"
                )
                return None

            route = data["routes"][0]
            duration_str = route.get("duration", "0s")
            duration_seconds = self._parse_duration(duration_str)
            distance_meters = route.get("distanceMeters", 0)

            return {
                "origin": origin,
                "destination": destination,
                "mode": normalized_mode,
                "use_case": use_case,
                "distance_meters": distance_meters,
                "distance_km": distance_meters / 1000 if distance_meters else 0,
                "duration_seconds": duration_seconds,
                "duration_minutes": duration_seconds / 60 if duration_seconds else 0,
                "polyline": route.get("polyline", {}).get("encodedPolyline"),
                "raw_route": route,
                **self._extract_step_summary(route, normalized_mode),
            }
        except requests.RequestException as e:
            response_text = ""
            try:
                response_text = e.response.text if e.response is not None else ""
            except Exception:
                response_text = ""
            print(
                "Routes API リクエストエラー: "
                f"{e} / use_case={use_case} / mode={normalized_mode} / "
                f"request={json.dumps(body, ensure_ascii=False)} / response={response_text}"
            )
            return None
        except Exception as e:
            print(
                "Routes API パースエラー: "
                f"{e} / use_case={use_case} / mode={normalized_mode}"
            )
            return None

    def _extract_step_summary(self, route: Dict[str, Any], mode: str) -> Dict[str, Any]:
        legs = route.get("legs", []) or []
        steps = legs[0].get("steps", []) if legs else []
        first_transit = None

        for step in steps:
            td = step.get("transitDetails") or {}
            if td:
                first_transit = td
                break

        if first_transit:
            line = first_transit.get("transitLine") or {}
            stop_details = first_transit.get("stopDetails") or {}
            dep = (stop_details.get("departureStop") or {}).get("name") or "出発駅"
            arr = (stop_details.get("arrivalStop") or {}).get("name") or "到着駅"
            line_name = line.get("nameShort") or line.get("name") or "電車"
            headsign = first_transit.get("headsign") or ""
            line_simple = f"{line_name}{(' ' + headsign) if headsign else ''}".strip()
            return {
                "route_from": dep,
                "route_to": arr,
                "route_line_simple": line_simple,
            }

        instruction = ""
        if steps:
            instruction = ((steps[0].get("navigationInstruction") or {}).get("instructions")) or ""

        if instruction:
            return {
                "route_from": "出発地",
                "route_to": "目的地",
                "route_line_simple": instruction,
            }

        return {
            "route_from": "出発地",
            "route_to": "目的地",
            "route_line_simple": self.format_route_result({
                "mode": mode,
                "distance_km": route.get("distanceMeters", 0) / 1000,
                "duration_minutes": self._parse_duration(route.get("duration", "0s")) / 60,
            }),
        }

    def compute_distance(self, origin: Tuple[float, float], destination: Tuple[float, float]) -> Optional[float]:
        from math import radians, cos, sin, asin, sqrt

        lon1, lat1 = origin[1], origin[0]
        lon2, lat2 = destination[1], destination[0]

        lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

        dlon = lon2 - lon1
        dlat = lat2 - lat1

        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))
        r = 6371

        return c * r

    @staticmethod
    def _parse_duration(duration_str: str) -> int:
        import re

        total_seconds = 0
        hours_match = re.search(r"(\d+)h", duration_str)
        if hours_match:
            total_seconds += int(hours_match.group(1)) * 3600
        minutes_match = re.search(r"(\d+)m", duration_str)
        if minutes_match:
            total_seconds += int(minutes_match.group(1)) * 60
        seconds_match = re.search(r"(\d+)s", duration_str)
        if seconds_match:
            total_seconds += int(seconds_match.group(1))
        return total_seconds

    def build_google_maps_directions_url(
        self,
        origin_name: str,
        destination_name: str,
        mode: str = "walk",
        departure_time: Optional[datetime] = None,
    ) -> str:
        import urllib.parse

        normalized_mode = self._normalize_mode(mode)
        mode_map = {
            "walk": "walking",
            "train": "transit",
            "car": "driving",
            "private_car": "driving",
            "rental_car": "driving",
            "taxi": "driving",
            "bike": "bicycling",
        }
        travelmode = mode_map.get(normalized_mode, "walking")
        url = (
            "https://www.google.com/maps/dir/?api=1"
            f"&origin={urllib.parse.quote(str(origin_name))}"
            f"&destination={urllib.parse.quote(str(destination_name))}"
            f"&travelmode={travelmode}"
        )

        if self.should_include_departure_time(
            mode=normalized_mode,
            departure_time=departure_time,
            use_case="final_itinerary",
        ):
            try:
                aware_dt = self._normalize_departure_time(departure_time)
                unix_ts = int(aware_dt.astimezone(timezone.utc).timestamp())
                url += f"&departure_time={unix_ts}"
            except Exception:
                pass

        return url

    @staticmethod
    def format_route_result(route_info: Dict[str, Any]) -> str:
        if not route_info:
            return "経路情報なし"

        mode = route_info.get("mode", "unknown")
        distance = route_info.get("distance_km", 0)
        duration = route_info.get("duration_minutes", 0)

        mode_ja = {
            "walk": "徒歩",
            "train": "電車",
            "car": "自家用車",
            "private_car": "自家用車",
            "rental_car": "レンタカー",
            "taxi": "タクシー",
            "bike": "自転車",
        }.get(mode, "不明")

        return f"{mode_ja}: {distance:.1f}km, 約{int(duration)}分"


if __name__ == "__main__":
    routes = RoutesAPI()
    print("=== 経路計算テスト ===")
    origin = (35.6762, 139.7674)
    destination = (35.7100, 139.8107)
    test_departure = datetime(2026, 4, 19, 12, 5)

    for mode in ["walk", "train", "car"]:
        route = routes.compute_route(
            origin,
            destination,
            mode=mode,
            departure_time=test_departure,
            use_case="diagnostic",
        )
        if route:
            print(f"\n{mode}:")
            print(f"  距離: {route['distance_km']:.2f}km")
            print(f"  時間: {route['duration_minutes']:.0f}分")
            print(f"  要約: {route.get('route_line_simple')}")
        else:
            print(f"\n{mode}: 計算失敗")
