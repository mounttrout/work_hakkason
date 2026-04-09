"""
maps/routes_api.py
Google Routes API（移動時間、経路取得）のラッパー
"""

import os
import requests
import json
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


class RoutesAPI:
    """Google Routes API クライアント"""
    
    BASE_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
    
    # 移動手段のマッピング
    TRANSPORT_MODES = {
        "walk": "WALK",
        "train": "TRANSIT",
        "car": "DRIVE",
        "private_car": "DRIVE",
        "rental_car": "DRIVE",
        "taxi": "DRIVE",
        "bike": "BICYCLE",
    }
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初期化
        
        Args:
            api_key: Google API キー（デフォルト: MAPS_API_KEY 環境変数）
        """
        self.api_key = api_key or os.getenv("MAPS_API_KEY")
        if not self.api_key:
            raise ValueError("MAPS_API_KEY 環境変数が設定されていません")
    
    def compute_route(self, origin: Tuple[float, float], destination: Tuple[float, float],
                     mode: str = "walk", departure_time: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        """
        2点間の最短経路と移動時間を計算
        
        Args:
            origin: 出発地点 (lat, lng)
            destination: 目的地点 (lat, lng)
            mode: 移動手段 ("walk", "train", "car", "taxi", "bike")
            departure_time: 出発時刻（デフォルト: 現在時刻）
        
        Returns:
            経路情報辞書、またはエラー時はNone
        """
        
        # 移動手段の変換
        route_preference = self.TRANSPORT_MODES.get(mode.lower(), "WALK")
        
        # リクエストボディの構築
        body = {
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
            "travelMode": route_preference,
            "computeAlternativeRoutes": False,
            "routeModifiers": {
                "avoidTolls": False,
                "avoidHighways": False,
                "avoidFerries": False,
            }
        }
        
        # 出発時刻の指定（TRANSITの場合推奨）
        if departure_time:
            body["departureTime"] = departure_time.isoformat() + "Z"
        
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline,routes.legs.steps.navigationInstruction.instructions,routes.legs.steps.transitDetails.headsign,routes.legs.steps.transitDetails.transitLine.name,routes.legs.steps.transitDetails.transitLine.nameShort,routes.legs.steps.transitDetails.stopDetails.arrivalStop.name,routes.legs.steps.transitDetails.stopDetails.departureStop.name",
        }
        
        try:
            response = requests.post(
                self.BASE_URL,
                json=body,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            
            if not data.get("routes"):
                print(f"Routes API: 経路が見つかりません")
                return None
            
            route = data["routes"][0]
            
            # 移動時間をパース（ISO 8601形式）
            duration_str = route.get("duration", "0s")
            duration_seconds = self._parse_duration(duration_str)
            
            # 距離
            distance_meters = route.get("distanceMeters", 0)
            
            return {
                "origin": origin,
                "destination": destination,
                "mode": mode,
                "distance_meters": distance_meters,
                "distance_km": distance_meters / 1000,
                "duration_seconds": duration_seconds,
                "duration_minutes": duration_seconds / 60,
                "polyline": route.get("polyline", {}).get("encodedPolyline"),
                **self._extract_step_summary(route, mode),
            }
        except requests.RequestException as e:
            print(f"Routes API リクエストエラー: {e}")
            return None
        except Exception as e:
            print(f"Routes API パースエラー: {e}")
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
            "route_line_simple": self.format_route_result({"mode": mode, "distance_km": route.get("distanceMeters", 0)/1000, "duration_minutes": self._parse_duration(route.get("duration", "0s"))/60}),
        }

    def compute_distance(self, origin: Tuple[float, float], destination: Tuple[float, float]) -> Optional[float]:
        """
        2点間の直線距離を計算（簡易版、緯度経度から）
        
        Args:
            origin: 出発地点 (lat, lng)
            destination: 目的地点 (lat, lng)
        
        Returns:
            距離（km）
        """
        from math import radians, cos, sin, asin, sqrt
        
        lon1, lat1 = origin[1], origin[0]
        lon2, lat2 = destination[1], destination[0]
        
        # ハバーサイン公式
        lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
        
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        r = 6371  # 地球の半径（km）
        
        return c * r
    
    @staticmethod
    def _parse_duration(duration_str: str) -> int:
        """
        ISO 8601形式の期間文字列をパース（例: "PT5M30S" → 330秒）
        
        Args:
            duration_str: ISO 8601形式の期間文字列
        
        Returns:
            秒単位の整数
        """
        # 簡易実装: "123s", "5m30s" パターン対応
        import re
        
        total_seconds = 0
        
        # 秒を抽出
        seconds_match = re.search(r'(\d+)s', duration_str)
        if seconds_match:
            total_seconds += int(seconds_match.group(1))
        
        # 分を抽出
        minutes_match = re.search(r'(\d+)m', duration_str)
        if minutes_match:
            total_seconds += int(minutes_match.group(1)) * 60
        
        # 時間を抽出
        hours_match = re.search(r'(\d+)h', duration_str)
        if hours_match:
            total_seconds += int(hours_match.group(1)) * 3600
        
        return total_seconds
    

    def build_google_maps_directions_url(self, origin_name: str, destination_name: str, mode: str = "walk") -> str:
        import urllib.parse
        mode_map = {
            "walk": "walking",
            "train": "transit",
            "car": "driving",
            "private_car": "driving",
            "rental_car": "driving",
            "taxi": "driving",
            "bike": "bicycling",
        }
        travelmode = mode_map.get(str(mode).lower(), "walking")
        return (
            "https://www.google.com/maps/dir/?api=1"
            f"&origin={urllib.parse.quote(str(origin_name))}"
            f"&destination={urllib.parse.quote(str(destination_name))}"
            f"&travelmode={travelmode}"
        )

    @staticmethod
    def format_route_result(route_info: Dict[str, Any]) -> str:
        """
        経路情報を人間が読みやすい形式にフォーマット
        
        Args:
            route_info: compute_route の戻り値
        
        Returns:
            フォーマットされた文字列
        """
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


# テスト用
if __name__ == "__main__":
    routes = RoutesAPI()
    
    # テスト: 経路計算
    print("=== 経路計算テスト ===")
    # 東京駅からスカイツリー
    origin = (35.6762, 139.7674)  # 東京駅
    destination = (35.7100, 139.8107)  # スカイツリー
    
    for mode in ["walk", "train"]:
        route = routes.compute_route(origin, destination, mode=mode)
        if route:
            print(f"\n{mode}:")
            print(f"  距離: {route['distance_km']:.2f}km")
            print(f"  時間: {route['duration_minutes']:.0f}分")
        else:
            print(f"\n{mode}: 計算失敗")
